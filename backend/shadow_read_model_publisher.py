"""Immutable, file-backed publisher for the production-read-only Daily Trend Map.

The publisher is the only path that may classify Daily history.  HTTP reads
only ``current.json`` and its referenced immutable version artifact.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

import shadow_trend_map as trend_map

DEFAULT_ROOT = Path(__file__).with_name("shadow-read-model")
CURRENT_NAME = "current.json"
ARTIFACT_DIR = "versions"
SCHEMA_VERSION = "daily-trend-map-shadow-read-model-v2"
DEFAULT_STALE_AFTER_SECONDS = 48 * 60 * 60
FAILURE_METADATA_NAME = "last-publish-failure.json"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_immutable(path: Path, value: Any) -> None:
    encoded = _json_bytes(value)
    if path.exists():
        if path.read_bytes() != encoded:
            raise RuntimeError(f"immutable shadow artifact already differs: {path.name}")
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
                raise RuntimeError(f"immutable shadow artifact already differs: {path.name}")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def record_publish_failure(root: str | Path | None, error: Exception, failure_count: int,
                           pointer_preserved: bool, pointer_verification: str) -> dict[str, Any]:
    """Atomically retain only bounded, read-only observability metadata."""
    root_path = Path(root or os.getenv("SIGNALIX_SHADOW_READ_MODEL_ROOT", DEFAULT_ROOT))
    metadata = {"event": "shadow_trend_map_publish_failure",
                "error_type": type(error).__name__, "message": str(error)[:240],
                "failure_count": int(failure_count), "pointer_preserved": bool(pointer_preserved),
                "pointer_verification": pointer_verification,
                "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    _atomic_write(root_path / FAILURE_METADATA_NAME, metadata)
    return metadata


def _read_failure_metadata(root: Path) -> dict[str, Any] | None:
    try:
        value = json.loads((root / FAILURE_METADATA_NAME).read_text())
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _iso(value: Any) -> str:
    if value is None:
        return dt.datetime.now(dt.timezone.utc).isoformat()
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _validate_report(report: Mapping[str, Any]) -> dict[str, int]:
    if (report.get("status") not in {trend_map.PRODUCTION_READ_ONLY, "DATA_BLOCKED"}
            or report.get("research_only") is not False
            or report.get("actionability") != trend_map.ACTIONABILITY
            or report.get("universe", {}).get("scope") != trend_map.UNIVERSE):
        raise ValueError("production read-only report policy or universe is invalid")
    if report.get("provenance", {}).get("source") != "price_data" or report.get("provenance", {}).get("query_mode") != "SELECT_ONLY":
        raise ValueError("shadow report provenance is invalid")
    if report.get("policy", {}).get("representation_revision") != trend_map.REPRESENTATION_REVISION:
        raise ValueError("shadow report representation revision is invalid")
    rows = report.get("rows")
    symbols = report.get("universe", {}).get("declared_symbols")
    if not isinstance(rows, list) or not isinstance(symbols, list) or len(rows) != len(symbols):
        raise ValueError("shadow report does not cover the declared universe")
    if [row.get("symbol") for row in rows] != symbols:
        raise ValueError("shadow rows are not in declared-universe order")
    for row in rows:
        if (row.get("retrieval_cap") != trend_map.RETRIEVAL_CAP
                or row.get("cap") != trend_map.RETRIEVAL_CAP
                or not isinstance(row.get("retrieval_cap_reached"), bool)
                or row.get("cap_reached") != row.get("retrieval_cap_reached")):
            raise ValueError("shadow row retrieval cap provenance is invalid")
        if row.get("retrieval_cap_reached") and (
                row.get("status") == "AVAILABLE" or row.get("data_quality_status") == "AVAILABLE"):
            if (row.get("quality_established") is not True
                    or row.get("invalid_count") != 0
                    or row.get("full_history_claim") is not False):
                raise ValueError("cap-hit shadow row cannot be published as AVAILABLE without established zero-invalid quality")
        quote = row.get("quote")
        if not isinstance(quote, Mapping):
            raise ValueError("shadow row quote envelope is invalid")
        if quote.get("source") != "price_data" or quote.get("provisional") is not False:
            raise ValueError("shadow row quote provenance is invalid")
        quote_provenance = quote.get("provenance")
        if (not isinstance(quote_provenance, Mapping)
                or quote_provenance.get("source") != "price_data"
                or quote_provenance.get("table") != "price_data"
                or quote_provenance.get("timeframe") != "1D"
                or quote_provenance.get("latest_completed_daily_close") is not True):
            raise ValueError("shadow row quote provenance is invalid")
        if quote.get("change_basis") not in {"previous_daily_close", "NOT_VERIFIED"} or quote.get("change_amount_basis") not in {"previous_daily_close", "NOT_VERIFIED"}:
            raise ValueError("shadow row quote change basis is invalid")
        price = quote.get("price")
        amount = quote.get("change_amount")
        percent = quote.get("change_pct")
        if any(value is not None and not trend_map._finite(value) for value in (price, amount, percent)):
            raise ValueError("shadow row quote values are invalid")
        if quote.get("availability") not in {"AVAILABLE", "NOT_VERIFIED"} or quote.get("change_availability") not in {"AVAILABLE", "NOT_VERIFIED"}:
            raise ValueError("shadow row quote availability is invalid")
        if quote.get("availability") == "AVAILABLE" and price is None:
            raise ValueError("shadow row quote availability does not match price")
        if quote.get("change_availability") == "AVAILABLE" and (amount is None or percent is None):
            raise ValueError("shadow row quote availability does not match change")
        if quote.get("change_availability") == "AVAILABLE" and quote.get("change_basis") != "previous_daily_close":
            raise ValueError("shadow row quote change basis is invalid")
    blocked = sum(row.get("status") == "DATA_BLOCKED" for row in rows)
    counts = {"declared": len(symbols), "evaluated": len(rows), "returned": len(rows), "blocked": blocked}
    declared = report.get("universe", {}).get("declared_count")
    if declared != counts["declared"]:
        raise ValueError("declared universe count mismatch")
    return counts


def _validate_timing(timing: Mapping[str, Any]) -> None:
    required = ("db_read_ms", "classify_ms", "serialize_write_ms", "total_ms")
    if any(key not in timing or not trend_map._finite(timing[key]) or float(timing[key]) < 0 for key in required):
        raise ValueError("shadow artifact timing is invalid")
    if timing.get("measurement_scope") != "pre_immutable_write":
        raise ValueError("shadow artifact timing scope is invalid")


def _artifact(report: Mapping[str, Any], published_at: str,
              timing: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    counts = _validate_report(report)
    policy_hash = report.get("policy", {}).get("hash")
    as_of = str(report.get("as_of"))
    universe_hash = report.get("universe", {}).get("symbol_hash") or trend_map._hash(report["universe"]["declared_symbols"])
    if not policy_hash or not as_of or as_of == "None":
        raise ValueError("shadow report identity is incomplete")
    representation_revision = trend_map.REPRESENTATION_REVISION
    persisted_timing = dict(timing or report.get("timing") or {})
    _validate_timing(persisted_timing)
    version_id = f"shadow-trend-map-{representation_revision}-{as_of}-{policy_hash[:16]}-{universe_hash[:16]}"
    artifact = dict(report)
    artifact.pop("timing", None)
    artifact.update({
        "schema_version": SCHEMA_VERSION,
        "artifact_id": version_id,
        "published_at": published_at,
        "identity": {"representation_revision": representation_revision,
                     "policy_hash": policy_hash, "as_of": as_of, "universe_hash": universe_hash},
        "counts": counts,
        "source": "shadow_read_model_publisher",
        "timing": persisted_timing,
    })
    # Timing is measurement metadata, not classification evidence. It is
    # persisted for read-back, and its fingerprint plus publication timestamp
    # make each changed immutable payload a distinct version.
    content_hash = _content_hash(artifact)
    measurement_hash = _measurement_hash(artifact)
    artifact["identity"] = {**artifact["identity"], "content_hash": content_hash,
                             "measurement_hash": measurement_hash}
    version_id = f"{version_id}-{content_hash}-{measurement_hash}"
    artifact["artifact_id"] = version_id
    return version_id, artifact


def _content_hash(artifact: Mapping[str, Any]) -> str:
    basis = dict(artifact)
    for key in ("artifact_id", "published_at", "timing"):
        basis.pop(key, None)
    identity = dict(basis.get("identity") or {})
    identity.pop("content_hash", None)
    identity.pop("measurement_hash", None)
    basis["identity"] = identity
    return trend_map._hash(basis)[:16]


def _measurement_hash(artifact: Mapping[str, Any]) -> str:
    return trend_map._hash({"published_at": artifact.get("published_at"),
                            "timing": artifact.get("timing")})[:16]


def _validate_pointer(root: Path, pointer: Mapping[str, Any]) -> dict[str, Any]:
    required = ("artifact_id", "artifact_path", "published_at", "as_of", "policy_hash", "universe_hash", "representation_revision", "content_hash", "measurement_hash")
    if any(not pointer.get(key) for key in required):
        raise ValueError("current shadow pointer is incomplete")
    if pointer.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("current shadow pointer schema version is invalid")
    if Path(pointer["artifact_path"]).is_absolute():
        raise ValueError("current shadow pointer path must be relative")
    artifact_path = (root / pointer["artifact_path"]).resolve()
    if root.resolve() not in artifact_path.parents:
        raise ValueError("current shadow pointer escapes its root")
    artifact = json.loads(artifact_path.read_text())
    if (artifact.get("artifact_id") != pointer["artifact_id"]
            or artifact.get("schema_version") != SCHEMA_VERSION
            or pointer["representation_revision"] != trend_map.REPRESENTATION_REVISION
            or artifact.get("identity", {}).get("representation_revision") != pointer["representation_revision"]
            or artifact.get("identity", {}).get("policy_hash") != pointer["policy_hash"]
            or artifact.get("identity", {}).get("as_of") != pointer["as_of"]
            or artifact.get("identity", {}).get("universe_hash") != pointer["universe_hash"]):
        raise ValueError("current shadow pointer does not match its artifact")
    if artifact.get("published_at") != pointer["published_at"]:
        raise ValueError("current shadow pointer publication time does not match its artifact")
    _validate_report(artifact)
    _validate_timing(artifact.get("timing", {}))
    identity = artifact["identity"]
    if (pointer.get("content_hash") != identity.get("content_hash")
            or pointer.get("measurement_hash") != identity.get("measurement_hash")
            or identity.get("content_hash") != _content_hash(artifact)
            or identity.get("measurement_hash") != _measurement_hash(artifact)):
        raise ValueError("current shadow artifact content or measurement hash is invalid")
    return artifact


def read_current_shadow_report(root: str | Path | None = None) -> dict[str, Any]:
    root_path = Path(root or os.getenv("SIGNALIX_SHADOW_READ_MODEL_ROOT", DEFAULT_ROOT))
    started = time.perf_counter()
    try:
        pointer_path = root_path / CURRENT_NAME
        pointer = json.loads(pointer_path.read_text())
        artifact = _validate_pointer(root_path, pointer)
        published_at = dt.datetime.fromisoformat(str(pointer["published_at"]).replace("Z", "+00:00"))
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=dt.timezone.utc)
        age_seconds = max(0.0, (dt.datetime.now(dt.timezone.utc) - published_at).total_seconds())
        threshold = float(os.getenv("SIGNALIX_SHADOW_STALE_AFTER_SECONDS", DEFAULT_STALE_AFTER_SECONDS))
        freshness_status = "STALE" if age_seconds > threshold else "FRESH"
        result = dict(artifact)
        result["artifact"] = {"id": pointer["artifact_id"], "path": str((root_path / pointer["artifact_path"]).resolve()), "published_at": pointer["published_at"]}
        result["freshness"] = {"status": freshness_status, "published_at": pointer["published_at"],
                                "as_of": artifact.get("as_of"), "age_seconds": round(age_seconds, 3),
                                "stale_after_seconds": threshold}
        result["read_path"] = {"latency_ms": round((time.perf_counter() - started) * 1000, 3),
                                "cache": "pointer_artifact", "validated_every_request": True,
                                "artifact_id": pointer["artifact_id"]}
        result["cache"] = {"status": "pointer_artifact", "ttl_seconds": 0, "as_of": artifact.get("as_of"), "policy_hash": artifact.get("policy", {}).get("hash")}
        result["last_failure"] = _read_failure_metadata(root_path)
        if freshness_status == "STALE":
            blocked = trend_map.unavailable_report(RuntimeError("shadow artifact is stale"))
            blocked["freshness"] = result["freshness"]
            blocked["read_path"] = result["read_path"]
            blocked["artifact"] = result["artifact"]
            blocked["last_failure"] = result["last_failure"]
            return blocked
        return result
    except Exception as error:
        blocked = trend_map.unavailable_report(error)
        blocked["read_path"] = {"latency_ms": round((time.perf_counter() - started) * 1000, 3),
                                 "cache": "pointer_artifact", "validated_every_request": True}
        return blocked | {"artifact": {"id": None, "path": str(root_path / CURRENT_NAME), "published_at": None}, "source": "shadow_read_model_pointer", "last_failure": _read_failure_metadata(root_path), "freshness": {"status": "UNKNOWN", "published_at": None, "age_seconds": None, "stale_after_seconds": DEFAULT_STALE_AFTER_SECONDS}}


def publish_shadow_read_model(*, adapter=None, conn=None, as_of=None, root: str | Path | None = None, published_at=None) -> dict[str, Any]:
    """Build, validate, and atomically publish one bounded shadow artifact."""
    root_path = Path(root or os.getenv("SIGNALIX_SHADOW_READ_MODEL_ROOT", DEFAULT_ROOT))
    started = time.perf_counter()
    report = trend_map.build_shadow_report(adapter=adapter, conn=conn, as_of=as_of, source="publisher")
    if (report.get("status") != trend_map.PRODUCTION_READ_ONLY
            or report.get("research_only") is not False
            or report.get("actionability") != trend_map.ACTIONABILITY
            or report.get("verification_status") != "VERIFIED"):
        raise RuntimeError("shadow report is not fully verified")
    serialize_started = time.perf_counter()
    published_at_value = _iso(published_at)
    # These are deliberately measured before immutable publication so the
    # exact values written into the artifact are known before _write_immutable.
    # They describe publisher preparation, while read_path.latency_ms describes
    # the later HTTP pointer/artifact read.
    report_timing = report.get("timing", {})
    timing = {"db_read_ms": report_timing.get("db_read_ms", 0.0),
              "classify_ms": report_timing.get("classify_ms", 0.0),
              "serialize_write_ms": 0.0,
              "total_ms": 0.0,
              "measurement_scope": "pre_immutable_write"}
    version_id, artifact = _artifact(report, published_at_value, timing)
    _json_bytes(artifact)
    timing["serialize_write_ms"] = round((time.perf_counter() - serialize_started) * 1000, 3)
    timing["total_ms"] = round((time.perf_counter() - started) * 1000, 3)
    version_id, artifact = _artifact(report, published_at_value, timing)
    artifact_path = root_path / ARTIFACT_DIR / f"{version_id}.json"
    _write_immutable(artifact_path, artifact)
    pointer = {"schema_version": SCHEMA_VERSION, "artifact_id": version_id, "artifact_path": str(Path(ARTIFACT_DIR) / artifact_path.name), "published_at": artifact["published_at"], "as_of": artifact["as_of"], "representation_revision": artifact["identity"]["representation_revision"], "policy_hash": artifact["identity"]["policy_hash"], "universe_hash": artifact["identity"]["universe_hash"], "content_hash": artifact["identity"]["content_hash"], "measurement_hash": artifact["identity"]["measurement_hash"]}
    _atomic_write(root_path / CURRENT_NAME, pointer)
    return {"artifact_id": version_id, "artifact_path": str(artifact_path), "pointer_path": str(root_path / CURRENT_NAME), "counts": artifact["counts"], "as_of": artifact["as_of"], "published_at": artifact["published_at"], "timing": timing}


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the bounded Daily trend-map shadow read model")
    parser.add_argument("--root", default=None)
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()
    print(json.dumps(publish_shadow_read_model(root=args.root, as_of=args.as_of), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
