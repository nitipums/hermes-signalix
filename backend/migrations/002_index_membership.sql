CREATE TABLE IF NOT EXISTS index_membership (
    symbol         TEXT PRIMARY KEY,
    index_name     TEXT NOT NULL,
    is_set50       BOOLEAN NOT NULL DEFAULT FALSE,
    effective_from DATE,
    source         TEXT,
    fetched_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_index_membership_set50 ON index_membership (is_set50);
