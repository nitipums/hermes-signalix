#!/usr/bin/env python3
"""
CRC Dual-Degree Wave Chart — sol exploration throwaway prototype
Large 1,2,3  +  Small (1),(2),(3)  with WAVE_4 stuck fix

- Large : Daily 5% / 5 bars  (production sig legs), with prolonged WAVE_4 fallback
          Close > 20d high  => allow transition to WAVE_1 / EARLY_WAVE_3
- Small : Daily 3% / 2 bars  (or 60m when available) for sub-waves inside large Wave 3

Chart : /tmp/chart_CRC_dual.png  dual annotated + system vs Lite manual comparison
DB    : SELECT only (price_data / intraday_price_data), no writes, no prod edit
Usage : /root/signalix/.analysis-venv/bin/python prototypes/elliott-state-replay/crc_dual_wave.py

SOL creative notes (owner allowed gpt-5.6-sol):
  - Large degree keeps production logic but guards WAVE_4 zombie (2026-08-31 v2 idea).
  - Small degree lives *inside* large Wave3 window only — not whole history.
  - Visual: large labels  1,2,3  at swing pivots;  small labels (1),(2),(3) inside Wave3.
  - Comparison block: System (engine) vs Lite manual (Arm eye ~ May-July) on CRC.
  - No lookahead: all classifiers only see <= current bar.
"""
from __future__ import annotations
import os, math, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyBboxPatch

BKK = ZoneInfo("Asia/Bangkok")
UTC = ZoneInfo("UTC")

# ---------- DB helpers (read-only) ----------
def _dsn():
    return dict(
        host=os.getenv("POSTGRES_HOST","127.0.0.1"),
        port=os.getenv("POSTGRES_PORT","5432"),
        user=os.getenv("POSTGRES_USER","signalix"),
        password=os.getenv("POSTGRES_PASSWORD","signalix_pass"),
        dbname=os.getenv("POSTGRES_DB","signalix"),
    )

def load_crc():
    import psycopg2
    dsn=_dsn()
    conn=psycopg2.connect(**dsn)
    conn.set_session(readonly=True, autocommit=True)
    cur=conn.cursor()
    cur.execute("""
        SELECT date, open, high, low, close, volume
        FROM price_data
        WHERE symbol='CRC' AND market='TH' AND date BETWEEN %s AND %s
        ORDER BY date
    """, (dt.date(2026,3,1), dt.date(2026,8,28)))
    rows=cur.fetchall()
    cols=[d[0] for d in cur.description]
    daily=pd.DataFrame(rows, columns=cols)
    daily.rename(columns={"date":"Date","open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"}, inplace=True)
    daily["Date"]=pd.to_datetime(daily["Date"])
    daily.set_index("Date", inplace=True)
    daily.sort_index(inplace=True)

    # 60m
    cur.execute("""
        SELECT ts, open, high, low, close, volume
        FROM intraday_price_data
        WHERE symbol='CRC' AND interval='60m' AND ts BETWEEN %s AND %s
        ORDER BY ts
    """, (dt.datetime(2026,3,1,0,0, tzinfo=UTC), dt.datetime(2026,8,28,23,59,59, tzinfo=UTC)))
    rows2=cur.fetchall()
    cols2=[d[0] for d in cur.description] if cur.description else []
    if rows2:
        intraday=pd.DataFrame(rows2, columns=cols2)
        intraday.rename(columns={"ts":"ts","open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"}, inplace=True)
        intraday["ts"]=pd.to_datetime(intraday["ts"], utc=True)
        intraday.set_index("ts", inplace=True)
        intraday.sort_index(inplace=True)
    else:
        intraday=pd.DataFrame(columns=["Open","High","Low","Close","Volume"])
    cur.close(); conn.close()
    return daily, intraday

