"""Application GA-OPERATIONS : API REST + WebSocket + service du frontend.

Chaque route applique le controle d'acces par role ; chaque action sensible
est journalisee dans le registre d'audit (immuable).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ga.core.config import AppConfig
from ga.core.events import EventBus, EventType, GAEvent
from ga.core.logging import get_logger
from ga.core.registry import ServiceRegistry
from ga.data import database as db
from ga.data.cache import CacheClient
from ga.data.media import MediaStore
from ga.data.repositories import (AlertRepo, AuditRepo, CameraRepo, DossierRepo, EventRepo,
                                  SettingRepo, SyncRepo, UserRepo)
from ga.intelligence.assistant import Assistant
from ga.intelligence.registries import (RegistryInactive, RegistryRateLimited,
                                        RegistryUnavailable, RegistryService,
                                        masquer_cin, masquer_plaque)
from ga.intelligence.reports import ReportGenerator
from ga.operations import auth
from ga.vision.manager import CameraManager

log = get_logger("ga.operations.app")


@dataclass
class AppContext:
    """Dependencies runtime injectees dans l'API."""
    cfg: AppConfig
    bus: EventBus
    registry: ServiceRegistry
    manager: CameraManager | None
    media: MediaStore
    cache: CacheClient
    sync_engine: Any | None = None
    processor: Any | None = None
    llm: Any | None = None
    assistant: Assistant | None = None
    report_generator: ReportGenerator | None = None
    started_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


# ---- modeles de requete ------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class CameraUpsert(BaseModel):
    id: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str
    source: str
    enabled: bool = True
    fps_limit: float = 15.0
    location: dict[str, float] = Field(default_factory=lambda: {"x": 0.5, "y": 0.5})
    analysis: dict[str, Any] = Field(default_factory=dict)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(admin|operateur|observateur)$")


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|operateur|observateur)$")
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class DecisionRequest(BaseModel):
    decision: str = Field(pattern="^(valide|rejete)$")
    comment: str | None = None


class ContestRequest(BaseModel):
    reason: str = Field(min_length=3)


class ReportRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=365)


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class AISettingsUpdate(BaseModel):
    conf_threshold: float | None = Field(default=None, ge=0.05, le=0.95)
    iou_threshold: float | None = Field(default=None, ge=0.05, le=0.95)
    speed_limit_kmh: float | None = Field(default=None, gt=0)
    intrusion_min_frames: int | None = Field(default=None, ge=1)


class IdentifyRequest(BaseModel):
    """Plaque optionnelle : sinon la plaque ANPR lue sur le dossier est utilisee."""
    plaque: str | None = Field(default=None, min_length=3, max_length=20)


