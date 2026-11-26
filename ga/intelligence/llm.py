"""Clients LLM : cloud (API compatible OpenAI) et local (API compatible Ollama).

Aucune donnee personnelle n'est envoyee au cloud : les requetes sont limitees
aux agregats operationnels (comptages, statistiques). Si aucun LLM n'est
configure, le systeme reste entierement fonctionnel (modeles de rapports
deterministes).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import httpx

from ga.core.config import LLMConfig
from ga.core.logging import get_logger

log = get_logger("ga.intelligence.llm")


class LLMUnavailable(RuntimeError):
    pass


class BaseLLM(ABC):
    name: str = "base"

    @abstractmethod
    def chat(self, system: str, user: str) -> str:
        """Poser une question au modele et retourner sa reponse textuelle."""


class CloudLLM(BaseLLM):
    """API compatible OpenAI : POST {api_url}/chat/completions."""

    def __init__(self, cfg: LLMConfig) -> None:
        if not cfg.api_url or not cfg.model:
            raise LLMUnavailable("LLM cloud mal configure (api_url / model manquants)")
        self.api_url = cfg.api_url.rstrip("/")
        self.model = cfg.model
        self.api_key = cfg.api_key
        self.timeout = cfg.timeout_seconds
        self.name = f"cloud:{cfg.model}"

    def chat(self, system: str, user: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.api_url}/chat/completions", headers=headers, json={
                "model": self.model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 0.2,
            })
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


class LocalLLM(BaseLLM):
    """API compatible Ollama : POST {api_url}/api/generate (modele execute sur site)."""

    def __init__(self, cfg: LLMConfig) -> None:
        if not cfg.api_url or not cfg.model:
            raise LLMUnavailable("LLM local mal configure (api_url / model manquants)")
        self.api_url = cfg.api_url.rstrip("/")
        self.model = cfg.model
        self.timeout = cfg.timeout_seconds
        self.name = f"local:{cfg.model}"

    def chat(self, system: str, user: str) -> str:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.api_url}/api/generate", json={
                "model": self.model,
                "prompt": f"{system}\n\n{user}",
                "stream": False,
            })
            response.raise_for_status()
            return response.json().get("response", "")


def create_llm(cfg: LLMConfig) -> Optional[BaseLLM]:
    """Fabrique : retourne None si aucun LLM n'est configure (mode degrade)."""
    try:
        if cfg.provider == "cloud":
            return CloudLLM(cfg)
        if cfg.provider == "local":
            return LocalLLM(cfg)
    except LLMUnavailable as exc:
        log.warning("LLM indisponible, fonctionnement sans LLM", extra={"ctx": {"raison": str(exc)}})
    return None
