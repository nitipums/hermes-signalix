"""Two-layer actionable setup state for S1/S2 (Stage + Setup State redesign 2026-08-19).

setup_quality  -> VCP/tightness gate (pass/fail)  [Arm decision D2]
setup_proximity-> entry timing: forming / near_trigger / action / extended  [D3]
S3/S4 have NO actionable proximity (state = None)  [D5]
All outputs are JSON-safe plain floats/None (numpy scalars break json.dumps).
"""
from __future__ import annotations

# Bee-gate v1 thresholds (adjustable).
SETUP_PROXIMITY_PCT = 0.05          # near_trigger within 5% of pivot/zone-top
EXTENDED_FROM_TRIGGER_PCT = 0.08    # extended if >8% beyond pivot
EXTENDED_RSI = 75.0
TIGHT_RANGE_20D_PCT = 12.0
VOL_CONTRACTION_RATIO = 1.0         # volume_ratio_50 < 1.0 => recent vol contracting

PROXIMITY_STATES = ("forming", "near_trigger", "action", "extended")
ACTIONABLE_STAGES = ("S1_basing", "S2_uptrend")


def _f(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_setup_quality(evidence: dict) -> dict:
    """VCP/tightness gate. pass = tight range + vol contraction + not extended."""
    range20 = _f(evidence.get("range_20d_pct"))
    vol_ratio = _f(evidence.get("volume_ratio_50"))
    rsi = _f(evidence.get("rsi_daily"))
    close = _f(evidence.get("close"))
    pivot = _f(evidence.get("rolling_trigger"))
    reasons = []

    if range20 is not None and range20 <= TIGHT_RANGE_20D_PCT:
        reasons.append("tight_range")
    else:
        reasons.append("range_too_wide")

    if vol_ratio is not None and vol_ratio < VOL_CONTRACTION_RATIO:
        reasons.append("vol_contraction")
    else:
        reasons.append("vol_expanding")

    extended = False
    if rsi is not None and rsi >= EXTENDED_RSI:
        extended = True
    if pivot and pivot > 0 and close and close / pivot - 1 > EXTENDED_FROM_TRIGGER_PCT:
        extended = True
    reasons.append("not_extended" if not extended else "extended")

    return {
        "pass": all(r not in ("range_too_wide", "vol_expanding", "extended") for r in reasons),
        "reasons": reasons,
        "range_20d_pct": range20,
        "vol_ratio_50": vol_ratio,
    }


def compute_setup_proximity(stage: str, evidence: dict) -> dict:
    """Entry timing per stage. S3/S4 => state None (risk buckets, not actionable)."""
    if stage not in ACTIONABLE_STAGES:
        return {"state": None, "pivot": None, "distance_pct": None, "zone": None}

    close = _f(evidence.get("close"))
    rsi = _f(evidence.get("rsi_daily"))
    empty = {"state": "forming", "pivot": None, "distance_pct": None, "zone": None}

    if stage == "S1_basing":
        pivot = _f(evidence.get("rolling_trigger"))
        if not pivot or pivot <= 0:
            return empty
        dist = (close / pivot - 1) if close else None
        if rsi is not None and rsi >= EXTENDED_RSI:
            state = "extended"
        elif dist is not None and dist > EXTENDED_FROM_TRIGGER_PCT:
            state = "extended"
        elif dist is not None and dist > 0:
            state = "action"
        elif dist is not None and dist >= -SETUP_PROXIMITY_PCT:
            state = "near_trigger"
        else:
            state = "forming"
        return {"state": state, "pivot": pivot,
                "distance_pct": round(dist, 4) if dist is not None else None,
                "zone": None}

    # S2_uptrend
    bz = evidence.get("buy_zones_90d") or {}
    fibs = sorted(float(v) for v in bz.values() if v is not None)
    if len(fibs) < 2:
        return empty
    zone = {"lo": fibs[0], "hi": fibs[-1]}
    swing_high = _f(evidence.get("swing_high_90d"))
    dist = (close / zone["hi"] - 1) if close else None
    if rsi is not None and rsi >= EXTENDED_RSI:
        state = "extended"
    elif swing_high and close and close > swing_high * (1 + EXTENDED_FROM_TRIGGER_PCT):
        state = "extended"
    elif close and zone["lo"] <= close <= zone["hi"]:
        state = "action"
    elif dist is not None and 0 < dist <= SETUP_PROXIMITY_PCT:
        state = "near_trigger"   # above zone top, approaching (<=5% away)
    else:
        state = "forming"
    return {"state": state, "pivot": swing_high,
            "distance_pct": round(dist, 4) if dist is not None else None,
            "zone": zone}


def compute_setup_state(stage: str, evidence: dict) -> dict:
    return {
        "quality": compute_setup_quality(evidence),
        "proximity": compute_setup_proximity(stage, evidence),
    }
