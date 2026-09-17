-- Migration 0006: Invalidate existing universe entries created under prior policy versions
-- or lacking independent book and ticker timestamps so they require complete revalidation.
UPDATE universe
SET liquidity_verified = 0,
    status = 'stale',
    reasons_json = json_array('POLICY_UPGRADE_REVALIDATION_REQUIRED')
WHERE policy_version != 'aura-liquidity-v2'
   OR book_event_time_ms IS NULL
   OR ticker_event_time_ms IS NULL;
