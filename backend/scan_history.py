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
        cur.execute("ALTER TABLE daily_scan_run_selection_audit DROP CONSTRAINT IF EXISTS daily_scan_run_selection_audit_selection_status_check")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_scan_run_selection_audit (
                run_id UUID PRIMARY KEY REFERENCES daily_scan_runs(id) ON DELETE RESTRICT,
                selection_status TEXT NOT NULL CHECK (selection_status IN ('selected','quarantined','legacy','excluded')),
                reason TEXT NOT NULL,
                audited_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        # Existing installations predate the four-way audit vocabulary.
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
        for table in ("daily_scan_runs", "daily_scan_observations", "daily_analysis_snapshots", "daily_breakout_events", "daily_breakout_event_observations"):
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


def persist_breakout_lifecycle(pg, results, run_id, scanner_version):
    """Append new events/observations; never update historical lifecycle rows."""
    cur = pg.cursor()
    created = observed = 0
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
            if state.get("primary_state") == "fresh_breakout" and not event_id:
                trigger = state.get("reference_level")
                pivot = tr.get("pre_break_pivot_low")
                if pivot is None:
                    raise ValueError(f"fresh breakout {symbol} missing required pre_break_pivot_low")
                failure = state.get("failure_level") or pivot
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
                trigger = float(state.get("reference_level") or (row.get("active_breakout_event") or {}).get("trigger_price"))
                distance = float(row.get("close")) / trigger - 1 if trigger else None
                cur.execute("""
                    INSERT INTO daily_breakout_event_observations
                    (id,event_id,scan_run_id,observed_on,stage,close,distance_from_trigger_pct,rsi_daily,volume_ratio_50,failure_reason,raw_evidence)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(event_id,scan_run_id) DO NOTHING
                """, (str(uuid.uuid4()), event_id, run_id, scan_date, state.get("stage") or "fresh",
                      float(row.get("close")), distance, tr.get("rsi_daily"), tr.get("volume_ratio_50"),
                      state.get("failure_reason"), _json({"daily_state": state, "readiness": tr})))
                observed += cur.rowcount
        pg.commit()
        return {"events_created": created, "observations_appended": observed}
    except Exception:
        pg.rollback()
        raise
    finally:
        cur.close()
