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


def summarize_sequence_ab(records):
    rows = list(records or [])
    shadow_present = 0
    pivot_comparable = 0
    pivot_divergence = 0
    state_divergence = 0
    v1_plans = 0
    v2_plans = 0
    v1_outcomes = Counter()
    v2_outcomes = Counter()
    v1_pre_entry = []
    v2_pre_entry = []
    low_cheat_observed = 0
    low_cheat_violations = 0
    for row in rows:
        shadow = row.get("sequence_policy_shadow_v2") or {}
        if not shadow:
            continue
        shadow_present += 1
        if shadow.get("low_cheat_observed"):
            low_cheat_observed += 1
        v1_pivot = (row.get("price") or {}).get("pivot_high")
        v2_pivot = (shadow.get("price") or {}).get("pivot_high")
        if v1_pivot is not None and v2_pivot is not None:
            pivot_comparable += 1
            if float(v1_pivot) != float(v2_pivot):
                pivot_divergence += 1
        if row.get("state") != shadow.get("state"):
            state_divergence += 1
        v1_plan = row.get("replay_trade_plan")
        v2_plan = row.get("sequence_v2_trade_plan")
        if v1_plan:
            v1_plans += 1
        if v2_plan:
            v2_plans += 1
            if (v2_plan.get("base_type") == "low_cheat_vcp"
                    or v2_plan.get("entry_profile") == "early_entry"):
                low_cheat_violations += 1
        v1_eval = row.get("replay_evaluation") or {}
        v2_eval = row.get("sequence_v2_replay_evaluation") or {}
        if v1_eval.get("outcome"):
            v1_outcomes[v1_eval["outcome"]] += 1
        if v2_eval.get("outcome"):
            v2_outcomes[v2_eval["outcome"]] += 1
        if v1_eval.get("pre_entry_bars") is not None:
            v1_pre_entry.append(float(v1_eval["pre_entry_bars"]))
        if v2_eval.get("pre_entry_bars") is not None:
            v2_pre_entry.append(float(v2_eval["pre_entry_bars"]))

    def stats(values):
        return {
            "count": len(values),
            "average": (sum(values) / len(values)) if values else None,
        }

    return {
        "records": len(rows),
        "shadow_present": shadow_present,
        "missing_shadow": len(rows) - shadow_present,
        "pivot_comparable": pivot_comparable,
        "pivot_divergence": pivot_divergence,
        "state_divergence": state_divergence,
        "v1_plan_count": v1_plans,
        "sequence_v2_plan_count": v2_plans,
        "v1_outcomes": dict(v1_outcomes),
        "sequence_v2_outcomes": dict(v2_outcomes),
        "v1_pre_entry_bars": stats(v1_pre_entry),
        "sequence_v2_pre_entry_bars": stats(v2_pre_entry),
        "low_cheat_observed": low_cheat_observed,
        "low_cheat_promotion_violations": low_cheat_violations,
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
        records = [row["result"] for row in cur.fetchall()]
        summary = summarize_shadow(records)
        summary["sequence_ab"] = summarize_sequence_ab(records)
        summary["replay_prefix"] = args.replay_prefix
        print(json.dumps(summary, sort_keys=True, default=str))
    finally:
        pg.close()


if __name__ == "__main__":
    main()
