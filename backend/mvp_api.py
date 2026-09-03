"""MVP API projection module — deterministic read-only transforms.

Converts dashboard_snapshot.json serialized cards into the frontend
API contract shapes for:

  GET /api/daily-shortlist  → project_shortlist_response(snapshot)
  GET /api/explorer         → project_explorer_response(items, page, page_size, search, stage)
  GET /api/symbol/{symbol}  → project_symbol_detail(items, symbol)

Uses existing daily_shortlist module for eligibility/ranking. Canonical setup
candidate construction performs bounded read-only DB queries; no path mutates
market data.
"""

from __future__ import annotations

import math
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from decision_dimensions import project_decision_dimensions
from provenance_contract import (
    DECISION_STATE_OFFICIAL_DAILY,
    DECISION_STATE_PROVISIONAL,
    resolve_decision_state,
)
from marginable import (
    eligible_symbols,
    enrich_item,
    filter_items,
    metadata as marginable_metadata,
    normalize_filter,
    normalize_rates,
)
import instruments
from eod_healthcheck import expected_market_date
from set_market_day_guard import SET_CLOSED_DATES
from freshness_assessment import (assess_projection_freshness as _resolve_freshness,
                                  daily_eod_status as _daily_eod_status)
from setup_candidate_contract import (attach_bonus_vcp, build_peer_context,
                                      build_setup_candidate)
from elliott_structure_engine import build_wave_contract
from trade_setup_engine import build_trade_setup
from trend_strength_engine import compute_trend_strength
from candidate_row_evidence import (assemble_candidate_data_status,
                                    assemble_candidate_provenance,
                                    build_current_quote)
from canonical_setup_projection import (
    _validate_canonical_setup_candidate,
    project_setup_candidates_response,
)


def resolve_universe(pg, universe_filter="marginable_long", *, active_symbols=None):
    """Resolve the bounded serving universe from the authoritative master."""
    if universe_filter not in {"marginable_long", "active_ord"}:
        raise ValueError(f"unknown universe filter: {universe_filter}")
    active = list(active_symbols if active_symbols is not None
                  else instruments.active_ord_symbols(pg))
    if universe_filter == "active_ord":
        symbols = sorted({str(symbol).strip().upper() for symbol in active if str(symbol).strip()})
        return symbols, {
            "universe_filter": "active_ord", "audit_only": True,
            "base_active_ord_count": len(symbols), "eligible_count": len(symbols),
            "excluded_count": 0, "excluded_reason": None,
        }
    symbols, manifest = eligible_symbols(active)
    manifest = dict(manifest)
    manifest["universe_filter"] = "marginable_long"
    manifest["audit_only"] = False
    return symbols, manifest


