# PATCH PREVIEW — build_dashboard.py (for Khim to apply)

The current `determine_action(group, ...)`, `plan(group, ...)`, and the
`serialize` lifecycle block switch on DEAD legacy group names (ready_validate,
retest_watch, avoid, ...) or on `daily_state.primary_state`. After the
stage-first change, the canonical key is `daily_state.phase` (and `stage`).
`group` is still a valid rollup, but action/plan/label must come from `phase`.

## A) determine_action — switch on phase, keep group fallback

Replace the `if group == ...` chain with a `phase`-first lookup. Suggested:

```python
def determine_action(group, readiness, snapshot, zones, phase=None):
    """Conservative next action — NOT a permission to trade.
    Phase (canonical) drives the action; group is a fallback only."""
    phase = phase or (readiness.get("_phase"))  # caller passes daily_state.phase
    rsi = readiness.get("rsi_daily")
    near = bool(readiness.get("near_buy_zone"))
    stop = readiness.get("stop_loss") or readiness.get("suggested_stop")
    cut = readiness.get("cut_level")
    close = snapshot.get("close")
    entry50, entry62 = zones.get("50"), zones.get("62")
    invalid = stop or cut

    if close is not None and invalid is not None:
        try:
            if float(close) <= float(invalid):
                return "INVALIDATED", "Price is at or below invalidation; remove this setup from the active plan."
        except (TypeError, ValueError):
            pass

    # --- Phase-driven (canonical) ---
    if phase in ("breakout_new",):
        return "VALIDATE FRESH BREAKOUT", "Fresh breakout; validate live price/liquidity before entry — not an entry signal."
    if phase == "breakout_extended":
        return "DO NOT CHASE", "Breakout extended from trigger or RSI; wait for a new base or controlled retest."
    if phase == "uptrend_pullback":
        return "HOLD IF SUPPORT DEFENDS", "In an uptrend pullback; require support defense and a higher low."
    if phase == "waiting_breakout":
        return "SET BREAKOUT ALERT", "Wait for a Daily close above the 20-day trigger with volume >= 1.2x."
    if phase == "base_tight":
        return "WATCH BASE", "Tight base / VCP; wait for a clean launch breakout."
    if phase in ("base_early",):
        return "WAIT", "Base forming; no qualified structure yet."
    if phase == "topping":
        return "AVOID CHASING", "Stage 3 distribution; protect gains, no new longs."
    if phase in ("declining", "broken"):
        return "NO LONG SETUP", "Stage 4 / broken structure; no qualified long until repair."

    # --- Group fallback (keeps current behaviour for rollups) ---
    if group == "avoid":
        return "AVOID NEW LONG", "Trend quality is weak. Reconsider only after the failed conditions improve."
    if rsi is not None and rsi >= 70 and group in {"uptrend_pullback", "waiting_breakout", "base"}:
        return "AVOID CHASING", f"RSI {rsi:.0f} is stretched; wait for a calm pullback or base."
    return "WAIT", "Wait for a defined setup and confirmation."
```

## B) plan() — same phase-first treatment
Mirror the phase keys above for the (label_a, value_a, label_b, value_b) tuple.
Keep `group` fallback for rollups that have no finer phase.

## C) serialize() — lifecycle badge from stage+phase
Replace the `primary_state` label map with stage/phase:

```python
    stage = (row.get("daily_state") or {}).get("stage")
    phase = (row.get("daily_state") or {}).get("phase")
    lifecycle = {
        "state": phase or "unclassified",
        "stage": stage or "none",
        "label": f"{(STAGE_LABELS.get(stage, stage))} · {(PHASE_LABELS.get(phase, phase))}",
        "fresh_opportunity": phase == "breakout_new",
        "extended": phase == "breakout_extended",
    }
```
And pass `phase` into `determine_action` / `plan`:
```python
    action, action_reason = determine_action(effective_group, readiness, decision_snapshot, zones, phase=phase)
    ...
    a_label, a_value, b_label, b_value = plan(effective_group, readiness, trend, decision_snapshot, phase=phase)
```

## D) Tests to update (Khim)
- `test_action_dashboard.py`: assertions on `groups["breakout_new"][0]["daily_state"]["origin"]`
  and `primary_state` → change to assert `phase` / `stage`.
- `test_scan_history.py` / `test_scan_history_integration.py`: `scan_group`
  "ready_validate" / "avoid" → use new groups (breakout_new / down_or_broken).
- `test_daily_setup_state.py`: still valid if kept; otherwise port to
  `stage_classifier` test suite (draft already has 12 passing).
