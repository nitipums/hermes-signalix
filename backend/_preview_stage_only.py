"""Preview: LAYER-1 ONLY — show the pure Stage 1-4 distribution (no groups,
no quality). This is what the stage scan should report before any layer-2
(action/group/quality) mapping. Read-only against Postgres.

Monkey-patches scan_universe to disable price/volume pre-filtering so we see
the full ORD universe classified by trend structure alone.
"""
import json
import collections
from unittest.mock import patch
from screening import scan_universe, classify_stage, MIN_DAYS
from stage_classifier import STAGE_LABELS, PHASE_LABELS

def _no_exclusion(df, min_price=None, min_today_trade_value=None):
    if df is None or len(df) < 2:
        return "insufficient_history"
    return None

with patch.object(__import__("screening"), "scan_exclusion_reason", _no_exclusion):
    results, _all = scan_universe(min_conditions=1, limit=None, market="TH",
                                  min_price=None, min_today_trade_value=None)

# Build evidence the same way group_scan_results does, but classify ONLY.
stage_counts = collections.Counter()
phase_counts = collections.Counter()
stage_examples = collections.defaultdict(list)
for row in results:
    trend = row.get("trend_template") or {}
    readiness = row.get("trade_readiness") or {}
    close = float(row.get("close") or 0)
    ma = (trend.get("ma") or {})
    evidence = {
        "close": close,
        "ma50": ma.get("ma50"), "ma150": ma.get("ma150"), "ma200": ma.get("ma200"),
        "above_ma50": readiness.get("above_ma50"),
        "above_ma150": readiness.get("above_ma150"),
        "above_ma200": readiness.get("above_ma200"),
        "ma50_slope_20d_pct": readiness.get("ma50_slope_20d_pct"),
        "ma150_slope_20d_pct": readiness.get("ma150_slope_20d_pct"),
        "ma200_slope_20d_pct": readiness.get("ma200_slope_20d_pct"),
        "macd": readiness.get("macd"),
        "rolling_trigger": readiness.get("breakout_level_20d"),
        "volume_ratio_50": readiness.get("volume_ratio_50"),
        "rsi_daily": readiness.get("rsi_daily"),
        "trend_template_conditions": trend.get("conditions_met"),
        "rs_rating": trend.get("rs_rating"),
        "rs_threshold": trend.get("rs_threshold"),
        "range_20d_pct": readiness.get("range_20d_pct"),
        "near_pullback_reference": readiness.get("near_buy_zone"),
        "vcp": (row.get("vcp") or {}).get("is_vcp", False),
        "readiness_status": readiness.get("status"),
    }
    state = classify_stage(evidence)
    st = state["stage"]
    ph = state["phase"]
    stage_counts[st] += 1
    phase_counts[(st, ph)] += 1
    if len(stage_examples[st]) < 8:
        stage_examples[st].append({
            "symbol": row["symbol"], "rs": trend.get("rs_rating"),
            "phase": ph, "phase_label": PHASE_LABELS.get(ph, ph),
        })

total = sum(stage_counts.values())
summary = {
    "total_classified": total,
    "stage_distribution": {STAGE_LABELS.get(k, k): v for k, v in stage_counts.most_common()},
    "stage_counts_raw": dict(stage_counts),
    "phase_breakdown": {f"{STAGE_LABELS.get(s,s)}/{PHASE_LABELS.get(p,p)}": c
                        for (s, p), c in phase_counts.most_common()},
    "examples": {STAGE_LABELS.get(k, k): [
        {"symbol": e["symbol"], "rs": e["rs"], "phase": e["phase_label"]} for e in v
    ] for k, v in stage_examples.items()},
}
with open("/root/signalix/backend/_preview_stage_only.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("=== LAYER-1 STAGE DISTRIBUTION (trend structure only) ===")
print("TOTAL:", total)
for k, v in stage_counts.most_common():
    print(f"  {STAGE_LABELS.get(k,k):22s} {v:5d}  ({100*v/total:.1f}%)")
print("\nPHASE breakdown:")
for (s, p), c in phase_counts.most_common():
    print(f"  {STAGE_LABELS.get(s,s):22s} / {PHASE_LABELS.get(p,p):18s} {c}")
print("\nExamples per stage (top by RS):")
for k, v in stage_examples.items():
    print(f"\n[{STAGE_LABELS.get(k,k)}]")
    for e in v[:4]:
        print(f"   - {e['symbol']:6s} RS={e['rs']:5.1f}  {e['phase_label']}")
print("\nWROTE /root/signalix/backend/_preview_stage_only.json")
