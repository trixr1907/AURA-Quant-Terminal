"""Legacy-Importer: v2.5-JSON-State (aura_shared_state.json, shadow_log.jsonl) -> SQLite.

Pflichtbestandteil der Migration M-1 (docs/ARCHITECTURE.md §7):
- Idempotent (Trade-IDs primaerschluesselbasiert; Shadow-Log ueber Datei-Hash-Marker).
- Dry-Run liefert denselben Vollstaendigkeitsreport ohne zu schreiben.
- Keine stillen Defaults: fehlende Felder werden als NULL importiert und im
  Report als Warnung ausgewiesen (z.B. fehlen Gebuehren in v2-Historiensaetzen).
- Bekannter Legacy-Defekt Q-03 (Time-Stop als 'sl_close' protokolliert) wird
  NICHT rueckwirkend korrigiert (keine Umschreibung von Historie), sondern im
  Report vermerkt.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KEY_TRADES = "aura-quant-terminal-active-trades-v2"
KEY_HISTORY = "aura-quant-terminal-history-trades-v2"
KEY_SRV_CFG = "aura-server-bot-config-v1"
KEY_SRV_BOT = "aura-server-bot-state-v1"

ENGINE_VERSION_LEGACY = "v2.5.0-legacy"


@dataclass
class ImportReport:
    dry_run: bool = True
    source_dir: str = ""
    source_sha256: dict[str, str] = field(default_factory=dict)
    trades_open: int = 0
    trades_closed: int = 0
    config_revisions: int = 0
    shadow_rows: int = 0
    duplicates_skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "source_dir": self.source_dir,
            "source_sha256": self.source_sha256,
            "trades_open": self.trades_open,
            "trades_closed": self.trades_closed,
            "config_revisions": self.config_revisions,
            "shadow_rows": self.shadow_rows,
            "duplicates_skipped": self.duplicates_skipped,
            "warnings": list(self.warnings),
        }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _dec(value: Any) -> str | None:
    """Zahl -> Decimal-Text; fehlende/ungueltige Werte -> None (kein Default)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN/Inf ablehnen
        return None
    return repr(f)


def _flag(value: Any) -> int:
    return 1 if value else 0


def _map_trade_open(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(t["id"]),
        "source": "legacy-import",
        "symbol": str(t.get("coin") or t.get("symbol") or ""),
        "dir": int(t.get("dir") or 0),
        "status": "open",
        "entry_price": _dec(t.get("entry")),
        "current_sl": _dec(t.get("currentSl") or t.get("initialSl")),
        "initial_sl": _dec(t.get("initialSl")),
        "tp1": _dec(t.get("tp1") or t.get("tp")),
        "tp2": _dec(t.get("tp2")),
        "tp3": _dec(t.get("tp3")),
        "tp1_hit": _flag(t.get("tp1Hit")),
        "tp2_hit": _flag(t.get("tp2Hit")),
        "tp3_hit": _flag(t.get("tp3Hit")),
        "be_active": _flag(t.get("beActive")),
        "notional": _dec(t.get("notional")),
        "margin": _dec(t.get("margin") or t.get("initialMargin")),
        "leverage": int(t.get("leverage") or 1),
        "opened_at_ms": int(t.get("openedAt") or 0),
        "closed_at_ms": None,
        "exit_price": None,
        "exit_reason": None,
        "realized_pnl": None,
        "fees": None,  # v2 speichert keine Gebuehren im Offen-Trade
        "max_hold_hours": t.get("maxHoldHours"),
        "config_rev": None,
        "engine_version": ENGINE_VERSION_LEGACY,
    }


def _map_trade_closed(t: dict[str, Any]) -> dict[str, Any]:
    row = _map_trade_open(t)
    row.update(
        {
            "status": "closed",
            "closed_at_ms": int(t.get("closedAt") or 0),
            "exit_price": _dec(t.get("exit")),
            "exit_reason": t.get("closeReason"),
            "realized_pnl": _dec(t.get("realizedPnl")),
            "fees": None,  # v2-Historie modelliert keine Gebuehren (Report-Warnung)
        }
    )
    return row


_INSERT_TRADE = """
INSERT OR IGNORE INTO trades (
    id, source, symbol, dir, status, entry_price, current_sl, initial_sl,
    tp1, tp2, tp3, tp1_hit, tp2_hit, tp3_hit, be_active,
    notional, margin, leverage, opened_at_ms, closed_at_ms,
    exit_price, exit_reason, realized_pnl, fees, max_hold_hours,
    config_rev, engine_version, record_schema
) VALUES (
    :id, :source, :symbol, :dir, :status, :entry_price, :current_sl, :initial_sl,
    :tp1, :tp2, :tp3, :tp1_hit, :tp2_hit, :tp3_hit, :be_active,
    :notional, :margin, :leverage, :opened_at_ms, :closed_at_ms,
    :exit_price, :exit_reason, :realized_pnl, :fees, :max_hold_hours,
    :config_rev, :engine_version, 3
)
"""


