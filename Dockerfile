# ==============================================================================
# AURA Quant Terminal - Multi-Stage Lightweight Production Dockerfile
# ==============================================================================

FROM python:3.12-alpine

# Set build & runtime metadata
LABEL maintainer="AURA Quant Team"
LABEL description="AURA Quant Terminal - Autonomous Quant Engine & Action Radar"
LABEL version="1.0.1"

# Set non-interactive & python optimization flags
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SYM_HOST=0.0.0.0 \
    SYM_PORT=8787

# Create non-root user for maximum security (Best Practice)
RUN addgroup -S aura && adduser -S aura -G aura

WORKDIR /app

# Copy application files
COPY --chown=aura:aura bitget_relay.py .
COPY --chown=aura:aura Symbiose_Dashboard.html .
COPY --chown=aura:aura SYMBIOSE_Tutorial.html .
COPY --chown=aura:aura data/ ./data/

# Switch to unprivileged user
USER aura

# Expose Web & Relay Port
EXPOSE 8787

# Native lightweight Python Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/serving', timeout=4)" || exit 1

# Start the AURA Quant Relay & Web Server
ENTRYPOINT ["python3", "bitget_relay.py"]
