"""Tests GA-SECURITY : zones d'intrusion, detection incendie, anomalies, alertes."""
from __future__ import annotations

import numpy as np
import pytest

from ga.security.alerts import AlertManager
from ga.security.anomaly import AnomalyDetector
from ga.security.fire import FireDetector
from ga.security.zones import Zone, ZoneMonitor, point_in_polygon

POLYGONE = [(100, 100), (400, 100), (400, 300), (100, 300)]


class TestZones:
    def test_point_dans_polygone(self):
        assert point_in_polygon(200, 200, POLYGONE)
        assert not point_in_polygon(50, 50, POLYGONE)
        assert not point_in_polygon(450, 200, POLYGONE)

    def test_intrusion_apres_n_images(self):
        monitor = ZoneMonitor([Zone("zone_sensible", POLYGONE, min_frames=4)])
        triggered = []
        for i in range(10):
            triggered += monitor.update(track_id=1, x=200, y=200, ts=i)
        assert triggered == ["zone_sensible"], f"declenchements : {triggered}"

    def test_sortie_reinitialise_le_compteur(self):
        monitor = ZoneMonitor([Zone("zone_sensible", POLYGONE, min_frames=5)])
        assert monitor.update(1, 200, 200, 0) == []
        assert monitor.update(1, 200, 200, 1) == []
        monitor.update(1, 20, 20, 2)   # sortie
        assert monitor.update(1, 200, 200, 3) == []  # compteur reparti
        assert monitor.update(1, 200, 200, 4) == []
        assert monitor.update(1, 200, 200, 5) == []

    def test_pistes_independantes(self):
        monitor = ZoneMonitor([Zone("z", POLYGONE, min_frames=2)])
        assert monitor.update(1, 200, 200, 0) == []
        assert monitor.update(2, 300, 250, 0) == []
        assert monitor.update(1, 200, 200, 1) == ["z"]
        assert monitor.update(2, 300, 250, 1) == ["z"]


class TestIncendie:
    def _frame_avec_flamme(self, seed: int = 0) -> np.ndarray:
        cv2 = pytest.importorskip("cv2")
        rng = np.random.default_rng(seed)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:] = 40
        # tache orange saturee (flammes) dont la taille varie = scintillement
        cv2.circle(frame, (320, 240), 18 + int(rng.integers(0, 6)), (0, 165, 255), -1)
        return frame

    def test_flamme_confirmee_apres_scintillement(self):
        detector = FireDetector(min_area_px=220, min_frames=6)
        confirmed_at = None
        for i in range(12):
            result = detector.analyze(self._frame_avec_flamme(seed=i))
            if result["flamme"]:
                confirmed_at = i
                break
        assert confirmed_at is not None, "flamme persistante non confirmee"

    def test_pas_de_fausse_alerte_sur_scene_calme(self):
        frame = np.full((480, 640, 3), 40, dtype=np.uint8)
        detector = FireDetector(min_area_px=220, min_frames=6)
        for _ in range(15):
            result = detector.analyze(frame)
        assert not result["flamme"] and not result["suspect"]

    def test_brasseur_de_fond_ne_declenche_pas(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:] = (90, 110, 130)  # teinte bleutee (hors plage des flammes)
        detector = FireDetector()
        for _ in range(10):
            result = detector.analyze(frame)
        assert not result["flamme"]


class TestAnomalie:
    def test_pique_detecte(self):
        detector = AnomalyDetector(window=100, zscore_threshold=3.0, min_history=20)
        anomaly = None
        for v in [10.0] * 40:
            detector.update(v)
        anomaly = detector.update(80.0)  # pique brutal
        assert anomaly is not None and anomaly["zscore"] > 3

    def test_regime_stable_sans_alerte(self):
        detector = AnomalyDetector(min_history=20)
        for i in range(100):
            anomaly = detector.update(10.0 + (i % 3))
        assert anomaly is None


class TestAlertes:
    def test_dedoublonnage(self, test_db, bus):
        manager = AlertManager(bus)
        first = manager.raise_alert("intrusion", "Intrusion zone A", "cam-1", "critical", {"zone": "A"})
        assert first is not None
        second = manager.raise_alert("intrusion", "Intrusion zone A", "cam-1", "critical", {"zone": "A"})
        assert second is None, "le dedoublonnage doit bloquer l'alerte immediate"

    def test_dedoublonnage_par_camera(self, test_db, bus):
        manager = AlertManager(bus)
        a1 = manager.raise_alert("intrusion", "msg", "cam-1", "critical")
        a2 = manager.raise_alert("intrusion", "msg", "cam-2", "critical")
        assert a1 is not None and a2 is not None, "cameras differentes : deux alertes"

    def test_alerte_persistee(self, test_db, bus):
        from ga.data import database as db
        from ga.data.repositories import AlertRepo
        manager = AlertManager(bus)
        alert = manager.raise_alert("vehicule_arrete", "vehicule arrete", "cam-1", "warning")
        with db.session_scope() as session:
            rows = AlertRepo(session).query(type_="vehicule_arrete")
        assert len(rows) == 1 and rows[0].uuid == alert["uuid"]