def _required_present(row: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [f for f in fields if row.get(f) in (None, "")]


def import_legacy_state(
    conn: sqlite3.Connection,
    state_dir: str | Path,
    *,
    dry_run: bool = True,
) -> ImportReport:
    """Importiert den v2.5-State. Dry-Run schreibt nichts."""
    src = Path(state_dir)
    report = ImportReport(dry_run=dry_run, source_dir=str(src))

    shared_path = src / "aura_shared_state.json"
    if not shared_path.exists():
        raise FileNotFoundError(f"Legacy-State fehlt: {shared_path}")
    shared = json.loads(shared_path.read_text(encoding="utf-8"))
    report.source_sha256[shared_path.name] = _sha256_file(shared_path)

    if int(shared.get("schema_version") or 0) != 2:
        report.warnings.append(
            f"aura_shared_state.json schema_version={shared.get('schema_version')!r} (erwartet: 2)"
        )

    open_trades = [t for t in shared.get(KEY_TRADES) or [] if isinstance(t, dict) and t.get("id")]
    closed_trades = [t for t in shared.get(KEY_HISTORY) or [] if isinstance(t, dict) and t.get("id")]

    mapped_open, mapped_closed = [], []
    for t in open_trades:
        row = _map_trade_open(t)
        missing = _required_present(row, ("symbol", "entry_price", "initial_sl", "notional", "margin"))
        if missing:
            report.warnings.append(f"Offener Trade {row['id']}: fehlende Felder {missing}")
        if row["dir"] not in (1, -1):
            report.warnings.append(f"Offener Trade {row['id']}: ungueltige dir={row['dir']}")
            continue
        mapped_open.append(row)
    for t in closed_trades:
        row = _map_trade_closed(t)
        if row["dir"] not in (1, -1):
            report.warnings.append(f"Historien-Trade {row['id']}: ungueltige dir={row['dir']}")
            continue
        if row["exit_reason"] is None:
            report.warnings.append(f"Historien-Trade {row['id']}: fehlender closeReason")
        mapped_closed.append(row)

    if closed_trades:
        report.warnings.append(
            "Legacy-Hinweis Q-03: v2.5 protokollierte Time-Stops faelschlich als 'sl_close'; "
            "exit_reason der importierten Historie kann daher falsch attributiert sein "
            "(Historie wird nicht umgeschrieben)."
        )
        report.warnings.append(
            "Legacy-Hinweis: v2.5-Historie enthaelt keine Gebuehren; fees=NULL (unbekannt), "
            "realized_pnl ist damit Brutto."
        )

    # Shadow-Log (optional)
    shadow_rows: list[dict[str, Any]] = []
    shadow_path = src / "shadow_log.jsonl"
    if shadow_path.exists():
        report.source_sha256[shadow_path.name] = _sha256_file(shadow_path)
        for lineno, line in enumerate(shadow_path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                report.warnings.append(f"shadow_log.jsonl Zeile {lineno}: ungueltiges JSON, uebersprungen")
                continue
            shadow_rows.append(
                {
                    "ts_ms": int(rec.get("ts") or rec.get("ts_ms") or 0),
                    "symbol": str(rec.get("symbol") or rec.get("coin") or ""),
                    "timeframe": str(rec.get("tf") or rec.get("timeframe") or ""),
                    "dir": int(rec.get("dir") or 0),
                    "score": rec.get("score"),
                    "decision": str(rec.get("decision") or "UNKNOWN"),
                    "reject_reason": rec.get("reject_reason"),
                    "config_sha256": str(rec.get("config_sha256") or rec.get("configSha256") or "legacy-unknown"),
                    "payload": line,
                }
            )

    report.trades_open = len(mapped_open)
    report.trades_closed = len(mapped_closed)
    report.shadow_rows = len(shadow_rows)
    report.config_revisions = 1 if isinstance(shared.get(KEY_SRV_CFG), dict) else 0

    if dry_run:
        return report

    now_ms = int(time.time() * 1000)
    marker = f"legacy_import:{report.source_sha256[shared_path.name]}"
    with conn:
        already = conn.execute(
            "SELECT 1 FROM audit_log WHERE action='legacy_import' AND detail LIKE ?",
            (f"%{marker}%",),
        ).fetchone()
        if already:
            report.duplicates_skipped = report.trades_open + report.trades_closed + report.shadow_rows
            report.trades_open = report.trades_closed = report.shadow_rows = 0
            report.config_revisions = 0
            report.warnings.append("Import bereits ausgefuehrt (Hash-Marker); nichts erneut geschrieben.")
            return report

        before = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        for row in mapped_open + mapped_closed:
            conn.execute(_INSERT_TRADE, row)
        after = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        report.duplicates_skipped = (len(mapped_open) + len(mapped_closed)) - (after - before)

        for row in shadow_rows:
            conn.execute(
                "INSERT INTO shadow_log (ts_ms, symbol, timeframe, dir, score, decision,"
                " reject_reason, config_sha256, payload) VALUES"
                " (:ts_ms, :symbol, :timeframe, :dir, :score, :decision,"
                " :reject_reason, :config_sha256, :payload)",
                row,
            )

        cfg = shared.get(KEY_SRV_CFG)
        if isinstance(cfg, dict):
            conn.execute(
                "INSERT INTO config_revisions (payload, source, created_at_ms, applied_at_ms)"
                " VALUES (?, 'legacy-import', ?, ?)",
                (json.dumps(cfg, sort_keys=True), now_ms, now_ms),
            )

        bot = shared.get(KEY_SRV_BOT)
        equity = _dec((bot or {}).get("equity")) or "0"
        conn.execute(
            "INSERT INTO runner_state (id, fsm_state, reason, equity, cycle_count, updated_at_ms)"
            " VALUES (1, 'HALTED', 'legacy import — Runner noch nicht aktiviert', ?, 0, ?)"
            " ON CONFLICT(id) DO UPDATE SET equity=excluded.equity, updated_at_ms=excluded.updated_at_ms",
            (equity, now_ms),
        )

        conn.execute(
            "INSERT INTO audit_log (ts_ms, actor, action, detail) VALUES (?, 'system', 'legacy_import', ?)",
            (now_ms, json.dumps({"marker": marker, "report": report.to_dict()}, sort_keys=True)),
        )
    return report
