"""Compact, validated chart read model for the Trend Map drawer."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping
from threading import RLock

SCHEMA_VERSION = "signalix.chart-read-model.v1"
DEFAULT_ROOT = Path(__file__).resolve().parent / "read-model" / "charts"
# Publication is EOD for the Daily/weekly/monthly aggregates and intraday for
# 60M.  The windows are deliberately explicit: a request may use a validated
# artifact only while its publication cadence can reasonably be trusted.
FRESHNESS_SECONDS = {
    "1D": 36 * 60 * 60,
    "60M": 3 * 60 * 60,
    "1W": 14 * 24 * 60 * 60,
    "1M": 45 * 24 * 60 * 60,
}
_TIMEFRAME_SOURCES = {
    "1D": {"price_data", "derived_daily_price_data"},
    "1W": {"price_data", "derived_daily_price_data"},
    "1M": {"price_data", "derived_daily_price_data"},
    "60M": {"intraday_price_data"},
}
_ARTIFACT_SOURCES = {
    "1D": "price_data+derived_daily_price_data",
    "1W": "price_data+derived_daily_price_data",
    "1M": "price_data+derived_daily_price_data",
    "60M": "intraday_price_data",
}
_CACHE_LOCK = RLock()
_VALIDATED_CACHE: dict[tuple[str, str, str, str], dict[str, Any]] = {}


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _root(root: str | Path | None = None) -> Path:
    return Path(root or os.getenv("SIGNALIX_CHART_READ_MODEL_ROOT", DEFAULT_ROOT))


def _parse_time(value: Any) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc)


def _atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_json(value)); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_immutable(path: Path, value: Any) -> None:
    encoded = _json(value)
    if path.exists():
        if path.read_bytes() != encoded:
            raise RuntimeError("chart artifact is immutable and differs")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != encoded:
                raise RuntimeError("chart artifact is immutable and differs")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _contains_raw_history(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(key == "raw_history" or _contains_raw_history(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_raw_history(item) for item in value)
    return False


def validate_artifact(artifact: Mapping[str, Any], *, now: dt.datetime | None = None) -> dict[str, Any]:
    timeframe = artifact.get("timeframe")
    if artifact.get("schema_version") != SCHEMA_VERSION or timeframe not in FRESHNESS_SECONDS:
        raise ValueError("chart artifact schema/timeframe is invalid")
    if _contains_raw_history(artifact):
        raise ValueError("chart artifact must not contain raw history")
    if artifact.get("query_mode") != "SELECT_ONLY" or artifact.get("read_only") is not True:
        raise ValueError("chart artifact provenance is invalid")
    provenance = artifact.get("provenance")
    if (not isinstance(provenance, Mapping)
            or provenance.get("source") != _ARTIFACT_SOURCES[timeframe]
            or provenance.get("timeframe") != timeframe):
        raise ValueError("chart artifact source provenance is invalid")
    freshness = artifact.get("freshness")
    if (not isinstance(freshness, Mapping)
            or freshness.get("max_age_seconds") != FRESHNESS_SECONDS[timeframe]):
        raise ValueError("chart artifact freshness policy is invalid")
    entries = artifact.get("entries")
    if not isinstance(entries, dict) or not entries:
        raise ValueError("chart artifact entries are required")
    observed = now or dt.datetime.now(dt.timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=dt.timezone.utc)
    generated = _parse_time(artifact.get("generated_at"))
    if generated > observed or (observed - generated).total_seconds() > FRESHNESS_SECONDS[timeframe]:
        raise ValueError("chart artifact is stale")
    for symbol, payload in entries.items():
        if not isinstance(symbol, str) or not symbol or not isinstance(payload, Mapping):
            raise ValueError("chart artifact entry is invalid")
        if str(payload.get("symbol", "")).upper() != symbol or payload.get("timeframe") != timeframe:
            raise ValueError("chart artifact payload identity is invalid")
        if not isinstance(payload.get("candles"), list):
            raise ValueError("chart artifact candles are invalid")
        entry_provenance = payload.get("provenance")
        if (not isinstance(entry_provenance, Mapping)
                or entry_provenance.get("source") not in _TIMEFRAME_SOURCES[timeframe]
                or "as_of" not in entry_provenance):
            raise ValueError("chart artifact provenance is incomplete")
    if artifact.get("symbol_count") != len(artifact["entries"]):
        raise ValueError("chart artifact symbol count is invalid")
    return dict(artifact)


def build_artifact(connection: Any, symbols: list[str], timeframe: str = "1D", *, generated_at: Any = None,
                   canonical_items: Mapping[str, dict] | None = None) -> dict[str, Any]:
    timeframe = (timeframe or "1D").upper()
    if timeframe not in FRESHNESS_SECONDS:
        raise ValueError("chart read model supports only 1D, 60M, 1W, and 1M")
    normalized = sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()})
    if not normalized:
        raise ValueError("chart read model symbols are required")
    import mvp_chart_db
    entries = {}
    for symbol in normalized:
        payload = mvp_chart_db.project_chart_db_response(
            symbol, timeframe=timeframe, connection=connection,
            canonical_item=(canonical_items or {}).get(symbol),
        )
        if payload is not None:
            compact = mvp_chart_db.compact_chart_db_response(payload)
            if compact is not None:
                entries[symbol] = compact
    generated_value = (generated_at.isoformat() if hasattr(generated_at, "isoformat") else generated_at) or dt.datetime.now(dt.timezone.utc).isoformat()
    artifact = {
        "schema_version": SCHEMA_VERSION, "timeframe": timeframe, "generated_at": generated_value,
        "source": "chart_db_select", "as_of": max((p.get("as_of") or (p.get("provenance") or {}).get("as_of")
                                                       for p in entries.values()
                                                       if p.get("as_of") or (p.get("provenance") or {}).get("as_of")), default=None),
        "freshness": {"max_age_seconds": FRESHNESS_SECONDS[timeframe]},
        "provenance": {"source": _ARTIFACT_SOURCES[timeframe], "timeframe": timeframe},
        "entries": entries, "symbol_count": len(normalized), "query_mode": "SELECT_ONLY", "read_only": True,
    }
    if not entries:
        raise RuntimeError("chart read model has no usable entries")
    return validate_artifact(artifact, now=_parse_time(generated_value))


def publish(connection: Any, symbols: list[str], timeframe: str = "1D", *, root: str | Path | None = None,
            generated_at: Any = None, canonical_items: Mapping[str, dict] | None = None) -> dict[str, Any]:
    artifact = build_artifact(connection, symbols, timeframe, generated_at=generated_at,
                              canonical_items=canonical_items)
    artifact_id = f"chart-{timeframe.lower()}-{hashlib.sha256(_json(artifact)).hexdigest()[:24]}"
    artifact["artifact_id"] = artifact_id
    root_path = _root(root)
    artifact_path = root_path / "versions" / f"{artifact_id}.json"
    _write_immutable(artifact_path, artifact)
    pointer = {"schema_version": SCHEMA_VERSION, "timeframe": timeframe, "artifact_id": artifact_id,
               "artifact_path": str(Path("versions") / artifact_path.name), "generated_at": artifact["generated_at"],
               "as_of": artifact["as_of"]}
    _atomic_write(root_path / f"current-{timeframe}.json", pointer)
    return {"artifact_id": artifact_id, "artifact_path": str(artifact_path), "timeframe": timeframe,
            "entry_count": len(artifact["entries"]), "as_of": artifact["as_of"]}


def warm_current(timeframe: str = "1D", *, root: str | Path | None = None) -> bool:
    """Load and validate one current artifact into the process cache."""
    try:
        return read_current("__startup_warm__", timeframe, root=root) is not None or bool(_VALIDATED_CACHE)
    except Exception:
        return False


def read_current(symbol: str, timeframe: str = "1D", *, root: str | Path | None = None,
                 now: dt.datetime | None = None) -> dict[str, Any] | None:
    timeframe = (timeframe or "1D").upper()
    if timeframe not in FRESHNESS_SECONDS:
        return None
    root_path = _root(root)
    try:
        pointer = json.loads((root_path / f"current-{timeframe}.json").read_text())
        relative = Path(str(pointer["artifact_path"]))
        if pointer.get("schema_version") != SCHEMA_VERSION or pointer.get("timeframe") != timeframe or relative.is_absolute() or ".." in relative.parts:
            raise ValueError("chart pointer is invalid")
        artifact_id = str(pointer["artifact_id"])
        if (pointer.get("generated_at") is None or pointer.get("as_of") is None
                or not artifact_id or pointer.get("artifact_id") != artifact_id):
            raise ValueError("chart pointer identity is invalid")
        cache_key = (str(root_path.resolve()), timeframe, artifact_id, str(relative))
        with _CACHE_LOCK:
            artifact = _VALIDATED_CACHE.get(cache_key)
        if artifact is None:
            artifact = json.loads((root_path / relative).read_text())
            validate_artifact(artifact, now=now)
            if (artifact.get("artifact_id") != artifact_id
                    or artifact.get("generated_at") != pointer.get("generated_at")
                    or artifact.get("as_of") != pointer.get("as_of")
                    or artifact.get("timeframe") != timeframe):
                raise ValueError("chart pointer identity is invalid")
            with _CACHE_LOCK:
                for key in list(_VALIDATED_CACHE):
                    if key[:2] == cache_key[:2]:
                        _VALIDATED_CACHE.pop(key, None)
                _VALIDATED_CACHE[cache_key] = artifact
        else:
            # Recheck only the cheap artifact freshness boundary; full entry
            # validation happened when this pointer identity was first loaded.
            if (artifact.get("artifact_id") != artifact_id
                    or artifact.get("generated_at") != pointer.get("generated_at")
                    or artifact.get("as_of") != pointer.get("as_of")
                    or artifact.get("timeframe") != timeframe):
                raise ValueError("chart pointer identity is invalid")
            observed = now or dt.datetime.now(dt.timezone.utc)
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=dt.timezone.utc)
            generated = _parse_time(artifact["generated_at"])
            if generated > observed or (observed - generated).total_seconds() > FRESHNESS_SECONDS[timeframe]:
                raise ValueError("chart artifact is stale")
        payload = artifact["entries"].get(str(symbol).strip().upper())
        return dict(payload) if isinstance(payload, Mapping) else None
    except (OSError, TypeError, ValueError, json.JSONDecodeError, KeyError):
        return None
