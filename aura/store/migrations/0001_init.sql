-- AURA v3 Initialschema (ADR-0002).
-- Konventionen:
--   * Zeitstempel: Unix-Millisekunden (UTC), INTEGER.
--   * Geldbetraege/Mengen mit Rundungsrelevanz: TEXT (Decimal), niemals REAL.
--   * Preise (Messwerte aus der Exchange): REAL zulaessig.
--   * Evidenztabellen (shadow_log, audit_log, trade_events) sind append-only.

CREATE TABLE schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL  -- ISO-8601 UTC
);

-- Marktdaten mit Provenienz (Mandat §6: Quelle, Event-Zeit, Empfangszeit, UTC).
CREATE TABLE candles (
    source          TEXT NOT NULL,            -- z.B. 'bitget'
    symbol          TEXT NOT NULL,            -- z.B. 'BTCUSDT'
    timeframe       TEXT NOT NULL,            -- '15m','1h','4h','1d'
    open_time_ms    INTEGER NOT NULL,         -- Event-Zeit (Kerzenbeginn, UTC ms)
    open            REAL NOT NULL,
    high            REAL NOT NULL,
    low             REAL NOT NULL,
    close           REAL NOT NULL,
    volume          REAL NOT NULL,
    closed          INTEGER NOT NULL,         -- 1 = geschlossene Kerze (signalwirksam)
    received_at_ms  INTEGER NOT NULL,         -- Empfangszeit (UTC ms)
    PRIMARY KEY (source, symbol, timeframe, open_time_ms)
);
CREATE INDEX idx_candles_lookup ON candles (symbol, timeframe, closed, open_time_ms);

-- Universum / Liquiditaetsstatus (fail-closed: liquidity_verified=0 blockiert Signale).
CREATE TABLE universe (
    symbol              TEXT PRIMARY KEY,
    active              INTEGER NOT NULL,
    liquidity_verified  INTEGER NOT NULL DEFAULT 0,
    vol_24h             REAL,                 -- NULL = unbekannt, niemals 0 als Default
    updated_at_ms       INTEGER NOT NULL
);

-- Paper-Trades (server-authoritative). Geld als TEXT (Decimal).
CREATE TABLE trades (
    id              TEXT PRIMARY KEY,
    source          TEXT NOT NULL,            -- 'server' (Runner) | 'legacy-import'
    symbol          TEXT NOT NULL,
    dir             INTEGER NOT NULL,         -- 1 long, -1 short
    status          TEXT NOT NULL,            -- 'open' | 'closed'
    entry_price     TEXT NOT NULL,
    current_sl      TEXT NOT NULL,
    initial_sl      TEXT NOT NULL,
    tp1             TEXT, tp2 TEXT, tp3 TEXT,
    tp1_hit         INTEGER NOT NULL DEFAULT 0,
    tp2_hit         INTEGER NOT NULL DEFAULT 0,
    tp3_hit         INTEGER NOT NULL DEFAULT 0,
    be_active       INTEGER NOT NULL DEFAULT 0,
    notional        TEXT NOT NULL,
    margin          TEXT NOT NULL,
    leverage        INTEGER NOT NULL,
    opened_at_ms    INTEGER NOT NULL,
    closed_at_ms    INTEGER,
    exit_price      TEXT,
    exit_reason     TEXT,                     -- 'sl_close'|'tp3_close'|'timestop'|'manual'|'halt_close'
    realized_pnl    TEXT,                     -- Decimal, NULL solange offen
    fees            TEXT,                     -- Decimal; NULL = unbekannt (z.B. Legacy-Import), nie als 0 verstecken
    max_hold_hours  REAL,
    config_rev      INTEGER,                  -- aktive Config-Revision bei Eroeffnung
    engine_version  TEXT NOT NULL,            -- Verarbeitungsversion (Provenienz)
    record_schema   INTEGER NOT NULL DEFAULT 3
);
CREATE INDEX idx_trades_status ON trades (status, symbol);

