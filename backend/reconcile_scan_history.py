"""Generate a live raw-to-canonical Signalix reconciliation report."""
import datetime as dt
import json
import os
from pathlib import Path
import psycopg2

OUT = Path(__file__).with_name("reconciliation_report.json")

def fetch(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()

def main():
    conn = psycopg2.connect(os.environ.get("DATABASE_URL", "dbname=signalix user=signalix host=postgres password=signalix_pass"))
    try:
        cur = conn.cursor()
        pairs = fetch(cur, """
            SELECT 'raw_runs',count(*) FROM daily_scan_runs
            UNION ALL SELECT 'audited_runs',count(*) FROM daily_scan_run_selection_audit
            UNION ALL SELECT 'selected_runs',count(*) FROM daily_scan_run_selection_audit WHERE selection_status='selected'
            UNION ALL SELECT 'quarantined_runs',count(*) FROM daily_scan_run_selection_audit WHERE selection_status='quarantined'
            UNION ALL SELECT 'legacy_runs',count(*) FROM daily_scan_run_selection_audit WHERE selection_status='legacy'
            UNION ALL SELECT 'excluded_runs',count(*) FROM daily_scan_run_selection_audit WHERE selection_status='excluded'
            UNION ALL SELECT 'canonical_runs',count(*) FROM daily_canonical_scan_runs
            UNION ALL SELECT 'canonical_events',count(*) FROM daily_canonical_breakout_events
            UNION ALL SELECT 'canonical_observations',count(*) FROM daily_canonical_breakout_event_observations
        """)
        counts = {k: int(v) for k, v in pairs}
        status_reasons = [{"status": s, "reason": r, "count": int(n)} for s, r, n in fetch(cur, "SELECT selection_status,reason,count(*) FROM daily_scan_run_selection_audit GROUP BY 1,2 ORDER BY 1,2")]
        dates = [str(row[0]) for row in fetch(cur, "SELECT DISTINCT scan_date FROM daily_canonical_scan_runs ORDER BY scan_date")]
        mismatch = fetch(cur, """
            SELECT count(*) FILTER (WHERE o.last_market_date <> r.scan_date), count(DISTINCT r.id) FILTER (WHERE o.last_market_date <> r.scan_date)
            FROM daily_scan_runs r LEFT JOIN daily_scan_observations o ON o.run_id=r.id
        """)[0]
        event_mismatch = fetch(cur, """
            SELECT count(*) FROM daily_breakout_event_observations o JOIN daily_scan_runs r ON r.id=o.scan_run_id WHERE o.observed_on <> r.scan_date
        """)[0][0]
        source_mismatch = fetch(cur, """
            SELECT count(*) FROM daily_scan_runs
            WHERE source_lineage->'evaluated_market_dates' IS NOT NULL
              AND (source_lineage->'evaluated_market_dates'->>0)::date <> scan_date
        """)[0][0]
        gpsc_raw_dates = [str(row[0]) for row in fetch(cur, "SELECT DISTINCT last_market_date FROM daily_scan_observations WHERE symbol='GPSC' ORDER BY 1")]
        gpsc_lifecycle = fetch(cur, """
            SELECT e.symbol,e.qualified_on,
              (SELECT count(DISTINCT r.scan_date) FROM daily_canonical_scan_runs r WHERE r.scan_date > e.qualified_on) AS age_sessions,
              o.stage,o.failure_reason
            FROM daily_canonical_breakout_events e
            LEFT JOIN LATERAL (SELECT stage,failure_reason FROM daily_canonical_breakout_event_observations WHERE event_id=e.id ORDER BY observed_on DESC LIMIT 1) o ON true
            WHERE e.symbol='GPSC' ORDER BY e.qualified_on DESC
        """)
        reps = [list(map(str, row)) for row in fetch(cur, "SELECT symbol,count(*) FROM daily_canonical_breakout_events GROUP BY symbol ORDER BY count(*) DESC,symbol LIMIT 10")]
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "scope": "live PostgreSQL immutable daily_scan_runs and canonical projections",
            "counts": counts,
            "audit_coverage": {"raw_equals_audited": counts["raw_runs"] == counts["audited_runs"], "raw_equals_joined": counts["raw_runs"] == int(fetch(cur, "SELECT joined_count FROM daily_scan_run_audit_coverage")[0][0])},
            "event_observation_audit": {"raw_event_observations": int(fetch(cur, "SELECT count(*) FROM daily_breakout_event_observations")[0][0]), "audited_event_observations": int(fetch(cur, "SELECT count(*) FROM daily_breakout_event_observation_selection_audit")[0][0]), "quarantined_date_mismatch": int(fetch(cur, "SELECT count(*) FROM daily_breakout_event_observation_selection_audit WHERE reason='observed_on_run_scan_date_mismatch'")[0][0])},
            "audit_status_reasons": status_reasons,
            "canonical_historical_dates": dates,
            "mismatch_rows": {"observation_last_market_date_vs_run_date": int(mismatch[0] or 0), "runs_with_observation_date_mismatch": int(mismatch[1] or 0), "event_observed_on_vs_run_date": int(event_mismatch), "runs_with_source_evaluated_date_mismatch": int(source_mismatch)},
            "representative_event_symbols": reps,
            "GPSC": {"raw_scan_observations": int(fetch(cur, "SELECT count(*) FROM daily_scan_observations WHERE symbol='GPSC'")[0][0]), "raw_event_observations": int(fetch(cur, "SELECT count(*) FROM daily_breakout_event_observations o JOIN daily_breakout_events e ON e.id=o.event_id WHERE e.symbol='GPSC'")[0][0]), "raw_event_observation_dates": [str(row[0]) for row in fetch(cur, "SELECT DISTINCT o.observed_on FROM daily_breakout_event_observations o JOIN daily_breakout_events e ON e.id=o.event_id WHERE e.symbol='GPSC' ORDER BY 1")], "raw_scan_observation_dates": gpsc_raw_dates, "canonical_events": int(fetch(cur, "SELECT count(*) FROM daily_canonical_breakout_events WHERE symbol='GPSC'")[0][0]), "canonical_observations": int(fetch(cur, "SELECT count(*) FROM daily_canonical_breakout_event_observations o JOIN daily_canonical_breakout_events e ON e.id=o.event_id WHERE e.symbol='GPSC'")[0][0]), "lifecycle": [list(map(str, row)) for row in gpsc_lifecycle]},
            "claims_not_supported": ["GPSC lifecycle age 122→57 is not supported by current raw/canonical rows"],
        }
        OUT.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    finally:
        conn.close()

if __name__ == "__main__":
    main()
