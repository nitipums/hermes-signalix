"""Preview: run the NEW stage-first classifier over the real DB universe.

Read-only against Postgres. Writes a JSON summary only — never mutates prod.
"""
import json
import collections
from screening import scan_universe, group_scan_results
from stage_classifier import STAGE_LABELS, PHASE_LABELS

# Scan full TH universe (min_conditions=1 so we see EVERY symbol's stage, not
# just qualified trends). This exercises the classifier end-to-end.
results, _all = scan_universe(min_conditions=1, limit=None, market="TH")

groups = group_scan_results(results)

# Distribution
dist = {k: len(v) for k, v in groups.items()}
total = sum(dist.values())

# Per-group sample (top by RS) + stage/phase breakdown inside each group
summary = {
    "total_symbols_classified": total,
    "group_distribution": dist,
    "samples": {},
}
for key, rows in groups.items():
    rows_sorted = sorted(rows, key=lambda r: r["trend_template"]["rs_rating"], reverse=True)
    stage_phase = collections.Counter()
    for r in rows_sorted:
        ds = r.get("daily_state") or {}
        stage_phase[(ds.get("stage"), ds.get("phase"))] += 1
    sample = []
    for r in rows_sorted[:8]:
        ds = r.get("daily_state") or {}
        sample.append({
            "symbol": r["symbol"],
            "rs": r["trend_template"]["rs_rating"],
            "met": r["trend_template"]["conditions_met"],
            "stage": ds.get("stage"),
            "phase": ds.get("phase"),
            "stage_label": ds.get("stage_label"),
            "phase_label": ds.get("phase_label"),
            "group_reason": r.get("group_reason"),
        })
    summary["samples"][key] = {
        "count": len(rows_sorted),
        "stage_phase_breakdown": {f"{s}/{p}": c for (s, p), c in stage_phase.most_common()},
        "top_by_rs": sample,
    }

with open("/root/signalix/backend/_preview_stage_groups.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

# Console summary
print("TOTAL CLASSIFIED:", total)
print("DISTRIBUTION:")
for k, v in sorted(dist.items(), key=lambda x: -x[1]):
    print(f"  {k:18s} {v:5d}  ({100*v/total:.1f}%)")
print("\nSTAGE/PHASE breakdown per group:")
for key, blk in summary["samples"].items():
    print(f"\n[{key}] count={blk['count']}")
    for sp, c in blk["stage_phase_breakdown"].items():
        print(f"   {sp:30s} {c}")
    for s in blk["top_by_rs"][:4]:
        print(f"   - {s['symbol']:6s} RS={s['rs']:5.1f} met={s['met']} {s['stage']}/{s['phase']}")
print("\nWROTE /root/signalix/backend/_preview_stage_groups.json")