-- Append-only Ereignisse je Trade (TP-Hits, BE, SL-Verschiebungen, Schliessung).
CREATE TABLE trade_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id    TEXT NOT NULL REFERENCES trades(id),
    ts_ms       INTEGER NOT NULL,
    event       TEXT NOT NULL,                -- 'open'|'tp1'|'tp2'|'tp3'|'auto_be'|'sl_close'|'timestop'|'manual_close'
    price       TEXT,
    detail      TEXT                          -- JSON, optional
);
CREATE INDEX idx_trade_events_trade ON trade_events (trade_id, ts_ms);

-- Idempotente Control-Plane-Kommandos (Not-Halt, Config, Close-All).
CREATE TABLE commands (
    id           TEXT PRIMARY KEY,            -- UUID, Idempotenzschluessel
    type         TEXT NOT NULL,               -- 'halt'|'resume'|'close_all'|'set_config'
    payload      TEXT NOT NULL,               -- JSON
    status       TEXT NOT NULL,               -- 'pending'|'applied'|'rejected'
    created_at_ms INTEGER NOT NULL,
    applied_at_ms INTEGER,
    result       TEXT
);

-- Konfigurationsrevisionen (angefordert vs. aktiv).
CREATE TABLE config_revisions (
    rev          INTEGER PRIMARY KEY AUTOINCREMENT,
    payload      TEXT NOT NULL,               -- JSON (serverseitig validiert)
    source       TEXT NOT NULL,               -- 'operator' | 'legacy-import'
    created_at_ms INTEGER NOT NULL,
    applied_at_ms INTEGER                     -- NULL = angefordert, noch nicht aktiv
);

-- Runner-Zustandsmaschine (eine Zeile).
CREATE TABLE runner_state (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    fsm_state    TEXT NOT NULL,               -- STARTING|WARMING_UP|RUNNING|DEGRADED|HALTED|RECOVERING
    reason       TEXT,
    equity       TEXT NOT NULL,               -- Decimal
    cycle_count  INTEGER NOT NULL DEFAULT 0,
    updated_at_ms INTEGER NOT NULL
);

-- Append-only Shadow-Entscheidungslog (Evidenz; nur INSERT).
CREATE TABLE shadow_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms        INTEGER NOT NULL,
    symbol       TEXT NOT NULL,
    timeframe    TEXT NOT NULL,
    dir          INTEGER NOT NULL,
    score        REAL,
    decision     TEXT NOT NULL,               -- 'ACCEPTED' | 'REJECTED'
    reject_reason TEXT,
    config_sha256 TEXT NOT NULL,
    payload      TEXT                         -- JSON (Rohdatensatz)
);
CREATE INDEX idx_shadow_log_ts ON shadow_log (ts_ms);

-- Benachrichtigungen mit Dedup und Zustellstatus.
CREATE TABLE notify_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key    TEXT NOT NULL UNIQUE,        -- Dedup-Schluessel
    kind         TEXT NOT NULL,
    payload      TEXT NOT NULL,               -- JSON (Secrets maskiert)
    status       TEXT NOT NULL,               -- 'pending'|'delivered'|'failed'
    attempts     INTEGER NOT NULL DEFAULT 0,
    created_at_ms INTEGER NOT NULL,
    delivered_at_ms INTEGER
);

-- Append-only Audit-Log (Login, Config, Not-Halt, Migrationen).
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms       INTEGER NOT NULL,
    actor       TEXT NOT NULL,                -- 'operator'|'system'|'worker'
    action      TEXT NOT NULL,
    detail      TEXT
);

-- Append-only-Schutz: Evidenztabellen verbieten UPDATE/DELETE.
CREATE TRIGGER shadow_log_no_update BEFORE UPDATE ON shadow_log
BEGIN SELECT RAISE(ABORT, 'shadow_log is append-only'); END;
CREATE TRIGGER shadow_log_no_delete BEFORE DELETE ON shadow_log
BEGIN SELECT RAISE(ABORT, 'shadow_log is append-only'); END;
CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER trade_events_no_update BEFORE UPDATE ON trade_events
BEGIN SELECT RAISE(ABORT, 'trade_events is append-only'); END;
CREATE TRIGGER trade_events_no_delete BEFORE DELETE ON trade_events
BEGIN SELECT RAISE(ABORT, 'trade_events is append-only'); END;
