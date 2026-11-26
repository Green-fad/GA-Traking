"""Tests GA-OPERATIONS : authentification, RBAC, endpoints, securite applicative."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from ga.core.config import AppConfig
from ga.core.events import EventBus
from ga.core.registry import ServiceRegistry
from ga.data import database as db
from ga.data.cache import CacheClient
from ga.data.media import MediaStore
from ga.data.repositories import AlertRepo, DossierRepo
from ga.intelligence.assistant import Assistant
from ga.intelligence.reports import ReportGenerator
from ga.operations.app import AppContext, create_app

ADMIN_PASS = "GAt Admin#2026"
USER_PASS = "MotDePasse#123"


@pytest.fixture()
def client(test_db, tmp_path):
    cfg = AppConfig()
    cfg.server.secret_key = "cle-de-test"
    cfg.data.media_dir = str(tmp_path / "media")
    ctx = AppContext(cfg=cfg, bus=EventBus(), registry=ServiceRegistry(), manager=None,
                     media=MediaStore(str(tmp_path / "media")), cache=CacheClient("", force_memory=True),
                     assistant=Assistant(), report_generator=ReportGenerator("Site test"))
    return TestClient(create_app(ctx))


def _login(client, username="admin", password=ADMIN_PASS):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _create_user(client, admin_token, username, role="observateur", password=USER_PASS):
    return client.post("/api/users", json={"username": username, "password": password, "role": role},
                       headers={"Authorization": f"Bearer {admin_token}"})


class TestAuthentification:
    def test_login_succes_et_me(self, client):
        response = _login(client)
        assert response.status_code == 200
        token = response.json()["token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["role"] == "admin"

    def test_login_echec(self, client):
        assert _login(client, "admin", "mauvais").status_code == 401

    def test_acces_sans_jeton_refuse(self, client):
        assert client.get("/api/dashboard/summary").status_code == 401
        assert client.get("/api/alerts").status_code == 401
        assert client.get("/api/events").status_code == 401

    def test_jeton_falsifie_refuse(self, client):
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer jeton-invente"})
        assert response.status_code == 401

    def test_injection_sql_ne_passe_pas(self, client):
        payload = {"username": "' OR '1'='1' --", "password": "x"}
        assert client.post("/api/auth/login", json=payload).status_code == 401

    def test_verrouillage_apres_5_echecs(self, client):
        for _ in range(5):
            client.post("/api/auth/login", json={"username": "user_lock", "password": "errone"})
        response = client.post("/api/auth/login", json={"username": "user_lock", "password": "errone"})
        assert response.status_code == 429


class TestRBAC:
    def test_observateur_ne_peut_pas_gerer_utilisateurs(self, client):
        admin_token = _login(client).json()["token"]
        _create_user(client, admin_token, "obs1", role="observateur")
        obs_token = _login(client, "obs1", USER_PASS).json()["token"]
        assert client.get("/api/users", headers={"Authorization": f"Bearer {obs_token}"}).status_code == 403

    def test_observateur_ne_peut_pas_acquitter(self, client):
        admin_token = _login(client).json()["token"]
        _create_user(client, admin_token, "obs2", role="observateur")
        obs_token = _login(client, "obs2", USER_PASS).json()["token"]
        with db.session_scope() as session:
            alert = AlertRepo(session).add(uuid.uuid4().hex, "intrusion", "test", "cam-1")
        response = client.post(f"/api/alerts/{alert.uuid}/ack",
                               headers={"Authorization": f"Bearer {obs_token}"})
        assert response.status_code == 403

    def test_operateur_peut_acquitter(self, client):
        admin_token = _login(client).json()["token"]
        _create_user(client, admin_token, "oper1", role="operateur")
        oper_token = _login(client, "oper1", USER_PASS).json()["token"]
        with db.session_scope() as session:
            alert = AlertRepo(session).add(uuid.uuid4().hex, "intrusion", "test", "cam-1")
        response = client.post(f"/api/alerts/{alert.uuid}/ack",
                               headers={"Authorization": f"Bearer {oper_token}"})
        assert response.status_code == 200
        assert response.json()["statut"] == "acquittee"

    def test_admin_ne_supprime_pas_le_dernier_admin(self, client):
        admin_token = _login(client).json()["token"]
        users = client.get("/api/users", headers={"Authorization": f"Bearer {admin_token}"}).json()
        admin_id = next(u["id"] for u in users if u["username"] == "admin")
        response = client.delete(f"/api/users/{admin_id}",
                                 headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 400


class TestEndpoints:
    def test_dashboard_summary(self, client):
        token = _login(client).json()["token"]
        response = client.get("/api/dashboard/summary", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        body = response.json()
        for key in ("alertes_ouvertes", "evenements_24h", "cameras_total", "serie_journaliere"):
            assert key in body

    def test_cycle_dossier_valide_puis_conteste(self, client):
        token = _login(client).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        with db.session_scope() as session:
            dossier = DossierRepo(session).add(uuid.uuid4().hex, "exces_vitesse_candidat",
                                               {"metriques": {"vitesse_kmh": 95}}, "cam-1")
        uuid_ = dossier.uuid
        decide = client.post(f"/api/dossiers/{uuid_}/decide",
                             json={"decision": "valide", "comment": "verifie"}, headers=headers)
        assert decide.status_code == 200
        # une deuxieme decision est refusee (tracabilite)
        decide2 = client.post(f"/api/dossiers/{uuid_}/decide",
                              json={"decision": "rejete"}, headers=headers)
        assert decide2.status_code == 409
        # contestation possible apres validation
        contest = client.post(f"/api/dossiers/{uuid_}/contest",
                              json={"reason": "contestation exploitant"}, headers=headers)
        assert contest.status_code == 200

    def test_parametres_ia(self, client):
        token = _login(client).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        got = client.get("/api/settings/ai", headers=headers)
        assert got.status_code == 200 and "conf_threshold" in got.json()
        put = client.put("/api/settings/ai", json={"conf_threshold": 0.4}, headers=headers)
        assert put.status_code == 200 and put.json()["parametres"]["conf_threshold"] == 0.4

    def test_systeme_modules_et_logs(self, client):
        token = _login(client).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        modules = client.get("/api/system/modules", headers=headers)
        assert modules.status_code == 200 and isinstance(modules.json(), dict)
        logs = client.get("/api/system/logs", headers=headers)
        assert logs.status_code == 200

    def test_assistant_repond(self, client):
        token = _login(client).json()["token"]
        response = client.post("/api/intelligence/assistant",
                               json={"message": "combien d'alertes aujourd'hui ?"},
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert "alerte" in response.json()["reponse"].lower()

    def test_rapport_se_genere(self, client):
        token = _login(client).json()["token"]
        response = client.post("/api/intelligence/report", json={"days": 7},
                               headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["chemin"].startswith("data/reports/")

    def test_medias_traversee_bloquee_api(self, client):
        token = _login(client).json()["token"]
        response = client.get("/api/media/../../etc/passwd",
                              headers={"Authorization": f"Bearer {token}"})
        assert response.status_code in (400, 404)

    def test_tracabilite_audit(self, client):
        token = _login(client).json()["token"]
        _create_user(client, token, "audit_target", role="observateur")
        from ga.data.repositories import AuditRepo
        with db.session_scope() as session:
            rows = AuditRepo(session).query(action="utilisateur_cree")
        assert len(rows) == 1 and rows[0].target == "audit_target"
