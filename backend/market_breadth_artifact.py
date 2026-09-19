"""Immutable Market Breadth publication and compact read-only API."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlsplit

from artifact_writer import atomic_write_text
from market_breadth import build_direction_metadata

ARTIFACT_VERSION = "signalix.market-breadth.artifact.v2"
API_VERSION = "signalix.market-breadth.api.v2"
SCHEMA_VERSION = "signalix.market-breadth.schema.v2"
POLICY_VERSION = "market-breadth-mb1"
DEFAULT_ROOT = Path(__file__).resolve().parent / "market-breadth-read-model"
RANGES = {"20": 20, "60": 60, "260": 260, "all": None}
_RANGE_FIELDS = {key: f"history_{key}" for key in RANGES}
_CACHE_LOCK = threading.RLock()
_ARTIFACT_CACHE: dict[str, tuple[tuple[str, str, str, int, int, int], dict]] = {}


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _hash(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _public_session(session: Mapping[str, Any]) -> dict:
    """Convert one MB-1 session to the aggregate-only public shape."""
    projected = dict(session)
    details = session.get("new_high_low")
    if not isinstance(details, Mapping) or not isinstance(details.get("aggregate"), Mapping):
        raise ValueError("market breadth new_high_low aggregate is required")
    quality = (session.get("quality") or {}).get("new_high_low")
    projected["new_high_low"] = {
        "aggregate": deepcopy(dict(details["aggregate"])),
        "quality": deepcopy(dict(quality)) if isinstance(quality, Mapping) else {},
        "reason": quality.get("reason") if isinstance(quality, Mapping) else "quality_unavailable",
    }
    return projected


def _sessions(build: Mapping[str, Any]) -> list[dict]:
    dates = list(build.get("history", {}).get("sessions", []))
    result = [{"session_date": date, **dict(build["sessions"][date])}
              for date in dates if date in build.get("sessions", {})]
    if not result:
        raise ValueError("market breadth artifact has no completed sessions")
    return [_public_session(session) for session in result]


def _range_identity(field: str, sessions: list[dict], requested: int | None) -> dict:
    return {"field": field, "requested": requested, "count": len(sessions),
            "as_of": sessions[-1]["session_date"] if sessions else None,
            "content_hash": _hash(sessions)}


def _artifact_payload(build: Mapping[str, Any], metadata: Mapping[str, Any] | None) -> dict:
    metadata = dict(metadata or {})
    sessions = _sessions(build)
    ranges = {"20": sessions[-20:], "60": sessions[-60:], "260": sessions[-260:], "all": sessions[-260:]}
    directions = {f"history_{key}": build_direction_metadata(value)
                  for key, value in ranges.items()}
    counts = {key: int((metadata.get("counts") or {}).get(key, 0)) for key in ("official", "derived", "blocked", "invalid")}
    provenance = dict(metadata.get("provenance") or {})
    provenance.setdefault("source", "price_data+derived_daily_price_data")
    provenance.setdefault("timeframe", build.get("source_timeframe", "1D"))
    provenance.setdefault("query_mode", "SELECT_ONLY")
    for session in sessions:
        ratio = session.get("ad_ratio")
        if isinstance(ratio, dict) and ratio.get("value") is None:
            ratio.setdefault("reason_code", ratio.get("status", "unavailable").lower())
    payload = {
        "artifact_version": ARTIFACT_VERSION, "api_version": API_VERSION,
        "schema_version": metadata.get("schema_version", SCHEMA_VERSION),
        "policy_version": metadata.get("policy_version", build.get("policy_version", POLICY_VERSION)),
        "status": "PRODUCTION_READ_ONLY", "research_only": False, "actionability": "NONE",
        "universe": build.get("universe"), "as_of": build.get("as_of"), "current": sessions[-1],
        "history_20": ranges["20"], "history_60": ranges["60"],
        "history_260": ranges["260"], "history_all": ranges["all"],
        "directions": directions,
        "prebuilt_ranges": {
            "current": _range_identity("current", [sessions[-1]], 1),
            **{_RANGE_FIELDS[key]: {
                **_range_identity(_RANGE_FIELDS[key], value, RANGES[key]),
                "direction_hash": _hash(directions[_RANGE_FIELDS[key]]),
            } for key, value in ranges.items()},
        },
        "provenance": provenance, "quality": build.get("quality"),
        "freshness": metadata.get("freshness", {"status": "AVAILABLE", "reason": "artifact_source_declared"}),
        "source": metadata.get("source", "market-breadth-mb1"), "run_id": metadata.get("run_id"),
        "source_identity": metadata.get("source_identity", metadata.get("source")),
        "run_identity": metadata.get("run_identity", metadata.get("run_id")), "counts": counts,
    }
    if "benchmark" in metadata:
        payload["benchmark"] = deepcopy(metadata["benchmark"])
    return payload


def _validate(payload: Any, *, content_hash: str | None = None) -> dict:
    if not isinstance(payload, dict) or payload.get("artifact_version") != ARTIFACT_VERSION:
        raise ValueError("invalid market breadth artifact schema")
    required = ("api_version", "schema_version", "policy_version", "status", "universe", "as_of", "current",
                "history_20", "history_60", "history_260", "history_all", "directions", "prebuilt_ranges", "provenance", "quality", "freshness", "counts")
    if any(key not in payload for key in required) or payload.get("api_version") != API_VERSION:
        raise ValueError("invalid market breadth artifact envelope")
    if payload.get("status") != "PRODUCTION_READ_ONLY" or payload.get("research_only") is not False or payload.get("actionability") != "NONE":
        raise ValueError("invalid market breadth artifact envelope")
    universe = payload.get("universe")
    if not isinstance(universe, dict) or universe.get("name") != "active_ord":
        raise ValueError("market breadth requires the active_ord universe")
    if not isinstance(payload.get("quality"), dict) or not isinstance(payload.get("freshness"), dict):
        raise ValueError("market breadth quality is required")
    if payload["quality"].get("status") in {"STALE", "UNKNOWN", "DATA_BLOCKED"} or payload["freshness"].get("status") in {"STALE", "UNKNOWN", "DATA_BLOCKED"}:
        raise ValueError("market breadth artifact is stale or unusable")
    if not isinstance(payload.get("provenance"), dict) or not payload["provenance"].get("source"):
        raise ValueError("market breadth provenance is required")
    if "benchmark" in payload and payload["benchmark"] is not None:
        benchmark = payload["benchmark"]
        if (not isinstance(benchmark, dict) or set(benchmark) != {
                "symbol", "source", "timeframe", "close", "change_1d_pct",
                "change_20d_pct", "as_of", "quality"}):
            raise ValueError("market breadth benchmark is invalid")
        if benchmark.get("symbol") != "SET" or benchmark.get("source") != "price_data" or benchmark.get("timeframe") != "1D":
            raise ValueError("market breadth benchmark identity is invalid")
        if not isinstance(benchmark.get("quality"), dict):
            raise ValueError("market breadth benchmark quality is required")
    if not isinstance(payload["current"], dict) or not payload["current"].get("session_date"):
        raise ValueError("market breadth current is invalid")
    identities = payload["prebuilt_ranges"]
    directions = payload["directions"]
    expected_fields = {"current", "history_20", "history_60", "history_260", "history_all"}
    if not isinstance(identities, dict) or set(identities) != expected_fields:
        raise ValueError("market breadth prebuilt range identities are invalid")
    if not isinstance(directions, dict) or set(directions) != expected_fields - {"current"}:
        raise ValueError("market breadth directions are invalid")
    if payload["current"] != payload["history_all"][-1]:
        raise ValueError("market breadth current is not the latest session")
    if str(payload["as_of"])[:10] != str(payload["current"]["session_date"])[:10]:
        raise ValueError("market breadth as_of is invalid")
    for field in ("history_20", "history_60", "history_260", "history_all"):
        sessions = payload[field]
        if not isinstance(sessions, list) or not sessions:
            raise ValueError("market breadth prebuilt history is empty")
        dates = [str(item.get("session_date", ""))[:10] for item in sessions]
        if any(not isinstance(item, dict) or not item.get("session_date") for item in sessions) or dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ValueError("market breadth prebuilt history ordering is invalid")
        identity = identities[field]
        if not isinstance(identity, dict) or identity.get("field") != field or identity.get("count") != len(sessions) or identity.get("as_of") != sessions[-1]["session_date"] or identity.get("content_hash") != _hash(sessions) or identity.get("direction_hash") != _hash(directions[field]):
            raise ValueError("market breadth prebuilt range identity is invalid")
        direction = directions[field]
        if (not isinstance(direction, dict) or
                set(direction) != {"label", "status", "reason", "baseline", "endpoint", "delta", "valid_sessions"} or
                direction.get("label") not in {"Rising", "Falling", "Mixed", "Unavailable"} or
                direction.get("status") not in {"AVAILABLE", "PARTIAL", "DATA_BLOCKED"} or
                not isinstance(direction.get("valid_sessions"), int) or direction["valid_sessions"] < 0):
            raise ValueError("market breadth direction shape is invalid")
        for session in sessions:
            details = session.get("new_high_low")
            if not isinstance(details, dict) or set(details) != {"aggregate", "quality", "reason"} or not isinstance(details["aggregate"], dict) or not isinstance(details["quality"], dict):
                raise ValueError("market breadth public new_high_low projection is invalid")
    if identities["current"] != _range_identity("current", [payload["current"]], 1):
        raise ValueError("market breadth current identity is invalid")
    if content_hash is not None and content_hash != _hash(payload):
        raise ValueError("market breadth artifact content hash mismatch")
    return payload


def publish_market_breadth_artifact(build: Mapping[str, Any], *, root: str | Path, metadata: Mapping[str, Any] | None = None) -> dict:
    payload = _validate(_artifact_payload(build, metadata))
    content_hash = _hash(payload)
    root = Path(root)
    version_path = root / "versions" / f"market-breadth-{content_hash}.json"
    if version_path.exists():
        if version_path.read_bytes() != _bytes(payload):
            raise ValueError("market breadth version already exists with different content")
    else:
        atomic_write_text(version_path, _bytes(payload).decode("utf-8"))
    pointer = {"artifact_version": ARTIFACT_VERSION, "path": version_path.name, "content_hash": content_hash}
    atomic_write_text(root / "current.json", _bytes(pointer).decode("utf-8"))
    return {"path": str(version_path), **pointer}


def _read_pointer(root: Path) -> tuple[dict, Path]:
    pointer = json.loads((root / "current.json").read_text(encoding="utf-8"))
    if not isinstance(pointer, dict) or pointer.get("artifact_version") != ARTIFACT_VERSION or not isinstance(pointer.get("path"), str) or Path(pointer["path"]).name != pointer["path"] or not isinstance(pointer.get("content_hash"), str):
        raise ValueError("invalid market breadth pointer")
    path = root / "versions" / pointer["path"]
    if path.parent != root / "versions" or path.stem != f"market-breadth-{pointer['content_hash']}":
        raise ValueError("market breadth pointer identity is invalid")
    return pointer, path


def load_market_breadth_artifact(root: str | Path | None = None) -> dict:
    root = Path(root or os.getenv("SIGNALIX_MARKET_BREADTH_ROOT", DEFAULT_ROOT))
    pointer, path = _read_pointer(root)
    stat = path.stat()
    key = (str(root.resolve()), pointer["path"], pointer["content_hash"], stat.st_ino, stat.st_size, stat.st_mtime_ns)
    cache_key = str(root.resolve())
    with _CACHE_LOCK:
        cached = _ARTIFACT_CACHE.get(cache_key)
        if cached is not None and cached[0] == key:
            return deepcopy(cached[1])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer["content_hash"]:
        raise ValueError("market breadth artifact content hash mismatch")
    payload = json.loads(raw.decode("utf-8"))
    if _bytes(payload) != raw:
        raise ValueError("market breadth artifact bytes are not canonical")
    validated = _validate(payload, content_hash=pointer["content_hash"])
    with _CACHE_LOCK:
        _ARTIFACT_CACHE[cache_key] = (key, validated)
    return deepcopy(validated)


def market_breadth_response(path: str, *, loader: Callable[[], Mapping[str, Any]] | None = None) -> tuple[dict, int]:
    query = parse_qs(urlsplit(path).query, keep_blank_values=True)
    value = query.get("range", ["20"])[0]
    if value not in RANGES:
        return {"status": "DATA_BLOCKED", "reason": "invalid_range", "allowed_ranges": list(RANGES)}, 400
    try:
        # The default loader returns a fully validated, hash-bound artifact.
        # Injected loaders are the test/runtime seam for an already published
        # read model; the request path must not rescan or rebuild its slices.
        artifact = dict((loader or load_market_breadth_artifact)())
        field = _RANGE_FIELDS[value]
        history = artifact[field]
        required = RANGES[value]
        if required is not None and len(history) != required:
            raise ValueError("requested range is unavailable")
        response = {key: artifact[key] for key in ("api_version", "status", "research_only", "actionability", "universe", "as_of", "provenance", "quality", "freshness", "schema_version", "policy_version", "source", "run_id", "source_identity", "run_identity", "counts")}
        if "benchmark" in artifact:
            response["benchmark"] = deepcopy(artifact["benchmark"])
        response.update({f"{key}_count": artifact["counts"][key] for key in ("official", "derived", "blocked", "invalid")})
        response.update({"current": artifact["current"], "history": history,
                         "direction": deepcopy(artifact["directions"][field]),
                         "content_identity": {"artifact_version": artifact["artifact_version"], "content_hash": _hash(artifact), "range": field, "range_hash": artifact["prebuilt_ranges"][field]["content_hash"]}})
        return response, 200
    except Exception as error:
        return {"status": "DATA_BLOCKED", "reason": "market_breadth_artifact_unavailable", "detail": type(error).__name__}, 503


def handle_market_breadth_api(path: str, handler, *, loader: Callable[[], Mapping[str, Any]] | None = None) -> bool:
    if urlsplit(path).path != "/api/market-breadth":
        return False
    payload, status = market_breadth_response(path, loader=loader)
    body = json.dumps(payload, separators=(",", ":"), default=str).encode()
    if hasattr(handler, "send_bytes"):
        handler.send_bytes(body, content_type="application/json; charset=utf-8", status=status)
    else:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    return True