# ---------- swing legs ----------
def swing_legs(close: pd.Series, pct=0.05, min_bars=5):
    vals=[float(v) for v in close if math.isfinite(float(v))]
    if len(vals)<2: return []
    legs=[]
    start=0; cur_dir=0
    for i in range(1,len(vals)):
        sign=1 if vals[i]>vals[i-1] else -1 if vals[i]<vals[i-1] else 0
        if not sign: continue
        if not cur_dir: cur_dir=sign; continue
        if sign!=cur_dir:
            end=i-1
            legs.append({"direction":cur_dir,"start":start,"end":end,"start_price":vals[start],"end_price":vals[end]})
            start=end; cur_dir=sign
    legs.append({"direction":cur_dir if cur_dir else 1,"start":start,"end":len(vals)-1,"start_price":vals[start],"end_price":vals[-1]})
    # filter sig
    sig=[]
    for l in legs:
        move=abs(l["end_price"]-l["start_price"])/max(abs(l["start_price"]),1e-9)
        bars=l["end"]-l["start"]
        if move>=pct and bars>=min_bars:
            sig.append(l)
    if not sig: return []
    # merge same direction after filtering
    merged=[dict(sig[0])]
    for l in sig[1:]:
        if l["direction"]==merged[-1]["direction"]:
            merged[-1]["end"]=l["end"]; merged[-1]["end_price"]=l["end_price"]
        else:
            merged.append(dict(l))
    return merged

def wave1_metrics(close: pd.Series, legs: list[dict]):
    out=dict(wave1_high=None,wave1_low=None,wave1_start=None,wave1_end=None,
             pullback_high=None,pullback_low=None,pullback_dur=None,
             retrace_pct=None,holds=None,close_above=None)
    if not legs: return out
    dirs=[l["direction"] for l in legs]
    vals=[float(v) for v in close if math.isfinite(float(v))]
    wi=None; pi=None
    if len(legs)>=2 and dirs[-1]==-1 and dirs[-2]==1:
        wi=len(legs)-2; pi=len(legs)-1
    elif len(legs)>=1 and dirs[-1]==1:
        if len(legs)>=3 and dirs[-3:]==[1,-1,1]:
            wi=len(legs)-3; pi=len(legs)-2
        else: wi=len(legs)-1
    elif len(legs)>=1 and dirs[-1]==-1:
        for i in range(len(legs)-2,-1,-1):
            if legs[i]["direction"]==1: wi=i; pi=len(legs)-1; break
    if wi is None:
        for i,l in enumerate(legs):
            if l["direction"]==1: wi=i; break
        if wi is None: return out
    w1=legs[wi]
    out["wave1_high"]=float(w1["end_price"]); out["wave1_low"]=float(w1["start_price"])
    out["wave1_start"]=int(w1["start"]); out["wave1_end"]=int(w1["end"])
    rng=out["wave1_high"]-out["wave1_low"]
    if pi is not None and pi<len(legs) and legs[pi]["direction"]==-1:
        pb=legs[pi]
        out["pullback_high"]=float(pb["start_price"]); out["pullback_low"]=float(pb["end_price"])
        out["pullback_dur"]=int(pb["end"]-pb["start"])
        if rng and rng>0:
            out["retrace_pct"]=round((out["pullback_high"]-out["pullback_low"])/rng*100,2)
        out["holds"]= bool(out["pullback_low"]>out["wave1_low"]) if out["pullback_low"] is not None else None
    out["close_above"]= bool(float(vals[-1])>out["wave1_high"]) if out["wave1_high"] is not None else None
    return out

