"""Tests GA-ROAD : calibration homographie, mesure de vitesse, evenements de trafic."""
from __future__ import annotations

import pytest

from ga.core.config import RoadConfig
from ga.road.calibration import RoadCalibration
from ga.road.events import TrafficAnalyzer
from ga.road.speed import SpeedTracker


class TestCalibration:
    def test_mapping_lineaire_exact(self):
        calib = RoadCalibration([[0, 0], [100, 0], [0, 100], [100, 100]],
                                [[0, 0], [10, 0], [0, 10], [10, 10]])
        wx, wy = calib.image_to_world(50, 50)
        assert wx == pytest.approx(5.0) and wy == pytest.approx(5.0)
        ix, iy = calib.world_to_image(3.0, 7.0)
        assert ix == pytest.approx(30.0) and iy == pytest.approx(70.0)

    def test_aller_retour_coherent(self):
        calib = RoadCalibration([[140, 700], [1140, 700], [1140, 500], [140, 500]],
                                [[0, 0], [50, 0], [50, 10], [0, 10]])
        for px, py in [(200, 600), (900, 550), (500, 650)]:
            wx, wy = calib.image_to_world(px, py)
            ix, iy = calib.world_to_image(wx, wy)
            assert ix == pytest.approx(px, abs=1e-3)
            assert iy == pytest.approx(py, abs=1e-3)

    def test_refuse_autre_que_4_points(self):
        with pytest.raises(ValueError):
            RoadCalibration([[0, 0], [1, 1]], [[0, 0], [1, 1]])


class TestVitesse:
    def test_vitesse_connue_1m_s(self):
        """1 px = 0.1 m ; objet avance de 10 px/s -> 1 m/s = 3.6 km/h."""
        calib = RoadCalibration([[0, 0], [100, 0], [0, 100], [100, 100]],
                                [[0, 0], [10, 0], [0, 10], [10, 10]])
        tracker = SpeedTracker(calib, smoothing_alpha=1.0, min_samples=2)
        for i in range(10):
            est = tracker.update(track_id=1, px=100 + i * 10, py=50, ts=i * 1.0)
        assert est is not None
        assert est.speed_kmh == pytest.approx(3.6, abs=0.05)
        assert est.samples >= 8

    def test_echantillon_insuffisant_signale(self):
        calib = RoadCalibration([[0, 0], [100, 0], [0, 100], [100, 100]],
                                [[0, 0], [10, 0], [0, 10], [10, 10]])
        tracker = SpeedTracker(calib, min_samples=4)
        est = tracker.update(track_id=1, px=0, py=0, ts=0.0)
        assert est is None or est.samples < 2  # premiere mesure jamais fiable

    def test_vitesse_diagonale(self):
        calib = RoadCalibration([[0, 0], [100, 0], [0, 100], [100, 100]],
                                [[0, 0], [10, 0], [0, 10], [10, 10]])
        tracker = SpeedTracker(calib, smoothing_alpha=1.0)
        # 3 m/s en x ET 4 m/s en y -> 5 m/s = 18 km/h
        for i in range(12):
            est = tracker.update(track_id=7, px=100 + i * 30, py=100 + i * 40, ts=i * 1.0)
        assert est.speed_kmh == pytest.approx(18.0, abs=0.2)


class TestEvenementsTrafic:
    def _analyzer(self, stopped_s: float = 8.0) -> TrafficAnalyzer:
        cfg = RoadConfig(stopped_speed_kmh=3.0, stopped_min_seconds=stopped_s,
                         speed_limit_kmh=80.0, speed_min_samples=2)
        return TrafficAnalyzer("cam-test", cfg, {})

    def test_vehicule_arrete_detecte_une_fois(self):
        analyzer = self._analyzer()
        events = []
        for i in range(100):
            events += analyzer.update_track(track_id=1, cls_name="voiture", x=100, y=200,
                                            ts=i * 1.0, speed_kmh=1.0)
        arrets = [e for e in events if e.kind == "vehicule_arrete"]
        assert len(arrets) == 1, f"arrets detectes : {len(arrets)}"
        assert arrets[0].details["duree_s"] >= 8.0

    def test_exces_vitesse_candidat(self):
        analyzer = self._analyzer()
        events = analyzer.update_track(1, "voiture", 100, 200, ts=10.0, speed_kmh=110.0)
        assert any(e.kind == "exces_vitesse_candidat" for e in events)
        assert events[0].details["vitesse_kmh"] == 110.0

    def test_mauvaise_direction(self):
        cfg = RoadConfig()
        analyzer = TrafficAnalyzer("cam-test", cfg, {"allowed_directions": {"voie_1": 0.0}})
        event = analyzer.check_direction(track_id=1, angle_deg=180.0, ts=1.0)
        assert event is not None and event.kind == "mauvaise_direction"
        assert analyzer.check_direction(track_id=2, angle_deg=15.0, ts=1.0) is None

    def test_aucun_evenement_en_regime_normal(self):
        analyzer = self._analyzer()
        events = []
        for i in range(60):
            events += analyzer.update_track(1, "voiture", 100 + i * 5, 200,
                                            ts=i * 0.5, speed_kmh=45.0)
        assert events == []
