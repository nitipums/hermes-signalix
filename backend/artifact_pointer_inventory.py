"""Read-only inventory and validation seam for active read-model pointers.

This module deliberately never publishes, repairs, removes, or moves anything.
It is suitable for release evidence: a missing pointer is reported as blocked,
and a malformed or tampered pointer is reported as NOT_VERIFIED.
"""
from __future__ import annotations

import hashlib
import json
import datetime as dt
from pathlib import Path
from typing import Any

import chart_read_model
import intraday_quote_read_model
import market_breadth_artifact
import trend_map_read_model_publisher


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _base(kind: str, root: str | Path | None) -> Path:
    defaults = {
        "trend_map": trend_map_read_model_publisher.DEFAULT_ROOT,
        "intraday_quotes": intraday_quote_read_model.ROOT,
        "market_breadth": market_breadth_artifact.DEFAULT_ROOT,
        "charts": chart_read_model.DEFAULT_ROOT,
    }
    if kind not in defaults:
        raise ValueError(f"unknown read-model kind: {kind}")
    return Path(root) if root is not None else defaults[kind]


def _result(kind: str, root: Path, pointer_name: str, *, status: str,
            reason: str, pointer: dict[str, Any] | None = None,
            target: Path | None = None, candidates: list[str] | None = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": status,
        "blocked": status != "VERIFIED",
        "reason": reason,
        "root": str(root),
        "pointer": pointer_name,
        "pointer_id": (pointer or {}).get("artifact_id") or (pointer or {}).get("path"),
        "target": str(target) if target is not None else None,
        "target_exists": bool(target and target.is_file()),
        "candidates": candidates or [],
    }


def _candidates(root: Path, pattern: str, target: Path | None = None) -> list[str]:
    versions = root / "versions"
    if not versions.is_dir():
        return []
    target_name = target.name if target is not None else None
    return sorted(path.name for path in versions.glob(pattern)
                  if path.is_file() and path.name != target_name)


def inspect_trend_map(root: str | Path | None = None) -> dict[str, Any]:
    root_path = _base("trend_map", root)
    pointer_name = trend_map_read_model_publisher.CURRENT_NAME
    target = None
    try:
        pointer = _read_json(root_path / pointer_name)
        relative = Path(pointer["artifact_path"])
        target = (root_path / relative).resolve()
        if relative.is_absolute() or not _inside(root_path, target):
            raise ValueError("pointer target escapes root")
        if not target.is_file():
            raise FileNotFoundError(str(target))
        trend_map_read_model_publisher._validate_pointer(root_path, pointer)
        return _result("trend_map", root_path, pointer_name, status="VERIFIED",
                       reason="pointer_target_identity_schema_content_hash_verified",
                       pointer=pointer, target=target,
                       candidates=_candidates(root_path, "*.json", target))
    except Exception as error:
        pointer = None
        try:
            pointer = _read_json(root_path / pointer_name)
        except Exception:
            pass
        return _result("trend_map", root_path, pointer_name, status="NOT_VERIFIED",
                       reason=type(error).__name__ + ": " + str(error), pointer=pointer,
                       target=target, candidates=_candidates(root_path, "*.json", target))


def inspect_intraday_quotes(root: str | Path | None = None) -> dict[str, Any]:
    root_path = _base("intraday_quotes", root)
    pointer_name = intraday_quote_read_model.CURRENT_NAME
    target = None
    try:
        pointer = _read_json(root_path / pointer_name)
        relative = Path(pointer["artifact_path"])
        target = (root_path / relative).resolve()
        if relative.is_absolute() or not _inside(root_path, target) or target.parent != (root_path / intraday_quote_read_model.VERSIONS).resolve():
            raise ValueError("pointer target escapes versions root")
        if not target.is_file():
            raise FileNotFoundError(str(target))
        artifact = _read_json(target)
        if pointer.get("schema_version") != intraday_quote_read_model.SCHEMA_VERSION:
            raise ValueError("pointer schema does not match")
        if artifact.get("schema_version") != pointer["schema_version"] or artifact.get("artifact_id") != pointer.get("artifact_id"):
            raise ValueError("pointer identity/schema does not match target")
        content = _json({key: value for key, value in artifact.items() if key != "artifact_id"})
        if _hash_bytes(content) != pointer.get("content_hash"):
            raise ValueError("pointer content hash does not match target")
        generated = dt.datetime.fromisoformat(str(artifact["generated_at"]).replace("Z", "+00:00"))
        intraday_quote_read_model.validate_artifact(artifact, now=generated)
        return _result("intraday_quotes", root_path, pointer_name, status="VERIFIED",
                       reason="pointer_target_identity_schema_content_hash_verified",
                       pointer=pointer, target=target,
                       candidates=_candidates(root_path, "*.json", target))
    except Exception as error:
        pointer = None
        try:
            pointer = _read_json(root_path / pointer_name)
        except Exception:
            pass
        return _result("intraday_quotes", root_path, pointer_name, status="NOT_VERIFIED",
                       reason=type(error).__name__ + ": " + str(error), pointer=pointer,
                       target=target, candidates=_candidates(root_path, "*.json", target))