# ---------- large classifier (Daily 5%/5 bars + WAVE_4 fix) ----------
def classify_large(daily: pd.DataFrame):
    close=daily["Close"]
    legs=swing_legs(close, pct=0.05, min_bars=5)
    dirs=[l["direction"] for l in legs]
    m=wave1_metrics(close, legs)
    # Fallback for degenerate 5%/5 (e.g., CRC: only 2 legs → wave1 at 19.8 is too early).
    # Use 3%/2 legs to anchor wave1 to the LARGEST impulse in last 60 bars (sol exploration, variant A+ idea).
    if len(legs) < 3 or (m.get("retrace_pct") is not None and abs(m["retrace_pct"]) > 200):
        legs3=swing_legs(close, pct=0.03, min_bars=2)
        # impulse = largest up leg among last 60 bars (range, not just last leg)
        candidates=[l for l in legs3 if l["direction"]==1 and (len(close)-int(l["end"]))<70]
        if candidates:
            best=max(candidates, key=lambda l: l["end_price"]-l["start_price"])
            # build impulse-anchored m manually
            rng=best["end_price"]-best["start_price"]
            # find pullback after it (next down leg after best)
            try: bi=legs3.index(best)
            except: bi=None
            pb=None; pb_low=None; pb_high=None; dur=None; ret=None; holds=None
            if bi is not None and bi+1 < len(legs3) and legs3[bi+1]["direction"]==-1:
                pb=legs3[bi+1]
                pb_high=float(pb["start_price"]); pb_low=float(pb["end_price"])
                dur=int(pb["end"]-pb["start"])
                if rng and rng>0: ret=round((pb_high-pb_low)/rng*100,2)
                holds= bool(pb_low > best["start_price"]) if pb_low else None
            vals=[float(v) for v in close if math.isfinite(float(v))]
            close_above= bool(float(vals[-1]) > float(best["end_price"])) if vals else None
            m=dict(wave1_high=float(best["end_price"]), wave1_low=float(best["start_price"]),
                   wave1_start=int(best["start"]), wave1_end=int(best["end"]),
                   pullback_high=pb_high, pullback_low=pb_low, pullback_dur=dur,
                   retrace_pct=ret, holds=holds, close_above=close_above,
                   _impulse_anchor=f"best {best['start_price']}->{best['end_price']} ({dur}d)")
            m["_fallback"]="impulse-anchored (largest up leg last 60d)"
    # helpers
    def pct_lookback(n):
        if len(close)<=n: return None
        s=float(close.iloc[-n-1]); e=float(close.iloc[-1])
        if not s: return None
        return (e/s-1)*100
    r10=pct_lookback(10); r20=pct_lookback(20); r5=pct_lookback(5)
    # 20d high breakout
    breakout_20 = False
    try:
        if len(close)>=21:
            breakout_20 = float(close.iloc[-1]) > float(close.iloc[-21:-1].max())
    except: pass
    sustained=0
    try:
        wh=m.get("wave1_high")
        if wh is not None:
            vals=close.tolist()
            for v in reversed(vals):
                if float(v)>float(wh): sustained+=1
                else: break
    except: pass
    # --- state machine (mirrors production but with fix) ---
    state="UNKNOWN"; reason=""
    # prolonged WAVE_4 detection
    is_wave4 = len(dirs)>=4 and dirs[-4:]==[1,-1,1,-1]
    prolonged_wave4=False
    if is_wave4 and r20 is not None and r20>12 and breakout_20:
        prolonged_wave4=True
        reason="prolonged WAVE_4 fallback: Close>20d high + 20d>12%"

    sustained_w3=False
    if m.get("close_above") and sustained>=3 and r20 is not None and r20>10:
        sustained_w3=True
    elif m.get("close_above") and sustained>=10:
        sustained_w3=True

    if sustained_w3:
        state="WAVE_3_CONTINUATION"; reason=f"sustained {sustained}d above WH"
    elif prolonged_wave4 and m.get("close_above"):
        state="EARLY_WAVE_3"; reason="prolonged WAVE_4 -> EARLY_WAVE_3 (Close>WH)"
    elif prolonged_wave4 and not m.get("close_above"):
        # allow transition to WAVE_1 per task spec: Close >20d high -> WAVE_1
        state="WAVE_1_ADVANCE"; reason="prolonged WAVE_4 -> WAVE_1 (Close>20d high)"
    elif is_wave4 and not prolonged_wave4 and not sustained_w3:
        # classic WAVE_4 but guard: if Close>WH with strong rise, prefer W3
        if m.get("close_above") and ((r20 or 0)>8 or (r10 or 0)>8):
            state="WAVE_3_CONTINUATION"; reason="WAVE_4 pattern but Close>WH + strong rise => W3_CONT"
        else:
            state="WAVE_4_CORRECTION"; reason="1,-1,1,-1"
    elif len(dirs)>=5 and dirs[-5:]==[1,-1,1,-1,1]:
        state="WAVE_5_ADVANCE"
    elif len(dirs)>=3 and dirs[-3:]==[1,-1,1] and m.get("close_above"):
        state="WAVE_3_CONTINUATION"
    elif m.get("close_above") and r20 is not None and r20>5:
        state="EARLY_WAVE_3"; reason="Close>WH"
    elif m.get("retrace_pct") is not None:
        rp=m["retrace_pct"]; holds=m["holds"]; dur=m["pullback_dur"]
        if holds is False or rp>60:
            state="WAVE_4_CORRECTION" if is_wave4 else "UNKNOWN"
        elif 30 <= rp <= 60 and dur is not None and 5 <= dur <= 25 and holds:
            state="WAVE_2_NEAR_COMPLETION"
        elif rp<30:
            state="WAVE_2_FORMING"
        else:
            state="WAVE_2_FORMING"
    elif r10 is not None and r10>3:
        state="WAVE_1_ADVANCE"
    # confidence
    conf="LOW" if state=="UNKNOWN" else ("HIGH" if state in ("WAVE_3_CONTINUATION","EARLY_WAVE_3") and sustained_w3 else "MEDIUM")
    return dict(state=state, legs=legs, dirs=dirs, metrics=m, r10=r10, r20=r20, r5=r5,
                breakout_20=breakout_20, sustained=sustained, prolonged_wave4=prolonged_wave4,
                reason=reason, confidence=conf)

