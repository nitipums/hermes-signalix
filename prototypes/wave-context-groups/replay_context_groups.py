#!/usr/bin/env python3
"""Read-only, no-lookahead replay adapter for exploratory Wave context groups.

This module does not alter Elliott structural state.  It calls the existing
Daily classifier once for every symbol/date prefix, then maps the returned
canonical state and evidence to a display-only context marker.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
REPLAY_LAB = REPO_ROOT / "prototypes" / "elliott-state-replay" / "replay_lab.py"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SYMBOLS = ("BCP", "APO", "BBGI", "BGRIM", "CBG", "CENTEL", "CPF", "PROUD", "SPRC", "TC")
WINDOW_START = dt.date(2025, 8, 28)
WINDOW_END = dt.date(2026, 8, 28)
RULE_NAME = "canonical-context-evidence-map"
RULE_VERSION = "1.0.0"

try:
    import pandas as pd  # type: ignore
    import elliott_structure_engine  # type: ignore
except Exception as exc:  # pragma: no cover - --help and pure mapping remain usable
    pd = None  # type: ignore
    elliott_structure_engine = None  # type: ignore
    ENGINE_IMPORT_ERROR: Exception | None = exc
else:
    ENGINE_IMPORT_ERROR = None


def _load_replay_helpers():
    """Load the prior adapter so connection, SELECT guard, and universe logic are reused."""
    spec = importlib.util.spec_from_file_location("signalix_readonly_replay_lab", REPLAY_LAB)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load replay helpers from {REPLAY_LAB}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def map_context(wave: dict[str, Any]) -> dict[str, Any]:
    """Map canonical state to exploratory context without changing that state.

    Extension v1 is deliberately conjunctive: the canonical state must already
    be WAVE_3_CONTINUATION, with >=10 consecutive Daily closes above the Wave-1
    high, >10% 20-session advance, measurable continuation, and breakout-day
    volume above its 20-session average. Missing evidence fails closed.

    Wave 4 is SIDEWAYS only when the emitted 20-session change is within +/-3%
    and drawdown from the engine reference high is no worse than -8%; it is a
    CORRECTION only with emitted measurable_pullback or <=-3% 20-session change.
    Otherwise the context is UNKNOWN.
    """
    state = str(wave.get("state") or "UNKNOWN")
    evidence = wave.get("evidence") if isinstance(wave.get("evidence"), dict) else {}
    marker = {
        "WAVE_1_ADVANCE": "WAVE_1_RISING",
        "WAVE_2_FORMING": "WAVE_2_PULLBACK",
        "WAVE_2_NEAR_COMPLETION": "WAVE_2_PULLBACK",
        "EARLY_WAVE_3": "WAVE_3_EARLY",
        "WAVE_3_CONTINUATION": "WAVE_3_CONTINUING",
        "WAVE_5_ADVANCE": "WAVE_5_RISING",
        "UNKNOWN": "NONE/UNKNOWN",
    }.get(state, "NONE/UNKNOWN")
    secondary = "NOT_EXPOSED"
    rationale: list[str] = []

    if state == "WAVE_3_CONTINUATION":
        days = evidence.get("sustained_days_above_wave1_high")
        advance20 = _number(evidence.get("daily_advance_20d_pct"))
        extension_checks = {
            "sustained_days_above_wave1_high_gte_10": isinstance(days, int) and days >= 10,
            "daily_advance_20d_pct_gt_10": advance20 is not None and advance20 > 10.0,
            "measurable_continuation": evidence.get("measurable_continuation") is True,
            "volume_above_avg": evidence.get("volume_above_avg") is True,
        }
        if all(extension_checks.values()):
            secondary = "WAVE_3_EXTENDED"
            rationale.append("all conservative extension checks passed")
        else:
            rationale.append("extension NOT_EXPOSED: one or more required checks absent/false")
    elif state == "WAVE_4_CORRECTION":
        advance20 = _number(evidence.get("daily_advance_20d_pct"))
        drawdown = _number(evidence.get("daily_drawdown_from_10d_high_pct"))
        if advance20 is not None and abs(advance20) <= 3.0 and drawdown is not None and drawdown >= -8.0:
            marker = "WAVE_4_SIDEWAYS"
            rationale.append("20-session change within +/-3% and drawdown >= -8%")
        elif evidence.get("measurable_pullback") is True or (advance20 is not None and advance20 <= -3.0):
            marker = "WAVE_4_CORRECTION"
            rationale.append("measurable pullback or 20-session decline <= -3%")
        else:
            marker = "UNKNOWN"
            rationale.append("Wave 4 subtype evidence insufficient")

    missing = list(evidence.get("missing_evidence") or [])
    ambiguous = marker in {"UNKNOWN", "NONE/UNKNOWN"} or bool(missing)
    return {
        "structural_state": state,
        "context_marker": marker,
        "secondary_marker": secondary,
        "ambiguous": ambiguous,
        "missing_evidence": missing,
        "rationale": rationale,
        "rule_name": RULE_NAME,
        "rule_version": RULE_VERSION,
    }


def _load_bounded_daily(conn, helpers, symbol: str, end: dt.date):
    # The prior helper contains the guarded SELECT and date <= as_of predicate.
    frame, latest = helpers.load_daily_pit(conn, symbol, end)
    if frame is not None and len(frame):
        frame = frame.sort_values("Date", kind="stable").reset_index(drop=True)
    return frame, latest


def replay_symbol(symbol: str, frame, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if frame is None or len(frame) == 0:
        return results
    dates = pd.to_datetime(frame["Date"]).dt.date
    positions = [index for index, value in enumerate(dates) if start <= value <= end]
    for index in positions:
        as_of = dates.iloc[index]
        prefix = frame.iloc[: index + 1].copy()
        if any(pd.to_datetime(prefix["Date"]).dt.date > as_of):
            raise AssertionError("no-lookahead invariant violated")
        wave = elliott_structure_engine.classify_wave_candidate(prefix)
        mapped = map_context(wave)
        results.append({
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "structural_state": mapped["structural_state"],
            "confidence": wave.get("confidence"),
            "context_marker": mapped["context_marker"],
            "secondary_marker": mapped["secondary_marker"],
            "ambiguous": mapped["ambiguous"],
            "missing_evidence": mapped["missing_evidence"],
            "rationale": mapped["rationale"],
        })
    return results


def _summarize(symbol: str, rows: list[dict[str, Any]], eligible: bool) -> dict[str, Any]:
    state_counts = Counter(row["structural_state"] for row in rows)
    context_counts = Counter(row["context_marker"] for row in rows)
    secondary_counts = Counter(row["secondary_marker"] for row in rows)
    transitions: list[dict[str, str]] = []
    for previous, current in zip(rows, rows[1:]):
        left = (previous["structural_state"], previous["context_marker"], previous["secondary_marker"])
        right = (current["structural_state"], current["context_marker"], current["secondary_marker"])
        if left != right:
            transitions.append({"date": current["as_of"], "from": " | ".join(left), "to": " | ".join(right)})
    spans: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row["context_marker"]
        spans.setdefault(key, {"first": row["as_of"], "last": row["as_of"]})["last"] = row["as_of"]
    return {
        "symbol": symbol,
        "marginable_long_eligible": eligible,
        "trading_date_prefix_count": len(rows),
        "final": rows[-1] if rows else None,
        "state_counts": dict(sorted(state_counts.items())),
        "context_counts": dict(sorted(context_counts.items())),
        "secondary_counts": dict(sorted(secondary_counts.items())),
        "transitions": transitions,
        "first_last_by_context": dict(sorted(spans.items())),
        "missing_count": sum(bool(row["missing_evidence"]) for row in rows),
        "ambiguous_count": sum(bool(row["ambiguous"]) for row in rows),
    }


def build_manifest(all_rows: dict[str, list[dict[str, Any]]], eligibility: dict[str, bool]) -> dict[str, Any]:
    summaries = [_summarize(symbol, all_rows.get(symbol, []), eligibility.get(symbol, False)) for symbol in SYMBOLS]
    return {
        "prototype": "wave-context-groups",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window": {"from": WINDOW_START.isoformat(), "to": WINDOW_END.isoformat(), "inclusive": True},
        "symbols": list(SYMBOLS),
        "rule": {
            "name": RULE_NAME,
            "version": RULE_VERSION,
            "extension": "W3_CONTINUATION AND sustained closes above W1 high >=10 AND 20d advance >10% AND measurable continuation AND volume above 20d average",
            "wave4_sideways": "W4 state AND abs(20d change)<=3% AND drawdown>=-8%",
            "wave4_correction": "W4 state AND (measurable pullback OR 20d change<=-3%); otherwise UNKNOWN",
        },
        "no_lookahead": "For each trading date as_of, classifier input is the sorted Daily prefix containing only rows with date <= as_of. The DB loader itself uses date <= window end.",
        "canonical_state_unchanged": True,
        "rows_included": False,
        "per_symbol": summaries,
    }


def render_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Wave context-group replay report", "",
        f"Window: `{WINDOW_START}` through `{WINDOW_END}` inclusive. Rule: `{RULE_NAME}` v`{RULE_VERSION}`.", "",
        "No lookahead: each classification receives only the Daily prefix with `date <= as_of`. Structural state is recorded unchanged; all context fields are exploratory.", "",
        "| Symbol | Eligible | Prefixes | Final state | Final context | Missing | Ambiguous | Transitions |",
        "|---|---:|---:|---|---|---:|---:|---:|",
    ]
    for summary in manifest["per_symbol"]:
        final = summary["final"] or {}
        lines.append(
            f"| {summary['symbol']} | {str(summary['marginable_long_eligible']).lower()} | {summary['trading_date_prefix_count']} | "
            f"{final.get('structural_state', 'NO_DATA')} | {final.get('context_marker', 'NO_DATA')} / {final.get('secondary_marker', 'NOT_EXPOSED')} | "
            f"{summary['missing_count']} | {summary['ambiguous_count']} | {len(summary['transitions'])} |"
        )
    lines.extend(["", "## Per-symbol details", ""])
    for summary in manifest["per_symbol"]:
        lines.extend([
            f"### {summary['symbol']}", "",
            f"- State counts: `{json.dumps(summary['state_counts'], sort_keys=True)}`",
            f"- Context counts: `{json.dumps(summary['context_counts'], sort_keys=True)}`",
            f"- Secondary counts: `{json.dumps(summary['secondary_counts'], sort_keys=True)}`",
            f"- First/last dates: `{json.dumps(summary['first_last_by_context'], sort_keys=True)}`",
            f"- Transitions: `{json.dumps(summary['transitions'], sort_keys=True)}`",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def synthetic_smoke() -> int:
    wave = {"state": "WAVE_3_CONTINUATION", "evidence": {
        "sustained_days_above_wave1_high": 10, "daily_advance_20d_pct": 10.01,
        "measurable_continuation": True, "volume_above_avg": True, "missing_evidence": [],
    }}
    mapped = map_context(wave)
    assert mapped["structural_state"] == "WAVE_3_CONTINUATION"
    assert mapped["context_marker"] == "WAVE_3_CONTINUING"
    assert mapped["secondary_marker"] == "WAVE_3_EXTENDED"
    wave["evidence"]["volume_above_avg"] = False
    assert map_context(wave)["secondary_marker"] == "NOT_EXPOSED"
    assert map_context({"state": "UNKNOWN", "evidence": {}})["context_marker"] == "NONE/UNKNOWN"
    print("synthetic smoke: PASS")
    return 0


def _tmp_path(raw: str) -> Path:
    path = Path(raw).resolve()
    try:
        path.relative_to(Path("/tmp").resolve())
    except ValueError as exc:
        raise ValueError(f"output must be under /tmp: {path}") from exc
    return path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Daily replay for exploratory Wave context groups")
    parser.add_argument("--manifest", default="/tmp/wave_context_groups_manifest.json", help="JSON output under /tmp")
    parser.add_argument("--report", default="/tmp/wave_context_groups_report.md", help="Markdown output under /tmp")
    parser.add_argument("--synthetic-smoke", action="store_true", help="run pure deterministic mapping checks; no DB access")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.synthetic_smoke:
        return synthetic_smoke()
    if ENGINE_IMPORT_ERROR is not None:
        print(f"ERROR importing engine dependencies: {ENGINE_IMPORT_ERROR}", file=sys.stderr)
        return 3
    try:
        manifest_path, report_path = _tmp_path(args.manifest), _tmp_path(args.report)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    helpers = _load_replay_helpers()
    conn = helpers._get_conn()
    try:
        eligible_symbols, universe_meta = helpers.resolve_universe(conn, "marginable_long")
        eligible = set(eligible_symbols)
        all_rows: dict[str, list[dict[str, Any]]] = {}
        for symbol in SYMBOLS:
            frame, _latest = _load_bounded_daily(conn, helpers, symbol, WINDOW_END)
            all_rows[symbol] = replay_symbol(symbol, frame, WINDOW_START, WINDOW_END)
        manifest = build_manifest(all_rows, {symbol: symbol in eligible for symbol in SYMBOLS})
        manifest["universe"] = universe_meta
    finally:
        conn.close()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(render_markdown(manifest), encoding="utf-8")
    outside = [symbol for symbol in SYMBOLS if not any(s["symbol"] == symbol and s["marginable_long_eligible"] for s in manifest["per_symbol"])]
    if outside:
        print("WARN outside marginable_long (replayed, not dropped): " + ", ".join(outside), file=sys.stderr)
    print(f"wrote {manifest_path} and {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
