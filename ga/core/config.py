"""Configuration typée de GAtraking (YAML + variables d'environnement).

Priorité : variables d'environnement GA__SECTION__CLE > fichier YAML > défauts.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path("config/gatraking.yaml")


class SiteConfig(BaseModel):
    name: str = "Site principal"
    timezone: str = "Europe/Paris"


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = "change-me"
    token_expire_minutes: int = 480


class CameraConfig(BaseModel):
    id: str
    name: str
    source: str  # URL rtsp://, chemin fichier video, ou index "0" pour webcam
    enabled: bool = True
    fps_limit: float = 15.0
    location: dict[str, float] = Field(default_factory=lambda: {"x": 0.5, "y": 0.5})
    # Analyse metier par camera (GA-ROAD / GA-SECURITY), en pixels image :
    # counting_lines: [[x1,y1,x2,y2], ...], allowed_directions: {cle: angle_deg},
    # zones: [{nom, points, type, min_images}], calibration: {image_points, world_points_m}
    analysis: dict[str, Any] = Field(default_factory=dict)


class AIConfig(BaseModel):
    detector: Literal["auto", "yolo_onnx", "mog2"] = "auto"
    model_path: str = "models/yolov8n.onnx"
    conf_threshold: float = 0.35
    iou_threshold: float = 0.45
    track_high_thresh: float = 0.5
    track_low_thresh: float = 0.1
    track_buffer: int = 30
    # detecteur de secours MOG2
    mog2_history: int = 500
    mog2_var_threshold: int = 28
    mog2_min_area: int = 500


class RoadConfig(BaseModel):
    speed_limit_kmh: float = 80.0
    stopped_speed_kmh: float = 3.0
    stopped_min_seconds: float = 8.0
    min_track_points: int = 6
    speed_smoothing_alpha: float = 0.35
    speed_min_samples: int = 4


class SecurityConfig(BaseModel):
    intrusion_min_frames: int = 6
    fire_min_area_px: int = 220
    fire_min_frames: int = 8
    anomaly_zscore: float = 3.0


class DataConfig(BaseModel):
    database_url: str = "sqlite:///data/gatraking.db"
    redis_url: str = "redis://localhost:6379/0"
    media_dir: str = "data/media"
    retention_days: int = 30


class LLMConfig(BaseModel):
    provider: Literal["none", "cloud", "local"] = "none"
    model: str = ""
    api_url: str = ""
    api_key: str = ""
    timeout_seconds: int = 30


class CloudConfig(BaseModel):
    enabled: bool = False
    api_url: str = ""
    api_token: str = ""
    sync_interval_seconds: int = 30
    batch_size: int = 50
    llm: LLMConfig = Field(default_factory=LLMConfig)


class RegistriesConfig(BaseModel):
    """Acces aux registres officiels (immatriculation -> titulaire, identite).

    DESACTIVE par defaut : l'interrogation des registres nationaux exige une
    habilitation legale de l'exploitant (fondement a consigner dans base_legale).
    Le jeton n'est jamais en clair dans la configuration : nom de variable d'env.
    """
    active: bool = False
    base_legale: str = ""
    fournisseur: Literal["http", "offline", "mock"] = "mock"
    url_immatriculation: str = ""   # endpoint plaque -> titulaire (fourni par l'autorite)
    url_identite: str = ""          # endpoint numero CIN -> identite
    jeton_env: str = "GA_REGISTRES_TOKEN"
    fichier_extract: str = ""       # extract autorise (CSV) en mode offline
    limite_minute: int = 12         # anti-requetes massives, par utilisateur
    masquer_adresse: bool = True


class AppConfig(BaseModel):
    site: SiteConfig = Field(default_factory=SiteConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    road: RoadConfig = Field(default_factory=RoadConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    registries: RegistriesConfig = Field(default_factory=RegistriesConfig)
    cameras: list[CameraConfig] = Field(default_factory=list)

    def ensure_dirs(self) -> None:
        """Creer les repertoires de donnees declares."""
        media = Path(self.data.media_dir)
        media.mkdir(parents=True, exist_ok=True)
        Path("data/reports").mkdir(parents=True, exist_ok=True)
        Path("data/evidence").mkdir(parents=True, exist_ok=True)
        db_url = self.data.database_url
        if db_url.startswith("sqlite:///"):
            db_path = Path(db_url.removeprefix("sqlite:///"))
            if db_path.parent != Path("."):
                db_path.parent.mkdir(parents=True, exist_ok=True)


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Appliquer les surcharges GA__SECTION__CLE (valeurs JSON si possible)."""
    import json

    prefix = "GA__"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key.removeprefix(prefix).lower().split("__")
        node = raw
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            parsed = value
        node[parts[-1]] = parsed
    return raw


def load_config(path: str | Path | None = None) -> AppConfig:
    """Charger la configuration : YAML -> surcharge env -> validation pydantic."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = {}
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    raw = _apply_env_overrides(raw)
    cfg = AppConfig.model_validate(raw)
    cfg.ensure_dirs()
    return cfg


def save_config(cfg: AppConfig, path: str | Path) -> None:
    """Sauvegarder la configuration en YAML (assistant de configuration)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg.model_dump(), fh, allow_unicode=True, sort_keys=False)
