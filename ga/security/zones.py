"""Zones d'interet polygonales et detection d'intrusion (pistes dans une zone interdite)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Zone:
    """Zone polygonale en pixels image."""

    name: str
    polygon: list[tuple[float, float]]
    kind: str = "interdite"       # interdite / vigilance
    min_frames: int = 6

    def contains(self, px: float, py: float) -> bool:
        return point_in_polygon(px, py, self.polygon)


def point_in_polygon(px: float, py: float, polygon: list[tuple[float, float]]) -> bool:
    """Test point-dans-polygone par ray casting (algorithme pair/impair)."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and \
                (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


class ZoneMonitor:
    """Surveille les pistes par rapport aux zones : alerte apres N images consecutives."""

    def __init__(self, zones: list[Zone]) -> None:
        self.zones = zones
        self._dwell: dict[tuple[int, str], int] = {}

    def update(self, track_id: int, x: float, y: float, ts: float) -> list[str]:
        """Retourne les noms de zones nouvellement intrudees par cette piste (1 alerte par entree)."""
        newly_triggered: list[str] = []
        for zone in self.zones:
            key = (track_id, zone.name)
            if zone.contains(x, y):
                self._dwell[key] = self._dwell.get(key, 0) + 1
                if self._dwell[key] == zone.min_frames:
                    newly_triggered.append(zone.name)
            else:
                self._dwell.pop(key, None)
        return newly_triggered

    def forget(self, track_id: int) -> None:
        for key in [k for k in self._dwell if k[0] == track_id]:
            del self._dwell[key]
