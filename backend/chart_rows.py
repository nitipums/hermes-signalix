"""Read-only chart row retrieval shared by the JSON chart endpoints."""

from __future__ import annotations

import datetime as dt


def fetch_chart_rows(cur, symbol, timeframe, limit, market="TH"):
    """Return stored bars, rolling the latest current-session 60m data into Day/Week/Month."""
    rows, _label, _metadata = fetch_chart_rows_with_metadata(
        cur, symbol, timeframe, limit, market=market
    )
    return rows, _label


def fetch_chart_rows_with_metadata(cur, symbol, timeframe, limit, market="TH"):
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

    daily_limit = limit if timeframe == "1D" else min(limit * (25 if timeframe == "1M" else 5), 1500)
    cur.execute("""SELECT date::timestamp, open, high, low, close, volume, false AS provisional
                   FROM price_data WHERE market=%s AND symbol=%s ORDER BY date DESC LIMIT %s""",
                (market.upper(), symbol, daily_limit))
    daily = cur.fetchall()
    # Keep the adapter tolerant of older tuple-shaped test/read-model cursors.
    daily = [row if len(row) > 6 else (*row, False) for row in daily]
    latest_confirmed_time = daily[0][0] if daily else None
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
        daily.append(provisional)

    has_provisional = bool(intra)
    metadata = {}
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
    for stamp, open_, high, low, close, volume, provisional in reversed(daily):
        day = stamp if isinstance(stamp, dt.date) and not isinstance(stamp, dt.datetime) else stamp.date()
        key = day - dt.timedelta(days=day.weekday()) if timeframe == "1W" else day.replace(day=1)
        if key not in periods:
            periods[key] = [dt.datetime.combine(key, dt.time()), open_, high, low, close,
                            float(volume or 0), bool(provisional)]
        else:
            period = periods[key]
            period[2] = max(period[2], high)
            period[3] = min(period[3], low)
            period[4] = close
            period[5] += float(volume or 0)
            period[6] = period[6] or bool(provisional)
    rows = list(reversed(sorted(periods.values(), key=lambda r: r[0])))[:limit]
    label = (("Weekly" if timeframe == "1W" else "Monthly") +
             (" + provisional current session (60m as-is)" if has_provisional
              else " Daily EOD (no current-session 60m data)"))
    if has_provisional and isinstance(intra[-1][0], dt.datetime) and intra[-1][0].tzinfo is not None:
        metadata["latest_intraday_time"] = intra[-1][0]
    return rows, label, metadata
