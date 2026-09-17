-- Separate timestamps for orderbook and ticker to ensure independent freshness validation.
ALTER TABLE universe ADD COLUMN book_event_time_ms INTEGER;
ALTER TABLE universe ADD COLUMN book_fetched_at_ms INTEGER;
ALTER TABLE universe ADD COLUMN ticker_event_time_ms INTEGER;
ALTER TABLE universe ADD COLUMN ticker_fetched_at_ms INTEGER;
