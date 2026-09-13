# Changelog

All notable changes to the **AURA — Confluence Terminal** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.5.2] – 2026-09-13 – Runde 21: Infra-PATCH — Receiver Health-Fix & Deploy-Zuverlässigkeit

### Fixed
- `wait_for_health()` im Deploy-Receiver: Timeout von 90 s auf 300 s erhöht (muss > Docker-StartPeriod 90 s sein). Dieser Race war die Root Cause des fehlgeschlagenen automatischen Deployments von v1.5.1: der Receiver hat das Image erfolgreich gebaut, dann aber den Healthcheck-Übergang von `starting` auf `healthy` nicht abgewartet und das Deployment abgebrochen.
- `bitget_relay.py` Z.391: Beispiel-URL im Kommentar von `http://ntfy.sh/my-aura-alerts` zu `https://ntfy.sh/<TOPIC-NAME>` korrigiert (Kommentar-only, kein Verhaltenscode).

### Changed
- Deploy-Receiver sendet nach jedem Deploy-Versuch receiver-originiert ntfy ✅/❌: Erfolg (Priority default), Fehlschlag (Priority high). Benachrichigtung ist damit unabhängig vom lokalen `bitget_relay.py`-Prozess.
- `scripts/build_package.py` und `tests/test_package_hygiene.py`: Release-Dokument-Referenz auf `RELEASE_v1.5.2.md` aktualisiert.

### Infrastructure
- `aura-quant-1` vs. `proxmox-aura` Host-Untersuchung dokumentiert: zwei physisch getrennte Maschinen in unterschiedlichen Tailscale-Netzen (`tailbb41d7` bzw. `tail8b74ea`). Beide Hosts erhalten den wait_for_health-Fix (aura-quant-1 direkt verifiziert, proxmox-aura dokumentiert mit Unterschieden im Server-Header).

### Scope
- Trials-Ledger bleibt auf `EXP-032`; Urteil bleibt `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
- Keine Änderungen an Score-, Sizing-, Radar-Klassifikations- oder Evidenzlogik.

## [1.5.1] – 2026-09-13 – Runde 20: MTF-Konfigurationsfix & Kein-Signal-Klartext

### Fixed
- Der Paper-Autobot prüft die MTF-Mindestanzahl jetzt gegen seine konfigurierte Schwelle `1/4` bis `4/4`, statt die fest auf `SYM.mtfNeed` basierende Radar-Executability zu übernehmen.
- `radarFiltered` verwendet denselben korrigierten Konfigurationspfad; die unmittelbare Fresh-Revalidierung vor dem Einstieg bleibt unverändert stärker.

### Changed
- Bei null ausgewählten Setups erklärt der Funnel den dominanten Ablehnungsgrund in Klartext; fehlende positive OOS-Erwartung wird ausdrücklich als korrektes Fail-closed-Verhalten und nicht als Defekt benannt.
- Reject-Labels besitzen Tooltips, und die Einstellungen erklären die Grenzen von MinScore, MTF und TimeStop gegenüber festen Radar- und Evidenz-Gates.
- `bitget_relay.py` Z.391: Beispiel-URL im Kommentar von `http://ntfy.sh/` zu `https://ntfy.sh/<TOPIC-NAME>` korrigiert (Kommentar-only, kein Verhaltenscode; landet real in v1.5.2).

### Infrastructure (docs-only, kein Versionsbump)
- Deploy-Receiver auf beiden VMs (aura-quant-1, proxmox-aura) um `_ntfy_notify()`-Funktion erweitert: Push-Alert bei Deploy-Erfolg (Priority: default) und Fehlschlag (Priority: high) via `AURA_NTFY_URL` — identisches Muster wie PF-33 in `bitget_relay.py`.
- `docs/deployment/NTFY_GUIDE.md` hinzugefügt: Endverbraucher-Leitfaden für ntfy auf Handy (Android/iOS) und PC, inkl. Topic-Sicherheit und Relay-Zusammenspiel.
- `docs/deployment/webhook-incident-20260913.md` hinzugefügt: Incidentbericht für v1.5.1 Health-Race-Condition (Root Cause: `wait_for_health()` 90s vs. Docker StartPeriod 90s).
- Root-Level RELEASE_v*.md Stubs (15 Dateien) entfernt — kanonische Quelle ist `docs/releases/` (Konvention seit Runde 18). Docs-Einheit bleibt bei 27 Release-Dateien in `docs/releases/`.
- `docs/README.md` und `README.md` um ntfy-Guide, Deploy-Kette und aktuelle Incident-Links aktualisiert.

