"""Acquisition video : RTSP, fichiers, webcams — avec reprise sur erreur (reconnexion).

Pensé pour la resilience : une camera qui tombe ne bloque jamais les autres.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from ga.core.logging import get_logger

log = get_logger("ga.vision.capture")


class VideoSource:
    """Source video unifiee avec reconnexion automatique et limiteur de debit."""

    def __init__(self, source: str, fps_limit: float = 15.0,
                 max_reconnect_attempts: int = 5, reconnect_delay_s: float = 2.0,
                 loop_file: bool = False) -> None:
        self.source = source
        self.fps_limit = fps_limit
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay_s = reconnect_delay_s
        self.loop_file = loop_file
        self._cap: Optional[cv2.VideoCapture] = None
        # fps_limit <= 0 : pas de limiteur (lecture aussi vite que possible)
        self._min_frame_interval = (1.0 / fps_limit) if fps_limit and fps_limit > 0 else 0.0
        self._last_read = 0.0
        self.frames_total = 0
        self.reconnects = 0
        self.last_error: str | None = None
        self.is_file = Path(source).suffix.lower() != "" and not source.lower().startswith(("rtsp://", "http"))

    def _open(self) -> bool:
        if self.source.lower().startswith("rtsp://"):
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG, [cv2.CAP_PROP_BUFFERSIZE, 2])
            if not cap.isOpened():
                # variante UDP si TCP echoue
                cap.release()
                cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        elif self.source.isdigit():
            cap = cv2.VideoCapture(int(self.source))
        else:
            if not Path(self.source).exists():
                self.last_error = f"fichier introuvable : {self.source}"
                return False
            cap = cv2.VideoCapture(self.source)
        self._cap = cap
        if not cap.isOpened():
            self.last_error = f"ouverture impossible : {self.source}"
            return False
        return True

    def read(self) -> Optional[np.ndarray]:
        """Lire une image en respectant la limite de debit ; reconnexion sur panne reseau."""
        now = time.monotonic()
        wait = self._min_frame_interval - (now - self._last_read)
        if wait > 0:
            time.sleep(wait)
        self._last_read = time.monotonic()

        for attempt in range(self.max_reconnect_attempts + 1):
            if self._cap is None or not self._cap.isOpened():
                if not self._open():
                    self.reconnects += 1
                    if self.is_file or attempt >= self.max_reconnect_attempts:
                        return None  # fichier absent : aucune nouvelle tentative utile
                    time.sleep(self.reconnect_delay_s)
                    continue
            ok, frame = self._cap.read()
            if ok:
                self.frames_total += 1
                self.last_error = None
                return frame
            # echec de lecture : fin de fichier ou flux interrompu
            self.last_error = "lecture interrompue (fin de fichier ou coupure flux)"
            self._release()
            if self.is_file:
                if self.loop_file and self._open():
                    ok, frame = self._cap.read()
                    if ok:
                        self.frames_total += 1
                        return frame
                return None  # fichier termine : pas de reconnexion utile
            self.reconnects += 1
            if attempt >= self.max_reconnect_attempts:
                return None
            time.sleep(self.reconnect_delay_s)
        return None

    def _release(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def release(self) -> None:
        self._release()

    def status(self) -> dict:
        return {
            "source": self.source,
            "images_lues": self.frames_total,
            "reconnexions": self.reconnects,
            "derniere_erreur": self.last_error,
        }
