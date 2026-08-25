"""Deferred/isolated runtime initialization.

Portfolio and portal schemas are not part of the owner-only MVP decision
surface, but remain enabled for backward compatibility while their data exists.
Keeping initialization here prevents app.py's core startup from owning their
implementation details.
"""
from __future__ import annotations

from collections.abc import Callable


def init_deferred_schemas(pg_factory: Callable):
    """Initialize portal/portfolio schemas through an injected DB factory."""
    from users import init_user_schema
    from portfolio import init_portfolio_schema

    init_user_schema()
    pg = pg_factory()
    try:
        init_portfolio_schema(pg)
    finally:
        pg.close()
