"""Geometrie de boites : IoU, centres, conversion (x1,y1,x2,y2) -> (cx,cy,w,h)."""
from __future__ import annotations

import numpy as np


def bbox_center(bbox: np.ndarray) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return (float(x1) + float(x2)) / 2.0, (float(y1) + float(y2)) / 2.0


def bbox_wh(bbox: np.ndarray) -> tuple[float, float]:
    return float(bbox[2] - bbox[0]), float(bbox[3] - bbox[1])


def bbox_bottom_center(bbox: np.ndarray) -> tuple[float, float]:
    """Point d'appui au sol d'un objet (pieds) : centre horizontal, bas vertical."""
    x1, _, x2, y2 = bbox
    return (float(x1) + float(x2)) / 2.0, float(y2)


def iou_xyxy(a: np.ndarray, b: np.ndarray) -> float:
    """Intersection sur union entre deux boites [x1,y1,x2,y2]."""
    x1 = max(float(a[0]), float(b[0]))
    y1 = max(float(a[1]), float(b[1]))
    x2 = min(float(a[2]), float(b[2]))
    y2 = min(float(a[3]), float(b[3]))
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, float(a[2]) - float(a[0])) * max(0.0, float(a[3]) - float(a[1]))
    area_b = max(0.0, float(b[2]) - float(b[0])) * max(0.0, float(b[3]) - float(b[1]))
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def iou_matrix(tracks_boxes: np.ndarray, det_boxes: np.ndarray) -> np.ndarray:
    """Matrice IoU (n_tracks x n_dets) vectorisee."""
    if len(tracks_boxes) == 0 or len(det_boxes) == 0:
        return np.zeros((len(tracks_boxes), len(det_boxes)), dtype=float)
    t = tracks_boxes.astype(float)
    d = det_boxes.astype(float)
    lt = np.minimum(t[:, None, :2], d[None, :, :2])
    rb = np.maximum(t[:, None, 2:4], d[None, :, 2:4])
    inter = np.prod(np.clip(rb - lt, 0, None), axis=2)
    area_t = np.prod(np.clip(t[:, 2:4] - t[:, :2], 0, None), axis=1)
    area_d = np.prod(np.clip(d[:, 2:4] - d[:, :2], 0, None), axis=1)
    union = area_t[:, None] + area_d[None, :] - inter
    return np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
