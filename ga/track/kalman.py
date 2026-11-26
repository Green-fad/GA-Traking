"""Filtre de Kalman a vitesse constante (2D) pour l'association BYTE.

Etat X = [cx, cy, vx, vy] ; mesure Z = [cx, cy].
Le bruit est dimensionne par la taille de la boite (approche SORT/BYTE) :
cette normalisation rend le filtre stable quelle que soit l'echelle objet.
"""
from __future__ import annotations

import numpy as np

from .geometry import bbox_center


class KalmanBox:
    """Filtre de Kalman lineaire sur le centre d'une boite englobante."""

    def __init__(self, bbox: np.ndarray, dt: float = 1.0) -> None:
        cx, cy = bbox_center(bbox)
        h = max(float(bbox[3] - bbox[1]), 10.0)
        self.state = np.array([cx, cy, 0.0, 0.0], dtype=float)
        self.dt = dt
        self.F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
        self.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        # bruits normalises par la taille de l'objet
        std_pos = h / 20.0
        std_vel = h / 80.0
        self.P = np.diag([std_pos ** 2, std_pos ** 2, std_vel ** 2, std_vel ** 2])
        self.R = np.diag([1.5 * std_pos ** 2, 1.5 * std_pos ** 2])
        self.Q = np.diag([std_pos ** 2 * dt, std_pos ** 2 * dt, std_vel ** 2 * dt, std_vel ** 2 * dt])

    def predict(self) -> np.ndarray:
        self.state = self.F @ self.state
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.state[:2].copy()

    def update(self, bbox: np.ndarray) -> None:
        z = np.array(bbox_center(bbox), dtype=float)
        y = z - self.H @ self.state
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.state = self.state + K @ y
        I_KH = np.eye(4) - K @ self.H
        self.P = I_KH @ self.P @ I_KH.T + K @ self.R @ K.T

    @property
    def center(self) -> np.ndarray:
        return self.state[:2]

    @property
    def velocity(self) -> np.ndarray:
        return self.state[2:4]

    def predicted_bbox(self, size: tuple[float, float]) -> np.ndarray:
        w, h = size
        cx, cy = self.center
        return np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])
