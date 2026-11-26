"""Analyse de trajectoires : historiques de positions, comptage par ligne, direction, statistiques."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class TrajectoryPoint:
    ts: float          # timestamp image (secondes)
    x: float           # pixels image (centre de la boite)
    y: float
    speed_kmh: Optional[float] = None
    bbox: Optional[tuple[float, float, float, float]] = None  # (x1, y1, x2, y2) si disponible


@dataclass
class Trajectory:
    track_id: int
    cls_name: str
    points: list[TrajectoryPoint] = field(default_factory=list)

    def append(self, point: TrajectoryPoint) -> None:
        self.points.append(point)

    def last(self) -> Optional[TrajectoryPoint]:
        return self.points[-1] if self.points else None

    def direction_angle(self, window: int = 10) -> Optional[float]:
        """Angle de deplacement (degres, 0 = est) sur les derniers points."""
        if len(self.points) < 2:
            return None
        p1 = self.points[-min(window, len(self.points))]
        p2 = self.points[-1]
        dx, dy = p2.x - p1.x, p2.y - p1.y
        if dx == 0 and dy == 0:
            return None
        return float(np.degrees(np.arctan2(dy, dx)))

    def crossed_line(self, line: tuple[tuple[float, float], tuple[float, float]]) -> bool:
        """Vrai si le dernier segment de trajectoire coupe le segment defini par la ligne."""
        if len(self.points) < 2:
            return False
        a = (self.points[-2].x, self.points[-2].y)
        b = (self.points[-1].x, self.points[-1].y)
        return _segments_intersect(a, b, line[0], line[1])


def _orientation(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> int:
    val = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
    if abs(val) < 1e-12:
        return 0
    return 1 if val > 0 else 2


def _segments_intersect(p1: tuple, p2: tuple, p3: tuple, p4: tuple) -> bool:
    d1 = _orientation(p3, p4, p1)
    d2 = _orientation(p3, p4, p2)
    d3 = _orientation(p1, p2, p3)
    d4 = _orientation(p1, p2, p4)
    if d1 != d2 and d3 != d4:
        return True
    return False


def side_of_line(point: tuple[float, float], line: tuple[tuple[float, float], tuple[float, float]]) -> int:
    """Cote d'un point par rapport a la ligne : -1, 0 (sur la ligne), +1."""
    (x1, y1), (x2, y2) = line
    cross = (x2 - x1) * (point[1] - y1) - (y2 - y1) * (point[0] - x1)
    if abs(cross) < 1e-9:
        return 0
    return 1 if cross > 0 else -1


class LineCounter:
    """Comptage bidirectionnel sur une ligne virtuelle (deux cotes A et B)."""

    def __init__(self, line: tuple[tuple[float, float], tuple[float, float]]) -> None:
        self.line = line
        self.counts = {"A_vers_B": 0, "B_vers_A": 0}
        self._last_side: dict[int, int] = {}

    def update(self, trajectory: Trajectory) -> bool:
        """Mettre a jour avec la trajectoire ; retourne True si un franchissement vient d'etre compte."""
        if not trajectory.points:
            return False
        tid = trajectory.track_id
        point = trajectory.points[-1]
        current_side = side_of_line((point.x, point.y), self.line)
        previous_side = self._last_side.get(tid, current_side)
        self._last_side[tid] = current_side
        if previous_side != 0 and current_side != 0 and previous_side != current_side \
                and trajectory.crossed_line(self.line):
            # convention : cote -1 = "A", cote +1 = "B"
            direction = "A_vers_B" if previous_side == -1 else "B_vers_A"
            self.counts[direction] += 1
            return True
        return False

    def stats(self) -> dict:
        return {"ligne": self.line, **self.counts, "total": sum(self.counts.values())}


class TrajectoryStore:
    """Registre des trajectoires par piste (borne en nombre de points)."""

    def __init__(self, max_points: int = 600) -> None:
        self.max_points = max_points
        self.trajectories: dict[int, Trajectory] = {}

    def update(self, track_id: int, cls_name: str, ts: float, x: float, y: float,
               speed_kmh: float | None = None,
               bbox: tuple[float, float, float, float] | None = None) -> Trajectory:
        traj = self.trajectories.get(track_id)
        if traj is None:
            traj = Trajectory(track_id=track_id, cls_name=cls_name)
            self.trajectories[track_id] = traj
        traj.append(TrajectoryPoint(ts=ts, x=x, y=y, speed_kmh=speed_kmh, bbox=bbox))
        if len(traj.points) > self.max_points:
            traj.points = traj.points[-self.max_points:]
        return traj

    def forget(self, track_ids: set[int]) -> None:
        for tid in track_ids:
            self.trajectories.pop(tid, None)

    def class_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for traj in self.trajectories.values():
            counts[traj.cls_name] = counts.get(traj.cls_name, 0) + 1
        return counts
