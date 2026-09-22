"""Deterministic active-universe seam for current read-only surfaces.

This module owns only the boundary between the authoritative active ORD loader
and the two current evidence surfaces.  Historical setup construction keeps
its compatibility wrapper in ``mvp_api``.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from typing import Any

import instruments
from marginable import eligible_symbols

UNIVERSE_FILTERS = frozenset({"marginable_long", "active_ord"})


def membership_digest(symbols: Iterable[str]) -> str:
    """Return the stable digest for canonical sorted membership."""
    canonical = sorted(str(symbol).strip().upper() for symbol in symbols if str(symbol).strip())
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _canonical_symbols(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip().upper() for value in values if str(value).strip()})


def resolve_active_universe(
    pg: Any,
    universe_filter: str = "marginable_long",
    *,
    active_symbols: Iterable[str] | None = None,
    active_symbol_loader: Callable[[Any], Iterable[str]] = instruments.active_ord_symbols,
    marginable_resolver: Callable[[Iterable[str]], tuple[list[str], dict]] = eligible_symbols,
) -> tuple[list[str], dict[str, Any]]:
    """Resolve one canonical active universe with injectable authorities."""
    if universe_filter not in UNIVERSE_FILTERS:
        raise ValueError(f"unknown universe filter: {universe_filter}")

    loaded = active_symbols if active_symbols is not None else active_symbol_loader(pg)
    active = _canonical_symbols(loaded)
    if universe_filter == "active_ord":
        return active, {
            "universe_filter": "active_ord",
            "audit_only": True,
            "base_active_ord_count": len(active),
            "eligible_count": len(active),
            "excluded_count": 0,
            "excluded_reason": None,
            "universe_membership": {"symbols": list(active), "digest": membership_digest(active)},
        }

    symbols, manifest = marginable_resolver(active)
    symbols = _canonical_symbols(symbols)
    manifest = dict(manifest)
    manifest.update({
        "universe_filter": "marginable_long",
        "universe_membership": {"symbols": list(symbols), "digest": membership_digest(symbols)},
        "audit_only": False,
    })
    return symbols, manifest
