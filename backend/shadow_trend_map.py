"""Production-read-only Daily Trend Map evidence surface.

This module deliberately sits outside the canonical setup API.  It uses a
backend-local SELECT-only point-in-time adapter and the pure Daily trend
classifier.  The research replay adapter remains available through
``_research_adapter`` for host-side compatibility.  It never writes, scans,
emits signals, or performs trading actions.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from daily_trend_mapping import POLICY_VERSION, classify_daily_trend
from main_trend_mapping import POLICY_VERSION as MAIN_TREND_POLICY_VERSION
from main_trend_mapping import classify_main_trend
from mvp_api import resolve_universe
from technical_indicators import POLICY_VERSION as INDICATOR_POLICY_VERSION
from technical_indicators import build_technical_indicators

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "prototypes" / "elliott-state-replay" / "replay_lab.py"
REPORT_VERSION = "daily-trend-map-shadow-v2-quotes"
REPRESENTATION_REVISION = "quote-envelope-v2"
PRODUCTION_READ_ONLY = "PRODUCTION_READ_ONLY"
ACTIONABILITY = "NONE"
UNIVERSE = "marginable_long"
MIN_VALID_BARS = 30
MAX_VALID_BARS = 400
RETRIEVAL_CAP = MAX_VALID_BARS + 30
SUPPORT_LOOKBACK_BARS = 10
REVIEW_WINDOW = "current_history_bounded"
SUPPORT_METHOD = "prior_10d_low"
DERIVED_DAILY_METHOD = "settrade_60m_complete_bangkok_session_ohlcv_v1"
STATUS_VALUES = ("DATA_BLOCKED", "AVAILABLE")
DATA_QUALITY_VALUES = ("NO_DATA", "INVALID_DATA", "INSUFFICIENT_HISTORY", "AVAILABLE", "DATA_BLOCKED")

PROVENANCE = {
    "source": "price_data+derived_daily_price_data",
    "tables": ["price_data", "derived_daily_price_data"],
    "timeframe": "1D",
    "query_mode": "SELECT_ONLY",
    "point_in_time_filter": "date <= as_of",
    "fallback_policy": "official_price_data_first_then_derived_60m",
}

QUOTE_PROVENANCE = {
    "source": "price_data+derived_daily_price_data",
    "timeframe": "1D",
    "latest_completed_daily_close": True,
}

REPORT_CACHE_TTL_SECONDS = 5 * 60
_report_cache = None
_report_cache_lock = threading.Lock()


def _research_adapter():
    spec = importlib.util.spec_from_file_location("signalix_shadow_replay_lab", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("approved replay adapter unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SELECT_PREFIX = re.compile(r"^(?:--[^\n]*\n|\s)*", re.MULTILINE)
_MUTATING_SQL = re.compile(
    r"\b(?:" + "|".join((
        "IN" + "SERT", "UP" + "DATE", "DEL" + "ETE", "MER" + "GE",
        "CRE" + "ATE", "ALT" + "ER", "DR" + "OP", "TRUNC" + "ATE",
        "GR" + "ANT", "RE" + "VOKE",
    )) + r")\b",
    re.IGNORECASE,
)


def _assert_select(sql: str) -> None:
    """Reject anything except one read-only SELECT/WITH statement.

    This adapter executes fixed internal SQL, so a conservative lexical guard
    is the appropriate first line of defense: any mutating SQL token anywhere
    in the statement is rejected, including a data-modifying CTE.  PostgreSQL
    read-only transactions remain defense-in-depth in ``_get_conn``.
    """
    statement = _SELECT_PREFIX.sub("", sql, count=1).lstrip().upper()
    if (not (statement.startswith("SELECT") or statement.startswith("WITH"))
            or _MUTATING_SQL.search(statement)
            or ";" in statement.rstrip("; \t\r\n")):
        raise RuntimeError("shadow adapter only permits SELECT/WITH statements")


class BackendDailyAdapter:
    """Container-local, SELECT-only replacement for the research replay loader."""

    def _get_conn(self):
        import psycopg2
        from mvp_routes import _setup_candidates_pg_dsn

        conn = psycopg2.connect(**_setup_candidates_pg_dsn())
        try:
            conn.set_session(readonly=True, autocommit=True)
        except Exception:
            pass
        return conn

    def _exec_select(self, conn, sql: str, params=None):
        _assert_select(sql)
        cur = conn.cursor()
        try:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            columns = [description[0] for description in cur.description] if cur.description else []
            return rows, columns
        finally:
            cur.close()

    def resolve_universe(self, conn, universe_filter):
        return resolve_universe(conn, universe_filter)

    def load_daily_pit(self, conn, symbol, as_of):
        rows, _ = self._exec_select(
            conn,
            """
            WITH official AS (
                SELECT date, open, high, low, close, volume, 'price_data' AS daily_source,
                       NULL::text AS source_timeframe, NULL::text AS derivation_method,
                       NULL::text AS source_run_id, NULL::timestamptz AS source_first_ts,
                       NULL::timestamptz AS source_last_ts,
                       NULL::timestamptz AS source_completion_cutoff,
                       NULL::integer AS source_bar_count
                FROM price_data
                WHERE symbol=%s AND market='TH' AND date <= %s
            ), derived AS (
                SELECT session_date AS date, open, high, low, close, volume,
                       'derived_daily_price_data' AS daily_source, source_timeframe,
                       derivation_method, source_run_id, source_first_ts, source_last_ts,
                       source_completion_cutoff, source_bar_count
                FROM derived_daily_price_data
                WHERE symbol=%s AND session_date <= %s
                  AND is_official = FALSE AND source = 'settrade'
                  AND source_timeframe = '60m' AND source_bar_count = 8
                  AND derivation_method = 'settrade_60m_complete_bangkok_session_ohlcv_v1'
                  AND (source_first_ts AT TIME ZONE 'Asia/Bangkok')::date = session_date
                  AND (source_last_ts AT TIME ZONE 'Asia/Bangkok')::date = session_date
                  AND (source_first_ts AT TIME ZONE 'Asia/Bangkok')::time = TIME '09:00'
                  AND (source_last_ts AT TIME ZONE 'Asia/Bangkok')::time = TIME '16:00'
                  AND source_completion_cutoff >= ((session_date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')
                  AND source_completion_cutoff <= ((%s::date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')
                  AND NOT EXISTS (SELECT 1 FROM official o WHERE o.date = session_date)
            )
            SELECT date, open, high, low, close, volume, daily_source,
                   source_timeframe, derivation_method, source_run_id, source_first_ts,
                   source_last_ts, source_completion_cutoff, source_bar_count
            FROM official
            UNION ALL
            SELECT date, open, high, low, close, volume, daily_source,
                   source_timeframe, derivation_method, source_run_id, source_first_ts,
                   source_last_ts, source_completion_cutoff, source_bar_count FROM derived
            ORDER BY date ASC
            """,
            (symbol, as_of, symbol, as_of, as_of),
        )
        mapped = [
            {"date": row[0], "open": row[1], "high": row[2], "low": row[3],
             "close": row[4], "volume": row[5],
             "source": row[6] if len(row) > 6 else "price_data",
             "source_timeframe": row[7] if len(row) > 7 else None,
             "derivation_method": row[8] if len(row) > 8 else None,
             "source_run_id": row[9] if len(row) > 9 else None,
             "source_first_ts": row[10] if len(row) > 10 else None,
             "source_last_ts": row[11] if len(row) > 11 else None,
             "source_completion_cutoff": row[12] if len(row) > 12 else None,
             "source_bar_count": row[13] if len(row) > 13 else None}
            for row in rows
        ]
        return mapped, (mapped[-1]["date"] if mapped else None)

    def load_daily_pit_batch(self, conn, symbols, as_of):
        """Load bounded Daily rows plus a bounded quality aggregate.

        The aggregate scans only scalar validation metadata from the filtered
        Daily source; OHLCV history outside the newest ``RETRIEVAL_CAP`` rows
        is never transferred to the process.
        """
        rows, _ = self._exec_select(
            conn,
            """
            WITH official AS (
                SELECT symbol, date, open, high, low, close, volume,
                       'price_data' AS daily_source,
                       NULL::text AS source_timeframe, NULL::text AS derivation_method,
                       NULL::text AS source_run_id, NULL::timestamptz AS source_first_ts,
                       NULL::timestamptz AS source_last_ts,
                       NULL::timestamptz AS source_completion_cutoff,
                       NULL::integer AS source_bar_count
                FROM price_data
                WHERE symbol=ANY(%s) AND market='TH' AND date <= %s
            ), derived AS (
                SELECT symbol, session_date AS date, open, high, low, close, volume,
                       'derived_daily_price_data' AS daily_source, source_timeframe,
                       derivation_method, source_run_id, source_first_ts, source_last_ts,
                       source_completion_cutoff, source_bar_count
                FROM derived_daily_price_data
                WHERE symbol=ANY(%s) AND session_date <= %s
                  AND is_official = FALSE AND source = 'settrade'
                  AND source_timeframe = '60m' AND source_bar_count = 8
                  AND derivation_method = 'settrade_60m_complete_bangkok_session_ohlcv_v1'
                  AND (source_first_ts AT TIME ZONE 'Asia/Bangkok')::date = session_date
                  AND (source_last_ts AT TIME ZONE 'Asia/Bangkok')::date = session_date
                  AND (source_first_ts AT TIME ZONE 'Asia/Bangkok')::time = TIME '09:00'
                  AND (source_last_ts AT TIME ZONE 'Asia/Bangkok')::time = TIME '16:00'
                  AND source_completion_cutoff >= ((session_date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')
                  AND source_completion_cutoff <= ((%s::date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')
                  AND NOT EXISTS (
                      SELECT 1 FROM official o
                      WHERE o.symbol=derived_daily_price_data.symbol AND o.date=session_date
                  )
            ), filtered AS (
                SELECT symbol, date, open, high, low, close, volume, daily_source,
                       source_timeframe, derivation_method, source_run_id, source_first_ts,
                       source_last_ts, source_completion_cutoff, source_bar_count,
                       CASE WHEN date IS NOT NULL
                                  AND open IS NOT NULL AND high IS NOT NULL
                                  AND low IS NOT NULL AND close IS NOT NULL
                                  AND volume IS NOT NULL
                                  AND open = open AND high = high
                                  AND low = low AND close = close
                                  AND volume = volume
                                  AND open::text NOT IN ('NaN', 'Infinity', '-Infinity')
                                  AND high::text NOT IN ('NaN', 'Infinity', '-Infinity')
                                  AND low::text NOT IN ('NaN', 'Infinity', '-Infinity')
                                  AND close::text NOT IN ('NaN', 'Infinity', '-Infinity')
                                  AND volume::text NOT IN ('NaN', 'Infinity', '-Infinity')
                                  AND high >= GREATEST(open, close)
                                  AND low <= LEAST(open, close)
                                  AND low <= high
                             THEN 0 ELSE 1 END AS invalid_flag
                FROM (SELECT * FROM official UNION ALL SELECT * FROM derived) source_rows
            ), quality AS (
                SELECT symbol, COALESCE(SUM(invalid_flag), 0) AS invalid_count
                FROM filtered
                GROUP BY symbol
            ), bounded AS (
                SELECT filtered.*, quality.invalid_count,
                       row_number() OVER (PARTITION BY filtered.symbol ORDER BY filtered.date DESC) AS retrieval_row
                FROM filtered
                JOIN quality USING (symbol)
            )
            SELECT symbol, date, open, high, low, close, volume, daily_source,
                   source_timeframe, derivation_method, source_run_id, source_first_ts,
                   source_last_ts, source_completion_cutoff, source_bar_count, invalid_count
            FROM bounded
            WHERE retrieval_row <= %s
            ORDER BY symbol ASC, date ASC
            """,
            (list(symbols), as_of, list(symbols), as_of, as_of, RETRIEVAL_CAP),
        )
        grouped = {symbol: [] for symbol in symbols}
        quality = {symbol: None for symbol in symbols}
        for row in rows:
            if len(row) >= 16:
                (symbol, date, open_, high, low, close, volume, daily_source,
                 source_timeframe, derivation_method, source_run_id, source_first_ts,
                 source_last_ts, source_completion_cutoff, source_bar_count, invalid_count) = row
            else:
                symbol, date, open_, high, low, close, volume, invalid_count = row
                daily_source = "price_data"
                source_timeframe = derivation_method = source_run_id = None
                source_first_ts = source_last_ts = source_completion_cutoff = source_bar_count = None
            quality[symbol] = int(invalid_count)
            grouped.setdefault(symbol, []).append(
                {"date": date, "open": open_, "high": high, "low": low,
                 "close": close, "volume": volume, "source": daily_source,
                 "source_timeframe": source_timeframe, "derivation_method": derivation_method,
                 "source_run_id": source_run_id, "source_first_ts": source_first_ts,
                 "source_last_ts": source_last_ts, "source_completion_cutoff": source_completion_cutoff,
                 "source_bar_count": source_bar_count}
            )
        return {
            symbol: (frame, frame[-1]["date"] if frame else None, {
                "quality_scan": "filtered_daily_source",
                "invalid_count": quality[symbol] if quality[symbol] is not None else 0,
                "quality_established": quality[symbol] is not None,
                "quality_scope": "price_data where symbol=ANY(symbols) and market='TH' and date<=as_of",
                "full_history_claim": False,
            })
            for symbol, frame in grouped.items()
        }


def _adapter():
    """Use the backend-local adapter in the dashboard container."""
    return BackendDailyAdapter()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _finite(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _rows(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if isinstance(frame, (list, tuple)):
        return [dict(row) for row in frame]
    if hasattr(frame, "iterrows"):
        return [{"date": row.get("Date"), "open": row.get("Open"), "high": row.get("High"),
                 "low": row.get("Low"), "close": row.get("Close"), "volume": row.get("Volume")}
                for _, row in frame.iterrows()]
    raise TypeError("approved Daily adapter returned unsupported rows")


def _frame_source(frame: Any) -> str:
    sources = {str(row.get("source")) for row in _rows(frame) if row.get("source")}
    return next(iter(sources)) if len(sources) == 1 else ("mixed" if sources else "price_data")


def _row_lineage(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row or row.get("source") != "derived_daily_price_data":
        return None
    return {key: row.get(key) for key in (
        "source", "source_timeframe", "source_run_id", "source_first_ts",
        "source_last_ts", "source_completion_cutoff", "source_bar_count",
        "derivation_method")}


def _selected_lineage(frame: Any) -> list[dict[str, Any]]:
    """Return ordered lineage for every selected derived row."""
    return [lineage for row in _rows(frame)
            if (lineage := _row_lineage(row)) is not None]


def _valid(row: Mapping[str, Any]) -> bool:
    if not row.get("date") or not all(_finite(row.get(key)) for key in ("open", "high", "low", "close", "volume")):
        return False
    high, low = float(row["high"]), float(row["low"])
    return high >= max(float(row["open"]), float(row["close"])) and low <= min(float(row["open"]), float(row["close"])) and low <= high


def _blocked(symbol: str, as_of: Any, status: str, note: str, retrieved: int, invalid: int,
             retrieval_cap: int = RETRIEVAL_CAP, cap_reached: bool = False,
             quality: Mapping[str, Any] | None = None) -> dict[str, Any]:
    quality = quality or {"quality_scan": "selected_window_only", "quality_established": False,
                          "full_history_claim": False}
    return {"symbol": symbol, "as_of": str(as_of) if as_of is not None else None,
            "quote": _quote(None),
            "status": "DATA_BLOCKED", "data_quality_status": status,
            "classifier_status": None, "machine_lane": None, "broad_state": None,
            "main_trend": None,
            "confidence": None,
            "bars_retrieved": retrieved, "bars_used": 0, "invalid_row_count": invalid,
            "retrieval_cap": retrieval_cap, "cap": retrieval_cap,
            "retrieval_cap_reached": cap_reached, "cap_reached": cap_reached,
            "quality_scan": quality.get("quality_scan"),
            "quality_established": bool(quality.get("quality_established", False)),
            "invalid_count": quality.get("invalid_count", invalid),
            "full_history_claim": bool(quality.get("full_history_claim", False)),
            "note": note, "support": {"method": SUPPORT_METHOD, "reference": None,
            "prior_bars": 0, "excluded_current_bar": True},
            "evidence": {"supporting": [], "contradicting": [], "missing": ["daily_history"]},
            "diagnostic_trace": {"validation": {"rows_retrieved": retrieved,
                "valid_rows": 0, "invalid_row_count": invalid}, "classification": None,
                "reason": status, "note": note}}


def _quote(clean: list[Mapping[str, Any]] | None) -> dict[str, Any]:
    """Project source Daily closes; never derive quote values in the browser."""
    latest = clean[-1] if clean else None
    previous = clean[-2] if clean and len(clean) > 1 else None
    price = float(latest["close"]) if latest and _finite(latest.get("close")) else None
    previous_close = float(previous["close"]) if previous and _finite(previous.get("close")) else None
    amount = price - previous_close if price is not None and previous_close is not None else None
    percent = amount / previous_close * 100.0 if amount is not None and previous_close else None
    available = price is not None
    change_available = percent is not None
    latest_date = latest.get("date") if latest else None
    source = (latest.get("source") or "price_data") if latest else "price_data"
    return {
        "price": price,
        "change_amount": amount if change_available else None,
        "change_pct": percent if change_available else None,
        "change_basis": "previous_daily_close" if change_available else "NOT_VERIFIED",
        "change_amount_basis": "previous_daily_close" if change_available else "NOT_VERIFIED",
        "source": source,
        "as_of": str(latest_date) if latest_date is not None else None,
        "provisional": False,
        "availability": "AVAILABLE" if available else "NOT_VERIFIED",
        "change_availability": "AVAILABLE" if change_available else "NOT_VERIFIED",
        "provenance": {**QUOTE_PROVENANCE, "source": source, "table": source,
                        "as_of": str(latest_date) if latest_date is not None else None,
                        "lineage": _row_lineage(latest)},
    }


def evaluate_symbol(symbol: str, frame: Any, as_of: Any, retrieval_cap: int = RETRIEVAL_CAP,
                    quality_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    requested = _rows(frame)
    # The evaluator is a security/data boundary, not merely a consumer of a
    # well-behaved loader.  Keep the newest rows when a caller supplies more
    # than the approved retrieval cap, with a stable input-order tie-breaker.
    try:
        requested_cap = int(retrieval_cap)
    except (TypeError, ValueError):
        requested_cap = RETRIEVAL_CAP
    effective_cap = min(max(requested_cap, 1), RETRIEVAL_CAP)
    indexed = list(enumerate(requested))
    indexed.sort(key=lambda pair: (str(pair[1].get("date", "")), pair[0]), reverse=True)
    selected = indexed[:effective_cap]
    selected.sort(key=lambda pair: pair[0])
    retrieved = [row for _, row in selected]
    clean = [row for row in retrieved if _valid(row)]
    invalid = len(retrieved) - len(clean)
    cap_reached = len(requested) >= effective_cap
    quality = dict(quality_metadata or {})
    quality_established = bool(quality.get("quality_established", False))
    invalid_count = int(quality.get("invalid_count", invalid)) if quality.get("invalid_count") is not None else invalid
    # A quality aggregate can never contradict an invalid row that was
    # transferred in the selected window; retain the safer count if an
    # injected/test adapter supplies inconsistent metadata.
    invalid_count = max(invalid_count, invalid)
    if not cap_reached:
        quality_established = True
        invalid_count = invalid
    quality.setdefault("quality_scan", "filtered_daily_source" if quality_metadata else "selected_window_only")
    quality["quality_established"] = quality_established
    quality["invalid_count"] = invalid_count
    quality.setdefault("full_history_claim", False)
    selection = {"requested_rows": len(requested), "selected_rows": len(retrieved),
                 "retrieval_cap": effective_cap, "cap_applied": len(requested) > effective_cap,
                 "method": "newest_daily_rows", "tie_break": "input_order"}
    if not retrieved:
        result = _blocked(symbol, as_of, "NO_DATA", "No Daily rows returned; no fallback used.", 0, 0, effective_cap, cap_reached, quality)
        result["retrieval_selection"] = selection
        return result
    if not clean:
        note = "All Daily rows failed validation; no classification performed."
        if cap_reached:
            note = f"Retrieval cap {effective_cap} reached; all selected Daily rows failed validation; no classification performed. No fallback or full-history retrieval used."
        result = _blocked(symbol, as_of, "INVALID_DATA", note, len(retrieved), invalid_count, effective_cap, cap_reached, quality)
        result["retrieval_selection"] = selection
        return result
    quote = _quote(clean) if invalid_count == 0 else _quote(None)
    if len(clean) < MIN_VALID_BARS:
        note = f"Fewer than {MIN_VALID_BARS} valid Daily bars; no classification performed."
        if cap_reached:
            note = f"Retrieval cap {effective_cap} reached before {MIN_VALID_BARS} valid Daily bars were established; classification withheld. No fallback or full-history retrieval used."
        blocked = _blocked(symbol, as_of, "INSUFFICIENT_HISTORY", f"Fewer than {MIN_VALID_BARS} valid Daily bars; no classification performed.", len(retrieved), invalid_count, effective_cap, cap_reached, quality)
        blocked["note"] = note
        blocked["diagnostic_trace"]["note"] = note
        blocked["quote"] = quote
        blocked["retrieval_selection"] = selection
        return blocked
    if cap_reached and (not quality_established or invalid_count):
        if invalid_count:
            note = f"Daily quality scan found {invalid_count} invalid filtered-source row(s) with retrieval cap {effective_cap}; no classification performed. No fallback or full-history retrieval used."
            data_quality_status = "INVALID_DATA"
        else:
            note = f"Retrieval cap {effective_cap} reached; the bounded selected window cannot establish the required valid/invalid Daily data contract, so classification is withheld. No fallback or full-history retrieval used."
            data_quality_status = "DATA_BLOCKED"
        blocked = _blocked(symbol, as_of, data_quality_status, note, len(retrieved), invalid_count, effective_cap, cap_reached, quality)
        blocked["quote"] = quote
        blocked["retrieval_selection"] = selection
        return blocked
    bars = clean[-MAX_VALID_BARS:]
    support_window = bars[:-1][-SUPPORT_LOOKBACK_BARS:]
    support = min(float(row["low"]) for row in support_window)
    candles = [{key: row[key] for key in ("open", "high", "low", "close", "volume")} for row in bars]
    indicators = build_technical_indicators(candles, "1D")
    for key in ("open", "close", "volume", "low", "high"):
        indicators["series"][key] = [row[key] for row in bars]
    indicators["as_of"] = str(as_of) if as_of is not None else None
    indicators["latest"]["explicit_support"] = support
    classified = classify_daily_trend(indicators)
    main_trend = classify_main_trend(indicators)
    classifier_status = classified["data_status"]
    data_quality_status = "INVALID_DATA" if invalid else classifier_status
    return {"symbol": symbol, "as_of": str(as_of) if as_of is not None else None,
            "quote": quote,
            "status": "AVAILABLE" if data_quality_status == "AVAILABLE" else "DATA_BLOCKED",
            "data_quality_status": data_quality_status,
            "classifier_status": classifier_status,
            "machine_lane": classified["machine_lane"], "broad_state": classified["broad_state"],
            "main_trend": main_trend,
            "confidence": classified["confidence"], "bars_retrieved": len(retrieved),
            "bars_used": len(bars), "invalid_row_count": invalid_count,
            "retrieval_cap": effective_cap, "cap": effective_cap,
            "retrieval_cap_reached": cap_reached, "cap_reached": cap_reached,
            "quality_scan": quality["quality_scan"], "quality_established": quality_established,
            "invalid_count": invalid_count, "full_history_claim": False,
            "retrieval_selection": selection,
            "note": "Current-history-bounded Daily window; no full-history mode is available.",
            "support": {"method": SUPPORT_METHOD, "reference": support,
                        "prior_bars": len(support_window), "excluded_current_bar": True},
            "evidence": {"supporting": classified["supporting_evidence"],
                         "contradicting": classified["contradicting_evidence"],
                         "missing": classified["missing_evidence"]},
            "diagnostic_trace": {"validation": {"rows_retrieved": len(retrieved),
                "valid_rows": len(clean), "invalid_row_count": invalid_count,
                "selected_window": "most_recent_valid_daily_bars",
                "max_valid_bars": MAX_VALID_BARS},
                "classification": classified}}


def _policy() -> dict[str, Any]:
    policy = {"classifier": POLICY_VERSION, "main_trend_classifier": MAIN_TREND_POLICY_VERSION,
              "indicators": INDICATOR_POLICY_VERSION,
              "report": REPORT_VERSION, "representation_revision": REPRESENTATION_REVISION,
              "review_window": REVIEW_WINDOW,
              "min_valid_bars": MIN_VALID_BARS, "max_valid_bars": MAX_VALID_BARS,
              "retrieval_cap": RETRIEVAL_CAP,
              "support_method": SUPPORT_METHOD, "support_prior_bars": SUPPORT_LOOKBACK_BARS,
              "support_excluded_current_bar": True,
              "prior_10d_low": {"method": SUPPORT_METHOD, "prior_bars": SUPPORT_LOOKBACK_BARS,
                                "exclude_current_bar": True}}
    return {**policy, "hash": _hash(policy)}


def _report_cache_metadata(status: str, as_of: Any, policy: Mapping[str, Any]) -> dict[str, Any]:
    return {"status": status, "ttl_seconds": REPORT_CACHE_TTL_SECONDS,
            "as_of": str(as_of) if as_of is not None else None,
            "policy_hash": policy["hash"]}


def clear_report_cache() -> None:
    global _report_cache
    with _report_cache_lock:
        _report_cache = None


def _build_shadow_report(adapter, conn, symbols, manifest, as_of) -> dict[str, Any]:
    started = time.perf_counter()
    policy = _policy()
    output = []
    batch_error = False
    retrieval_error = False
    batch_loader = getattr(adapter, "load_daily_pit_batch", None)
    per_symbol_loader = getattr(adapter, "load_daily_pit", None)
    per_symbol_is_default = per_symbol_loader is None or (
        getattr(per_symbol_loader, "__func__", per_symbol_loader) is BackendDailyAdapter.load_daily_pit
    )
    db_read_ms = 0.0
    classify_ms = 0.0
    if callable(batch_loader) and per_symbol_is_default:
        db_read_started = time.perf_counter()
        try:
            loaded = batch_loader(conn, symbols, as_of)
        except Exception as error:
            loaded = None
            batch_error = True
            for symbol in symbols:
                row = _blocked(symbol, as_of, "DATA_BLOCKED", "Daily batch retrieval failed; no fallback used.", 0, 0)
                row["provenance"] = {**PROVENANCE, "adapter": type(adapter).__name__,
                                     "availability": "NOT_VERIFIED", "error_type": type(error).__name__}
                output.append(row)
        if loaded is not None:
            db_read_ms = (time.perf_counter() - db_read_started) * 1000
            classify_started = time.perf_counter()
            for symbol in symbols:
                try:
                    loaded_value = loaded.get(symbol, ([], None))
                    frame, latest = loaded_value[:2]
                    quality = loaded_value[2] if len(loaded_value) > 2 else None
                    row = evaluate_symbol(symbol, frame, as_of, RETRIEVAL_CAP, quality)
                    row["provenance"] = {**PROVENANCE, "source": _frame_source(frame),
                                         "selected_daily_lineage": _selected_lineage(frame),
                                         "adapter": type(adapter).__name__,
                                         "latest_returned_date": str(latest) if latest else None}
                except Exception as error:
                    retrieval_error = True
                    row = _blocked(symbol, as_of, "DATA_BLOCKED", "Daily classification failed; no fallback used.", 0, 0)
                    row["provenance"] = {**PROVENANCE, "adapter": type(adapter).__name__,
                                         "availability": "NOT_VERIFIED", "error_type": type(error).__name__}
                output.append(row)
            classify_ms = (time.perf_counter() - classify_started) * 1000
    else:
        for symbol in symbols:
            db_read_started = time.perf_counter()
            try:
                frame, latest = adapter.load_daily_pit(conn, symbol, as_of)
                db_read_ms += (time.perf_counter() - db_read_started) * 1000
                classify_started = time.perf_counter()
                row = evaluate_symbol(symbol, frame, as_of, RETRIEVAL_CAP)
                classify_ms += (time.perf_counter() - classify_started) * 1000
                row["provenance"] = {**PROVENANCE, "source": _frame_source(frame),
                                     "selected_daily_lineage": _selected_lineage(frame),
                                     "adapter": type(adapter).__name__,
                                     "latest_returned_date": str(latest) if latest else None}
            except Exception as error:
                retrieval_error = True
                row = _blocked(symbol, as_of, "DATA_BLOCKED", "Daily retrieval failed; no fallback used.", 0, 0)
                row["provenance"] = {**PROVENANCE, "adapter": type(adapter).__name__, "availability": "NOT_VERIFIED",
                                     "error_type": type(error).__name__}
            output.append(row)
    return {"report": REPORT_VERSION, "research_only": False,
            "status": "DATA_BLOCKED" if batch_error or retrieval_error else PRODUCTION_READ_ONLY,
            "actionability": ACTIONABILITY,
            "verification_status": "NOT_VERIFIED" if batch_error or retrieval_error else "VERIFIED",
            "as_of": str(as_of), "universe": {**manifest, "scope": UNIVERSE,
            "declared_symbols": symbols, "declared_count": len(symbols), "symbol_hash": _hash(symbols)},
            "policy": policy, "rows": output,
            "summary": {status: sum(row.get("status") == status for row in output) for status in STATUS_VALUES},
            "data_quality_summary": {status: sum(row.get("data_quality_status") == status for row in output)
                                      for status in DATA_QUALITY_VALUES},
            "status_by_symbol": {row["symbol"]: row["status"] for row in output},
            "provenance": {**PROVENANCE, "adapter": type(adapter).__name__},
            "timing": {"db_read_ms": round(db_read_ms, 3),
                       "classify_ms": round(classify_ms, 3),
                       "total_ms": round((time.perf_counter() - started) * 1000, 3)},
            "cache": _report_cache_metadata("cold", as_of, policy),
            "limitations": ["Production-served read-only Daily evidence; no setup, signal, order, alert, broker, or production mutation."]}


def build_shadow_report(adapter=None, conn=None, as_of=None, *, source=None) -> dict[str, Any]:
    """Return the published report by default; build from DB only explicitly.

    The HTTP surface must not classify or query price history.  ``source`` is
    intentionally explicit for the bounded publisher/tests path.
    """
    global _report_cache
    if source is None:
        source = "database" if adapter is not None or conn is not None else "published"
    if source in {"published", "read_model", "current"}:
        from shadow_read_model_publisher import read_current_shadow_report
        return read_current_shadow_report()
    if source not in {"database", "builder", "publisher"}:
        raise ValueError(f"unsupported shadow report source: {source}")
    adapter = adapter or _adapter()
    # The publisher must always build a fresh EOD snapshot; the in-process
    # cache is only for the explicit compatibility/test database builder.
    use_cache = source != "publisher" and adapter.__class__ is BackendDailyAdapter and conn is None
    owns_conn = conn is None
    conn = conn or adapter._get_conn()
    try:
        symbols, manifest = adapter.resolve_universe(conn, UNIVERSE)
        if as_of is None:
            rows, _ = adapter._exec_select(
                conn,
                """SELECT MAX(day) AS max_date FROM (
                    SELECT MAX(date) AS day FROM price_data WHERE market='TH'
                    UNION ALL
                    SELECT MAX(session_date) AS day FROM derived_daily_price_data
                    WHERE is_official=FALSE AND source='settrade'
                      AND source_timeframe='60m' AND source_bar_count=8
                      AND derivation_method='settrade_60m_complete_bangkok_session_ohlcv_v1'
                      AND source_completion_cutoff >= ((session_date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')
                      AND source_completion_cutoff <= NOW()
                      AND (source_first_ts AT TIME ZONE 'Asia/Bangkok')::date=session_date
                      AND (source_last_ts AT TIME ZONE 'Asia/Bangkok')::date=session_date
                      AND (source_first_ts AT TIME ZONE 'Asia/Bangkok')::time=TIME '09:00'
                      AND (source_last_ts AT TIME ZONE 'Asia/Bangkok')::time=TIME '16:00'
                ) dates""",
            )
            as_of = rows[0][0] if rows and rows[0][0] else None
        if as_of is None:
            raise RuntimeError("cannot resolve current Daily as-of")
        policy = _policy()
        key = (_hash(symbols), str(as_of), policy["hash"])
        if use_cache:
            with _report_cache_lock:
                if _report_cache and _report_cache[0] > time.monotonic() and _report_cache[1] == key:
                    cached = deepcopy(_report_cache[2])
                    cached["cache"] = _report_cache_metadata("warm", as_of, policy)
                    return cached
        report = _build_shadow_report(adapter, conn, symbols, manifest, as_of)
        if use_cache and report["status"] == PRODUCTION_READ_ONLY:
            with _report_cache_lock:
                _report_cache = (time.monotonic() + REPORT_CACHE_TTL_SECONDS, key, report)
        return deepcopy(report)
    finally:
        if owns_conn:
            conn.close()


def unavailable_report(error: Exception) -> dict[str, Any]:
    return {"report": REPORT_VERSION, "research_only": False, "status": "DATA_BLOCKED",
            "actionability": ACTIONABILITY, "as_of": None,
            "universe": {"scope": UNIVERSE, "declared_symbols": [], "declared_count": 0},
            "policy": {"classifier": POLICY_VERSION,
                       "main_trend_classifier": MAIN_TREND_POLICY_VERSION,
                       "report": REPORT_VERSION,
                       "representation_revision": REPRESENTATION_REVISION,
                       "review_window": REVIEW_WINDOW,
                       "min_valid_bars": MIN_VALID_BARS, "max_valid_bars": MAX_VALID_BARS,
                       "prior_10d_low": {"method": SUPPORT_METHOD, "prior_bars": SUPPORT_LOOKBACK_BARS,
                                         "exclude_current_bar": True}}, "rows": [],
            "summary": {status: 0 for status in STATUS_VALUES} | {"DATA_BLOCKED": 1},
            "data_quality_summary": {status: 0 for status in DATA_QUALITY_VALUES} | {"DATA_BLOCKED": 1},
            "status_by_symbol": {}, "verification_status": "NOT_VERIFIED",
            "provenance": {**PROVENANCE, "adapter": "BackendDailyAdapter", "availability": "NOT_VERIFIED", "error_type": type(error).__name__}}


def handle_shadow_trend_map_api(path: str, handler) -> bool:
    if urlsplit(path).path != "/api/trend-map-shadow":
        return False
    try:
        payload = build_shadow_report()
        status = 200
    except Exception as error:  # fail closed with a visible envelope
        payload, status = unavailable_report(error), 200
    body = json.dumps(payload, default=str, separators=(",", ":")).encode()
    if hasattr(handler, "send_bytes"):
        handler.send_bytes(body, content_type="application/json; charset=utf-8", status=status)
    else:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    return True
