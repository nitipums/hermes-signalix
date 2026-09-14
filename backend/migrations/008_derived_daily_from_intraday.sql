BEGIN;

-- Derived Daily fallback storage.
-- Source is Settrade 60m; rows are never official Daily evidence.
CREATE TABLE IF NOT EXISTS derived_daily_price_data (
    symbol TEXT NOT NULL,
    session_date DATE NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL,
    source_timeframe TEXT NOT NULL,
    derivation_method TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    source_first_ts TIMESTAMPTZ NOT NULL,
    source_last_ts TIMESTAMPTZ NOT NULL,
    source_completion_cutoff TIMESTAMPTZ,
    source_bar_count INTEGER NOT NULL,
    is_official BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, session_date, source, source_timeframe)
);

CREATE INDEX IF NOT EXISTS derived_daily_price_data_symbol_date_idx
    ON derived_daily_price_data (symbol, session_date DESC);

ALTER TABLE derived_daily_price_data
    ADD COLUMN IF NOT EXISTS source_completion_cutoff TIMESTAMPTZ;

ALTER TABLE derived_daily_price_data
    DROP CONSTRAINT IF EXISTS derived_daily_price_data_official_false_ck;
ALTER TABLE derived_daily_price_data
    ADD CONSTRAINT derived_daily_price_data_official_false_ck
    CHECK (is_official = FALSE);

-- Existing rows are trusted only when their persisted source timestamps prove
-- the exact complete Bangkok session.  The 16:00 candle is complete at 17:00
-- ICT; do not infer completion for malformed or partial legacy rows.
UPDATE derived_daily_price_data
SET source_completion_cutoff =
    ((session_date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok'),
    derivation_method = 'settrade_60m_complete_bangkok_session_ohlcv_v1'
WHERE source_completion_cutoff IS NULL
  AND source = 'settrade'
  AND source_timeframe = '60m'
  AND source_bar_count = 8
  AND derivation_method IN (
      'settrade_60m_complete_bangkok_session_ohlcv_v1',
      'OHLCV_SESSION_AGGREGATE'
  )
  AND (source_first_ts AT TIME ZONE 'Asia/Bangkok')::date = session_date
  AND (source_last_ts AT TIME ZONE 'Asia/Bangkok')::date = session_date
  AND (source_first_ts AT TIME ZONE 'Asia/Bangkok')::time = TIME '09:00'
  AND (source_last_ts AT TIME ZONE 'Asia/Bangkok')::time = TIME '16:00';

ALTER TABLE derived_daily_price_data
    DROP CONSTRAINT IF EXISTS derived_daily_price_data_completion_ck;
ALTER TABLE derived_daily_price_data
    ADD CONSTRAINT derived_daily_price_data_completion_ck
    CHECK (source_completion_cutoff IS NULL OR
           source_completion_cutoff >= source_last_ts);

COMMIT;
