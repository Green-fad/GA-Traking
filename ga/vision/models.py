"""Registre de versionnement des modeles IA : empreinte SHA-256, activation, historique."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ga.core.logging import get_logger

log = get_logger("ga.vision.models")

REGISTRY_FILE = Path("models/registry.json")


def file_sha256(path: str | Path) -> str:
    sha = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


class ModelsRegistry:
    """Registre fichier des poids IA : {models: [{name, version, path, sha256, classes}]}.

    Les poids ne sont jamais versionnes dans git ; le registre garantit
    la tracabilite (version + empreinte) de chaque modele deploye.
    """

    def __init__(self, registry_path: str | Path = REGISTRY_FILE) -> None:
        self.path = Path(registry_path)
        self._models: list[dict[str, Any]] = []
        if self.path.exists():
            try:
                self._models = json.loads(self.path.read_text(encoding="utf-8")).get("models", [])
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("registre de modeles illisible, reinitialise", extra={"ctx": {"erreur": str(exc)}})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"models": self._models}, indent=2), encoding="utf-8")

    def register(self, name: str, version: str, path: str, classes: list[str] | None = None,
                 *, verify: bool = True) -> dict[str, Any]:
        """Enregistrer un modele (verifie l'existence et calcule l'empreinte)."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"modele introuvable : {path}")
        sha = file_sha256(p) if verify else ""
        entry = {"name": name, "version": version, "path": str(p), "sha256": sha,
                 "classes": classes or [], "added_at": datetime.now(timezone.utc).isoformat()}
        self._models = [m for m in self._models if not (m["name"] == name and m["version"] == version)]
        self._models.append(entry)
        self._save()
        log.info("modele enregistre", extra={"ctx": {"nom": name, "version": version, "sha256": sha[:16]}})
        return entry

    def verify_integrity(self, name: str, version: str) -> bool:
        """Verifier que le fichier du modele correspond toujours a son empreinte."""
        entry = self.get(name, version)
        if entry is None or not entry.get("sha256"):
            return False
        path = Path(entry["path"])
        if not path.exists():
            return False
        return file_sha256(path) == entry["sha256"]

    def get(self, name: str, version: str | None = None) -> Optional[dict[str, Any]]:
        for m in self._models:
            if m["name"] != name:
                continue
            if version is None or m["version"] == version:
                return m
        return None

    def latest(self, name: str) -> Optional[dict[str, Any]]:
        matches = [m for m in self._models if m["name"] == name]
        return max(matches, key=lambda m: m.get("added_at", "")) if matches else None

    def list(self) -> list[dict[str, Any]]:
        return list(self._models)