### Scope
- PATCH als Prozess-/UI-Fix und Konfigurations-Plumbing eines bestehenden Vertrags; keine Änderungen an Score-, Sizing-, Radar-Klassifikations- oder Evidenzlogik.
- Trials-Ledger bleibt auf `EXP-032`; Urteil bleibt `SOFTWARE_GO / MODEL_NO_EVIDENCE`.

## [1.5.0] – 2026-09-13 – Runde 19: Chart-Bedienung & Zeichentools-MVP

### Added
- Lokale Chart-Zeichnungen: horizontale Linie und Zwei-Punkt-Trendlinie mit Auswahl, Anker-Verschiebung, Löschen und symbolbezogener Persistenz.
- Ziehbare Chart-Höhe für Maus/Touch/Tastatur mit 44-px-Hitbox, Grenzen und lokaler Persistenz.
- Fokus-Kerzenloads erhalten an Radar-Batch-Grenzen Vorrang; auch begrenzte Retries bleiben vor Radar-Arbeit.

### Changed
- Live-Tracker und Paper-Autobot verwenden dieselbe kompakte Live-Karte; Autobot-Felder sind eine optionale Erweiterung.
- Time-Stop-Werkzeug liegt eingeklappt unter „Erweitert: Manuelle Analyse“; der automatische Entry-Optimizer bleibt unverändert.

### Scope
- Prozess-/UI-Release ohne Änderungen an Score-, Signal- oder Sizing-Logik. Zeichnungen sind rein lokale Overlays.
- Trials-Ledger bleibt nach Klassifikation als Prozess-/UI-Fix unverändert auf `EXP-032`; Scheduling ändert nur die Reihenfolge von Datenabrufen, nicht deren Auswertung.

## [1.4.1] - 2026-09-13

### Fixed
- **PF-37 Autobot Live-Tracking:** `renderTradeCard()` erhält wieder echte `calculateTradeMetrics`-Werte im Autobot-Container; Autobot-Karten aktualisieren synchron mit Ticker-Ticks ohne Flackern.
- **PF-38 Klartext & Tooltips:** Deutsche Endverbraucher-Erklärungen für BTC-Regime (BULL, BEAR, SIDEWAYS, EMA200, ADX, Squeeze) mit `tabindex="0"` und `aria-describedby`; Hero-Level-Kacheln (Entry, SL, TP1, TP2) mit informativen Tooltips und Touch-Icons.
- **PF-39 Chart-Frische & Lade-Zustand:** Neues Frische-Badge am Chartkopf (`Kerzen: vor Xs · Quelle`) aktualisiert im Sekundentakt und färbt sich bei Fehler rot; `chart-load-state`-Band zeigt Zustand `Lade…` ehrlich an und verschwindet nach erfolgreichem Laden.

