# ==============================================================================
# AURA Quant Terminal - Multi-Stage Lightweight Production Dockerfile
# ==============================================================================

FROM python:3.12-alpine

# Set build & runtime metadata
LABEL maintainer="AURA Quant Team"
LABEL description="AURA Quant Terminal - Autonomous Quant Engine & Action Radar"
LABEL version="1.3.0"

# Set non-interactive & python optimization flags
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SYM_HOST=0.0.0.0 \
    SYM_PORT=8787 \
    AURA_STATE_DIR=/var/lib/aura

# Create non-root user for maximum security (Best Practice)
RUN addgroup -S aura && adduser -S aura -G aura

# Prepare the persistent state mount before switching to the non-root user.
RUN mkdir -p /var/lib/aura && chown -R aura:aura /var/lib/aura

WORKDIR /app

# Copy application files
COPY --chown=aura:aura bitget_relay.py .
COPY --chown=aura:aura VERSION .
COPY --chown=aura:aura Symbiose_Dashboard.html .
COPY --chown=aura:aura SYMBIOSE_Tutorial.html .
COPY --chown=aura:aura data/ ./data/

# Switch to unprivileged user
USER aura

# Expose Web & Relay Port
EXPOSE 8787

# Native lightweight Python Healthcheck
# /ready requires a recent successful public-market uplink; the start period
# permits the first dashboard/public probe without a premature unhealthy state.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/ready', timeout=4)" || exit 1

# Start the AURA Quant Relay & Web Server
ENTRYPOINT ["python3", "bitget_relay.py"]
