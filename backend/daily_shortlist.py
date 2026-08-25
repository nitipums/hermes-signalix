"""Task 2: Deterministic Daily Shortlist eligibility and ranking policy.

Pure module — no DB, no clock, no regime scoring. Operates only on a
serialized build_dashboard.serialize() card dict.

Hard gates decide eligibility and publication state (READY / PRE_READY).
Ranking is explainable (40/30/20) with a liquidity gate + tie-breaker.
Ordering is stable under input permutation.

See: docs/superpowers/specs/2026-08-23-daily-shortlist-explorer-design.md
"""
from __future__ import annotations

# --- Constants (canonical policy, t_69ff91c2 action-queue contract) ---
READY_QUEUES = {"fresh_breakout", "qualified_pullback", "retest_watch"}
PRE_READY_QUEUES = {"pre_breakout"}
MIN_AVG_DAILY_VALUE_20 = 10_000_000  # THB 10m 20-day average daily value
POLICY_VERSION = "daily-shortlist-v1"
LANE_POLICY_VERSION = "daily-shortlist-v2-lanes"

# Canonical lane order for the compact shortlist table.
LANE_ORDER = ("REVIEW_NOW", "PREPARE", "LEADERSHIP_EXTENDED")

# Extended-visibility evidence thresholds (evidence-driven, never hardcoded
# ATH alone: an item needs an explicit high52/athHigh field to qualify via
# the proximity path).
NEAR_52W_HIGH_PCT = 0.05   # close within 5% of 52W high counts as near-high

# Deterministic actions for the LEADERSHIP_EXTENDED lane, chosen from
# evidence only (quality pass + trigger proximity => review; else wait).
_EXTENDED_ACTION_REVIEW = "REVIEW EXTENDED"
_EXTENDED_ACTION_WAIT = "WAIT FOR RESET"

# Action queues that belong to Daily EOD only; everything else is excluded.
_DAILY_ONLY_QUEUES = READY_QUEUES | PRE_READY_QUEUES

# Stages/phases that indicate broken/declining/avoid structure.
_BROKEN_STAGES = {"S3_distributing", "S4_down"}
_BROKEN_PHASES = {"broken", "declining"}

# Canonical action terms that must NEVER pair with a READY publication state.
# A READY candidate is entry-ready confirmation — not a risk/avoid cue.
_CONTRADICTORY_READY_ACTIONS = {
    "NO LONG",
    "AVOID NEW LONG",
    "AVOID CHASING",
    "AVOID",
    "DO NOT CHASE",
    "NO LONG SETUP",
    "INVALIDATED",
    "WAIT",
    "WAIT FOR CONFIRMATION",
    "WAIT FOR QUALIFIED BREAKOUT",
    "WATCH / WAIT",
}

# Canonical normalized action for PRE_READY candidates — they require an
# explicit confirmation/wait condition, never a ready-to-trade directive.
_PRE_READY_ACTION = "WAIT FOR CONFIRMATION"

# Non-Daily provenance states. Intraday-only / event-driven candidates are
# excluded from the Daily surface (intraday is a separate observation layer).
_INTRADAY_ONLY_QUEUES = {"intraday_emerging"}


