"""Signalix — Ranking computation (Contract v0.2.0 §5: setup-ranking-v1.0.0).

4-component ranking with weights:
- setup/structure: 40%
- entry_proximity: 30%
- risk_reward: 20%
- market_alignment: 10%

Deterministic, persisted at scan time, missing = NULL not zero.
"""

from __future__ import annotations

RANKING_POLICY_VERSION = "setup-ranking-v1.0.0"
RANKING_WEIGHTS = {
    "setup_structure": 0.40,
    "entry_proximity": 0.30,
    "risk_reward": 0.20,
    "market_alignment": 0.10,
}


def compute_ranking_components(row: dict, regime_state: str | None) -> dict:
    """
    Compute 4 ranking components per Contract v0.2.0 §5.
    
    Returns dict with component values, normalized [0,1], missing status, reason codes.
    """
    reasons = []
    components = {}
    
    # 1. setup/structure (40%): VCP + trend template conditions + tight range
    vcp = row.get("vcp", {}).get("is_vcp", False)
    conditions_met = row.get("trend_template", {}).get("conditions_met", 0)
    range_20d = row.get("analysis_metrics", {}).get("max_20d")
    min_20d = row.get("analysis_metrics", {}).get("min_20d")
    close = row.get("close")
    
    setup_score = None
    if conditions_met is not None:
        base = conditions_met / 8.0
        if vcp:
            base = min(1.0, base + 0.15)
        if range_20d is not None and min_20d is not None and close is not None and close > 0:
            range_pct = (range_20d - min_20d) / close
            if range_pct > 0.15:
                base *= 0.8
        setup_score = max(0.0, min(1.0, base))
    else:
        reasons.append("SETUP_MISSING_CONDITIONS")
    
    components["setup_structure"] = {
        "value": setup_score,
        "normalized": setup_score,
        "missing": setup_score is None,
        "reason_codes": [] if setup_score is not None else ["SETUP_MISSING_CONDITIONS"],
    }
    
    # 2. entry_proximity (30%): distance to trigger/buy zone
    # Only applicable for actionable stages (S1/S2). For S3/S4, use neutral score.
    proximity = row.get("daily_state", {}).get("setup_proximity", {})
    distance_pct = proximity.get("distance_pct")
    prox_state = proximity.get("state")
    stage = row.get("daily_state", {}).get("stage")
    
    prox_score = None
    is_actionable_stage = stage in ("S1_basing", "S2_uptrend")
    
    if is_actionable_stage:
        if distance_pct is not None:
            if distance_pct <= 0:
                prox_score = 1.0
            elif distance_pct <= 0.05:
                prox_score = 1.0 - (distance_pct / 0.05) * 0.3
            elif distance_pct <= 0.15:
                prox_score = 0.7 - ((distance_pct - 0.05) / 0.10) * 0.7
            else:
                prox_score = 0.0
        elif prox_state == "action":
            prox_score = 1.0
        elif prox_state == "near_trigger":
            prox_score = 0.8
        elif prox_state == "forming":
            prox_score = 0.4
        elif prox_state == "extended":
            prox_score = 0.1
        else:
            prox_score = 0.0
            reasons.append("PROXIMITY_MISSING")
    else:
        prox_score = 0.5
    
    components["entry_proximity"] = {
        "value": prox_score,
        "normalized": prox_score,
        "missing": is_actionable_stage and distance_pct is None and prox_state is None,
        "reason_codes": [] if not (is_actionable_stage and distance_pct is None and prox_state is None) else ["PROXIMITY_MISSING"],
    }
    
    # 3. risk_reward (20%): position sizing + stop distance
    pos_sizing = row.get("position_sizing", {})
    risk_reward = pos_sizing.get("risk_reward_ratio")
    suggested_stop = row.get("suggested_stop")
    
    rr_score = None
    if risk_reward is not None and risk_reward > 0:
        rr_score = min(1.0, max(0.0, (risk_reward - 1.0) / 3.0))
    elif suggested_stop is not None and row.get("close") and row["close"] > 0:
        stop_dist = abs(row["close"] - suggested_stop) / row["close"]
        if stop_dist > 0:
            rr_score = min(1.0, (3.0 * stop_dist - 1.0) / 3.0)
            if rr_score < 0:
                rr_score = 0.0
        else:
            reasons.append("RISK_REWARD_MISSING_STOP")
    else:
        reasons.append("RISK_REWARD_MISSING")
    
    components["risk_reward"] = {
        "value": rr_score,
        "normalized": max(0.0, rr_score) if rr_score is not None else None,
        "missing": rr_score is None,
        "reason_codes": [] if rr_score is not None else ["RISK_REWARD_MISSING"],
    }
    
    # 4. market_alignment (10%): regime-based
    alignment_map = {
        "HIGH_VOLATILITY": -0.5,
        "LIQUIDITY_EVENT": -0.3,
        "LOW_SPREAD": 0.3,
        "NORMAL": 0.0,
    }
    alignment = alignment_map.get(regime_state, 0.0)
    alignment_normalized = (alignment + 0.5) / 0.8
    
    components["market_alignment"] = {
        "value": alignment,
        "normalized": alignment_normalized,
        "missing": False,
        "reason_codes": [],
    }
    
    # Compute total if all components present
    total = None
    missing_count = sum(1 for c in components.values() if c["missing"])
    if missing_count == 0:
        total = sum(
            c["normalized"] * RANKING_WEIGHTS[name]
            for name, c in components.items()
        )
    
    return {
        "components": components,
        "total_score": total,
        "missing_count": missing_count,
        "reason_codes": reasons,
        "policy_version": "setup-ranking-v1.0.0",
        "weights": RANKING_WEIGHTS,
    }


def compute_symbol_ranking(row: dict, regime_state: str | None) -> dict:
    """Convenience function to compute and attach ranking to a row."""
    ranking = compute_ranking_components(row, regime_state)
    row["ranking"] = ranking
    return ranking


RANKING_WEIGHTS = {
    "setup_structure": 0.40,
    "entry_proximity": 0.30,
    "risk_reward": 0.20,
    "market_alignment": 0.10,
}