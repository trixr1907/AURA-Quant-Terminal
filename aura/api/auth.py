"""Authentifizierung, Autorisierung und Sicherheits-Middleware (aura.api.auth).

Dokumentiert in docs/SECURITY.md (ADR-0004).
Mandats-Garantien:
  * Constant-Time Token-Vergleich (secrets.compare_digest).
  * Strikte Trennung von Read-only und privilegierten State-Mutationen.
  * Security-Headers: CSP, X-Frame-Options, X-Content-Type-Options.
"""

from __future__ import annotations

import os
import secrets
import time
from typing import Callable

from fastapi import Depends, Header, HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

# Token aus Environment oder sicherer Default
AUTH_TOKEN_ENV_VAR = "AURA_RELAY_TOKEN"
SESSION_COOKIE_NAME = "aura_session"
SESSION_DURATION_SEC = 86400  # 24 Stunden

# In-Memory Session Store: session_id -> expires_at_ts
_ACTIVE_SESSIONS: dict[str, float] = {}

# In-Memory Rate Limiter fuer Login-Fehlversuche: client_ip -> list[timestamp]
_FAILED_LOGINS: dict[str, list[float]] = {}
MAX_FAILED_LOGINS_PER_WINDOW = 5
RATE_LIMIT_WINDOW_SEC = 60.0


def check_login_rate_limit(client_ip: str) -> None:
    """Prueft ob die Rate von Fehlversuchen fuer client_ip ueberschritten wurde."""
    now = time.time()
    attempts = [t for t in _FAILED_LOGINS.get(client_ip, []) if now - t < RATE_LIMIT_WINDOW_SEC]
    _FAILED_LOGINS[client_ip] = attempts
    if len(attempts) >= MAX_FAILED_LOGINS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Zu viele fehlgeschlagene Anmeldeversuche. Bitte warten Sie {int(RATE_LIMIT_WINDOW_SEC)} Sekunden.",
        )


def record_failed_login(client_ip: str) -> None:
    """Registriert einen fehlgeschlagenen Anmeldeversuch."""
    now = time.time()
    attempts = [t for t in _FAILED_LOGINS.get(client_ip, []) if now - t < RATE_LIMIT_WINDOW_SEC]
    attempts.append(now)
    _FAILED_LOGINS[client_ip] = attempts


def clear_failed_logins(client_ip: str) -> None:
    """Loescht Fehlversuche nach erfolgreicher Anmeldung."""
    _FAILED_LOGINS.pop(client_ip, None)


def create_session() -> str:
    """Erzeugt eine kryptografisch sichere Session-ID."""
    session_id = secrets.token_hex(32)
    _ACTIVE_SESSIONS[session_id] = time.time() + SESSION_DURATION_SEC
    return session_id


def is_valid_session(session_id: str | None) -> bool:
    if not session_id or session_id not in _ACTIVE_SESSIONS:
        return False
    if time.time() > _ACTIVE_SESSIONS[session_id]:
        _ACTIVE_SESSIONS.pop(session_id, None)
        return False
    return True


def destroy_session(session_id: str | None) -> None:
    if session_id:
        _ACTIVE_SESSIONS.pop(session_id, None)


def get_configured_token() -> str:
    token = os.environ.get(AUTH_TOKEN_ENV_VAR, "").strip()
    if not token:
        # Falls in DEV kein Token gesetzt ist, nutzen wir einen definierten Entwicklungs-Token
        token = "aura_dev_insecure_token_change_in_prod"
    return token


def verify_auth_token(
    request: Request,
    x_aura_token: str | None = Header(default=None, alias="X-AURA-TOKEN"),
    authorization: str | None = Header(default=None),
) -> str:
    """FastAPI Dependency: Prueft ob ein valider Auth-Token oder eine Session vorliegt."""
    configured = get_configured_token()

    # 1. Pruefe Session Cookie
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token and is_valid_session(cookie_token):
        # CSRF-Schutz fuer mutierende HTTP-Methoden bei Cookie-Authentifizierung
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")
            host = request.headers.get("host")
            if origin:
                origin_host = origin.split("://")[-1].split("/")[0]
                if host and origin_host.lower() != host.lower():
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="CSRF-Pruefung fehlgeschlagen: Origin stimmt nicht mit Host ueberein",
                    )
            elif referer:
                from urllib.parse import urlparse
                ref_host = urlparse(referer).netloc
                if host and ref_host.lower() != host.lower():
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="CSRF-Pruefung fehlgeschlagen: Referer stimmt nicht mit Host ueberein",
                    )
        return "session_operator"

    # 2. Pruefe Header
    token_to_check = None
    if x_aura_token:
        token_to_check = x_aura_token.strip()
    elif authorization and authorization.startswith("Bearer "):
        token_to_check = authorization.split("Bearer ", 1)[1].strip()

    if not token_to_check:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentifizierung erforderlich: Fehlende Session, X-AURA-TOKEN oder Bearer-Header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(token_to_check, configured):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert: Ungueltiger Authentifizierungs-Token",
        )

    return token_to_check


def optional_auth_token(
    request: Request,
    x_aura_token: str | None = Header(default=None, alias="X-AURA-TOKEN"),
    authorization: str | None = Header(default=None),
) -> str | None:
    """FastAPI Dependency: Prueft optional auf Operator-Session/Token. Gibt None bei anonym zurueck."""
    try:
        return verify_auth_token(request, x_aura_token, authorization)
    except HTTPException:
        return None


optional_operator_session = optional_auth_token


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Fuegt allen HTTP-Antworten robuste Security-Header hinzu."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' wss: ws: https://api.bitget.com https://ntfy.sh;"
        )
        return response
