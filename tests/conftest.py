"""Fixtures communes : base isolee par test, magasin de medias, bus."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# racine du projet sur sys.path (imports des modules ga et tools)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ga.core.config import AppConfig
from ga.core.events import EventBus
from ga.data import database as db
from ga.data.media import MediaStore


@pytest.fixture()
def test_db(tmp_path, request):
    """Base SQLite jetable, unique par test (le module database est global)."""
    url = f"sqlite:///{tmp_path}/test_{request.node.name.replace('/', '_')}.db"
    db.init_db(url)
    yield url
    db.dispose()


@pytest.fixture()
def media_store(tmp_path):
    return MediaStore(str(tmp_path / "media"), retention_days=7)


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def base_cfg() -> AppConfig:
    return AppConfig()
