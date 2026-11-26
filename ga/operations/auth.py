"""Authentification et controle d'acces : PBKDF2, JWT HS256, RBAC, limiteur de tentatives."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from ga.core.logging import get_logger
from ga.data import database as db
from ga.data.models import User
from ga.data.repositories import AuditRepo, UserRepo

log = get_logger("ga.operations.auth")

PBKDF2_ITERATIONS = 200_000
bearer_scheme = HTTPBearer(auto_error=False)


# ---- hachage de mot de passe -------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


# ---- JWT -----------------------------------------------------------------------
_secret_holder: str = "change-me"


def set_secret(secret: str) -> None:
    """Injecter la cle secrete (fait par la fabrique d'application au demarrage)."""
    global _secret_holder
    _secret_holder = secret


def create_token(username: str, role: str, expire_minutes: int) -> str:
    payload = {"sub": username, "role": role,
               "iat": int(time.time()), "exp": int(time.time() + expire_minutes * 60)}
    return jwt.encode(payload, _secret_holder, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _secret_holder, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "jeton expire") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "jeton invalide") from exc


# ---- limiteur de tentatives (anti force brute) -----------------------------------
class LoginLimiter:
    """5 echecs par (utilisateur, ip) -> verrouillage 60 s."""

    MAX_FAILURES = 5
    LOCK_SECONDS = 60

    def __init__(self) -> None:
        self._failures: dict[tuple[str, str], list[float]] = {}

    def check_locked(self, username: str, ip: str) -> bool:
        key = (username, ip)
        window = [t for t in self._failures.get(key, []) if time.time() - t < self.LOCK_SECONDS]
        self._failures[key] = window
        return len(window) >= self.MAX_FAILURES

    def record_failure(self, username: str, ip: str) -> None:
        self._failures.setdefault((username, ip), []).append(time.time())

    def reset(self, username: str, ip: str) -> None:
        self._failures.pop((username, ip), None)


# ---- dependances FastAPI -----------------------------------------------------------
def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> dict:
    """Dependance : extrait et valide le jeton ; retourne {username, role}."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentification requise")
    claims = decode_token(credentials.credentials)
    return {"username": claims["sub"], "role": claims.get("role", "observateur")}


ROLE_RANK = {"observateur": 1, "operateur": 2, "admin": 3}


def require_role(minimum: str):
    """Fabrique de dependance RBAC : role minimal requis."""
    if minimum not in ROLE_RANK:
        raise ValueError(f"role inconnu : {minimum}")

    def checker(user: dict = Depends(get_current_user)) -> dict:
        if ROLE_RANK.get(user["role"], 0) < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "droits insuffisants")
        return user

    return checker


def audit(action: str, request: Request | None, username: str | None, target: str | None = None,
          details: dict | None = None) -> None:
    """Journaliser une operation sensible (immuable)."""
    ip = request.client.host if request and request.client else None
    with db.session_scope() as session:
        AuditRepo(session).add(action=action, username=username, target=target,
                               details=details or {}, ip=ip)


def authenticate(username: str, password: str, ip: str | None) -> Optional[User]:
    """Verifier les identifiants (limiteur inclus) ; journalise chaque tentative."""
    limiter: LoginLimiter = _get_limiter()
    if limiter.check_locked(username, ip or ""):
        audit("login_verrouille", None, username, details={"ip": ip})
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "trop de tentatives, reessayez dans 1 minute")
    with db.session_scope() as session:
        user = UserRepo(session).get_by_username(username)
        if user is None or not user.active or not verify_password(password, user.password_hash):
            limiter.record_failure(username, ip or "")
            audit("login_echec", None, username, details={"ip": ip})
            return None
        UserRepo(session).touch_login(username)
    limiter.reset(username, ip or "")
    audit("login_succes", None, username, details={"ip": ip})
    return user


_limiter_instance: LoginLimiter | None = None


def _get_limiter() -> LoginLimiter:
    global _limiter_instance
    if _limiter_instance is None:
        _limiter_instance = LoginLimiter()
    return _limiter_instance


def bootstrap_admin() -> None:
    """Creer l'administrateur initial si la table est vide (mot de passe temporaire)."""
    with db.session_scope() as session:
        if UserRepo(session).count() == 0:
            UserRepo(session).create("admin", hash_password("GAt Admin#2026"), role="admin")
            log.warning("administrateur initial cree (changer le mot de passe immediatement)")
