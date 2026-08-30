"""Conservative, observable Daily Elliott candidate evidence."""

from __future__ import annotations

import math

import pandas as pd


WAVE_STATES = {
    "WAVE_1_ADVANCE",
    "WAVE_2_FORMING",
    "WAVE_2_NEAR_COMPLETION",
    "EARLY_WAVE_3",
    "WAVE_3_CONTINUATION",
    "WAVE_4_CORRECTION",
    "WAVE_5_ADVANCE",
    "UNKNOWN",
}


def _json_value(value):
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _json_value(value.item())
    return str(value)


def _close_available(daily_df: pd.DataFrame | None) -> bool:
    return daily_df is not None and "Close" in daily_df and len(daily_df) > 0


def classify_wave_candidate(
    daily_df: pd.DataFrame,
    swing_evidence: dict | None = None,
) -> dict:
    """Return a cautious structural candidate, never an authoritative count."""
    evidence = dict(swing_evidence or {})
    missing = []
    required = ("prior_advance", "confirmed_swing_anchors", "structure_intact")
    for key in required:
        if evidence.get(key) is None:
            missing.append(key)
    if not _close_available(daily_df):
        missing.append("daily_ohlcv")

    evidence_out = _json_value(evidence)
    evidence_out["missing_evidence"] = missing
    result = {
        "timeframe": "daily",
        "state": "UNKNOWN",
        "confidence": "INSUFFICIENT" if missing else "PARTIAL",
        "evidence": evidence_out,
    }
    if missing or evidence.get("structure_intact") is False:
        return result

    # Explicit observable phase markers are preferred. They are not treated as
    # an objective Elliott count; they simply preserve confirmed chart review.
    phase = str(evidence.get("phase", evidence.get("candidate_state", ""))).upper()
    aliases = {
        "WAVE_1": "WAVE_1_ADVANCE", "WAVE1": "WAVE_1_ADVANCE",
        "WAVE_2": "WAVE_2_FORMING", "WAVE2": "WAVE_2_FORMING",
        "EARLY_WAVE3": "EARLY_WAVE_3", "WAVE3": "WAVE_3_CONTINUATION",
        "WAVE_4": "WAVE_4_CORRECTION", "WAVE4": "WAVE_4_CORRECTION",
        "WAVE_5": "WAVE_5_ADVANCE", "WAVE5": "WAVE_5_ADVANCE",
    }
    if phase in WAVE_STATES:
        result["state"] = phase
        result["confidence"] = "PARTIAL"
        return result
    if phase in aliases:
        result["state"] = aliases[phase]
        return result

    if evidence.get("wave_5_advance"):
        state = "WAVE_5_ADVANCE"
    elif evidence.get("wave_4_correction"):
        state = "WAVE_4_CORRECTION"
    elif evidence.get("wave_3_continuation") or evidence.get("continuation_confirmed"):
        state = "WAVE_3_CONTINUATION"
    elif evidence.get("breakout_confirmed") or evidence.get("early_wave_3"):
        state = "EARLY_WAVE_3"
    elif evidence.get("pullback_depth_pct") is not None:
        state = "WAVE_2_NEAR_COMPLETION" if evidence.get("fib_zone") else "WAVE_2_FORMING"
    elif evidence.get("prior_advance"):
        state = "WAVE_1_ADVANCE"
    else:
        return result
    result["state"] = state
    return result
