"""CLI GAtraking : `python -m ga serve|demo|migrate|backup|hardware`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ga.core.config import AppConfig, load_config
from ga.core.events import EventBus
from ga.core.logging import get_logger, setup_logging
from ga.core.pipeline import EventProcessor
from ga.core.registry import ServiceRegistry
from ga.core.router import CloudLinkState, LocalCloudRouter, WorkloadKind
from ga.data.cache import CacheClient
from ga.data.database import dispose, init_db
from ga.data.media import MediaStore
from ga.data.sync import SyncEngine
from ga.intelligence.assistant import Assistant
from ga.intelligence.llm import create_llm
from ga.intelligence.reports import ReportGenerator
from ga.operations.app import AppContext, create_app
from ga.vision.manager import CameraManager

log = get_logger("ga.cli")


def build_system(cfg: AppConfig, *, with_cameras: bool = True, loop_files: bool = False):
    """Assembler tous les modules GAtraking (registre + contexte applicatif)."""
    setup_logging()
    bus = EventBus()
    init_db(cfg.data.database_url)
    media = MediaStore(cfg.data.media_dir, cfg.data.retention_days)
    cache = CacheClient(cfg.data.redis_url if Path("/run").exists() else "")
    processor = EventProcessor(cfg, bus, media, cloud_sync=cfg.cloud.enabled)
    manager = CameraManager(cfg.cameras, cfg.ai, bus, loop_files=loop_files) if with_cameras else None
    sync_engine = SyncEngine(cfg.cloud.api_url, cfg.cloud.api_token,
                             cfg.cloud.batch_size, cfg.cloud.sync_interval_seconds,
                             site_name=cfg.site.name) if cfg.cloud.enabled else None
    llm = create_llm(cfg.cloud.llm)
    registry = ServiceRegistry()
    registry.register(bus) if False else None  # bus non-GAModule : gere par le pipeline
    registry.register(processor)
    if manager is not None:
        registry.register(manager)
    if sync_engine is not None:
        registry.register(sync_engine)  # start/stop par defaut via duck typing

    ctx = AppContext(cfg=cfg, bus=bus, registry=registry, manager=manager, media=media,
                     cache=cache, sync_engine=sync_engine, processor=processor,
                     llm=llm, assistant=Assistant(llm), report_generator=ReportGenerator(llm, cfg.site.name))
    return ctx, registry


def cmd_serve(args: argparse.Namespace) -> None:
    """Demarrer la plateforme complete (API + pipeline + cameras)."""
    import uvicorn

    cfg = load_config(args.config)
    ctx, registry = build_system(cfg)
    app = create_app(ctx)

    async def startup() -> None:
        await registry.start_all()

    app.add_event_handler("startup", startup)
    app.add_event_handler("shutdown", registry.stop_all)
    uvicorn.run(app, host=cfg.server.host, port=cfg.server.port, log_level="warning")


def cmd_migrate(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    init_db(cfg.data.database_url)
    print(f"schema initialise : {cfg.data.database_url}")


def cmd_hardware(args: argparse.Namespace) -> None:
    """Detection du materiel : CPU, RAM, GPU, acceleration disponible."""
    import psutil
    print(f"CPU        : {psutil.cpu_count()} coeurs, {psutil.cpu_percent(interval=0.5):.0f}% charge")
    vm = psutil.virtual_memory()
    print(f"RAM        : {vm.total / 1e9:.1f} Go ({vm.percent:.0f}% utilise)")
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        print(f"ONNX Runtime: {ort.__version__}, providers : {providers}")
        if "CUDAExecutionProvider" in providers:
            print("GPU        : CUDA disponible -> acceleration activable (pip install onnxruntime-gpu)")
        else:
            print("GPU        : CUDA non detecte -> traitement CPU (fonctionnel)")
    except ImportError:
        print("ONNX Runtime absent -> detecteur de secours MOG2 (100% CPU, sans modele)")


def cmd_demo(args: argparse.Namespace) -> None:
    from tools.demo_pipeline import run_demo
    run_demo(config_path=args.config, output_dir=args.output, frames=int(args.frames))


def cmd_backup(args: argparse.Namespace) -> None:
    from deploy.backup import run_backup
    run_backup(config_path=args.config, output=args.output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gatraking", description="Plateforme GAtraking")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, cmd in (("serve", cmd_serve), ("migrate", cmd_migrate),
                      ("hardware", cmd_hardware), ("demo", cmd_demo), ("backup", cmd_backup)):
        p = sub.add_parser(name)
        p.add_argument("--config", default="config/gatraking.yaml")
        if name in ("demo", "backup"):
            p.add_argument("--output", default=None)
        if name == "demo":
            p.add_argument("--frames", default=900)
        p.set_defaults(func=cmd)
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except KeyboardInterrupt:
        print("\narret demandé")
        return 0
    finally:
        dispose()


if __name__ == "__main__":
    sys.exit(main())