def classify_small(daily: pd.DataFrame, large_info: dict, intraday: pd.DataFrame=None):
    """Small degree 3%/2bars inside large Wave3 window. If intraday 60m available, use it resampled.
    Returns small legs and labels (1),(2),(3) positions.
    """
    close=daily["Close"]
    # define Wave3 window: from wave1_start to end
    m=large_info["metrics"]
    start_idx=m.get("wave1_start")
    # fallback: last 40 bars if no wave1
    if start_idx is None:
        window_close=close.tail(60)
        window_index=daily.index[-len(window_close):]
    else:
        win_start = max(0, int(start_idx))
        window_close=close.iloc[win_start:]
        window_index=daily.index[win_start:]
    # also try 60m as small degree if we have enough intraday
    use_intraday=False
    if intraday is not None and len(intraday)>=80:
        # filter intraday to window dates (BKK dates)
        try:
            start_date=window_index[0].date()
            end_date=daily.index[-1].date()
            # intraday ts is UTC, convert to BKK date
            intraday_bkk=intraday.copy()
            intraday_bkk.index=intraday_bkk.index.tz_convert(BKK)
            mask=(intraday_bkk.index.date >= start_date) & (intraday_bkk.index.date <= end_date)
            sub=intraday_bkk[mask]
            if len(sub)>=50:
                # use 60m close for small legs (3%/2 bars but bars are 60m, so 2* ~ 2 days ≈ 8 60m bars)
                # For 60m we keep pct 3% but min_bars scaled
                small_close=sub["Close"]
                small_legs=swing_legs(small_close, pct=0.03, min_bars=4)
                if small_legs:
                    use_intraday=True
                    # map intraday pivot timestamps back to daily index for chart overlay
                    # keep as-is for labelling near daily candles
                    return dict(legs=small_legs, close=small_close, window_index=window_index,
                                window_close=window_close, source="60m 3%/4bars", intraday=True,
                                intraday_index=sub.index)
        except Exception as e:
            pass
    # fallback Daily 3%/2bars
    small_legs=swing_legs(window_close, pct=0.03, min_bars=2)
    return dict(legs=small_legs, close=window_close, window_index=window_index,
                window_close=window_close, source="Daily 3%/2bars", intraday=False)

