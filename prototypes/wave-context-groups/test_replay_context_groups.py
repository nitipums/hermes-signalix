import datetime as dt
import importlib.util
from pathlib import Path

import pandas as pd
import pytest


MODULE_PATH = Path(__file__).with_name("replay_context_groups.py")
SPEC = importlib.util.spec_from_file_location("test_context_replay_module", MODULE_PATH)
assert SPEC and SPEC.loader
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def _row(as_of, state="WAVE_1_ADVANCE", ambiguous=False, missing=None):
    return {
        "symbol": "AAA",
        "as_of": as_of,
        "structural_state": state,
        "confidence": "MEDIUM",
        "context_marker": "WAVE_1_RISING" if state != "UNKNOWN" else "NONE/UNKNOWN",
        "secondary_marker": "NOT_EXPOSED",
        "ambiguous": ambiguous,
        "missing_evidence": list(missing or []),
        "rationale": [],
    }


def test_symbol_selection_keeps_default_ten_and_deduplicates_all_eligible():
    mode, symbols = replay.select_symbols(False, ["ZZZ"])
    assert mode == "owner_labelled_10"
    assert symbols == replay.SYMBOLS

    mode, symbols = replay.select_symbols(True, ["bbb", "AAA", "BBB", ""])
    assert mode == "all_marginable_long_eligible"
    assert symbols == ("AAA", "BBB")


def test_all_eligible_manifest_retains_no_data_and_reconciles_totals():
    symbols = ("AAA", "BBB", "CCC", "DDD")
    rows = {
        "AAA": [_row("2026-08-28")],
        "BBB": [],
        "CCC": [_row("2026-08-28", missing=["ordered anchors"])],
        "DDD": [_row("2026-08-28", state="UNKNOWN", ambiguous=True)],
    }
    manifest = replay.build_manifest(
        rows,
        {symbol: True for symbol in symbols},
        symbols,
        {"eligible_count": 4, "expected_eligible": 4, "schema_version": "test-rule-v1"},
        "all_marginable_long_eligible",
    )

    assert [row["symbol"] for row in manifest["per_symbol"]] == list(symbols)
    assert manifest["per_symbol"][1]["accounting_status"] == "NO_DAILY_DATA"
    assert manifest["per_symbol"][1]["final"] is None
    assert manifest["coverage"] == {
        "expected_eligible_count": 4,
        "observed_eligible_count": 4,
        "selected_symbol_count": 4,
        "unique_symbol_count": 4,
        "symbols_unique": True,
        "evaluated_symbol_count": 3,
        "prefix_evaluation_count": 3,
        "no_daily_data_symbol_count": 1,
        "insufficient_evidence_symbol_count": 1,
        "ambiguous_symbol_count": 1,
        "returned_accounting_row_count": 4,
        "symbol_totals_reconcile": True,
        "prefix_totals_reconcile": True,
    }


def test_all_eligible_manifest_rejects_selection_parity_mismatch():
    with pytest.raises(AssertionError, match="does not match"):
        replay.build_manifest(
            {"AAA": []},
            {"AAA": True},
            ("AAA",),
            {"eligible_count": 2, "expected_eligible": 2},
            "all_marginable_long_eligible",
        )


def test_replay_uses_only_inclusive_prefix_through_each_as_of(monkeypatch):
    frame = pd.DataFrame({
        "Date": pd.to_datetime(["2026-08-26", "2026-08-27", "2026-08-28", "2026-08-29"]),
        "Open": [1.0, 2.0, 3.0, 4.0],
        "High": [1.0, 2.0, 3.0, 4.0],
        "Low": [1.0, 2.0, 3.0, 4.0],
        "Close": [1.0, 2.0, 3.0, 4.0],
        "Volume": [10, 20, 30, 40],
    })
    seen = []

    class Engine:
        @staticmethod
        def classify_wave_candidate(prefix):
            dates = pd.to_datetime(prefix["Date"]).dt.date.tolist()
            seen.append(dates)
            return {"state": "WAVE_1_ADVANCE", "confidence": "MEDIUM", "evidence": {}}

    monkeypatch.setattr(replay, "elliott_structure_engine", Engine)
    rows = replay.replay_symbol("AAA", frame, dt.date(2026, 8, 27), dt.date(2026, 8, 28))

    assert [row["as_of"] for row in rows] == ["2026-08-27", "2026-08-28"]
    assert seen == [
        [dt.date(2026, 8, 26), dt.date(2026, 8, 27)],
        [dt.date(2026, 8, 26), dt.date(2026, 8, 27), dt.date(2026, 8, 28)],
    ]
    assert all(max(prefix) <= dt.date.fromisoformat(row["as_of"]) for prefix, row in zip(seen, rows))


def test_parse_as_of_accepts_strict_iso_date_and_rejects_invalid_values():
    assert replay.parse_args(["--as-of", "2026-08-28"]).as_of == dt.date(2026, 8, 28)
    for invalid in ("2026-02-30", "28-08-2026", "2026-8-28"):
        with pytest.raises(SystemExit):
            replay.parse_args(["--as-of", invalid])


def test_single_as_of_selects_one_exact_observation_with_full_prefix(monkeypatch):
    frame = pd.DataFrame({
        "Date": pd.to_datetime(["2026-08-26", "2026-08-27", "2026-08-28", "2026-08-29"]),
        "Close": [1.0, 2.0, 3.0, 4.0],
    })
    seen = []

    class Engine:
        @staticmethod
        def classify_wave_candidate(prefix):
            seen.append(pd.to_datetime(prefix["Date"]).dt.date.tolist())
            return {"state": "WAVE_1_ADVANCE", "confidence": "MEDIUM", "evidence": {}}

    monkeypatch.setattr(replay, "elliott_structure_engine", Engine)
    rows = replay.replay_symbol_as_of("AAA", frame, dt.date(2026, 8, 28))

    assert [row["as_of"] for row in rows] == ["2026-08-28"]
    assert seen == [[dt.date(2026, 8, 26), dt.date(2026, 8, 27), dt.date(2026, 8, 28)]]


def test_single_as_of_manifest_uses_requested_window_and_reconciles_prefixes():
    requested = dt.date(2026, 8, 28)
    manifest = replay.build_manifest(
        {"AAA": [_row(requested.isoformat())], "BBB": []},
        {"AAA": True, "BBB": True},
        ("AAA", "BBB"),
        {"eligible_count": 2, "expected_eligible": 2},
        "all_marginable_long_eligible",
        requested,
        requested,
    )

    assert manifest["window"] == {"from": "2026-08-28", "to": "2026-08-28", "inclusive": True}
    assert manifest["coverage"]["prefix_evaluation_count"] == 1
    assert manifest["coverage"]["evaluated_symbol_count"] == 1
    assert manifest["coverage"]["no_daily_data_symbol_count"] == 1
    assert manifest["coverage"]["symbol_totals_reconcile"] is True
