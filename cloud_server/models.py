"""Modeles du serveur cloud : elements recus par site, deduplication par cle."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CloudBase(DeclarativeBase):
    pass


class ReceivedItem(CloudBase):
    """Element recu d'un site : la cle d'idempotence garantit l'unicite."""

    __tablename__ = "received_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    site: Mapped[str] = mapped_column(String(128), index=True)
    payload_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class KnownKey(CloudBase):
    """Cles deja connues (meme pour les elements ecartes) — reponse 409 sans double ecriture."""

    __tablename__ = "known_keys"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
