"""Tests GA-TRACK : Kalman, ByteTrack, comptage de lignes, trajectoires."""
from __future__ import annotations

import numpy as np
import pytest

from ga.track.bytetrack import ByteTracker, Detection, TrackState
from ga.track.kalman import KalmanBox
from ga.track.trajectories import LineCounter, Trajectory, TrajectoryPoint, TrajectoryStore, side_of_line


def _moving_sequence(n_frames: int, speed_px: float = 5.0, y: float = 100.0,
                     start_x: float = 50.0, w: float = 60.0, h: float = 40.0,
                     score: float = 0.9) -> list[list[Detection]]:
    frames = []
    for i in range(n_frames):
        x = start_x + i * speed_px
        bbox = np.array([x, y, x + w, y + h])
        frames.append([Detection(bbox=bbox, score=score, cls=2, cls_name="voiture")])
    return frames


class TestKalman:
    def test_converge_vers_la_position_mesuree(self):
        kf = KalmanBox(np.array([100.0, 200.0, 160.0, 240.0]))
        for i in range(30):
            kf.predict()
            kf.update(np.array([100.0 + i * 5, 200.0, 160.0 + i * 5, 240.0]))
        # centre de la derniere boite : (100+i*5 + 160+i*5)/2 = 130 + i*5
        assert abs(kf.center[0] - (130 + 29 * 5)) < 2.0
        assert kf.velocity[0] > 4.0  # a appris la vitesse

    def test_prediction_extrapole(self):
        kf = KalmanBox(np.array([0.0, 0.0, 10.0, 10.0]))  # centre initial (5, 5)
        kf.state[2] = 3.0  # vx
        state = kf.predict()
        assert state[0] == pytest.approx(8.0)  # 5 (centre) + 3 (vitesse)


class TestByteTracker:
    def test_identite_stable_sur_sequence(self):
        tracker = ByteTracker(high_thresh=0.5, min_hits=2)
        ids = []
        for frame in _moving_sequence(40):
            tracks = tracker.update(frame)
            if tracks:
                ids.append(tracks[0].track_id)
        assert ids, "aucune piste produite"
        assert len(set(ids)) == 1, f"identite instable : {set(ids)}"

    def test_deux_objets_separes(self):
        tracker = ByteTracker(high_thresh=0.5, min_hits=2)
        last_ids = set()
        for i in range(40):
            dets = [
                Detection(bbox=np.array([50 + i * 5, 100, 110 + i * 5, 140]), score=0.9, cls=2, cls_name="voiture"),
                Detection(bbox=np.array([500 + i * 3, 400, 560 + i * 3, 440]), score=0.9, cls=2, cls_name="voiture"),
            ]
            tracks = tracker.update(dets)
            last_ids = {t.track_id for t in tracks}
        assert len(last_ids) == 2, "deux objets eloignes doivent donner deux pistes"

    def test_piste_perdue_apres_disparition(self):
        tracker = ByteTracker(high_thresh=0.5, min_hits=2, max_time_lost=5)
        for frame in _moving_sequence(10):
            tracker.update(frame)
        # plus aucune detection : les pistes passent LOST puis REMOVED
        for _ in range(10):
            tracker.update([])
        assert len(tracker.active_tracks()) == 0
        assert all(t.state == TrackState.REMOVED for t in tracker._tracks)

    def test_association_basse_confiance_recupere_une_occlusion(self):
        """BYTE : les detections de faible confiance doivent prolonger une piste existante."""
        tracker = ByteTracker(high_thresh=0.5, low_thresh=0.1, min_hits=2)
        frames = []
        for i in range(15):
            x = 50 + i * 5
            score = 0.9 if i < 8 else 0.3  # occlusion partielle -> faible confiance
            frames.append([Detection(bbox=np.array([x, 100, x + 60, 140]), score=score, cls=2, cls_name="voiture")])
        ids = set()
        for frame in frames:
            for t in tracker.update(frame):
                ids.add(t.track_id)
        assert len(ids) == 1, f"l'occlusion a brise la piste : {len(ids)} identites"


class TestComptage:
    def test_franchissement_unique(self):
        """La trajectoire traverse la ligne lors de son DERNIER segment (cas du pipeline)."""
        line = ((0.0, 300.0), (1000.0, 300.0))
        traj = Trajectory(track_id=1, cls_name="voiture")
        traj.append(TrajectoryPoint(ts=1.0, x=200, y=280))
        traj.append(TrajectoryPoint(ts=2.0, x=210, y=320))
        assert traj.crossed_line(line)
        assert side_of_line((200, 280), line) == -1
        assert side_of_line((210, 320), line) == 1

    def test_comptage_bidirectionnel(self):
        line = ((0.0, 300.0), (1000.0, 300.0))
        counter = LineCounter(line)
        # objet 1 : haut -> bas (cote A vers cote B), maj point par point comme le pipeline
        t1 = Trajectory(track_id=1, cls_name="voiture")
        for ts, y in ((0.0, 280.0), (1.0, 320.0)):
            t1.append(TrajectoryPoint(ts=ts, x=200, y=y))
            counted = counter.update(t1)
        assert counted is True
        # objet 2 : bas -> haut (cote B vers cote A)
        t2 = Trajectory(track_id=2, cls_name="voiture")
        for ts, y in ((0.0, 340.0), (1.0, 260.0)):
            t2.append(TrajectoryPoint(ts=ts, x=700, y=y))
            counted = counter.update(t2)
        assert counted is True
        stats = counter.stats()
        assert stats["total"] == 2
        assert stats["A_vers_B"] == 1 and stats["B_vers_A"] == 1

    def test_pas_de_double_comptage(self):
        line = ((0.0, 300.0), (1000.0, 300.0))
        counter = LineCounter(line)
        traj = Trajectory(track_id=1, cls_name="voiture")
        counts = []
        ys = [250 + i * 11 for i in range(10)]  # un seul croisement de y=300
        for i, y in enumerate(ys):
            traj.append(TrajectoryPoint(ts=i / 10, x=200, y=float(y)))
            counts.append(counter.update(traj))
        assert counts.count(True) == 1  # un seul franchissement compte


class TestTrajectoryStore:
    def test_memorisation_bornee(self):
        store = TrajectoryStore(max_points=10)
        for i in range(50):
            store.update(1, "voiture", ts=i / 10, x=i, y=i)
        assert len(store.trajectories[1].points) == 10
        assert store.trajectories[1].points[-1].x == 49

    def test_angle_de_direction(self):
        traj = Trajectory(track_id=1, cls_name="voiture")
        for i in range(10):
            traj.append(TrajectoryPoint(ts=i / 10, x=i * 10, y=0))
        assert traj.direction_angle() == pytest.approx(0.0, abs=1.0)
