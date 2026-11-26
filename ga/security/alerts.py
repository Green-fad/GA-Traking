"""Gestion des alertes : persistence, dedoublonnage, publication, sync cloud."""
from __future__ import annotations

import uuid
from typing import Any

from ga.core.events import EventBus, EventType, GAEvent, Severity
from ga.core.logging import get_logger
from ga.data import database as db
from ga.data.repositories import AlertRepo, SyncRepo

log = get_logger("ga.security.alerts")

# fenetre de dedoublonnage par (type, camera) en secondes
DEDUP_WINDOWS = {"intrusion": 60, "incendie_suspecte": 30, "anomalie": 120, "vehicule_arrete": 180}


class AlertManager:
    """Cree les alertes en base avec dedoublonnage et les pousse sur le bus + file de sync."""

    def __init__(self, bus: EventBus | None = None, *, cloud_sync: bool = False) -> None:
        self.bus = bus
        self.cloud_sync = cloud_sync

    def raise_alert(self, type_: str, message: str, camera_id: str | None = None,
                    severity: str = "warning", payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Retourne l'alerte creee, ou None si dedoublonnee."""
        window = DEDUP_WINDOWS.get(type_, 60)
        with db.session_scope() as session:
            recent = AlertRepo(session).recent_for_dedup(type_, camera_id, seconds=window)
            if recent is not None:
                return None
            alert_uuid = uuid.uuid4().hex
            AlertRepo(session).add(uuid=alert_uuid, type_=type_, message=message,
                                   camera_id=camera_id, severity=severity, payload=payload or {})
            if self.cloud_sync:
                SyncRepo(session).enqueue(
                    idempotency_key=f"alerte:{alert_uuid}",
                    payload_type="alerte",
                    payload={"uuid": alert_uuid, "type": type_, "message": message,
                             "camera_id": camera_id, "severity": severity, **(payload or {})},
                )
        log.info("alerte creee", extra={"ctx": {"type": type_, "camera": camera_id, "gravite": severity}})
        if self.bus:
            self.bus.publish_threadsafe(GAEvent(
                type=EventType.ALERT_CREATED, camera_id=camera_id,
                severity=Severity(severity),
                payload={"uuid": alert_uuid, "type": type_, "message": message, "severity": severity,
                         **(payload or {})},
            ))
        return {"uuid": alert_uuid, "type": type_, "message": message, "severity": severity}
