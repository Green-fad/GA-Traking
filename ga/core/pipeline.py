"""Pipeline d'orchestration GA-CORE : relie vision -> tracking -> road -> security -> data.

S'abonne aux evenements du bus et fait tourner l'analyse metier :
trajectoires, vitesses (si calibre), comptage, zones, incendie, anomalies,
dossiers de preuves et alertes — le tout avec persistance et synchronisation.
"""
from __future__ import annotations

import uuid
from typing import Any

import numpy as np

from ga.core.config import AppConfig, CameraConfig
from ga.core.events import EventBus, EventType, GAEvent, Severity
from ga.core.logging import get_logger
from ga.core.registry import GAModule, HealthStatus
from ga.data import database as db
from ga.data.media import MediaStore
from ga.data.repositories import EventRepo
from ga.road.calibration import RoadCalibration
from ga.road.dossier import DossierBuilder
from ga.road.events import TrafficAnalyzer, TrafficEvent, VEHICLE_NAMES
from ga.road.speed import SpeedTracker
from ga.security.alerts import AlertManager
from ga.security.anomaly import AnomalyDetector
from ga.security.fire import FireDetector
from ga.security.zones import Zone, ZoneMonitor
from ga.track.trajectories import LineCounter, TrajectoryStore

log = get_logger("ga.core.pipeline")

# evenements metier persistes + gravite
EVENT_SEVERITY = {
    "exces_vitesse_candidat": "warning",
    "mauvaise_direction": "warning",
    "vehicule_arrete": "warning",
    "intrusion": "critical",
    "incendie_suspecte": "critical",
    "anomalie": "warning",
    "franchissement_ligne": "info",
}
DOSSIER_KINDS = {"exces_vitesse_candidat", "mauvaise_direction", "vehicule_arrete", "intrusion"}

# detection d'arret par disparition (mode detecteur de fond) : un objet immobile
# absorbe par le modele de fond est toujours present sur la scene
VANISH_GRACE_S = 0.8          # disparition minimale avant d'envisager l'arret
VANISH_MIN_SPAN_S = 2.0       # duree de suivi minimale avant disparition
VANISH_WINDOW_S = 1.0         # fenetre d'immobilite : la derniere seconde avant disparition
VANISH_MAX_DISPLACEMENT_M = 0.6   # deplacement maximal du bord de boite = immobile
VANISH_EDGE_MARGIN_PX = 40    # disparition au bord du champ = sortie de vue
VANISH_CLEANUP_S = 5.0        # purge des pistes disparues sans mesure d'immobilite