def _to_float(value):
    """JSON-safe float coercion; returns None on missing/non-numeric."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _daily_fresh(item: dict) -> bool:
    """True when Daily EOD provenance is non-stale and present."""
    daily = item.get("daily_eod_freshness") or {}
    if daily.get("status") != "latest_available":
        return False
    if not daily.get("as_of"):
        return False
    if item.get("dataFreshness") in ("stale", "unknown"):
        return False
    return True


def _structure_quality(item: dict) -> float:
    """40% — trend quality, mature structure integrity."""
    setup_q = item.get("setup_quality") or {}
    close = _to_float(item.get("close"))
    breakout_level = _to_float(item.get("breakoutLevel"))

    components = []
    # Quality gate (VCP/tightness): pass => 1.0, fail => 0.0
    components.append(1.0 if bool(setup_q.get("pass")) else 0.0)
    # Trend strength proxy: RS rating scaled to [0, 1] (rs/100 capped).
    rs = _to_float(item.get("rs"))
    if rs is not None:
        components.append(max(0.0, min(1.0, rs / 100.0)))
    # Structure integrity: close above breakout trigger.
    if close is not None and breakout_level is not None and breakout_level > 0:
        components.append(1.0 if close >= breakout_level else 0.0)
    # Stage: S2/S1 actionable; S3/S4 never reach here (excluded).
    stage = item.get("stage") or "S1_basing"
    if stage == "S2_uptrend":
        components.append(1.0)
    elif stage == "S1_basing":
        components.append(0.7)
    return round(sum(components) / len(components), 4) if components else 0.0


def _entry_readiness(item: dict) -> float:
    """30% — trigger proximity and confirmation status; no extended chase."""
    queue = item.get("action_queue")
    prox = item.get("setup_proximity") or {}
    state = prox.get("state")

    if queue in _DAILY_ONLY_QUEUES:
        # READY queues (action/near-trigger confirmed) score high.
        if state in ("action", "near_trigger"):
            return 1.0
        if state == "forming":
            return 0.5
    # Default conservative.
    return 0.5


def _risk_reward(item: dict) -> float:
    """20% — clear invalidation, risk distance, and available reward vs risk."""
    close = _to_float(item.get("close"))
    stop = _to_float(item.get("riskStop") or item.get("stop"))
    breakout = _to_float(item.get("breakoutLevel"))
    if not close or close <= 0:
        return 0.0
    if not stop or stop >= close:
        # No valid risk boundary => cannot rank risk/reward.
        return 0.0
    risk = close - stop
    if risk <= 0:
        return 0.0
    reward = abs(breakout - close) if breakout else risk
    rr = reward / risk
    # Saturating map: 1.0 RR => 0.25, 3.0+ RR => 1.0
    return round(min(1.0, max(0.0, (rr - 1.0) / 8.0 + 0.25)), 4)


def _liquidity_component(item: dict) -> float:
    """Liquidity gate + tie-breaker: 20d avg value / threshold (capped 1.0)."""
    val = _to_float(item.get("avgDailyValue20"))
    if val is None or val < MIN_AVG_DAILY_VALUE_20:
        return 0.0
    return round(min(1.0, val / (MIN_AVG_DAILY_VALUE_20 * 2)), 4)


def _trigger(item: dict) -> str | None:
    """Explainable trigger label (entry condition)."""
    phase = item.get("phase")
    queue = item.get("action_queue")
    if phase == "breakout_new" or queue == "fresh_breakout":
        return "Daily close >= breakout trigger with quality pass"
    if queue == "pre_breakout":
        return "Near trigger/pivot; confirm with close + volume"
    if queue == "qualified_pullback":
        return "Pullback holding support reference"
    if queue == "retest_watch":
        return "Breakout retest at reference"
    return None


def _invalidation(item: dict) -> str | None:
    """Explainable invalidation/system-stop boundary."""
    stop = _to_float(item.get("riskStop") or item.get("stop"))
    if stop is not None:
        return f"Close <= risk stop {stop:.2f}"
    return None


def _source(item: dict) -> str:
    daily = item.get("daily_eod_freshness") or {}
    return (daily.get("source") or item.get("source") or "Daily EOD")


def _as_of(item: dict) -> str | None:
    daily = item.get("daily_eod_freshness") or {}
    return daily.get("as_of") or item.get("daily_date") or item.get("date")


def normalize_action(item: dict, publication_state: str | None) -> tuple[str, str | None]:
    """Return (normalized_action, source_action) enforcing the action contract.

    - READY candidates may NOT expose NO LONG, AVOID, DO NOT CHASE, INVALIDATED,
      or any contradictory wait/risk action. If the source action contradicts
      READY, it is replaced with the queue-appropriate positive directive and
      the original is preserved as ``source_action``.
    - PRE_READY candidates must expose WAIT FOR CONFIRMATION (or an explicit
      wait action); a contradictory ready directive is downgraded.
    - The original source action is always preserved as ``source_action`` for
      audit traceability.

    The full ORD scan coverage is not altered: every item still maps to exactly
    one action queue; this is a presentation-layer normalization of the
    ``action`` label only.
    """
    source_action = item.get("action")
    action_upper = (source_action or "").upper()
    queue = item.get("action_queue")

    if publication_state == "READY":
        if action_upper in _CONTRADICTORY_READY_ACTIONS:
            # Map to the queue-appropriate positive directive.
            normalized = _ready_action_for_queue(queue)
            source_action = source_action if source_action else None
            return normalized, source_action
        # Accept the source action for READY if it is not contradictory.
        return source_action or _ready_action_for_queue(queue), source_action

    if publication_state == "PRE_READY":
        # PRE_READY must always expose an explicit wait/confirmation action.
        if action_upper in _CONTRADICTORY_READY_ACTIONS:
            # Already a wait action — keep but normalize to canonical form.
            return _PRE_READY_ACTION, source_action
        # Source action looks ready-like but publication state is PRE_READY;
        # downgrade to the canonical confirmation wait.
        return _PRE_READY_ACTION, source_action

    return source_action or "NO ACTIONABLE SETUP", source_action


def _ready_action_for_queue(queue: str | None) -> str:
    """Canonical READY action per Daily EOD queue."""
    if queue is None:
        return "REVIEW FRESH BREAKOUT"
    return {
        "fresh_breakout": "REVIEW FRESH BREAKOUT",
        "qualified_pullback": "REVIEW SUPPORT DEFENSE",
        "retest_watch": "REVIEW RETEST",
    }.get(queue, "REVIEW FRESH BREAKOUT")


def _why_now(item: dict, publication_state: str) -> str | None:
    """Human-readable why-now: combines trigger and readiness state."""
    prox = item.get("setup_proximity") or {}
    state = prox.get("state")
    if publication_state == "READY":
        if state == "action":
            return "Trigger confirmed — close at/above breakout level with quality pass"
        if state == "near_trigger":
            return "Near trigger; setup ready for confirmation"
    if publication_state == "PRE_READY":
        if state == "near_trigger":
            return "Near trigger/pivot; confirm with close + volume"
        if state == "forming":
            return "Setup forming; confirmation condition not yet met"
    return None


def _why_not(item: dict) -> str | None:
    """Human-readable why-not: invalidation boundary (may be None)."""
    return _invalidation(item)


def classify_shortlist(item: dict) -> dict:
    """Classify one serialized card for Daily Shortlist eligibility + ranking.

    Returns:
      {eligible: bool, publication_state: "READY"|"PRE_READY"|None,
       exclusion_reasons: list[str], rank_components: dict[str, float],
       total_score: float|None, policy_version: str}
    """
    if not isinstance(item, dict):
        return _ineligible(["INVALID_INPUT"], None, POLICY_VERSION)

    symbol = item.get("symbol")

    # --- Hard gate: liquidity ---
    liquid = _to_float(item.get("avgDailyValue20"))
    if liquid is None or liquid < MIN_AVG_DAILY_VALUE_20:
        return _ineligible(["LIQUIDITY_BELOW_20D_THB_10M"], symbol, POLICY_VERSION)

    # --- Hard gate: provenance (Daily EOD only) ---
    if not _daily_fresh(item):
        return _ineligible(["STALE_PROVENANCE"], symbol, POLICY_VERSION)

    # --- Hard gate: actionable Daily queue ---
    queue = item.get("action_queue")
    if queue is None:
        return _ineligible(["NO_ACTION_QUEUE"], symbol, POLICY_VERSION)
    if queue in _INTRADAY_ONLY_QUEUES:
        return _ineligible(["INTRADAY_ONLY"], symbol, POLICY_VERSION)
    if queue not in _DAILY_ONLY_QUEUES:
        # monitor_only, avoid_new_longs, or unknown => excluded from Daily surface
        return _ineligible(["NON_DAILY_QUEUE"], symbol, POLICY_VERSION)

    # --- Hard gate: broken / invalidated / developing ---
    phase = item.get("phase")
    stage = item.get("stage") or "S1_basing"
    action = item.get("action")
    if phase in _BROKEN_PHASES or stage in _BROKEN_STAGES:
        reason = "INVALIDATED" if phase in _BROKEN_PHASES else "BROKEN_STRUCTURE"
        return _ineligible([reason], symbol, POLICY_VERSION)
    if action == "DO NOT CHASE":
        return _ineligible(["DO_NOT_CHASE"], symbol, POLICY_VERSION)
    if phase == "base_early" or (phase == "base_tight"
                                 and (item.get("setup_proximity") or {}).get("state") == "forming"):
        return _ineligible(["DEVELOPING_BASE"], symbol, POLICY_VERSION)

    # --- Publication state ---
    if queue in READY_QUEUES:
        pub = "READY"
    elif queue in PRE_READY_QUEUES:
        pub = "PRE_READY"
    else:
        return _ineligible(["NON_DAILY_QUEUE"], symbol, POLICY_VERSION)

    # --- Ranking (explainable 40/30/20 + liquidity gate) ---
    components = {
        "structure_quality": _structure_quality(item),
        "entry_readiness": _entry_readiness(item),
        "risk_reward": _risk_reward(item),
        "liquidity": _liquidity_component(item),
    }
    total = round(
        0.4 * components["structure_quality"]
        + 0.3 * components["entry_readiness"]
        + 0.2 * components["risk_reward"], 4)

    return {
        "eligible": True,
        "publication_state": pub,
        "exclusion_reasons": [],
        "rank_components": components,
        "total_score": total,
        "policy_version": POLICY_VERSION,
    }


def _ineligible(reasons, symbol, policy_version):
    return {
        "eligible": False,
        "publication_state": None,
        "exclusion_reasons": reasons,
        "rank_components": {},
        "total_score": None,
        "policy_version": policy_version,
        "symbol": symbol,
    }


def project_shortlist(items: list[dict]) -> list[dict]:
    """Return eligible Daily Shortlist records, ordered deterministically.

    Sort key: (-total_score, -avgDailyValue20, symbol) so higher-quality /
    higher-liquidity names rank first and ties break by symbol (stable).
    """
    classified = []
    for item in items or []:
        result = classify_shortlist(item)
        if result["eligible"]:
            components = result["rank_components"]
            pub = result["publication_state"]
            # Enforce action contract: normalize contradictory READY/PRE_READY
            # actions; preserve the original as source_action for audit.
            normalized_action, source_action = normalize_action(item, pub)
            classified.append({
                "symbol": item.get("symbol"),
                "publication_state": pub,
                "lifecycle_state": item.get("lifecycle_state") or item.get("lifecycleState") or item.get("phase") or "unclassified",
                "action": normalized_action,
                "source_action": source_action,
                "rank_components": components,
                "policy_version": result["policy_version"],
                "total_score": result["total_score"],
                "trigger": _trigger(item),
                "invalidation": _invalidation(item),
                "why_now": _why_now(item, pub),
                "why_not": _why_not(item),
                "source": _source(item),
                "as_of": _as_of(item),
                "avgDailyValue20": _to_float(item.get("avgDailyValue20")) or 0.0,
            })
            record = classified[-1]
            record["shortlist_lane"] = (
                "REVIEW_NOW" if pub == "READY" else "PREPARE")
            record["is_extended"] = False
            record["extended_reasons"] = []
    # Stable deterministic ordering:
    # READY before PRE_READY (by spec §4), then score desc, liquidity desc,
    # symbol asc as the stable tiebreaker.
    state_order = {"READY": 0, "PRE_READY": 1}
    classified.sort(key=lambda r: (
        state_order.get(r["publication_state"], 99),
        -(r["total_score"] or 0.0),
        -(_to_float(r.get("avgDailyValue20")) or 0.0),
        r["symbol"] or "",
    ))
    return classified


# ---------------------------------------------------------------------------
# Task C: Leadership Extended lane (visibility-only, never READY)
# ---------------------------------------------------------------------------

def _extended_reasons(item: dict) -> list[str]:
    """Collect explicit evidence-based reasons a name is extended.

    Every reason requires an evidence field on the serialized card; ATH alone
    is never sufficient without high52/athHigh/extended evidence present.
    """
    reasons = []
    if item.get("extended") is True or item.get("phase") == "breakout_extended":
        # build_dashboard flags: {"code": "extended"} / phase breakout_extended
        reasons.append("EXTENDED_BREAKOUT")
    close = _to_float(item.get("close"))
    for field, code in (("high52", "NEAR_52W_HIGH"), ("athHigh", "NEAR_ATH")):
        high = _to_float(item.get(field))
        if close and high and high > 0:
            if (high - close) / high <= NEAR_52W_HIGH_PCT:
                reasons.append(code)
    return reasons


def classify_shortlist_extended(item: dict) -> dict:
    """Classify one card as eligible for the LEADERSHIP_EXTENDED lane.

    Same hard gates as classify_shortlist (liquidity, freshness, broken/
    invalidated/developing), but instead of READY/PRE_READY queues it accepts
    extended/near-52W/near-ATH candidates with explicit evidence.  Returns
    publication_state "EXTENDED" (never READY) plus extended_reasons.
    """
    if not isinstance(item, dict):
        return _ineligible(["INVALID_INPUT"], None, LANE_POLICY_VERSION)

    symbol = item.get("symbol")

    # --- Same hard gates as the base policy ---
    liquid = _to_float(item.get("avgDailyValue20"))
    if liquid is None or liquid < MIN_AVG_DAILY_VALUE_20:
        return _ineligible(["LIQUIDITY_BELOW_20D_THB_10M"], symbol, LANE_POLICY_VERSION)
    if not _daily_fresh(item):
        return _ineligible(["STALE_PROVENANCE"], symbol, LANE_POLICY_VERSION)
    phase = item.get("phase")
    stage = item.get("stage") or "S1_basing"
    if phase in _BROKEN_PHASES or stage in _BROKEN_STAGES:
        return _ineligible(
            ["INVALIDATED" if phase in _BROKEN_PHASES else "BROKEN_STRUCTURE"],
            symbol, LANE_POLICY_VERSION)
    if phase == "base_early" or (phase == "base_tight"
                                 and (item.get("setup_proximity") or {}).get("state") == "forming"):
        return _ineligible(["DEVELOPING_BASE"], symbol, LANE_POLICY_VERSION)

    # --- Extended evidence gate ---
    reasons = _extended_reasons(item)
    if not reasons:
        return _ineligible(["NO_EXTENDED_EVIDENCE"], symbol, LANE_POLICY_VERSION)

    components = {
        "structure_quality": _structure_quality(item),
        "entry_readiness": _entry_readiness(item),
        "risk_reward": _risk_reward(item),
        "liquidity": _liquidity_component(item),
    }
    total = round(
        0.4 * components["structure_quality"]
        + 0.3 * components["entry_readiness"]
        + 0.2 * components["risk_reward"], 4)
    return {
        "eligible": True,
        "publication_state": "EXTENDED",
        "is_extended": True,
        "extended_reasons": reasons,
        "exclusion_reasons": [],
        "rank_components": components,
        "total_score": total,
        "policy_version": LANE_POLICY_VERSION,
    }


def _extended_action(item: dict) -> str:
    """Deterministic extended action from evidence only.

    Quality pass AND near trigger/pivot => REVIEW EXTENDED (leadership name
    worth active review); otherwise WAIT FOR RESET (too far / no quality).
    """
    quality_pass = bool((item.get("setup_quality") or {}).get("pass"))
    state = (item.get("setup_proximity") or {}).get("state")
    near = state in ("action", "near_trigger")
    return _EXTENDED_ACTION_REVIEW if (quality_pass and near) else _EXTENDED_ACTION_WAIT


def _extended_why_now(item: dict) -> str | None:
    reasons = _extended_reasons(item)
    if not reasons:
        return None
    return f"Extended leadership candidate ({', '.join(reasons)}); not Ready — review extension risk before any entry"


def project_shortlist_lanes(items: list[dict]) -> dict[str, list[dict]]:
    """Project items into the three canonical shortlist lanes.

    Lane order is fixed by LANE_ORDER. Within each lane ordering matches
    project_shortlist semantics (score desc, liquidity desc, symbol asc);
    LEADERSHIP_EXTENDED uses the same key with publication EXTENDED last.
    Broken/invalidated/stale/illiquid/developing names enter NO lane.
    """
    ready_pre = project_shortlist(items or [])
    lanes: dict[str, list[dict]] = {lane: [] for lane in LANE_ORDER}
    for r in ready_pre:
        lane = "REVIEW_NOW" if r["publication_state"] == "READY" else "PREPARE"
        record = dict(r)
        record["shortlist_lane"] = lane
        record["is_extended"] = False
        record["extended_reasons"] = []
        lanes[lane].append(record)

    extended = []
    for item in items or []:
        result = classify_shortlist_extended(item)
        if not result["eligible"]:
            continue
        normalized_action, source_action = normalize_action(item, None)
        action = _extended_action(item)
        extended.append({
            "symbol": item.get("symbol"),
            "publication_state": "EXTENDED",
            "lifecycle_state": item.get("lifecycle_state") or item.get("lifecycleState") or item.get("phase") or "unclassified",
            "action": action,
            "source_action": source_action,
            "rank_components": result["rank_components"],
            "policy_version": result["policy_version"],
            "total_score": result["total_score"],
            "trigger": _trigger(item),
            "invalidation": _invalidation(item),
            "why_now": _extended_why_now(item),
            "why_not": _why_not(item),
            "source": _source(item),
            "as_of": _as_of(item),
            "avgDailyValue20": _to_float(item.get("avgDailyValue20")) or 0.0,
            "shortlist_lane": "LEADERSHIP_EXTENDED",
            "is_extended": True,
            "extended_reasons": result["extended_reasons"],
        })
    extended.sort(key=lambda r: (
        -(r["total_score"] or 0.0),
        -(_to_float(r.get("avgDailyValue20")) or 0.0),
        r["symbol"] or "",
    ))
    lanes["LEADERSHIP_EXTENDED"] = extended
    return lanes
