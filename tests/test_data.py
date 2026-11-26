"""Tests GA-DATA : file de sync idempotente, medias securises, registre de modeles."""
from __future__ import annotations

import httpx
import numpy as np
import pytest
from sqlalchemy import select

from ga.data import database as db
from ga.data.media import MediaStore
from ga.data.models import SyncQueue
from ga.data.repositories import ModelRegistryRepo, SyncRepo
from ga.data.sync import SyncEngine
from ga.vision.models import ModelsRegistry


class TestFileSync:
    def test_idempotence_cle_unique(self, test_db):
        with db.session_scope() as session:
            SyncRepo(session).enqueue("alerte:abc", "alerte", {"x": 1})
            SyncRepo(session).enqueue("alerte:abc", "alerte", {"x": 1})  # doublon
            rows = SyncRepo(session).claim_batch(limit=10)
        assert len(rows) == 1, "une seule entree pour une cle d'idempotence"

    def test_envoi_marque_envoye(self, test_db):
        engine = SyncEngine("https://cloud.test", "token", batch_size=10)
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            assert "Idempotency-Key" in request.headers
            assert request.headers["Authorization"] == "Bearer token"
            return httpx.Response(200, json={"ok": True})

        with db.session_scope() as session:
            SyncRepo(session).enqueue("evt:1", "evenement", {"a": 1})
            SyncRepo(session).enqueue("evt:2", "evenement", {"b": 2})
        transport = httpx.MockTransport(handler)
        sent = engine.flush_once(httpx.AsyncClient(transport=transport))
        assert sent == 2
        with db.session_scope() as session:
            assert SyncRepo(session).stats().get("sent") == 2

    def test_reseau_hors_ligne_replanifie(self, test_db):
        engine = SyncEngine("https://cloud.test", "token")

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("coupure reseau")

        with db.session_scope() as session:
            SyncRepo(session).enqueue("evt:offline", "evenement", {"a": 1})
        engine.flush_once(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with db.session_scope() as session:
            stats = SyncRepo(session).stats()
            rows = session.scalars(select(SyncQueue)).all()
        assert stats.get("pending", 0) == 1, "l'evenement doit rester en file (aucune perte)"
        assert len(rows) == 1 and rows[0].attempts >= 1, \
            "l'echec reseau doit incrementer les tentatives sans supprimer l'entree"

    def test_409_traite_comme_deja_connu(self, test_db):
        engine = SyncEngine("https://cloud.test", "token")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(409, json={"detail": "deja recu"})

        with db.session_scope() as session:
            SyncRepo(session).enqueue("evt:dup", "evenement", {"a": 1})
        sent = engine.flush_once(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        assert sent == 1
        with db.session_scope() as session:
            assert SyncRepo(session).stats().get("sent") == 1


class TestMedias:
    def test_sauvegarde_et_lecture(self, media_store):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[:, :, 0] = 255
        rel = media_store.save_frame(frame, "cam-01", prefix="preuve")
        assert rel.startswith("cam-01/")
        data = media_store.read_bytes(rel)
        assert len(data) > 500

    def test_traversee_de_chemin_bloquee(self, media_store):
        with pytest.raises(ValueError):
            media_store.resolve("../../etc/passwd")
        with pytest.raises(ValueError):
            media_store._safe_relpath("cam/../evil", "2026-01-01", "x.jpg")

    def test_purge_retention(self, media_store, tmp_path):
        import os
        import time
        frame = np.zeros((50, 50, 3), dtype=np.uint8)
        rel = media_store.save_frame(frame, "cam-01")
        path = media_store.resolve(rel)
        old_ts = time.time() - 90 * 86400  # 90 jours
        os.utime(path, (old_ts, old_ts))
        removed = media_store.cleanup(retention_days=30)
        assert removed == 1 and not path.exists()


class TestRegistreModeles:
    def test_enregistrement_et_integrite(self, tmp_path):
        registry = ModelsRegistry(tmp_path / "registry.json")
        fake_model = tmp_path / "yolov8n.onnx"
        fake_model.write_bytes(b"MODELE-FACTICE-" * 100)
        entry = registry.register("yolov8n", "1.0", str(fake_model), classes=["personne", "voiture"])
        assert entry["sha256"]
        assert registry.verify_integrity("yolov8n", "1.0") is True
        fake_model.write_bytes(b"MODELE-ALTERE-" * 100)
        assert registry.verify_integrity("yolov8n", "1.0") is False

    def test_versionnement_actif(self, test_db):
        with db.session_scope() as session:
            repo = ModelRegistryRepo(session)
            repo.register("detecteur", "1.0", "models/a.onnx", "sha-a", ["voiture"])
            repo.register("detecteur", "1.1", "models/b.onnx", "sha-b", ["voiture"])
            repo.activate("detecteur", "1.0")
            assert repo.active("detecteur").version == "1.0"
            repo.activate("detecteur", "1.1")
            active = repo.active("detecteur")
            assert active.version == "1.1"
            others = [m for m in repo.list() if m.name == "detecteur" and m.activated]
            assert len(others) == 1, "un seul modele actif par nom"
