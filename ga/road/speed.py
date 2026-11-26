"""Mesure de vitesse par suivi de trajectoire calibree (metres reels, lissage EMA)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ga.road.calibration import RoadCalibration


@dataclass
class SpeedEstimate:
    track_id: int
    speed_kmh: float
    samples: int
    distance_m: float


class SpeedTracker:
    """Vitesse d'une piste : conversions image->monde, derivee lissee (EMA).

    Deux protections contre le bruit de detection :
    - tremblement : deplacement < 5 cm entre deux images = bruit, pas un mouvement ;
    - acceleration implausible : ecart instantane > accel_max m/s2 = artefact
      (boite partielle a l'entree/sortie du champ), mesure ecartee ; apres
      15 rejets consecutifs le filtre re-apprend (objet reellement accelere).
    """

    ACCEL_MAX_M_S2 = 15.0
    RELEARN_AFTER_REJECTS = 15

    def __init__(self, calibration: RoadCalibration, smoothing_alpha: float = 0.35,
                 min_samples: int = 4) -> None:
        if not (0.0 < smoothing_alpha <= 1.0):
            raise ValueError("alpha de lissage dans (0, 1]")
        self.calibration = calibration
        self.alpha = smoothing_alpha
        self.min_samples = min_samples
        self._last: dict[int, tuple[float, tuple[float, float]]] = {}   # id -> (ts, world)
        self._speed: dict[int, float] = {}                              # id -> m/s lisse
        self._distance: dict[int, float] = {}
        self._count: dict[int, int] = {}                                # id -> nb d'echantillons
        self._rejects: dict[int, int] = {}                              # id -> rejets consecutifs
        self._stagnation: dict[int, int] = {}                           # id -> images sans mouvement

    def update(self, track_id: int, px: float, py: float, ts: float) -> Optional[SpeedEstimate]:
        """Mettre a jour avec la position sol d'une piste ; retourne l'estimation si fiable."""
        wx, wy = self.calibration.image_to_world(px, py)
        prev = self._last.get(track_id)
        self._last[track_id] = (ts, (wx, wy))
        if prev is None:
            return None
        prev_ts, (prev_x, prev_y) = prev
        dt = ts - prev_ts
        if dt <= 1e-4:
            return self._as_estimate(track_id)
        dist = float(np.hypot(wx - prev_x, wy - prev_y))
        if dist < 0.05:
            # moins de 5 cm entre deux images : tremblement de detection...
            self._stagnation[track_id] = self._stagnation.get(track_id, 0) + 1
            if self._stagnation[track_id] >= 5:
                self._speed[track_id] = 0.0  # ...prolonge = objet reellement immobile
            return self._as_estimate(track_id)
        self._stagnation[track_id] = 0
        instant = dist / dt  # m/s
        current = self._speed.get(track_id)
        if current is not None and abs(instant - current) > self.ACCEL_MAX_M_S2 * dt:
            # acceleration physiquement implausible : artefact de detection
            self._rejects[track_id] = self._rejects.get(track_id, 0) + 1
            if self._rejects[track_id] >= self.RELEARN_AFTER_REJECTS:
                self._speed[track_id] = instant  # re-apprentissage
                self._rejects[track_id] = 0
            self._distance[track_id] = self._distance.get(track_id, 0.0) + dist
            self._count[track_id] = self._count.get(track_id, 0) + 1
            return self._as_estimate(track_id)
        self._rejects[track_id] = 0
        if current is None:
            self._speed[track_id] = instant
        else:
            self._speed[track_id] = self.alpha * instant + (1 - self.alpha) * current
        self._distance[track_id] = self._distance.get(track_id, 0.0) + dist
        self._count[track_id] = self._count.get(track_id, 0) + 1
        return self._as_estimate(track_id)

    def _as_estimate(self, track_id: int) -> Optional[SpeedEstimate]:
        speed = self._speed.get(track_id)
        if speed is None or self._last.get(track_id) is None:
            return None
        return SpeedEstimate(track_id=track_id, speed_kmh=round(speed * 3.6, 1),
                             samples=self._count.get(track_id, 0),
                             distance_m=round(self._distance.get(track_id, 0.0), 2))

    def forget(self, track_id: int) -> None:
        self._last.pop(track_id, None)
        self._speed.pop(track_id, None)
        self._distance.pop(track_id, None)
        self._count.pop(track_id, None)
        self._rejects.pop(track_id, None)
        self._stagnation.pop(track_id, None)

    def current(self, track_id: int) -> Optional[SpeedEstimate]:
        return self._as_estimate(track_id)
