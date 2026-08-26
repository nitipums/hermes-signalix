-- Historical, normalized SET index membership.
-- The legacy index_membership table remains for backward compatibility while
-- callers migrate to this table.
CREATE TABLE IF NOT EXISTS index_memberships (
    symbol         TEXT NOT NULL,
    index_name     TEXT NOT NULL, -- SET50, SET100, SET50FF, SET100FF
    effective_from DATE NOT NULL,
    effective_to   DATE,
    source         TEXT NOT NULL,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, index_name, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_index_memberships_current
    ON index_memberships (index_name, effective_from, effective_to);
