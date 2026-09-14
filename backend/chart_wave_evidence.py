"""Canonical wave evidence with an explicitly named legacy fallback.

Chart retrieval must not own wave interpretation.  The legacy chart payload
still exposes this field, so its existing projection is isolated here until
all callers consume canonical symbol evidence directly.
"""

from __future__ import annotations

import pandas as pd

from elliott_structure_engine import build_wave_contract


def canonical_chart_wave_evidence(item: dict | None) -> dict | None:
    """Project Daily markers already published in canonical symbol evidence."""
    if not isinstance(item, dict):
        return None
    wave = item.get("wave") if isinstance(item.get("wave"), dict) else {}
    markers = wave.get("evidence_markers")
    if not isinstance(markers, list):
        markers = (wave.get("chart_evidence") or {}).get("daily", {}).get("markers")
    if not isinstance(markers, list):
        return None
    return {"timeframe": "daily", "markers": markers,
            "explanation": wave.get("evidence_explanation"),
            "snapshot_id": (item.get("provenance") or {}).get("snapshot_id"),
            "mapping": {"daily": "authoritative", "60m": "not_projected"}}


def neutral_chart_wave_evidence(timeframe: str) -> dict:
    """Return the safe primary chart evidence when Daily evidence is absent.

    A chart read may still have candles, including a provisional 60m
    aggregation, but that data is not a substitute for the published Daily
    Wave interpretation.
    """
    timeframe = {"1D": "daily", "1W": "weekly", "1M": "monthly",
                 "60M": "60m"}.get(str(timeframe).upper(), str(timeframe).lower())
    return {
        "timeframe": timeframe,
        "markers": [],
        "status": "NOT_VERIFIED",
        "mapping": {"daily": "not_verified", "60m": "setup_only"},
        "missing": ["canonical_daily_wave_evidence"],
        "source": "canonical_daily_evidence_unavailable",
    }


def build_legacy_chart_wave_evidence(candles: list[dict], timeframe: str, as_of: str | None) -> dict:
    """Preserve the historical wave_evidence response shape and marker values."""
    evidence = {
        "timeframe": timeframe.lower(),
        "markers": [],
        "mapping": {"daily": "not_projected", "60m": "setup_only"},
    }
    if timeframe == "1D":
        daily = pd.DataFrame(candles)
        if not daily.empty:
            daily = daily.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                          "close": "Close", "volume": "Volume"})
            wave = build_wave_contract(daily, {}, snapshot_id="daily:" + str(as_of))
            return {"timeframe": "daily", "markers": wave.get("evidence_markers", []),
                    "explanation": wave.get("evidence_explanation"),
                    "snapshot_id": wave.get("snapshot_id"),
                    "mapping": {"daily": "authoritative", "60m": "not_projected"}}
    elif timeframe == "60M":
        evidence["missing"] = ["daily_markers_not_projected"]
    return evidence
