"""Tests GA-VISION : detecteur MOG2 sur scene synthetique, capture, fabrique."""
from __future__ import annotations

import numpy as np
import pytest

from ga.core.config import AIConfig
from ga.track.bytetrack import Detection
from ga.vision.capture import VideoSource
from ga.vision.detector import MOG2Detector, create_detector

cv2 = pytest.importorskip("cv2")

from tools.make_demo_video import ecrire_video, render_frame, scene_demo  # noqa: E402


class TestMOG2:
    def test_detecte_vehicule_en_mouvement(self):
        scene = scene_demo()
        detector = MOG2Detector(min_area=400, history=300)
        best_count = 0
        for f in range(80, 160):  # apres le warmup
            frame = render_frame(scene, f)
            detections = detector.detect(frame)
            best_count = max(best_count, len(detections))
        assert best_count >= 2, f"MOG2 n'a pas detecte les vehicules (max {best_count})"

    def test_scene_statique_sans_detection(self):
        scene = scene_demo()
        scene.actors = []           # scene vide
        scene.incendie_a = 0
        detector = MOG2Detector(min_area=400)
        for _ in range(40):
            detections = detector.detect(render_frame(scene, 0))
        assert detections == [], "une scene figee ne doit rien detecter"


class TestFabrique:
    def test_auto_bascule_sur_mog2_sans_modele(self, tmp_path):
        cfg = AIConfig(detector="auto", model_path=str(tmp_path / "absent.onnx"))
        detector = create_detector(cfg)
        assert detector.name.startswith("mog2")

    def test_mog2_forcé(self):
        detector = create_detector(AIConfig(detector="mog2"))
        assert detector.name.startswith("mog2")


class TestCapture:
    def test_lecture_fichier(self, tmp_path):
        scene = scene_demo()
        path = ecrire_video(scene, 20, tmp_path / "clip.mp4")
        source = VideoSource(str(path), fps_limit=0, max_reconnect_attempts=0)
        read = 0
        while True:
            frame = source.read()
            if frame is None:
                break
            read += 1
        assert read >= 18, f"seulement {read} images lues"
        assert source.status()["images_lues"] == read
