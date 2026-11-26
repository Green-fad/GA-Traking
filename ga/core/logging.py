"""Journalisation structuree JSON pour tous les modules GAtraking."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """Formateur JSON : timestamp ISO, niveau, module, message, contexte extra."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "ctx", None)
        if isinstance(extra, dict):
            entry["ctx"] = extra
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: str = "INFO", logfile: str | None = "data/gatraking.log") -> None:
    """Configurer la journalisation JSON sur console + fichier."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)
    formatter = JsonFormatter()
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)
    if logfile:
        from pathlib import Path

        Path(logfile).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(logfile, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Logger module avec support de contexte structure : log.info("...", extra={"ctx": {...}})."""
    return logging.getLogger(name)
