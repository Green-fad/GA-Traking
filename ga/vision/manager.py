"""Gestion multi-cameras : un thread par camera, detection + tracking, publication d'evenements.

Contrat de sortie (payload TRACKS_UPDATED) :
    {"camera_id": str, "ts": float, "tracks": [
        {"id": int, "classe": str, "bbox": [x1,y1,x2,y2], "centre": [cx,cy],
         "vitesse_px": [vx,vy], "score": float}
    ]}
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional

import numpy as np

from ga.core.config import CameraConfig, AIConfig
from ga.core.events import EventBus, EventType, GAEvent, Severity
from ga.core.logging import get_logger
from ga.core.registry import GAModule, HealthStatus
from ga.track.bytetrack import ByteTracker
from ga.vision.capture import VideoSource
from ga.vision.detector import BaseDetector, create_detector

log = get_logger("ga.vision.manager")


class CameraWorker:
    """Boucle de traitement d'une camera : lecture -> detection -> suivi -> publication."""

    def __init__(self, cfg: CameraConfig, ai_cfg: AIConfig, bus: EventBus,
                 detector: BaseDetector, loop_file: bool = False) -> None:
        self.cfg = cfg
        self.bus = bus
        self.detector = detector
        self.source = VideoSource(cfg.source, cfg.fps_limit, loop_file=loop_file)
        self.tracker = ByteTracker(high_thresh=ai_cfg.track_high_thresh,
                                   low_thresh=ai_cfg.track_low_thresh,
                                   max_time_lost=ai_cfg.track_buffer)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_tracks: list[dict] = []
        self._processed = 0
        self._fps = 0.0
        self._last_frame_ts: float | None = None
        self._last_frame_pub = 0.0

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"cam-{self.cfg.id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self.source.release()

    def _run(self) -> None:
        log.info("camera demarree", extra={"ctx": {"camera": self.cfg.id, "source": self.cfg.source}})
        fps_counter, fps_t0 = 0, time.monotonic()
        while not self._stop.is_set():
            frame = self.source.read()
            if frame is None:
                log.warning("source video terminee/indisponible",
                            extra={"ctx": {"camera": self.cfg.id, "erreur": self.source.last_error}})
                self._stop.wait(2.0)  # patience puis nouvelle tentative de reconnexion
                continue
            ts = time.time()
            detections = self.detector.detect(frame)
            tracks = self.tracker.update(detections)
            payload_tracks = []
            for t in tracks:
                cx, cy = t.center
                vx, vy = t.velocity
                payload_tracks.append({
                    "id": t.track_id, "classe": t.cls_name, "score": round(t.score, 3),
                    "bbox": [round(v, 1) for v in t.bbox],
                    "centre": [round(cx, 1), round(cy, 1)],
                    "vitesse_px": [round(vx, 2), round(vy, 2)],
                })
            self._last_tracks = payload_tracks
            self._last_frame_ts = ts
            self._processed += 1
            fps_counter += 1
            now = time.monotonic()
            if now - fps_t0 >= 5.0:
                self._fps = fps_counter / (now - fps_t0)
                fps_counter, fps_t0 = 0, now
            self.bus.publish_threadsafe(GAEvent(
                type=EventType.TRACKS_UPDATED, camera_id=self.cfg.id,
                payload={"ts": ts, "tracks": payload_tracks},
            ))
            # échantillon d'image pour GA-SECURITY (analyse incendie) : ~1 image / 2 s
            if ts - self._last_frame_pub > 2.0:
                self._last_frame_pub = ts
                self.bus.publish_threadsafe(GAEvent(
                    type=EventType.CAMERA_FRAME, camera_id=self.cfg.id,
                    payload={"ts": ts, "frame": frame},
                ))
        log.info("camera arretee", extra={"ctx": {"camera": self.cfg.id, "images_traitees": self._processed}})

    def status(self) -> dict:
        return {
            "camera_id": self.cfg.id, "nom": self.cfg.name, "source": self.cfg.source,
            "actif": self._thread.is_alive() if self._thread else False,
            "images_traitees": self._processed, "fps": round(self._fps, 1),
            "pistes_actives": len(self._last_tracks),
            "derniere_image": self._last_frame_ts,
            "source_infos": self.source.status(),
        }

    def healthy(self) -> bool:
        alive = bool(self._thread and self._thread.is_alive())
        return alive or (self._processed == 0 and self.source.reconnects == 0)


class CameraManager(GAModule):
    """GA-VISION : orchestration de tous les flux camera (GAModule du registre)."""

    name = "ga_vision"

    def __init__(self, cameras: list[CameraConfig], ai_cfg: AIConfig, bus: EventBus,
                 *, loop_files: bool = False) -> None:
        self.cameras_cfg = cameras
        self.ai_cfg = ai_cfg
        self.bus = bus
        self.loop_files = loop_files
        self.detector: BaseDetector | None = None
        self.workers: dict[str, CameraWorker] = {}

    async def start(self) -> None:
        if self.detector is None:
            self.detector = create_detector(self.ai_cfg)
        for cfg in self.cameras_cfg:
            if cfg.enabled:
                worker = CameraWorker(cfg, self.ai_cfg, self.bus, self.detector, loop_file=self.loop_files)
                worker.start()
                self.workers[cfg.id] = worker
        log.info("GA-VISION demarre", extra={"ctx": {"cameras": len(self.workers), "detecteur": self.detector.name}})

    async def stop(self) -> None:
        for worker in self.workers.values():
            worker.stop()
        self.workers.clear()
        if self.detector:
            self.detector.close()

    def health(self) -> HealthStatus:
        if not self.workers:
            return HealthStatus(False, "aucune camera active")
        all_ok = all(w.healthy() for w in self.workers.values())
        return HealthStatus(all_ok, f"{len(self.workers)} flux", **{
            w.cfg.id: {"actif": w.healthy(), "images": w._processed} for w in self.workers.values()})

    def status_all(self) -> list[dict]:
        return [w.status() for w in self.workers.values()]

    def camera_status(self, camera_id: str) -> Optional[dict]:
        worker = self.workers.get(camera_id)
        return worker.status() if worker else None
