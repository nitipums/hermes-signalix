"""Read-only ownership registry for serving setup policies.

The Daily EOD and isolated 60m VCP policies intentionally remain separate.
This module records existing values; it is not an evaluation engine.
"""
from __future__ import annotations

from types import MappingProxyType


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


_POLICIES = _freeze({
    "daily_eod": {
        "timeframe": "daily_eod",
        "policy_id": "signalix/daily-eod-vcp",
        "version": "daily-shortlist-v1",
        "owner": "daily_shortlist + signal_core/setup_state",
        "thresholds": {
            "min_history_bars": 260,
            "freshness": "latest_available Daily EOD",
            "breakout_buffer_pct": 0.01,
            "breakout_volume_ratio": 1.20,
            "liquidity_avg_daily_value_20_thb": 10_000_000,
            "legacy_scan_liquidity_avg_daily_value_20_thb": 15_000_000,
            "extension_from_trigger_pct": 0.08,
            "extension_rsi": 75.0,
            "invalidation": "tightest of swing low and -7% hard stop",
        },
    },
    "vcp_60m": {
        "timeframe": "vcp_60m",
        "policy_id": "signalix/vcp-finder-60m",
        "version": "signalix/vcp-finder-60m-v2-latest-sequence",
        "owner": "vcp_finder.VCP60Config",
        "thresholds": {
            "min_history_bars": 80,
            "pattern_bars": 60,
            "freshness_sessions": 2,
            "breakout_buffer_pct": 0.005,
            "breakout_atr_fraction": 0.10,
            "breakout_volume_ratio": 1.50,
            "liquidity_avg_trade_value_20_thb": 10_000_000,
            "extension_from_pivot_pct": 0.03,
            "invalidation": "prior pivot low / ATR-linked failure",
        },
    },
})

# Public read-only handle for callers that need the complete registry.
POLICY_REGISTRY = _POLICIES


def get_policy(timeframe: str):
    """Return an immutable policy mapping for ``daily_eod`` or ``vcp_60m``."""
    try:
        return _POLICIES[timeframe]
    except KeyError as exc:
        raise KeyError(f"unknown policy timeframe: {timeframe}") from exc


def policy_registry():
    """Return the immutable complete registry."""
    return _POLICIES


get_policy_registry = policy_registry
