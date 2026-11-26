"""Registre de services GA-CORE : cycle de vie demarrage/arret + sante."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from ga.core.logging import get_logger

log = get_logger("ga.core.registry")


class HealthStatus:
    def __init__(self, healthy: bool, detail: str = "", **metrics: object) -> None:
        self.healthy = healthy
        self.detail = detail
        self.metrics = metrics

    def to_dict(self) -> dict:
        return {"healthy": self.healthy, "detail": self.detail, **self.metrics}


class GAModule(ABC):
    """Contrat d'un module GAtraking gere par le registre."""

    name: str = "module"

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    def health(self) -> HealthStatus: ...


class ServiceRegistry:
    """Registre central : demarrage ordonne, arret propre, agregation de sante."""

    def __init__(self) -> None:
        self._modules: dict[str, GAModule] = {}
        self._started_at: dict[str, float] = {}

    def register(self, module: GAModule, *, replace: bool = False) -> None:
        if module.name in self._modules and not replace:
            raise ValueError(f"module deja enregistre : {module.name}")
        self._modules[module.name] = module

    def get(self, name: str) -> GAModule:
        if name not in self._modules:
            raise KeyError(f"module inconnu : {name}")
        return self._modules[name]

    @property
    def module_names(self) -> list[str]:
        return list(self._modules.keys())

    async def start_all(self) -> None:
        for name, module in self._modules.items():
            t0 = time.perf_counter()
            try:
                await module.start()
                self._started_at[name] = time.time()
                log.info("module demarre", extra={"ctx": {"module": name, "duree_ms": round((time.perf_counter() - t0) * 1000, 1)}})
            except Exception as exc:
                log.error("demarrage de module en echec", exc_info=exc, extra={"ctx": {"module": name}})

    async def stop_all(self) -> None:
        for name, module in reversed(list(self._modules.items())):
            try:
                await module.stop()
                self._started_at.pop(name, None)
                log.info("module arrete", extra={"ctx": {"module": name}})
            except Exception as exc:
                log.error("arret de module en echec", exc_info=exc, extra={"ctx": {"module": name}})

    def health_all(self) -> dict[str, dict]:
        report: dict[str, dict] = {}
        for name, module in self._modules.items():
            try:
                status = module.health()
                data = status.to_dict()
            except Exception as exc:
                data = {"healthy": False, "detail": f"echec du diagnostic : {exc}"}
            data["uptime_s"] = round(time.time() - self._started_at[name], 1) if name in self._started_at else 0.0
            report[name] = data
        return report

    def is_healthy(self) -> bool:
        return all(s.to_dict().get("healthy") for s in (m.health() for m in self._modules.values()))