### Research status
- Urteil bleibt unverändert ehrlich `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
- Trials-Ledger unverändert auf `EXP-032`.

---

## [1.4.0] - 2026-09-13

### Added
- Separater produktpflichtiger Checkpoint (`ledger_checkpoint.json`) gegen Tail-Truncation des Trials-Ledgers.
- Skript `scripts/append_ledger.py` für validierte Appends und atomare Checkpoint-Updates.
- Unabhängige Python-Referenz `scripts/cvd_reference.py` für die formelgetreue CVD-/EMA-CVD-Langzeitmessung gegen die Dashboard-Engine.
- Vollständige Regressionstests für Checkpoint-Verifikation und CVD-Parität.

### Changed
- `scripts/verify_ledger.py` gleicht `last_entry_id`, `entry_count` und `chain_head` fail-closed mit dem Checkpoint ab.
- `scripts/release_check.py` führt `scripts/cvd_reference.py` im automatisierten Release-Gate aus.
- Version auf 1.2.10 synchronisiert.

### Research status
- F-06 ist durch den produktpflichtigen Checkpoint und die Tail-Truncation-Prüfung vollständig geschlossen.
- F-16 ist durch die unabhängige Python-Referenz über 64.859 Bars mit 0 Vergleichskipps und einer maximalen relativen Drift von $2,54 \times 10^{-11} \le 10^{-10}$ als akzeptiertes numerisches Verhalten abgeschlossen.
- Urteil bleibt ehrlich `SOFTWARE_GO / MODEL_NO_EVIDENCE`.

---

## [1.2.9] - 2026-09-12

### Added
- SHA-256-verknüpfter, maschinenlesbarer Trials-Ledger und fail-closed Verifier im Release-Gate.
- CVD-/EMA-CVD-/Vergleichs-/Delta-Felder im Pine Data Window als Voraussetzung für eine unabhängige Pine↔JS-Langzeitmessung.
- Regressionstests für gültige, fehlende und manipulierte Ledger sowie DSR-Monotonie.

### Changed
- Phase-D-DSR bezieht die verifizierte historische Modellversuchszahl aus dem Ledger und verwendet konservativ `max(45, ledger N)`; fehlende oder ungültige Evidenz bricht ab.
- Version auf 1.2.9 synchronisiert.

### Research status
- F-05 und F-06 sind technisch geschlossen.
- F-16 bleibt bis zum erneuten TradingView-Export der neuen CVD-Felder `NICHT GEPRÜFT`; vorhandene Fixtures enthalten diese unabhängigen Pine-Zustände nicht. Das ist kein Edge-Nachweis.

---

## [1.2.8] - 2026-09-12

### Added
- **Path-aware SemVer progression regression coverage:**
  - Verifies that documentation and infrastructure-only commits remain release-neutral.
  - Preserves fail-closed enforcement for product, test, dependency, and build changes.
- **Release Documentation:**
  - Added `docs/releases/RELEASE_v1.2.8.md`.

### Changed
- **Version Progression Gate:**
  - Replaced commit-count detection with `git diff --name-only <tag>..HEAD` path classification.
  - Exempted `.github/**`, `docs/**`, Markdown files, and `LICENSE` from forced version bumps.

### Fixed
- Corrected the v1.2.6 F-09 count from 49 to 51 audited `innerHTML` occurrences.
- Completed the v1.2.7 CI history with the previously omitted workflow-fix commits.

---

## [1.2.7] - 2026-09-12

### Added
- **Deterministic Pytest Dependency Pinning (K7):**
  - Added `pytest==9.1.1` to `requirements.txt` for guaranteed build reproducibility.
  - Added `docs/releases/RELEASE_v1.2.7.md`.

### Changed
- **CI / Release Workflow Hardening:**
  - Pinned Python 3.12 in the release workflow (`e4db4ec`).
  - Added pytest to release dependencies and repaired branch CI (`fc2f683`).
  - Restored the branch `release_check` invocation without `--allow-current-version` (`69873e0`).
  - Removed ad-hoc unpinned `pip install ... pytest` from `.github/workflows/ci.yml` and `.github/workflows/publish-release.yml`.
  - Standardized `publish-release.yml` on Python 3.12 matching `ci.yml`.

---

## [1.2.6] - 2026-09-12

### Added
- **Behavior-based Exit-Path & Kelly Test Harness (F-17..F-20):**
  - Analytical Kelly oracle tests (`tests/test_kelly_oracle.js`) verifying $f^*=p-q/b$, half-Kelly, hard-cap, and sample ramp.
  - Runtime behavioral test suite (`tests/test_autobot_timestop_behavior.js`) exercising `Autobot.updateActiveTrades()` across timeframes (15m, 1h, 4h, 1d), holding deadlines, PnL states, and 12-bar fallbacks.
  - 100% mutation test coverage (15/15 mutants killed via `scripts/audit_rev2_mutations.py`).
- **Release Documentation:**
  - Added `docs/releases/RELEASE_v1.2.6.md` and updated canonical documentation index.

### Changed
- **Pine v6 ↔ JS Signal Parity (F-16):**
  - Epsilon-protected VWAP comparison in `Symbiose_Dashboard.html` (`(c - vwap) > 1e-9 * c`) preventing IEEE-754 underflow flips on float equality.
  - Documented ADX knife-edge discretization at thresholds 18 and 25 as accepted behavior.
- **Security & Hygiene (F-09, F-10, F-14):**
  - Audited all 51 `innerHTML` assignments in `Symbiose_Dashboard.html`; verified and hardened external data escaping via `esc()` and `textContent`.
  - Consolidated documentation in canonical `docs/` hierarchy (`docs/research/`, `docs/deployment/`, `docs/releases/`) and replaced redundant root copies with pointers.
  - Removed dead legacy klines parsing functions (`binanceKlines`, `bybitKlines`, `cgKlines`) from `Symbiose_Dashboard.html`.
- **CI & Release Workflow:**
  - Automated version progression checks in `scripts/release_check.py` and GitHub Actions workflow with SHA-256 pinned actions.

### Fixed
- Fixed critical trend gate mutation regression and test gaps in Autobot monitoring.
- Fixed version inconsistencies across relay, dashboard, tutorial, scripts, and Dockerfile.

---

## [1.2.5] - 2026-09-12

### Added
- **Native TradingView Drawing Tool HUD Assist (`#tv-drawing-tool-modal`):**
  - Integrated 1-click parameter copy fields for **Entry**, **Take Profit (TP1/TP2/TP3)**, and **Stop Loss (SL)** directly from active trades.
  - Calculation and display of Risk/Reward Ratio (CRV), Leverage, Notional Position Size, and Lot Size.
  - Zero indicator slots consumed on TradingView (eliminates chart clutter and script limits).
- **Paper Trading Mode Unlocked:**
  - Removed hero candidate locks on `btn-paper-trade` (`startPaperTradeFromCockpit`), enabling continuous manual and automated paper trading sessions.
- **Direct Protocol Dispatch (`tradingview://`):**
  - Automatic invocation of the TradingView Desktop application with URL scheme fallback to browser.

### Changed
- Decoupled chart drawing overlay logic from `Symbiose_Signal_System_v1.pine` to maintain a lightweight, pure confluence indicator.
- Updated documentation and test suites to reflect drawing tool HUD specifications.

---

## [1.2.4] - 2026-09-12

### Added
- **Dedicated Trade-Specific Position Tool:**
  - Separated 1:1 drawing tool assistance from the core confluence signal system.
  - Added quick copy actions for single trades in the active trade table.
- **Relay Dispatch Resilience:**
  - Hardened CORS and Origin handling in `bitget_relay.py` for headless and remote environments.

---

## [1.2.3] - 2026-09-12

### Added
- **AURA Brand Identity & Designer Assets:**
  - SVG vector assets (`assets/aura_logo.svg`, `assets/aura_logo_horizontal.svg`).
  - Dark-mode responsive brand guidelines (`docs/brand_design.md`).
- **Release Package Hygiene:**
  - Filtered test artifacts, internal diagnostics, and historical reports from release zip distributions.

---

## [1.2.2] - 2026-09-12

### Added
- **TradingView Long/Short Position Tool Bridge:**
  - Pine Script v6 coordinate rendering matching TradingView Solutions 43000517002 and 43000516992.
- **Origin Routing Whitelist:**
  - Allowed origin-header validation for TradingView Desktop app communication.

---

## [1.2.1] - 2026-09-12

### Added
- **Realistic Default Configuration:**
  - Default parameters: 1,000 USDT capital, 5% risk, 10x leverage, 500k USDT 24h min volume.
- **Autobot Setup Discovery Quick-Guide:**
  - Interactive help modals for beginner transparency.

---

## [1.2.0] - 2026-09-11

### Added
- **Strict Bitget USDT-M Perpetual Futures Focus:**
  - Filtered market universe to active USDT-margined perpetuals only.
- **Market Structure Visualization:**
  - Enhanced Break of Structure (BOS) and Change of Character (CHoCH) labels in Pine Script.
- **Autobot Activity Profiles:**
  - Configurable scan funnels and activity presets.

---

## [1.1.8] - 2026-09-11
- **TradingView Basic Bridge & Workflow QoL:** Setup discovery, edge cockpit quick-picks, and radar ranking.

## [1.1.7] - 2026-09-11
- **Setup Discovery & Edge Cockpit Quick-Picks:** Dynamic candidate ranking and quick-selection UI.

## [1.1.6] - 2026-09-11
- **Fail-Closed Liquidity Gating & Relay Resilience:** Progressive radar loading, docker readiness probes.

## [1.1.5] - 2026-09-10
- **Live Trade Tracker & Runner Trailing:** SuperTrend dynamic trail, time-stop scaling, and break-even stops.

## [1.1.1] - 2026-09-10
- **Cross-Device State Sync:** Offline queue, conflict resolution, and atomic multi-device mutations.

## [1.1.0] - 2026-09-10
- **Scientific Audit & Anti-P-Hacking Gates:** K=4 Walk-Forward Backtesting, Deflated Sharpe Ratio (DSR), and immutable trial tracking.
