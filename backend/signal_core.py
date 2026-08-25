"""Signalix deterministic pure-math core extracted from scanner.py (P2-01)."""

import math
import datetime as dt
import pandas as pd
import numpy as np

# ---- Tunables ----
RS_LOOKBACK = 252          # ~1 trading year for RS vs market
RS_THRESHOLD = 50          # Minervini wants >= 70-80 in a strong bull market; in the
                          # current Thai regime (SET +34% the last year but most
                          # names flat/sideways), the best 7/8-cohort stocks peak
                          # at rank-Rs ~59. 50 keeps the scan useful while still
                          # excluding the bottom half of the universe.
MIN_DAYS = 260             # need enough history for 200d MA + 52w
VCP_PERIOD = 60            # look at last ~3 months for VCP
VCP_MIN_CONTRACTIONS = 2   # at least 2 contraction legs
# Fib retracement levels for buy-zone (Wave-2 pullback methodology)
BUY_FIB_LEVELS = (0.5, 0.618)


def rma(series: pd.Series, n: int) -> pd.Series:
    """Wilder's moving average (for RS smoothing)."""
    return series.ewm(alpha=1 / n, adjust=False).mean()


def compute_rs_rating(stock_close: pd.Series, market_close: pd.Series) -> float:
    """
    RS Rating (0-100) = percentile rank of this stock's 1y return vs market.

    The OLD implementation clamped a linear map (50 + diff/0.5*50), which made
    any stock outperforming the market by >50% saturate at RS=100 — i.e. every
    strong momentum name reported RS=100.0 (see scan_run4.log). That is NOT a
    ranking and is useless for prioritisation.

    New behaviour: returns the percentile rank (0-100) when `market_close` is
    provided as a *series of peer returns*; for the single-symbol helper below
    we instead expose `compute_rs_percentile` which takes a precomputed array of
    relative returns and ranks the stock within it.
    """
    if len(stock_close) < RS_LOOKBACK or len(market_close) < RS_LOOKBACK:
        return 0.0
    s_ret = stock_close.iloc[-1] / stock_close.iloc[-RS_LOOKBACK] - 1
    m_ret = market_close.iloc[-1] / market_close.iloc[-RS_LOOKBACK] - 1
    diff = s_ret - m_ret
    # map diff in [-0.5, +0.5] -> [0, 100] clamped (kept ONLY for the single-
    # symbol path; the universe scan uses rank-based percentile instead).
    rating = 50 + (diff / 0.5) * 50
    return float(max(0.0, min(100.0, rating)))


def compute_rs_percentile(rel_returns: "pd.Series | list[float] | None" = None) -> float:
    """
    Rank-based RS Rating.

    Pass a pandas Series indexed by symbol of relative returns
    (stock_1y_return - market_1y_return) and we return the percentile rank
    (0-100) of the LAST element. For the universe scan this is the authoritative
    RS Rating — it spreads names across the full 0-100 scale instead of
    saturating at 100.
    """
    if rel_returns is None or len(rel_returns) == 0:
        return 0.0
    s = pd.Series(rel_returns) if not isinstance(rel_returns, pd.Series) else rel_returns
    # pandas ranks ascending: strongest relative return has percentile 1.0.
    # Do NOT invert it; inversion assigned RS~0 to the strongest names.
    ranks = s.rank(pct=True) * 100
    return float(ranks.iloc[-1])


def detect_vcp(highs: pd.Series, lows: pd.Series, period: int):  # type hint kept
    """
    Crude VCP detection: look at rolling (high-low)/low volatility over
    successive windows; if it contracts repeatedly, it's a VCP.
    Returns {is_vcp, contractions, latest_contraction_pct}
    """
    sub = pd.concat([highs, lows], axis=1).tail(period)
    if len(sub) < 20:
        return {"is_vcp": False, "contractions": 0, "latest_contraction_pct": 0.0}
    # split into 3 legs
    legs = 3
    size = len(sub) // legs
    contractions = []
    for i in range(legs):
        seg = sub.iloc[i * size:(i + 1) * size]
        if len(seg) == 0:
            continue
        rng = (seg.iloc[:, 0].max() - seg.iloc[:, 1].min()) / seg.iloc[:, 1].min()
        contractions.append(rng * 100)
    # contraction = each leg smaller than previous
    is_vcp = (len(contractions) >= VCP_MIN_CONTRACTIONS and
              all(contractions[i] > contractions[i + 1] for i in range(len(contractions) - 1)))
    latest = contractions[-1] if contractions else 0.0
    return {"is_vcp": bool(is_vcp), "contractions": [round(c, 1) for c in contractions],
            "latest_contraction_pct": round(latest, 1)}


