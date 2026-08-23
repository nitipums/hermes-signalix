-- P0: Market Regime Persistence (Contract v0.2.0 §3.1)
--
-- Adds daily_market_regime: one row per scan run with the computed market regime
-- and all required inputs for audit/reproducibility.
--
-- Append-only: immutable via daily_scan_history_reject_mutation trigger.
-- FK to daily_scan_runs ensures regime is tied to a specific scan snapshot.

CREATE TABLE IF NOT EXISTS daily_market_regime (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES daily_scan_runs(id) ON DELETE RESTRICT,
    regime_state TEXT NOT NULL CHECK (regime_state IN (
        'HIGH_VOLATILITY', 'LIQUIDITY_EVENT', 'LOW_SPREAD', 'NORMAL'
    )),
    atr_pct_20d DOUBLE PRECISION,
    median_spread_bps DOUBLE PRECISION,
    liquidity_event_flag BOOLEAN,
    breadth_pct_above_ma50 DOUBLE PRECISION,
    benchmark_at_or_above_ma50 BOOLEAN,
    liquidity_event_reason_codes JSONB,
    reason_codes JSONB,
    policy_version TEXT NOT NULL,
    data_timestamp_utc TIMESTAMPTZ NOT NULL,
    computed_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(run_id)
);

CREATE INDEX IF NOT EXISTS daily_market_regime_run_id_idx ON daily_market_regime(run_id);
CREATE INDEX IF NOT EXISTS daily_market_regime_state_idx ON daily_market_regime(regime_state);
CREATE INDEX IF NOT EXISTS daily_market_regime_data_ts_idx ON daily_market_regime(data_timestamp_utc);

COMMENT ON TABLE daily_market_regime IS
    'Market regime computed per scan snapshot (Contract v0.2.0 regime-v0.2.0). '
    'One row per daily_scan_runs run. Contains the 4-state regime enum, '
    'all required inputs (V, S, L, B, M), reason_codes for invalid/missing inputs, '
    'policy_version, and UTC timestamps. Append-only via daily_scan_history_reject_mutation trigger.';

-- Attach mutation guard (reuse existing immutable trigger)
DROP TRIGGER IF EXISTS daily_market_regime_immutable ON daily_market_regime;
CREATE TRIGGER daily_market_regime_immutable
BEFORE UPDATE OR DELETE ON daily_market_regime
FOR EACH ROW EXECUTE FUNCTION daily_scan_history_reject_mutation();