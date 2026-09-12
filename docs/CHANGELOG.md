# Changelog

All notable changes to the **AURA — Confluence Terminal** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
