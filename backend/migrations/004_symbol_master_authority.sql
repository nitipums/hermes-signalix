-- P0-2: Authoritative active-ORD instrument master.
--
-- `symbol_master` is the single source of truth for the SET/mai ordinary-share
-- universe. The weekly `signalix-settrade-master` timer calls
-- `sync_settrade_master.sync_db` to (re)seed EVERY taxonomy column from
-- Settrade's official stock-list JSON. Symbols absent from the official list
-- are marked `inactive`; manually excluded symbols are marked `excluded`.
--
-- This migration is idempotent (CREATE TABLE IF NOT EXISTS + ADD COLUMN IF NOT
-- EXISTS) and matches the existing production schema exactly, so it is safe to
-- apply against a live DB without data loss or lock contention.
CREATE TABLE IF NOT EXISTS symbol_master (
    symbol           TEXT PRIMARY KEY,
    instrument_type  TEXT NOT NULL,                       -- 'ORD' | 'DR' | ...
    status           TEXT NOT NULL DEFAULT 'active',     -- active | inactive | excluded | delisted
    reason           TEXT,                                -- human-readable status reason
    marked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    venue            TEXT,                                -- SET | MAI (primary listing segment)
    asset_class      TEXT,                                -- equity (taxonomy authority)
    currency         TEXT,                                -- THB (taxonomy authority)
    timezone         TEXT,                                -- Asia/Bangkok (taxonomy authority)
    session          TEXT,                                -- SET (session calendar authority)
    source           TEXT,                                -- e.g. settrade_stock_master
    freshness        TEXT                                 -- fresh | stale | unknown
);

-- Partial index the active-ORD universe: this is the only path the scanner,
-- intraday fetch, and dashboard join against. Non-active rows stay indexed
-- only for the /symbols/excluded audit endpoint.
CREATE INDEX IF NOT EXISTS idx_symbol_master_active_lookup
    ON symbol_master (instrument_type, status)
    WHERE (instrument_type = 'ORD' AND (status IS NULL OR status = 'active'));

CREATE INDEX IF NOT EXISTS idx_symbol_master_freshness
    ON symbol_master (freshness) WHERE freshness IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_symbol_master_venue
    ON symbol_master (venue) WHERE venue IS NOT NULL;

COMMENT ON TABLE symbol_master IS
    'Authoritative active-ORD instrument master. Seeded weekly from the '
    'Settrade stock-list JSON (sync_settrade_master.sync_db). Venue, asset '
    'class, currency, timezone and session are taxonomy authority fields; '
    'Yahoo company_profiles is a non-authoritative fallback, never a price '
    'or signal input.';
