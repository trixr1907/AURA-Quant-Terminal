-- Persist restart-critical execution state without recomputing it from current config.
ALTER TABLE trades ADD COLUMN entry_fee TEXT;
ALTER TABLE trades ADD COLUMN timeframe TEXT NOT NULL DEFAULT '1h';
ALTER TABLE trades ADD COLUMN remaining_qty TEXT;
