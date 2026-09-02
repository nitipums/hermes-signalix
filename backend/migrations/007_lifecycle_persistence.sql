-- T9A: immutable lifecycle candidates, machine snapshots, and owner reviews.
-- This migration is intentionally safe to apply more than once.

CREATE TABLE IF NOT EXISTS lifecycle_candidates (
    candidate_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL CHECK (btrim(symbol) <> ''),
    thesis_as_of TIMESTAMPTZ NOT NULL,
    policy_version TEXT NOT NULL CHECK (btrim(policy_version) <> ''),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lifecycle_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES lifecycle_candidates(candidate_id) ON DELETE RESTRICT,
    setup_id TEXT NOT NULL CHECK (btrim(setup_id) <> ''),
    observation_as_of TIMESTAMPTZ NOT NULL,
    policy_version TEXT NOT NULL CHECK (btrim(policy_version) <> ''),
    source TEXT NOT NULL CHECK (btrim(source) <> ''),
    setup_plan JSONB NOT NULL,
    machine_payload JSONB NOT NULL,
    lifecycle_status TEXT NOT NULL CHECK (btrim(lifecycle_status) <> ''),
    expiry_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (candidate_id, setup_id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS lifecycle_review_events (
    event_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES lifecycle_candidates(candidate_id) ON DELETE RESTRICT,
    setup_id TEXT NOT NULL CHECK (btrim(setup_id) <> ''),
    snapshot_id TEXT NOT NULL,
    event TEXT NOT NULL CHECK (event IN (
        'AGREE', 'WATCH', 'DISAGREE_WAVE', 'REJECT_SETUP',
        'MISSED_CANDIDATE', 'NOTE'
    )),
    reviewer TEXT NOT NULL CHECK (btrim(reviewer) <> ''),
    note TEXT,
    idempotency_key TEXT NOT NULL UNIQUE CHECK (btrim(idempotency_key) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (candidate_id, setup_id, snapshot_id)
        REFERENCES lifecycle_snapshots(candidate_id, setup_id, snapshot_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS lifecycle_snapshots_candidate_idx
    ON lifecycle_snapshots (candidate_id, observation_as_of DESC);
CREATE INDEX IF NOT EXISTS lifecycle_snapshots_setup_idx
    ON lifecycle_snapshots (candidate_id, setup_id, observation_as_of DESC);
CREATE INDEX IF NOT EXISTS lifecycle_review_events_candidate_idx
    ON lifecycle_review_events (candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS lifecycle_review_events_snapshot_idx
    ON lifecycle_review_events (snapshot_id, created_at DESC);

CREATE OR REPLACE FUNCTION lifecycle_persistence_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'lifecycle history is append-only: % is not permitted on %',
        TG_OP, TG_TABLE_NAME;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'lifecycle_candidates_append_only') THEN
        CREATE TRIGGER lifecycle_candidates_append_only
        BEFORE UPDATE OR DELETE ON lifecycle_candidates
        FOR EACH ROW EXECUTE FUNCTION lifecycle_persistence_reject_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'lifecycle_snapshots_append_only') THEN
        CREATE TRIGGER lifecycle_snapshots_append_only
        BEFORE UPDATE OR DELETE ON lifecycle_snapshots
        FOR EACH ROW EXECUTE FUNCTION lifecycle_persistence_reject_mutation();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'lifecycle_review_events_append_only') THEN
        CREATE TRIGGER lifecycle_review_events_append_only
        BEFORE UPDATE OR DELETE ON lifecycle_review_events
        FOR EACH ROW EXECUTE FUNCTION lifecycle_persistence_reject_mutation();
    END IF;
END;
$$;
