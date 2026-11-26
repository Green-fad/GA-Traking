"""Tests couche registres officiels : connecteurs, garde-fous, RBAC, audit, E2E API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ga.core.config import AppConfig, RegistriesConfig
from ga.core.events import EventBus
from ga.core.registry import ServiceRegistry
from ga.data import database as db
from ga.data.cache import CacheClient
from ga.data.media import MediaStore
from ga.data.repositories import DossierRepo
from ga.intelligence.assistant import Assistant
from ga.intelligence.registries import (MockRegistryConnector, OfflineRegistryConnector,
                                        RegistryInactive, RegistryRateLimited,
                                        RegistryUnavailable, RegistryService,
                                        masquer_cin, masquer_plaque)
from ga.intelligence.reports import ReportGenerator
from ga.operations.app import AppContext, create_app

ADMIN_PASS = "GAt Admin#2026"
OPERATEUR_PASS = "MotDePasse#123"


@pytest.fixture()
def client(test_db, tmp_path):
    cfg = AppConfig()
    cfg.server.secret_key = "cle-de-test"
    cfg.data.media_dir = str(tmp_path / "media")
    cfg.registries = RegistriesConfig(active=True, base_legale="arrete d'habilitation de test",
                                      fournisseur="mock", limite_minute=4)
    ctx = AppContext(cfg=cfg, bus=EventBus(), registry=ServiceRegistry(), manager=None,
                     media=MediaStore(str(tmp_path / "media")), cache=CacheClient("", force_memory=True),
                     assistant=Assistant(), report_generator=ReportGenerator("Site test"))
    return TestClient(create_app(ctx))


def _login(client, username="admin", password=ADMIN_PASS):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _dossier(plaque: str | None = "AB123CD") -> str:
    import uuid as _uuid

    uuid = "dos" + _uuid.uuid4().hex[:29]
    with db.session_scope() as session:
        evidence = {"type": "exces_vitesse", "images": []}
        if plaque:
            evidence["plaque"] = plaque
        DossierRepo(session).add(uuid=uuid, kind="exces_vitesse", evidence=evidence)
    return uuid


class TestGardeFous:
    def test_inactif_par_defaut(self):
        service = RegistryService(RegistriesConfig(), connecteur=MockRegistryConnector())
        with pytest.raises(RegistryInactive):
            service.identifier_vehicule("AB123CD", "admin")

    def test_base_legale_obligatoire(self):
        service = RegistryService(RegistriesConfig(active=True), connecteur=MockRegistryConnector())
        with pytest.raises(RegistryInactive):
            service.identifier_vehicule("AB123CD", "admin")

    def test_limite_anti_requetes_massives(self):
        cfg = RegistriesConfig(active=True, base_legale="test", limite_minute=3)
        service = RegistryService(cfg, connecteur=MockRegistryConnector())
        for _ in range(3):
            service.identifier_vehicule("AB123CD", "op1")
        with pytest.raises(RegistryRateLimited):
            service.identifier_vehicule("AB123CD", "op1")
        # un autre utilisateur garde son propre quota
        assert service.identifier_vehicule("AB123CD", "op2")["trouve"] is True


class TestConnecteurs:
    def test_mock_titulaire(self):
        brut = MockRegistryConnector().cherche_titulaire("ab-123-cd")
        assert brut is not None and brut["nom"] == "Benali"

    def test_offline_extract_csv(self, tmp_path):
        (tmp_path / "vehicules.csv").write_text(
            "plaque;cin;nom;prenom;marque;modele;couleur\n"
            "XY987ZT;C111222;Alami;Nadia;Toyota;Corolla;rouge\n", encoding="utf-8")
        (tmp_path / "identites.csv").write_text(
            "cin;nom;prenom;date_naissance;adresse\n"
            "C111222;Alami;Nadia;1990-01-15;3 rue des Fleurs\n", encoding="utf-8")
        connecteur = OfflineRegistryConnector(str(tmp_path))
        titulaire = connecteur.cherche_titulaire("xy-987-zt")
        identite = connecteur.cherche_identite("c111222")
        assert titulaire["nom"] == "Alami" and titulaire["modele"] == "Corolla"
        assert identite["date_naissance"] == "1990-01-15"

    def test_offline_extract_absent(self, tmp_path):
        with pytest.raises(RegistryUnavailable):
            OfflineRegistryConnector(str(tmp_path / "inexistant"))

    def test_masquages(self):
        assert masquer_cin("C198745") == "C1***5"
        assert masquer_plaque("AB123CD") == "AB***D"


class TestService:
    def _service(self, **kwargs) -> tuple[RegistryService, list]:
        audits: list = []
        cfg = RegistriesConfig(active=True, base_legale="test", **kwargs)
        return RegistryService(cfg, connecteur=MockRegistryConnector(),
                               audit_fn=lambda **kw: audits.append(kw)), audits

    def test_masquage_par_role(self):
        service, _ = self._service()
        admin = service.identifier_vehicule("AB123CD", "a", role="admin")
        operateur = service.identifier_vehicule("AB123CD", "o", role="operateur")
        assert admin["cin"] == "C198745"
        assert operateur["cin"] == "C1***5"

    def test_audit_trace_sans_plaque_en_clair(self):
        service, audits = self._service()
        service.identifier_vehicule("AB123CD", "inspecteur", dossier_uuid="dos42")
        assert audits and audits[0]["action"] == "registre_vehicule"
        assert audits[0]["target"] == "dossier:dos42"
        assert "AB123CD" not in str(audits)  # jamais de plaque en clair dans l'audit

    def test_inconnu_reponse_sobriete(self):
        service, audits = self._service()
        reponse = service.identifier_vehicule("ZZ999YY", "a")
        assert reponse["trouve"] is False
        assert "nom" not in reponse  # aucun champ personnel invente


class TestApiRegistres:
    def test_identification_depuis_la_plaque_anpr(self, client):
        token = _login(client).json()["token"]
        uuid = _dossier("AB123CD")
        reponse = client.post(f"/api/dossiers/{uuid}/identifier",
                              headers={"Authorization": f"Bearer {token}"})
        assert reponse.status_code == 200
        corps = reponse.json()
        assert corps["trouve"] is True and corps["nom"] == "Benali"
        # l'identification est conservee dans le dossier
        dossier = client.get(f"/api/dossiers/{uuid}",
                             headers={"Authorization": f"Bearer {token}"}).json()
        assert dossier["preuves"]["identification"]["nom"] == "Benali"

    def test_observateur_refuse(self, client):
        token_admin = _login(client).json()["token"]
        client.post("/api/users", json={"username": "obs1", "password": OPERATEUR_PASS, "role": "observateur"},
                    headers={"Authorization": f"Bearer {token_admin}"})
        token_obs = _login(client, "obs1", OPERATEUR_PASS).json()["token"]
        uuid = _dossier("AB123CD")
        assert client.post(f"/api/dossiers/{uuid}/identifier",
                           headers={"Authorization": f"Bearer {token_obs}"}).status_code == 403

    def test_sans_plaque_refuse(self, client):
        token = _login(client).json()["token"]
        uuid = _dossier(None)
        assert client.post(f"/api/dossiers/{uuid}/identifier",
                           headers={"Authorization": f"Bearer {token}"}).status_code == 400

    def test_limite_debit_api(self, client):
        token = _login(client).json()["token"]
        codes = [client.post(f"/api/dossiers/{_dossier('AB123CD')}/identifier",
                             headers={"Authorization": f"Bearer {token}"}).status_code
                 for _ in range(5)]
        assert codes[:4] == [200, 200, 200, 200]
        assert codes[4] == 429  # limite_minute=4 de la fixture

    def test_interrogation_directe_exige_un_dossier(self, client):
        token = _login(client).json()["token"]
        uuid = _dossier("1234AB56")
        sans_finalite = client.get("/api/registres/vehicule/1234AB56",
                                   headers={"Authorization": f"Bearer {token}"})
        assert sans_finalite.status_code == 422  # parametre dossier obligatoire
        dossier_inconnu = client.get("/api/registres/vehicule/1234AB56",
                                     params={"dossier": "dos-inconnu"},
                                     headers={"Authorization": f"Bearer {token}"})
        assert dossier_inconnu.status_code == 400
        ok = client.get("/api/registres/vehicule/1234AB56", params={"dossier": uuid},
                        headers={"Authorization": f"Bearer {token}"})
        assert ok.status_code == 200 and ok.json()["trouve"] is True

    def test_registres_inactifs_sur_api(self, test_db, tmp_path):
        cfg = AppConfig()
        cfg.server.secret_key = "cle-de-test"
        cfg.data.media_dir = str(tmp_path / "media")  # registries par defaut : inactif
        ctx = AppContext(cfg=cfg, bus=EventBus(), registry=ServiceRegistry(), manager=None,
                         media=MediaStore(str(tmp_path / "media")),
                         cache=CacheClient("", force_memory=True),
                         assistant=Assistant(), report_generator=ReportGenerator("Site test"))
        client = TestClient(create_app(ctx))
        token = _login(client).json()["token"]
        uuid = _dossier("AB123CD")
        assert client.post(f"/api/dossiers/{uuid}/identifier",
                           headers={"Authorization": f"Bearer {token}"}).status_code == 503

    def test_etat_reserve_admin(self, client):
        token_admin = _login(client).json()["token"]
        etat = client.get("/api/registres/etat", headers={"Authorization": f"Bearer {token_admin}"})
        assert etat.status_code == 200 and etat.json()["actif"] is True
        client.post("/api/users", json={"username": "obs2", "password": OPERATEUR_PASS, "role": "observateur"},
                    headers={"Authorization": f"Bearer {token_admin}"})
        token_obs = _login(client, "obs2", OPERATEUR_PASS).json()["token"]
        assert client.get("/api/registres/etat",
                          headers={"Authorization": f"Bearer {token_obs}"}).status_code == 403
