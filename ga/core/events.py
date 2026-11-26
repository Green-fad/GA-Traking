"""Bus d'evenements asynchrone type de GA-CORE.

Tous les modules publient des evenements typed (pydantic) ; les abonnes
(synchrones ou asynchrones) sont isoles : une erreur dans un handler
n'interrompt jamais la chaine de traitement.
"""
from __future__ import annotations

import asyncio
import inspect
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel, Field

from ga.core.logging import get_logger

log = get_logger("ga.core.events")


class EventType(str, Enum):
    CAMERA_FRAME = "camera.frame"
    DETECTION_BATCH = "vision.detections"
    TRACKS_UPDATED = "track.tracks_updated"
    COUNT_UPDATE = "road.count_update"
    SPEED_EVENT = "road.speed_event"
    TRAFFIC_EVENT = "road.traffic_event"
    INTRUSION = "security.intrusion"
    FIRE_SUSPECTED = "security.fire_suspected"
    ANOMALY = "security.anomaly"
    ALERT_CREATED = "alert.created"
    ALERT_ACK = "alert.ack"
    ALERT_RESOLVED = "alert.resolved"
    DOSSIER_CREATED = "dossier.created"
    DOSSIER_DECISION = "dossier.decision"
    SYNC_QUEUED = "sync.queued"
    SYSTEM_STATUS = "system.status"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class GAEvent(BaseModel):
    """Evenement normalise circulant entre les modules."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: EventType
    camera_id: Optional[str] = None
    severity: Severity = Severity.INFO
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"use_enum_values": True}


Handler = Callable[[GAEvent], Any]  # handler sync (retour direct) ou async (coroutine)


class EventBus:
    """Bus pub/sub async avec isolation des erreurs et support multi-producteurs."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        self._global_handlers: list[Handler] = []
        self._queue: asyncio.Queue[GAEvent | None] = asyncio.Queue(maxsize=10000)
        self._worker: asyncio.Task | None = None
        self._published = 0
        self._dropped = 0

    def subscribe(self, handler: Handler, event_type: EventType | None = None) -> None:
        """Enregistrer un handler pour un type donne ou pour tous les evenements."""
        if event_type is None:
            self._global_handlers.append(handler)
        else:
            self._handlers[event_type].append(handler)

    def publish_threadsafe(self, event: GAEvent) -> None:
        """Publier depuis n'importe quel contexte (thread camera, boucle async, sync)."""
        try:
            loop = asyncio.get_running_loop()
            # boucle en cours dans ce thread : dispatch immediat
            self._dispatch(event)
            _ = loop
            return
        except RuntimeError:
            pass
        try:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(self._enqueue_sync, event)
        except RuntimeError:
            # Aucune boucle (tests / traitement offline) : dispatch direct.
            self._dispatch(event)

    def _enqueue_sync(self, event: GAEvent) -> None:
        try:
            self._queue.put_nowait(event)
            self._published += 1
        except asyncio.QueueFull:
            self._dropped += 1
            log.warning("file d'evenements pleine, evenement abandonne", extra={"ctx": {"type": event.type}})

    async def publish(self, event: GAEvent) -> None:
        """Publier depuis la boucle async."""
        if self._worker is None:
            self._dispatch(event)
            self._published += 1
            return
        self._enqueue_sync(event)

    def publish_sync(self, event: GAEvent) -> None:
        """Publication bloquante (demonstrations / tests sans boucle asyncio)."""
        self._dispatch(event)
        self._published += 1

    async def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._worker:
            self._queue.put_nowait(None)
            try:
                await asyncio.wait_for(self._worker, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._worker.cancel()
            self._worker = None

    async def _run(self) -> None:
        while True:
            event = await self._queue.get()
            if event is None:
                break
            self._dispatch(event)

    def _dispatch(self, event: GAEvent) -> None:
        """Invoquer les handlers (sync en ligne, async planifies), erreurs isolees."""
        for handler in self._handlers.get(EventType(event.type), []) + self._global_handlers:
            try:
                result = handler(event)
                if inspect.iscoroutine(result) or isinstance(result, asyncio.Future):
                    self._schedule_coro(handler, result, event)
            except Exception as exc:  # isolation maximale du bus
                log.error("erreur au dispatch d'evenement", exc_info=exc,
                          extra={"ctx": {"type": event.type,
                                         "handler": getattr(handler, "__name__", "?")}})

    def _schedule_coro(self, handler: Handler, coro: Awaitable[None], event: GAEvent) -> None:
        """Executer une coroutine handler dans la boucle courante ou a part."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._safe_call(handler, coro, event))
        except RuntimeError:
            try:
                asyncio.run(self._safe_call(handler, coro, event))
            except Exception as exc:
                log.error("execution de handler async impossible", exc_info=exc,
                          extra={"ctx": {"type": event.type}})

    async def _safe_call(self, handler: Handler, coro: Awaitable[None], event: GAEvent) -> None:
        try:
            await coro
        except Exception as exc:
            log.error("handler d'evenement en echec", exc_info=exc,
                      extra={"ctx": {"handler": getattr(handler, "__name__", "?"),
                                     "type": event.type}})

    def stats(self) -> dict[str, int]:
        return {
            "published": self._published,
            "dropped": self._dropped,
            "queue_size": self._queue.qsize(),
            "subscribers": sum(len(v) for v in self._handlers.values()) + len(self._global_handlers),
        }
