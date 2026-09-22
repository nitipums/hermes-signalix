"""Compact, immutable display-quote read model for the Daily Trend Map.

The producer is called after an intraday ingestion summary has been committed.
It performs only bounded SELECTs and publishes a version plus an atomic pointer;
the HTTP reader validates the pointer and version without opening PostgreSQL.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from trend_map import BackendDailyAdapter, UNIVERSE, _finite

ROOT = Path(__file__).resolve().parent / "trend-map-read-model" / "intraday-quotes"
CURRENT_NAME = "current.json"
VERSIONS = "versions"
SCHEMA_VERSION = "signalix.intraday-quote-read-model.v1"
FRESHNESS_POLICY = {"max_age_seconds": 2 * 60 * 60, "expires_after_seconds": 2 * 60 * 60}


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_json(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_immutable(path: Path, value: Any) -> None:
    encoded = _json(value)
    if path.exists():
        if path.read_bytes() != encoded:
            raise RuntimeError("intraday quote artifact is immutable and differs")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != encoded:
                raise RuntimeError("intraday quote artifact is immutable and differs")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _root(root: str | Path | None = None) -> Path:
    return Path(root or os.getenv("SIGNALIX_INTRADAY_QUOTE_ROOT", ROOT))


def _iso(value: Any) -> str:
    if value is None:
        return dt.datetime.now(dt.timezone.utc).isoformat()
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _symbols(adapter: BackendDailyAdapter, conn: Any) -> list[str]:
    symbols, _ = adapter.resolve_universe(conn, UNIVERSE)
    if not isinstance(symbols, list) or any(not isinstance(symbol, str) or not symbol for symbol in symbols):
        raise ValueError("canonical universe is invalid")
    return symbols


def _validate_item(item: Mapping[str, Any]) -> None:
    if not isinstance(item.get("symbol"), str):
        raise ValueError("quote symbol is invalid")
    if item.get("status") not in {"AVAILABLE", "UNAVAILABLE"}:
        raise ValueError("quote status is invalid")
    if item.get("status") == "AVAILABLE":
        for key in ("latest_completed_60m", "price", "daily_baseline"):
            if not item.get(key):
                raise ValueError("available quote is incomplete")
        if not _finite(item["price"]) or not _finite(item["daily_baseline"]["close"]):
            raise ValueError("quote value is invalid")
        if item["daily_baseline"].get("source") not in {"price_data", "derived_daily_price_data"}:
            raise ValueError("daily baseline source is invalid")


def validate_artifact(artifact: Mapping[str, Any], *, now: dt.datetime | None = None,
                      check_freshness: bool = True) -> dict[str, Any]:
    if artifact.get("schema_version") != SCHEMA_VERSION or artifact.get("query_mode") != "SELECT_ONLY":
        raise ValueError("intraday quote artifact schema/provenance is invalid")
    if artifact.get("universe", {}).get("scope") != UNIVERSE:
        raise ValueError("intraday quote artifact universe is invalid")
    quotes = artifact.get("quotes")
    symbols = artifact.get("universe", {}).get("symbols")
    if not isinstance(quotes, list) or not isinstance(symbols, list) or len(quotes) != len(symbols):
        raise ValueError("intraday quote artifact coverage is invalid")
    if [item.get("symbol") for item in quotes if isinstance(item, Mapping)] != symbols:
        raise ValueError("intraday quote artifact order is invalid")
    for item in quotes:
        if not isinstance(item, Mapping):
            raise ValueError("intraday quote item is invalid")
        _validate_item(item)
    generated = dt.datetime.fromisoformat(str(artifact["generated_at"]).replace("Z", "+00:00"))
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=dt.timezone.utc)
    if check_freshness:
        observed = now or dt.datetime.now(dt.timezone.utc)
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=dt.timezone.utc)
        if generated > observed:
            raise ValueError("intraday quote artifact was generated in the future")
        age = max(0.0, (observed - generated).total_seconds())
        if age > float(artifact.get("freshness_policy", {}).get("expires_after_seconds", 0)):
            raise ValueError("intraday quote artifact is stale")
        for item in quotes:
            stamp = item.get("latest_completed_60m") if isinstance(item, Mapping) else None
            if stamp:
                latest = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                if latest.tzinfo is None:
                    latest = latest.replace(tzinfo=dt.timezone.utc)
                if latest > observed:
                    raise ValueError("intraday quote artifact contains a future observation")
    return dict(artifact)


def build_artifact(conn: Any, summary: Mapping[str, Any], *, adapter: BackendDailyAdapter | None = None,
                   generated_at: Any = None) -> dict[str, Any]:
    adapter = adapter or BackendDailyAdapter()
    symbols = _symbols(adapter, conn)
    observed = adapter.load_intraday_quotes(conn, symbols, now=dt.datetime.now(dt.timezone.utc))
    quotes = []
    for symbol in symbols:
        item = observed.get(symbol)
        if item is None:
            quotes.append({"symbol": symbol, "status": "UNAVAILABLE"})
            continue
        baseline_source = item["daily_source"]
        price = float(item["close"])
        baseline = float(item["daily_close"])
        change = price - baseline
        quotes.append({
            "symbol": symbol, "status": "AVAILABLE",
            "latest_completed_60m": item["ts"], "price": price,
            "change_amount": change, "change_pct": change / baseline * 100,
            "change_basis": "previous_daily_close",
            "daily_baseline": {"date": item["daily_date"], "source": baseline_source,
                               "timeframe": "1D", "close": baseline},
        })
    generated_value = _iso(generated_at)
    artifact = {
        "schema_version": SCHEMA_VERSION, "generated_at": generated_value,
        "source_run": {"run_id": summary.get("run_id"), "status": summary.get("status"),
                        "fetch_completed_at": summary.get("fetch_completed_at")},
        "universe": {"scope": UNIVERSE, "symbols": symbols, "symbol_count": len(symbols),
                     "symbol_hash": hashlib.sha256("\n".join(symbols).encode()).hexdigest()},
        "quotes": quotes, "freshness_policy": dict(FRESHNESS_POLICY),
        "query_mode": "SELECT_ONLY", "read_only": True,
    }
    validate_artifact(artifact, now=dt.datetime.fromisoformat(generated_value.replace("Z", "+00:00")))
    return artifact


def publish(conn: Any, summary: Mapping[str, Any], *, root: str | Path | None = None,
            adapter: BackendDailyAdapter | None = None, generated_at: Any = None) -> dict[str, Any]:
    root_path = _root(root)
    artifact = build_artifact(conn, summary, adapter=adapter, generated_at=generated_at)
    digest = hashlib.sha256(_json(artifact)).hexdigest()
    artifact_id = f"intraday-quotes-{artifact['source_run'].get('run_id') or 'unknown'}-{digest[:24]}"
    artifact["artifact_id"] = artifact_id
    path = root_path / VERSIONS / f"{artifact_id}.json"
    _write_immutable(path, artifact)
    pointer = {"schema_version": SCHEMA_VERSION, "artifact_id": artifact_id,
               "artifact_path": str(Path(VERSIONS) / path.name),
               "generated_at": artifact["generated_at"], "content_hash": digest}
    _atomic_write(root_path / CURRENT_NAME, pointer)
    return {"artifact_id": artifact_id, "artifact_path": str(path), "pointer_path": str(root_path / CURRENT_NAME),
            "symbol_count": len(artifact["quotes"])}


def read_current(root: str | Path | None = None, *, now: dt.datetime | None = None) -> dict[str, Any]:
    root_path = _root(root)
    pointer = json.loads((root_path / CURRENT_NAME).read_text())
    if pointer.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("intraday quote pointer schema is invalid")
    artifact_path = root_path / pointer["artifact_path"]
    if artifact_path.resolve().parent != (root_path / VERSIONS).resolve():
        raise ValueError("intraday quote pointer escapes versions directory")
    artifact = json.loads(artifact_path.read_text())
    if artifact.get("artifact_id") != pointer.get("artifact_id"):
        raise ValueError("intraday quote pointer identity is invalid")
    if hashlib.sha256(_json({key: value for key, value in artifact.items() if key != "artifact_id"})).hexdigest() != pointer.get("content_hash"):
        raise ValueError("intraday quote artifact hash is invalid")
    validate_artifact(artifact, now=now)
    return artifact
