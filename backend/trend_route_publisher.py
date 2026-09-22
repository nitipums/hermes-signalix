"""Immutable Trend Route read-model publisher and fail-closed reader."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from trend_route import ROUTE_POLICY_VERSION, compact_route

DEFAULT_ROOT = Path(__file__).with_name("trend-route-read-model")
SCHEMA_VERSION = "trend-route-read-model-v1"


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _hash(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()[:24]


def _atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".route-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_bytes(value)); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _immutable(path: Path, value: Any) -> None:
    encoded = _bytes(value)
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("immutable Trend Route artifact mismatch")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".route-version-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
        os.link(temp, path)
    except FileExistsError:
        if path.read_bytes() != encoded:
            raise ValueError("immutable Trend Route artifact mismatch")
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _validate(route: Mapping[str, Any]) -> None:
    if route.get("policy_version") != ROUTE_POLICY_VERSION:
        raise ValueError("Trend Route policy mismatch")
    if route.get("status") not in {"FULL", "PARTIAL", "NOT_VERIFIED"}:
        raise ValueError("Trend Route status invalid")
    if route.get("provenance", {}).get("query_mode") != "READ_MODEL":
        raise ValueError("Trend Route provenance is not read-model-only")
    if not route.get("coverage", {}).get("no_lookahead") is True:
        raise ValueError("Trend Route no-lookahead metadata missing")
    if any(key in route for key in ("ohlcv", "indicators", "raw_history")):
        raise ValueError("Trend Route artifact contains raw history")


def publish_route_read_model(routes: Mapping[str, Mapping[str, Any]], *, root: str | Path | None = None,
                             published_at: Any = None, universe: Mapping[str, Any] | None = None,
                             metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    root_path = Path(root or os.getenv("SIGNALIX_TREND_ROUTE_ROOT", DEFAULT_ROOT))
    published = published_at.isoformat() if hasattr(published_at, "isoformat") else str(published_at or dt.datetime.now(dt.timezone.utc).isoformat())
    compact = {str(symbol): compact_route(route) for symbol, route in sorted(routes.items())}
    for route in compact.values():
        _validate(route)
    identity_basis = {"schema_version": SCHEMA_VERSION, "policy_version": ROUTE_POLICY_VERSION,
                      "universe": universe or {}, "metadata": metadata or {}, "routes": compact}
    content_hash = _hash(identity_basis)
    artifact_id = f"trend-route-{content_hash}"
    # Publication time belongs to the mutable pointer metadata, not the
    # immutable route version identity.  Keeping it out of the version file
    # also lets a republish of identical normalized input reuse that version.
    artifact = {**identity_basis, **(dict(metadata or {})), "artifact_id": artifact_id, "identity": {"content_hash": content_hash,
                "policy_version": ROUTE_POLICY_VERSION, "universe_hash": _hash(universe or {})}}
    artifact_path = root_path / "versions" / f"{artifact_id}.json"
    _immutable(artifact_path, artifact)
    pointer = {"schema_version": SCHEMA_VERSION, "artifact_id": artifact_id,
               "artifact_path": str(Path("versions") / artifact_path.name), "published_at": published,
               "content_hash": content_hash, "policy_version": ROUTE_POLICY_VERSION,
               "universe_hash": artifact["identity"]["universe_hash"]}
    _atomic(root_path / "current.json", pointer)
    return {"artifact_id": artifact_id, "artifact_path": str(artifact_path), "pointer_path": str(root_path / "current.json")}


def read_current_route(root: str | Path | None = None, *, stale_after_seconds: float | None = None) -> dict[str, Any]:
    root_path = Path(root or os.getenv("SIGNALIX_TREND_ROUTE_ROOT", DEFAULT_ROOT))
    blocked = {"status": "NOT_VERIFIED", "verification_status": "NOT_VERIFIED", "reason_codes": ["MISSING_OR_CORRUPT_ARTIFACT"], "routes": {}}
    try:
        pointer = json.loads((root_path / "current.json").read_text())
        if pointer.get("schema_version") != SCHEMA_VERSION or not pointer.get("artifact_path"):
            raise ValueError("pointer schema mismatch")
        path = (root_path / pointer["artifact_path"]).resolve()
        if root_path.resolve() not in path.parents:
            raise ValueError("pointer escapes root")
        artifact = json.loads(path.read_text())
        if (artifact.get("artifact_id") != pointer.get("artifact_id") or artifact.get("identity", {}).get("content_hash") != pointer.get("content_hash")
                or artifact.get("policy_version") != ROUTE_POLICY_VERSION):
            raise ValueError("pointer/artifact mismatch")
        if stale_after_seconds is not None:
            published = dt.datetime.fromisoformat(str(pointer["published_at"]).replace("Z", "+00:00"))
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
            age = (dt.datetime.now(dt.timezone.utc) - published).total_seconds()
            if age > float(stale_after_seconds) or age < -60:
                raise ValueError("Trend Route artifact is stale or from the future")
        if _hash({key: artifact[key] for key in ("schema_version", "policy_version", "universe", "metadata", "routes")}) != pointer.get("content_hash"):
            raise ValueError("artifact content hash mismatch")
        routes = artifact.get("routes")
        if not isinstance(routes, dict):
            raise ValueError("routes missing")
        for route in routes.values():
            _validate(route)
        return {**artifact, "verification_status": "VERIFIED"}
    except Exception:
        return blocked


def read_symbol_route(symbol: str, *, root: str | Path | None = None) -> dict[str, Any]:
    model = read_current_route(root)
    route = model.get("routes", {}).get(str(symbol))
    if not isinstance(route, Mapping):
        return {"status": "NOT_VERIFIED", "verification_status": model.get("verification_status", "NOT_VERIFIED"),
                "reason_codes": model.get("reason_codes", ["SYMBOL_NOT_PUBLISHED"]), "symbol": symbol}
    return dict(route)


read_current = read_current_route
publish = publish_route_read_model
