"""Test d'integration : pipeline complet sur video synthetique.

Verifie la chaine REELLE : detection -> tracking -> calibration/vitesse ->
evenements routiers -> intrusion -> alertes -> dossiers -> base -> rapport.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

cv2 = pytest.importorskip("cv2")

from ga.core.config import AppConfig, CameraConfig
from ga.core.events import EventBus, EventType, GAEvent
from ga.core.pipeline import EventProcessor
from ga.data import database as db
from ga.data.media import MediaStore
from ga.data.repositories import AlertRepo, DossierRepo, EventRepo, SyncRepo
from ga.track.bytetrack import ByteTracker
from ga.vision.detector import MOG2Detector
from tools.make_demo_video import calibration_points, ecrire_video, render_frame, scene_demo, vitesse_reelle_kmh

FRAMES = 420
CAM_ID = "cam-test"


@pytest.fixture(scope="module")
def pipeline_results(tmp_path_factory):
    """Exécuter le pipeline reel sur une video synthetique (une fois pour le module)."""
    tmp = tmp_path_factory.mktemp("integration")
    scene = scene_demo()
    video = ecrire_video(scene, FRAMES, tmp / "scene.mp4")

    cfg = AppConfig()
    cfg.ai.detector = "mog2"
    cfg.ai.mog2_history = 1200
    cfg.ai.mog2_var_threshold = 30
    cfg.ai.mog2_min_area = 400
    cfg.road.speed_limit_kmh = 80.0
    # tolerance d'arret : le bruit des boites MOG2 peut depasser 3 km/h sur un objet quasi statique
    cfg.road.stopped_speed_kmh = 5.0
    cfg.road.stopped_min_seconds = 8.0
    cfg.road.speed_smoothing_alpha = 0.25
    cfg.security.fire_min_frames = 5
    cfg.cameras = [CameraConfig(id=CAM_ID, name="Test", source="demo", analysis=calibration_points(scene))]

    from ga.data import database as database_mod
    database_mod.init_db(f"sqlite:///{tmp}/integration.db")

    bus = EventBus()
    processor = EventProcessor(cfg, bus, MediaStore(str(tmp / "media")), cloud_sync=True)
    import asyncio
    asyncio.run(processor.start(start_bus=False))

    detector = MOG2Detector(min_area=400, history=1200, var_threshold=30)
    tracker = ByteTracker(max_time_lost=30)
    # lecture du fichier video compresse (meme chaine que la demonstration)
    from ga.vision.capture import VideoSource
    source = VideoSource(str(video), fps_limit=0)
    f = 0
    while True:
        frame = source.read()
        if frame is None:
            break
        detections = detector.detect(frame)
        tracks = tracker.update(detections)
        payload = [{"id": t.track_id, "classe": t.cls_name, "score": round(t.score, 2),
                    "bbox": [float(v) for v in t.bbox],
                    "centre": [float(c) for c in t.center],
                    "vitesse_px": [float(v) for v in t.velocity]} for t in tracks]
        bus.publish_sync(GAEvent(type=EventType.TRACKS_UPDATED, camera_id=CAM_ID,
                                 payload={"ts": f / scene.fps, "tracks": payload}))
        if f % 60 == 0:
            bus.publish_sync(GAEvent(type=EventType.CAMERA_FRAME, camera_id=CAM_ID,
                                     payload={"ts": f / scene.fps, "frame": frame.copy()}))
        f += 1
    return {"scene": scene, "tmp": tmp}


class TestPipelineIntegration:
    def test_evenements_routiers_detectes(self, pipeline_results):
        with db.session_scope() as session:
            types = {ev.type for ev in EventRepo(session).query(days=1, limit=2000)}
        assert "franchissement_ligne" in types, f"comptage manquant : {types}"
        assert "vehicule_arrete" in types, f"arret manquant : {types}"
        assert "exces_vitesse_candidat" in types, f"exces manquant : {types}"

    def test_intrusion_detectee(self, pipeline_results):
        with db.session_scope() as session:
            intrusions = [e for e in EventRepo(session).query(days=1, limit=2000)
                          if e.type == "intrusion"]
        assert len(intrusions) >= 1, "le pieton en zone interdite n'a pas ete detecte"

    def test_alertes_creees(self, pipeline_results):
        with db.session_scope() as session:
            alerts = AlertRepo(session).query(days=1, limit=500)
        by_type = {a.type for a in alerts}
        assert "intrusion" in by_type
        assert any(a.severity == "critical" for a in alerts)

    def test_dossiers_de_preuve(self, pipeline_results):
        with db.session_scope() as session:
            dossiers = DossierRepo(session).query(limit=100)
        assert len(dossiers) >= 2, f"dossiers crees : {len(dossiers)}"
        assert all(d.status == "a_verifier" for d in dossiers), "pas de validation automatique"

    def test_images_de_preuve_sauvegardees(self, pipeline_results):
        with db.session_scope() as session:
            dossiers = DossierRepo(session).query(limit=100)
        with_images = [d for d in dossiers if d.evidence.get("images")]
        assert with_images, "au moins un dossier doit contenir une image de preuve"
        media = MediaStore(str(pipeline_results["tmp"] / "media"))
        path = media.resolve(with_images[0].evidence["images"][0]["chemin"])
        assert path.exists() and path.stat().st_size > 500

    def test_vitesse_mesuree_conforme_a_la_verite(self, pipeline_results):
        """Le vehicule rapide roule a ~89 km/h (verite terrain) : la mesure doit l'approcher."""
        scene = pipeline_results["scene"]
        with db.session_scope() as session:
            exces = [e for e in EventRepo(session).query(days=1, limit=2000)
                     if e.type == "exces_vitesse_candidat"]
        assert exces, "aucune mesure d'exces de vitesse"
        verite = vitesse_reelle_kmh(scene.actors[1], scene)
        assert any(abs(e.payload["vitesse_kmh"] - verite) / verite < 0.15 for e in exces), \
            f"aucune mesure proche de la verite {verite:.1f} km/h : " \
            f"{[e.payload['vitesse_kmh'] for e in exces]}"

    def test_synchronisation_mise_en_file(self, pipeline_results):
        """cloud_sync=True dans le test : les alertes/evenements doivent etre en file."""
        with db.session_scope() as session:
            stats = SyncRepo(session).stats()
        assert stats.get("pending", 0) + stats.get("sent", 0) >= 1, "file de sync vide"