def trend_template(df: pd.DataFrame, rs_rating: float) -> dict:
    """
    Evaluate the 8 Minervini conditions. Returns dict of booleans + extras.
    df must have columns: Open, High, Low, Close and a DatetimeIndex.
    """
    close = _close_series(df)
    res = {}
    if len(close) < MIN_DAYS:
        return {"pass": False, "conditions_met": 0, "reason": "insufficient history",
                "conditions": {}, "ma": {}, "rs_rating": rs_rating}

    ma50 = close.rolling(50).mean().iloc[-1]
    ma150 = close.rolling(150).mean().iloc[-1]
    ma200 = close.rolling(200).mean().iloc[-1]
    ma200_1m_ago = close.rolling(200).mean().iloc[-22] if len(close) >= 222 else ma200

    price = close.iloc[-1]
    hi_52 = close.rolling(252).max().iloc[-1]
    lo_52 = close.rolling(252).min().iloc[-1]

    c1 = price >= ma150
    c2 = ma150 >= ma200
    c3 = ma200 >= ma200_1m_ago
    c4 = ma50 >= ma150
    c5 = price >= ma50
    c6 = price >= lo_52 * 1.25
    c7 = price >= hi_52 * 0.75          # within 25% of 52w high
    c8 = rs_rating >= RS_THRESHOLD

    conds = {"c1_price_above_150ma": bool(c1), "c2_150ma_above_200ma": bool(c2),
             "c3_200ma_uptrend": bool(c3), "c4_50ma_above_150ma": bool(c4),
             "c5_price_above_50ma": bool(c5), "c6_25pct_above_52wlow": bool(c6),
             "c7_within_25pct_52whigh": bool(c7), "c8_rs_above_threshold": bool(c8)}

    met = sum(conds.values())
    return {"pass": met == 8, "conditions_met": int(met), "conditions": conds,
            "ma": {"ma50": round(float(ma50), 2), "ma150": round(float(ma150), 2),
                   "ma200": round(float(ma200), 2), "price": round(float(price), 2),
                   "hi_52": round(float(hi_52), 2), "lo_52": round(float(lo_52), 2)},
            "rs_rating": round(rs_rating, 1)}


def position_sizing(price: float, stop: float, portfolio_value: float = 100000.0,
                    risk_pct: float = 0.01) -> dict:
    """Fixed-% risk position sizing. Risk 1% of portfolio per trade."""
    if price <= 0 or stop >= price:
        return {"shares": 0, "risk_amount": 0.0, "risk_per_share": 0.0, "note": "invalid stop"}
    risk_amount = portfolio_value * risk_pct
    risk_per_share = price - stop
    shares = math.floor(risk_amount / risk_per_share)
    return {"shares": int(shares), "risk_amount": round(risk_amount, 2),
            "risk_per_share": round(risk_per_share, 2),
            "stop_loss": round(stop, 2), "notional": round(shares * price, 2)}


def _close_series(df_or_series):
    """Return a clean Close Series regardless of yfinance MultiIndex wrapping."""
    if isinstance(df_or_series, pd.Series):
        return df_or_series
    df = df_or_series
    if isinstance(df.columns, pd.MultiIndex):
        # (field, ticker) -> take first ticker's Close
        df = df.xs(df.columns.get_level_values(1)[0], axis=1, level=1)
    return df["Close"]