# ---- fabrique --------------------------------------------------------------
def create_app(ctx: AppContext) -> FastAPI:
    auth.set_secret(ctx.cfg.server.secret_key)
    auth.bootstrap_admin()
    app = FastAPI(title="GAtraking API", version="1.0.0", docs_url="/api/docs",
                  openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"], allow_credentials=False)
    app.state.ctx = ctx
    app.state.ws_clients: set[WebSocket] = set()
    # registres officiels (immatriculation/identite) : desactives sans habilitation
    app.state.registries = RegistryService(
        ctx.cfg.registries,
        audit_fn=lambda action, username, target, details:
            auth.audit(action, None, username, target=target, details=details))

    def broadcast_alert(event: GAEvent) -> None:
        """Diffuser les alertes aux clients WebSocket connectes."""
        clients = list(app.state.ws_clients)
        # le champ "type" du message est l'evenement bus ; le type d'alerte metier
        # reste disponible sous "type_alerte" (le payload ne doit pas l'ecraser)
        data = dict(event.payload)
        data["type"] = "alert.created"
        data["type_alerte"] = event.payload.get("type")
        payload = json.dumps(data, default=str)
        for ws in clients:
            try:
                asyncio.get_running_loop().create_task(_safe_send(ws, payload))
            except RuntimeError:
                pass

    async def _safe_send(ws: WebSocket, payload: str) -> None:
        try:
            await ws.send_text(payload)
        except Exception:
            app.state.ws_clients.discard(ws)

    ctx.bus.subscribe(broadcast_alert, EventType.ALERT_CREATED)

    # ---- authentification ------------------------------------------------
    @app.post("/api/auth/login")
    def login(body: LoginRequest, request: Request):
        ip = request.client.host if request.client else None
        user = auth.authenticate(body.username, body.password, ip)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "identifiants invalides")
        token = auth.create_token(user.username, user.role, ctx.cfg.server.token_expire_minutes)
        return {"token": token, "utilisateur": {"username": user.username, "role": user.role}}

    @app.get("/api/auth/me")
    def me(user: dict = Depends(auth.get_current_user)):
        return user

    # ---- tableau de bord -------------------------------------------------
    @app.get("/api/dashboard/summary")
    def dashboard(user: dict = Depends(auth.get_current_user)):
        with db.session_scope() as session:
            open_alerts = AlertRepo(session).count(status="nouveau", days=7)
            alerts_24h = AlertRepo(session).count(days=1)
            events_24h = EventRepo(session).count(days=1)
            series = EventRepo(session).by_day(days=7)
            dossiers_pending = len(DossierRepo(session).query(status="a_verifier", limit=500))
            recent_alerts = AlertRepo(session).query(days=7, limit=10)
            recent_data = [{"uuid": a.uuid, "ts": a.ts.isoformat(), "type": a.type,
                            "gravite": a.severity, "message": a.message,
                            "camera": a.camera_id, "statut": a.status} for a in recent_alerts]
        cameras_online = 0
        cameras_total = 0
        if ctx.processor is not None:
            cameras_total = len(ctx.cfg.cameras)
        if ctx.manager is not None:
            statuses = ctx.manager.status_all()
            cameras_total = len(statuses) or cameras_total
            cameras_online = sum(1 for s in statuses if s["actif"])
        return {"alertes_ouvertes": open_alerts, "alertes_24h": alerts_24h,
                "evenements_24h": events_24h, "dossiers_a_verifier": dossiers_pending,
                "cameras_total": cameras_total, "cameras_en_ligne": cameras_online,
                "serie_journaliere": series, "alertes_recentes": recent_data}

    # ---- cameras ----------------------------------------------------------
    @app.get("/api/cameras")
    def list_cameras(user: dict = Depends(auth.get_current_user)):
        with db.session_scope() as session:
            cams = [c for c in CameraRepo(session).list()]
            data = [{"id": c.id, "nom": c.name, "source": c.source, "active": c.enabled,
                     "fps_limite": c.fps_limit, "position": {"x": c.location_x, "y": c.location_y},
                     "derniere_vue": c.last_seen.isoformat() if c.last_seen else None} for c in cams]
        runtime = {s["camera_id"]: s for s in (ctx.manager.status_all() if ctx.manager else [])}
        for item in data:
            item["runtime"] = runtime.get(item["id"])
        return data

    @app.post("/api/cameras", status_code=201)
    def add_camera(body: CameraUpsert, request: Request,
                   user: dict = Depends(auth.require_role("operateur"))):
        if ctx.processor is not None and ctx.processor.context_for(body.id) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "identifiant de camera deja utilise")
        with db.session_scope() as session:
            CameraRepo(session).upsert(body.id, body.name, body.source, body.enabled,
                                       body.fps_limit, body.location)
        auth.audit("camera_ajoutee", request, user["username"], target=body.id)
        return {"id": body.id, "note": "redemarrage du service requis pour appliquer le nouveau flux"}

    @app.put("/api/cameras/{camera_id}")
    def update_camera(camera_id: str, body: CameraUpsert, request: Request,
                      user: dict = Depends(auth.require_role("operateur"))):
        if body.id != camera_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "identifiant incoherent")
        with db.session_scope() as session:
            updated = CameraRepo(session).upsert(camera_id, body.name, body.source,
                                                 body.enabled, body.fps_limit, body.location)
            if updated is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "camera inconnue")
        auth.audit("camera_modifiee", request, user["username"], target=camera_id)
        return {"id": camera_id}

    @app.delete("/api/cameras/{camera_id}")
    def delete_camera(camera_id: str, request: Request,
                      user: dict = Depends(auth.require_role("operateur"))):
        with db.session_scope() as session:
            if not CameraRepo(session).delete(camera_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "camera inconnue")
        auth.audit("camera_supprimee", request, user["username"], target=camera_id)
        return {"supprimee": camera_id}

    @app.get("/api/cameras/{camera_id}/snapshot")
    def camera_snapshot(camera_id: str, user: dict = Depends(auth.get_current_user)):
        if ctx.processor is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "pipeline non demarre")
        frame = ctx.processor.last_frame(camera_id)
        if frame is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "aucune image disponible pour cette camera")
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "encodage image impossible")
        return Response(content=buffer.tobytes(), media_type="image/jpeg")

    @app.get("/api/cameras/{camera_id}/stream")
    async def camera_stream(camera_id: str, user: dict = Depends(auth.get_current_user)):
        """Flux MJPEG d'instantanes (~2 images/s, cadence d'echantillonnage GA-SECURITY).

        Pour du temps reel plein debit, brancher directement le flux RTSP de la
        camera sur un visionneur ; ce flux sert au mur video de la console.
        """
        if ctx.processor is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "pipeline non demarre")

        async def mjpeg():
            import asyncio

            while True:
                frame = ctx.processor.stream_frame(camera_id)
                if frame is not None:
                    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                    if ok:
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                               + buffer.tobytes() + b"\r\n")
                await asyncio.sleep(0.5)

        return StreamingResponse(mjpeg(),
                                 media_type="multipart/x-mixed-replace; boundary=frame")

    # ---- alertes ------------------------------------------------------------
    @app.get("/api/alerts")
    def list_alerts(statut: str | None = None, camera: str | None = None,
                    gravite: str | None = None, days: int = Query(7, ge=1, le=365),
                    limit: int = Query(100, ge=1, le=1000), offset: int = 0,
                    user: dict = Depends(auth.get_current_user)):
        with db.session_scope() as session:
            rows = AlertRepo(session).query(status=statut, camera_id=camera,
                                            severity=gravite, days=days, limit=limit, offset=offset)
            return [{"uuid": a.uuid, "ts": a.ts.isoformat(), "type": a.type, "gravite": a.severity,
                     "message": a.message, "camera": a.camera_id, "statut": a.status,
                     "acquittee_par": a.ack_by, "resolue_par": a.resolved_by,
                     "payload": a.payload} for a in rows]

    @app.post("/api/alerts/{alert_uuid}/ack")
    def ack_alert(alert_uuid: str, request: Request,
                  user: dict = Depends(auth.require_role("operateur"))):
        with db.session_scope() as session:
            alert = AlertRepo(session).ack(alert_uuid, user["username"])
            if alert is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "alerte inconnue ou deja traitee")
        auth.audit("alerte_acquittee", request, user["username"], target=alert_uuid)
        ctx.bus.publish_threadsafe(GAEvent(type=EventType.ALERT_ACK, payload={"uuid": alert_uuid}))
        return {"uuid": alert_uuid, "statut": "acquittee"}

    @app.post("/api/alerts/{alert_uuid}/resolve")
    def resolve_alert(alert_uuid: str, request: Request,
                      user: dict = Depends(auth.require_role("operateur"))):
        with db.session_scope() as session:
            alert = AlertRepo(session).resolve(alert_uuid, user["username"])
            if alert is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "alerte inconnue")
        auth.audit("alerte_resolue", request, user["username"], target=alert_uuid)
        ctx.bus.publish_threadsafe(GAEvent(type=EventType.ALERT_RESOLVED, payload={"uuid": alert_uuid}))
        return {"uuid": alert_uuid, "statut": "resolue"}

    # ---- evenements ------------------------------------------------------------
    @app.get("/api/events")
    def list_events(camera: str | None = None, type_: str | None = Query(None, alias="type"),
                    days: int = Query(7, ge=1, le=365), limit: int = Query(200, ge=1, le=2000),
                    offset: int = 0, user: dict = Depends(auth.get_current_user)):
        with db.session_scope() as session:
            rows = EventRepo(session).query(camera_id=camera, type_=type_, days=days,
                                            limit=limit, offset=offset)
            return [{"uuid": e.uuid, "ts": e.ts.isoformat(), "type": e.type,
                     "gravite": e.severity, "camera": e.camera_id, "payload": e.payload} for e in rows]

    @app.get("/api/events/series")
    def event_series(days: int = Query(7, ge=1, le=365),
                     user: dict = Depends(auth.get_current_user)):
        with db.session_scope() as session:
            return EventRepo(session).by_day(days=days)

    # ---- dossiers (validation humaine) --------------------------------------------
    @app.get("/api/dossiers")
    def list_dossiers(statut: str | None = None, limit: int = Query(100, ge=1, le=500),
                      user: dict = Depends(auth.get_current_user)):
        with db.session_scope() as session:
            rows = DossierRepo(session).query(status=statut, limit=limit)
            return [{"uuid": d.uuid, "ts": d.created_at.isoformat(), "type": d.kind,
                     "statut": d.status, "camera": d.camera_id,
                     "plaque": d.evidence.get("plaque"),
                     "identifie": bool(d.evidence.get("identification")),
                     "images": d.evidence.get("images", []),
                     "metriques": d.evidence.get("metriques", {}),
                     "decision_par": d.decision_by,
                     "commentaire": d.decision_comment} for d in rows]

    @app.get("/api/dossiers/{dossier_uuid}")
    def get_dossier(dossier_uuid: str, user: dict = Depends(auth.get_current_user)):
        with db.session_scope() as session:
            d = DossierRepo(session).get(dossier_uuid)
            if d is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "dossier inconnu")
            preuves = dict(d.evidence)
            ident = preuves.get("identification")
            if ident and user["role"] != "admin":
                # minimisation : CIN masque pour les roles non admin, adresse jamais affichee
                ident = dict(ident)
                ident["cin"] = masquer_cin(str(ident.get("cin", "")))
                if "adresse" in ident:
                    ident["adresse"] = "***"
                preuves["identification"] = ident
            return {"uuid": d.uuid, "ts": d.created_at.isoformat(), "type": d.kind,
                    "statut": d.status, "camera": d.camera_id, "preuves": preuves,
                    "decision_par": d.decision_by, "decision_ts": d.decision_ts.isoformat() if d.decision_ts else None,
                    "commentaire": d.decision_comment, "motif_contestation": d.contest_reason}

    @app.post("/api/dossiers/{dossier_uuid}/decide")
    def decide_dossier(dossier_uuid: str, body: DecisionRequest, request: Request,
                       user: dict = Depends(auth.require_role("operateur"))):
        with db.session_scope() as session:
            d = DossierRepo(session).decide(dossier_uuid, body.decision, user["username"], body.comment)
            if d is None:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    "dossier introuvable ou deja decide (aucune re-decision)")
        auth.audit(f"dossier_{body.decision}", request, user["username"], target=dossier_uuid,
                   details={"commentaire": body.comment})
        ctx.bus.publish_threadsafe(GAEvent(type=EventType.DOSSIER_DECISION,
                                           payload={"uuid": dossier_uuid, "decision": body.decision}))
        return {"uuid": dossier_uuid, "statut": body.decision}

    @app.post("/api/dossiers/{dossier_uuid}/contest")
    def contest_dossier(dossier_uuid: str, body: ContestRequest, request: Request,
                        user: dict = Depends(auth.require_role("operateur"))):
        with db.session_scope() as session:
            d = DossierRepo(session).contest(dossier_uuid, body.reason)
            if d is None:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    "seul un dossier valide peut etre conteste")
        auth.audit("dossier_conteste", request, user["username"], target=dossier_uuid,
                   details={"motif": body.reason})
        return {"uuid": dossier_uuid, "statut": "conteste"}

    # ---- registres officiels (immatriculation/identite, habilitation obligatoire)
    @app.post("/api/dossiers/{dossier_uuid}/identifier")
    def identifier_dossier(dossier_uuid: str, request: Request,
                           body: IdentifyRequest | None = None,
                           user: dict = Depends(auth.require_role("operateur"))):
        """Identifier le titulaire du vehicule d'un dossier d'infraction.

        La plaque vient de l'ANPR (preuve du dossier) ou du corps de la requete ;
        la finalite est toujours l'instruction d'un dossier (usage limite et audite).
        """
        with db.session_scope() as session:
            d = DossierRepo(session).get(dossier_uuid)
            if d is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "dossier inconnu")
            plaque = (body.plaque if body and body.plaque else d.evidence.get("plaque"))
            evidence = dict(d.evidence)
        if not plaque:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "aucune plaque lue par l'ANPR sur ce dossier ; fournir 'plaque'")
        try:
            resultat = app.state.registries.identifier_vehicule(
                plaque, user["username"], dossier_uuid=dossier_uuid, role=user["role"])
        except RegistryInactive as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
        except RegistryRateLimited as exc:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
        except RegistryUnavailable as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
        if resultat.get("trouve"):
            evidence["identification"] = resultat
            with db.session_scope() as session:
                DossierRepo(session).update_evidence(dossier_uuid, evidence)
        auth.audit("registre_vehicule", request, user["username"], target=dossier_uuid,
                   details={"plaque": masquer_plaque(plaque), "trouve": resultat.get("trouve")})
        return {"uuid": dossier_uuid, **resultat}

    @app.get("/api/registres/vehicule/{plaque}")
    def registre_vehicule(plaque: str, request: Request, dossier: str = Query(..., min_length=6),
                          user: dict = Depends(auth.require_role("operateur"))):
        """Interrogation directe : finalite obligatoire (?dossier=UUID du dossier en cours)."""
        with db.session_scope() as session:
            if DossierRepo(session).get(dossier) is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    "dossier inconnu : l'interrogation doit servir une instruction")
        try:
            resultat = app.state.registries.identifier_vehicule(
                plaque, user["username"], dossier_uuid=dossier, role=user["role"])
        except RegistryInactive as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
        except RegistryRateLimited as exc:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
        except RegistryUnavailable as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
        auth.audit("registre_vehicule", request, user["username"], target=dossier,
                   details={"plaque": masquer_plaque(plaque), "trouve": resultat.get("trouve")})
        return resultat

    @app.get("/api/registres/etat")
    def registres_etat(user: dict = Depends(auth.require_role("admin"))):
        """Etat de la couche registres : activation, fondement legal, limites."""
        return app.state.registries.etat()

    # ---- utilisateurs ---------------------------------------------------------
    @app.get("/api/users")
    def list_users(user: dict = Depends(auth.require_role("admin"))):
        with db.session_scope() as session:
            return [{"id": u.id, "username": u.username, "role": u.role, "actif": u.active,
                     "derniere_connexion": u.last_login.isoformat() if u.last_login else None}
                    for u in UserRepo(session).list()]

    @app.post("/api/users", status_code=201)
    def create_user(body: UserCreate, request: Request,
                    user: dict = Depends(auth.require_role("admin"))):
        with db.session_scope() as session:
            if UserRepo(session).get_by_username(body.username) is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, "utilisateur deja existant")
            u = UserRepo(session).create(body.username, auth.hash_password(body.password), body.role)
            new_id = u.id
        auth.audit("utilisateur_cree", request, user["username"], target=body.username,
                   details={"role": body.role})
        return {"id": new_id, "username": body.username, "role": body.role}

    @app.put("/api/users/{user_id}")
    def update_user(user_id: int, body: UserUpdate, request: Request,
                    user: dict = Depends(auth.require_role("admin"))):
        with db.session_scope() as session:
            u = UserRepo(session).update(user_id, body.role, body.active,
                                         auth.hash_password(body.password) if body.password else None)
            if u is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "utilisateur inconnu")
            if body.active is False and u.username == user["username"]:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "impossible de desactiver son propre compte")
        auth.audit("utilisateur_modifie", request, user["username"], target=u.username,
                   details={"role": body.role, "actif": body.active})
        return {"id": user_id}

    @app.delete("/api/users/{user_id}")
    def delete_user(user_id: int, request: Request,
                    user: dict = Depends(auth.require_role("admin"))):
        with db.session_scope() as session:
            target = next((u for u in UserRepo(session).list() if u.id == user_id), None)
            if target is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "utilisateur inconnu")
            admins = [u for u in UserRepo(session).list() if u.role == "admin" and u.active]
            if target.role == "admin" and len(admins) <= 1:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "impossible de supprimer le dernier admin")
            UserRepo(session).delete(user_id)
        auth.audit("utilisateur_supprime", request, user["username"], target=target.username)
        return {"supprime": user_id}

    # ---- parametres IA -------------------------------------------------------
    @app.get("/api/settings/ai")
    def get_ai_settings(user: dict = Depends(auth.get_current_user)):
        with db.session_scope() as session:
            override = SettingRepo(session).get("ai_params")
        base = {"detector": ctx.cfg.ai.detector, "model_path": ctx.cfg.ai.model_path,
                "conf_threshold": ctx.cfg.ai.conf_threshold, "iou_threshold": ctx.cfg.ai.iou_threshold,
                "speed_limit_kmh": ctx.cfg.road.speed_limit_kmh,
                "intrusion_min_frames": ctx.cfg.security.intrusion_min_frames}
        base.update(override)
        return base

    @app.put("/api/settings/ai")
    def put_ai_settings(body: AISettingsUpdate, request: Request,
                        user: dict = Depends(auth.require_role("admin"))):
        values = {k: v for k, v in body.model_dump().items() if v is not None}
        if not values:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "aucun parametre fourni")
        with db.session_scope() as session:
            current = SettingRepo(session).get("ai_params")
            current.update(values)
            SettingRepo(session).set("ai_params", current)
        auth.audit("parametres_ia_modifies", request, user["username"], details=values)
        return {"parametres": current,
                "note": "appliques au prochain demarrage du pipeline (configuration persistee)"}

    # ---- systeme ---------------------------------------------------------------
    @app.get("/api/system/resources")
    def system_resources(user: dict = Depends(auth.get_current_user)):
        import psutil
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
        except ImportError:
            providers = []
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage(".")
        return {"cpu_percent": psutil.cpu_percent(interval=0.2),
                "cpu_coeurs": psutil.cpu_count(),
                "ram_percent": vm.percent, "ram_total_go": round(vm.total / 1e9, 1),
                "disque_percent": disk.percent,
                "acceleration": {"providers_onnx": providers,
                                 "detecteur": ctx.manager.detector.name if ctx.manager and ctx.manager.detector else "non demarre"},
                "medias": ctx.media.stats()}

    @app.get("/api/system/cloud")
    def system_cloud(user: dict = Depends(auth.get_current_user)):
        sync = ctx.sync_engine.health() if ctx.sync_engine else {"configure": False}
        return {"cloud_active": ctx.cfg.cloud.enabled,
                "synchronisation": sync,
                "llm": {"provider": ctx.cfg.cloud.llm.provider, "modele": ctx.cfg.cloud.llm.model,
                        "connecte": ctx.llm is not None}}

    @app.get("/api/system/modules")
    def system_modules(user: dict = Depends(auth.get_current_user)):
        return ctx.registry.health_all()

    @app.get("/api/system/logs")
    def system_logs(niveau: str | None = None, limit: int = Query(300, ge=1, le=2000),
                    user: dict = Depends(auth.get_current_user)):
        log_path = Path("data/gatraking.log")
        if not log_path.exists():
            return []
        lines = log_path.read_text(encoding="utf-8").splitlines()[-limit:]
        entries = []
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if niveau and entry.get("level", "").lower() != niveau.lower():
                continue
            entries.append(entry)
        return entries

    # ---- GA-INTELLIGENCE -----------------------------------------------------
    @app.get("/api/intelligence/reports")
    def list_reports(user: dict = Depends(auth.get_current_user)):
        with db.session_scope() as session:
            from ga.data.repositories import ReportRepo
            rows = ReportRepo(session).query(limit=50)
            return [{"uuid": r.uuid, "ts": r.created_at.isoformat(), "periode": [r.period_start.isoformat(), r.period_end.isoformat()],
                     "genere_par": r.generated_by, "chemin": r.path} for r in rows]

    @app.post("/api/intelligence/report")
    def generate_report(body: ReportRequest, user: dict = Depends(auth.require_role("operateur"))):
        if ctx.report_generator is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "module de rapports indisponible")
        return ctx.report_generator.generate(days=body.days)

    @app.post("/api/intelligence/assistant")
    def ask_assistant(body: AssistantRequest, user: dict = Depends(auth.get_current_user)):
        if ctx.assistant is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "assistant indisponible")
        return ctx.assistant.answer(body.message)

    # ---- medias (acces protege) ------------------------------------------------
    @app.get("/api/media/{rel_path:path}")
    def get_media(rel_path: str, user: dict = Depends(auth.get_current_user)):
        try:
            path = ctx.media.resolve(rel_path)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "media introuvable")
        return FileResponse(path, media_type="image/jpeg")

    # ---- WebSocket alertes -------------------------------------------------------
    @app.websocket("/ws/alerts")
    async def ws_alerts(websocket: WebSocket, token: str = Query("")):
        try:
            claims = auth.decode_token(token)
        except HTTPException:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        app.state.ws_clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()  # keepalive / pings du client
        except WebSocketDisconnect:
            app.state.ws_clients.discard(websocket)

    # ---- frontend SPA ------------------------------------------------------------
    # priorite : build React (frontend/dist) sinon console legacy autonome
    frontend_dist = Path("frontend/dist")
    legacy_console = Path("frontend/legacy-console.html")
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        if (frontend_dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            if full_path.startswith("api/") or full_path == "api":
                raise HTTPException(status.HTTP_404_NOT_FOUND, "route API inconnue")
            candidate = frontend_dist / full_path
            if full_path and candidate.is_file() and candidate.resolve().is_relative_to(frontend_dist.resolve()):
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")
    elif legacy_console.exists():

        @app.get("/{full_path:path}", include_in_schema=False)
        async def legacy_fallback(full_path: str):
            if full_path.startswith("api/") or full_path == "api":
                raise HTTPException(status.HTTP_404_NOT_FOUND, "route API inconnue")
            return FileResponse(legacy_console)

    @app.get("/api/health", include_in_schema=False)
    def health():
        return {"service": "gatraking", "sain": ctx.registry.is_healthy()}

    return app
