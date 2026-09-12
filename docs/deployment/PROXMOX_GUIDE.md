# 🚀 AURA Quant Terminal - Smart Auto-Installer (Docker & Proxmox VE)

Der neue **Smart Installer** scannt das Zielsystem vollautomatisch und wählt ohne manuellen Aufwand den besten Weg:

```
                  ┌─────────────────────────────────┐
                  │ Zielsystem / Server wird gescannt │
                  └────────────────┬────────────────┘
                                   │
               ┌───────────────────┴───────────────────┐
               ▼                                       ▼
     [ Docker vorhanden? ]                   [ Proxmox VE Node? ]
       ├── JA: Baut & startet Container        ├── JA: Erstellt isolierten Docker-LXC
       └── NEIN: Installiert Docker             │       oder Ultra-Schlank Alpine LXC
           automatisiert & startet             └── NEIN: Installiert Docker Engine
                                                         vollautomatisch
```

---

## ⚡ 1-Click Deployment von Windows (`PROXMOX_DEPLOY.bat`)
1. Führe **`PROXMOX_DEPLOY.bat`** per Doppelklick aus.
2. Gib die IP-Adresse deines Servers ein (z. B. `192.168.178.50`).
3. Das Skript verbindet sich, scannt nach Docker / Proxmox und richtet alles schlüsselfertig ein.

---

## 🐧 1-Befehl Ausführung auf dem Linux-Host / Proxmox Shell
```bash
chmod +x smart_homelab_installer.sh
./smart_homelab_installer.sh
```

---

## 🛡️ Was passiert im Detail?
1. **Wenn Docker bereits installiert ist**:
   - Erkennt die laufende Engine sofort.
   - Baut das gehärtete, schlanke `aura-quant-terminal:latest` Image.
   - Startet den Container mit `restart: unless-stopped` auf Port 8787.
2. **Wenn Proxmox VE erkannt wird**:
   - Lässt den Proxmox-Host sauber und unberührt.
   - Erstellt einen eigenen LXC-Container (Debian mit Nesting & Keyctl).
   - Installiert Docker **innerhalb** dieses isolierten Containers.
   - Startet AURA Terminal darin per Docker.
3. **Wenn ein Standard-Linux-Server (ohne Docker) erkannt wird**:
   - Lädt die offizielle Docker-Engine via `get.docker.com` herunter.
   - Aktiviert den Docker-Dienst und startet das Terminal.
