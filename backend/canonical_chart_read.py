"""Canonical, read-only chart row retrieval and aggregation rules.

This module owns the shared database read contract used by the legacy FastAPI
chart route and the MVP chart response. It deliberately returns rows in the
historical newest-first shape; public chart payload adapters reverse them to
oldest-first where required.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any


DEFAULT_CHART_CANDLE_LIMIT = 260


@dataclass(frozen=True)
class ChartReadResult:
    """Normalized, read-only chart data at the chart retrieval seam.

    This is intentionally a chart result, not a wave/evidence contract.  The
    public API adapter remains responsible for indicators and compatibility
    fields; callers receive one ordered candle representation from here.
    """

    candles: list[dict[str, Any]]
    source_timeframe: str
    provisional: bool
    as_of: str | None
    latest_time: str | None
    source: str
    label: str


def _chart_timestamp(value: Any, timeframe: str) -> str | None:
    if value is None:
        return None
    raw = value.isoformat() if hasattr(value, "isoformat") else str(value)
    raw = raw.strip()
    if not raw:
        return None
    if timeframe != "60M":
        return raw[:10] if len(raw) >= 10 else raw
    if len(raw) > 10 and raw[10] == " ":
        raw = raw[:10] + "T" + raw[11:]
    return raw


def _read_cutoff(value: Any = None) -> dt.datetime:
    """Normalize an optional point-in-time read cutoff to UTC."""
    if value is None:
        return dt.datetime.now(dt.timezone.utc)
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return dt.datetime.combine(value, dt.time.max, tzinfo=dt.timezone.utc)
    if not isinstance(value, dt.datetime):
        raise TypeError("read_cutoff must be a date or datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _lineage_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    """Return the stored source identity, tolerating older seven-column rows."""
    source = row[7] if len(row) > 7 else "price_data"
    if len(row) < 15:
        return {"source": source}
    fields = ("source_run_id", "source_first_ts", "source_last_ts",
              "source_completion_cutoff", "source_timeframe",
              "source_bar_count", "derivation_method")
    result = {"source": source}
    for field, value in zip(fields, row[8:15]):
        if value is not None:
            result[field] = _chart_timestamp(value, "60M") if field.endswith("_ts") or field == "source_completion_cutoff" else value
    return result


def _source_from_row(row: tuple[Any, ...]) -> str:
    """Return the source column when present, preserving legacy row shapes."""
    return row[7] if len(row) > 7 else "price_data"


def _source_for_provenance(provenance: dict[str, Any]) -> str:
    sources = provenance.get("sources") or [provenance.get("source")]
    sources = [source for source in sources if source]
    return sources[0] if len(sources) == 1 else ("mixed" if sources else "price_data")


def read_chart_result(cur, symbol, timeframe, limit, market="TH", read_cutoff=None) -> ChartReadResult:
    """Retrieve, normalize, and order one chart result for any supported timeframe."""
    timeframe = (timeframe or "1D").upper()
    if timeframe not in {"1D", "1W", "60M", "1M"}:
        raise ValueError("timeframe must be 1D, 1W, 60M, or 1M")
    rows, label, metadata = fetch_chart_rows_with_metadata(
        cur, symbol, timeframe, limit, market=market, read_cutoff=read_cutoff
    )
    candles = [{
        "date": _chart_timestamp(row[0], timeframe),
        "open": float(row[1]) if row[1] is not None else None,
        "high": float(row[2]) if row[2] is not None else None,
        "low": float(row[3]) if row[3] is not None else None,
        "close": float(row[4]) if row[4] is not None else None,
        "volume": float(row[5]) if row[5] is not None else None,
        "provisional": bool(row[6]) if len(row) > 6 else False,
        "source": metadata.get("source_by_date", {}).get(
            _chart_timestamp(row[0], timeframe),
            metadata.get("source") or ("intraday_price_data" if timeframe == "60M" else "price_data"),
        ),
        "provenance": metadata.get("provenance_by_date", {}).get(
            _chart_timestamp(row[0], timeframe),
            {"source": metadata.get("source") or ("intraday_price_data" if timeframe == "60M" else "price_data")},
        ),
    } for row in rows]
    # Row retrieval is newest-first; chart consumers are oldest-first.
    candles.reverse()
    as_of = candles[-1]["date"] if candles else None
    latest_time = (
        _chart_timestamp(metadata.get("latest_intraday_time"), "60M")
        or _chart_timestamp(metadata.get("latest_confirmed_time"), "1D")
        or as_of
    )
    return ChartReadResult(
        candles=candles,
        source_timeframe=timeframe,
        provisional=any(candle["provisional"] for candle in candles),
        as_of=as_of,
        latest_time=latest_time,
        source=metadata.get("source") or ("intraday_price_data" if timeframe == "60M" else "price_data"),
        label=label,
    )


def fetch_chart_rows(cur, symbol, timeframe, limit, market="TH", read_cutoff=None):
    """Return stored bars, rolling the latest current-session 60m data into Day/Week/Month."""
    rows, _label, _metadata = fetch_chart_rows_with_metadata(
        cur, symbol, timeframe, limit, market=market, read_cutoff=read_cutoff
    )
    return rows, _label


def fetch_chart_rows_with_metadata(cur, symbol, timeframe, limit, market="TH", read_cutoff=None):
    """Return chart rows plus source timestamps needed by metadata consumers."""
    if timeframe == "60M":
        if market.upper() != "TH":
            return [], "60-minute data is not configured for this market", {}
        cur.execute("""SELECT ts, open, high, low, close, volume,
                              (ROW_NUMBER() OVER (ORDER BY ts DESC) = 1) AS provisional
                       FROM intraday_price_data WHERE symbol=%s AND interval='60m'
                       ORDER BY ts DESC LIMIT %s""", (symbol, limit))
        rows = cur.fetchall()
        return rows, "60-minute (latest candle may be in progress)", {}

    # A 260-candle monthly response needs roughly 6,500 trading-day rows.
    # Keep enough read-only source history for MA240 to become verifiable.
    daily_limit = limit if timeframe == "1D" else min(limit * (25 if timeframe == "1M" else 5), 7500)
    cur.execute("""WITH official AS (
                       SELECT date::timestamp, open, high, low, close, volume,
                              false AS provisional, 'price_data' AS source,
                              NULL::text AS source_run_id, NULL::timestamptz AS source_first_ts,
                              NULL::timestamptz AS source_last_ts, NULL::timestamptz AS source_completion_cutoff,
                              NULL::text AS source_timeframe, NULL::integer AS source_bar_count,
                              NULL::text AS derivation_method
                       FROM price_data
                       WHERE market=%s AND symbol=%s
                   ), derived AS (
                       SELECT session_date::timestamp, open, high, low, close, volume,
                              false AS provisional, 'derived_daily_price_data' AS source,
                              source_run_id, source_first_ts, source_last_ts, source_completion_cutoff,
                              source_timeframe, source_bar_count, derivation_method
                       FROM derived_daily_price_data
                       WHERE symbol=%s
                         AND is_official = FALSE
                         AND source = 'settrade'
                         AND source_timeframe = '60m'
                         AND source_bar_count = 8
                         AND derivation_method = 'settrade_60m_complete_bangkok_session_ohlcv_v1'
                         AND (source_first_ts AT TIME ZONE 'Asia/Bangkok')::date = session_date
                         AND (source_last_ts AT TIME ZONE 'Asia/Bangkok')::date = session_date
                         AND (source_first_ts AT TIME ZONE 'Asia/Bangkok')::time = TIME '09:00'
                         AND (source_last_ts AT TIME ZONE 'Asia/Bangkok')::time = TIME '16:00'
                         AND source_completion_cutoff >= ((session_date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')
                         AND source_completion_cutoff <= %s
                         AND open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL
                         AND close IS NOT NULL AND volume IS NOT NULL
                         AND open::text NOT IN ('NaN', 'Infinity', '-Infinity')
                         AND high::text NOT IN ('NaN', 'Infinity', '-Infinity')
                         AND low::text NOT IN ('NaN', 'Infinity', '-Infinity')
                         AND close::text NOT IN ('NaN', 'Infinity', '-Infinity')
                         AND volume::text NOT IN ('NaN', 'Infinity', '-Infinity')
                         AND open >= 0 AND high >= 0 AND low >= 0 AND close >= 0 AND volume >= 0
                         AND high >= GREATEST(open, close, low)
                         AND low <= LEAST(open, close, high)
                         AND NOT EXISTS (
                             SELECT 1 FROM official o WHERE o.date::date = session_date
                         )
                   )
                   SELECT date, open, high, low, close, volume, provisional, source,
                          source_run_id, source_first_ts, source_last_ts,
                          source_completion_cutoff, source_timeframe, source_bar_count,
                          derivation_method
                   FROM (
                       SELECT * FROM official
                       UNION ALL
                       SELECT * FROM derived
                   ) daily_rows
                   ORDER BY date DESC LIMIT %s""",
                (market.upper(), symbol, symbol, _read_cutoff(read_cutoff), daily_limit))
    daily = cur.fetchall()
    # SQL enforces this ordering; retain the same safety boundary for older
    # read-model cursors and deterministic fake cursors used by callers/tests.
    selected_daily = {}
    for row in daily:
        date_key = _chart_timestamp(row[0], "1D")
        source = _source_from_row(row)
        previous = selected_daily.get(date_key)
        if previous is None or (source == "price_data" and _source_from_row(previous) != "price_data"):
            selected_daily[date_key] = row
    daily = list(selected_daily.values())
    # Keep the adapter tolerant of older tuple-shaped test/read-model cursors.
    source_by_date = {
        _chart_timestamp(row[0], "1D"): _source_from_row(row)
        for row in daily
    }
    provenance_by_date = {
        _chart_timestamp(row[0], "1D"): _lineage_from_row(row) for row in daily
    }
    daily = [row[:7] if len(row) > 7 else (row if len(row) >= 7 else (*row, False))
             for row in daily]
    latest_confirmed_time = daily[0][0] if daily else None
    daily_sources = set(source_by_date.values())
    if daily_sources:
        ordered_sources = [source for source in ("price_data", "derived_daily_price_data")
                           if source in daily_sources]
        metadata = {"source": " + ".join(ordered_sources),
                    "source_by_date": source_by_date,
                    "provenance_by_date": provenance_by_date}
    else:
        metadata = {}
    cur.execute("""SELECT ts, open, high, low, close, volume FROM intraday_price_data
                   WHERE symbol=%s AND interval='60m' AND (ts AT TIME ZONE 'Asia/Bangkok')::date = (NOW() AT TIME ZONE 'Asia/Bangkok')::date
                   ORDER BY ts ASC""", (symbol,))
    intra = cur.fetchall()
    if intra and isinstance(intra[-1][0], dt.datetime) and intra[-1][0].tzinfo is not None:
        stamp = intra[-1][0]
        today = stamp.astimezone(dt.timezone(dt.timedelta(hours=7))).date()
        provisional = (dt.datetime.combine(today, dt.time()), intra[0][1], max(r[2] for r in intra),
                       min(r[3] for r in intra), intra[-1][4], sum(float(r[5] or 0) for r in intra), True)
        daily = [row for row in daily if (row[0] if isinstance(row[0], dt.date) and not isinstance(row[0], dt.datetime)
                                          else row[0].date()) != today]
        provisional_date = _chart_timestamp(intra[-1][0], "1D")
        daily.append(provisional)
        metadata.setdefault("source_by_date", {})[provisional_date] = "intraday_price_data"
        metadata.setdefault("provenance_by_date", {})[provisional_date] = {
            "source": "intraday_price_data", "source_timeframe": "60m",
            "current_session": True, "provisional": True,
        }

    has_provisional = bool(intra)
    if latest_confirmed_time is not None:
        metadata["latest_confirmed_time"] = latest_confirmed_time
    daily.sort(key=lambda r: r[0], reverse=True)
    if timeframe == "1D":
        label = ("Daily EOD + provisional current session (60m as-is)"
                 if has_provisional else "Daily EOD (no current-session 60m data)")
        if has_provisional and isinstance(intra[-1][0], dt.datetime) and intra[-1][0].tzinfo is not None:
            metadata["latest_intraday_time"] = intra[-1][0]
        return daily[:limit], label, metadata

    periods = {}
    period_provenance: dict[str, dict[str, Any]] = {}
    for stamp, open_, high, low, close, volume, provisional in reversed(daily):
        day = stamp if isinstance(stamp, dt.date) and not isinstance(stamp, dt.datetime) else stamp.date()
        key = day - dt.timedelta(days=day.weekday()) if timeframe == "1W" else day.replace(day=1)
        day_key = _chart_timestamp(stamp, "1D")
        row_provenance = metadata.get("provenance_by_date", {}).get(day_key, {"source": "price_data"})
        if key not in periods:
            periods[key] = [dt.datetime.combine(key, dt.time()), open_, high, low, close,
                            float(volume or 0), bool(provisional)]
            period_provenance[_chart_timestamp(key, "1D")] = {
                "source": row_provenance.get("source", "price_data"),
                "sources": [row_provenance.get("source", "price_data")],
                "constituent_lineage": [row_provenance],
            }
        else:
            period = periods[key]
            period[2] = max(period[2], high)
            period[3] = min(period[3], low)
            period[4] = close
            period[5] += float(volume or 0)
            period[6] = period[6] or bool(provisional)
            bucket = period_provenance[_chart_timestamp(key, "1D")]
            source = row_provenance.get("source", "price_data")
            if source not in bucket["sources"]:
                bucket["sources"].append(source)
            bucket["constituent_lineage"].append(row_provenance)
            bucket["source"] = _source_for_provenance(bucket)
    for provenance in period_provenance.values():
        provenance["source"] = _source_for_provenance(provenance)
    metadata["source_by_date"] = {
        date: provenance["source"] for date, provenance in period_provenance.items()
    }
    metadata["provenance_by_date"] = period_provenance
    rows = list(reversed(sorted(periods.values(), key=lambda r: r[0])))[:limit]
    label = (("Weekly" if timeframe == "1W" else "Monthly") +
             (" + provisional current session (60m as-is)" if has_provisional
              else " Daily EOD (no current-session 60m data)"))
    if has_provisional and isinstance(intra[-1][0], dt.datetime) and intra[-1][0].tzinfo is not None:
        metadata["latest_intraday_time"] = intra[-1][0]
    return rows, label, metadata
