"""Generateur de video synthetique GAtraking : scene routiste deterministe avec
vehicules (vitesses connues), pieton en zone interdite et debut d'incendie.

Utilise par la demonstration fonctionnelle, les tests d'integration et la
qualification du pipeline — toutes les vitesses reelles sont calculees avec la
meme calibration que celle fournie a la camera, ce qui permet de verifier la
mesure de vitesse contre la verite terrain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


@dataclass
class Actor:
    nom: str
    x: float
    y: float
    vx: float                 # px/frame
    vy: float                 # px/frame
    w: int
    h: int
    couleur: tuple[int, int, int]
    entree: int = 0           # frame d'apparition
    arret_a: Optional[int] = None  # frame de mise a l'arret (vx,vy -> 0)
    stop_depuis: Optional[int] = None

    def position(self, frame: int) -> tuple[float, float] | None:
        if frame < self.entree:
            return None
        f = frame - self.entree
        if self.arret_a is not None and f >= self.arret_a - self.entree:
            f = self.arret_a - self.entree
        return self.x + self.vx * f, self.y + self.vy * f


@dataclass
class SceneConfig:
    largeur: int = 1280
    hauteur: int = 720
    fps: int = 30
    # bande routiere calibree : (100..1140, 500..700) px  <->  (0..50, 0..10) m
    route_y_haut: int = 500
    route_y_bas: int = 700
    m_par_px_x: float = 50.0 / 1000.0
    m_par_px_y: float = 10.0 / 200.0
    incendie_a: int = 450     # frame de debut d'incendie (0 = aucun)
    incendie_pos: tuple[int, int] = (1120, 160)
    actors: list[Actor] = field(default_factory=list)


def scene_demo(cfg: SceneConfig | None = None) -> SceneConfig:
    """Scenario de demonstration : 3 vehicules + 1 pieton (+ incendie optionnel).

    voiture_arret : roule puis s'arrete net (couleur tranchante pour rester
    visible par la soustraction de fond meme immobile).
    """
    cfg = cfg or SceneConfig()
    cfg.actors = [
        Actor("camionnette", x=-120, y=600, vx=3.5, vy=0, w=100, h=50, couleur=(60, 120, 220)),
        Actor("voiture_rapide", x=-140, y=560, vx=18.5, vy=0, w=90, h=45, couleur=(40, 40, 210), entree=90),
        Actor("voiture_arret", x=-120, y=645, vx=4.0, vy=0, w=85, h=40, couleur=(40, 40, 220),
              entree=60, arret_a=150),
        Actor("pieton", x=200, y=330, vx=0, vy=1.8, w=26, h=52, couleur=(240, 240, 240)),
    ]
    return cfg


def _fond(cfg: SceneConfig) -> np.ndarray:
    frame = np.full((cfg.hauteur, cfg.largeur, 3), (60, 55, 50), dtype=np.uint8)
    # ciel / fond superieur
    frame[:cfg.route_y_haut, :] = (48, 42, 36)
    # bande routiere
    frame[cfg.route_y_haut:cfg.route_y_bas, :] = (70, 68, 66)
    # bandes lane discontinues (statiques)
    for y in (cfg.route_y_haut + 50, cfg.route_y_haut + 100):
        for x in range(0, cfg.largeur, 80):
            frame[y:y + 4, x:x + 40] = (200, 200, 200)
    return frame


def _dessiner_incendie(frame: np.ndarray, cfg: SceneConfig, frame_id: int) -> None:
    if cfg.incendie_a <= 0 or frame_id < cfg.incendie_a:
        return
    cx, cy = cfg.incendie_pos
    rng = np.random.default_rng(frame_id)
    r = 16 + int(rng.integers(0, 9))
    cv2.circle(frame, (cx, cy), r, (0, 140, 255), -1)     # orange (BGR)
    cv2.circle(frame, (cx, cy), max(6, r // 2), (0, 220, 255), -1)  # jaune coeur
    if r > 20:
        cv2.circle(frame, (cx + 18, cy - 8), 6, (0, 140, 255), -1)


def render_frame(cfg: SceneConfig, frame_id: int) -> np.ndarray:
    frame = _fond(cfg).copy()
    # zone interdite (contour rouge, statique)
    cv2.rectangle(frame, (100, cfg.route_y_haut - 50), (400, cfg.route_y_bas), (40, 40, 220), 2)
    for actor in cfg.actors:
        pos = actor.position(frame_id)
        if pos is None:
            continue
        x, y = int(pos[0]), int(pos[1])
        if x > cfg.largeur + actor.w or x < -actor.w * 2:
            continue
        cv2.rectangle(frame, (x, y), (x + actor.w, y + actor.h), actor.couleur, -1)
    _dessiner_incendie(frame, cfg, frame_id)
    return frame


def vitesse_reelle_kmh(actor: Actor, cfg: SceneConfig, fps: float | None = None) -> float:
    """Vitesse reelle de l'acteur en km/h (via la meme calibration que la camera)."""
    import math

    fps = fps or cfg.fps
    dx = actor.vx * cfg.m_par_px_x * fps
    dy = actor.vy * cfg.m_par_px_y * fps
    return math.sqrt(dx * dx + dy * dy) * 3.6


def ecrire_video(cfg: SceneConfig, frames: int, path: str | Path) -> Path:
    """Produire le fichier video mp4 du scenario."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), cfg.fps,
                             (cfg.largeur, cfg.hauteur))
    for f in range(frames):
        writer.write(render_frame(cfg, f))
    writer.release()
    return path


def calibration_points(cfg: SceneConfig) -> dict:
    """Configuration d'analyse camera (calibration + zone + ligne de comptage)."""
    return {
        "calibration": {
            "image_points": [[100, cfg.route_y_bas], [1140, cfg.route_y_bas],
                             [1140, cfg.route_y_haut], [100, cfg.route_y_haut]],
            "world_points_m": [[0, 0], [50, 0], [50, 10], [0, 10]],
        },
        "counting_lines": [[600, cfg.route_y_haut - 120, 600, cfg.route_y_bas]],
        "zones": [{
            "nom": "zone_interdite",
            "points": [[100, cfg.route_y_haut - 50], [400, cfg.route_y_haut - 50],
                       [400, cfg.route_y_bas], [100, cfg.route_y_bas]],
            "type": "interdite",
            "min_images": 6,
        }],
    }


if __name__ == "__main__":
    scene = scene_demo()
    out = ecrire_video(scene, 900, "demo_output/scene_demo.mp4")
    print(f"video generee : {out}")
    for actor in scene.actors:
        print(f"  {actor.nom} : {vitesse_reelle_kmh(actor, scene):.1f} km/h")
