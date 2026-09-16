# AURA v3 — Betriebshandbuch & Runbook (OPERATIONS_RUNBOOK.md)

**Status:** Kanonisch v3.0 · **Datum:** 2026-09-17 · **Geltung:** Verbindlich fuer Betrieb, Notfaelle, Updates und Wiederherstellung

---

## 1. Start, Stopp & Status

### Erstmaliger Start
```bash
cp .env.example .env
# Setze ein sicheres AURA_RELAY_TOKEN in .env
docker compose build --no-cache
docker compose up -d
```

### Status & Health pruefen
```bash
docker compose ps
curl -s http://127.0.0.1:8000/api/v3/health | jq .
```

### Logs ansehen
```bash
docker compose logs -f --tail=100 aura-worker
docker compose logs -f --tail=100 aura-api
```

---

## 2. Not-Halt Prozedur (Emergency Halt)

Wenn unerwartetes Marktverhalten oder Fehlsignale auftreten:

### Via Web-Oberfläche:
Auf den roten Button `Not-Halt` klicken und bestaetigen.

### Via CLI / API:
```bash
curl -X POST http://127.0.0.1:8000/api/v3/halt \
  -H "X-AURA-TOKEN: <dein_token>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Manuelle Abschaltung durch Operator"}'
```

**Wirkung:**
- Neue Paper-Trades werden sofort blockiert.
- Bestehende Positionen bleiben aktiv und werden weiterhin bis zu ihrem SL/TP oder Timestop ueberwacht.

### Wiederaufnahme:
```bash
curl -X POST http://127.0.0.1:8000/api/v3/resume \
  -H "X-AURA-TOKEN: <dein_token>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Wiederaufnahme nach Pruefung"}'
```

---

## 3. Backup & Wiederherstellung

### Manuelles Backup erstellen
```bash
python3 scripts/backup.py --db /data/aura_state.db --dest /mnt/backups
```

### Wiederherstellung (Restore)
```bash
# 1. Dienste stoppen
docker compose stop aura-worker aura-api

# 2. Restore durchfuehren (inklusive Integritaetspruefung & SHA-256 Check)
python3 scripts/restore.py --backup /mnt/backups/aura_backup_20260917_030000.db --target /data/aura_state.db

# 3. Dienste wieder starten
docker compose start aura-api aura-worker
```

---

## 4. Update- und Rollback-Verfahren (ADR-0005)

### Update durchfuehren:
```bash
git fetch origin
git checkout <neuer_release_tag>
docker compose build
docker compose up -d
```

### Rollback:
```bash
git checkout <vorheriger_release_tag>
docker compose up -d
```
