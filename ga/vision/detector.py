"""Detection d'objets : YOLO (ONNX Runtime, CPU ou GPU) + detecteur de secours MOG2.

L'architecture assure la continuite de service : si le modele YOLO est absent
ou l'acceleration indisponible, le detecteur de fond MOG2 prend le relais
(fonctionnement hors-ligne garanti).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ga.core.config import AIConfig
from ga.core.logging import get_logger
from ga.track.bytetrack import Detection

log = get_logger("ga.vision.detector")

# Classes COCO exploitees par GAtraking (identifiant -> libelle FR)
COCO_CLASSES = {
    0: "personne", 1: "velo", 2: "voiture", 3: "moto", 5: "bus", 6: "camionnette", 7: "camion",
}
VEHICLE_CLASSES = {"voiture", "moto", "bus", "camionnette", "camion", "velo"}


class DetectorUnavailable(RuntimeError):
    """Le detecteur demande n'est pas utilisable sur cette machine."""


class BaseDetector(ABC):
    name: str = "base"

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[Detection]: ...

    def close(self) -> None:  # pragma: no cover - ressources optionnelles
        pass

    def info(self) -> dict:
        return {"nom": self.name}


class YOLOOnnxDetector(BaseDetector):
    """YOLO v8/v5 exporte ONNX : pretraitement letterbox + decodage + NMS."""

    IMG_SIZE = 640

    def __init__(self, model_path: str, conf_threshold: float = 0.35, iou_threshold: float = 0.45) -> None:
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise DetectorUnavailable("onnxruntime non installe") from exc
        path = Path(model_path)
        if not path.exists():
            raise DetectorUnavailable(f"modele introuvable : {model_path}")
        providers = ort.get_available_providers()
        chosen = ["CPUExecutionProvider"]
        if "CUDAExecutionProvider" in providers:
            chosen = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(path), providers=chosen)
        self.input_name = self.session.get_inputs()[0].name
        self.device = "gpu" if "CUDA" in chosen[0] else "cpu"
        self.name = f"yolo_onnx ({self.device})"
        log.info("YOLO ONNX charge", extra={"ctx": {"modele": str(path), "device": self.device, "providers": providers}})

    def _letterbox(self, frame: np.ndarray) -> tuple[np.ndarray, float, float, float]:
        h, w = frame.shape[:2]
        scale = min(self.IMG_SIZE / w, self.IMG_SIZE / h)
        nw, nh = int(round(w * scale)), int(round(h * scale))
        resized = cv2.resize(frame, (nw, nh))
        canvas = np.full((self.IMG_SIZE, self.IMG_SIZE, 3), 114, dtype=np.uint8)
        top, left = (self.IMG_SIZE - nh) // 2, (self.IMG_SIZE - nw) // 2
        canvas[top:top + nh, left:left + nw] = resized
        blob = cv2.dnn.blobFromImage(canvas, 1 / 255.0, swapRB=True)
        return blob, scale, left, top

    def detect(self, frame: np.ndarray) -> list[Detection]:
        blob, scale, pad_x, pad_y = self._letterbox(frame)
        outputs = self.session.run(None, {self.input_name: blob})
        pred = outputs[0]
        if pred.ndim == 3:
            pred = pred[0]
        # YOLOv8 : (4+nc, N) -> [cx,cy,w,h, scores classes]
        boxes_raw = pred[:4, :].T
        scores_all = pred[4:, :].T
        cls_ids = scores_all.argmax(axis=1)
        confs = scores_all.max(axis=1)
        keep_mask = confs >= self.conf_threshold
        boxes_raw, confs, cls_ids = boxes_raw[keep_mask], confs[keep_mask], cls_ids[keep_mask]
        detections: list[Detection] = []
        if len(boxes_raw):
            xywh = boxes_raw.copy()
            xywh[:, :2] -= xywh[:, 2:4] / 2  # centre -> coin superieur gauche
            indices = cv2.dnn.NMSBoxes(
                xywh.tolist(), confs.tolist(), self.conf_threshold, self.iou_threshold
            )
            flat = np.array(indices).flatten() if len(indices) else []
            for i in flat:
                cx, cy, bw, bh = boxes_raw[i]
                x1 = (cx - bw / 2 - pad_x) / scale
                y1 = (cy - bh / 2 - pad_y) / scale
                x2 = (cx + bw / 2 - pad_x) / scale
                y2 = (cy + bh / 2 - pad_y) / scale
                cls_id = int(cls_ids[i])
                detections.append(Detection(
                    bbox=np.array([x1, y1, x2, y2]), score=float(confs[i]),
                    cls=cls_id, cls_name=COCO_CLASSES.get(cls_id, f"classe_{cls_id}"),
                ))
        return detections


class MOG2Detector(BaseDetector):
    """Detecteur de secours : soustraction de fond MOG2 (100% hors-ligne, sans modele)."""

    def __init__(self, conf_threshold: float = 0.35, min_area: int = 500,
                 history: int = 400, var_threshold: int = 28) -> None:
        self.conf_threshold = conf_threshold
        self.min_area = min_area
        self._mog2 = cv2.createBackgroundSubtractorMOG2(history=history, varThreshold=var_threshold,
                                                        detectShadows=False)
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        self._warmup_frames = 0
        self.name = "mog2 (secours)"

    def detect(self, frame: np.ndarray) -> list[Detection]:
        mask = self._mog2.apply(frame)
        self._warmup_frames += 1
        if self._warmup_frames < 12:
            return []  # stabilisation du modele de fond
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections: list[Detection] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            fill = area / max(w * h, 1)
            # score de confiance = taux de remplissage (proxy), borne au seuil haut
            score = float(min(0.9, max(self.conf_threshold + 0.15, fill)))
            ratio = h / max(w, 1)
            cls_name = "personne" if ratio > 1.4 and w < frame.shape[1] * 0.08 else "voiture"
            detections.append(Detection(
                bbox=np.array([x, y, x + w, y + h], dtype=float),
                score=score, cls=2 if cls_name == "voiture" else 0, cls_name=cls_name,
            ))
        return detections


def create_detector(cfg: AIConfig) -> BaseDetector:
    """Fabrique : 'auto' essaie YOLO ONNX puis bascule MOG2 ; 'mog2' force le secours."""
    if cfg.detector == "mog2":
        return MOG2Detector(conf_threshold=cfg.conf_threshold, min_area=cfg.mog2_min_area,
                            history=cfg.mog2_history, var_threshold=cfg.mog2_var_threshold)
    if cfg.detector in ("auto", "yolo_onnx"):
        try:
            detector = YOLOOnnxDetector(cfg.model_path, cfg.conf_threshold, cfg.iou_threshold)
            return detector
        except DetectorUnavailable as exc:
            if cfg.detector == "yolo_onnx":
                raise
            log.warning("YOLO indisponible, repli detecteur MOG2", extra={"ctx": {"raison": str(exc)}})
            return MOG2Detector(conf_threshold=cfg.conf_threshold, min_area=cfg.mog2_min_area,
                                history=cfg.mog2_history, var_threshold=cfg.mog2_var_threshold)
    raise ValueError(f"detecteur inconnu : {cfg.detector}")
