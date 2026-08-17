"""Explicit market and watchlist contracts for the shared technical scanner.

A universe selects its benchmark, its eligible symbols, and market-specific
pre-screen policy.  Indicator calculations remain in ``scanner.py`` and are
identical for every market.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Universe:
    key: str
    market: str
    benchmark_symbol: str
    symbols: tuple[str, ...]
    min_price: float | None = None
    min_today_trade_value: float | None = None


# These are the common, market-level defaults.  They deliberately do not
# encode a fixed list: Thailand's active universe comes from its native EOD DB.
MARKET_DEFAULTS = {
    "TH": Universe(
        key="th_all",
        market="TH",
        benchmark_symbol="SET",
        symbols=(),
        min_price=0.60,
        min_today_trade_value=15_000_000.0,
    ),
}


# Curated from Situational Awareness LP's 2026-06-30 13F information table.
# Excludes the filing's listed put hedge and keeps only US-tradeable long-theme
# names.  It is an idea universe, not an instruction to replicate fund weights.
UNIVERSES = {
    "us_ai_buildout": Universe(
        key="us_ai_buildout",
        market="US",
        benchmark_symbol="SPY",
        symbols=(
            "SNDK", "MU", "BE", "TSM", "NBIS", "CRWV", "CORZ", "STM",
            "APLD", "RIOT", "IREN", "CLSK", "HIVE", "BTDR", "BW", "PUMP",
            "SEI", "WULF", "TE",
        ),
    ),
}


def get_universe(key: str) -> Universe:
    """Return a named scan universe or raise a stable caller-facing error."""
    try:
        return UNIVERSES[key.lower()]
    except KeyError as exc:
        raise ValueError(f"unknown universe: {key}") from exc


def market_default(market: str) -> Universe:
    """Return default policy for a broad market scan."""
    try:
        return MARKET_DEFAULTS[market.upper()]
    except KeyError as exc:
        raise ValueError(f"unknown market: {market}") from exc
