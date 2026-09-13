# AURA Confluence Terminal — Release v1.5.2

**Datum:** 2026-09-13  
**Typ:** PATCH (Infrastruktur / Prozess / Deploy-Zuverlässigkeit)  
**SemVer-Grund:** wait_for_health()-Timeout-Korrektur im Deploy-Receiver, receiver-originierte ntfy-Benachrichtigungen, bitget_relay.py Kommentar-Fix, build_package/test_package_hygiene Release-Dokument-Referenzen.  
**Urteil:** SOFTWARE_GO / MODEL_NO_EVIDENCE (unverändert)  
**Ledger-Status:** EXP-032 (unverändert)

---

## Änderungen

### 1. Deploy-Receiver: wait_for_health() Race-Condition Fix
- **Problem:** In v1.5.1 schlug das automatische Deployment fehl, weil `wait_for_health()` einen Timeout von 90 s verwendete — exakt gleich lang wie die `StartPeriod=90s` des Dockerfile-Healthchecks. Der Receiver brach den Restart ab, während der Container noch den Zustand `starting` hatte.
- **Fix:** Timeout auf ≥ 300 s angehoben und Versionspolling auf `GET /serving == Ziel-Tag` gemäß Runbook 2026-09-12 ausgerichtet.

### 2. Receiver-originierte ntfy-Benachrichtigungen
- Der Deploy-Receiver sendet nach jedem Deploy-Versuch direkt einen Push-Alert an `AURA_NTFY_URL`:
  - Erfolg: `AURA Deploy ✅ v1.5.2` (Priority: default)
  - Fehlschlag: `AURA Deploy ❌ v1.5.2` (Priority: high)
- Benachrichtigung ist vollständig unabhängig vom lokalen `bitget_relay.py`-Prozess.

### 3. bitget_relay.py Kommentar-Fix (Z.391)
- Beispiel-URL im Kommentar von `http://ntfy.sh/my-aura-alerts` zu `https://ntfy.sh/<TOPIC-NAME>` korrigiert (reine Dokumentation im Code).

### 4. Release-Dokument-Referenzen
- `scripts/build_package.py` und `tests/test_package_hygiene.py` auf `RELEASE_v1.5.2.md` aktualisiert.

---

## Verifikations-Nachweise (Regel 2: ausgeführte Befehle + Ausgabe)

### Pytest-Suite
```
$ python3 -m pytest -q --tb=no
236 passed, 57 subtests passed in 10.12s
```

### Dashboard-Integrität & Version-Marker
```
$ cat VERSION
1.5.2

$ grep -c "1\.5\.2" Symbiose_Dashboard.html
5
```

### Scope & Evidenz-Garantie
- Keine Änderungen an Signal-, Score-, Radar- oder Sizing-Algorithmen.
- Reine Prozess-, Dokumentations- und Infrastruktur-Korrekturen.
- `TRIALS_LEDGER.md` bleibt auf `EXP-032`.
- Urteil: `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
