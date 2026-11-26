"""Detection visuelle d'incendie : heuristique couleur + scintillement temporel.

Approche honnete et documentee : masque HSV (flammes orange/rouge/jaune saturees)
+ variance temporelle du masque (le feu scintille) + zone d'interet.
Ce detecteur fonctionne sans modele et hors-ligne ; un classifieur ONNX
peut le remplacer si un modele d'incendie est fourni (voir GA-VISION).
"""
from __future__ import annotations

from collections import deque

import cv2
import numpy as np

from ga.core.logging import get_logger

log = get_logger("ga.security.fire")


class FireDetector:
    """Detecteur heuristique de flammes dans une image (region d'interet optionnelle)."""

    def __init__(self, min_area_px: int = 220, min_frames: int = 8,
                 history: int = 30, flicker_std_threshold: float = 0.18,
                 region: tuple[int, int, int, int] | None = None) -> None:
        self.min_area = min_area_px
        self.min_frames = min_frames
        self.region = region
        self._history: deque[float] = deque(maxlen=history)
        self._consecutive = 0

    def _color_mask(self, frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        # flammes : teinte rouge-orange-jaune (0-40 et 170-180), sat et valeur elevees
        lower1 = np.array([0, 90, 120]); upper1 = np.array([40, 255, 255])
        lower2 = np.array([170, 90, 120]); upper2 = np.array([180, 255, 255])
        m1 = cv2.inRange(hsv, lower1, upper1)
        m2 = cv2.inRange(hsv, lower2, upper2)
        return cv2.bitwise_or(m1, m2)

    def analyze(self, frame: np.ndarray) -> dict:
        """Analyser une image ; retourne {"flamme": bool, "area": int, "confiance": float}."""
        if self.region:
            x1, y1, x2, y2 = self.region
            roi = frame[y1:y2, x1:x2]
        else:
            roi = frame
        mask = self._color_mask(roi)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        area = int(cv2.countNonZero(mask))
        self._history.append(area)
        flicker = float(np.std(self._history) / (np.mean(self._history) + 1e-6)) if self._history else 0.0
        suspect = area >= self.min_area
        self._consecutive = self._consecutive + 1 if suspect else 0
        confirmed = suspect and self._consecutive >= self.min_frames and flicker >= 0.05
        confidence = min(0.95, (area / max(self.min_area * 3, 1)) * 0.6 + min(flicker, 1.0) * 0.3) if suspect else 0.0
        return {"flamme": bool(confirmed), "suspect": bool(suspect),
                "area_px": area, "scintillement": round(flicker, 3),
                "images_consecutives": self._consecutive, "confiance": round(confidence, 2)}

    def reset(self) -> None:
        self._history.clear()
        self._consecutive = 0
