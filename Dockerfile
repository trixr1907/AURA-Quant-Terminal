# ==============================================================================
# AURA Quant Terminal v2.5.0 / v3.0.0 — Production Dockerfile
# ==============================================================================
# Pinned Debian-slim Base Image (reproducible build, no alpine musl quirks)
FROM python:3.12.3-slim-bookworm AS base

# Build & Runtime Metadata
LABEL maintainer="AURA Quant Team"
LABEL description="AURA Quant Terminal — Evidenzbasierte Quant-Engine & Paper-Runner"
LABEL version="2.5.0"

# Python Flags fuer Produktion
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    AURA_DB_PATH=/data/aura_state.db \
    AURA_STATE_DIR=/var/lib/aura

WORKDIR /app

# Erstelle unprivilegierten Benutzer (UID 1000) vor Verzeichniserstellung und chown
RUN groupadd -g 1000 aura && \
    useradd -u 1000 -g aura -m -s /bin/bash aura

RUN mkdir -p /var/lib/aura && chown -R aura:aura /var/lib/aura
RUN mkdir -p /data /app && chown -R aura:aura /data /app

# Installiere verifizierten Lockstand der Python-Abhaengigkeiten (D1)
COPY requirements.lock requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.lock

# Kopiere Quellcode und statische Assets
COPY --chown=aura:aura VERSION .
COPY --chown=aura:aura aura/ /app/aura/
COPY --chown=aura:aura data/ /app/data/
COPY --chown=aura:aura scripts/ /app/scripts/
COPY --chown=aura:aura bitget_relay.py headless_autobot.js SYMBIOSE_Tutorial.html shadow_collector.js /app/
COPY --chown=aura:aura Symbiose_Dashboard.html /app/Symbiose_Dashboard.html

# Wechsle zum unprivilegierten Benutzer
USER aura

# Volumes fuer persistente SQLite WAL-Datenbank und State
VOLUME ["/data", "/var/lib/aura"]

# Standardmaessig API-Server starten
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/ready', timeout=4) if False else urllib.request.urlopen('http://127.0.0.1:8000/api/v3/health', timeout=4)" || exit 1

CMD ["uvicorn", "aura.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
