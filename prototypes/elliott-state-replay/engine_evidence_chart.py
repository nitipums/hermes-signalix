#!/usr/bin/env python3
"""THROWAWAY Signalix chart spike: plot only evidence the engine exposes.

This is prototype evidence, not production code or an Elliott-wave truth claim.
Database access is SELECT-only/read-only; outputs are restricted to /tmp.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import elliott_structure_engine as engine  # noqa: E402
import replay_lab  # noqa: E402

DEFAULT_SYMBOLS = "CRC,BGRIM,AWC"
DEFAULT_FROM = "2025-08-28"
DEFAULT_TO = "2026-08-28"
DEFAULT_OUT = "/tmp/signalix-engine-evidence-chart"
EXPECTED_ELIGIBLE = 237

STATE_COLORS = {
    "UNKNOWN": "#94a3b8",
    "WAVE_1_ADVANCE": "#16a34a",
    "WAVE_2_FORMING": "#eab308",
    "WAVE_2_NEAR_COMPLETION": "#f97316",
    "EARLY_WAVE_3": "#dc2626",
    "WAVE_3_CONTINUATION": "#7c3aed",
    "WAVE_4_CORRECTION": "#2563eb",
    "WAVE_5_ADVANCE": "#db2777",
}
STATE_SHORT = {
    "WAVE_1_ADVANCE": "W1",
    "WAVE_2_FORMING": "W2 forming",
    "WAVE_2_NEAR_COMPLETION": "W2 near",
    "EARLY_WAVE_3": "EARLY W3",
    "WAVE_3_CONTINUATION": "W3 cont",
    "WAVE_4_CORRECTION": "W4",
    "WAVE_5_ADVANCE": "W5",
    "UNKNOWN": "UNKNOWN",
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--from", dest="from_date", default=DEFAULT_FROM)
    parser.add_argument("--to", dest="to_date", default=DEFAULT_TO)
    parser.add_argument("--out-dir", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def json_safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if pd.notna(value) else None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def ensure_tmp(path: str) -> Path:
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(Path("/tmp").resolve())
    except ValueError as exc:
        raise ValueError(f"--out-dir must be under /tmp: {resolved}") from exc
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def load_bounded_daily(conn, symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    rows, cols = replay_lab._exec_select(
        conn,
        """SELECT date, open, high, low, close, volume
           FROM price_data
           WHERE symbol=%s AND market='TH' AND date >= %s AND date <= %s
           ORDER BY date ASC""",
        (symbol, start, end),
    )
    if not rows:
        raise ValueError(f"{symbol}: no Daily OHLCV rows in {start}..{end}")
    frame = pd.DataFrame(rows, columns=cols).rename(
        columns={"date": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )
    frame["Date"] = pd.to_datetime(frame["Date"])
    for col in ("Open", "High", "Low", "Close", "Volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if frame[["Open", "High", "Low", "Close"]].dropna(how="any").empty:
        raise ValueError(f"{symbol}: no usable Daily OHLC rows")
    return frame.reset_index(drop=True)


def run_no_lookahead(frame: pd.DataFrame):
    observations = []
    state_counts = collections.Counter()
    confidence_counts = collections.Counter()
    missing_counts = collections.Counter()
    previous = None
    transitions = []
    final_result = None
    for index in range(len(frame)):
        prefix = frame.iloc[: index + 1].copy()
        result = engine.classify_wave_candidate(prefix)
        final_result = result
        evidence = result.get("evidence") or {}
        state = str(result.get("state") or "UNKNOWN")
        confidence = str(result.get("confidence") or "UNKNOWN")
        date = frame.iloc[index]["Date"]
        state_counts[state] += 1
        confidence_counts[confidence] += 1
        for item in evidence.get("missing_evidence") or []:
            missing_counts[str(item)] += 1
        observation = {
            "date": date,
            "state": state,
            "confidence": confidence,
            "close": float(frame.iloc[index]["Close"]),
            "wave1_low": evidence.get("wave1_low"),
            "wave1_high": evidence.get("wave1_high"),
            "retracement_pct": evidence.get("retracement_pct"),
            "holds_above_wave1_low": evidence.get("holds_above_wave1_low"),
        }
        observations.append(observation)
        if state != previous:
            transitions.append({
                "date": date.isoformat(),
                "from": previous,
                "to": state,
                "close": observation["close"],
                "confidence": confidence,
            })
            previous = state
    return observations, transitions, final_result, state_counts, confidence_counts, missing_counts


def state_runs(observations):
    runs = []
    for obs in observations:
        if not runs or runs[-1]["state"] != obs["state"]:
            runs.append({"start": obs["date"], "end": obs["date"], "state": obs["state"]})
        else:
            runs[-1]["end"] = obs["date"]
    return runs


def weekly_raw_legs(frame: pd.DataFrame):
    weekly = (
        frame.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]]
        .resample("W-FRI")
        .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
        .dropna(subset=["Open", "High", "Low", "Close"])
    )
    legs = engine._swing_legs_ohlc(weekly, pct=0.07, min_bars=2)
    mapped = []
    for leg in legs:
        start = int(leg["start"])
        end = int(leg["end"])
        mapped.append({
            **json_safe(leg),
            "start_date": weekly.index[start].date().isoformat(),
            "end_date": weekly.index[end].date().isoformat(),
        })
    return weekly, mapped


def map_small_evidence(frame: pd.DataFrame, evidence: dict):
    mapped = []
    for item in evidence.get("small_waves") or []:
        try:
            end = int(item["end"])
            if end < 0 or end >= len(frame):
                raise IndexError(end)
            mapped.append({
                **json_safe(item),
                "date": frame.iloc[end]["Date"].date().isoformat(),
                "lineage": "exact engine evidence index",
            })
        except Exception:
            mapped.append({"label": item.get("label") if isinstance(item, dict) else None, "date": "NOT_EXPOSED", "lineage": "NOT_EXPOSED"})
    return mapped


def render_chart(symbol: str, frame: pd.DataFrame, observations, transitions, final_result, weekly, weekly_legs, out_path: Path):
    evidence = final_result.get("evidence") or {}
    small = map_small_evidence(frame, evidence)
    fig = plt.figure(figsize=(16, 10))
    grid = fig.add_gridspec(3, 1, height_ratios=[3.2, 1.0, 1.8], hspace=0.34)
    price_ax = fig.add_subplot(grid[0, 0])
    state_ax = fig.add_subplot(grid[1, 0], sharex=price_ax)
    week_ax = fig.add_subplot(grid[2, 0])

    dates = frame["Date"]
    price_ax.plot(dates, frame["Close"], color="#0f172a", linewidth=1.4, label="Daily Close")
    price_ax.fill_between(dates, frame["Low"], frame["High"], color="#cbd5e1", alpha=0.42, label="Daily High-Low")

    interesting = {"WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3", "WAVE_3_CONTINUATION"}
    offset_slot = 0
    date_to_close = {row.Date.date().isoformat(): float(row.Close) for row in frame.itertuples()}
    for transition in transitions:
        if transition["to"] not in interesting:
            continue
        when = pd.Timestamp(transition["date"])
        price = date_to_close.get(when.date().isoformat(), transition["close"])
        color = STATE_COLORS.get(transition["to"], "#334155")
        y_offset = 13 + (offset_slot % 4) * 12
        offset_slot += 1
        price_ax.scatter([when], [price], color=color, s=26, zorder=5)
        price_ax.annotate(
            f"detect {STATE_SHORT.get(transition['to'], transition['to'])}",
            xy=(when, price), xytext=(0, y_offset), textcoords="offset points",
            ha="center", fontsize=6.7, color=color,
            arrowprops={"arrowstyle": "-", "color": color, "lw": 0.55},
        )

    for index, item in enumerate(small):
        if item.get("date") == "NOT_EXPOSED":
            continue
        when = pd.Timestamp(item["date"])
        price = date_to_close.get(item["date"])
        if price is None:
            continue
        price_ax.annotate(
            f"small evidence {item.get('label', '(?)')}", xy=(when, price),
            xytext=(8 + (index % 3) * 9, -22 - (index % 2) * 11), textcoords="offset points",
            fontsize=6.4, color="#7e22ce", arrowprops={"arrowstyle": "-", "color": "#a855f7", "lw": 0.5},
        )

    anchor_text = (
        "FINAL ENGINE ANCHOR VALUES (as-of end)\n"
        f"wave1_low: {evidence.get('wave1_low')} | date: NOT_EXPOSED\n"
        f"wave1_high: {evidence.get('wave1_high')} | date: NOT_EXPOSED\n"
        f"retracement_pct: {evidence.get('retracement_pct')}\n"
        f"holds_above_wave1_low: {evidence.get('holds_above_wave1_low')}\n"
        "Markers above are detection dates, NOT wave endpoints."
    )
    price_ax.text(
        0.012, 0.985, anchor_text, transform=price_ax.transAxes, va="top", ha="left", fontsize=8,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "white", "edgecolor": "#64748b", "alpha": 0.94},
    )
    price_ax.set_title(f"{symbol} — honest engine evidence (no-lookahead); detection dates ≠ Elliott endpoints", fontsize=11)
    price_ax.set_ylabel("THB")
    price_ax.grid(alpha=0.15)
    price_ax.legend(loc="lower right", fontsize=7)

    ordered_states = list(STATE_COLORS)
    state_y = {state: index for index, state in enumerate(ordered_states)}
    for run in state_runs(observations):
        color = STATE_COLORS.get(run["state"], "#94a3b8")
        y = state_y.get(run["state"], 0)
        state_ax.plot([run["start"], run["end"]], [y, y], color=color, linewidth=6, solid_capstyle="butt")
    state_ax.set_yticks(range(len(ordered_states)), [STATE_SHORT.get(item, item) for item in ordered_states], fontsize=6.5)
    state_ax.set_title("Detected state timeline (point-in-time classifier output; not a claimed wave interval)", fontsize=8)
    state_ax.grid(axis="x", alpha=0.15)

    week_ax.plot(weekly.index, weekly["Close"], color="#334155", linewidth=1.2, marker="o", markersize=2.5, label="W-FRI Close")
    for index, leg in enumerate(weekly_legs):
        start = pd.Timestamp(leg["start_date"])
        end = pd.Timestamp(leg["end_date"])
        color = "#16a34a" if int(leg["direction"]) == 1 else "#dc2626"
        week_ax.plot([start, end], [leg["start_price"], leg["end_price"]], color=color, linewidth=2.2)
        week_ax.annotate(
            f"raw {'up' if int(leg['direction']) == 1 else 'down'} leg {index + 1}",
            xy=(end, leg["end_price"]), xytext=(4, 7 if int(leg["direction"]) == 1 else -12),
            textcoords="offset points", fontsize=6.5, color=color,
        )
    week_ax.set_title("Weekly raw structural legs — 7% / 2 bars pilot (NOT Elliott state; NOT labels 1/2/3)", fontsize=8)
    week_ax.set_ylabel("THB")
    week_ax.grid(alpha=0.15)
    week_ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    week_ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))

    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return small


def process_symbol(conn, symbol: str, start: dt.date, end: dt.date, out_dir: Path):
    frame = load_bounded_daily(conn, symbol, start, end)
    observations, transitions, final_result, state_counts, confidence_counts, missing_counts = run_no_lookahead(frame)
    weekly, weekly_legs = weekly_raw_legs(frame)
    png = out_dir / f"{symbol}_engine_evidence.png"
    small = render_chart(symbol, frame, observations, transitions, final_result, weekly, weekly_legs, png)
    evidence = final_result.get("evidence") or {}
    sidecar = {
        "status": "COMPLETE_PROTOTYPE_EVIDENCE",
        "symbol": symbol,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "trading_rows": len(frame),
        "no_lookahead": "for each trading as_of, classifier receives only Daily rows with date <= as_of",
        "engine": {"variant": final_result.get("variant") or getattr(engine, "VARIANT", None), "config": evidence.get("variant_config")},
        "state_counts": dict(sorted(state_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "missing_evidence_counts": dict(sorted(missing_counts.items())),
        "transitions": transitions,
        "final_anchor": {
            "wave1_low": evidence.get("wave1_low"),
            "wave1_low_date": "NOT_EXPOSED",
            "wave1_high": evidence.get("wave1_high"),
            "wave1_high_date": "NOT_EXPOSED",
            "retracement_pct": evidence.get("retracement_pct"),
            "holds_above_wave1_low": evidence.get("holds_above_wave1_low"),
        },
        "small_degree_evidence": small,
        "weekly_raw_structural_legs": weekly_legs,
        "weekly_raw_leg_count": len(weekly_legs),
        "semantic_limitations": [
            "Detection transitions are classifier dates, not Elliott endpoints.",
            "The classifier does not expose final Wave-1 anchor indices/dates; dates are NOT_EXPOSED and never inferred from matching prices.",
            "Weekly 7%/2-bar output is raw structure only, not an Elliott state or labels 1/2/3.",
            "This throwaway chart is not production, owner approval, or trading advice.",
        ],
        "artifact": str(png),
    }
    sidecar_path = out_dir / f"{symbol}_engine_evidence.json"
    sidecar_path.write_text(json.dumps(json_safe(sidecar), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return sidecar, sidecar_path, png


def run(argv=None) -> int:
    args = parse_args(argv)
    out_dir = ensure_tmp(args.out_dir)
    manifest_path = out_dir / "manifest.json"
    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    if not symbols:
        raise ValueError("--symbols must contain at least one symbol")
    start = dt.date.fromisoformat(args.from_date)
    end = dt.date.fromisoformat(args.to_date)
    if end < start:
        raise ValueError("--to must be >= --from")

    manifest = {
        "status": "RUNNING",
        "symbols": symbols,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "expected_eligible": EXPECTED_ELIGIBLE,
        "artifacts": [],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    conn = None
    try:
        conn = replay_lab._get_conn()
        eligible, universe = replay_lab.resolve_universe(conn, "marginable_long")
        manifest["universe"] = universe
        manifest["universe"]["expected_eligible"] = EXPECTED_ELIGIBLE
        manifest["universe"]["observed_eligible"] = len(eligible)
        for symbol in symbols:
            sidecar, sidecar_path, png = process_symbol(conn, symbol, start, end, out_dir)
            manifest["artifacts"].append({
                "symbol": symbol,
                "png": str(png),
                "json": str(sidecar_path),
                "trading_rows": sidecar["trading_rows"],
                "state_counts": sidecar["state_counts"],
                "confidence_counts": sidecar["confidence_counts"],
                "missing_evidence_counts": sidecar["missing_evidence_counts"],
                "weekly_raw_leg_count": sidecar["weekly_raw_leg_count"],
            })
        manifest["status"] = "COMPLETE_PROTOTYPE_EVIDENCE"
        manifest["no_lookahead"] = "Daily prefix date <= each trading as_of; weekly pilot resamples only the bounded Daily rows"
        manifest["semantic_limitations"] = [
            "Observed universe is reported from the current replay resolver and may differ from expected 237.",
            "Anchor dates are NOT_EXPOSED by the engine contract.",
            "Weekly legs are raw structure, not Elliott states.",
            "No production or owner-approval verdict is implied.",
        ]
        manifest_path.write_text(json.dumps(json_safe(manifest), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(f"COMPLETE_PROTOTYPE_EVIDENCE symbols={len(symbols)} manifest={manifest_path}")
        for item in manifest["artifacts"]:
            print(f"{item['symbol']} rows={item['trading_rows']} weekly_raw_legs={item['weekly_raw_leg_count']} png={item['png']} json={item['json']}")
        return 0
    except Exception as exc:
        manifest["status"] = "FAIL"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest_path.write_text(json.dumps(json_safe(manifest), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(f"FAIL manifest={manifest_path} error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    finally:
        if conn is not None:
            conn.close()


def main() -> int:
    try:
        return run()
    except Exception as exc:
        print(f"FAIL before run: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
