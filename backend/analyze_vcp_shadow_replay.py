"""Read-only summary for persisted VCP decision-shadow replay records."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter

import psycopg2
import psycopg2.extras


ACTION_LANES = {"REVIEW_NOW", "PREPARE"}


def summarize_shadow(records):
    rows = list(records or [])
    lanes = Counter()
    tradability = Counter()
    missing_evidence = Counter()
    outcomes = Counter()
    state_lane = Counter()
    contradictions = Counter({
        "extended_in_action_lane": 0,
        "failed_in_action_lane": 0,
        "event_watch_actionable": 0,
        "data_blocked_actionable": 0,
    })
    shadow_records = 0
    for row in rows:
        shadow = row.get("decision_shadow_v2") or {}
        if not shadow:
            continue
        shadow_records += 1
        state = shadow.get("lifecycle_state") or row.get("state") or "NOT_VERIFIED"
        lane = shadow.get("decision_lane") or "DATA_BLOCKED"
        actionability = shadow.get("actionability") or "NO_ACTION"
        lanes[lane] += 1
        state_lane[f"{state}->{lane}"] += 1
        passes = bool((shadow.get("tradability") or {}).get("passes_default_filters"))
        tradability["default_pass" if passes else "default_fail"] += 1
        for reason in (shadow.get("quality") or {}).get("failing_evidence") or []:
            missing_evidence[str(reason)] += 1
        evaluation = row.get("replay_evaluation") or {}
        outcomes[evaluation.get("outcome") or "NOT_VERIFIED"] += 1
        if state == "EXTENDED" and lane in ACTION_LANES:
            contradictions["extended_in_action_lane"] += 1
        if state == "FAILED" and lane in ACTION_LANES:
            contradictions["failed_in_action_lane"] += 1
        if lane == "EVENT_WATCH" and actionability == "ACTIONABLE_REVIEW":
            contradictions["event_watch_actionable"] += 1
        if lane == "DATA_BLOCKED" and actionability != "NO_ACTION":
            contradictions["data_blocked_actionable"] += 1
    return {
        "records": len(rows),
        "shadow_records": shadow_records,
        "missing_shadow": len(rows) - shadow_records,
        "lane_counts": dict(lanes),
        "actionability_counts": dict(Counter(
            (row.get("decision_shadow_v2") or {}).get("actionability")
            for row in rows if row.get("decision_shadow_v2")
        )),
        "tradability": {
            "default_pass": tradability["default_pass"],
            "default_fail": tradability["default_fail"],
        },
        "state_lane_matrix": dict(state_lane),
        "missing_evidence": dict(missing_evidence),
        "outcomes": dict(outcomes),
        "contradictions": dict(contradictions),
    }


def _pg_args():
    return {
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "signalix"),
        "password": os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
        "dbname": os.getenv("POSTGRES_DB", "signalix"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-prefix", required=True)
    args = parser.parse_args()
    pg = psycopg2.connect(**_pg_args())
    try:
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """SELECT result
               FROM vcp_finder_60m_replay_results
               WHERE replay_id LIKE %s
               ORDER BY replay_id, symbol""",
            (args.replay_prefix + "%",),
        )
        summary = summarize_shadow([row["result"] for row in cur.fetchall()])
        summary["replay_prefix"] = args.replay_prefix
        print(json.dumps(summary, sort_keys=True, default=str))
    finally:
        pg.close()


if __name__ == "__main__":
    main()