def inspect_market_breadth(root: str | Path | None = None) -> dict[str, Any]:
    root_path = _base("market_breadth", root)
    pointer_name = "current.json"
    target = None
    try:
        pointer = _read_json(root_path / pointer_name)
        if pointer.get("artifact_version") != market_breadth_artifact.ARTIFACT_VERSION:
            raise ValueError("market breadth pointer artifact version does not match")
        relative = Path(pointer["path"])
        target = (root_path / "versions" / relative.name).resolve()
        if (relative.is_absolute() or relative.name != str(relative)
                or not _inside(root_path / "versions", target)
                or target.parent != (root_path / "versions").resolve()):
            raise ValueError("market breadth pointer target is invalid")
        raw = target.read_bytes()
        if _hash_bytes(raw) != pointer.get("content_hash"):
            raise ValueError("market breadth content hash does not match target")
        if target.name != f"market-breadth-{pointer['content_hash']}.json":
            raise ValueError("market breadth pointer identity is invalid")
        payload = _read_json(target)
        market_breadth_artifact._validate(payload, content_hash=pointer["content_hash"])
        return _result("market_breadth", root_path, pointer_name, status="VERIFIED",
                       reason="pointer_target_identity_schema_content_hash_verified",
                       pointer=pointer, target=target,
                       candidates=_candidates(root_path, "market-breadth-*.json", target))
    except FileNotFoundError:
        return _result("market_breadth", root_path, pointer_name, status="NOT_VERIFIED",
                       reason="current_pointer_missing_blocked", target=target,
                       candidates=_candidates(root_path, "market-breadth-*.json", target))
    except Exception as error:
        return _result("market_breadth", root_path, pointer_name, status="NOT_VERIFIED",
                       reason=type(error).__name__ + ": " + str(error), target=target,
                       candidates=_candidates(root_path, "market-breadth-*.json", target))


def inspect_charts(root: str | Path | None = None) -> list[dict[str, Any]]:
    root_path = _base("charts", root)
    results = []
    for timeframe in ("1D", "60M", "1W", "1M"):
        pointer_name = f"current-{timeframe}.json"
        target = None
        try:
            pointer = _read_json(root_path / pointer_name)
            relative = Path(pointer["artifact_path"])
            target = (root_path / relative).resolve()
            versions_root = (root_path / "versions").resolve()
            if (relative.is_absolute() or not _inside(versions_root, target)
                    or target.parent != versions_root):
                raise ValueError("chart pointer target is not directly under versions root")
            if not target.is_file():
                raise FileNotFoundError(str(target))
            artifact = _read_json(target)
            if (pointer.get("schema_version") != chart_read_model.SCHEMA_VERSION
                    or pointer.get("timeframe") != timeframe
                    or artifact.get("artifact_id") != pointer.get("artifact_id")
                    or artifact.get("timeframe") != timeframe
                    or pointer.get("generated_at") != artifact.get("generated_at")
                    or pointer.get("as_of") != artifact.get("as_of")):
                raise ValueError("chart pointer identity/schema does not match target")
            identity_basis = {key: value for key, value in artifact.items() if key != "artifact_id"}
            expected_id = f"chart-{timeframe.lower()}-{_hash_bytes(_json(identity_basis))[:24]}"
            if expected_id != pointer.get("artifact_id"):
                raise ValueError("chart artifact content identity does not match target")
            chart_read_model.validate_artifact(artifact)
            result = _result("chart", root_path, pointer_name, status="VERIFIED",
                             reason="pointer_target_identity_schema_content_hash_verified",
                             pointer=pointer, target=target,
                             candidates=_candidates(root_path, "*.json", target))
        except FileNotFoundError:
            result = _result("chart", root_path, pointer_name, status="NOT_VERIFIED",
                             reason="current_pointer_missing_blocked", target=target,
                             candidates=_candidates(root_path, "*.json", target))
        except Exception as error:
            result = _result("chart", root_path, pointer_name, status="NOT_VERIFIED",
                             reason=type(error).__name__ + ": " + str(error), target=target,
                             candidates=_candidates(root_path, "*.json", target))
        result["timeframe"] = timeframe
        results.append(result)
    return results


def inventory_active_read_models(*, roots: dict[str, str | Path] | None = None) -> dict[str, Any]:
    roots = roots or {}
    return {
        "trend_map": inspect_trend_map(roots.get("trend_map")),
        "intraday_quotes": inspect_intraday_quotes(roots.get("intraday_quotes")),
        "market_breadth": inspect_market_breadth(roots.get("market_breadth")),
        "charts": inspect_charts(roots.get("charts")),
    }
