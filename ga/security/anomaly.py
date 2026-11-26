"""Detection d'anomalies statistiques : z-score glissant sur comptages et vitesses."""
from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from ga.core.logging import get_logger

log = get_logger("ga.security.anomaly")


class AnomalyDetector:
    """Detecteur d'anomalie par z-score glissant (fenetre bornée)."""

    def __init__(self, window: int = 60, zscore_threshold: float = 3.0, min_history: int = 20) -> None:
        self.window = window
        self.threshold = zscore_threshold
        self.min_history = min_history
        self._values: deque[float] = deque(maxlen=window)

    def update(self, value: float) -> Optional[dict]:
        """Ajouter une valeur (ex: comptage par intervalle, vitesse moyenne) ; retourne une anomalie si z-score > seuil."""
        z = None
        if len(self._values) >= self.min_history:
            arr = np.array(self._values, dtype=float)
            std = float(arr.std())
            mean = float(arr.mean())
            if std > 1e-9:
                z = (value - mean) / std
            elif abs(value - mean) > 1e-9:
                z = 99.0  # variance nulle : tout ecart est une rupture nette
        self._values.append(float(value))
        if z is not None and abs(z) >= self.threshold:
            log.info("anomalie statistique detectee", extra={"ctx": {
                "valeur": value, "zscore": round(min(abs(z), 99.0), 2),
                "moyenne_fenetre": round(float(np.mean(self._values)), 2)}})
            return {"valeur": value, "zscore": round(min(abs(z), 99.0), 2),
                    "moyenne_fenetre": round(float(np.mean(self._values)), 2)}
        return None
