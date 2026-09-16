# AURA v3 — Proxmox VM & Docker Deployment-Leitfaden (DEPLOYMENT_PROXMOX.md)

**Status:** Kanonisch v3.0 · **Datum:** 2026-09-17 · **Geltung:** Verbindlich fuer das Deployment auf dem Proxmox-Homelab-Server

---

## 1. Proxmox Linux-VM Spezifikation

| Eigenschaft | Empfohlene Konfiguration | Begruendung |
|---|---|---|
| **Betriebssystem** | Debian 12 (Bookworm) oder Ubuntu 24.04 LTS | Minimale Angriffsflaeche, stabil fuer 24/7 Serverbetrieb |
| **vCPUs** | 2 vCPUs | Reicht vollstaendig fuer API, Async-Worker und Bitget-Polling |
| **RAM** | 4 GB | 512MB fuer Container-Budgets, Rest fuer OS und FS-Cache |
| **Disk** | 32 GB (ZFS / LVM thin) | SQLite WAL-Datenbank waechst ca. 50MB/Monat |
| **QEMU Guest Agent** | Aktiviert (`qemu-guest-agent`) | Sauberes Herunterfahren und Proxmox-Monitoring |
| **Proxmox Autostart** | `onboot: 1`, `startup: order=2` | VM startet nach Stromausfall/Host-Reboot automatisch |

---

## 2. Netzwerk- & Zugriffs-Architektur

- **Private IP:** z.B. `192.168.8.115` im lokalen Heimnetz.
- **VPN-Fernzugriff:** WireGuard oder Tailscale direkt auf der Linux-VM oder dem Router.
- **Keine Portweiterleitung im Router:** Die VM wird niemals direkt an das oeffentliche Internet geroutet.
- **Exponierter Port:** Ausschliesslich Port 8000 fuer das Web-Dashboard und die API.

---

## 3. Docker Compose Struktur & Persistenz

Die Anwendung laeuft ueber zwei isolierte Container aus demselben reproduzierbaren Image:

1. `aura-api`: Web-Server & REST/WebSocket-API (Port 8000).
2. `aura-worker`: Autonomer 24/7-Hintergrunddienst fuer Marktdaten, Scanner und Paper-Runner.

Persistenter Speicher: Docker Volume `aura_data` gemountet nach `/data`.

```yaml
# docker-compose.yml Auszug
volumes:
  aura_data:
    name: aura_v3_data
```

---

## 4. Empfohlenes Backup-Ziel (Getrennt vom VM-Datenträger)

Mandats-Garantie: Backups gehoeren **niemals** ausschliesslich auf denselben Datentraeger wie die VM.

### Empfohlene Strategie:
1. **Ziel:** Gemountetes NFS-Share oder SMB-Share des lokalen NAS (z.B. Synology / TrueNAS) unter `/mnt/aura_backups`.
2. **Automatisierter Cronjob auf der VM:**
   ```bash
   # Taegliches Online-Backup um 03:00 UTC
   0 3 * * * cd /opt/aura && python3 scripts/backup.py --db /var/lib/docker/volumes/aura_v3_data/_data/aura_state.db --dest /mnt/aura_backups >> /var/log/aura_backup.log 2>&1
   ```
3. **Ergaenzend:** Proxmox VE Backup Server (PBS) Snapshot der gesamten VM.
