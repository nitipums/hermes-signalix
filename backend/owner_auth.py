"""Fail-closed owner credential checks shared by retained compatibility APIs."""
from __future__ import annotations

import hmac


def require_owner_token(provided: str, expected: str) -> bool:
    """Return true only for two present, constant-time-equal credentials."""
    return bool(provided and expected and hmac.compare_digest(provided, expected))


def require_owner_identity(
    provided_token: str,
    expected_token: str,
    requested_identity: str,
    bound_owner_identity: str,
) -> bool:
    """Bind the configured owner credential to the configured owner identity."""
    return bool(
        require_owner_token(provided_token, expected_token)
        and requested_identity
        and bound_owner_identity
        and hmac.compare_digest(str(requested_identity), str(bound_owner_identity))
    )
