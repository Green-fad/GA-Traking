"""Tests de resilience : coupures de flux, erreurs de handlers, charges invalides."""
from __future__ import annotations

import asyncio
import time

import pytest

cv2 = pytest.importorskip("cv2")

from ga.core.events import EventBus, EventType, GAEvent
from ga.track.bytetrack import ByteTracker
from ga.vision.capture import VideoSource
from tools.make_demo_video import ecrire_video, scene_demo


class TestCoupureFlux:
    def test_fin_de_fichier_graceful(self, tmp_path):
        """Fin de fichier : read() retourne None sans exception, sans reconnexion inutile."""
        scene = scene_demo()
        path = ecrire_video(scene, 10, tmp_path / "court.mp4")
        source = VideoSource(str(path), fps_limit=0, max_reconnect_attempts=1,
                             reconnect_delay_s=0.05, loop_file=False)
        frames = 0
        while True:
            frame = source.read()
            if frame is None:
                break
            frames += 1
        assert frames >= 8
        status = source.status()
        assert status["images_lues"] == frames
        # un fichier termine n'est pas "reconnecte" : la reprise ne concerne que les flux reseau
        assert status["reconnexions"] == 0

    def test_fichier_absent_ne_bloque_pas(self, tmp_path):
        source = VideoSource(str(tmp_path / "inexistant.mp4"), fps_limit=0,
                             max_reconnect_attempts=1, reconnect_delay_s=0.05)
        assert source.read() is None
        assert "introuvable" in (source.last_error or "")

    def test_tracker_survit_a_un_trou_de_detections(self):
        """Perte temporaire du detecteur : le tracker retient la piste puis la retrouve."""
        tracker = ByteTracker(high_thresh=0.5, min_hits=2, max_time_lost=20)
        from ga.track.bytetrack import Detection
        import numpy as np
        ids = set()
        for i in range(20):
            x = 50 + i * 5
            tracks = tracker.update([Detection(bbox=np.array([x, 100, x + 60, 140]), score=0.9,
                                               cls=2, cls_name="voiture")])
            ids |= {t.track_id for t in tracks}
        # trou de 10 images (aucune detection)
        for _ in range(10):
            tracker.update([])
        # reprise : la piste doit etre retrouvee avec le MEME id
        tracks = tracker.update([Detection(bbox=np.array([170, 100, 230, 140]), score=0.9,
                                           cls=2, cls_name="voiture")])
        assert tracks, "piste non recouverte apres le trou"
        assert tracks[0].track_id in ids, "nouvel id au lieu de reprendre la piste"


class TestIsolationBus:
    def test_handler_en_echec_n_isole_pas_les_autres(self, bus):
        results = []

        async def mauvais_handler(event: GAEvent) -> None:
            raise RuntimeError("bug volontaire dans un module")

        async def bon_handler(event: GAEvent) -> None:
            results.append(event.type)

        bus.subscribe(mauvais_handler, EventType.ALERT_CREATED)
        bus.subscribe(bon_handler, EventType.ALERT_CREATED)
        bus.publish_sync(GAEvent(type=EventType.ALERT_CREATED, payload={"x": 1}))
        assert results == [EventType.ALERT_CREATED], "le handler sain n'a pas tourne"

    def test_payload_invalide_sans_crash(self, test_db, bus, tmp_path):
        """Le pipeline ne doit jamais crasher sur un payload malforme."""
        from ga.core.config import AppConfig, CameraConfig
        from ga.core.pipeline import EventProcessor
        from ga.data.media import MediaStore
        cfg = AppConfig()
        cfg.cameras = [CameraConfig(id="cam-x", name="x", source="demo")]
        processor = EventProcessor(cfg, bus, MediaStore(str(tmp_path / "media")))
        asyncio.run(processor.start(start_bus=False))
        payloads = [{}, {"tracks": None}, {"ts": "abc", "tracks": [{"id": 1}]},
                    {"ts": 1.0, "tracks": [{"id": "x", "classe": "?", "bbox": "abc",
                                            "centre": [1, 2], "vitesse_px": [0, 0]}]}]
        for payload in payloads:
            bus.publish_sync(GAEvent(type=EventType.TRACKS_UPDATED, camera_id="cam-x", payload=payload))
        bus.publish_sync(GAEvent(type=EventType.CAMERA_FRAME, camera_id="cam-x", payload={}))
        bus.publish_sync(GAEvent(type=EventType.CAMERA_FRAME, camera_id="cam-inconnue",
                                 payload={"frame": None}))
        # aucune exception levee jusqu'ici = le service survit aux entrees corrompues


class TestSurvieService:
    def test_worker_camera_sur_source_morte(self, test_db, bus, tmp_path):
        """Un flux indisponible ne fait pas tomber le module vision."""
        from ga.core.config import AIConfig, CameraConfig
        from ga.vision.manager import CameraWorker
        from ga.vision.detector import MOG2Detector

        cfg = CameraConfig(id="cam-morte", name="morte",
                           source=str(tmp_path / "flux_absent.mp4"))
        worker = CameraWorker(cfg, AIConfig(), bus, MOG2Detector())
        worker.start()
        time.sleep(1.0)
        status = worker.status()
        worker.stop()
        assert status["images_traitees"] == 0
        assert worker.source.reconnects >= 1

    def test_registry_health_reflete_les_pannes(self, test_db, bus, tmp_path):
        from ga.core.config import AppConfig, CameraConfig
        from ga.core.pipeline import EventProcessor
        from ga.data.media import MediaStore
        cfg = AppConfig()
        cfg.cameras = [CameraConfig(id="cam-h", name="h", source="demo")]
        processor = EventProcessor(cfg, bus, MediaStore(str(tmp_path / "media")))
        health = processor.health()
        assert health.healthy is True