def _number(value, default=None):
    """Safe float coercion; returns default on None/non-numeric."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_name(item: dict) -> str | None:
    """Best-effort company name from serialized card."""
    return (
        item.get("companyName")
        or item.get("name")
        or item.get("company_name")
    )


def _resolve_market_cap(item: dict) -> float | None:
    """Market cap from independence block or direct field."""
    ind = item.get("independence") or {}
    return _number(ind.get("market_cap") or item.get("market_cap") or item.get("marketCap"))


def _resolve_index_membership(item: dict) -> list[str]:
    """Prefer normalized as-of membership; retain the legacy flag fallback."""
    normalized = item.get("index_membership")
    if isinstance(normalized, (list, tuple)):
        return [str(value) for value in normalized if value]
    ind = item.get("independence") or {}
    result = []
    if bool(ind.get("is_set50")):
        result.append("SET50")
    if result and "SET50" in result:
        result.append("SET100")  # SET50 is subset of SET100
    return result


def _resolve_provenance(item: dict, scan_time: str | None, scan_run_id: str | None) -> dict:
    """Provenance block per frontend contract."""
    return {
        "scan_run_id": scan_run_id or "",
        "scan_time": scan_time or "",
    }


def _resolve_trigger(item: dict) -> str | None:
    """Explainable trigger label — only when real evidence exists.

    Returns None when no authoritative trigger source is present.
    Never synthesises "Near pivot" or "No explicit trigger" as if facts.
    """
    t = item.get("trigger")
    if t and str(t).strip():
        return str(t).strip()
    # breakoutEvidence.trigger is a real data field
    bev = item.get("breakoutEvidence") or {}
    if bev.get("trigger"):
        return f"Break above {bev['trigger']}"
    # NOT_VERIFIED: no authoritative trigger evidence exists
    return None


def _resolve_invalidation(item: dict) -> str | None:
    """Explainable invalidation/system-stop boundary — only when real evidence exists.

    Returns None when no authoritative invalidation source is present.
    Never synthesises "No invalidation level defined" as if a fact.
    """
    inv = item.get("invalidation")
    if inv and str(inv).strip():
        return str(inv).strip()
    stop = _number(item.get("riskStop") or item.get("stop"))
    if stop is not None:
        return f"Close <= {stop:.2f}"
    # NOT_VERIFIED: no authoritative invalidation evidence exists
    return None


def _resolve_rr(item: dict) -> float | None:
    """Risk/reward ratio from target vs risk_stop."""
    target = _number(item.get("t161") or item.get("t127") or item.get("target"))
    stop = _number(item.get("riskStop") or item.get("stop"))
    close = _number(item.get("close"))
    if not target or not stop or not close or stop >= close:
        return None
    risk = close - stop
    if risk <= 0:
        return None
    reward = max(0, target - close)
    if reward <= 0:
        return None
    return round(reward / risk, 2)


def _resolve_target(item: dict) -> float | None:
    """Price target from fib extensions or explicit target."""
    return (
        _number(item.get("target"))
        or _number(item.get("t161"))
        or _number(item.get("t127"))
    )


def _resolve_change_pct(item: dict) -> float | None:
    """Change percent from serialized card."""
    val = _number(item.get("changePct") or item.get("change"))
    return round(val, 2) if val is not None else None


def _resolve_change_amount(item: dict) -> float | None:
    """Change amount — only from a directly serialized source field.

    Returns None when changeAmount is not present in the source data.
    Does NOT approximate from changePct × close.
    """
    val = _number(item.get("changeAmount"))
    if val is not None:
        return round(val, 2)
    # NOT_VERIFIED: no direct changeAmount source; do not approximate
    return None


def _resolve_description(item: dict) -> str | None:
    """Business description."""
    desc = item.get("businessSummary")
    if desc and str(desc).strip():
        return str(desc).strip()
    return item.get("description")


def _card_to_shortlist_item(item: dict, scan_time: str | None, scan_run_id: str | None) -> dict:
    """Map one serialized card to the frontend shortlist item contract."""
    item = enrich_item(item)
    sp = item.get("setup_proximity") or {}
    sq = item.get("setup_quality") or {}
    daily_fresh = item.get("daily_eod_freshness") or {}
    daily_eod = item.get("dailyEodDecision") or {}
    daily_eod_is_official = (
        daily_eod.get("source") == "Daily EOD"
        and daily_eod.get("as_of")
        and (
            item.get("dataFreshness") == "fresh"
            or daily_fresh.get("status") == "fresh"
        )
    )
    return {
        "symbol": item.get("symbol"),
        "name": _resolve_name(item),
        "sector": item.get("sector"),
        "industry": item.get("industry"),
        "description": _resolve_description(item),
        "market_cap": _resolve_market_cap(item),
        "trade_value": _number(item.get("tradeValue") or item.get("turnover")),
        "index_membership": _resolve_index_membership(item),
        "margin_pct": _number(item.get("margin_pct") or item.get("marginPct")),
        "margin_rate_pct": _number(item.get("margin_rate_pct")),
        "margin_marker": item.get("margin_marker"),
        "margin_can_buy": item.get("margin_can_buy"),
        "margin_can_add_collateral": item.get("margin_can_add_collateral"),
        "margin_can_short": item.get("margin_can_short"),
        "marginable": dict(item.get("marginable") or {}),
        "target": _resolve_target(item),
        "rr": _resolve_rr(item),
        "high52": _number(item.get("high52")),
        "low52": _number(item.get("low52")),
        "ath_high": _number(item.get("athHigh")),
        "ath_low": _number(item.get("athLow")),
        "stage": item.get("stage"),
        "phase": item.get("phase"),
        "decision_state": item.get("decision_state")
            or item.get("decisionState")
            or (DECISION_STATE_OFFICIAL_DAILY if daily_eod_is_official else DECISION_STATE_PROVISIONAL),
        "action": item.get("action"),
        "action_queue": item.get("action_queue"),
        "close": _number(item.get("close")),
        "change_pct": _resolve_change_pct(item),
        "change_amount": _resolve_change_amount(item),
        "volume": _number(item.get("volume"), 0),
        "avgDailyValue20": _number(item.get("avgDailyValue20"), 0),
        "setup_quality": {
            "pass": bool(sq.get("pass")),
            "score": _number(sq.get("score")),
            "reasons": sq.get("reasons") or [],
        },
        "setup_proximity": {
            "state": sp.get("state"),
            "pivot": _number(sp.get("pivot")),
            "distance_pct": _number(sp.get("distance_pct")),
            "zone": sp.get("zone"),
        },
        "decision_dimensions": project_decision_dimensions(item),
        "trigger": _resolve_trigger(item),
        "invalidation": _resolve_invalidation(item),
        "risk_stop": _number(item.get("riskStop") or item.get("stop")),
        "risk_pct": _number(item.get("riskStopPct") or item.get("riskPct")),
        "rs": _number(item.get("rs"), 0),
        "source": item.get("priceSource") or item.get("source") or "Daily EOD",
        "data_freshness": item.get("dataFreshness")
            or item.get("data_freshness")
            or (daily_fresh.get("status")),
        "provenance": _resolve_provenance(item, scan_time, scan_run_id),
    }


def _resolve_decision_state(items: list[dict]) -> str:
    """Determine decision_state from items' availability.

    When any item has official_daily decision_state, return official_daily.
    Otherwise provisional.
    """
    for item in items:
        ds = item.get("decision_state") or item.get("decisionState")
        if ds == DECISION_STATE_OFFICIAL_DAILY:
            return DECISION_STATE_OFFICIAL_DAILY
    return DECISION_STATE_PROVISIONAL


def _watch_lane_projection(items: list[dict], *, excluded_symbols: set[str],
                           scan_time: str | None, scan_run_id: str | None) -> tuple[list[dict], list[dict]]:
    """Project price movers separately from actionable Daily Shortlist lanes.

    These are context/watch-only lanes. They never receive shortlist rank,
    READY/PRE_READY state, or a positive entry directive.
    """
    rising, caution = [], []
    for raw in items:
        symbol = str(raw.get("symbol", "")).upper()
        if not symbol or symbol in excluded_symbols:
            continue
        daily = raw.get("daily_eod_freshness") or {}
        if daily.get("status") != "latest_available" or raw.get("dataFreshness") in ("stale", "unknown"):
            continue
        change = _resolve_change_pct(raw)
        if change is None or change < 5.0:
            continue
        stage = raw.get("stage")
        phase = raw.get("phase")
        quality = raw.get("setup_quality") or {}
        reasons = list(quality.get("reasons") or [])
        volume_ratio = _number(
            raw.get("volumeRatio50")
            or raw.get("volume_ratio_50")
            or quality.get("vol_ratio_50")
        )
        has_volume_evidence = bool(raw.get("volumeSurge")) or (volume_ratio is not None and volume_ratio >= 2.0)
        if not has_volume_evidence:
            continue
        card = _card_to_shortlist_item(raw, scan_time, scan_run_id)
        card.update({
            "publication_state": "WATCH_ONLY",
            "watch_state": "RISING_MOVERS",
            "watch_change_pct": change,
            "watch_volume_ratio": volume_ratio,
            "action": "WATCH ONLY",
            "action_queue": "rising_movers_watch",
            "rank_components": {},
            "total_score": None,
            "policy_version": None,
        })
        if stage in {"S1_basing", "S2_uptrend"} and phase not in {"broken", "declining"}:
            card["watch_reason"] = "Price/volume surge, but Daily setup is not confirmed"
            rising.append(card)
        elif stage in {"S3_distributing", "S4_down"} or phase in {"topping", "breakout_extended", "declining", "broken"} or "extended" in reasons:
            card["watch_state"] = "CAUTION"
            card["action"] = "DO NOT CHASE"
            card["action_queue"] = "caution_watch"
            card["watch_reason"] = "Price/volume surge in weak, topping, or extended structure"
            caution.append(card)
    rising.sort(key=lambda x: (-float(x.get("watch_change_pct") or 0), str(x.get("symbol"))))
    caution.sort(key=lambda x: (-float(x.get("watch_change_pct") or 0), str(x.get("symbol"))))
    return rising, caution


def _find_item_by_symbol(items: list[dict], symbol: str) -> dict | None:
    """Case-insensitive symbol lookup."""
    upper = symbol.upper()
    for item in items:
        if str(item.get("symbol", "")).upper() == upper:
            return item
    return None


# ── Public API ────────────────────────────────────────────────────────

def filter_price_band(items: list[dict], price_band: str | None) -> list[dict]:
    """Presentation-only price band filter; never changes scan eligibility."""
    band = str(price_band or "all").strip().lower()
    if band not in {"all", "below_2", "2_to_10", "above_10"}:
        band = "all"
    if band == "all":
        return list(items)
    result = []
    for item in items:
        try:
            price = float(item.get("close"))
        except (TypeError, ValueError):
            continue
        if band == "below_2" and price < 2:
            result.append(item)
        elif band == "2_to_10" and 2 <= price <= 10:
            result.append(item)
        elif band == "above_10" and price > 10:
            result.append(item)
    return result


def _setup_candidate_from_snapshot(item: dict, snapshot_meta: dict | None = None) -> dict:
    """Compatibility-only validator for callers that explicitly load snapshots.

    The canonical route does not call this adapter or load a snapshot. It is
    retained for replay/audit callers and deliberately refuses legacy cards.
    """
    return _validate_canonical_setup_candidate(item)


def _wave_inputs(daily_df):
    """Derive only observable v1 evidence from the Daily OHLCV series."""
    if daily_df is None or "Close" not in daily_df:
        return {}
    close = daily_df["Close"].astype(float).dropna()
    if len(close) < 21:
        return {}
    prior_advance = float(close.iloc[-1]) > float(close.iloc[-21])
    anchors = close.iloc[-20:]
    confirmed = anchors.nunique() >= 3
    structure_intact = float(close.iloc[-1]) >= float(anchors.min())
    return {
        "prior_advance": prior_advance,
        "confirmed_swing_anchors": confirmed,
        "structure_intact": structure_intact,
    }


def _load_daily_for_symbol(screening, symbol, pg, market):
    return screening.load_symbol(symbol, pg=pg, lookback=400, market=market)


def _load_intraday_for_symbol(screening, symbol, pg, market):
    frame = screening.load_symbol_intraday(symbol, pg=pg, interval="60m", lookback=400, market=market)
    return _normalize_candidate_ohlcv_frame(frame, timeframe="60m")


def _normalize_candidate_ohlcv_frame(frame, *, timeframe=None):
    """Normalize producer frames before they reach validation and row building.

    DB loaders currently emit title-case columns, but the producer boundary is
    also used by read-only compatibility/test loaders.  Keep the evaluator and
    quote publisher on one explicit OHLCV contract without weakening global
    validation or changing the frame's values/index.
    """
    if frame is None:
        return None
    columns = {}
    for canonical in ("Open", "High", "Low", "Close", "Volume"):
        matches = [column for column in frame.columns
                   if str(column).casefold() == canonical.casefold()]
        if len(matches) != 1:
            return frame
        columns[matches[0]] = canonical
    normalized = frame.rename(columns=columns)
    if timeframe:
        normalized.attrs["timeframe"] = timeframe
    if hasattr(frame, "attrs"):
        normalized.attrs.update(frame.attrs)
    return normalized


def _evaluate_candidate_engines(daily_df, intraday_df, daily_evidence_valid):
    """Run the independent Daily/60m engines for one symbol.

    The engines are pure transforms over per-symbol frames. Keeping this
    adapter small makes bounded parallel evaluation deterministic (the caller
    consumes ``executor.map`` in symbol order) while preserving the existing
    evidence inputs and the historical setup-state adapter.
    """
    daily_input = daily_df if daily_evidence_valid else None
    wave = build_wave_contract(
        daily_input, _wave_inputs(daily_df) if daily_evidence_valid else {}
    )
    setup = build_trade_setup(
        {**wave, "state": wave.get("primary_state", "UNKNOWN")}, intraday_df
    )
    return wave, setup


def _evaluate_candidate_engines_worker(args):
    """Process-pool adapter for the CPU-bound per-symbol evaluator."""
    return _evaluate_candidate_engines(*args)


def _bulk_candidate_frames(pg, symbols, *, market="TH", lookback=400):
    """Load bounded Daily and 60m frames in two queries, grouped by symbol."""
    import pandas as pd
    if not symbols:
        return {}, {}, 0

    def load(sql, params, timeframe=None):
        cur = pg.cursor()
        try:
            cur.execute(sql, params)
            rows = cur.fetchall()
        finally:
            cur.close()
        grouped = {}
        for row in rows:
            grouped.setdefault(str(row[0]), []).append(row[1:])
        frames = {}
        for symbol, values in grouped.items():
            frame = pd.DataFrame(values, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
            frame["Date"] = pd.to_datetime(frame["Date"])
            frame = frame.set_index("Date").sort_index()
            if timeframe:
                frame.attrs["timeframe"] = timeframe
                frame.attrs["as_of"] = frame.index[-1]
            frames[symbol] = _normalize_candidate_ohlcv_frame(frame, timeframe=timeframe)
        return frames

    # A partitioned window query makes PostgreSQL scan/sort the complete
    # matching history before discarding all but 400 rows per symbol.  The
    # candidate universe is bounded, so indexed per-symbol probes are both
    # cheaper and preserve the full-universe result without changing evidence.
    ranked_daily = """SELECT symbols.symbol, rows.date, rows.open, rows.high,
                             rows.low, rows.close, rows.volume
                      FROM unnest(%s::text[]) AS symbols(symbol)
                      CROSS JOIN LATERAL (
                          SELECT date, open, high, low, close, volume
                          FROM price_data
                          WHERE market=%s AND symbol=symbols.symbol
                          ORDER BY date DESC LIMIT %s
                      ) rows
                      ORDER BY symbols.symbol, rows.date"""
    ranked_intraday = """SELECT symbols.symbol, rows.ts, rows.open, rows.high,
                                rows.low, rows.close, rows.volume
                         FROM unnest(%s::text[]) AS symbols(symbol)
                         CROSS JOIN LATERAL (
                             SELECT ts, open, high, low, close, volume
                             FROM intraday_price_data
                             WHERE interval=%s AND symbol=symbols.symbol
                             ORDER BY ts DESC LIMIT %s
                         ) rows
                         ORDER BY symbols.symbol, rows.ts"""
    daily = load(ranked_daily, (list(symbols), market.upper(), lookback))
    intraday = load(ranked_intraday, (list(symbols), "60m", lookback), "60m")
    return daily, intraday, 2


def _load_daily_canonical_metadata(pg, symbols, as_of_by_symbol, *, market="TH"):
    """Load point-in-time Daily high/low and normalized index evidence.

    The 52W window is the latest 252 Daily rows at each candidate as-of date;
    ATH is the observed Daily high/low over all rows through that date.  Both
    queries are read-only and fail closed when a compatibility test seam does
    not provide a PostgreSQL-shaped cursor.
    """
    if not symbols:
        return {}
    dates = [str(as_of_by_symbol.get(symbol) or "")[:10] or None for symbol in symbols]
    metadata = {symbol: {} for symbol in symbols}
    cur = pg.cursor()
    try:
        cur.execute("""WITH requested(symbol, as_of) AS (
                         SELECT * FROM unnest(%s::text[], %s::date[])
                       )
                       SELECT requested.symbol, w.high52, w.low52, ath.ath_high, ath.ath_low
                       FROM requested
                       LEFT JOIN LATERAL (
                         SELECT MAX(high) AS high52, MIN(low) AS low52
                         FROM (SELECT high, low FROM price_data
                               WHERE market=%s AND symbol=requested.symbol AND date <= requested.as_of
                               ORDER BY date DESC LIMIT 252) windowed
                       ) w ON TRUE
                       LEFT JOIN LATERAL (
                         SELECT MAX(high) AS ath_high, MIN(low) AS ath_low
                         FROM price_data
                         WHERE market=%s AND symbol=requested.symbol AND date <= requested.as_of
                       ) ath ON TRUE""", (list(symbols), dates, market.upper(), market.upper()))
        for row in cur.fetchall():
            symbol, high52, low52, ath_high, ath_low = row
            metadata.setdefault(str(symbol), {}).update({
                "high52": _number(high52), "low52": _number(low52),
                "ath_high": _number(ath_high), "ath_low": _number(ath_low),
                "index_membership_evidence": {"source": "price_data", "as_of": dates[symbols.index(str(symbol))]},
            })
    finally:
        cur.close()

    cur = pg.cursor()
    try:
        cur.execute("""WITH requested(symbol, as_of) AS (
                         SELECT * FROM unnest(%s::text[], %s::date[])
                       )
                       SELECT m.symbol, m.index_name, m.effective_from, m.effective_to, m.source,
                              requested.as_of
                       FROM index_memberships m
                       JOIN requested ON requested.symbol = m.symbol
                       WHERE m.effective_from <= requested.as_of
                         AND (m.effective_to IS NULL OR m.effective_to >= requested.as_of)
                       ORDER BY m.symbol, m.index_name""", (list(symbols), dates))
        for symbol, index_name, effective_from, effective_to, source, as_of in cur.fetchall():
            entry = {"index_name": str(index_name), "effective_from": str(effective_from),
                     "effective_to": str(effective_to) if effective_to else None,
                     "source": str(source), "as_of": str(as_of)}
            row = metadata.setdefault(str(symbol), {})
            row.setdefault("index_membership", []).append(str(index_name))
            row.setdefault("index_membership_evidence", {}).setdefault("memberships", []).append(entry)
    finally:
        cur.close()
    return metadata


def _relative_strength_ranks(daily_frames, market_df):
    import pandas as pd
    lookback = 252
    if market_df is None or len(market_df) < lookback:
        # Zero is a real-looking percentile and therefore fabricates evidence.
        # Omit the rank until both benchmark and symbol history are sufficient.
        return {}
    market_return = market_df["Close"].iloc[-1] / market_df["Close"].iloc[-lookback] - 1
    returns = {}
    for symbol, frame in daily_frames.items():
        if frame is not None and len(frame) >= lookback:
            close = frame["Close"]
            returns[symbol] = close.iloc[-1] / close.iloc[-lookback] - 1 - market_return
    if not returns:
        return {}
    ranks = pd.Series(returns).rank(pct=True) * 100
    return {symbol: float(value) for symbol, value in ranks.items()}


def _daily_final_session_available(daily_df, expected_session):
    if daily_df is None or len(daily_df) == 0:
        return False
    try:
        return daily_df.index[-1].date() == expected_session
    except (AttributeError, IndexError):
        return False


def _previous_set_session(session):
    """Return the immediately preceding SET trading session."""
    session -= timedelta(days=1)
    while session.weekday() >= 5 or session.isoformat() in SET_CLOSED_DATES:
        session -= timedelta(days=1)
    return session


def _daily_evidence_status(daily_df, expected_session, evidence_valid):
    """Separate usable official Daily evidence from current EOD publication."""
    if not evidence_valid:
        return (False, "unknown", "missing") if daily_df is None or len(daily_df) == 0 else (
            False, "invalid", "invalid"
        )
    daily_session = daily_df.index[-1].date()
    if daily_session == expected_session:
        return True, "fresh", "available"
    if daily_session == _previous_set_session(expected_session):
        return True, "fresh", "pending"
    return False, "stale", "missing"


def _valid_candidate_ohlcv(frame) -> bool:
    """Validate required OHLCV without rejecting valid positive flat candles."""
    import pandas as pd
    required = ["Open", "High", "Low", "Close", "Volume"]
    if (frame is None or len(frame) == 0
            or not isinstance(frame.index, pd.DatetimeIndex)
            or frame.index.hasnans
            or not frame.index.is_unique
            or not frame.index.is_monotonic_increasing
            or not set(required).issubset(frame.columns)):
        return False
    values = frame[required].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any() or not (values > 0).all().all():
        return False
    return bool(((values["High"] >= values[["Open", "Close"]].max(axis=1))
                 & (values["Low"] <= values[["Open", "Close"]].min(axis=1))
                 & (values["High"] >= values["Low"])).all())


def _expected_intraday_session_date(now=None):
    """Return the SET session that should have current 60m observations."""
    current = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Bangkok"))
    session = current.date()
    before_first_completed_bar = (current.hour, current.minute) < (10, 15)
    if (session.weekday() >= 5 or session.isoformat() in SET_CLOSED_DATES
            or before_first_completed_bar):
        session -= timedelta(days=1)
        while session.weekday() >= 5 or session.isoformat() in SET_CLOSED_DATES:
            session -= timedelta(days=1)
    return session


def _expected_intraday_interval_start(now=None):
    """Return the latest 60m bar start that should be complete by ``now``."""
    current = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Bangkok"))
    session = _expected_intraday_session_date(current)
    current_time = (current.hour, current.minute)
    if current.date() != session or current_time < (11, 0):
        if current.date() == session:
            session -= timedelta(days=1)
            while session.weekday() >= 5 or session.isoformat() in SET_CLOSED_DATES:
                session -= timedelta(days=1)
        return datetime.combine(session, datetime.min.time(), tzinfo=ZoneInfo("Asia/Bangkok")).replace(hour=16)
    if current_time < (12, 0):
        hour = 10
    elif current_time < (12, 30):
        hour = 11
    elif current_time < (15, 0):
        hour = 12
    elif current_time < (16, 0):
        hour = 14
    elif current_time < (16, 30):
        hour = 15
    else:
        hour = 16
    return datetime.combine(session, datetime.min.time(), tzinfo=ZoneInfo("Asia/Bangkok")).replace(hour=hour)


def _intraday_60m_status(intraday_df, expected_interval_start):
    valid_interval = (intraday_df is not None and len(intraday_df) >= 3
                      and intraday_df.attrs.get("timeframe") == "60m")
    if not valid_interval:
        return False, False, "unknown", None
    try:
        timestamp = intraday_df.index[-1]
        as_of = timestamp.isoformat()
        if getattr(timestamp, "tzinfo", None) is None:
            timestamp = timestamp.replace(tzinfo=ZoneInfo("Asia/Bangkok"))
        else:
            timestamp = timestamp.astimezone(ZoneInfo("Asia/Bangkok"))
    except (AttributeError, IndexError, TypeError, ValueError):
        return True, False, "unknown", None
    if expected_interval_start.tzinfo is None:
        expected_interval_start = expected_interval_start.replace(
            tzinfo=ZoneInfo("Asia/Bangkok")
        )
    else:
        expected_interval_start = expected_interval_start.astimezone(
            ZoneInfo("Asia/Bangkok")
        )
    current = timestamp >= expected_interval_start
    return True, current, "fresh" if current else "stale", as_of


@dataclass(frozen=True)
class _CandidateRowContext:
    """Inputs owned by the builder stages that finalize one candidate row."""

    symbol: str
    daily_df: Any
    intraday_df: Any
    daily_evidence_valid: bool
    daily_evidence_usable: bool
    daily_current: bool
    daily_freshness: str
    daily_final_status: str
    intraday_available: bool
    intraday_current: bool
    intraday_freshness: str
    intraday_as_of: str | None
    rs_rank: float | None
    profile: dict[str, Any]
    universe_manifest: dict[str, Any]
    wave: dict[str, Any]
    setup: dict[str, Any]
    canonical_metadata: dict[str, Any] | None


@dataclass(frozen=True)
class _CandidateRowResult:
    """Named outputs needed to aggregate the finalized candidate rows."""

    row: dict[str, Any]
    candidate_freshness: str
    daily_freshness: str
    intraday_freshness: str


def _build_candidate_row(*, context: _CandidateRowContext) -> _CandidateRowResult:
    """Finalize one evaluated symbol into the canonical candidate contract."""
    symbol = context.symbol
    daily_df = context.daily_df
    daily_evidence_valid = context.daily_evidence_valid
    daily_evidence_usable = context.daily_evidence_usable
    daily_current = context.daily_current
    daily_freshness = context.daily_freshness
    daily_final_status = context.daily_final_status
    intraday_available = context.intraday_available
    intraday_current = context.intraday_current
    intraday_freshness = context.intraday_freshness
    intraday_as_of = context.intraday_as_of
    rs_rank = context.rs_rank
    profile = context.profile
    universe_manifest = context.universe_manifest
    wave = context.wave
    setup = dict(context.setup)
    canonical_metadata = context.canonical_metadata
    as_of = daily_df.index[-1].isoformat() if daily_evidence_valid else None
    prior_ath = None
    if daily_df is not None and "High" in daily_df and len(daily_df) > 1:
        prior_highs = daily_df["High"].iloc[:-1].astype(float).dropna()
        prior_ath = float(prior_highs.max()) if not prior_highs.empty else None
    trend = compute_trend_strength(
        daily_df if daily_evidence_valid else None,
        relative_strength=rs_rank, prior_ath=prior_ath
    )
    if not daily_evidence_usable:
        wave = {
            **wave,
            "primary_state": "NOT_VERIFIABLE",
            "alternative_state": "NOT_VERIFIABLE",
            "confidence": "LOW",
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "missing_evidence": sorted(set(
                list(wave.get("missing_evidence") or []) + ["usable_official_daily"]
            )),
        }
    if not intraday_current:
        setup = {**setup, "status": "DATA_BLOCKED"}
    peer_data = {
        "sector": profile.get("sector"), "industry": profile.get("industry"),
        "peer_data_status": "UNKNOWN",
    }
    peer_symbols = profile.get("peer_symbols") or profile.get("peers")
    if peer_symbols is not None:
        peer_data["peer_symbols"] = peer_symbols
    peer_context = build_peer_context(symbol, peer_data)
    data_status, setup, candidate_freshness = assemble_candidate_data_status(
        daily_df=daily_df,
        daily_evidence_valid=daily_evidence_valid,
        daily_evidence_usable=daily_evidence_usable,
        daily_current=daily_current,
        daily_freshness=daily_freshness,
        daily_final_status=daily_final_status,
        intraday_available=intraday_available,
        intraday_current=intraday_current,
        intraday_freshness=intraday_freshness,
        intraday_as_of=intraday_as_of,
        setup=setup,
    )
    bonus_evidence = {}
    attach_bonus_vcp({"bonus_evidence": bonus_evidence}, {
        "present": None, "quality": "NOT_VERIFIED", "source": "legacy_audit_only"
    })
    # Keep the compatibility provenance on the legacy audit placeholder;
    # attach_bonus_vcp has already enforced its non-positive shape.
    bonus_evidence["vcp"]["source"] = "legacy_audit_only"
    provenance = assemble_candidate_provenance(
        as_of=as_of,
        intraday_as_of=intraday_as_of,
        candidate_freshness=candidate_freshness,
        universe_manifest=universe_manifest,
    )
    quote = build_current_quote(
        daily_df=daily_df, intraday_df=context.intraday_df,
        intraday_current=intraday_current,
        daily_evidence_valid=daily_evidence_valid,
    )
    row = build_setup_candidate(
        symbol, as_of, data_status, trend, wave, setup, peer_context,
        bonus_evidence,
        provenance,
        canonical_metadata,
        quote,
    )
    return _CandidateRowResult(
        row=row,
        candidate_freshness=candidate_freshness,
        daily_freshness=daily_freshness,
        intraday_freshness=intraday_freshness,
    )


def build_setup_candidates_from_data(pg, *, market="TH"):
    """Build the canonical source from the authoritative read-only data path."""
    import screening
    # RS ranking only reads the latest and 252nd benchmark closes. Keep the
    # market query bounded to that actual dependency; candidate Daily/60m
    # history remains the full 400-row evidence window below.
    rs_lookback = 252
    build_started = time.monotonic()
    stage_started = build_started
    symbols, universe_manifest = resolve_universe(pg, "marginable_long")
    profiles = instruments.profile_taxonomy(pg, symbols=symbols)
    market_df = screening.load_market(pg, lookback=rs_lookback, market=market)
    source_ms = round((time.monotonic() - stage_started) * 1000, 3)
    stage_started = time.monotonic()
    try:
        daily_frames, intraday_frames, ohlcv_query_count = _bulk_candidate_frames(
            pg, symbols, market=market
        )
        rs_ranks = _relative_strength_ranks(daily_frames, market_df)
    except (AttributeError, TypeError):
        # Small pure tests may provide a sentinel instead of a DB connection.
        daily_frames = intraday_frames = None
        ohlcv_query_count = len(symbols) * 2
        rs_ranks = screening._universe_rs_ranks(pg, market_df, symbols)
        # The legacy adapter historically filled unavailable ranks with 0.0.
        # Canonical setup candidates must expose unknown RS as null instead.
        rs_ranks = {
            symbol: value for symbol, value in (rs_ranks or {}).items()
            if _number(value) is not None and _number(value) > 0
        }
    load_ms = round((time.monotonic() - stage_started) * 1000, 3)
    stage_started = time.monotonic()
    candidates = []
    latest_daily = None
    expected_daily_session = expected_market_date()
    expected_intraday_interval = _expected_intraday_interval_start()
    freshness_statuses = []
    daily_freshness_statuses = []
    intraday_freshness_statuses = []
    evaluation_inputs = {}
    for symbol in symbols:
        daily_df = (daily_frames.get(symbol) if daily_frames is not None
                    else _load_daily_for_symbol(screening, symbol, pg, market))
        intraday_df = (intraday_frames.get(symbol) if intraday_frames is not None
                       else _load_intraday_for_symbol(screening, symbol, pg, market))
        if intraday_df is not None:
            intraday_df.attrs["as_of"] = intraday_df.index[-1]
        daily_evidence_valid = _valid_candidate_ohlcv(daily_df)
        daily_current = (daily_evidence_valid
                         and _daily_final_session_available(daily_df, expected_daily_session))
        daily_usable, daily_freshness, daily_final_status = _daily_evidence_status(
            daily_df, expected_daily_session, daily_evidence_valid
        )
        intraday_available, intraday_current, intraday_freshness, intraday_as_of = (
            _intraday_60m_status(intraday_df, expected_intraday_interval)
        )
        evaluation_inputs[symbol] = (
            daily_df, intraday_df, daily_usable, daily_current, daily_freshness,
            daily_final_status,
            intraday_available, intraday_current, intraday_freshness, intraday_as_of,
            daily_evidence_valid,
        )

    as_of_by_symbol = {
        symbol: (frame.index[-1].date().isoformat() if frame is not None and len(frame) else None)
        for symbol, (frame, *_rest) in evaluation_inputs.items()
    }
    try:
        canonical_metadata = _load_daily_canonical_metadata(
            pg, symbols, as_of_by_symbol, market=market
        ) if daily_frames is not None else {}
    except (AttributeError, TypeError, ValueError, IndexError):
        canonical_metadata = {}

    # Daily Elliott and 60m setup calculations are independent per symbol but
    # are CPU-bound Python/pandas work. Threads do not bypass the GIL here and
    # made the cold full-universe build slower; processes provide actual CPU
    # concurrency without changing the pure engine inputs. executor.map
    # preserves symbol order, so ranking/pagination and all output ordering
    # remain deterministic. The fallback path stays serial for pure test
    # sentinels and legacy loaders.
    engine_results = {}
    evaluation_workers = 1
    if daily_frames is not None and intraday_frames is not None and len(symbols) > 1:
        evaluation_workers = min(4, len(symbols))
        with ProcessPoolExecutor(max_workers=evaluation_workers) as executor:
            results = executor.map(
                _evaluate_candidate_engines_worker,
                ((evaluation_inputs[symbol][0], evaluation_inputs[symbol][1],
                  evaluation_inputs[symbol][2]) for symbol in symbols),
                chunksize=8,
            )
            engine_results = dict(zip(symbols, results))

    for symbol in symbols:
        (daily_df, intraday_df, daily_evidence_usable, daily_current, daily_freshness,
         daily_final_status,
         intraday_available, intraday_current, intraday_freshness, intraday_as_of,
         daily_evidence_valid) = (
            evaluation_inputs[symbol]
        )
        as_of = daily_df.index[-1].isoformat() if daily_evidence_valid else None
        if as_of and (latest_daily is None or as_of > latest_daily):
            latest_daily = as_of
        if engine_results:
            wave, setup = engine_results[symbol]
        else:
            wave, setup = _evaluate_candidate_engines(
                daily_df, intraday_df, daily_evidence_usable
            )
        profile = profiles.get(symbol) or {}
        result = _build_candidate_row(context=_CandidateRowContext(
            symbol=symbol,
            daily_df=daily_df,
            intraday_df=intraday_df,
            daily_evidence_valid=daily_evidence_valid,
            daily_evidence_usable=daily_evidence_usable,
            daily_current=daily_current,
            daily_freshness=daily_freshness,
            daily_final_status=daily_final_status,
            intraday_available=intraday_available,
            intraday_current=intraday_current,
            intraday_freshness=intraday_freshness,
            intraday_as_of=intraday_as_of,
            rs_rank=rs_ranks.get(symbol),
            profile=profile,
            universe_manifest=universe_manifest,
            wave=wave,
            setup=setup,
            canonical_metadata=canonical_metadata.get(symbol),
        ))
        freshness_statuses.append(result.candidate_freshness)
        daily_freshness_statuses.append(result.daily_freshness)
        intraday_freshness_statuses.append(result.intraday_freshness)
        candidates.append(result.row)
    overall_freshness = ("fresh" if freshness_statuses and all(value == "fresh" for value in freshness_statuses)
                         else "stale" if any(value == "stale" for value in freshness_statuses) else "unknown")
    evaluate_ms = round((time.monotonic() - stage_started) * 1000, 3)
    total_ms = round((time.monotonic() - build_started) * 1000, 3)
    def aggregate_statuses(statuses):
        statuses = set(statuses)
        if "stale" in statuses:
            return "stale"
        if "unknown" in statuses:
            return "unknown"
        if "fresh" in statuses:
            return "fresh"
        return "unknown"

    return candidates, {"scan_time": latest_daily, "freshness": {
                            "status": overall_freshness,
                            "daily_status": aggregate_statuses(daily_freshness_statuses),
                            "intraday_status": aggregate_statuses(intraday_freshness_statuses),
                        },
                        "source": "price_data+intraday_price_data", "universe": "TH-ORD",
                        "build_observability": {
                            "duration_ms": total_ms,
                            "stages_ms": {"source_context": source_ms, "ohlcv_load": load_ms,
                                          "candidate_evaluation": evaluate_ms},
                            "ohlcv_query_count": ohlcv_query_count,
                            "ohlcv_row_count": (
                                sum(len(frame) for frame in daily_frames.values())
                                + sum(len(frame) for frame in intraday_frames.values())
                            ) if daily_frames is not None and intraday_frames is not None else None,
                            "evaluated_row_count": len(candidates),
                            "candidate_evaluation_workers": evaluation_workers,
                            "candidate_evaluation_parallel": evaluation_workers > 1,
                        },
                        **universe_manifest}


def persist_setup_candidate_lifecycle(cur, candidate: dict, **kwargs) -> dict:
    """Explicit completed-60m persistence hook for a producer result.

    The canonical builder above remains read-only.  A completed-60m evaluator
    may opt into this adapter with its caller-owned cursor/transaction.
    """
    from lifecycle_persistence import persist_completed_60m_candidate
    return persist_completed_60m_candidate(cur, candidate, **kwargs)


def project_shortlist_response(items: list[dict], snapshot_meta: dict | None = None,
                               marginable_filter: str = "krungsri",
                               margin_rates=None, price_band: str = "all") -> dict:
    """Build the GET /api/daily-shortlist response from serialized cards.

    Uses daily_shortlist.project_shortlist() for eligibility/ranking,
    then maps to frontend contract shape. The default surface is the
    owner-selected Krungsri Credit Balance marginable list.
    """
    # Keep the retired shortlist classifier out of the canonical setup import
    # path.  This compatibility route is the only consumer that needs it.
    from daily_shortlist import project_shortlist

    marginable_filter = normalize_filter(marginable_filter)
    margin_rates = normalize_rates(margin_rates)
    items = filter_price_band(filter_items(items, marginable_filter, margin_rates), price_band)
    margin_meta = marginable_metadata()
    if not items:
        return {
            "decision_state": DECISION_STATE_PROVISIONAL,
            "freshness": {
                "status": "unknown",
                "source": "none",
                "as_of": None,
                "data_fetched_at": None,
            },
            "ready": [],
            "pre_ready": [],
            "rising_movers": [],
            "caution": [],
            "scan_time": None,
            "scan_run_id": None,
            "marginable_filter": marginable_filter,
            "marginable_filter_label": marginable_filter.replace("_", " ").title(),
            "margin_rates": margin_rates,
            "marginable_source": margin_meta,
        }

    # Normalize the explicit Daily EOD contract before classification. The
    # shortlist gate runs before card mapping, so deriving official_daily only
    # inside _card_to_shortlist_item is too late.
    normalized_items = []
    for raw in items:
        item = dict(raw)
        daily_eod = item.get("dailyEodDecision") or {}
        daily_fresh = item.get("daily_eod_freshness") or {}
        if (
            not item.get("decision_state")
            and not item.get("decisionState")
            and daily_eod.get("source") == "Daily EOD"
            and daily_eod.get("as_of")
            and (
                item.get("dataFreshness") == "fresh"
                or daily_fresh.get("status") == "fresh"
            )
        ):
            item["decision_state"] = DECISION_STATE_OFFICIAL_DAILY
        normalized_items.append(item)

    candidates = project_shortlist(normalized_items)

    ready = [c for c in candidates if c.get("publication_state") == "READY"]
    pre_ready = [c for c in candidates if c.get("publication_state") == "PRE_READY"]

    # Find the full serialized cards for each candidate
    items_by_symbol = {}
    for it in items:
        sym = str(it.get("symbol", "")).upper()
        if sym:
            items_by_symbol[sym] = it

    # Derive scan metadata from items (use the latest as_of)
    scan_time = None
    for it in items:
        ts = it.get("daily_eod_freshness", {}).get("as_of") or it.get("date")
        if ts and (scan_time is None or str(ts) > str(scan_time)):
            scan_time = str(ts)
    scan_run_id = items[0].get("provenance", {}).get("scan_run_id") if items else None

    def enrich(cand):
        sym = str(cand.get("symbol", "")).upper()
        card = items_by_symbol.get(sym, {})
        result = _card_to_shortlist_item(card, scan_time, scan_run_id)
        # Override action with the shortlist-normalized action
        result["action"] = cand.get("action") or result["action"]
        result["action_queue"] = cand.get("action_queue") or result.get("action_queue")
        result["decision_state"] = DECISION_STATE_OFFICIAL_DAILY  # shortlist = official daily
        # Let the shortlist projection's fail-closed trigger/invalidation
        # override any stale raw-card wording; None is a deliberate signal.
        result["trigger"] = cand.get("trigger")
        result["invalidation"] = cand.get("invalidation")
        return result

    ready_items = [enrich(r) for r in ready]
    pre_items = [enrich(p) for p in pre_ready]
    rising_items, caution_items = _watch_lane_projection(
        normalized_items,
        excluded_symbols={str(x.get("symbol", "")).upper() for x in candidates},
        scan_time=scan_time,
        scan_run_id=scan_run_id,
    )

    # Prefer canonical MVP root metadata; item-derived fallback is transitional.
    freshness = (snapshot_meta or {}).get("freshness") or _resolve_freshness(items)
    root_run_id = (snapshot_meta or {}).get("run_id")

    return {
        "decision_state": DECISION_STATE_OFFICIAL_DAILY if (ready or pre_ready) else DECISION_STATE_PROVISIONAL,
        "freshness": freshness,
        "ready": ready_items,
        "pre_ready": pre_items,
        "rising_movers": rising_items,
        "caution": caution_items,
        "scan_time": scan_time,
        "scan_run_id": root_run_id or scan_run_id or "",
        "marginable_filter": marginable_filter,
        "marginable_filter_label": marginable_filter.replace("_", " ").title(),
        "margin_rates": margin_rates,
        "marginable_source": margin_meta,
    }


def project_explorer_response(
    items: list[dict],
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    stage: str | None = None,
    snapshot_meta: dict | None = None,
    marginable_filter: str = "krungsri",
    margin_rates=None,
    price_band: str = "all",
) -> dict:
    """Build the GET /api/explorer response from serialized cards.

    Returns paginated, filterable list of all symbols in research-only format.
    The default view is limited to the owner-selected Krungsri list.
    """
    marginable_filter = normalize_filter(marginable_filter)
    margin_rates = normalize_rates(margin_rates)
    items = filter_price_band(filter_items(items, marginable_filter, margin_rates), price_band)
    margin_meta = marginable_metadata()
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    if not items:
        return {
            "decision_state": DECISION_STATE_PROVISIONAL,
            "freshness": {
                "status": "unknown",
                "source": "none",
                "as_of": None,
                "data_fetched_at": None,
            },
            "items": [],
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "total_items": 0,
            "scan_time": None,
            "scan_run_id": None,
            "marginable_filter": marginable_filter,
            "marginable_filter_label": marginable_filter.replace("_", " ").title(),
            "margin_rates": margin_rates,
            "marginable_source": margin_meta,
        }

    # Filter
    filtered = list(items)
    if stage:
        filtered = [it for it in filtered if it.get("stage") == stage]
    if search:
        q = search.strip().upper()
        filtered = [
            it for it in filtered
            if q in str(it.get("symbol", "")).upper()
            or q in str(_resolve_name(it) or "").upper()
        ]

    total_items = len(filtered)
    total_pages = max(1, math.ceil(total_items / page_size)) if total_items > 0 else 0
    page = min(page, total_pages) if total_pages > 0 else 1
    start = (page - 1) * page_size
    page_items = filtered[start:start + page_size]

    scan_time = None
    for it in items:
        ts = it.get("daily_eod_freshness", {}).get("as_of") or it.get("date")
        if ts and (scan_time is None or str(ts) > str(scan_time)):
            scan_time = str(ts)
    scan_run_id = items[0].get("provenance", {}).get("scan_run_id") if items else None

    def to_explorer_item(item: dict) -> dict:
        daily_fresh = item.get("daily_eod_freshness") or {}
        return {
            "symbol": item.get("symbol"),
            "name": _resolve_name(item) or "",
            "stage": item.get("stage"),
            "close": _number(item.get("close")),
            "change_pct": _resolve_change_pct(item),
            "phase": item.get("phase"),
            "volume": _number(item.get("volume"), 0),
            "avgDailyValue20": _number(item.get("avgDailyValue20"), 0),
            "rs": _number(item.get("rs"), 0),
            "source": item.get("priceSource") or "Daily EOD",
            "data_freshness": item.get("dataFreshness")
                or daily_fresh.get("status"),
            "decision_state": item.get("decision_state")
                or DECISION_STATE_PROVISIONAL,
            "margin_pct": _number(item.get("margin_pct")),
            "margin_rate_pct": _number(item.get("margin_rate_pct")),
            "margin_marker": item.get("margin_marker"),
            "marginable": dict(item.get("marginable") or {}),
        }

    result_items = [to_explorer_item(it) for it in page_items]
    root_run_id = (snapshot_meta or {}).get("run_id")

    return {
        "decision_state": (snapshot_meta or {}).get("decision_state") or _resolve_decision_state(items),
        "freshness": (snapshot_meta or {}).get("freshness") or _resolve_freshness(items),
        "items": result_items,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_items": total_items,
        "scan_time": scan_time,
        "scan_run_id": root_run_id or scan_run_id or "",
        "marginable_filter": marginable_filter,
        "marginable_filter_label": marginable_filter.replace("_", " ").title(),
        "margin_rates": margin_rates,
        "marginable_source": margin_meta,
    }


def project_symbol_detail(items: list[dict], symbol: str) -> dict | None:
    """Build the GET /api/symbol/{symbol} drawer detail response."""
    item = _find_item_by_symbol(items, symbol)
    if item is None:
        return None

    scan_time = None
    for it in items:
        provenance_ts = (it.get("provenance") or {}).get("scan_time")
        ts = provenance_ts or it.get("daily_eod_freshness", {}).get("as_of") or it.get("date")
        if ts and (scan_time is None or str(ts) > str(scan_time)):
            scan_time = str(ts)
    scan_run_id = items[0].get("provenance", {}).get("scan_run_id") if items else None

    detail = _card_to_shortlist_item(item, scan_time, scan_run_id)
    # Drawer must use the same shortlist projection as the card; otherwise raw
    # producer action can disagree with the publication/action queue shown in
    # Daily Shortlist.
    projected = project_shortlist_response(items, marginable_filter="all")
    projected_by_symbol = {
        entry.get("symbol"): entry
        for lane in ("ready", "pre_ready")
        for entry in projected.get(lane, [])
    }
    shortlist_item = projected_by_symbol.get(symbol.upper())
    if shortlist_item:
        detail["action"] = shortlist_item.get("action") or detail.get("action")
        detail["action_queue"] = shortlist_item.get("action_queue") or detail.get("action_queue")
    return detail


def project_canonical_symbol_detail(items: list[dict], symbol: str,
                                   snapshot_meta: dict | None = None) -> dict | None:
    """Return one canonical setup item plus metadata used by the drawer."""
    item = _find_item_by_symbol(items, symbol)
    if item is None:
        return None
    scan_time = (snapshot_meta or {}).get("scan_time") or item.get("as_of")
    scan_run_id = ((snapshot_meta or {}).get("run_id")
                   or (item.get("provenance") or {}).get("scan_run_id"))
    drawer_metadata = _card_to_shortlist_item(item, scan_time, scan_run_id)
    metadata_fields = (
        "name", "sector", "industry", "market_cap", "description", "close",
        "change_pct", "change_amount", "trade_value", "avgDailyValue20",
        "index_membership", "margin_pct", "margin_rate_pct", "high52", "low52",
        "ath_high", "ath_low",
    )
    context = item.get("context") or {}
    if drawer_metadata.get("sector") is None:
        drawer_metadata["sector"] = context.get("sector")
    if drawer_metadata.get("industry") is None:
        drawer_metadata["industry"] = context.get("industry")
    return {
        **item,
        **{field: drawer_metadata[field] for field in metadata_fields
           if drawer_metadata.get(field) is not None},
    }
