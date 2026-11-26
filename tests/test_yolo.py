"""Tests du detecteur YOLO reel (poids officiels, inferance ONNX Runtime).

Ces tests sont automatiquement ignores si le modele n'est pas present
(``python tools/fetch_model.py`` pour l'acquerir) — la suite reste verte
sur une machine sans modele.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ga.vision.detector import DetectorUnavailable, YOLOOnnxDetector
from ga.vision.models import ModelsRegistry

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

MODEL = Path("models/yolov8n.onnx")
BUS_IMAGE = Path("models/_test_bus.jpg")

pytestmark = pytest.mark.skipif(
    not MODEL.exists(), reason="models/yolov8n.onnx absent — lancer python tools/fetch_model.py")


@pytest.fixture(scope="module")
def detector() -> YOLOOnnxDetector:
    return YOLOOnnxDetector(str(MODEL))


class TestYOLOReel:
    def test_inference_sur_image_reelle(self, detector: YOLOOnnxDetector):
        """Image reelle (bus.jpg, Ultralytics) : le bus et des personnes doivent etre detectes."""
        if not BUS_IMAGE.exists():
            pytest.skip("image de test absente — relancer tools/fetch_model.py")
        frame = cv2.imread(str(BUS_IMAGE))
        detections = detector.detect(frame)
        assert len(detections) >= 2, f"trop peu de detections : {len(detections)}"
        labels = {d.cls_name for d in detections}
        assert "personne" in labels, f"personnes non detectees : {labels}"

    def test_format_des_detections(self, detector: YOLOOnnxDetector):
        frame = np.full((640, 640, 3), 120, dtype=np.uint8)
        detections = detector.detect(frame)
        for d in detections:  # scene vide -> probablement vide, mais jamais incoherent
            assert d.bbox.shape == (4,)
            assert 0.0 <= d.score <= 1.0
            assert d.bbox[0] <= d.bbox[2] and d.bbox[1] <= d.bbox[3]

    def test_registre_modele_verifie_l_integrite(self):
        registry = ModelsRegistry()
        entry = registry.get("yolov8n")
        assert entry is not None, "modele non enregistre — relancer tools/fetch_model.py"
        assert registry.verify_integrity("yolov8n", entry["version"]), \
            "le fichier du modele ne correspond plus a l'empreinte enregistree"

    def test_auto_selectionne_yolo_quand_le_modele_existe(self):
        from ga.core.config import AIConfig
        from ga.vision.detector import create_detector

        detector = create_detector(AIConfig(detector="auto", model_path=str(MODEL)))
        assert detector.name.startswith("yolo_onnx"), \
            "le detecteur auto doit choisir YOLO quand le modele est present"