class EventProcessor(GAModule):
    """Coeur analytique : transforme les pistes trackees en evenements, alertes et dossiers."""

    name = "ga_pipeline"

    def __init__(self, cfg: AppConfig, bus: EventBus, media: MediaStore,
                 *, cloud_sync: bool = False) -> None:
        self.cfg = cfg
        self.bus = bus
        self.media = media
        self.cloud_sync = cloud_sync
        self.alerts = AlertManager(bus, cloud_sync=cloud_sync)
        self.dossiers = DossierBuilder(media, bus, cloud_sync=cloud_sync)
        self._camera_ctx: dict[str, dict[str, Any]] = {}
        self._last_frames: dict[str, np.ndarray] = {}
        self._dossier_ts: dict[str, float] = {}
        self._emit_ts: dict[str, float] = {}
        self._event_stats = {"traitees": 0, "alertes": 0, "dossiers": 0, "evenements_db": 0}

    # ---- cycle de vie -----------------------------------------------------
    async def start(self, *, start_bus: bool = True) -> None:
        for cam in self.cfg.cameras:
            self._camera_ctx[cam.id] = self._build_context(cam)
        self.bus.subscribe(self._on_tracks, EventType.TRACKS_UPDATED)
        self.bus.subscribe(self._on_frame, EventType.CAMERA_FRAME)
        if start_bus:
            await self.bus.start()
        log.info("pipeline analytique demarre", extra={"ctx": {"cameras": len(self._camera_ctx)}})

    async def stop(self) -> None:
        await self.bus.stop()

    def health(self) -> HealthStatus:
        return HealthStatus(True, "pipeline operationnel", **self._event_stats)

    def _build_context(self, cam: CameraConfig) -> dict[str, Any]:
        analysis = cam.analysis or {}
        calibration = RoadCalibration.from_config(analysis.get("calibration"))
        zones = [Zone(z.get("nom", "zone"), [tuple(p) for p in z.get("points", [])],
                      z.get("type", "interdite"), int(z.get("min_images", self.cfg.security.intrusion_min_frames)))
                 for z in analysis.get("zones", [])]
        quad_bbox = None
        if analysis.get("calibration", {}).get("image_points"):
            pts = analysis["calibration"]["image_points"]
            quad_bbox = (min(p[0] for p in pts), min(p[1] for p in pts),
                         max(p[0] for p in pts), max(p[1] for p in pts))
        return {
            "cfg": cam,
            "trajectoires": TrajectoryStore(),
            "vitesses": SpeedTracker(calibration, self.cfg.road.speed_smoothing_alpha,
                                     self.cfg.road.speed_min_samples) if calibration else None,
            "calibration": calibration,
            "trafic": TrafficAnalyzer(cam.id, self.cfg.road, analysis),
            "zones": ZoneMonitor(zones),
            "quad_bbox": quad_bbox,
            # lignes de comptage : config a plat [x1, y1, x2, y2] -> paires de points
            "compteurs": [LineCounter(((float(l[0]), float(l[1])), (float(l[2]), float(l[3]))))
                          for l in analysis.get("counting_lines", [])],
            "feu": FireDetector(self.cfg.security.fire_min_area_px, self.cfg.security.fire_min_frames),
            "anomalie": AnomalyDetector(zscore_threshold=self.cfg.security.anomaly_zscore),
            "images": 0,
        }

    def context_for(self, camera_id: str) -> dict[str, Any] | None:
        return self._camera_ctx.get(camera_id)

    def last_frame(self, camera_id: str) -> np.ndarray | None:
        """Derniere image vue pour cette camera (instantane pour le mur video)."""
        return self._last_frames.get(camera_id)

    # ---- traitement des pistes ---------------------------------------------
    def _on_tracks(self, event: GAEvent) -> None:
        camera_id = event.camera_id or ""
        ctx = self._camera_ctx.get(camera_id)
        if ctx is None:
            return
        try:
            ts = float(event.payload.get("ts", 0.0))
            tracks: list[dict] = event.payload.get("tracks") or []
        except (TypeError, ValueError):
            return  # payload corrompu : ignore sans interrompre le service
        traj_store: TrajectoryStore = ctx["trajectoires"]

        for track in tracks:
            tid = track["id"]
            cls_name = track["classe"]
            cx, cy = track["centre"]
            bbox = tuple(track.get("bbox") or (cx, cy, cx, cy))
            traj = traj_store.update(tid, cls_name, ts, cx, cy, bbox=bbox)

            # vitesse (si calibration) puis evenements de trafic
            speed_kmh = None
            if ctx["vitesses"] is not None:
                x1, _, x2, y2 = track["bbox"]
                estimate = ctx["vitesses"].update(tid, (x1 + x2) / 2, y2, ts)
                if estimate is not None and estimate.samples >= self.cfg.road.speed_min_samples:
                    speed_kmh = estimate.speed_kmh
            traffic_events = ctx["trafic"].update_track(tid, cls_name, cx, cy, ts, speed_kmh)

            # direction
            angle = traj.direction_angle()
            if angle is not None:
                wrong_way = ctx["trafic"].check_direction(tid, angle, ts)
                if wrong_way:
                    traffic_events.append(wrong_way)

            # zones sensibles (point d'appui = bas de bbox)
            x1, _, x2, y2 = track["bbox"]
            for zone_name in ctx["zones"].update(tid, (x1 + x2) / 2, y2, ts):
                traffic_events.append(TrafficEvent(
                    kind="intrusion", track_id=tid, camera_id=camera_id, ts=ts,
                    details={"zone": zone_name},
                ))

            # franchissement de lignes de comptage
            for counter in ctx["compteurs"]:
                if counter.update(traj):
                    self._persist_business_event(camera_id, "franchissement_ligne", ts,
                                                 {"ligne": counter.line, **counter.stats()})
                    self.bus.publish_threadsafe(GAEvent(
                        type=EventType.COUNT_UPDATE, camera_id=camera_id,
                        payload={"ts": ts, **counter.stats()}))

            for te in traffic_events:
                self._handle_traffic_event(ctx, te, ts, frame=self._last_frames.get(camera_id))

        # densite de trafic : alimentation du detecteur d'anomalies (1 echantillon / 30 images)
        ctx["images"] += 1
        if ctx["images"] % 30 == 0 and tracks:
            anomaly = ctx["anomalie"].update(float(len(tracks)))
            if anomaly:
                self._persist_business_event(camera_id, "anomalie", ts, anomaly)
                alert = self.alerts.raise_alert("anomalie",
                                                "Variation anormale de la densite de trafic",
                                                camera_id, "warning", anomaly)
                if alert:
                    self._event_stats["alertes"] += 1
        self._event_stats["traitees"] += len(tracks)
        self._check_vanished_vehicles(ctx, camera_id, ts)

    def _check_vanished_vehicles(self, ctx: dict, camera_id: str, ts: float) -> None:
        """Arret par disparition : vehicule immobile absorbe par le modele de fond.

        Avec un detecteur de fond (MOG2), un vehicule qui s'arrete finit fusionne
        avec la scene : sa piste disparait alors qu'il est toujours la. L'immobilite
        est jugee sur le deplacement reel de la trajectoire recente (en metres via
        la calibration), robuste au tremblement des boites de detection.
        """
        traj_store: TrajectoryStore = ctx["trajectoires"]
        calibration = ctx.get("calibration")
        quad_bbox = ctx.get("quad_bbox")
        for tid, traj in list(traj_store.trajectories.items()):
            last = traj.last()
            if last is None:
                continue
            silent = ts - last.ts
            if silent < VANISH_GRACE_S:
                continue
            span = last.ts - traj.points[0].ts
            recent = [p for p in traj.points if p.ts >= last.ts - VANISH_WINDOW_S]
            immobile = False
            if calibration is not None and len(recent) >= 3:
                # immobilite jugee sur les bords de boite : l'erosion du modele de fond
                # fait deriver le centre, mais un bord reste stable pour un objet arrete
                edges_right = [p.bbox[2] for p in recent if p.bbox is not None]
                edges_left = [p.bbox[0] for p in recent if p.bbox is not None]
                if len(edges_right) >= 3:
                    try:
                        def _wx(px: float) -> float:
                            return calibration.image_to_world(px, last.y)[0]
                        disp_right = abs(_wx(max(edges_right)) - _wx(min(edges_right)))
                        disp_left = abs(_wx(max(edges_left)) - _wx(min(edges_left)))
                        immobile = traj.cls_name in VEHICLE_NAMES \
                            and min(disp_right, disp_left) < VANISH_MAX_DISPLACEMENT_M
                    except ValueError:
                        immobile = False
            if not immobile or span < VANISH_MIN_SPAN_S:
                if silent > VANISH_CLEANUP_S:
                    traj_store.trajectories.pop(tid, None)
                    if ctx.get("vitesses"):
                        ctx["vitesses"].forget(tid)
                continue
            # bord du champ : seuls les cotes lateraux et le haut correspondent a une
            # sortie de vue ; le bas du cadre reste une zone de detection legitime
            if quad_bbox is not None and not (
                    quad_bbox[0] + VANISH_EDGE_MARGIN_PX <= last.x <= quad_bbox[2] - VANISH_EDGE_MARGIN_PX
                    and last.y >= quad_bbox[1] + VANISH_EDGE_MARGIN_PX):
                traj_store.trajectories.pop(tid, None)
                if ctx.get("vitesses"):
                    ctx["vitesses"].forget(tid)
                continue
            traj_store.trajectories.pop(tid, None)  # evenement emis une seule fois
            if ctx.get("vitesses"):
                ctx["vitesses"].forget(tid)
            self._handle_traffic_event(
                ctx, TrafficEvent(kind="vehicule_arrete", track_id=tid, camera_id=camera_id, ts=ts,
                                  details={"duree_s": round(span, 1), "x": last.x, "y": last.y,
                                           "mode": "absorption_fond"}),
                ts, frame=self._last_frames.get(camera_id))

    def _handle_traffic_event(self, ctx: dict, te: Any, ts: float, frame: np.ndarray | None) -> None:
        severity = EVENT_SEVERITY.get(te.kind, "info")
        self._persist_business_event(te.camera_id, te.kind, te.ts, te.details)

        # dossier de preuve pour les infractions candidates (une fois par piste/type/30 s)
        debounce_key = f"{te.camera_id}:{te.kind}:{te.track_id}"
        if te.kind == "intrusion":
            # les changements d'identite de piste ne doivent pas dupliquer les dossiers :
            # le debounce d'intrusion porte sur la zone
            debounce_key = f"{te.camera_id}:intrusion:{te.details.get('zone', '?')}"
        if te.kind in DOSSIER_KINDS and ts - self._dossier_ts.get(debounce_key, -1e9) > 30.0:
            self._dossier_ts[debounce_key] = ts
            traj = ctx["trajectoires"].trajectories.get(te.track_id)
            self.dossiers.build_dossier(
                kind=te.kind, camera_id=te.camera_id, track_id=te.track_id, ts=te.ts,
                frame=frame, metrics=te.details,
                trajectory=[(p.x, p.y) for p in (traj.points[-30:] if traj else [])],
            )
            self._event_stats["dossiers"] += 1

        # alerte (dedoublonnee) pour les cas a traiter en priorite
        if te.kind in ("intrusion", "incendie_suspecte", "vehicule_arrete"):
            message = {
                "intrusion": f"Intrusion detectee dans une zone interdite ({te.details.get('zone', '?')})",
                "incendie_suspecte": "Debut d'incendie suspecte : flammes visibles dans l'image",
                "vehicule_arrete": f"Vehicule arrete depuis {te.details.get('duree_s', '?')} s",
            }.get(te.kind, te.kind)
            alert = self.alerts.raise_alert(te.kind, message, te.camera_id, severity, te.details)
            if alert:
                self._event_stats["alertes"] += 1

    # ---- traitement des images (incendie) -----------------------------------
    def _on_frame(self, event: GAEvent) -> None:
        camera_id = event.camera_id or ""
        ctx = self._camera_ctx.get(camera_id)
        if ctx is None:
            return
        frame = event.payload.get("frame")
        if not isinstance(frame, np.ndarray):
            return
        self._last_frames[camera_id] = frame
        result = ctx["feu"].analyze(frame)
        if result.get("flamme") and self._should_emit(f"incendie:{camera_id}",
                                                      float(event.payload.get("ts", 0.0)), 30.0):
            self._persist_business_event(camera_id, "incendie_suspecte", float(event.payload.get("ts", 0.0)), result)
            alert = self.alerts.raise_alert("incendie_suspecte",
                                            "Debut d'incendie suspecte : flammes visibles dans l'image",
                                            camera_id, "critical", result)
            if alert:
                self._event_stats["alertes"] += 1

    # ---- persistance ---------------------------------------------------------
    def _should_emit(self, key: str, ts: float, window: float = 30.0) -> bool:
        """Anti-repetition : un meme evenement n'est persiste qu'une fois par fenetre."""
        if ts - self._emit_ts.get(key, -1e9) >= window:
            self._emit_ts[key] = ts
            return True
        return False

    def _persist_business_event(self, camera_id: str, kind: str, ts: float, details: dict) -> None:
        with db.session_scope() as session:
            EventRepo(session).add(uuid=uuid.uuid4().hex, type_=kind, camera_id=camera_id,
                                   severity=EVENT_SEVERITY.get(kind, "info"), payload=details)
        self._event_stats["evenements_db"] += 1

    def stats(self) -> dict:
        return dict(self._event_stats)
