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
from typing import Callable

from fastapi import Depends, Header, HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

# Token aus Environment oder sicherer Default
AUTH_TOKEN_ENV_VAR = "AURA_RELAY_TOKEN"


def get_configured_token() -> str:
    token = os.environ.get(AUTH_TOKEN_ENV_VAR, "").strip()
    if not token:
        # Falls in DEV kein Token gesetzt ist, nutzen wir einen definierten Entwicklungs-Token
        token = "aura_dev_insecure_token_change_in_prod"
    return token


def verify_auth_token(
    x_aura_token: str | None = Header(default=None, alias="X-AURA-TOKEN"),
    authorization: str | None = Header(default=None),
) -> str:
    """FastAPI Dependency: Prueft ob ein valider Auth-Token uebergeben wurde."""
    configured = get_configured_token()
    token_to_check = None

    if x_aura_token:
        token_to_check = x_aura_token.strip()
    elif authorization and authorization.startswith("Bearer "):
        token_to_check = authorization.split("Bearer ", 1)[1].strip()

    if not token_to_check:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentifizierung erforderlich: Fehlender X-AURA-TOKEN oder Bearer-Header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(token_to_check, configured):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert: Ungueltiger Authentifizierungs-Token",
        )

    return token_to_check


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
