# ==============================================================================
# AURA Quant Terminal v3 — Production Dockerfile
# ==============================================================================
# Pinned Debian-slim Base Image (reproducible build, no alpine musl quirks)
FROM python:3.12.3-slim-bookworm AS base

# Build & Runtime Metadata
LABEL maintainer="AURA Quant Team"
LABEL description="AURA Quant Terminal v3 — Evidenzbasierte Quant-Engine & Paper-Runner"
LABEL version="3.0.0"

# Python Flags fuer Produktion
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    AURA_DB_PATH=/data/aura_state.db

WORKDIR /app

# Erstelle unprivilegierten Benutzer (UID 1000) und Datenverzeichnis
RUN groupadd -g 1000 aura && \
    useradd -u 1000 -g aura -m -s /bin/bash aura && \
    mkdir -p /data && chown -R aura:aura /data /app

# Installiere Python-Abhaengigkeiten
COPY pyproject.toml requirements.txt* /app/
RUN pip install --no-cache-dir fastapi uvicorn pydantic

# Kopiere Quellcode und statische Assets
COPY --chown=aura:aura aura/ /app/aura/
COPY --chown=aura:aura data/ /app/data/
COPY --chown=aura:aura scripts/ /app/scripts/
COPY --chown=aura:aura Symbiose_Dashboard.html /app/Symbiose_Dashboard.html
COPY --chown=aura:aura VERSION /app/VERSION

# Wechsle zum unprivilegierten Benutzer
USER aura

# Volume fuer persistente SQLite WAL-Datenbank
VOLUME ["/data"]

# Standardmaessig API-Server starten
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v3/health', timeout=4)" || exit 1

CMD ["uvicorn", "aura.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