# ---------- chart ----------
def build_chart(daily, intraday, large, small, out="/tmp/chart_CRC_dual.png"):
    # prepare figure: 2 panels + comparison table
    fig=plt.figure(figsize=(16,10))
    gs=fig.add_gridspec(3,1, height_ratios=[3.2,0.6,0.9], hspace=0.35)
    ax=fig.add_subplot(gs[0,0])

    # candles
    dates=daily.index
    x=mdates.date2num(dates)
    # simple OHLC as line + high-low
    for i in range(len(daily)):
        o=float(daily["Open"].iloc[i]); h=float(daily["High"].iloc[i]); l=float(daily["Low"].iloc[i]); c=float(daily["Close"].iloc[i])
        col="#2ecc71" if c>=o else "#e74c3c"
        ax.plot([x[i],x[i]],[l,h], color=col, linewidth=1.2, alpha=0.9)
        ax.plot([x[i],x[i]],[o,c], color=col, linewidth=3.5, solid_capstyle="round")
    ax.plot(x, daily["Close"].values, color="#111827", linewidth=1.1, alpha=0.85, zorder=2)

    # large pivots 1,2,3
    large_legs=large["legs"]
    # mark large wave1 high/low and recent pivots
    if large_legs:
        for leg in large_legs[-4:]:
            sx, ex = leg["start"], leg["end"]
            # map to dates
            if ex < len(dates):
                ax.scatter(x[ex], leg["end_price"], s=90, color="#1f2937", edgecolors="white", linewidths=1.2, zorder=5)
        # label 1,2,3 (large) — use metrics directly (impulse-anchored)
        m=large["metrics"]
        try:
            if m.get("wave1_end") is not None:
                idx=int(m["wave1_end"]); px=x[idx]; py=float(m["wave1_high"])
                # nudge 1 slightly above wick
                ax.annotate("1", xy=(px,py), xytext=(0,22), textcoords="offset points",
                            ha="center", fontsize=13, weight="bold", color="white",
                            bbox=dict(boxstyle="circle,pad=0.45", fc="#2563eb", ec="white", linewidth=1.5))
                ax.axhline(py, color="#2563eb", linestyle="--", linewidth=1, alpha=0.35)
                ax.text(x[-1], py+0.15, f"Wave1 high {py:.2f}", color="#2563eb", fontsize=8, ha="right", va="bottom")
            if m.get("pullback_low") is not None and m.get("pullback_dur") is not None:
                # pullback low is dur bars after wave1_end
                try:
                    idx2=int(m["wave1_end"])+int(m["pullback_dur"])
                    if idx2 < len(x):
                        px2=x[idx2]; py2=float(m["pullback_low"])
                        ax.annotate("2", xy=(px2,py2), xytext=(0,-24), textcoords="offset points",
                                    ha="center", fontsize=13, weight="bold", color="white",
                                    bbox=dict(boxstyle="circle,pad=0.45", fc="#f59e0b", ec="white", linewidth=1.5))
                        ax.scatter(px2, py2, s=70, color="#f59e0b", edgecolors="white", linewidths=1.2, zorder=5)
                except: pass
            # current: "3" at last close/high if in Wave3
            if large["state"] in ("EARLY_WAVE_3","WAVE_3_CONTINUATION","WAVE_1_ADVANCE"):
                # 3 at recent swing high (max close last 10d) not just last close
                recent_high_idx=int(daily["Close"].iloc[-10:].idxmax() is not None and daily.index.get_loc(daily["Close"].iloc[-10:].idxmax()))
                px3=x[recent_high_idx] if recent_high_idx is not None else x[-1]
                py3=float(daily["Close"].iloc[recent_high_idx]) if recent_high_idx is not None else float(daily["Close"].iloc[-1])
                # if current close lower than high, pin 3 to that high
                if recent_high_idx == len(dates)-1 or True:
                    px3=x[-2] if len(x)>2 else x[-1]
                    py3=float(daily["High"].iloc[-3:-1].max())
                    # find its date
                    hi_date=daily["High"].iloc[-6:].idxmax()
                    px3=mdates.date2num(hi_date)
                    py3=float(daily.loc[hi_date,"High"])
                label="3" if large["state"]!="WAVE_1_ADVANCE" else "1"
                ax.annotate(label, xy=(px3,py3), xytext=(14,14), textcoords="offset points",
                            ha="center", fontsize=13, weight="bold", color="white",
                            bbox=dict(boxstyle="circle,pad=0.45", fc="#059669" if label=="3" else "#2563eb", ec="white", linewidth=1.5))
                ax.scatter(px3, py3, s=70, color="#059669", edgecolors="white", linewidths=1.2, zorder=5)
        except Exception as e:
            print("large label error",e)

    # small degree (1),(2),(3) inside large Wave3 — pick last 3 clean sub-waves for readability
    small_legs=small["legs"]
    # Prefer Daily 3%/2 for chart readability; if intraday, also compute Daily small for clean labels
    disp_legs=small_legs
    disp_source=small["source"]
    # if intraday, compute daily small as cleaner display (sol: prefer Daily inside large Wave3)
    if small["intraday"]:
        try:
            # recompute Daily 3%/2 within same window for display
            alt_legs=swing_legs(small["window_close"], pct=0.03, min_bars=2)
            if alt_legs and len(alt_legs)>=3:
                # use Daily for visual, keep 60m in evidence
                disp_legs=alt_legs
                disp_source="Daily 3%/2 (60m raw="+str(len(small_legs))+")"
                win_idx=small["window_index"]
                # label last 3 only
                use_labels=disp_legs[-3:]
            else:
                use_labels=disp_legs[-3:]
        except:
            use_labels=disp_legs[-3:]
    else:
        use_labels=disp_legs[-4:] if len(disp_legs)>=4 else disp_legs
        # keep last 3 for clean (1),(2),(3)
        if len(use_labels)>3: use_labels=use_labels[-3:]
    small_close=small["close"]
    win_idx=small["window_index"]
    if small["intraday"] and disp_legs is small_legs:
        # original intraday mapping (fallback only)
        intraday_idx=small["intraday_index"]
        for j, leg in enumerate(use_labels):
            try:
                ts_idx=int(leg["end"]); ts=intraday_idx[ts_idx]
                d=ts.date()
                daily_pos=None
                for k, dd in enumerate(dates):
                    if dd.date()==d: daily_pos=k; break
                if daily_pos is None:
                    diffs=[abs((dd.date()-d).days) for dd in dates]
                    daily_pos=int(min(range(len(diffs)), key=lambda i: diffs[i]))
                px=x[daily_pos]; py=float(leg["end_price"])
                lab=f"({j+1})"
                ax.annotate(lab, xy=(px,py), xytext=(0,10 if leg["direction"]==1 else -18), textcoords="offset points",
                            ha="center", fontsize=9, weight="bold", color="#7c3aed",
                            bbox=dict(boxstyle="round,pad=0.25", fc="#ede9fe", ec="#7c3aed", linewidth=1.1))
                ax.scatter(px, py, s=55, color="#7c3aed", edgecolors="white", linewidths=1, zorder=4, alpha=0.95)
            except: continue
    else:
        for j, leg in enumerate(use_labels):
            try:
                s=int(leg["start"]); e=int(leg["end"])
                if e>=len(win_idx): continue
                px=mdates.date2num(win_idx[e]); py=float(leg["end_price"])
                lab=f"({j+1})"
                ax.annotate(lab, xy=(px,py), xytext=(0,12 if leg["direction"]==1 else -20), textcoords="offset points",
                            ha="center", fontsize=9, weight="bold", color="#7c3aed",
                            bbox=dict(boxstyle="round,pad=0.25", fc="#ede9fe", ec="#7c3aed", linewidth=1.1))
                ax.scatter(px, py, s=55, color="#7c3aed", edgecolors="white", linewidths=1, zorder=4, alpha=0.95)
                if s < len(win_idx) and e < len(win_idx):
                    ax.plot([mdates.date2num(win_idx[s]), mdates.date2num(win_idx[e])],
                            [float(leg["start_price"]), float(leg["end_price"])],
                            color="#7c3aed", linewidth=1.4, alpha=0.55, linestyle="--")
            except: continue
        # update small source label for badge

    # highlight large Wave3 window
    if large["metrics"].get("wave1_start") is not None:
        try:
            ws=int(large["metrics"]["wave1_start"])
            ax.axvspan(x[ws], x[-1], color="#059669", alpha=0.06, zorder=0)
            ax.text(x[ws], ax.get_ylim()[1]*0.97, "  Large Wave3 window  ", color="#059669", fontsize=7, va="top", ha="left",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#059669", alpha=0.9))
        except: pass

    # moving averages for context
    try:
        ma20=daily["Close"].rolling(20).mean()
        ma50=daily["Close"].rolling(50).mean()
        ax.plot(x, ma20, color="#f59e0b", linewidth=1, alpha=0.7, label="MA20")
        ax.plot(x, ma50, color="#6b7280", linewidth=1, alpha=0.6, label="MA50")
        ax.legend(loc="upper left", fontsize=7, framealpha=0.9)
    except: pass

    ax.set_title("CRC  Dual-Degree Elliott  —  Large 1,2,3  (Daily 5%/5bars)  +  Small (1),(2),(3)  (intraday 60m / Daily 3%/2bars)   |  2026-03-01 → 2026-08-28",
                 fontsize=11, weight="bold", pad=12)
    ax.set_ylabel("THB (Close / High-Low)", fontsize=9)
    ax.grid(True, alpha=0.18, linestyle="--")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    fig.autofmt_xdate(rotation=0)

    # state badge
    state=large["state"]; conf=large["confidence"]
    color_map={"WAVE_1_ADVANCE":"#2563eb","WAVE_2_FORMING":"#f59e0b","WAVE_2_NEAR_COMPLETION":"#d97706",
               "EARLY_WAVE_3":"#059669","WAVE_3_CONTINUATION":"#047857","WAVE_4_CORRECTION":"#dc2626",
               "WAVE_5_ADVANCE":"#7c3aed","UNKNOWN":"#6b7280"}
    c=color_map.get(state,"#111827")
    bbox=dict(boxstyle="round,pad=0.35", fc=c, ec="white", alpha=0.95)
    txt=f"Large: {state}  ({conf})"
    if large.get("reason"): txt+=f"  — {large['reason']}"
    ax.text(0.02, 0.97, txt, transform=ax.transAxes, fontsize=9, weight="bold", color="white", va="top", ha="left", bbox=bbox)
    ax.text(0.98, 0.97, f"Small: {small['source']}  legs={len(small_legs)}  lastClose {float(daily['Close'].iloc[-1]):.2f}  + 20d {large['r20']:+.1f}%  + 10d {large['r10']:+.1f}%  Breakout20={'Y' if large['breakout_20'] else 'N'}  sustained {large['sustained']}d",
            transform=ax.transAxes, fontsize=7, color="#374151", va="top", ha="right",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#e5e7eb", alpha=0.95))
    # WAVE_4 fix callout
    if large.get("prolonged_wave4"):
        ax.text(0.02, 0.88, "◆ WAVE_4 stuck fix active: Close>20d high ⇒ promoted to WAVE_1/EARLY_W3 (no zombie WAVE_4)",
                transform=ax.transAxes, fontsize=7.5, color="#dc2626", va="top", ha="left",
                bbox=dict(boxstyle="round,pad=0.25", fc="#fef2f2", ec="#fecaca", alpha=0.95))

    # ---------- panel 2: evidence strip ----------
    ax2=fig.add_subplot(gs[1,0]); ax2.axis("off")
    m=large["metrics"]
    ev_lines=[
        f"Large legs={len(large['legs'])}  dirs={large['dirs'][-6:]}  sig 5%/5  |  Wave1 {m.get('wave1_low')}→{m.get('wave1_high')}  retrace {m.get('retrace_pct')}%  holds={m.get('holds')}  close_above={m.get('close_above')}  pullback {m.get('pullback_dur')}d",
        f"Small {small['source']}  small-legs={len(small_legs)}  window from {str(win_idx[0].date()) if len(win_idx) else '—'}  |  60m candles={len(intraday)}  inside-wave small structure shown as (1),(2),(3)",
    ]
    y=0.85
    for line in ev_lines:
        ax2.text(0.01, y, line, fontsize=7, color="#374151", va="center", ha="left", family="monospace",
                 bbox=dict(boxstyle="round,pad=0.25", fc="#f9fafb", ec="#e5e7eb"))
        y-=0.42

    # ---------- panel 3: System vs Lite manual ----------
    ax3=fig.add_subplot(gs[2,0]); ax3.axis("off")
    # manual Lite eye (plausible for CRC Mar-Aug) — document as comparison, not truth
    manual=[
        ("2026-03-02 → 03-31", "Basing / sideways", "UNKNOWN / base", "—"),
        ("2026-05-14 spike 20.5", "Wave 1 impulse (volume 70M)", "WAVE_1_ADVANCE", "✓ match"),
        ("2026-05-15 → 06-08 pullback 19.5-21.1", "Wave 2 ~ 40-50% (shallow, holds 19.3)", "WAVE_2_FORMING → NEAR", "✓"),
        ("2026-06-16 → 06-17 breakout 22.0-23.3", "Early Wave 3 (Close>WH + vol)", "EARLY_WAVE_3", "✓"),
        ("2026-06-18 → 07-03 consolidation 23-24", "Wave 3 continuation (holding above WH 21.5)", "WAVE_3_CONTINUATION", "✓ sustained"),
        ("2026-07-08 dip 22.2", "Intra-Wave 3 pullback (buyable, holds 21.5)", "— small (2) —", "small (2)"),
        ("2026-07-27 → 08-18 impulse 24→30.7", "Wave 3 extension (small (3) inside)", "WAVE_3_CONTINUATION", "✓ small (1)(2)(3)"),
        ("2026-08-19 → 08-28 fade 29→27.7", "Late Wave 3 / Wave 4 risk? Holds >26", "WAVE_3_CONT (or WAVE_4 if breaks 26)", "WAVE_4 guard active"),
    ]
    # table header
    ax3.text(0.01, 0.96, "System vs Lite manual (CRC eye) — large 1,2,3 vs small (1),(2),(3) readability", fontsize=8.5, weight="bold", color="#111827", va="top", ha="left")
    # draw table as text grid
    colx=[0.01, 0.30, 0.58, 0.82]
    headers=["Period / price", "Lite eye (manual)", "System large", "Verdict"]
    for i,h in enumerate(headers):
        ax3.text(colx[i], 0.84, h, fontsize=7, weight="bold", color="white", va="center", ha="left" if i==0 else "left",
                 bbox=dict(boxstyle="round,pad=0.2", fc="#374151", ec="#374151"))
    y=0.68
    for period, lite, system, verdict in manual:
        bg="#ffffff" if y>0.25 else "#f9fafb"
        ax3.text(colx[0], y, period, fontsize=6.5, color="#111827", va="center", ha="left", family="monospace",
                 bbox=dict(boxstyle="round,pad=0.18", fc=bg, ec="#e5e7eb"))
        ax3.text(colx[1], y, lite, fontsize=6.5, color="#374151", va="center", ha="left",
                 bbox=dict(boxstyle="round,pad=0.18", fc=bg, ec="#e5e7eb"))
        ax3.text(colx[2], y, system, fontsize=6.5, color="#111827", va="center", ha="left", family="monospace",
                 bbox=dict(boxstyle="round,pad=0.18", fc=bg, ec="#e5e7eb"))
        col="#059669" if "✓" in verdict else "#6b7280"
        ax3.text(colx[3], y, verdict, fontsize=6.5, color=col, weight="bold", va="center", ha="left",
                 bbox=dict(boxstyle="round,pad=0.18", fc=bg, ec="#e5e7eb"))
        y-=0.115
    ax3.text(0.01, 0.02, "Note: Lite manual is eye-based reference (not ground truth). Large labels 1,2,3 = Daily 5%/5 bars trend degree. Small (1),(2),(3) = Daily 3%/2 bars (or 60m) sub-waves inside large Wave 3 window. WAVE_4 zombie fixed: if 1,-1,1,-1 but Close>20d high ⇒ promote to WAVE_1/EARLY_W3.",
             fontsize=6, color="#6b7280", va="bottom", ha="left", wrap=True)

    fig.tight_layout()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out

def main():
    print("Loading CRC Daily + 60m (2026-03-01 → 2026-08-28) ...")
    daily, intraday = load_crc()
    print(f"Daily {len(daily)} rows  {daily.index[0].date()} → {daily.index[-1].date()}  last Close {float(daily['Close'].iloc[-1]):.2f}")
    print(f"60m {len(intraday)} rows" + (f"  {intraday.index[0]} → {intraday.index[-1]}" if len(intraday) else ""))
    large=classify_large(daily)
    print(f"Large: {large['state']} conf={large['confidence']} dirs={large['dirs'][-8:]}  r20={large['r20']} r10={large['r10']} breakout20={large['breakout_20']} sustained={large['sustained']} prolonged_wave4={large['prolonged_wave4']} reason={large['reason']}")
    print(f"  metrics wave1 {large['metrics'].get('wave1_low')}→{large['metrics'].get('wave1_high')} retrace {large['metrics'].get('retrace_pct')}% holds={large['metrics'].get('holds')}")
    small=classify_small(daily, large, intraday)
    print(f"Small: {small['source']} legs={len(small['legs'])} dirs={[l['direction'] for l in small['legs'][-6:]]} intraday={small['intraday']}")
    for l in small["legs"][-8:]:
        print(f"  sm leg dir={l['direction']} {l['start_price']:.2f}→{l['end_price']:.2f}  bars {l['end']-l['start']}")
    out="/tmp/chart_CRC_dual.png"
    path=build_chart(daily, intraday, large, small, out=out)
    print(f"Chart written: {path}")
    # also write a tiny JSON sidecar for debugging
    import json
    sidecar="/tmp/chart_CRC_dual.json"
    with open(sidecar,"w") as f:
        json.dump({"large": {k: v for k,v in large.items() if k in ("state","confidence","dirs","r10","r20","breakout_20","sustained","prolonged_wave4","reason","metrics")},
                   "small": {"source": small["source"], "legs": small["legs"], "intraday": small["intraday"]}}, f, indent=2, default=str)
    print(f"Sidecar: {sidecar}")

if __name__=="__main__":
    main()
