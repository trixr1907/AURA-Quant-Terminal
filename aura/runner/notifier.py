"""Server-seitiger Notification Dispatcher (aura.runner.notifier).

Unterstuetzt ntfy mit Deduplizierung, Cooldowns und Status-Logging.
Mandats-Garantie: Keine API-Tokens oder Secrets im Klartext in Logs/Payloads.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request

logger = logging.getLogger("aura.runner.notifier")


@dataclass
class NotificationConfig:
    enabled: bool = True
    topic_url: str = "https://ntfy.sh/aura_quant_alerts_test"
    auth_token: str | None = None  # Optional Bearer Token
    cooldown_seconds: int = 300    # 5 Minuten Cooldown fuer identische Signale
    max_retries: int = 2


class NotificationDispatcher:
    """Server-authoritativer Benachrichtigungsdienst mit Deduplizierung."""

    def __init__(
        self,
        config: NotificationConfig | None = None,
        conn: sqlite3.Connection | None = None,
    ):
        self.config = config or NotificationConfig()
        self.conn = conn
        self._sent_hashes: dict[str, float] = {}

    def send_alert(
        self,
        title: str,
        message: str,
        priority: int = 3,  # 1=min, 3=default, 4=high, 5=urgent
        tags: list[str] | None = None,
        event_type: str = "SIGNAL",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Sendet einen Alert via ntfy mit Deduplizierung und Audit-Logging."""
        if not self.config.enabled or not self.config.topic_url:
            return False

        # Deduplizierungs-Hash ueber Titel und Inhalt
        dedup_str = f"{title}:{message}"
        h = hashlib.sha256(dedup_str.encode("utf-8")).hexdigest()
        now = time.time()

        last_sent = self._sent_hashes.get(h, 0.0)
        if (now - last_sent) < self.config.cooldown_seconds:
            logger.debug("Benachrichtigung unterdrueckt (Cooldown aktiv): %s", title)
            return False

        headers = {
            "Title": title.encode("utf-8"),
            "Priority": str(priority),
        }
        if tags:
            headers["Tags"] = ",".join(tags)
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"

        success = False
        error_msg = ""
        try:
            req = request.Request(
                self.config.topic_url,
                data=message.encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with request.urlopen(req, timeout=10.0) as resp:
                if 200 <= resp.status < 300:
                    success = True
                    self._sent_hashes[h] = now
                    logger.info("Alert erfolgreich versendet: %s (Priority %d)", title, priority)
                else:
                    error_msg = f"HTTP {resp.status}"
        except Exception as ex:
            error_msg = str(ex)
            logger.warning("Fehler beim Versenden des Alerts '%s': %s", title, error_msg)

        # Audit-Logging in SQLite
        if self.conn:
            self._log_event(
                event_type=f"NOTIF_{event_type}",
                severity="INFO" if success else "WARN",
                payload={
                    "title": title,
                    "priority": priority,
                    "success": success,
                    "error": error_msg,
                    "metadata": metadata or {},
                },
            )

        return success

    def _log_event(self, event_type: str, severity: str, payload: dict[str, Any]) -> None:
        if not self.conn:
            return
        now_ms = int(time.time() * 1000)
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO system_events (event_time, event_type, severity, component, payload) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        now_ms,
                        event_type,
                        severity,
                        "notifier",
                        json.dumps(payload),
                    ),
                )
        except Exception as ex:
            logger.error("Konnte Notification-Event nicht loggen: %s", ex)