def fibonaccis_from_swing(high: float, low: float) -> dict:
    """
    Standard fib retracements of a swing (Wave-1) measured from high to low.
    Used for buy-zone / pullback monitoring per Arm's methodology.
    """
    rng = high - low
    return {f"{int(p*100)}": round(low + p * rng, 2) for p in (0.236, 0.382, 0.5, 0.618, 0.786)}


def buy_zone(df: pd.DataFrame) -> dict:
    """
    Compute buy-zone / monitor levels for a candidate.

    Methodology (per owner):
    - Wave-1 leg = the recent impulse up from the last significant low into the
      current price. We approximate Wave 1 as the last 22-day swing from a local
      min to the most recent close.
    - Buy zone = fib 0.5 / 0.618 retracement of that leg (pullback entry).
    - Monitor band = the recent swing-low support; a daily close below it (or a
      -7% hard stop, whichever is tighter) is the cut level.

    Returns a dict with: wave1_high, wave1_low, fibs, buy_zone (dict of levels),
    monitor_support, stop (tightest of swing / -7%).
    """
    recent = df["Close"].tail(22)
    if len(recent) < 5:
        return {}
    swing_low = float(recent.min())
    swing_high = float(recent.max())
    # use swing_high as wave1 top unless last close is higher (extend to high)
    high = max(swing_high, float(df["Close"].iloc[-1]))
    low = swing_low
    fibs = fibonaccis_from_swing(high, low)
    buy_levels = {k: v for k, v in fibs.items() if k in ("50", "62")}  # 0.5 / 0.618
    price = float(df["Close"].iloc[-1])
    # hard stop -7% from entry; swing stop = swing low
    hard_stop = price * 0.93
    stop = max(round(hard_stop, 2), round(low, 2))  # tighter (higher) of the two
    return {
        "wave1_high": round(high, 2),
        "wave1_low": round(low, 2),
        "fibs": fibs,
        "buy_zones": buy_levels,
        "monitor_support": round(low, 2),
        "stop_loss": stop,
    }


def rsi(close: pd.Series, period: int = 14) -> float | None:
    """Wilder RSI from EOD closes; returns None until enough bars exist."""
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean().iloc[-1]
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean().iloc[-1]
    if pd.isna(avg_gain) or pd.isna(avg_loss):
        return None
    if avg_loss == 0:
        return 100.0
    return round(float(100 - 100 / (1 + avg_gain / avg_loss)), 1)


