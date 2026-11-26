"""Test E2E de la synchronisation : SyncEngine REELLE -> serveur cloud REEL (ASGI).

Verifie la chaine complete : envoi par lots, deduplication par cle d'idempotence
cote cloud, attribution du site, agregats multisites.
"""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from cloud_server.app import create_app
from ga.data import database as db
from ga.data.repositories import SyncRepo
from ga.data.sync import SyncEngine


@pytest.fixture()
def cloud(tmp_path):
    """Serveur cloud reel avec sa propre base jetable."""
    app = create_app(db_url=f"sqlite:///{tmp_path}/cloud.db", token="jeton-cloud-test")
    return TestClient(app)


def _client_for(app) -> httpx.AsyncClient:
    from httpx import ASGITransport

    return httpx.AsyncClient(transport=ASGITransport(app=app.app), base_url="http://cloud-test")


class TestSynchronisationE2E:
    def test_reception_deduplication_et_stats(self, cloud, test_db):
        import asyncio

        engine = SyncEngine("http://cloud-test/api/v1", "jeton-cloud-test", site_name="Site-A")

        def with_client(fn) -> object:
            client = _client_for(cloud)
            try:
                return fn(client)
            finally:
                asyncio.run(client.aclose())

        with db.session_scope() as session:
            SyncRepo(session).enqueue("alerte:1", "alerte", {"type": "intrusion", "severity": "critical"})
            SyncRepo(session).enqueue("alerte:2", "alerte", {"type": "vehicule_arrete"})
            SyncRepo(session).enqueue("dossier:1", "dossier", {"kind": "exces_vitesse_candidat"})

        # 1er envoi : tout est recu
        sent = with_client(engine.flush_once)
        assert sent == 3
        health = cloud.get("/api/v1/health").json()
        assert health["elements_recus"] == 3

        # re-enfilement d'une cle DEJA envoyee : no-op cote site (idempotence locale),
        # rien n'est renvoye ; la deduplication cote cloud est testee ci-dessous
        with db.session_scope() as session:
            row = SyncRepo(session).enqueue("alerte:1", "alerte", {"type": "intrusion"})
            assert row.status == "sent"  # la file ne rejoue pas un envoi deja effectue
        sent2 = with_client(engine.flush_once)
        assert sent2 == 0
        response = cloud.post("/api/v1/sync/batch",
                              json={"items": [{"key": "alerte:1", "type": "alerte", "payload": {}}]},
                              headers={"Authorization": "Bearer jeton-cloud-test", "X-GA-Site": "Site-A"})
        assert response.status_code == 200
        assert response.json()["doublons"] == 1

        # authentification : jeton invalide refuse
        refused = cloud.get("/api/v1/stats/multisite",
                            headers={"Authorization": "Bearer mauvais"})
        assert refused.status_code == 401

        # agregats multisites calcules depuis les donnees recues (3 elements : 2 alertes + 1 dossier)
        stats = cloud.get("/api/v1/stats/multisite", params={"days": 7},
                          headers={"Authorization": "Bearer jeton-cloud-test"}).json()
        assert stats["par_site"]["Site-A"]["total"] == 3
        assert stats["types_global"]["alerte"] == 2
        assert stats["types_global"]["dossier"] == 1

        # liste des sites avec derniere reception
        sites = cloud.get("/api/v1/sites", headers={"Authorization": "Bearer jeton-cloud-test"}).json()
        assert any(s["site"] == "Site-A" for s in sites)

    def test_le_serveur_survit_a_un_lot_invalide(self, cloud):
        response = cloud.post("/api/v1/sync/batch",
                              json={"items": [{"key": "x", "type": "", "payload": {}}]},
                              headers={"Authorization": "Bearer jeton-cloud-test"})
        assert response.status_code in (200, 422)  # jamais de crash serveur
