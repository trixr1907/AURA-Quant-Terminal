# AURA Deploy-Benachrichtigungen via ntfy

Dieser Leitfaden erklärt in wenigen Schritten, wie du auf Handy und PC sofort benachrichtigt wirst, sobald ein neues AURA-Release deployt wurde — erfolgreich oder mit Fehler.

---

## Was ist ntfy?

ntfy (sprich: „notify") ist ein einfacher Push-Benachrichtigungsdienst. Das Prinzip: Du wählst einen **Topic-Namen** — eine Art Briefkasten-Adresse. Wer diese Adresse kennt, kann Nachrichten senden und empfangen. Deshalb gilt: **Der Topic-Name ist wie ein Passwort — nie teilen, nie in Code oder Commits schreiben.**

Der AURA Deploy-Receiver schickt nach jedem Deploy-Versuch automatisch eine Nachricht an deinen Topic.

---

## Handy einrichten

1. Installiere die kostenlose App **ntfy**:
   - Android: [Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy) oder [F-Droid](https://f-droid.org/packages/io.heckel.ntfy/)
   - iOS: [App Store](https://apps.apple.com/app/ntfy/id1625396347)

2. Öffne die App → tippe auf **+** (oben rechts).

3. Trage deinen Topic-Namen ein (den du vom System-Eigentümer direkt mitgeteilt bekommst — er steht nie im Repo).

4. Tippe auf **Subscribe** — fertig.

**Erwartetes Ergebnis nach dem nächsten Deploy:**
- Erfolg: Titel `AURA Deploy ✅ v1.x.y`, Body: _Container serving 1.x.y — deployt auf <vm-name>._
- Fehlschlag: Titel `AURA Deploy ❌ v1.x.y` (Priority: high = lauter Ton), Body mit konkretem Fehlergrund.

---

## PC einrichten

1. Öffne `https://ntfy.sh` im Browser.
2. Klicke auf **Subscribe to topic** und trag den Topic-Namen ein.
3. **Desktop-Benachrichtigungen aktivieren:** Klicke auf das Glockensymbol oben — Browser fragt nach Berechtigung, einmal bestätigen.
4. Optional: In Chrome/Edge → Adressleiste → **App installieren** → eigenes Fenster ohne Browser-Tabs.

---

## Selbst testen

Du kannst jederzeit eine Testnachricht schicken, um sicherzustellen dass alles funktioniert:

**Per curl** (ersetze `<TOPIC-NAME>` durch deinen echten Topic-Namen, der dir direkt mitgeteilt wurde):

```bash
curl -d "AURA Deploy-Test erfolgreich" \
     -H "X-Title: Test-Benachrichtigung" \
     https://ntfy.sh/<TOPIC-NAME>
```

**Erwartetes Ergebnis:** Die Nachricht erscheint innerhalb von Sekunden in der App und im Browser-Tab.

Oder direkt über die ntfy Web-UI: Öffne `https://ntfy.sh/<TOPIC-NAME>` → **Publish** → Testnachricht eingeben → Send.

---

## Zusammenspiel der Benachrichtigungsquellen

Beide Quellen schicken Nachrichten in denselben Topic — eine App, alles im Blick:

| Quelle | Ereignis | Priorität |
|--------|----------|-----------|
| Deploy-Receiver (beide VMs) | Release deployt ✅ | default |
| Deploy-Receiver (beide VMs) | Deploy fehlgeschlagen ❌ | high (lauter Ton) |
| `bitget_relay.py` (PF-33, via `AURA_NTFY_URL`) | Trade geschlossen | default |

---

## Trade- & Signal-Pushes (24/7 ohne offenen Browser)

Ab **AURA v1.7.0** sendet der **Headless Paper-Autobot** im Docker-Container alle Trade-Events und Regime-Wechsel **rund um die Uhr**, völlig unabhängig davon, ob auf PC oder Handy ein Browser geöffnet ist.

### Signal-Matrix

| Ereignis | Auslöser | Priorität | Bemerkung |
|---|---|---|---|
| **Trade eröffnet** | Headless-Runner findet OOS-valides Setup | P3 (default) | Sofort nach Order-Freigabe |
| **TP1 / TP2 / TP3** | Kurs erreicht Take-Profit-Levels | P3 (default) | Once-Flag verhindert Re-Pushes |
| **Stop-Loss / Time-Stop** | SL oder Stagnations-Stop getriggert | P4 (hoch) / P3 | Sofortiger Exit-Push |
| **BTC-Regime-Wechsel** | Makro-Trend wechselt (z. B. BULL → BEAR) | P4 (hoch) | Relay BTC-Wächter |
| **Tages-Digest** | Täglicher PnL- & Trade-Report (07:00 UTC) | P1 (niedrig) | 24h Performance-Zusammenfassung |
| **Runner-Fehler** | Server-Bot ausgefallen (>5 Min kein Zyklus) | P4 (hoch) | 60 Min Cooldown |

### 1. Umgebungsvariable setzen
Dem Container `aura-terminal` auf der VM (z. B. VM 201) die Umgebungsvariable mitgeben:

```bash
AURA_NTFY_URL=https://ntfy.sh/<TOPIC-NAME>
```

*(Hierbei denselben `<TOPIC-NAME>` wie für Deploy-Alerts verwenden — niemals den echten Namen in Git committen).*

### 2. Verhalten & Payload
- **Trigger:** Sobald ein Paper-Trade geschlossen wird (Take-Profit, Stop-Loss, Break-Even oder manuelle Intervention).
- **Inhalt:** Symbol (z. B. `BTCUSDT`), Richtung (`LONG`/`SHORT`), realisierte PnL in USDT, Netto-ROI %, R-Multiple und Schließungsgrund.
- **Fail-Safe:** Ist `AURA_NTFY_URL` nicht gesetzt oder leer, verhält sich der Push als lautloser No-Op — keine Fehlermeldungen, kein Blockieren des Relays.

---

## Sicherheit

- **Topic-Name = Passwort:** Wer ihn kennt, kann lesen und schreiben. Teile ihn nur mit Personen, die AURA-Benachrichtigungen empfangen sollen.
- **Raten-Schutz:** ntfy.sh-Topics können von Dritten beschrieben werden, wenn der Name bekannt ist. Wähle keinen erratbaren Namen — der vom System-Eigentümer verwendete Name ist zufallsgeneriert.
- **Eigener Server:** Für höhere Sicherheit (Passwort-Schutz, eigene Domain) kann ntfy selbst gehostet werden: [ntfy Self-Hosting Doku](https://docs.ntfy.sh/install/). Der Receiver und das Relay unterstützen beliebige `http://`- und `https://`-URLs.
- **Kein Secret im Repo:** Im Repo erscheint immer nur der Platzhalter `<TOPIC-NAME>`. Der echte Topic wird dem Eigentümer direkt im Chat mitgeteilt.
