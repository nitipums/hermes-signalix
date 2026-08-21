"""Immutable PostgreSQL persistence for daily full-universe scan snapshots.

This module deliberately has no dependency on intraday tables/state.  A scan run
is append-only and each evaluated symbol receives one immutable observation.
"""
import datetime as dt
import json
import uuid


DEFAULT_SCANNER_VERSION = "signalix/full-scan-v1"
PRODUCTION_SCANNER_VERSION = "signalix/daily-state-v2"
BACKFILL_SCANNER_VERSION = "signalix/daily-state-v2-backfill"
BACKFILL_LOCK_KEY = 729100100

# All history consumers must select through these predicates/views.  In
# particular, a timestamp is only a tie-breaker *after* lineage and date have
# been constrained; it is never a definition of "latest".
CANONICAL_PRODUCTION_PREDICATE = """scanner_version = 'signalix/daily-state-v2'
    AND source_lineage->>'source' = 'price_data'
    AND COALESCE(source_lineage->>'mode', '') <> 'historical_backfill'"""
CANONICAL_BACKFILL_PREDICATE = """scanner_version = 'signalix/daily-state-v2-backfill'
    AND source_lineage->>'source' = 'price_data'
    AND source_lineage->>'mode' = 'historical_backfill'"""


def _json(value):
    """Serialize a JSONB payload deterministically without retaining references."""
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def _scan_date(results, explicit_date):
    if explicit_date is not None:
        if isinstance(explicit_date, dt.datetime):
            return explicit_date.date()
        if isinstance(explicit_date, dt.date):
            return explicit_date
        return dt.date.fromisoformat(str(explicit_date))
    for result in results:
        value = result.get("last_date")
        if value:
            return dt.date.fromisoformat(str(value)[:10])
    return dt.datetime.now(dt.timezone.utc).date()


