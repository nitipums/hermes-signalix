-- P0: Immutable breakout event observation lifecycle (stage transitions)
--
-- Adds daily_breakout_event_stage_transitions: an append-only, immutable log of
-- every stage transition an event progresses through (e.g. fresh -> extended ->
-- broken -> failed). Each row is a single transition: from_stage -> to_stage,
-- attributed to the scan run that observed it, with the event's original trigger,
-- pivot, and failure level available via the event FK.
--
-- Idempotency: (event_id, to_stage, observed_on) is UNIQUE; a rerun that produces
-- the same stage for the same event+date is a no-op (ON CONFLICT DO NOTHING).
-- Mutation protection: the append-only trigger rejects UPDATE/DELETE on the
-- transition log, matching the daily events/observations tables.
CREATE TABLE IF NOT EXISTS daily_breakout_event_stage_transitions (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES daily_breakout_events(id) ON DELETE RESTRICT,
    from_stage TEXT,
    to_stage TEXT NOT NULL,
    observed_on DATE NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    distance_from_trigger_pct DOUBLE PRECISION,
    scan_run_id UUID NOT NULL REFERENCES daily_scan_runs(id) ON DELETE RESTRICT,
    failure_reason TEXT,
    raw_evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(event_id, to_stage, observed_on, scan_run_id)
);

CREATE INDEX IF NOT EXISTS daily_breakout_event_stage_transitions_event_idx
    ON daily_breakout_event_stage_transitions(event_id, observed_on DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS daily_breakout_event_stage_transitions_scan_run_idx
    ON daily_breakout_event_stage_transitions(scan_run_id);

COMMENT ON TABLE daily_breakout_event_stage_transitions IS
    'Immutable append-only log of breakout event stage transitions. Each row '
    'records from_stage -> to_stage for a single event observation cycle, '
    'attributed to the scan run that observed it. The event row holds the '
    'original trigger_price, pre_break_pivot_low, and failure_level; this table '
    'records the observation-level stage progression (fresh->extended->broken->'
    'failed etc.). Never updated or deleted.';
