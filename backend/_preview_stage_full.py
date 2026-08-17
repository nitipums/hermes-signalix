"""Preview v2: run stage-first classifier on the FULL ORD universe with NO
price/volume pre-filtering (per Arm's layering rule: trend = layer 1, quality
= layer 2+). Read-only against Postgres; writes JSON only.

This monkey-patches scan_universe's exclusion so we can SEE the full distribution
before changing production code.
"""
import json
import collections
from unittest.mock import patch
from screening import scan_universe, group_scan_results, scan_exclusion_reason, MIN_DAYS
from stage_classifier import STAGE_LABELS, PHASE_LABELS

# Force NO pre-scan price/volume exclusion (layer-1 = trend only).
def _no_exclusion(df, min_price=None, min_today_trade_value=None):
    if df is None or len(df) < 2:
        return "insufficient_history"
    return None

with patch.object(__import__("screening"), "scan_exclusion_reason", _no_exclusion):
    # min_price=None + min_today_trade_value=None disables the SQL-side filter too.
    results, _all = scan_universe(min_conditions=1, limit=None, market="TH",
                                  min_price=None, min_today_trade_value=None)

groups = group_scan_results(results)
dist = {k: len(v) for k, v in groups.items()}
total = sum(dist.values())

summary = {"total_symbols_classified": total, "group_distribution": dist, "samples": {}}
for key, rows in groups.items():
    rows_sorted = sorted(rows, key=lambda r: r["trend_template"]["rs_rating"], reverse=True)
    stage_phase = collections.Counter()
    for r in rows_sorted:
        ds = r.get("daily_state") or {}
        stage_phase[(ds.get("stage"), ds.get("phase"))] += 1
    sample = [{
        "symbol": r["symbol"], "rs": r["trend_template"]["rs_rating"],
        "met": r["trend_template"]["conditions_met"],
        "stage": (r.get("daily_state") or {}).get("stage"),
        "phase": (r.get("daily_state") or {}).get("phase"),
    } for r in rows_sorted[:6]]
    summary["samples"][key] = {
        "count": len(rows_sorted),
        "stage_phase_breakdown": {f"{s}/{p}": c for (s, p), c in stage_phase.most_common()},
        "top_by_rs": sample,
    }

with open("/root/signalix/backend/_preview_stage_full.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("TOTAL CLASSIFIED (no price/volume filter):", total)
for k, v in sorted(dist.items(), key=lambda x: -x[1]):
    print(f"  {k:18s} {v:5d}  ({100*v/total:.1f}%)")
print("\nSTAGE/PHASE per group:")
for key, blk in summary["samples"].items():
    print(f"\n[{key}] count={blk['count']}")
    for sp, c in blk["stage_phase_breakdown"].items():
        print(f"   {sp:30s} {c}")
print("\nWROTE /root/signalix/backend/_preview_stage_full.json")
