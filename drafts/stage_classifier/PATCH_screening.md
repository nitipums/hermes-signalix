# PATCH PREVIEW — screening.py (for Khim to apply)

## 1) DELETE the legacy duplicate `group_scan_results` (lines ~348-401)
The first definition uses dead group names (ready_validate, retest_watch, ...).
Python keeps the second (v2) silently, so this is dead code that misleads
reviewers and is referenced by stale tests. Remove the ENTIRE first function:

```python
def group_scan_results(results):
    """Build an action-first queue; each group tells the user what to do next."""
    groups = {
        "ready_validate": [], "retest_watch": [], "near_breakout": [], "pullback_watch": [],
        "breakout_watch": [], "recovery_watch": [], "speculative_reversal": [],
        "base_building": [], "avoid": [],
    }
    ...
    return groups
```

## 2) UPDATE the remaining (v2) `group_scan_results` to use stage classifier

Replace the function body's `classify_daily_state(evidence, ...)` call and the
group-mapping block with the stage-first classifier. Minimal diff:

```python
from stage_classifier import classify_stage   # NEW import (or keep daily_setup_state too)

# inside group_scan_results(results, events=None):
        # --- NEW: single canonical stage/phase classification ---
        state = classify_stage(evidence, events.get(row["symbol"]))
        if row.get("last_date") and evidence.get("latest_scan_date") and row["last_date"] != evidence["latest_scan_date"]:
            state["data_freshness"] = "stale"
        phase = state["phase"]
        stage = state["stage"]
        # One level-one dashboard group derived from (stage, phase).
        if stage == "S2_uptrend" and phase in ("breakout_new", "breakout_extended"):
            key = "breakout_new"
        elif stage == "S2_uptrend" and phase == "uptrend_pullback":
            key = "uptrend_pullback"
        elif stage == "S2_uptrend" and phase in ("waiting_breakout",):
            key = "waiting_breakout"
        elif stage == "S1_basing":
            key = "base"
        elif stage in ("S3_distributing", "S4_down") or phase in ("broken", "declining"):
            key = "down_or_broken"
        else:
            key = "waiting_breakout"
        row["daily_state"] = state
        row["scan_group"] = key
        row["group_reason"] = f"{state['stage_label']} · {state['phase_label']}"
        groups[key].append(row)
```

NOTE: `evidence` dict is unchanged — it already carries every key
`classify_stage` needs (close, ma200, ma200_slope_20d_pct, above_ma200,
rolling_trigger, volume_ratio_50, rsi_daily, trend_template_conditions,
range_20d_pct, near_pullback_reference, vcp). Add `readiness_status` if you
want the BUY/HOLD hint carried through (optional, display-only).
