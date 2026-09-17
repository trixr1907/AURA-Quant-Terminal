-- Persist exactly-once closed-bar decisions per symbol/timeframe.
CREATE TABLE processed_bars (
    source          TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    open_time_ms    INTEGER NOT NULL,
    processed_at_ms INTEGER NOT NULL,
    decision        TEXT NOT NULL,
    trade_id        TEXT,
    detail          TEXT,
    PRIMARY KEY (source, symbol, timeframe, open_time_ms)
);
CREATE INDEX idx_processed_bars_lookup
    ON processed_bars (symbol, timeframe, open_time_ms);
