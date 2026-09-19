"""Structural interface for bounded Daily point-in-time history loaders."""
from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


DailyRow = Mapping[str, Any]
DailyFrame = Sequence[DailyRow]
DailyLoad = tuple[DailyFrame, Any]
DailyBatchLoad = Mapping[str, DailyLoad | tuple[DailyFrame, Any, Mapping[str, Any]]]


@runtime_checkable
class DailyHistoryAdapter(Protocol):
    """The narrow Daily-history seam shared by Trend Map and Trend Route."""

    def load_daily_pit(self, conn: Any, symbol: str, as_of: Any) -> DailyLoad:
        ...

    def load_daily_pit_batch(self, conn: Any, symbols: Sequence[str], as_of: Any) -> DailyBatchLoad:
        ...
