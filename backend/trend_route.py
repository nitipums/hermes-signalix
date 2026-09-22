"""Pure, deterministic Trend Route projection.

The route is a presentation of completed Daily Main Trend observations.  It
does not recalculate Main Trend, infer actions, or retain OHLCV/indicator
arrays.  Callers may pass either snapshot envelopes or already projected
observations; the normalizer makes that boundary explicit.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from typing import Any, Iterable, Mapping

LABELS = {1: "BASING", 2: "UP", 3: "DISTRIBUTING", 4: "DOWN"}
LABEL_ORDER = ("BASING", "UP", "DISTRIBUTING", "DOWN")
ROUTE_POLICY_VERSION = "trend-route-v1"
MAX_SESSIONS = 260
_DROP_FIELDS = {"open", "high", "low", "close", "volume", "ohlcv", "series", "indicators"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()[:16]


def _date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Mapping):
        value = value.get("main_trend", value.get("value"))
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value in LABELS else None


def _snapshots(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        for key in ("snapshots", "history", "sessions", "rows"):
            if isinstance(value.get(key), list):
                return [item for item in value[key] if isinstance(item, Mapping)]
        return [value]
    return [item for item in (value or []) if isinstance(item, Mapping)]


def normalize_snapshot(snapshot: Mapping[str, Any], *, symbol: str | None = None) -> dict[str, Any] | None:
    """Normalize one completed Daily observation without exposing raw history."""
    when = snapshot.get("date", snapshot.get("as_of", snapshot.get("session_date")))
    date = _date(when)
    numeric = _numeric(snapshot.get("main_trend", snapshot.get("trend", snapshot.get("value"))))
    if date is None or numeric is None:
        return None
    policy = snapshot.get("policy_version", snapshot.get("policy", ROUTE_POLICY_VERSION))
    if isinstance(policy, Mapping):
        policy = policy.get("main_trend_classifier", policy.get("version", ROUTE_POLICY_VERSION))
    return {"date": date.isoformat(), "session": date.isoformat(), "main_trend": numeric,
            "label": LABELS[numeric], "policy_version": str(policy),
            "symbol": str(snapshot.get("symbol", symbol)) if snapshot.get("symbol", symbol) is not None else None,
            "source": str(snapshot.get("source", "published_read_model"))}


def _is_gap(previous: dt.date, current: dt.date, previous_policy: str, current_policy: str,
            expected_sessions: set[dt.date] | None = None) -> tuple[bool, str | None]:
    if previous_policy != current_policy:
        return True, "POLICY_CHANGED"
    if current <= previous:
        return True, "INVALID_SESSION_ORDER"
    if expected_sessions is None:
        return False, None
    missing = any(previous < session < current for session in expected_sessions)
    return missing, "MISSING_SESSION_GAP" if missing else None


def build_route(snapshots: Any, *, symbol: str | None = None, cutoff: Any = None,
                max_sessions: int = MAX_SESSIONS, expected_sessions: Iterable[Any] | None = None) -> dict[str, Any]:
    """Build a compact route from completed observations up to one cutoff."""
    cutoff_date = _date(cutoff) if cutoff is not None else None
    normalized = [normalize_snapshot(item, symbol=symbol) for item in _snapshots(snapshots)]
    normalized = [item for item in normalized if item and (cutoff_date is None or _date(item["date"]) <= cutoff_date)]
    normalized.sort(key=lambda item: (item["date"], item["symbol"] or ""))
    if symbol is not None:
        normalized = [item for item in normalized if item["symbol"] in (None, symbol)]
    # A route is bounded to the newest completed sessions; this is also the
    # only history that can be represented by the public read model.
    session_limit = max(1, int(max_sessions))
    normalized = normalized[-session_limit:]
    expected = {_date(value) for value in (expected_sessions or [])}
    expected.discard(None)
    if cutoff_date is not None:
        expected = {value for value in expected if value <= cutoff_date}
    if expected:
        expected = set(sorted(expected)[-session_limit:])
    observed_dates = {_date(item["date"]) for item in normalized}
    missing_expected = expected - observed_dates if expected else set()
    points: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    gap_count = 0
    for item in normalized:
        current = dict(item)
        current["id"] = "session-" + _hash({key: current[key] for key in ("date", "main_trend", "policy_version")})
        points.append(current)
    for index, point in enumerate(points):
        previous = points[index - 1] if index else None
        gap, reason = _is_gap(_date(previous["date"]) if previous else _date(point["date"]), _date(point["date"]),
                              previous["policy_version"] if previous else point["policy_version"], point["policy_version"], expected) if previous else (False, None)
        if gap:
            gap_count += 1
        starts = not segments or gap or point["label"] != segments[-1]["label"]
        if starts:
            segment = {"label": point["label"], "trend": point["main_trend"], "start": point["date"],
                       "end": point["date"], "sessions": 1, "gap_before": reason,
                       "id": "segment-" + _hash({"symbol": symbol, "label": point["label"], "start": point["date"], "policy": point["policy_version"]})}
            segments.append(segment)
        else:
            segments[-1]["end"] = point["date"]
            segments[-1]["sessions"] += 1
        if previous and (gap or point["label"] != previous["label"]):
            transitions.append({"id": "transition-" + _hash({"from": previous["label"], "to": point["label"], "date": point["date"], "gap": gap}),
                                "from": previous["label"], "to": point["label"], "date": point["date"],
                                "from_trend": previous["main_trend"], "to_trend": point["main_trend"],
                                "observed": not gap, "reason": reason if gap else "LABEL_CHANGED"})
    effective_cutoff = cutoff_date or (_date(points[-1]["date"]) if points else None)
    current_segment_id = None
    if effective_cutoff is not None:
        for segment in segments:
            segment["current"] = segment["end"] == effective_cutoff.isoformat()
            segment["main_trend"] = segment["trend"]
            segment["quality"] = "VERIFIED" if segment["sessions"] > 0 else "NOT_VERIFIED"
            segment["provenance"] = {"source": "published_daily_main_trend", "timeframe": "1D"}
            segment["date"] = segment["end"]
            segment["session_count"] = segment["sessions"]
            if segment["current"]:
                current_segment_id = segment["id"]
    durations = {label: {"sessions": sum(s["sessions"] for s in segments if s["label"] == label),
                         "segments": sum(s["label"] == label for s in segments)} for label in LABEL_ORDER}
    complete = bool(points) and gap_count == 0 and not missing_expected and all(point["policy_version"] == points[0]["policy_version"] for point in points)
    status = "FULL" if complete else "PARTIAL" if points else "NOT_VERIFIED"
    reasons = [] if complete else (["NO_VALID_SESSIONS"] if not points else (["MISSING_SESSION_GAP"] if gap_count or missing_expected else ["POLICY_CHANGED"]))
    return {"symbol": symbol, "status": status, "reason_codes": reasons, "policy_version": ROUTE_POLICY_VERSION,
            "coverage": {"status": status, "sessions": len(points), "max_sessions": int(max_sessions),
                         "first_session": points[0]["date"] if points else None, "latest_session": points[-1]["date"] if points else None,
                         "gap_count": gap_count, "expected_sessions": len(expected),
                         "missing_expected_sessions": len(missing_expected), "no_lookahead": True},
            "segments": [{key: value for key, value in segment.items()} for segment in segments],
            "current_segment": current_segment_id,
            "transitions": transitions, "duration_summaries": durations, "observations": points,
            "provenance": {"source": "published_daily_main_trend", "timeframe": "1D", "query_mode": "READ_MODEL", "no_lookahead": True}}


def compact_route(route: Mapping[str, Any]) -> dict[str, Any]:
    """Remove observation internals from the symbol-scoped public payload."""
    result = dict(route)
    result["observations"] = [{key: row[key] for key in ("id", "date", "session", "main_trend", "label", "policy_version") if key in row}
                              for row in route.get("observations", []) if isinstance(row, Mapping)]
    return result


class TrendRouteError(ValueError):
    pass


# Small compatibility names keep the pure seam easy to discover for callers
# without creating a second implementation or a second route contract.
build_trend_route = build_route
build_semantic_route = build_route
normalize_snapshots = lambda snapshots, **kwargs: [item for raw in _snapshots(snapshots)
                                                   if (item := normalize_snapshot(raw, **kwargs)) is not None]