def init_daily_scan_history_schema(pg):
    """Create append-only daily scan history tables and DB mutation guards."""
    cur = pg.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_scan_runs (
                id UUID PRIMARY KEY,
                scan_date DATE NOT NULL,
                run_timestamp TIMESTAMPTZ NOT NULL,
                scanner_version TEXT NOT NULL,
                source_lineage JSONB NOT NULL,
                retry_of_run_id UUID REFERENCES daily_scan_runs(id),
                retry_root_run_id UUID REFERENCES daily_scan_runs(id),
                evaluated_symbol_count INTEGER NOT NULL CHECK (evaluated_symbol_count >= 0),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            ALTER TABLE daily_scan_runs
            ADD COLUMN IF NOT EXISTS retry_root_run_id UUID REFERENCES daily_scan_runs(id)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_scan_observations (
                id UUID PRIMARY KEY,
                run_id UUID NOT NULL REFERENCES daily_scan_runs(id) ON DELETE RESTRICT,
                symbol TEXT NOT NULL,
                classification TEXT NOT NULL,
                classification_reason TEXT,
                conditions_met INTEGER,
                trend_template_pass BOOLEAN,
                rs_rating DOUBLE PRECISION,
                readiness_status TEXT,
                last_market_date DATE,
                raw_payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (run_id, symbol)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS daily_scan_observations_run_id_idx ON daily_scan_observations(run_id)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_analysis_snapshots (
                id UUID PRIMARY KEY,
                run_id UUID NOT NULL REFERENCES daily_scan_runs(id) ON DELETE RESTRICT,
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                analysis_date DATE NOT NULL,
                close DOUBLE PRECISION,
                volume DOUBLE PRECISION,
                ma20 DOUBLE PRECISION,
                ma50 DOUBLE PRECISION,
                ma150 DOUBLE PRECISION,
                ma200 DOUBLE PRECISION,
                max_20d DOUBLE PRECISION,
                min_20d DOUBLE PRECISION,
                max_52w DOUBLE PRECISION,
                min_52w DOUBLE PRECISION,
                rsi14 DOUBLE PRECISION,
                volume_ratio_50 DOUBLE PRECISION,
                trade_value DOUBLE PRECISION,
                rs_rating DOUBLE PRECISION,
                conditions_met INTEGER,
                scan_group TEXT,
                metrics JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (run_id, market, symbol)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS daily_analysis_snapshots_symbol_date_idx ON daily_analysis_snapshots(market, symbol, analysis_date DESC)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_symbol_ath_cache (
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                all_time_high DOUBLE PRECISION NOT NULL,
                prior_all_time_high DOUBLE PRECISION,
                latest_high DOUBLE PRECISION,
                last_seen_date DATE NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (market, symbol)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_breakout_events (
                id UUID PRIMARY KEY,
                symbol TEXT NOT NULL,
                origin TEXT NOT NULL,
                trigger_price NUMERIC(18,4) NOT NULL,
                qualified_on DATE NOT NULL,
                qualification_close DOUBLE PRECISION NOT NULL,
                qualification_volume_ratio DOUBLE PRECISION,
                pre_break_pivot_low NUMERIC(18,4) NOT NULL,
                failure_level NUMERIC(18,4) NOT NULL,
                trend_template_conditions INTEGER,
                rs_rating DOUBLE PRECISION,
                scan_run_id UUID NOT NULL REFERENCES daily_scan_runs(id) ON DELETE RESTRICT,
                scanner_version TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, qualified_on, trigger_price, scanner_version)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_breakout_event_observations (
                id UUID PRIMARY KEY,
                event_id UUID NOT NULL REFERENCES daily_breakout_events(id) ON DELETE RESTRICT,
                scan_run_id UUID NOT NULL REFERENCES daily_scan_runs(id) ON DELETE RESTRICT,
                observed_on DATE NOT NULL,
                stage TEXT NOT NULL,
                close DOUBLE PRECISION NOT NULL,
                distance_from_trigger_pct DOUBLE PRECISION,
                rsi_daily DOUBLE PRECISION,
                volume_ratio_50 DOUBLE PRECISION,
                failure_reason TEXT,
                raw_evidence JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(event_id, scan_run_id)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS daily_breakout_events_symbol_idx ON daily_breakout_events(symbol, qualified_on DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS daily_breakout_event_obs_event_idx ON daily_breakout_event_observations(event_id, observed_on DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS daily_scan_runs_scan_date_idx ON daily_scan_runs(scan_date, run_timestamp DESC)")
        # Immutable stage-transition log for the breakout event lifecycle.
        # Each row records from_stage -> to_stage for one event observation cycle,
        # attributed to the scan run that observed it. The event row holds the
        # original trigger_price / pre_break_pivot_low / failure_level; this table
        # records the observation-level stage progression (fresh->extended->
        # broken->failed etc.). Idempotent on (event_id, to_stage, observed_on,
        # scan_run_id); append-only via the shared daily_scan_history_reject_mutation
        # trigger added below.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_breakout_event_stage_transitions (
               -- immutable trigger function: daily_scan_history_reject_mutation
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
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS daily_breakout_event_stage_transitions_event_idx ON daily_breakout_event_stage_transitions(event_id, observed_on DESC, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS daily_breakout_event_stage_transitions_scan_run_idx ON daily_breakout_event_stage_transitions(scan_run_id)")
        # Intraday emerging events: append-only, lower confidence, reconciled by EOD
        cur.execute("""
            CREATE TABLE IF NOT EXISTS intraday_events (
                id UUID PRIMARY KEY,
                symbol TEXT NOT NULL,
                origin TEXT NOT NULL,
                trigger_price NUMERIC(18,4) NOT NULL,
                first_seen TIMESTAMPTZ NOT NULL,
                first_candle_ts TIMESTAMPTZ NOT NULL,
                interval TEXT NOT NULL,
                qualification_close DOUBLE PRECISION,
                qualification_volume_ratio DOUBLE PRECISION,
                pre_break_pivot_low NUMERIC(18,4),
                failure_level NUMERIC(18,4),
                trend_template_conditions INTEGER,
                rs_rating DOUBLE PRECISION,
                intraday_run_id TEXT REFERENCES intraday_ingestion_runs(run_id) ON DELETE SET NULL,
                source_lineage JSONB NOT NULL DEFAULT '{}',
                confidence TEXT NOT NULL DEFAULT 'emerging' CHECK (confidence IN ('emerging','confirmed','expired','invalidated','not_confirmed')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, first_candle_ts, trigger_price, interval)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS intraday_event_observations (
                id UUID PRIMARY KEY,
                event_id UUID NOT NULL REFERENCES intraday_events(id) ON DELETE RESTRICT,
                intraday_run_id TEXT REFERENCES intraday_ingestion_runs(run_id) ON DELETE SET NULL,
                observed_at TIMESTAMPTZ NOT NULL,
                candle_ts TIMESTAMPTZ NOT NULL,
                stage TEXT NOT NULL,
                close DOUBLE PRECISION NOT NULL,
                distance_from_trigger_pct DOUBLE PRECISION,
                rsi_daily DOUBLE PRECISION,
                volume_ratio_50 DOUBLE PRECISION,
                failure_reason TEXT,
                raw_evidence JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(event_id, intraday_run_id)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS intraday_events_symbol_idx ON intraday_events(symbol, first_candle_ts DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS intraday_events_confidence_idx ON intraday_events(confidence, first_candle_ts DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS intraday_event_obs_event_idx ON intraday_event_observations(event_id, observed_at DESC)")
        # P0-4 hardenings: daily-event lineage, candle-level observation dedup,
        # and append-only mutation guards on the intraday side.
        # (a) Lineage link to the official Daily baseline once EOD confirms.
        cur.execute("""
            ALTER TABLE intraday_events
            ADD COLUMN IF NOT EXISTS resolved_daily_event_id UUID REFERENCES daily_breakout_events(id) ON DELETE SET NULL
        """)
        cur.execute("""
            ALTER TABLE intraday_events
            ADD COLUMN IF NOT EXISTS reconciled_at TIMESTAMPTZ
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS intraday_events_resolved_idx ON intraday_events(resolved_daily_event_id)")
        # (b) Observation uniqueness must be per candle, not per ingestion run:
        #     the old UNIQUE(event_id, intraday_run_id) never fired because
        #     intraday_run_id was NULL for evaluator-written rows.
        cur.execute("""
            ALTER TABLE intraday_event_observations
            DROP CONSTRAINT IF EXISTS intraday_event_observations_event_id_intraday_run_id_key
        """)
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'intraday_event_obs_event_candle_unique'
                ) THEN
                    ALTER TABLE intraday_event_observations
                    ADD CONSTRAINT intraday_event_obs_event_candle_unique UNIQUE (event_id, candle_ts);
                END IF;
            END $$;
        """)
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS intraday_event_obs_event_candle_uniq_idx ON intraday_event_observations(event_id, candle_ts)")
        # (c) Append-only guards. Daily rows are already fully immutable.  The
        #     intraday event row is append-only EXCEPT the confidence lifecycle
        #     columns that only the EOD reconciler may transition; observations
        #     are fully immutable.
        cur.execute("""
            CREATE OR REPLACE FUNCTION intraday_event_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'intraday events are append-only; deleting is not allowed';
                END IF;
                IF NEW.confidence IS DISTINCT FROM OLD.confidence
                   OR NEW.resolved_daily_event_id IS DISTINCT FROM OLD.resolved_daily_event_id
                   OR NEW.reconciled_at IS DISTINCT FROM OLD.reconciled_at THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'intraday event rows are immutable except confidence lifecycle fields';
            END;
            $$ LANGUAGE plpgsql
        """)
        cur.execute("""
            CREATE OR REPLACE FUNCTION intraday_event_observation_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'intraday event observations are immutable';
            END;
            $$ LANGUAGE plpgsql
        """)
        for table, fn in (("intraday_events", "intraday_event_reject_mutation"),
                          ("intraday_event_observations", "intraday_event_observation_reject_mutation")):
            cur.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
            cur.execute(f"""
                CREATE TRIGGER {table}_append_only
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION {fn}()
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_scan_run_selection_audit (
                run_id UUID PRIMARY KEY REFERENCES daily_scan_runs(id) ON DELETE RESTRICT,
                selection_status TEXT NOT NULL CHECK (selection_status IN ('selected','quarantined','legacy','excluded')),
                reason TEXT NOT NULL,
                audited_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        # Existing installations predate the four-way audit vocabulary.
        cur.execute("ALTER TABLE daily_scan_run_selection_audit DROP CONSTRAINT IF EXISTS daily_scan_run_selection_audit_selection_status_check")
        cur.execute("ALTER TABLE daily_scan_run_selection_audit ADD CONSTRAINT daily_scan_run_selection_audit_selection_status_check CHECK (selection_status IN ('selected','quarantined','legacy','excluded'))")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_breakout_event_observation_selection_audit (
                observation_id UUID PRIMARY KEY REFERENCES daily_breakout_event_observations(id) ON DELETE RESTRICT,
                selection_status TEXT NOT NULL CHECK (selection_status IN ('selected','quarantined')),
                reason TEXT NOT NULL,
                audited_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        # Audit every immutable raw run.  The window/tie-break is deliberately
        # repeated in each CASE so the result is deterministic and reproducible.
        # Legacy and excluded rows remain visible in the audit, but can never
        # enter a canonical projection.
        cur.execute(f"""
            INSERT INTO daily_scan_run_selection_audit(run_id, selection_status, reason)
            SELECT r.id,
              CASE
                WHEN r.scanner_version NOT IN ('signalix/daily-state-v2','signalix/daily-state-v2-backfill') THEN 'legacy'
                WHEN r.scan_date = DATE '2026-08-14' AND r.scanner_version='signalix/daily-state-v2-backfill' THEN 'quarantined'
                WHEN r.source_lineage->>'source' <> 'price_data' THEN 'excluded'
                WHEN r.scanner_version='signalix/daily-state-v2-backfill'
                  AND r.source_lineage->>'mode'='historical_backfill'
                  AND ROW_NUMBER() OVER (PARTITION BY r.scanner_version,r.scan_date ORDER BY r.run_timestamp DESC,r.id DESC) > 1 THEN 'quarantined'
                WHEN r.scanner_version='signalix/daily-state-v2-backfill'
                  AND r.source_lineage->>'mode'='historical_backfill'
                  AND r.source_lineage->'evaluated_market_dates' IS NOT NULL
                  AND (r.source_lineage->'evaluated_market_dates'->>0)::date <> r.scan_date THEN 'quarantined'
                WHEN r.scanner_version IN ('signalix/daily-state-v2','signalix/daily-state-v2-backfill') THEN 'selected'
                ELSE 'excluded'
              END,
              CASE
                WHEN r.scanner_version NOT IN ('signalix/daily-state-v2','signalix/daily-state-v2-backfill') THEN 'legacy_scanner_version_excluded_from_canonical'
                WHEN r.scan_date = DATE '2026-08-14' AND r.scanner_version='signalix/daily-state-v2-backfill' THEN 'extra_current_date_backfill'
                WHEN r.source_lineage->>'source' <> 'price_data' THEN 'source_lineage_not_price_data'
                WHEN r.scanner_version='signalix/daily-state-v2-backfill' AND ROW_NUMBER() OVER (PARTITION BY r.scanner_version,r.scan_date ORDER BY r.run_timestamp DESC,r.id DESC) > 1 THEN 'duplicate_backfill_run'
                WHEN r.scanner_version='signalix/daily-state-v2-backfill' AND r.source_lineage->'evaluated_market_dates' IS NOT NULL AND (r.source_lineage->'evaluated_market_dates'->>0)::date <> r.scan_date THEN 'scan_date_evaluated_market_date_mismatch'
                WHEN r.scanner_version='signalix/daily-state-v2' THEN 'canonical_production_lineage'
                ELSE 'canonical_tie_break_run_timestamp_desc_id_desc'
              END
            FROM daily_scan_runs r
            ON CONFLICT (run_id) DO UPDATE SET selection_status=EXCLUDED.selection_status, reason=EXCLUDED.reason, audited_at=NOW()
        """)
        cur.execute("""
            CREATE OR REPLACE VIEW daily_scan_run_audit_coverage AS
            SELECT (SELECT COUNT(*) FROM daily_scan_runs) AS raw_count,
                   (SELECT COUNT(*) FROM daily_scan_run_selection_audit) AS audited_count,
                   (SELECT COUNT(*) FROM daily_scan_runs r JOIN daily_scan_run_selection_audit a ON a.run_id=r.id) AS joined_count
        """)
        cur.execute("""
            CREATE OR REPLACE VIEW daily_canonical_scan_runs AS
            SELECT r.*
            FROM daily_scan_runs r
            JOIN daily_scan_run_selection_audit a ON a.run_id=r.id
            WHERE a.selection_status='selected'
              AND ((r.scanner_version='signalix/daily-state-v2'
                    AND r.source_lineage->>'source'='price_data'
                    AND COALESCE(r.source_lineage->>'mode','') <> 'historical_backfill')
                OR (r.scanner_version='signalix/daily-state-v2-backfill'
                    AND r.source_lineage->>'source'='price_data'
                    AND r.source_lineage->>'mode'='historical_backfill'))
        """ )
        cur.execute("""
            INSERT INTO daily_breakout_event_observation_selection_audit(observation_id, selection_status, reason)
            SELECT o.id, 'quarantined', 'observed_on_run_scan_date_mismatch'
            FROM daily_breakout_event_observations o
            JOIN daily_scan_runs r ON r.id=o.scan_run_id
            WHERE o.observed_on <> r.scan_date
            ON CONFLICT (observation_id) DO NOTHING
        """)
        cur.execute("""
            CREATE OR REPLACE VIEW daily_canonical_breakout_event_observations AS
            SELECT o.*
            FROM daily_breakout_event_observations o
            JOIN daily_canonical_scan_runs r ON r.id=o.scan_run_id
            LEFT JOIN daily_breakout_event_observation_selection_audit a ON a.observation_id=o.id
            WHERE COALESCE(a.selection_status,'selected')='selected'
              AND o.observed_on=r.scan_date
        """)
        cur.execute("""
            CREATE OR REPLACE VIEW daily_canonical_breakout_events AS
            SELECT e.*
            FROM daily_breakout_events e
            JOIN daily_canonical_scan_runs r ON r.id=e.scan_run_id
        """)
        cur.execute("""
            CREATE OR REPLACE FUNCTION daily_scan_history_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'daily scan history is immutable';
            END;
            $$ LANGUAGE plpgsql
        """)
        for table in ("daily_scan_runs", "daily_scan_observations", "daily_analysis_snapshots", "daily_breakout_events", "daily_breakout_event_observations", "daily_breakout_event_stage_transitions"):
            cur.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
            cur.execute(f"""
                CREATE TRIGGER {table}_immutable
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION daily_scan_history_reject_mutation()
            """)
        pg.commit()
    except Exception:
        pg.rollback()
        raise
    finally:
        cur.close()


def _normalized_fields(result):
    trend = result.get("trend_template") or {}
    readiness = result.get("trade_readiness") or {}
    last_date = result.get("last_date")
    return {
        "classification": str(result.get("scan_group") or "unclassified"),
        "classification_reason": result.get("group_reason"),
        "conditions_met": trend.get("conditions_met"),
        "trend_template_pass": trend.get("pass"),
        "rs_rating": trend.get("rs_rating"),
        "readiness_status": readiness.get("status"),
        "last_market_date": dt.date.fromisoformat(str(last_date)[:10]) if last_date else None,
    }


def _retry_root_run_id(cur, retry_of_run_id):
    """Resolve a retry root from its explicit parent, never timestamp/order."""
    if retry_of_run_id is None:
        return None, None
    try:
        parent_id = str(uuid.UUID(str(retry_of_run_id)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("retry_of_run_id must be a UUID of an existing run") from exc
    cur.execute(
        """SELECT COALESCE(retry_root_run_id, id)
           FROM daily_scan_runs WHERE id = %s""",
        (parent_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError("retry_of_run_id does not reference an existing run")
    return parent_id, str(row[0])


def persist_daily_scan_snapshot(
    pg,
    results,
    *,
    scan_date=None,
    scanner_version=DEFAULT_SCANNER_VERSION,
    source_lineage=None,
    retry_of_run_id=None,
    run_timestamp=None,
):
    """Append one immutable run and an observation for every evaluated result.

    ``results`` must be the complete evaluator output, not the filtered delivery
    candidate list.  No upsert is used: a rerun always creates a new run UUID.
    """
    if results is None:
        raise ValueError("results must be an iterable of evaluated symbol payloads")
    results = list(results)
    symbols = [str(row.get("symbol") or "").upper() for row in results]
    if not all(symbols):
        raise ValueError("every scan observation requires a symbol")
    if len(set(symbols)) != len(symbols):
        raise ValueError("a scan run may contain each symbol only once")

    run_id = str(uuid.uuid4())
    timestamp = run_timestamp or dt.datetime.now(dt.timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
    date_value = _scan_date(results, scan_date)
    lineage = source_lineage or {"source": "price_data", "freshness": "unspecified"}

    cur = pg.cursor()
    original_autocommit = getattr(pg, "autocommit", None)
    transactional = isinstance(original_autocommit, bool) and original_autocommit
    if transactional:
        pg.autocommit = False
    try:
        retry_parent_id, retry_root_id = _retry_root_run_id(cur, retry_of_run_id)
        cur.execute(
            """INSERT INTO daily_scan_runs
               (id, scan_date, run_timestamp, scanner_version, source_lineage,
                retry_of_run_id, retry_root_run_id, evaluated_symbol_count)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (run_id, date_value, timestamp, scanner_version, _json(lineage), retry_parent_id,
             retry_root_id, len(results)),
        )
        for result, symbol in zip(results, symbols):
            normalized = _normalized_fields(result)
            cur.execute(
                """INSERT INTO daily_scan_observations
                   (id, run_id, symbol, classification, classification_reason,
                    conditions_met, trend_template_pass, rs_rating, readiness_status,
                    last_market_date, raw_payload)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (str(uuid.uuid4()), run_id, symbol, normalized["classification"],
                 normalized["classification_reason"], normalized["conditions_met"],
                 normalized["trend_template_pass"], normalized["rs_rating"],
                 normalized["readiness_status"], normalized["last_market_date"], _json(result)),
            )
            metrics = result.get("analysis_metrics") or {}
            trend = result.get("trend_template") or {}
            ma = trend.get("ma") or {}
            cur.execute(
                """INSERT INTO daily_analysis_snapshots
                   (id, run_id, market, symbol, analysis_date, close, volume,
                    ma20, ma50, ma150, ma200, max_20d, min_20d, max_52w,
                    min_52w, rsi14, volume_ratio_50, trade_value, rs_rating,
                    conditions_met, scan_group, metrics)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (str(uuid.uuid4()), run_id, str(result.get("market") or "TH"), symbol,
                 normalized["last_market_date"], result.get("close"), metrics.get("volume"),
                 metrics.get("ma20"), metrics.get("ma50", ma.get("ma50")),
                 metrics.get("ma150", ma.get("ma150")), metrics.get("ma200", ma.get("ma200")),
                 metrics.get("max_20d"), metrics.get("min_20d"),
                 metrics.get("max_52w", ma.get("hi_52")), metrics.get("min_52w", ma.get("lo_52")),
                 metrics.get("rsi14"), metrics.get("volume_ratio_50"), metrics.get("trade_value"),
                 normalized["rs_rating"], normalized["conditions_met"],
                 normalized["classification"], _json(metrics)),
            )
        pg.commit()
    except Exception:
        pg.rollback()
        raise
    finally:
        cur.close()
        if transactional:
            pg.autocommit = original_autocommit
    return {
        "run_id": run_id,
        "scan_date": date_value.isoformat(),
        "run_timestamp": timestamp.isoformat(),
        "observation_count": len(results),
        "retry_of_run_id": retry_parent_id,
        "retry_root_run_id": retry_root_id,
    }


def active_breakout_events(pg):
    """Return the latest non-failed immutable event per symbol for Daily classification."""
    cur = pg.cursor()
    try:
        cur.execute("""
            SELECT DISTINCT ON (e.symbol)
                e.symbol,e.id,e.trigger_price,e.origin,e.pre_break_pivot_low,
                e.qualified_on,
                (SELECT COUNT(DISTINCT r.scan_date) FROM daily_canonical_scan_runs r
                   WHERE r.scan_date > e.qualified_on) AS age_sessions,
                o.stage,o.failure_reason
            FROM daily_canonical_breakout_events e
            LEFT JOIN LATERAL (
                SELECT stage,failure_reason FROM daily_canonical_breakout_event_observations
 WHERE event_id=e.id ORDER BY observed_on DESC, created_at DESC LIMIT 1
 ) o ON TRUE
 JOIN daily_canonical_scan_runs er ON er.id=e.scan_run_id
            ORDER BY e.symbol,e.qualified_on DESC,e.created_at DESC,e.id DESC
        """)
        out = {}
        for symbol, event_id, trigger, origin, pivot, qualified_on, age, stage, reason in cur.fetchall():
            if stage == "failed":
                continue
            out[symbol] = {"event_id": str(event_id), "trigger_price": float(trigger), "origin": origin,
                           "pivot_low": float(pivot), "age_sessions": int(age or 0),
                           "qualified_on": str(qualified_on)}
        return out
    finally:
        cur.close()


def breakout_event_lifecycle(pg, event_id):
    """Return the immutable lifecycle timeline for a single breakout event.

    Includes the event row (original trigger / pivot / failure_level), all
    observations in chronological order, and all recorded stage transitions
    (from_stage -> to_stage).  This is a read-only projection over append-only
    tables; no rows are ever mutated.
    """
    cur = pg.cursor()
    try:
        cur.execute("""
            SELECT e.symbol, e.origin, e.trigger_price, e.qualified_on,
                   e.qualification_close, e.pre_break_pivot_low, e.failure_level,
                   e.rs_rating, e.scan_run_id, e.created_at
            FROM daily_breakout_events e
            WHERE e.id = %s
        """, (str(event_id),))
        ev = cur.fetchone()
        if ev is None:
            return None
        event = {
            "symbol": ev[0], "origin": ev[1], "trigger_price": float(ev[2]),
            "qualified_on": str(ev[3]), "qualification_close": float(ev[4]) if ev[4] else None,
            "pivot_low": float(ev[5]), "failure_level": float(ev[6]),
            "rs_rating": float(ev[7]) if ev[7] else None,
            "scan_run_id": str(ev[8]), "created_at": ev[9].isoformat(),
        }
        cur.execute("""
            SELECT o.observed_on, o.stage, o.close, o.distance_from_trigger_pct,
                   o.rsi_daily, o.volume_ratio_50, o.failure_reason, o.scan_run_id
            FROM daily_breakout_event_observations o
            WHERE o.event_id = %s
            ORDER BY o.observed_on ASC, o.created_at ASC
        """, (str(event_id),))
        observations = [
            {"observed_on": str(r[0]), "stage": r[1], "close": float(r[2]),
             "distance_from_trigger_pct": float(r[3]) if r[3] else None,
             "rsi_daily": float(r[4]) if r[4] else None,
             "volume_ratio_50": float(r[5]) if r[5] else None,
             "failure_reason": r[6], "scan_run_id": str(r[7])}
            for r in cur.fetchall()
        ]
        cur.execute("""
            SELECT t.from_stage, t.to_stage, t.observed_on, t.close,
                   t.distance_from_trigger_pct, t.failure_reason, t.scan_run_id
            FROM daily_breakout_event_stage_transitions t
            WHERE t.event_id = %s
            ORDER BY t.observed_on ASC, t.created_at ASC
        """, (str(event_id),))
        transitions = [
            {"from_stage": r[0], "to_stage": r[1], "observed_on": str(r[2]),
             "close": float(r[3]), "distance_from_trigger_pct": float(r[4]) if r[4] else None,
             "failure_reason": r[5], "scan_run_id": str(r[6])}
            for r in cur.fetchall()
        ]
        return {"event": event, "observations": observations, "transitions": transitions}
    finally:
        cur.close()


def persist_breakout_lifecycle(pg, results, run_id, scanner_version):
    """Append new events/observations; never update historical lifecycle rows."""
    cur = pg.cursor()
    created = observed = transitions = 0
    try:
        # The owning run is the authority for observation date.  This prevents
        # a stale/mislabelled evaluator payload from creating new mismatches.
        cur.execute("SELECT scan_date FROM daily_scan_runs WHERE id=%s", (run_id,))
        run_row = cur.fetchone()
        if run_row is None:
            raise ValueError(f"unknown scan run {run_id}")
        run_scan_date = run_row[0]
        for row in results:
            state = row.get("daily_state") or {}
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            tr = row.get("trade_readiness") or {}
            scan_date = run_scan_date
            event_id = (row.get("active_breakout_event") or {}).get("event_id")
            if event_id:
                cur.execute("SELECT id FROM daily_breakout_events WHERE id=%s", (str(event_id),))
                found = cur.fetchone()
                event_id = str(found[0]) if found else None
            # New stage-first classifier: phase == "breakout_new" indicates fresh breakout
            # Legacy: primary_state == "fresh_breakout"
            is_fresh_breakout = (state.get("phase") == "breakout_new"
                                 or state.get("primary_state") == "fresh_breakout"
                                 or row.get("scan_group") == "breakout_new")
            if is_fresh_breakout and not event_id:
                trigger = state.get("reference_level") or tr.get("breakout_level_20d")
                pivot = tr.get("pre_break_pivot_low")
                if pivot is None:
                    # A malformed candidate must not abort persistence for the
                    # complete scan. Keep it dashboard-visible, but do not
                    # create an immutable lifecycle event without its pivot.
                    continue
                failure = state.get("failure_level") or tr.get("stop_loss") or tr.get("suggested_stop") or pivot
                cur.execute("""
                    INSERT INTO daily_breakout_events
                    (id,symbol,origin,trigger_price,qualified_on,qualification_close,qualification_volume_ratio,
                     pre_break_pivot_low,failure_level,trend_template_conditions,rs_rating,scan_run_id,scanner_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(symbol,qualified_on,trigger_price,scanner_version) DO NOTHING
                    RETURNING id
                """, (str(uuid.uuid4()), symbol, state.get("origin") or "unknown", str(trigger), scan_date,
                      float(row.get("close")), tr.get("volume_ratio_50"), str(pivot), str(failure),
                      (row.get("trend_template") or {}).get("conditions_met"),
                      (row.get("trend_template") or {}).get("rs_rating"), run_id, scanner_version))
                returned = cur.fetchone()
                if returned:
                    event_id = str(returned[0]); created += 1
                else:
                    cur.execute("SELECT id FROM daily_breakout_events WHERE symbol=%s AND qualified_on=%s AND trigger_price=%s AND scanner_version=%s", (symbol, scan_date, str(trigger), scanner_version))
                    found = cur.fetchone(); event_id = str(found[0]) if found else None
            if event_id:
                trigger = float(state.get("reference_level") or tr.get("breakout_level_20d") or (row.get("active_breakout_event") or {}).get("trigger_price"))
                distance = float(row.get("close")) / trigger - 1 if trigger else None
                current_stage = state.get("stage") or state.get("phase") or "fresh"
                # Record the observation (idempotent: one per event+run).
                cur.execute("""
                    INSERT INTO daily_breakout_event_observations
                    (id,event_id,scan_run_id,observed_on,stage,close,distance_from_trigger_pct,rsi_daily,volume_ratio_50,failure_reason,raw_evidence)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(event_id,scan_run_id) DO NOTHING
                """, (str(uuid.uuid4()), event_id, run_id, scan_date, current_stage,
                      float(row.get("close")), distance, tr.get("rsi_daily"), tr.get("volume_ratio_50"),
                      state.get("failure_reason"), _json({"daily_state": state, "readiness": tr})))
                observed += int(cur.rowcount or 0)
                # Record stage transition: compare current stage against the most
                # recent preceding observation stage for this event.  Only the
                # first observation in a given stage+date emits a transition row
                # (idempotent via UNIQUE(event_id, to_stage, observed_on, scan_run_id)).
                cur.execute("""
                    SELECT stage FROM daily_breakout_event_observations
                    WHERE event_id=%s AND scan_run_id<>%s
                    ORDER BY observed_on DESC, created_at DESC LIMIT 1
                """, (event_id, run_id))
                prev = cur.fetchone()
                from_stage = prev[0] if prev else None
                if from_stage != current_stage:
                    cur.execute("""
                        INSERT INTO daily_breakout_event_stage_transitions
                        (id,event_id,from_stage,to_stage,observed_on,close,
                         distance_from_trigger_pct,scan_run_id,failure_reason,raw_evidence)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(event_id,to_stage,observed_on,scan_run_id) DO NOTHING
                    """, (str(uuid.uuid4()), event_id, from_stage, current_stage, scan_date,
                          float(row.get("close")), distance, run_id,
                          state.get("failure_reason"), _json({"daily_state": state, "readiness": tr})))
                    transitions += int(cur.rowcount or 0)
        pg.commit()
        return {"events_created": created, "observations_appended": observed, "transitions_recorded": transitions}
    except Exception:
        pg.rollback()
        raise
    finally:
        cur.close()


# ============================================================
# Intraday emerging events — append-only, lower confidence
# EOD scan owns final class; reconciles earlier events as
# confirmed/expired/invalidated/not_confirmed.
# ============================================================

def persist_intraday_events(pg, events, *, intraday_run_id=None, source_lineage=None):
    """Append intraday emerging events and their observations.

    ``events`` is a list of dicts from intraday_evaluator with keys:
      - symbol, origin, trigger_price, first_candle_ts, interval
      - qualification_close, qualification_volume_ratio (optional)
      - pre_break_pivot_low, failure_level (optional)
      - trend_template_conditions, rs_rating (optional)
      - observations: list of {candle_ts, stage, close, distance_from_trigger_pct,
        rsi_daily, volume_ratio_50, failure_reason, raw_evidence}

    Each run creates new rows; no upsert on events (append-only).
    Observations are deduped by (event_id, intraday_run_id).
    """
    if not events:
        return {"events_created": 0, "observations_appended": 0}

    lineage = source_lineage or {"source": "intraday_evaluator", "freshness": "unspecified"}

    cur = pg.cursor()
    original_autocommit = getattr(pg, "autocommit", None)
    transactional = isinstance(original_autocommit, bool) and original_autocommit
    if transactional:
        pg.autocommit = False
    try:
        created = 0
        observed = 0
        for ev in events:
            symbol = str(ev.get("symbol") or "").upper()
            if not symbol:
                continue
            trigger = ev.get("trigger_price")
            if trigger is None:
                continue
            trigger_f = float(trigger)
            interval = ev.get("interval") or "60m"
            event_id = None
            # Reuse an ACTIVE emerging/confirmed event for the same breakout
            # cycle (symbol + trigger within tolerance + interval).  Without
            # this, every candle that stays above the trigger fabricates a new
            # event and the table explodes with near-identical rows.
            cur.execute("""
                SELECT id FROM intraday_events
                WHERE symbol=%s AND interval=%s
                  AND confidence IN ('emerging','confirmed')
                  AND ABS(trigger_price - %s) <= %s * 0.005
                ORDER BY first_candle_ts ASC, created_at ASC
                LIMIT 1
            """, (symbol, interval, trigger_f, trigger_f))
            active = cur.fetchone()
            if active:
                event_id = str(active[0])
            else:
                event_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO intraday_events
                    (id, symbol, origin, trigger_price, first_seen, first_candle_ts, interval,
                     qualification_close, qualification_volume_ratio, pre_break_pivot_low,
                     failure_level, trend_template_conditions, rs_rating,
                     intraday_run_id, source_lineage)
                    VALUES (%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(symbol, first_candle_ts, trigger_price, interval) DO NOTHING
                    RETURNING id
                """, (
                    event_id, symbol, ev.get("origin") or "intraday", str(trigger),
                    ev.get("first_candle_ts"), interval,
                    ev.get("qualification_close"), ev.get("qualification_volume_ratio"),
                    ev.get("pre_break_pivot_low"), ev.get("failure_level"),
                    ev.get("trend_template_conditions"), ev.get("rs_rating"),
                    intraday_run_id, _json(lineage),
                ))
                returned = cur.fetchone()
                if returned:
                    created += 1
                else:
                    # Race: an identical row was inserted concurrently.
                    cur.execute("""
                        SELECT id FROM intraday_events
                        WHERE symbol=%s AND first_candle_ts=%s AND trigger_price=%s AND interval=%s
                    """, (symbol, ev.get("first_candle_ts"), str(trigger), interval))
                    found = cur.fetchone()
                    if found:
                        event_id = str(found[0])
                    else:
                        continue

            # Append observations for this event (one row per candle).
            for obs in ev.get("observations") or []:
                candle_ts = obs.get("candle_ts")
                if candle_ts is None:
                    continue
                cur.execute("""
                    INSERT INTO intraday_event_observations
                    (id, event_id, intraday_run_id, observed_at, candle_ts, stage, close,
                     distance_from_trigger_pct, rsi_daily, volume_ratio_50, failure_reason, raw_evidence)
                    VALUES (%s,%s,%s,NOW(),%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(event_id, candle_ts) DO NOTHING
                """, (
                    str(uuid.uuid4()), event_id, intraday_run_id,
                    candle_ts, obs.get("stage"), obs.get("close"),
                    obs.get("distance_from_trigger_pct"), obs.get("rsi_daily"),
                    obs.get("volume_ratio_50"), obs.get("failure_reason"),
                    _json(obs.get("raw_evidence") or {}),
                ))
                observed += int(cur.rowcount or 0)
        pg.commit()
        return {"events_created": created, "observations_appended": observed}
    except Exception:
        pg.rollback()
        raise
    finally:
        cur.close()
        if transactional:
            pg.autocommit = original_autocommit


def reconcile_intraday_events_at_eod(pg, daily_run_id, scanner_version, symbols=None):
    """EOD reconciliation: promote intraday emerging events to Daily events.

    For each intraday event with confidence='emerging' for the given symbols,
    check if the EOD scan confirms it (fresh_breakout with matching trigger).
    If confirmed -> create daily_breakout_event + observations, mark intraday event 'confirmed'.
    If expired/no match -> mark intraday event 'expired' or 'not_confirmed'.
    If invalidated (below failure_level) -> mark intraday event 'invalidated'.

    This is called from the EOD scan after persist_daily_scan_snapshot.
    """
    cur = pg.cursor()
    try:
        # Get the scan date of the owning EOD run
        cur.execute("SELECT scan_date FROM daily_scan_runs WHERE id=%s", (daily_run_id,))
        run_row = cur.fetchone()
        if run_row is None:
            raise ValueError(f"unknown daily scan run {daily_run_id}")
        scan_date = run_row[0]

        # Build a map of EOD breakout events from today's scan
        cur.execute("""
            SELECT e.id, e.symbol, e.trigger_price, e.origin, e.pre_break_pivot_low,
                   e.failure_level, e.qualified_on, e.qualification_close, e.qualification_volume_ratio,
                   e.trend_template_conditions, e.rs_rating
            FROM daily_breakout_events e
            WHERE e.scan_run_id = %s
        """, (daily_run_id,))
        eod_events = {}
        for row in cur.fetchall():
            eid, sym, trigger, origin, pivot, failure, qual_on, qual_close, qual_vol, tt_cond, rs = row
            eod_events[sym] = {
                "event_id": str(eid), "trigger_price": float(trigger), "origin": origin,
                "pivot_low": float(pivot), "failure_level": float(failure),
                "qualified_on": qual_on, "qualification_close": float(qual_close),
                "qualification_volume_ratio": qual_vol,
                "trend_template_conditions": tt_cond, "rs_rating": rs,
            }

        # Find intraday emerging events for these symbols (or all if symbols=None).
        # Only 'emerging' rows are reconciled; already-finalized rows are
        # left untouched (idempotent by construction).
        where = "confidence = 'emerging'"
        params = []
        if symbols:
            placeholders = ",".join(["%s"] * len(symbols))
            where += f" AND symbol IN ({placeholders})"
            params = [s.upper() for s in symbols]
        cur.execute(f"""
            SELECT id, symbol, trigger_price, first_candle_ts, failure_level, pre_break_pivot_low, intraday_run_id
            FROM intraday_events
            WHERE {where}
            ORDER BY symbol, first_candle_ts
        """, params)
        intraday_emerging = cur.fetchall()

        promoted = 0
        expired = 0
        invalidated = 0
        not_confirmed = 0

        for ev_id, symbol, trigger, first_candle_ts, failure_level, pivot_low, run_id in intraday_emerging:
            trigger_f = float(trigger)
            eod = eod_events.get(symbol)

            # Check if EOD confirmed this breakout (same trigger ±0.5%)
            if eod and abs(eod["trigger_price"] - trigger_f) / trigger_f <= 0.005:
                # Confirmed: link the intraday event to the official Daily event
                # that owns the final class, and record when reconciliation ran.
                cur.execute("""
                    UPDATE intraday_events
                    SET confidence='confirmed', resolved_daily_event_id=%s, reconciled_at=NOW()
                    WHERE id=%s
                """, (eod["event_id"], ev_id))
                promoted += 1
            elif eod:
                # EOD has a breakout for this symbol but different trigger -> not_confirmed
                cur.execute("""
                    UPDATE intraday_events
                    SET confidence='not_confirmed', resolved_daily_event_id=NULL, reconciled_at=NOW()
                    WHERE id=%s
                """, (ev_id,))
                not_confirmed += 1
            else:
                # No EOD breakout for this symbol today
                # Check if intraday price action invalidated (below failure level)
                cur.execute("""
                    SELECT close FROM intraday_event_observations
                    WHERE event_id=%s ORDER BY observed_at DESC LIMIT 1
                """, (ev_id,))
                latest_obs = cur.fetchone()
                if latest_obs and failure_level is not None:
                    latest_close = float(latest_obs[0])
                    if latest_close <= float(failure_level):
                        cur.execute("""
                            UPDATE intraday_events
                            SET confidence='invalidated', resolved_daily_event_id=NULL, reconciled_at=NOW()
                            WHERE id=%s
                        """, (ev_id,))
                        invalidated += 1
                        continue
                # Otherwise expired (no EOD confirmation, not invalidated)
                cur.execute("""
                    UPDATE intraday_events
                    SET confidence='expired', resolved_daily_event_id=NULL, reconciled_at=NOW()
                    WHERE id=%s
                """, (ev_id,))
                expired += 1

        pg.commit()
        return {
            "promoted": promoted, "expired": expired,
            "invalidated": invalidated, "not_confirmed": not_confirmed,
        }
    except Exception:
        pg.rollback()
        raise
    finally:
        cur.close()


def get_active_intraday_events(pg, confidence=None):
    """Return active intraday events (for dashboard overlay)."""
    cur = pg.cursor()
    try:
        where = "confidence IN ('emerging','confirmed')"
        params = []
        if confidence:
            where = "confidence = %s"
            params = [confidence]
        cur.execute(f"""
            SELECT DISTINCT ON (symbol)
                id, symbol, origin, trigger_price, first_seen, first_candle_ts, interval,
                confidence, failure_level, pre_break_pivot_low, intraday_run_id,
                resolved_daily_event_id, reconciled_at
            FROM intraday_events
            WHERE {where}
            ORDER BY symbol, first_candle_ts DESC
        """, params)
        out = {}
        for row in cur.fetchall():
            ev_id, symbol, origin, trigger, first_seen, first_candle, interval, conf, failure, pivot, run_id, resolved, reconciled = row
            out[symbol] = {
                "event_id": str(ev_id), "origin": origin, "trigger_price": float(trigger),
                "first_seen": first_seen.isoformat() if first_seen else None,
                "first_candle_ts": first_candle.isoformat() if first_candle else None,
                "interval": interval, "confidence": conf,
                "failure_level": float(failure) if failure else None,
                "pivot_low": float(pivot) if pivot else None,
                "intraday_run_id": str(run_id) if run_id else None,
                "resolved_daily_event_id": str(resolved) if resolved else None,
                "reconciled_at": reconciled.isoformat() if reconciled else None,
            }
        return out
    finally:
        cur.close()
