"""Facts-only Team Scan v1 projection and deterministic views.

This module intentionally has no dependency on the setup-candidate contract.
It consumes bounded OHLCV rows from the published marginable_long universe.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from statistics import mean

TIMEZONE = "Asia/Bangkok"
API_VERSION = "team-facts-v1"
MAX_DAILY = 400
MAX_INTRADAY = 200
VOLUME_RATIO_BASIS = "current_daily_volume / mean(previous_20_daily_volumes)"
_CANONICAL_UNIVERSE = "marginable_long"

_ITEM_KEYS = {"identity", "current", "indicators", "candles", "provenance"}
_FORBIDDEN = {"state", "setup", "lane", "trigger", "trade_stop", "thesis_invalidation",
              "target", "risk_distance", "rr", "r:r", "wave", "primary_state",
              "mapped_label", "classification", "higher_low", "prior_advance",
              "reclaim", "buy", "order"}


def load_ohlcv(pg, symbols, *, daily_limit=MAX_DAILY, intraday_limit=MAX_INTRADAY):
    """Read bounded Daily and 60m history; never invokes a builder or writes."""
    cur = pg.cursor()
    try:
        cur.execute("""SELECT symbols.symbol, rows.date, rows.open, rows.high,
                              rows.low, rows.close, rows.volume
                       FROM unnest(%s::text[]) AS symbols(symbol)
                       CROSS JOIN LATERAL (
                         SELECT date, open, high, low, close, volume FROM price_data
                         WHERE market='TH' AND symbol=symbols.symbol
                         ORDER BY date DESC LIMIT %s) rows
                       ORDER BY symbols.symbol, rows.date""", (list(symbols), daily_limit))
        daily = {}
        for symbol, stamp, open_, high, low, close, volume in cur.fetchall():
            daily.setdefault(str(symbol).upper(), []).append((stamp, open_, high, low, close, volume))
        cur.execute("""SELECT symbols.symbol, rows.ts, rows.open, rows.high,
                              rows.low, rows.close, rows.volume
                       FROM unnest(%s::text[]) AS symbols(symbol)
                       CROSS JOIN LATERAL (
                         SELECT ts, open, high, low, close, volume FROM intraday_price_data
                         WHERE symbol=symbols.symbol AND interval='60m'
                         ORDER BY ts DESC LIMIT %s) rows
                       ORDER BY symbols.symbol, rows.ts""", (list(symbols), intraday_limit))
        intraday = {}
        for symbol, stamp, open_, high, low, close, volume in cur.fetchall():
            intraday.setdefault(str(symbol).upper(), []).append((stamp, open_, high, low, close, volume))
        return daily, intraday
    finally:
        cur.close()


def load_history(pg, symbol, timeframe, limit):
    """Read only one requested symbol/timeframe for the detail route."""
    cur = pg.cursor()
    try:
        if timeframe == "1D":
            cur.execute("""SELECT date, open, high, low, close, volume FROM price_data
                           WHERE market='TH' AND symbol=%s ORDER BY date DESC LIMIT %s""",
                        (symbol, limit))
        else:
            cur.execute("""SELECT ts, open, high, low, close, volume FROM intraday_price_data
                           WHERE symbol=%s AND interval='60m' ORDER BY ts DESC LIMIT %s""",
                        (symbol, limit))
        return cur.fetchall()
    finally:
        cur.close()


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _sma(values, n):
    return mean(values[-n:]) if len(values) >= n else None


def _rsi(values, n=14):
    if len(values) <= n:
        return None
    gains = [max(values[i] - values[i - 1], 0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0) for i in range(1, len(values))]
    avg_gain, avg_loss = mean(gains[-n:]), mean(losses[-n:])
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def _stamp(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _aware_datetime(value):
    """Parse a timestamp without turning a Daily date into an instant."""
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _latest_completed(intraday_by_symbol, now):
    boundary = now.replace(minute=0, second=0, microsecond=0) if now else None
    stamps = []
    for rows in intraday_by_symbol.values():
        for row in rows:
            stamp = _stamp(row[0])
            if boundary is None or _is_completed(stamp, boundary):
                parsed = _aware_datetime(stamp)
                if parsed is not None:
                    stamps.append(parsed)
    latest = max(stamps) if stamps else None
    return latest.isoformat() if latest else None


def _candle(row, timeframe, source):
    stamp, open_, high, low, close, volume = row[:6]
    return {"timestamp": _stamp(stamp), "open": _num(open_), "high": _num(high),
            "low": _num(low), "close": _num(close), "volume": _num(volume),
            "timeframe": timeframe, "source": source}


def _facts(identity, daily, intraday, *, now=None):
    daily = [_candle(r, "1D", "price_data") for r in daily]
    intraday = [_candle(r, "60m", "intraday_price_data") for r in intraday]
    daily = sorted(daily, key=lambda x: x["timestamp"] or "")
    intraday = sorted(intraday, key=lambda x: x["timestamp"] or "")
    # Stored bars are observations; only bars whose timestamp has reached the
    # current completed hourly boundary qualify for a view.
    boundary = None
    if now is not None and hasattr(now, "replace"):
        boundary = now.replace(minute=0, second=0, microsecond=0)
    completed = [bar for bar in intraday if boundary is None or _is_completed(bar["timestamp"], boundary)]
    latest_intra = completed[-1] if completed else None
    current = daily[-1] if daily else None
    closes = [x["close"] for x in daily if x["close"] is not None]
    volumes = [x["volume"] for x in daily if x["volume"] is not None]
    price = latest_intra["close"] if latest_intra else (current["close"] if current else None)
    previous = daily[-2]["close"] if len(daily) > 1 else None
    previous_volumes = volumes[:-1][-20:]
    average_previous_volume = mean(previous_volumes) if len(previous_volumes) == 20 else None
    has_daily_baseline = bool(daily)
    indicators = {
        "sma5": _sma(closes, 5), "sma20": _sma(closes, 20),
        "sma50": _sma(closes, 50), "sma200": _sma(closes, 200),
        "volume": current["volume"] if current else None,
        "average_volume": _sma(volumes, 20), "volume_ratio_20": None,
        "rsi14": _rsi(closes), "high_20": max((x["high"] for x in daily[-20:] if x["high"] is not None), default=None),
        "high_52w": max((x["high"] for x in daily[-252:] if x["high"] is not None), default=None),
        "previous_252_high": max((x["high"] for x in daily[-253:-1] if x["high"] is not None), default=None),
    }
    if average_previous_volume is not None and indicators["volume"] is not None:
        indicators["volume_ratio_20"] = indicators["volume"] / average_previous_volume
    high = indicators["high_52w"]
    indicators["distance_to_high_52w_pct"] = ((price / high) - 1) * 100 if price is not None and high else None
    change = price - previous if has_daily_baseline and price is not None and previous is not None else None
    change_pct = change / previous * 100 if change is not None and previous else None
    latest_timestamp = latest_intra["timestamp"] if latest_intra else (current["timestamp"] if current else None)
    # Keep the original machine-readable names and publish the facts contract
    # spellings as aliases.  Every value above is calculated from Daily rows.
    indicators.update({
        "SMA5": indicators["sma5"], "SMA20": indicators["sma20"],
        "SMA50": indicators["sma50"], "SMA200": indicators["sma200"],
        "RSI14": indicators["rsi14"],
        "volume_average": indicators["average_volume"],
        "volume_ratio": indicators["volume_ratio_20"],
        "high20": indicators["high_20"], "high52w": indicators["high_52w"],
        "previous252high": indicators["previous_252_high"],
    })
    missing_reasons = []
    if not has_daily_baseline:
        missing_reasons.append("daily_baseline_missing")
    if not completed:
        missing_reasons.append("completed_60m_missing")
    return {"identity": identity, "data_status": {
        "status": "DATA_INCOMPLETE" if missing_reasons else "COMPLETE",
        "reasons": missing_reasons,
    }, "current": {"latest_price": price, "previous_daily_close": previous,
        "change_amount": change, "change_pct": change_pct, "timestamp": latest_timestamp,
        "timeframe": "60m" if latest_intra else "1D", "completed_bar": bool(latest_intra or current)}, "indicators": indicators,
        "candles": {"daily": daily, "completed_60m": completed},
        "provenance": {"daily": {"source": "price_data", "timeframe": "1D",
                                    "latest": current["timestamp"] if current else None},
                        "intraday": {"source": "intraday_price_data", "timeframe": "60m",
                                      "latest_completed": latest_intra["timestamp"] if latest_intra else None}}}


def _is_completed(stamp, boundary):
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if parsed.tzinfo is None and boundary.tzinfo is not None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= boundary
    except (TypeError, ValueError):
        return False


def _eligible(f, view, now=None):
    c, i = f["current"], f["indicators"]
    common = [(f["identity"].get("can_buy") is True, "can_buy"),
              (f["identity"].get("instrument_type") == "ORD", "instrument_type"),
              (bool(f["candles"]["daily"]), "daily_close"),
              (bool(f["candles"]["completed_60m"]), "completed_intraday"),
              (c["latest_price"] is not None and i["volume"] is not None, "price_or_volume")]
    if any(not ok for ok, _ in common):
        return False, next(reason for ok, reason in common if not ok)
    if now is not None:
        try:
            latest = datetime.fromisoformat(
                f["provenance"]["intraday"]["latest_completed"].replace("Z", "+00:00")
            )
            daily = datetime.fromisoformat(
                f["provenance"]["daily"]["latest"][:10]
            ).replace(tzinfo=timezone.utc)
        except (AttributeError, TypeError, ValueError):
            return False, "stale"
        if (now - latest).total_seconds() > 3 * 86400:
            return False, "60m_stale"
        if (now - daily).total_seconds() > 7 * 86400:
            return False, "daily_stale"
    if view == "momentum":
        checks = [(c["change_pct"] is not None and c["change_pct"] > 0, "change_pct"),
                  (i["sma5"] is not None and c["latest_price"] > i["sma5"], "sma5"),
                  (i["sma20"] is not None and c["latest_price"] > i["sma20"], "sma20"),
                  (i["volume_ratio_20"] is not None and i["volume_ratio_20"] >= 1, "volume_ratio_20")]
    elif view == "near_high":
        checks = [(len(f["candles"]["daily"]) >= 252, "daily_history"), (i["sma5"] is not None and c["latest_price"] > i["sma5"], "sma5"),
                  (i["sma20"] is not None and c["latest_price"] > i["sma20"], "sma20"), (i["high_52w"] is not None and c["latest_price"] >= i["high_52w"] * .97, "high_52w"),
                  (c["change_pct"] is not None and c["change_pct"] >= 0, "change_pct")]
    else:
        checks = [(len(f["candles"]["daily"]) >= 60, "daily_history"), (i["sma20"] is not None and c["latest_price"] > i["sma20"], "sma20"),
                  (i["sma50"] is not None and c["latest_price"] >= i["sma50"], "sma50"), (c["change_pct"] is not None and c["change_pct"] >= -1.5, "change_pct"),
                  (i["high_20"] is not None and c["latest_price"] >= i["high_20"] * .92, "high_20")]
    return (True, None) if all(ok for ok, _ in checks) else (False, next(reason for ok, reason in checks if not ok))


def _freshness(model_freshness, identities, rows_by_symbol, intraday_by_symbol, now):
    """Expose source coverage independently; partial coverage stays partial."""
    source = dict(model_freshness or {})
    daily_missing, intraday_missing, reasons = [], [], {}
    for identity in identities:
        symbol = identity["symbol"]
        daily = rows_by_symbol.get(symbol, [])
        intra = intraday_by_symbol.get(symbol, [])
        if not daily:
            daily_missing.append(symbol)
            reasons.setdefault(symbol, []).append("daily_baseline_missing")
        if not intra:
            intraday_missing.append(symbol)
            reasons.setdefault(symbol, []).append("intraday_missing")
    daily_status = "partial" if daily_missing else (source.get("daily_status") or "fresh")
    intraday_status = "partial" if intraday_missing else (source.get("intraday_status") or "fresh")
    missing = sorted(set(daily_missing + intraday_missing))
    overall = "fresh"
    if missing:
        overall = "partial"
    elif source.get("status") in {"stale", "unknown"}:
        overall = source["status"]
    return {**source, "status": overall, "overall": {"status": overall},
            "daily": {"status": daily_status, "missing_symbols": sorted(daily_missing)},
            "intraday": {"status": intraday_status, "missing_symbols": sorted(intraday_missing)},
            "missing_symbols": {"symbols": missing, "daily": sorted(daily_missing),
                                 "intraday": sorted(intraday_missing), "reasons": reasons}}


def _canonical_can_buy(item):
    """Derive identity from the validated published universe membership.

    ``marginable_long`` is a serving-universe fact, not an inferred stock
    signal.  An explicit future per-item value is accepted only when it
    agrees with that canonical membership.
    """
    if "can_buy" in item:
        if type(item["can_buy"]) is not bool or item["can_buy"] is not True:
            raise ValueError("explicit item can_buy disagrees with marginable_long")
    return True


def build_response(model, rows_by_symbol, intraday_by_symbol, *, now=None):
    if not isinstance(model, dict) or model.get("universe") != _CANONICAL_UNIVERSE:
        raise ValueError("team facts requires the canonical marginable_long universe")
    if not isinstance(model.get("items"), list):
        raise ValueError("team facts model items are incomplete")
    identities = []
    seen = set()
    for item in model.get("items", []):
        if not isinstance(item, dict):
            raise ValueError("team facts model item is malformed")
        can_buy = _canonical_can_buy(item)
        symbol = str(item.get("symbol", "")).upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        identities.append({"symbol": symbol, "market": "TH", "instrument_type": "ORD",
                           "can_buy": can_buy,
                           "universe": _CANONICAL_UNIVERSE})
    views = {}
    for view in ("momentum", "near_high", "pullback"):
        items, reasons = [], {}
        for identity in sorted(identities, key=lambda x: x["symbol"]):
            f = _facts(identity, rows_by_symbol.get(identity["symbol"], []), intraday_by_symbol.get(identity["symbol"], []), now=now)
            ok, reason = _eligible(f, view, now=now)
            if ok: items.append(_compact_fact(f))
            else: reasons[reason] = reasons.get(reason, 0) + 1
        views[view] = {"items": items, "count": len(items), "excluded_count": sum(reasons.values()), "exclusion_reasons": reasons}
    as_of = _latest_completed(intraday_by_symbol, now)
    if as_of is None:
        daily_stamps = [_stamp(max(rows, key=lambda row: _stamp(row[0]) or "")[0])
                        for rows in rows_by_symbol.values() if rows]
        as_of = max(daily_stamps) if daily_stamps else None
    freshness = _freshness(model.get("freshness"), identities, rows_by_symbol, intraday_by_symbol, now)
    return {"api_version": API_VERSION, "contract": "team-facts-list-v1",
            "consumer": "team_facts", "timezone": TIMEZONE,
            "contract_note": "Facts and deterministic indicators for independent review; not trading truth or orders.",
            "views": views, "run": {"source": "price_data+intraday_price_data", "universe": "marginable_long",
            "eligible_count": model.get("eligible_count"), "base_active_ord_count": model.get("base_active_ord_count"),
            "excluded_count": model.get("excluded_count"), "source_version": model.get("source_version"),
            "published_at": model.get("published_at"), "as_of": as_of,
            "freshness": freshness, "coverage": {"symbols_requested": len(identities),
            "views": {name: value["count"] for name, value in views.items()}}, "status": "read_only",
            "capabilities": {"volume_ratio_basis": VOLUME_RATIO_BASIS,
                             "history_limits": {"1D": MAX_DAILY, "60m": MAX_INTRADAY},
                             "detail_route": "/api/team/setup-candidates/{symbol}/history"}}}


def _compact_fact(fact):
    """Keep list responses bounded while retaining the latest intraday fact."""
    compact = dict(fact)
    candles = fact.get("candles") or {}
    compact["candles"] = {}
    if candles.get("completed_60m"):
        compact["candles"]["latest_completed_60m"] = candles["completed_60m"][-1]
    return compact


def build_history_response(model, symbol, daily, intraday, *, timeframe, limit, now=None):
    """Build one-symbol facts plus only the requested, bounded history."""
    canonical = next((item for item in model.get("items", [])
                      if str(item.get("symbol", "")).upper() == symbol.upper()), None)
    if canonical is None:
        return None
    identity = {"symbol": symbol.upper(), "market": "TH", "instrument_type": "ORD",
                "can_buy": _canonical_can_buy(canonical), "universe": _CANONICAL_UNIVERSE}
    fact = _facts(identity, daily, intraday, now=now)
    candles = {"daily": fact["candles"]["daily"][-limit:]} if timeframe == "1D" else {
        "completed_60m": fact["candles"]["completed_60m"][-limit:]
    }
    fact = {**fact, "candles": candles}
    as_of = _latest_completed({symbol.upper(): intraday}, now)
    if as_of is None and daily:
        as_of = _stamp(sorted(daily, key=lambda row: _stamp(row[0]) or "")[-1][0])
    freshness = _freshness(model.get("freshness"), [identity], {symbol.upper(): daily},
                           {symbol.upper(): intraday}, now)
    return {"api_version": API_VERSION, "contract": "team-facts-history-v1",
            "contract_note": "Facts and deterministic indicators for independent review; not trading truth or orders.",
            "symbol": symbol.upper(), "timeframe": timeframe, "limit": limit,
            "history": {"source": "price_data" if timeframe == "1D" else "intraday_price_data",
                        "timeframe": timeframe,
                        "completed_60m_filter": "timestamp <= current completed hourly boundary" if timeframe == "60m" else None},
            "facts": {key: value for key, value in fact.items() if key != "candles"},
            "candles": candles, "run": {"universe": _CANONICAL_UNIVERSE,
            "eligible_count": model.get("eligible_count"), "base_active_ord_count": model.get("base_active_ord_count"),
            "excluded_count": model.get("excluded_count"), "published_at": model.get("published_at"),
            "as_of": as_of, "freshness": freshness,
            "status": "read_only"},
            "capabilities": {"volume_ratio_basis": VOLUME_RATIO_BASIS,
                             "history_limits": {"1D": MAX_DAILY, "60m": MAX_INTRADAY}}}
