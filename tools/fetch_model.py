"""Acquisition et enregistrement des poids YOLO pour GAtraking.

Telecharge les poids officiels Ultralytics, les convertit en ONNX (si torch
disponible), enregistre la version dans le registre (models/registry.json)
avec empreinte SHA-256 et verifie l'integrite.

Usage :
    python tools/fetch_model.py            # telecharge pt, convertit ONNX, enregistre
    python tools/fetch_model.py --skip-pt  # seulement l'enregistrement d'un onnx existant
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ga.vision.models import ModelsRegistry, file_sha256

PT_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt"
PT_PATH = Path("models/yolov8n.pt")
ONNX_PATH = Path("models/yolov8n.onnx")
# libelles metier des classes COCO exploitees par la plateforme (0-7 : personnes/vehicules)
CLASSES = ["personne", "velo", "voiture", "moto", "bus", "camionnette", "camion"]


def download_pt() -> bool:
    if PT_PATH.exists() and PT_PATH.stat().st_size > 1_000_000:
        print(f"[ok] poids deja presents : {PT_PATH}")
        return True
    print(f"[..] telechargement {PT_URL}")
    try:
        import urllib.request

        PT_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(PT_URL, PT_PATH)
    except Exception as exc:
        print(f"[!!] telechargement impossible : {exc}")
        return False
    return PT_PATH.exists() and PT_PATH.stat().st_size > 1_000_000


def convert_onnx() -> bool:
    if ONNX_PATH.exists() and ONNX_PATH.stat().st_size > 1_000_000:
        print(f"[ok] modele ONNX deja present : {ONNX_PATH}")
        return True
    print("[..] conversion pt -> ONNX (ultralytics)")
    try:
        from ultralytics import YOLO

        model = YOLO(str(PT_PATH))
        exported = model.export(format="onnx", opset=12, imgsz=640, simplify=False)
        produced = Path(exported)
        if produced != ONNX_PATH and produced.exists():
            produced.replace(ONNX_PATH)
    except ImportError as exc:
        print(f"[!!] conversion impossible (pip install ultralytics) : {exc}")
        return False
    return ONNX_PATH.exists() and ONNX_PATH.stat().st_size > 1_000_000


def register() -> None:
    registry = ModelsRegistry()
    sha = file_sha256(ONNX_PATH)
    entry = registry.register("yolov8n", "8.3", str(ONNX_PATH), classes=CLASSES)
    print(f"[ok] enregistre : yolov8n 8.3 — sha256 {entry['sha256'][:16]}…")
    assert registry.verify_integrity("yolov8n", "8.3"), "integrite invalide juste apres l'enregistrement"
    print("[ok] integrite verifiee")


def smoke_test() -> bool:
    """Validation reelle : detection sur l'image de test Ultralytics (bus.jpg)."""
    try:
        import urllib.request

        import cv2

        from ga.vision.detector import YOLOOnnxDetector

        img_path = Path("models/_test_bus.jpg")
        if not img_path.exists():
            urllib.request.urlretrieve("https://ultralytics.com/images/bus.jpg", img_path)
        frame = cv2.imread(str(img_path))
        detector = YOLOOnnxDetector(str(ONNX_PATH))
        detections = detector.detect(frame)
        labels = sorted({d.cls_name for d in detections})
        print(f"[ok] inference reelle : {len(detections)} objets detectes ({', '.join(labels) or 'aucun'})")
        return len(detections) > 0
    except Exception as exc:
        print(f"[!!] test d'inference en echec : {exc}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-pt", action="store_true", help="ne pas (re)telecharger les poids .pt")
    args = parser.parse_args()
    ok = True
    if not args.skip_pt:
        ok = download_pt() and ok
        ok = convert_onnx() and ok
    if ok:
        register()
        ok = smoke_test()
    sys.exit(0 if ok else 1)
