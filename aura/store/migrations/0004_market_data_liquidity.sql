-- Canonical Bitget instrument metadata and explainable liquidity snapshots.
ALTER TABLE universe ADD COLUMN source TEXT;
ALTER TABLE universe ADD COLUMN status TEXT NOT NULL DEFAULT 'loading';
ALTER TABLE universe ADD COLUMN policy_version TEXT;
ALTER TABLE universe ADD COLUMN event_time_ms INTEGER;
ALTER TABLE universe ADD COLUMN fetched_at_ms INTEGER;
ALTER TABLE universe ADD COLUMN reasons_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE universe ADD COLUMN spread_bps TEXT;
ALTER TABLE universe ADD COLUMN bid_depth_notional TEXT;
ALTER TABLE universe ADD COLUMN ask_depth_notional TEXT;
ALTER TABLE universe ADD COLUMN quote_volume_24h TEXT;
ALTER TABLE universe ADD COLUMN raw_snapshot_sha256 TEXT;

CREATE TABLE instrument_specs (
    symbol          TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    product_type    TEXT NOT NULL,
    symbol_type     TEXT NOT NULL,
    symbol_status   TEXT NOT NULL,
    base_coin       TEXT NOT NULL,
    quote_coin      TEXT NOT NULL,
    settle_coin     TEXT NOT NULL,
    price_tick      TEXT NOT NULL,
    qty_step        TEXT NOT NULL,
    min_qty         TEXT NOT NULL,
    min_notional    TEXT NOT NULL,
    maker_fee_rate  TEXT NOT NULL,
    taker_fee_rate  TEXT NOT NULL,
    max_leverage    INTEGER NOT NULL,
    event_time_ms   INTEGER NOT NULL,
    fetched_at_ms   INTEGER NOT NULL,
    raw_snapshot_sha256 TEXT NOT NULL
);
