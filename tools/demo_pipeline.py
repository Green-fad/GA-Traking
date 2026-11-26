"""Demonstration fonctionnelle GAtraking : pipeline complet de bout en bout.

Chaine executee reellement :
    video synthetique -> capture -> detection (MOG2 ou YOLO) -> ByteTrack
    -> vitesses calibrees -> evenements routiers -> zones -> incendie
    -> alertes + dossiers de preuve -> base de donnees -> rapport operationnel
    -> video annotee + resume JSON.

Usage : python tools/demo_pipeline.py [--frames 900] [--output demo_output]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np

from ga.core.config import AppConfig, CameraConfig
from ga.core.events import EventBus, EventType, GAEvent
from ga.data import database as db
from ga.data.media import MediaStore
from ga.data.repositories import AlertRepo, DossierRepo, EventRepo
from ga.core.pipeline import EventProcessor
from ga.intelligence.reports import ReportGenerator
from ga.track.bytetrack import ByteTracker
from ga.vision.capture import VideoSource
from ga.vision.detector import MOG2Detector
from tools.make_demo_video import calibration_points, ecrire_video, render_frame, scene_demo, vitesse_reelle_kmh

CAM_ID = "cam-demo"


def build_config(frames: int) -> AppConfig:
    cfg = AppConfig()
    cfg.site.name = "Demo GAtraking"
    cfg.ai.detector = "mog2"
    cfg.ai.mog2_history = 1200       # absorption lente : les vehicules arretes restent visibles
    cfg.ai.mog2_var_threshold = 30
    cfg.ai.mog2_min_area = 400
    cfg.ai.track_high_thresh = 0.5
    cfg.ai.track_low_thresh = 0.1
    cfg.road.speed_limit_kmh = 80.0
    cfg.road.stopped_speed_kmh = 5.0   # tolerance au tremblement des boites de detection
    cfg.road.stopped_min_seconds = 8.0
    cfg.road.speed_smoothing_alpha = 0.25
    cfg.road.speed_min_samples = 4
    cfg.security.intrusion_min_frames = 6
    cfg.security.fire_min_frames = 5
    scene = scene_demo()
    analysis = calibration_points(scene)
    cfg.cameras = [CameraConfig(id=CAM_ID, name="Camera demo", source="demo", enabled=True,
                                fps_limit=30.0, analysis=analysis)]
    return cfg


def run_demo(config_path: str | None = None, output_dir: str = "demo_output",
             frames: int = 900) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # 1. scene synthetique (verite terrain connue)
    scene = scene_demo()
    video_path = ecrire_video(scene, frames, out / "scene_demo.mp4")
    verite = {a.nom: round(vitesse_reelle_kmh(a, scene), 1) for a in scene.actors}

    cfg = build_config(frames)
    # base de demonstration neuve a chaque execution (resultats reproductibles)
    db_file = Path("demo_output/demo.db")
    if db_file.exists():
        db_file.unlink()
    db.init_db("sqlite:///demo_output/demo.db")
    bus = EventBus()
    media = MediaStore("data/media", retention_days=30)
    processor = EventProcessor(cfg, bus, media, cloud_sync=False)
    asyncio.run(processor.start(start_bus=False))  # demo synchrone : pas de worker asyncio

    # 2. pipeline reel : detection MOG2 -> ByteTrack -> analyse metier
    detector = MOG2Detector(conf_threshold=cfg.ai.conf_threshold, min_area=cfg.ai.mog2_min_area,
                            history=cfg.ai.mog2_history, var_threshold=cfg.ai.mog2_var_threshold)
    tracker = ByteTracker(high_thresh=cfg.ai.track_high_thresh, low_thresh=cfg.ai.track_low_thresh,
                          max_time_lost=cfg.ai.track_buffer)
    source = VideoSource(str(video_path), fps_limit=0, loop_file=False)

    writer = cv2.VideoWriter(str(out / "demo_annote.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                             scene.fps, (scene.largeur, scene.hauteur))
    frame_id = 0
    vitesses_ctx = processor.context_for(CAM_ID)["vitesses"]
    compteur_detections = 0

    while True:
        frame = source.read()
        if frame is None:
            break
        detections = detector.detect(frame)
        compteur_detections += len(detections)
        tracks = tracker.update(detections)
        payload = [{"id": t.track_id, "classe": t.cls_name, "score": round(t.score, 2),
                    "bbox": [round(v, 1) for v in t.bbox],
                    "centre": [round(c, 1) for c in t.center],
                    "vitesse_px": [round(v, 1) for v in t.velocity]} for t in tracks]
        bus.publish_sync(GAEvent(type=EventType.TRACKS_UPDATED, camera_id=CAM_ID,
                                 payload={"ts": frame_id / scene.fps, "tracks": payload}))
        if frame_id % 60 == 0:  # echantillon pour GA-SECURITY (incendie) ~1/2s
            bus.publish_sync(GAEvent(type=EventType.CAMERA_FRAME, camera_id=CAM_ID,
                                     payload={"ts": frame_id / scene.fps, "frame": frame.copy()}))

        # 3. annotation video : boites + identites + vitesses mesurees
        for t in tracks:
            x1, y1, x2, y2 = [int(v) for v in t.bbox]
            est = vitesses_ctx.current(t.track_id)
            speed_txt = f"{est.speed_kmh:.0f} km/h" if est and est.samples >= 4 else ""
            cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 220, 80), 2)
            cv2.putText(frame, f"#{t.track_id} {t.cls_name} {speed_txt}", (x1, max(12, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        writer.write(frame)
        frame_id += 1
    writer.release()
    source.release()
    asyncio.run(processor.stop())

    # 4. lecture des resultats reels dans la base
    with db.session_scope() as session:
        events = EventRepo(session).query(days=1, limit=2000)
        par_type: dict[str, int] = {}
        for ev in events:
            par_type[ev.type] = par_type.get(ev.type, 0) + 1
        alerts = AlertRepo(session).query(days=1, limit=500)
        dossiers = DossierRepo(session).query(limit=500)

    # 5. rapport operationnel (GA-INTELLIGENCE)
    rapport = ReportGenerator(site_name="Demo GAtraking").generate(days=1)

    resume = {
        "images_traitees": frame_id,
        "detections": compteur_detections,
        "evenements_par_type": par_type,
        "alertes": [{"type": a.type, "gravite": a.severity, "message": a.message} for a in alerts],
        "dossiers": [{"type": d.kind, "statut": d.status} for d in dossiers],
        "vitesses_reelles_kmh": verite,
        "rapport": rapport["chemin"],
        "duree_traitement_s": round(time.time() - t0, 1),
        "videos": {"scene": str(video_path), "annotee": str(out / "demo_annote.mp4")},
    }
    (out / "demo_resume.json").write_text(json.dumps(resume, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resume, indent=2, ensure_ascii=False))
    return resume


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=900)
    parser.add_argument("--output", default="demo_output")
    args = parser.parse_args()
    run_demo(output_dir=args.output, frames=args.frames)
