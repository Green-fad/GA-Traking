"""Application du serveur cloud GAtraking (fabrique FastAPI)."""
from __future__ import annotations

import hmac
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from cloud_server.models import CloudBase, KnownKey, ReceivedItem, utcnow


class SyncItem(BaseModel):
    key: str = Field(min_length=3, max_length=80)
    type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncBatch(BaseModel):
    items: list[SyncItem] = Field(default_factory=list, max_length=500)


def _require_token(expected: str):
    def check(authorization: str | None = Header(default=None)) -> None:
        if not expected:
            return  # jeton non configure : reception ouverte (environnement de test)
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "jeton requis")
        if not hmac.compare_digest(authorization.removeprefix("Bearer "), expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "jeton invalide")
    return check


def create_app(db_url: str | None = None, token: str | None = None) -> FastAPI:
    db_url = db_url or os.environ.get("GA_CLOUD_DB", "sqlite:///data/cloud.db")
    if db_url.startswith("sqlite:///"):
        Path(db_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(db_url, future=True, connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {})
    CloudBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    expected_token = token if token is not None else os.environ.get("GA_CLOUD_TOKEN", "")
    auth = _require_token(expected_token)

    app = FastAPI(title="GAtraking Cloud", version="1.0.0", docs_url="/api/docs")

    @app.get("/api/v1/health")
    def health():
        with session_factory() as s:
            total = s.scalar(select(func.count(ReceivedItem.id))) or 0
        return {"service": "gatraking-cloud", "sain": True, "elements_recus": total}

    @app.post("/api/v1/sync/batch", status_code=200, dependencies=[Depends(auth)])
    def receive_batch(batch: SyncBatch, x_ga_site: str | None = Header(default=None)):
        """Reception idempotente : une cle deja connue est comptee 'duplicate' et ignoree."""
        site = (x_ga_site or "site-inconnu")[:128]
        received, duplicates = 0, 0
        with session_factory() as s:
            for item in batch.items:
                known = s.get(KnownKey, item.key)
                if known is not None or s.scalars(
                        select(ReceivedItem).where(ReceivedItem.idempotency_key == item.key)).first():
                    duplicates += 1
                    if known is None:
                        s.add(KnownKey(key=item.key, source=site, note="deja recu"))
                    continue
                s.add(ReceivedItem(idempotency_key=item.key, site=site,
                                   payload_type=item.type, payload=item.payload))
                received += 1
            s.commit()
        return {"recus": received, "doublons": duplicates, "total_lot": len(batch.items)}

    @app.get("/api/v1/stats/multisite", dependencies=[Depends(auth)])
    def multisite_stats(days: int = 7):
        """Agregats multisites : par site, par type — base sur les donnees reellement recues."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        with session_factory() as s:
            rows = s.execute(
                select(ReceivedItem.site, ReceivedItem.payload_type, func.count(ReceivedItem.id))
                .where(ReceivedItem.received_at >= since)
                .group_by(ReceivedItem.site, ReceivedItem.payload_type)).all()
            sites = s.execute(
                select(ReceivedItem.site, func.count(ReceivedItem.id))
                .where(ReceivedItem.received_at >= since)
                .group_by(ReceivedItem.site)).all()
        by_site_type: dict[str, dict[str, int]] = {}
        for site, ptype, count in rows:
            by_site_type.setdefault(site, {})[ptype] = count
        global_types: Counter = Counter()
        for types in by_site_type.values():
            global_types.update(types)
        return {"fenetre_jours": days,
                "par_site": {site: {"total": n, "par_type": by_site_type.get(site, {})}
                             for site, n in sites},
                "types_global": dict(global_types)}

    @app.get("/api/v1/sites", dependencies=[Depends(auth)])
    def sites():
        with session_factory() as s:
            rows = s.execute(select(ReceivedItem.site, func.max(ReceivedItem.received_at),
                                    func.count(ReceivedItem.id)).group_by(ReceivedItem.site)).all()
        return [{"site": site, "elements": n, "derniere_reception": str(last)} for site, last, n in rows]

    return app


app = create_app()
