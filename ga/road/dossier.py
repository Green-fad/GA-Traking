"""Constitution de dossiers de preuves : images horodatees + metriques, verifiables par un humain.

Un dossier contient : type, camera, piste, serie d'images de preuve, metriques
(vitesse, trajectoire), horodatage. Statut initial : 'a_verifier'.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ga.core.events import EventBus, EventType, GAEvent
from ga.core.logging import get_logger
from ga.data import database as db
from ga.data.media import MediaStore
from ga.data.repositories import DossierRepo, SyncRepo

log = get_logger("ga.road.dossier")


@dataclass
class EvidenceFrame:
    path: str
    ts: float
    label: str


class DossierBuilder:
    """Cree les dossiers dans la base + met les evenements en file de synchronisation."""

    def __init__(self, media: MediaStore, bus: EventBus | None = None,
                 *, cloud_sync: bool = False) -> None:
        self.media = media
        self.bus = bus
        self.cloud_sync = cloud_sync

    def capture_frames(self, frame: np.ndarray, camera_id: str, track_id: int, count: int = 3) -> list[EvidenceFrame]:
        """Capturer une sequence de preuve a partir de l'image courante."""
        frames = [self.media.save_frame(frame, camera_id, prefix=f"preuve_t{track_id}_{i}")]
        return [EvidenceFrame(path=frames[0], ts=0.0, label="image_principale")]

    def build_dossier(self, kind: str, camera_id: str, track_id: int, ts: float,
                      frame: np.ndarray | None, metrics: dict[str, Any],
                      trajectory: list[tuple[float, float]] | None = None,
                      plate: str | None = None) -> dict[str, Any]:
        """Constituer et enregistrer un dossier de preuve ; retourne son resume.

        `plate` : plaque lue par l'ANPR au moment de l'infraction (None si non lue).
        """
        dossier_uuid = uuid.uuid4().hex
        evidence: dict[str, Any] = {
            "type": kind,
            "camera_id": camera_id,
            "track_id": track_id,
            "ts": ts,
            "metriques": metrics,
            "images": [],
            "trajectoire": trajectory or [],
        }
        if plate:
            evidence["plaque"] = plate
        if frame is not None:
            try:
                rel = self.media.save_frame(frame, camera_id, prefix=f"preuve_{kind}_t{track_id}")
                evidence["images"].append({"chemin": rel, "ts": ts, "etiquette": "preuve_principale"})
            except (IOError, ValueError) as exc:
                log.warning("image de preuve non sauvegardee", extra={"ctx": {"erreur": str(exc)}})

        with db.session_scope() as session:
            DossierRepo(session).add(uuid=dossier_uuid, kind=kind, evidence=evidence, camera_id=camera_id)
            if self.cloud_sync:
                SyncRepo(session).enqueue(
                    idempotency_key=f"dossier:{dossier_uuid}",
                    payload_type="dossier",
                    payload=evidence,
                )
        log.info("dossier de preuve cree", extra={"ctx": {
            "uuid": dossier_uuid, "type": kind, "camera": camera_id, "piste": track_id}})
        if self.bus:
            self.bus.publish_threadsafe(GAEvent(
                type=EventType.DOSSIER_CREATED, camera_id=camera_id,
                payload={"uuid": dossier_uuid, "type": kind, "piste": track_id},
            ))
        return {"uuid": dossier_uuid, "type": kind, "statut": "a_verifier", **evidence}
