"""ByteTrack : suivi multi-objets par association en deux etapes (association BYTE).

Reference de l'algorithme : BYTE (Zhang et al., 2021) — les detections de faible
confiance sont egalement associees pour recuperer les objets partiellement occlus.

Pipeline par image :
1. prevoir chaque piste actives (Kalman) ;
2. 1ere association : pistes x detections de haute confiance (IoU + Hongrois) ;
3. 2e association : pistes restantes x detections de faible confiance ;
4. naissance de pistes sur les detections hautes non associees ;
5. suppression des pistes perdues depuis trop longtemps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
from scipy.optimize import linear_sum_assignment

from .geometry import bbox_wh, iou_matrix
from .kalman import KalmanBox


class TrackState(str, Enum):
    TENTATIVE = "tentative"
    CONFIRMED = "confirmee"
    LOST = "perdue"
    REMOVED = "supprimee"


@dataclass
class Detection:
    bbox: np.ndarray          # [x1, y1, x2, y2]
    score: float
    cls: int = 0
    cls_name: str = "objet"

    @property
    def center(self) -> np.ndarray:
        return (self.bbox[:2] + self.bbox[2:4]) / 2.0


@dataclass
class Track:
    track_id: int
    bbox: np.ndarray
    score: float
    cls: int
    cls_name: str
    state: TrackState = TrackState.TENTATIVE
    hits: int = 1
    age: int = 1
    time_since_update: int = 0
    is_activated: bool = False
    kf: KalmanBox = field(default=None, repr=False)

    @property
    def center(self) -> np.ndarray:
        return self.kf.center

    @property
    def velocity(self) -> np.ndarray:
        return self.kf.velocity


class ByteTracker:
    """Suivi BYTE avec Kalman, seuils haut/bas configurables."""

    def __init__(self, high_thresh: float = 0.5, low_thresh: float = 0.1,
                 match_thresh: float = 0.8, match_thresh_low: float = 0.5,
                 max_time_lost: int = 30, min_hits: int = 3) -> None:
        self.high_thresh = high_thresh
        self.low_thresh = low_thresh
        self.match_thresh = match_thresh        # 1 - IoU minimal requis (1ere association)
        self.match_thresh_low = match_thresh_low  # 2e association (plus tolerante)
        self.max_time_lost = max_time_lost
        self.min_hits = min_hits
        self._tracks: list[Track] = []
        self._next_id = 1
        self._frame_id = 0

    # ---- interface publique ---------------------------------------------
    def update(self, detections: list[Detection]) -> list[Track]:
        """Traiter une image ; retourne les pistes visibles confirmees (is_activated)."""
        self._frame_id += 1
        dets = sorted(detections, key=lambda d: -d.score)
        highs = [d for d in dets if d.score >= self.high_thresh]
        lows = [d for d in dets if self.low_thresh <= d.score < self.high_thresh]

        # 1) prediction
        for t in self._tracks:
            t.kf.predict()
            t.age += 1
            t.time_since_update += 1

        # 2) premiere association : hautes confiances vs toutes pistes actives
        active = [t for t in self._tracks if t.state != TrackState.REMOVED]
        matched_t, matched_d, unmatched_tracks = self._associate(active, highs, self.match_thresh)

        for ti, di in zip(matched_t, matched_d):
            self._apply_detection(active[ti], highs[di])

        # 3) deuxieme association : pistes restantes x faibles confiances
        remaining = [active[i] for i in unmatched_tracks]
        matched_t2, matched_d2, unmatched_after = self._associate(remaining, lows, self.match_thresh_low)
        for ti, di in zip(matched_t2, matched_d2):
            self._apply_detection(remaining[ti], lows[di])

        # 4) nouvelles pistes depuis les hautes confiances non associees
        used_high = set(matched_d)
        unmatched_high = [i for i in range(len(highs)) if i not in used_high]
        for di in unmatched_high:
            self._spawn(highs[di])

        # 5) etat de survie
        output: list[Track] = []
        for t in self._tracks:
            if t.time_since_update > self.max_time_lost:
                t.state = TrackState.REMOVED
                t.is_activated = False
            elif t.time_since_update == 0:
                if t.state == TrackState.LOST:
                    t.state = TrackState.CONFIRMED
                if t.hits >= self.min_hits or self._frame_id <= self.min_hits:
                    t.is_activated = True
            else:
                t.state = TrackState.LOST
                t.is_activated = False
        self._tracks = [t for t in self._tracks if t.state != TrackState.REMOVED]
        output = [t for t in self._tracks if t.is_activated and t.time_since_update == 0]
        return output

    def active_tracks(self) -> list[Track]:
        return [t for t in self._tracks if t.state == TrackState.CONFIRMED]

    def stats(self) -> dict:
        return {
            "image": self._frame_id,
            "pistes_actives": len(self.active_tracks()),
            "pistes_totales": self._next_id - 1,
        }

    # ---- mecanique interne ------------------------------------------------
    def _associate(self, tracks: list[Track], dets: list[Detection],
                   thresh: float) -> tuple[list[int], list[int], list[int]]:
        if not tracks or not dets:
            return [], [], list(range(len(tracks)))
        t_boxes = np.array([
            t.kf.predicted_bbox(bbox_wh(t.bbox)) if t.time_since_update > 0 else t.bbox
            for t in tracks
        ])
        d_boxes = np.array([d.bbox for d in dets])
        iou = iou_matrix(t_boxes, d_boxes)
        cost = 1.0 - iou
        cost[cost > thresh] = 1.0 + 1e-6  # interdit
        rows, cols = linear_sum_assignment(cost)
        matched_t, matched_d = [], []
        for r, c in zip(rows, cols):
            if cost[r, c] <= thresh:
                matched_t.append(r)
                matched_d.append(c)
        unmatched = [i for i in range(len(tracks)) if i not in matched_t]
        return matched_t, matched_d, unmatched

    def _apply_detection(self, track: Track, det: Detection) -> None:
        track.kf.update(det.bbox)
        w, h = bbox_wh(det.bbox)
        cx, cy = track.kf.center
        track.bbox = np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])
        track.score = det.score
        track.cls = det.cls
        track.cls_name = det.cls_name
        track.hits += 1
        track.time_since_update = 0

    def _spawn(self, det: Detection) -> None:
        track = Track(track_id=self._next_id, bbox=det.bbox.copy(), score=det.score,
                      cls=det.cls, cls_name=det.cls_name, kf=KalmanBox(det.bbox))
        self._next_id += 1
        self._tracks.append(track)
