"""Deferred/isolated runtime initialization for the retained user portal."""
from __future__ import annotations

from collections.abc import Callable


def init_deferred_schemas(pg_factory: Callable):
    """Initialize the retained portal schema."""
    from users import init_user_schema

    init_user_schema()
