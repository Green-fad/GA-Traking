"""Analyse des evenements routiers : exces de vitesse candidats, vehicules arretes,
mauvaise direction, franchissements — chaque evenement est une CANDIDATE a
verifier par un operateur (aucune sanction automatique).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ga.core.logging import get_logger
from ga.core.config import RoadConfig
from ga.road.speed import SpeedTracker

log = get_logger("ga.road.events")

# classes vehicules (les evenements de vitesse/arret ne concernent que les vehicules)
VEHICLE_NAMES = {"voiture", "camion", "bus", "camionnette", "moto", "velo"}


@dataclass
class TrafficEvent:
    kind: str                 # exces_vitesse_candidat / vehicule_arrete / mauvaise_direction / franchissement
    track_id: int
    camera_id: str
    ts: float
    details: dict = field(default_factory=dict)


class TrafficAnalyzer:
    """Analyse par camera : lignes de comptage, sens de circulation, arrets, vitesses.

    Configuration par camera (dictionnaire) :
        counting_lines: [[x1,y1,x2,y2], ...]                     (pixels image)
        allowed_directions: {"ligne_1": angle_deg, ...}          (angle de circulation attendu)
        zones: {"nom_zone": [[x,y], ...]}                        (pixels, zones d'arret interdit)
    """
    DIRECTION_TOLERANCE_DEG = 45.0

    def __init__(self, camera_id: str, cfg: RoadConfig, camera_analysis: dict | None = None) -> None:
        self.camera_id = camera_id
        self.cfg = cfg
        self.camera_analysis = camera_analysis or {}
        self._stop_start: dict[int, float] = {}      # piste -> debut d'arret (ts)
        self._stop_fired: set[int] = set()           # pistes deja notifiees (re-armees au redemarrage)
        self._speed_fired: set[int] = set()          # pistes deja notifiees pour exces de vitesse
        self._last_ts: dict[int, float] = {}

    def update_track(self, track_id: int, cls_name: str, x: float, y: float,
                     ts: float, speed_kmh: float | None = None) -> list[TrafficEvent]:
        """Mettre a jour une position ; retourne les evenements detects."""
        events: list[TrafficEvent] = []
        self._last_ts[track_id] = ts
        is_vehicle = cls_name in VEHICLE_NAMES

        # 1) vehicule arrete (vitesse mesuree < seuil pendant >= N secondes)
        if is_vehicle and speed_kmh is not None and speed_kmh <= self.cfg.stopped_speed_kmh:
            start = self._stop_start.setdefault(track_id, ts)
            if ts - start >= self.cfg.stopped_min_seconds and track_id not in self._stop_fired:
                events.append(TrafficEvent(
                    kind="vehicule_arrete", track_id=track_id, camera_id=self.camera_id, ts=ts,
                    details={"duree_s": round(ts - start, 1), "vitesse_kmh": speed_kmh, "x": x, "y": y},
                ))
                self._stop_fired.add(track_id)  # un seul evenement par phase d'arret
        else:
            # le vehicule roule a nouveau : re-armement de la detection d'arret
            self._stop_start.pop(track_id, None)
            self._stop_fired.discard(track_id)

        # 2) exces de vitesse candidat (vitesse > limite + marge 10%) : un seul evenement par piste
        if is_vehicle and speed_kmh is not None and speed_kmh > self.cfg.speed_limit_kmh * 1.1:
            if track_id not in self._speed_fired:
                self._speed_fired.add(track_id)
                events.append(TrafficEvent(
                    kind="exces_vitesse_candidat", track_id=track_id, camera_id=self.camera_id, ts=ts,
                    details={"vitesse_kmh": speed_kmh, "limite_kmh": self.cfg.speed_limit_kmh, "x": x, "y": y},
                ))
        elif is_vehicle and speed_kmh is not None and speed_kmh <= self.cfg.speed_limit_kmh:
            self._speed_fired.discard(track_id)  # retombe sous la limite : re-armement
        return events

    def check_direction(self, track_id: int, angle_deg: float, ts: float) -> Optional[TrafficEvent]:
        """Verifier la direction d'une piste contre le sens attendu de sa zone/ligne."""
        allowed = self.camera_analysis.get("allowed_directions", {})
        if not allowed:
            return None
        # sens attendu le plus proche (angle modulo 360)
        best_key, best_diff = None, 1e9
        for key, expected in allowed.items():
            diff = abs((angle_deg - float(expected) + 180) % 360 - 180)
            if diff < best_diff:
                best_key, best_diff = key, diff
        if best_key is not None and best_diff > self.DIRECTION_TOLERANCE_DEG:
            return TrafficEvent(
                kind="mauvaise_direction", track_id=track_id, camera_id=self.camera_id, ts=ts,
                details={"angle_deg": round(angle_deg, 1), "sens_attendu": best_key,
                         "tolerance_deg": self.DIRECTION_TOLERANCE_DEG},
            )
        return None
