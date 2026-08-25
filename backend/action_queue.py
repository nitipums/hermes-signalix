"""P1 Action Queue Redesign (t_69ff91c2): canonical 7-queue projection.

Deterministic, presentation-layer queue assignment over the canonical
stage-first classifier (stage_classifier.py) + setup_state.py quality/proximity.
Never changes FULL ORD scan coverage: every item maps to exactly one queue.

Queues (canonical, t_69ff91c2):
  intraday_emerging  Intraday Emerging   — active append-only emerging event
  fresh_breakout     Fresh Breakout      — new breakout + quality pass
  pre_breakout       Pre-breakout        — near trigger/pivot + quality pass
  retest_watch       Retest Watch        — qualified breakout in retest window
                                         (event-driven lane; setup_quality NOT
                                         required — active event w/ trigger
                                         price is the R3 qualification)
  qualified_pullback Qualified Pullback  — pullback at/near reference + quality pass
  monitor_only       Monitor Only        — everything watchable but not actionable
                                         (incl. extended DO-NOT-CHASE, base
                                         forming, weak quality)
  avoid_new_longs    Avoid New Longs     — S3/S4, broken/declining

Hard rule (t_69ff91c2): recovery/base/weak generic labels never enter an
actionable queue. Actionable queues are exactly:
  {fresh_breakout, pre_breakout, retest_watch, qualified_pullback}
plus the event-driven intraday_emerging. Base/recovery states land in
monitor_only until they independently satisfy a stage+quality+proximity gate.
"""
from __future__ import annotations

ACTIONABLE_QUEUES = (
    "intraday_emerging", "fresh_breakout", "pre_breakout",
    "retest_watch", "qualified_pullback",
)
NON_ACTIONABLE_QUEUES = ("monitor_only", "avoid_new_longs")

QUEUE_LABELS = {
    "intraday_emerging": "Intraday Emerging",
    "fresh_breakout": "Fresh Breakout",
    "pre_breakout": "Pre-breakout",
    "retest_watch": "Retest Watch",
    "qualified_pullback": "Qualified Pullback",
    "monitor_only": "Monitor Only",
    "avoid_new_longs": "Avoid New Longs",
}


def _event_is_active_emerging(event) -> bool:
    """Only an active emerging/confirmed intraday event qualifies."""
    if not isinstance(event, dict):
        return False
    status = event.get("status")
    if status is not None and status != "active":
        return False
    return event.get("confidence") in ("emerging", "confirmed")


# Canonical v0.2.0 legacy display terms. They MUST NOT be emitted by the
# canonical API/UI except under an explicit `legacy_alias` field.
LEGACY_PROXIMITY_ALIASES = {
    "action": "READY",
    "near_trigger": "NEAR TRIGGER",
    "forming": "FORMING",
    "extended": "EXTENDED",
}

# Explicit data-block reason codes (contract section 4.1 hard blocks).
DATA_BLOCK_INSUFFICIENT = "DATA_MISSING_REQUIRED"
DATA_BLOCK_STALE = "DATA_STALE"


def assign_action_queue(stage, phase, quality_pass, proximity_state,
                        intraday_event=None) -> str:
    """Map one canonical item to exactly one action queue."""
    # R3 qualified-retest hard gate: evaluated FIRST so a confirmed
    # breakout-retest event lands in retest_watch, not the emerging-event
    # lane. The qualification is the persisted event/provenance evidence
    # (an active event carrying its original trigger price); setup_quality
    # does NOT gate retest_watch — the event evidence IS the gate, the same
    # way intraday_emerging keeps its own event-driven lane. The phase label
    # alone never qualifies.
    if phase == "breakout_retest":
        # Hard gate: require active event with trigger_price
        if isinstance(intraday_event, dict) and intraday_event.get("trigger_price") is not None and intraday_event.get("status") in (None, "active"):
            return "retest_watch"
        return "monitor_only"


    # 0) Active emerging event wins (append-only evidence, independent lane).
    if _event_is_active_emerging(intraday_event):
        return "intraday_emerging"

    # 1) Risk stages/phases => Avoid New Longs (never actionable).
    if stage in ("S3_distributing", "S4_down") or phase in ("broken", "declining"):
        return "avoid_new_longs"

    quality_pass = bool(quality_pass)

    # 2) Stage 2 phases.
    if stage == "S2_uptrend":
        if phase == "breakout_extended":
            return "monitor_only"          # DO NOT CHASE
        if phase == "breakout_new":
            return "fresh_breakout" if quality_pass else "monitor_only"
        if phase == "waiting_breakout":
            if quality_pass and proximity_state in ("near_trigger", "action"):
                return "pre_breakout"
            return "monitor_only"
        if phase == "uptrend_pullback":
            if quality_pass and proximity_state in ("near_trigger", "action"):
                return "qualified_pullback"
            return "monitor_only"
        return "monitor_only"

    # 3) Stage 1 basing: only a tight base near a real trigger is pre-breakout;
    #    generic base/recovery labels stay non-actionable.
    if stage == "S1_basing":
        if phase == "base_tight" and quality_pass \
                and proximity_state in ("near_trigger", "action"):
            return "pre_breakout"
        return "monitor_only"

    # 4) Unknown/insufficient data: explicit non-actionable state, never a
    #    silent Avoid New Longs (missing data is not a risk verdict).
    return "monitor_only"


def queue_label(queue: str) -> str:
    return QUEUE_LABELS.get(queue, queue)
