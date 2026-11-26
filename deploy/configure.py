"""Assistant de configuration initiale GAtraking (guide interactif).

Ecrit config/gatraking.yaml : site, serveur, cameras, cloud. Detection
materielle incluse (selection CPU/GPU).
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ga.core.config import AppConfig, CameraConfig, save_config


def ask(label: str, default: str = "") -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def main() -> None:
    cfg = AppConfig()
    print("=== Assistant de configuration GAtraking ===\n")
    cfg.site.name = ask("Nom du site", cfg.site.name)
    cfg.server.port = int(ask("Port de la console", str(cfg.server.port)))
    cfg.server.secret_key = secrets.token_hex(32)
    print("Cle secrete serveur genere automatiquement.")

    # materiel
    try:
        import onnxruntime as ort
        gpu = "CUDAExecutionProvider" in ort.get_available_providers()
    except ImportError:
        gpu = False
    if gpu:
        print("GPU CUDA detecte : installez onnxruntime-gpu pour l'acceleration.")
    else:
        print("Traitement CPU (fonctionnel). Detecteur : YOLO si modele fourni, sinon MOG2.")
    cfg.ai.model_path = ask("Chemin du modele YOLO ONNX (vide = repli MOG2)", "models/yolov8n.onnx")

    # cameras
    while True:
        if ask("Ajouter une camera ? (o/N)", "n").lower() not in ("o", "oui", "y"):
            break
        cam_id = ask("  Identifiant (ex: cam-01)")
        name = ask("  Nom", cam_id)
        source = ask("  Source (rtsp://... ou chemin fichier)")
        cfg.cameras.append(CameraConfig(id=cam_id, name=name, source=source))

    # cloud
    if ask("Activer la synchronisation cloud ? (o/N)", "n").lower() in ("o", "oui", "y"):
        cfg.cloud.enabled = True
        cfg.cloud.api_url = ask("  URL API cloud", cfg.cloud.api_url)
        cfg.cloud.api_token = ask("  Jeton cloud", "")
        prov = ask("  LLM : none/cloud/local", "none")
        cfg.cloud.llm.provider = prov
        if prov != "none":
            cfg.cloud.llm.api_url = ask("  URL LLM", "")
            cfg.cloud.llm.model = ask("  Modele", "")

    path = Path("config/gatraking.yaml")
    save_config(cfg, path)
    print(f"\nConfiguration ecrite : {path}")
    print("Prochaine etape : python -m ga.cli migrate && python -m ga.cli serve")


if __name__ == "__main__":
    main()
