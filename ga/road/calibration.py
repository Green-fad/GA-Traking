"""Calibration caméra -> monde réel par homographie (4 points image, 4 points metres).

La mesure de vitesse n'est fiable QUE si la camera est calibree :
4 points visibles dans l'image dont on connait les coordonnees reelles (metres).
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from ga.core.logging import get_logger

log = get_logger("ga.road.calibration")


class RoadCalibration:
    """Transformation image (pixels) -> plan sol (metres) par homographie."""

    def __init__(self, image_points: list[list[float]], world_points: list[list[float]]) -> None:
        if len(image_points) != 4 or len(world_points) != 4:
            raise ValueError("la calibration exige exactement 4 points image et 4 points monde")
        src = np.array(image_points, dtype=np.float32)
        dst = np.array(world_points, dtype=np.float32)
        self.H: np.ndarray = cv2.getPerspectiveTransform(src, dst)
        self.H_inv: np.ndarray = np.linalg.inv(self.H)
        log.info("calibration chargee", extra={"ctx": {"image": image_points, "monde_m": world_points}})

    def image_to_world(self, px: float, py: float) -> tuple[float, float]:
        """Convertir un point image (pixels) en coordonnees sol (metres)."""
        v = self.H @ np.array([px, py, 1.0], dtype=float)
        if abs(v[2]) < 1e-12:
            raise ValueError("point image degeneré (homographie)")
        return float(v[0] / v[2]), float(v[1] / v[2])

    def world_to_image(self, wx: float, wy: float) -> tuple[float, float]:
        v = self.H_inv @ np.array([wx, wy, 1.0], dtype=float)
        if abs(v[2]) < 1e-12:
            raise ValueError("point monde degeneré")
        return float(v[0] / v[2]), float(v[1] / v[2])

    @classmethod
    def from_config(cls, cfg: Optional[dict]) -> Optional["RoadCalibration"]:
        """Construire depuis la configuration camera ; None si non calibree."""
        if not cfg or "image_points" not in cfg or "world_points_m" not in cfg:
            return None
        return cls(cfg["image_points"], cfg["world_points_m"])
