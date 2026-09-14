"""Point-in-time seven-day market replay for the private shadow UI."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from actionable_signal_policy import POLICY_VERSION, project_market_buy_signal


SCHEMA_VERSION = "shadow-market-buy-signals-v1"
WINDOW_DAYS = 7


def _session_boundaries(pg, *, now: datetime, days: int = WINDOW_DAYS) -> list[tuple[Any, Any]]:
    """Return each Thai session and its last stored completed 60m timestamp."""
    cur = pg.cursor()
    try:
        cur.execute(
            """SELECT (ts AT TIME ZONE 'Asia/Bangkok')::date AS session_date,
                      MAX(ts) AS completed_60m_as_of
               FROM intraday_price_data
               WHERE interval='60m' AND ts >= %s AND ts <= %s
               GROUP BY 1 ORDER BY 1""",
            (now - timedelta(days=days), now),
        )
        return list(cur.fetchall())
    finally:
        cur.close()


def _event_key(signal: dict) -> tuple:
    plan = signal.get("plan") or {}
    return (
        signal.get("symbol"), plan.get("trigger"), plan.get("trade_stop"),
        plan.get("target_1"), signal.get("policy_version"),
    )


def build_shadow_buy_replay(
    pg,
    *,
    now: datetime | None = None,
    days: int = WINDOW_DAYS,
    candidate_builder: Callable | None = None,
    session_loader: Callable | None = None,
) -> dict:
    """Re-evaluate trailing sessions with strict point-in-time boundaries."""
    if days != WINDOW_DAYS:
        raise ValueError("only the seven-day shadow window is supported")
    observed_now = now or datetime.now(timezone.utc)
    if observed_now.tzinfo is None:
        observed_now = observed_now.replace(tzinfo=timezone.utc)
    if candidate_builder is None:
        from mvp_api import build_setup_candidates_from_data
        candidate_builder = build_setup_candidates_from_data
    loader = session_loader or _session_boundaries
    sessions = loader(pg, now=observed_now, days=days)

    events: dict[tuple, dict] = {}
    evaluated_observations = 0
    session_summaries = []
    for session_date, completed_as_of in sessions:
        candidates, metadata = candidate_builder(
            pg, as_of=session_date, completed_60m_as_of=completed_as_of
        )
        candidates = candidates if isinstance(candidates, list) else []
        evaluated_observations += len(candidates)
        buy_count = 0
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            signal = project_market_buy_signal(candidate)
            if signal["signal"] != "BUY_NOW":
                continue
            buy_count += 1
            key = _event_key(signal)
            timestamp = completed_as_of.isoformat() if hasattr(completed_as_of, "isoformat") else str(completed_as_of)
            existing = events.get(key)
            if existing is None:
                events[key] = {
                    **signal,
                    "first_signaled_at": timestamp,
                    "last_signaled_at": timestamp,
                    "sessions_present": 1,
                    "first_signal_price": signal.get("current_price"),
                    "latest_signal_price": signal.get("current_price"),
                }
            else:
                existing["last_signaled_at"] = timestamp
                existing["sessions_present"] += 1
                existing["latest_signal_price"] = signal.get("current_price")
                existing["confidence"] = signal.get("confidence")
        session_summaries.append({
            "session_date": str(session_date),
            "completed_60m_as_of": completed_as_of.isoformat() if hasattr(completed_as_of, "isoformat") else str(completed_as_of),
            "evaluated_count": len(candidates),
            "buy_now_count": buy_count,
            "source": (metadata or {}).get("source") if isinstance(metadata, dict) else None,
        })

    items = sorted(
        events.values(),
        key=lambda item: (
            str(item.get("last_signaled_at") or ""),
            (item.get("confidence") or {}).get("score") or 0,
            item.get("symbol") or "",
        ),
        reverse=True,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "mode": "PAPER_SHADOW",
        "scope": "MARKET_BUY_SCAN",
        "window_days": days,
        "window_start": (observed_now - timedelta(days=days)).isoformat(),
        "window_end": observed_now.isoformat(),
        "generated_at": observed_now.isoformat(),
        "session_count": len(sessions),
        "evaluated_observations": evaluated_observations,
        "signal_count": len(items),
        "items": items,
        "sessions": session_summaries,
        "confidence_semantics": {
            "kind": "EVIDENCE_SCORE",
            "calibration_status": "NOT_CALIBRATED",
            "is_probability": False,
        },
        "execution": {"authorized": False, "alerts_enabled": False,
                      "broker_execution_enabled": False},
        "provenance": {
            "daily_source": "price_data",
            "intraday_source": "intraday_price_data",
            "timeframe_boundary": "Daily thesis + completed 60m trigger",
            "no_lookahead": True,
            "read_only": True,
        },
    }