def trade_readiness(df: pd.DataFrame, tt: dict, bz: dict) -> dict:
    """Classify an EOD setup using tvcheck's BUY/HOLD/OVERBOUGHT/BREAK logic.

    Signalix stores Thai daily EOD bars, not 15-minute bars. Therefore this is
    deliberately a *daily* RSI proxy: it preserves the decision hierarchy and
    recent-structure Fib logic but never claims intraday confirmation.
    """
    close = _close_series(df)
    price = float(close.iloc[-1])
    recent = df.tail(90)
    # The cut level must precede today's bar; including today's low makes a
    # close below it impossible (daily Low is always <= daily Close).
    prior_structure = df.iloc[-91:-1] if len(df) >= 91 else df.iloc[:-1]
    swing_low = float(prior_structure["Low"].min())
    swing_high = float(recent["High"].max())
    rng = swing_high - swing_low
    fib50 = round(swing_low + rng * 0.5, 2)
    fib618 = round(swing_low + rng * 0.618, 2)
    nearest_label, nearest = min((("50", fib50), ("62", fib618)), key=lambda x: abs(price - x[1]))
    near_buy_zone = price > 0 and abs(price - nearest) / price <= 0.02
    rsi_daily = rsi(close)
    rsi_prev = rsi(close.iloc[:-3]) if len(close) > 17 else None
    rsi_rising = rsi_daily is not None and rsi_prev is not None and rsi_daily > rsi_prev
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
    ma200_prev = close.rolling(200).mean().iloc[-22] if len(close) >= 222 else None
    ma150 = close.rolling(150).mean().iloc[-1] if len(close) >= 150 else None
    ma150_prev = close.rolling(150).mean().iloc[-22] if len(close) >= 172 else None
    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
    ma50_prev = close.rolling(50).mean().iloc[-21] if len(close) >= 70 else None
    above_ma200 = ma200 is not None and price > float(ma200)
    above_ma50 = ma50 is not None and price >= float(ma50)
    ma50_slope_20d = ((float(ma50) / float(ma50_prev) - 1) * 100
                      if ma50 is not None and ma50_prev not in (None, 0) else None)
    # Stage classification (Minervini/Weinstein) needs the 200-day MA slope.
    ma200_slope_20d_pct = ((float(ma200) / float(ma200_prev) - 1) * 100
                           if ma200 is not None and ma200_prev not in (None, 0) else None)
    ma150_slope_20d_pct = ((float(ma150) / float(ma150_prev) - 1) * 100
                           if ma150 is not None and ma150_prev not in (None, 0) else None)
    # MACD proxy (fast MA - slow MA) — layer-2 quality signal, self-contained.
    macd_line = round(float(ma50) - float(ma150), 4) if (ma50 is not None and ma150 is not None) else None
    prior_20_high = float(df["High"].iloc[-21:-1].max()) if len(df) >= 21 else None
    avg_volume_50 = float(df["Volume"].tail(50).mean()) if len(df) >= 50 else None
    volume_ratio_50 = (float(df["Volume"].iloc[-1]) / avg_volume_50
                       if avg_volume_50 and avg_volume_50 > 0 else None)
    breakout_20d = prior_20_high is not None and price >= prior_20_high
    range_20_pct = ((float(df["High"].tail(20).max()) - float(df["Low"].tail(20).min())) / price * 100
                    if len(df) >= 20 and price > 0 else None)
    is_break = price < swing_low
    is_overbought = rsi_daily is not None and rsi_daily >= 78
    buy_setup = (tt.get("conditions_met", 0) >= 8 and near_buy_zone and
                 rsi_daily is not None and 38 <= rsi_daily <= 62 and
                 rsi_rising and above_ma200)
    if is_break:
        status, color = "BREAK", "#f85149"
    elif tt.get("conditions_met", 0) < 8:
        status, color = "WAIT", "#8b949e"
    elif is_overbought:
        status, color = "OVERBOUGHT", "#d29922"
    elif buy_setup:
        status, color = "BUY", "#3fb950"
    else:
        status, color = "HOLD", "#58a6ff"
    targets = {"127": round(swing_high + rng * .272, 2), "161": round(swing_high + rng * .618, 2)}
    stop = max(round(price * .93, 2), round(swing_low, 2))
    return {
        "status": status, "color": color, "timeframe": "daily_eod",
        "rsi_daily": rsi_daily, "rsi_daily_previous": rsi_prev,
        "rsi_rising": bool(rsi_rising), "above_ma200": bool(above_ma200),
        "above_ma50": bool(above_ma50),
        "ma50_slope_20d_pct": round(ma50_slope_20d, 2) if ma50_slope_20d is not None else None,
        "ma200_slope_20d_pct": round(ma200_slope_20d_pct, 2) if ma200_slope_20d_pct is not None else None,
        "ma150_slope_20d_pct": round(ma150_slope_20d_pct, 2) if ma150_slope_20d_pct is not None else None,
        "macd": macd_line,
        "range_20d_pct": round(range_20_pct, 2) if range_20_pct is not None else None,
        "breakout_20d": bool(breakout_20d),
        "breakout_level_20d": round(prior_20_high, 2) if prior_20_high is not None else None,
        "pre_break_pivot_low": round(float(df["Low"].iloc[-6:-1].min()), 2) if len(df) >= 6 else None,
        "volume_ratio_50": round(volume_ratio_50, 2) if volume_ratio_50 is not None else None,
        "near_buy_zone": bool(near_buy_zone), "nearest_fib": nearest_label,
        "nearest_fib_price": nearest, "swing_high_90d": round(swing_high, 2),
        "swing_low_90d": round(swing_low, 2), "buy_zones_90d": {"50": fib50, "62": fib618},
        "cut_level": round(swing_low, 2), "stop_loss": stop, "targets": targets,
    }
