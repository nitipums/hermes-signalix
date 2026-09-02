"""Compatibility adapters for the canonical chart row read contract."""

from __future__ import annotations

from canonical_chart_read import (
    fetch_chart_rows_with_metadata as _canonical_fetch_chart_rows_with_metadata,
)


def fetch_chart_rows(cur, symbol, timeframe, limit, market="TH"):
    """Compatibility import for canonical chart row retrieval."""
    rows, _label, _metadata = fetch_chart_rows_with_metadata(
        cur, symbol, timeframe, limit, market=market
    )
    return rows, _label


def fetch_chart_rows_with_metadata(cur, symbol, timeframe, limit, market="TH"):
    """Compatibility import for canonical chart rows and read metadata."""
    return _canonical_fetch_chart_rows_with_metadata(cur, symbol, timeframe, limit, market=market)
