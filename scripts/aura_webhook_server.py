#!/usr/bin/env python3
"""
aura_webhook_server.py — Webhook Receiver for GitHub Releases
============================================================
Listens for GitHub Webhook POST requests (e.g. event: release -> action: published)
and triggers container rebuild and deployment immediately.
Supports HMAC-SHA256 signature verification with WEBHOOK_SECRET.
"""

import hmac
import hashlib
import json
import logging
import os
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from aura_auto_updater import update_and_redeploy, fetch_latest_release

PORT = int(os.environ.get("WEBHOOK_PORT", "9000"))
SECRET = os.environ.get("WEBHOOK_SECRET", "").encode("utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AURA-Webhook] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("AURAWebhook")


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(content_length)

        # 1. Verify Signature if SECRET is set
        if SECRET:
            sig = self.headers.get("X-Hub-Signature-256", "")
            if not sig.startswith("sha256="):
                log.warning("Webhook abgelehnt: Fehlende oder ungültige Signatur.")
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"Unauthorized: Missing or invalid signature\n")
                return

            expected_sig = "sha256=" + hmac.new(SECRET, payload, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                log.warning("Webhook abgelehnt: Signatur stimmt nicht überein.")
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden: Signature mismatch\n")
                return

        # 2. Check GitHub Event
        event = self.headers.get("X-GitHub-Event", "")
        log.info(f"Webhook empfangen! GitHub-Event: {event}")

        try:
            data = json.loads(payload.decode("utf-8"))
        except Exception:
            data = {}

        # Handle 'release' or 'push' event
        if event == "release":
            action = data.get("action")
            release = data.get("release", {})
            tag = release.get("tag_name", "").lstrip("v")
            log.info(f"Release Event: Action={action}, Tag=v{tag}")
            
            if action in ("published", "created", "released"):
                assets = release.get("assets", [])
                zip_url = None
                for asset in assets:
                    if asset.get("name") == "symbiose.zip":
                        zip_url = asset.get("browser_download_url")
                        break
                if not zip_url:
                    zip_url = release.get("zipball_url")

                if tag and zip_url:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Update triggered\n")
                    update_and_redeploy(tag, zip_url)
                    return

        elif event == "ping":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"PONG\n")
            return

        # Fallback: check latest release
        rel = fetch_latest_release()
        if rel:
            tag, zip_url = rel
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Update triggered via fallback\n")
            update_and_redeploy(tag, zip_url)
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Event ignored\n")


def main():
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    log.info(f"AURA Webhook Server lauscht auf Port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
