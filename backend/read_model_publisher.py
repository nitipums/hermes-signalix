"""Atomic publication of the canonical setup-candidate read model.

This module owns the refresh-time boundary only.  API serving is deliberately
out of scope for T02: a caller hands it the complete result of
``build_setup_candidates_from_data`` and it writes a versioned artifact and a
small current-version pointer.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from artifact_writer import atomic_write_json
from canonical_setup_projection import _validate_canonical_setup_candidate
from setup_candidate_contract import sort_setup_candidates


CONTRACT_VERSION = "signalix.setup-candidates.read-model.v1"
EXPECTED_UNIVERSE = "marginable_long"
EXPECTED_COUNT = 237
LANES = ("REVIEW_NOW", "SETUP_FORMING", "DAILY_CANDIDATE", "WAIT", "AVOID", "DATA_BLOCKED")
DEFAULT_ROOT = Path(__file__).resolve().parent / "read-model"
INTRADAY_METADATA_FILENAME = "intraday-latest.json"
_READ_MODEL_CACHE_LIMIT = 2
_READ_MODEL_CACHE_LOCK = threading.RLock()
_READ_MODEL_CACHE: OrderedDict[tuple[str, str, str, str], dict] = OrderedDict()
_READ_MODEL_CURRENT_IDENTITIES: dict[str, tuple[str, str, str, str]] = {}


class _ReadOnlyDict(dict):
    """A JSON-serializable dict that rejects mutation of cached data."""

    def _readonly(self, *args, **kwargs):
        raise TypeError("cached read model is read-only")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _readonly


class _ReadOnlyList(list):
    """A JSON-serializable list that rejects mutation of cached data."""

    def _readonly(self, *args, **kwargs):
        raise TypeError("cached read model is read-only")

    __setitem__ = __delitem__ = __iadd__ = __imul__ = append = extend = insert = pop = remove = reverse = sort = _readonly


def _freeze_read_model(value: Any) -> Any:
    if isinstance(value, dict):
        return _ReadOnlyDict({key: _freeze_read_model(item) for key, item in value.items()})
    if isinstance(value, list):
        return _ReadOnlyList(_freeze_read_model(item) for item in value)
    return value


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _source_version(source_versions: dict[str, Any]) -> str:
    """Create a stable identity from the completed Daily/60m inputs."""
    if not isinstance(source_versions, dict) or not source_versions:
        raise ValueError("source_versions are required")
    identity = _json_bytes(source_versions)
    return "read-model-" + hashlib.sha256(identity).hexdigest()[:16]


def _validate_build(items: list[dict], metadata: dict, source_versions: dict[str, Any]) -> tuple[list[dict], dict]:
    if not isinstance(items, list) or len(items) != EXPECTED_COUNT:
        raise ValueError(f"read model requires exactly {EXPECTED_COUNT} evaluated candidates")
    if not isinstance(metadata, dict):
        raise ValueError("builder metadata must be an object")
    if metadata.get("universe_filter") != EXPECTED_UNIVERSE:
        raise ValueError("read model must be built for marginable_long")
    if metadata.get("eligible_count") != EXPECTED_COUNT:
        raise ValueError("read model eligible_count must be 237")
    if metadata.get("excluded_count") is None:
        raise ValueError("read model excluded_count is required")
    if not isinstance(source_versions, dict) or not isinstance(source_versions.get("daily"), dict) or not isinstance(source_versions.get("intraday"), dict):
        raise ValueError("completed Daily and 60m source versions are required")
    for timeframe in ("daily", "intraday"):
        version = source_versions[timeframe]
        if not (version.get("run_id") or version.get("source")) or not version.get("as_of"):
            raise ValueError(f"{timeframe} source version identity is incomplete")

    symbols = [str(item.get("symbol", "")).upper() if isinstance(item, dict) else "" for item in items]
    if any(not symbol for symbol in symbols) or len(set(symbols)) != EXPECTED_COUNT:
        raise ValueError("read model symbols must be unique and complete")
    validated = [_validate_canonical_setup_candidate(item) for item in items]
    ordered = sort_setup_candidates(copy.deepcopy(validated))
    counts = {lane: sum(item.get("decision_lane") == lane for item in ordered) for lane in LANES}
    return ordered, counts


def build_read_model(
    items: list[dict],
    metadata: dict,
    *,
    source_versions: dict[str, Any],
    published_at: str,
) -> dict:
    """Build and validate an immutable canonical read-model envelope."""
    ordered, counts = _validate_build(items, metadata, source_versions)
    source_version = _source_version(source_versions)
    provenance = {
        "source_version": source_version,
        "source_versions": copy.deepcopy(source_versions),
        "daily_source": "price_data",
        "intraday_source": "intraday_price_data",
        "freshness": copy.deepcopy(metadata.get("freshness") or {}),
        "as_of": metadata.get("scan_time"),
        "intraday_as_of": source_versions["intraday"].get("as_of") if isinstance(source_versions["intraday"], dict) else None,
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "source_version": source_version,
        "published_at": published_at,
        "policy_version": "setup-candidates-v1",
        "universe": EXPECTED_UNIVERSE,
        "items": ordered,
        "count": len(ordered),
        "evaluated_count": len(ordered),
        "counts": counts,
        "freshness": copy.deepcopy(metadata.get("freshness") or {}),
        "provenance": provenance,
        "base_active_ord_count": metadata.get("base_active_ord_count"),
        "eligible_count": metadata.get("eligible_count"),
        "excluded_count": metadata.get("excluded_count"),
        "excluded_reason": metadata.get("excluded_reason"),
        "universe_metadata": {
            key: metadata.get(key)
            for key in ("schema_version", "source_document", "effective_date")
            if metadata.get(key) is not None
        },
    }


def publish_read_model(model: dict, root: str | Path) -> dict:
    """Write a validated model version, then atomically move the current pointer.

    The model is validated again at this boundary so callers cannot bypass the
    complete-build guarantee by constructing an envelope manually.  The old
    pointer is untouched if validation or the version write fails.
    """
    if not isinstance(model, dict) or model.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("invalid canonical read-model envelope")
    items, counts = _validate_build(
        model.get("items"),
        {
            "universe_filter": model.get("universe"),
            "eligible_count": model.get("eligible_count"),
            "excluded_count": model.get("excluded_count"),
        },
        model.get("provenance", {}).get("source_versions"),
    )
    if model.get("source_version") != _source_version(model["provenance"]["source_versions"]):
        raise ValueError("read model source_version does not match source_versions")
    if items != model.get("items") or counts != model.get("counts"):
        raise ValueError("read model ordering or lane counts are not canonical")
    root = Path(root)
    versions = root / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    source_version = model["source_version"]
    version_path = versions / f"{source_version}.json"
    # A version is content-addressed by source identity and never overwritten.
    if version_path.exists():
        existing = json.loads(version_path.read_text(encoding="utf-8"))
        if existing != model:
            raise ValueError("source version already exists with different content")
    else:
        atomic_write_json(version_path, model)
    pointer = {"contract_version": CONTRACT_VERSION, "source_version": source_version, "path": str(version_path.name)}
    atomic_write_json(root / "current.json", pointer)
    return {"source_version": source_version, "path": str(version_path), "count": len(items), "counts": counts}


def _intraday_metadata_path(root: str | Path | None = None) -> Path:
    configured = os.getenv("SIGNALIX_INTRADAY_METADATA_PATH")
    if configured:
        return Path(configured)
    return Path(root or os.getenv("SIGNALIX_READ_MODEL_ROOT", DEFAULT_ROOT)) / INTRADAY_METADATA_FILENAME


def publish_intraday_metadata(metadata: dict, root: str | Path | None = None) -> dict:
    """Atomically publish the small product-scope intraday freshness seam."""
    if not isinstance(metadata, dict):
        raise ValueError("intraday metadata must be an object")
    required = ("run_id", "status", "fetch_completed_at", "universe")
    if any(not metadata.get(key) for key in required):
        raise ValueError("intraday metadata identity is incomplete")
    if metadata["universe"] != EXPECTED_UNIVERSE:
        raise ValueError("only marginable_long intraday metadata is publishable")
    if metadata["status"] not in {"full_success", "partial_success"}:
        raise ValueError("intraday metadata status is not product-eligible")
    payload = {
        "schema_version": "signalix.intraday-metadata.v1",
        "run_id": str(metadata["run_id"]),
        "status": str(metadata["status"]),
        "fetch_completed_at": str(metadata["fetch_completed_at"]),
        "universe": EXPECTED_UNIVERSE,
        "published_at": str(metadata.get("published_at") or ""),
    }
    path = _intraday_metadata_path(root)
    atomic_write_json(path, payload)
    return {"path": str(path), **payload}


def load_intraday_metadata(root: str | Path | None = None) -> dict | None:
    """Read the bounded sidecar; malformed or absent metadata is unavailable."""
    try:
        payload = json.loads(_intraday_metadata_path(root).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return None
    if (not isinstance(payload, dict)
            or payload.get("schema_version") != "signalix.intraday-metadata.v1"
            or payload.get("universe") != EXPECTED_UNIVERSE
            or payload.get("status") not in {"full_success", "partial_success"}
            or not payload.get("run_id") or not payload.get("fetch_completed_at")):
        return None
    return payload


def load_current_read_model(root: str | Path | None = None) -> dict:
    """Read and validate the atomically selected canonical model.

    The pointer is the only mutable selection boundary.  This function never
    writes, falls back to another artifact, or rebuilds a model.
    """
    root = Path(root or os.getenv("SIGNALIX_READ_MODEL_ROOT", DEFAULT_ROOT))
    root_key = str(root.resolve())

    # Keep pointer reads inside the same lock as cache selection.  This makes
    # a pointer change and the corresponding cache invalidation one operation,
    # while concurrent misses naturally become a single file load/validation.
    with _READ_MODEL_CACHE_LOCK:
        pointer_path = root / "current.json"
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if (not isinstance(pointer, dict)
                or pointer.get("contract_version") != CONTRACT_VERSION
                or not isinstance(pointer.get("source_version"), str)
                or not isinstance(pointer.get("path"), str)
                or Path(pointer["path"]).name != pointer["path"]):
            raise ValueError("invalid canonical read-model pointer")

        identity = (root_key, pointer["contract_version"], pointer["source_version"], pointer["path"])
        previous_identity = _READ_MODEL_CURRENT_IDENTITIES.get(root_key)
        if previous_identity != identity:
            if previous_identity is not None:
                _READ_MODEL_CACHE.pop(previous_identity, None)
            _READ_MODEL_CURRENT_IDENTITIES[root_key] = identity
        cached = _READ_MODEL_CACHE.get(identity)
        if cached is not None:
            _READ_MODEL_CACHE.move_to_end(identity)
            return cached

        version_path = root / "versions" / pointer["path"]
        if version_path.parent != (root / "versions") or version_path.stem != pointer["source_version"]:
            raise ValueError("canonical read-model pointer path does not match source version")
        model = json.loads(version_path.read_text(encoding="utf-8"))
        if not isinstance(model, dict) or model.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("invalid canonical read-model envelope")
        provenance = model.get("provenance")
        if not isinstance(provenance, dict):
            raise ValueError("read-model provenance is required")
        items, counts = _validate_build(
            model.get("items"),
            {
                "universe_filter": model.get("universe"),
                "eligible_count": model.get("eligible_count"),
                "excluded_count": model.get("excluded_count"),
            },
            provenance.get("source_versions"),
        )
        if (model.get("source_version") != pointer["source_version"]
                or model.get("source_version") != _source_version(provenance["source_versions"])
                or model.get("items") != items
                or model.get("counts") != counts
                or model.get("count") != EXPECTED_COUNT
                or model.get("evaluated_count") != EXPECTED_COUNT):
            raise ValueError("canonical read-model contents are not valid")

        cached = _freeze_read_model(model)
        _READ_MODEL_CACHE[identity] = cached
        _READ_MODEL_CACHE.move_to_end(identity)
        while len(_READ_MODEL_CACHE) > _READ_MODEL_CACHE_LIMIT:
            _READ_MODEL_CACHE.popitem(last=False)
        return cached


def publish_builder_result(
    builder: Callable[..., tuple[list[dict], dict]],
    *args,
    root: str | Path,
    source_versions: dict[str, Any],
    published_at: str,
    **kwargs,
) -> dict:
    """Explicit caller adapter: build fully, then publish only on success."""
    items, metadata = builder(*args, **kwargs)
    model = build_read_model(items, metadata, source_versions=source_versions, published_at=published_at)
    return publish_read_model(model, root)
