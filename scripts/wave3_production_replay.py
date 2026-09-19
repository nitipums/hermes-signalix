#!/usr/bin/env python3
"""Read-only Wave-3 candidate replay for the 20-symbol and 237-row gates."""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from wave3_candidate_engine import PUBLISHABLE_STATES, _blank, classify_candles  # noqa: E402

PRIOR = "CPF PROUD SPRC TC APO BBGI BCP BGRIM CBG CENTEL".split()
HOLDOUT = "ADVANC BTG FUTURERT KCE MCS PSP SAT STPI TOP WPH".split()
EXPECTATIONS = {"BCP": "LIKELY_POSITIVE_W3", "KCE": "LIKELY_POSITIVE_W3",
                "APO": "LIKELY_NOT_CURRENT_W3", "BBGI": "LIKELY_NOT_CURRENT_W3_OR_W4",
                "BGRIM": "POSSIBLE_EARLY_W3", "CBG": "POSSIBLE_EARLY_W3",
                "CENTEL": "POSSIBLE_EARLY_W3"}


def load_candles(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    return [row for row in payload.get("candles", []) if not row.get("provisional", False)]


def relation(state: str, expectation: str | None) -> str:
    if not expectation:
        return "UNDERDETERMINED"
    positive = state in PUBLISHABLE_STATES
    if expectation == "LIKELY_POSITIVE_W3":
        return "SUPPORTS" if positive else "CHALLENGES"
    if expectation.startswith("LIKELY_NOT_CURRENT_W3"):
        return "SUPPORTS" if not positive else "CHALLENGES"
    return "SUPPORTS" if state == "EARLY_WAVE_3" else "UNDERDETERMINED"


def history(candles: list[dict], count: int = 5) -> list[dict]:
    return [{"as_of": result["as_of"], "raw_state": result["raw_state"],
             "published_state": result["published_state"]}
            for result in (classify_candles(candles[:end])
                           for end in range(max(1, len(candles) - count + 1), len(candles) + 1))]


def row(symbol: str, chart_dir: Path, current: dict) -> dict:
    path = chart_dir / f"{symbol}-day.json"
    if path.exists():
        candles = load_candles(path)
        result = classify_candles(candles) if candles else _blank("no_daily_data")
        coverage = "GE_250_BARS" if len(candles) >= 250 else "INSUFFICIENT_HISTORY"
    else:
        candles, result, coverage = [], _blank("NO_DAILY_DATA_AVAILABLE_TO_ISOLATED_REPLAY"), "NO_DATA"
    wave = current.get(symbol, {}).get("wave", {})
    return {"symbol": symbol, "coverage": coverage, "bars_available": len(candles), **result,
            "adjacent_as_of_history": history(candles),
            "current_engine_before": {"state": wave.get("primary_state"), "confidence": wave.get("confidence")},
            "owner_expectation": EXPECTATIONS.get(symbol),
            "owner_relation": relation(result["published_state"], EXPECTATIONS.get(symbol))}


def counts(rows: list[dict], key: str) -> dict:
    return dict(sorted(collections.Counter(str(r[key]) for r in rows).items()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chart-dir", required=True, type=Path)
    parser.add_argument("--engine-json", required=True, type=Path)
    parser.add_argument("--universe-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    engine_payload = json.loads(args.engine_json.read_text())
    current = {item["symbol"]: item for item in engine_payload.get("items", [])}
    twenty = [row(symbol, args.chart_dir, current) for symbol in PRIOR + HOLDOUT]
    universe_payload = json.loads(args.universe_json.read_text())
    symbols = sorted({str(item["symbol"]).upper() for item in universe_payload["securities"]
                      if item.get("instrument_type") == "ORD" and item.get("can_buy") is True})
    full = [row(symbol, args.chart_dir, current) for symbol in symbols]
    usable = [item for item in full if item["coverage"] != "NO_DATA"]
    reasons = collections.Counter(reason for item in full for reason in item["rejection_reasons"])
    transitions = [{"symbol": item["symbol"], "history": item["adjacent_as_of_history"],
                    "revisions": sum(a["published_state"] != b["published_state"]
                                     for a, b in zip(item["adjacent_as_of_history"], item["adjacent_as_of_history"][1:]))}
                   for item in usable]
    report = {
        "status": "PASS" if len(usable) == len(symbols) == 237 else "NOT_VERIFIED_INCOMPLETE_READ_ONLY_DATA",
        "policy": "wave3-confirmed-pivots-v1", "timezone": "Asia/Bangkok",
        "no_lookahead": "PASS_PREFIX_ONLY", "twenty_symbol_rows": twenty,
        "universe": {"expected": 237, "evaluated": len(usable), "returned": len(full)},
        "coverage_distribution": counts(full, "coverage"),
        "state_distribution": counts(full, "published_state"),
        "confidence_distribution": counts(full, "confidence"),
        "rejection_distribution": dict(sorted(reasons.items())),
        "adjacent_as_of_stability": transitions,
        "canonical_api_envelope": {"source_items_available": len(engine_payload.get("items", [])),
                                   "items_is_list": isinstance(engine_payload.get("items"), list),
                                   "all_eligible_rows_preserved": len(full) == 237},
        "rows": full,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "wave3-round2-20-symbol.json").write_text(json.dumps({"rows": twenty}, indent=2, allow_nan=False) + "\n")
    (args.output_dir / "wave3-round3-shadow.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"round2": {"returned": len(twenty), "states": counts(twenty, "published_state")},
                      "round3": report["universe"], "coverage": report["coverage_distribution"],
                      "states": report["state_distribution"], "status": report["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
