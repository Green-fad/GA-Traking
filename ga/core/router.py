"""Routage des traitements entre local et cloud (GA-CORE).

Regles :
- alertes urgentes et traitement essentiel : TOUJOURS local (continuite offline).
- analyses approfondies / rapports consolides : cloud si disponible et autorise.
- hors ligne : tout local + mise en file persistante pour synchronisation ulterieure.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from ga.core.logging import get_logger

log = get_logger("ga.core.router")


class Route(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    LOCAL_THEN_CLOUD = "local_then_cloud"  # traitement local immediat + synchronisation
    QUEUE_FOR_SYNC = "queue_for_sync"


class WorkloadKind(str, Enum):
    DETECTION = "detection"
    TRACKING = "tracking"
    URGENT_ALERT = "urgent_alert"
    EVENT_STORAGE = "event_storage"
    LLM_ANALYSIS = "llm_analysis"
    CONSOLIDATED_REPORT = "consolidated_report"
    MULTI_SITE_STATS = "multi_site_stats"
    MODEL_DISTRIBUTION = "model_distribution"
    BACKUP = "backup"


class CloudLinkState:
    """Etat observe de la liaison cloud (latence, derniere connexion)."""

    def __init__(self) -> None:
        self.online: bool = False
        self.last_check: float = 0.0
        self.last_latency_ms: float | None = None
        self.consecutive_failures: int = 0

    def record_success(self, latency_ms: float) -> None:
        self.online = True
        self.last_check = time.time()
        self.last_latency_ms = latency_ms
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        self.online = False
        self.last_check = time.time()
        self.consecutive_failures += 1


class LocalCloudRouter:
    """Decide, pour chaque charge de travail, du traitement local ou cloud."""

    def __init__(self, cloud_enabled: bool, cloud_state: CloudLinkState | None = None) -> None:
        self.cloud_enabled = cloud_enabled
        self.state = cloud_state or CloudLinkState()

    def route(self, kind: WorkloadKind) -> Route:
        cloud_available = self.cloud_enabled and self.state.online
        if kind in (WorkloadKind.DETECTION, WorkloadKind.TRACKING, WorkloadKind.URGENT_ALERT, WorkloadKind.EVENT_STORAGE):
            # Essentiels : jamais dependants du cloud.
            return Route.LOCAL
        if kind in (WorkloadKind.LLM_ANALYSIS, WorkloadKind.CONSOLIDATED_REPORT, WorkloadKind.MULTI_SITE_STATS):
            if cloud_available:
                return Route.CLOUD
            return Route.QUEUE_FOR_SYNC if kind == WorkloadKind.MULTI_SITE_STATS else Route.LOCAL
        if kind == WorkloadKind.BACKUP:
            return Route.CLOUD if cloud_available else Route.QUEUE_FOR_SYNC
        if kind == WorkloadKind.MODEL_DISTRIBUTION:
            return Route.CLOUD if cloud_available else Route.LOCAL
        return Route.LOCAL
