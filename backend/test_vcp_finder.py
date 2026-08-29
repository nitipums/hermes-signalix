import json
from datetime import datetime, timedelta, timezone

import pandas as pd

import vcp_finder
from vcp_finder import VCP60Config, _review_lane, _sequences, find_vcp_60m


def bars(n=100, start=10.0):
    ts = datetime(2026, 8, 1, tzinfo=timezone.utc)
    rows = []
    price = start
    for i in range(n):
        price += 0.03
        rows.append({
            "ts": ts + timedelta(hours=i),
            "open": price,
            "high": price + 0.08,
            "low": price - 0.08,
            "close": price + 0.02,
            "volume": 1000 + (i % 5) * 10,
        })
    return rows


def test_insufficient_history_is_explicit_and_json_safe():
    result = find_vcp_60m(pd.DataFrame(bars(79)))
    assert result["state"] == "NOT_VERIFIED"
    assert "insufficient_history" in result["reason_codes"]
    assert result["actionable"] is False
    json.dumps(result)


def test_freshness_requires_closed_bar_and_explicit_health():
    as_of = datetime(2026, 8, 5, 4, tzinfo=timezone.utc)
    unknown = find_vcp_60m(pd.DataFrame(bars(100)), as_of=as_of)
    assert unknown["data"]["freshness"] == "unknown"
    assert unknown["data"]["latest_closed_bar"] != unknown["data"]["last_bar_ts"]
    assert unknown["state"] == "NOT_VERIFIED"

    fresh = find_vcp_60m(
        pd.DataFrame(bars(100)), as_of=as_of,
        feed_status="available", ingestion_status="full_success",
    )
    assert fresh["data"]["freshness"] == "fresh"


def test_open_latest_bar_is_not_reported_as_latest_closed_bar():
    as_of = datetime(2026, 8, 5, 4, tzinfo=timezone.utc)
    result = find_vcp_60m(
        pd.DataFrame(bars(100)), as_of=as_of,
        feed_status="available", ingestion_status="full_success",
    )
    assert result["data"]["latest_bar_may_be_open"] is True
    assert result["data"]["latest_closed_bar"] != result["data"]["last_bar_ts"]


def test_downtrend_with_shrinking_ranges_is_not_vcp():
    rows = []
    ts = datetime(2026, 8, 1, tzinfo=timezone.utc)
    price = 30.0
    for i in range(100):
        price -= 0.08
        width = max(0.02, 0.30 - i * 0.002)
        rows.append({"ts": ts + timedelta(hours=i), "open": price, "high": price + width,
                     "low": price - width, "close": price - 0.01, "volume": 1000})
    result = find_vcp_60m(pd.DataFrame(rows))
    assert result["state"] not in {"READY", "CONFIRMED", "EXTENDED"}
    assert result["actionable"] is False


def test_invalid_and_duplicate_rows_are_reported():
    rows = bars(90)
    rows.append(rows[-1].copy())
    rows.append({"ts": rows[0]["ts"] + timedelta(hours=1), "open": 3, "high": 2,
                 "low": 4, "close": 3, "volume": -1})
    result = find_vcp_60m(pd.DataFrame(rows))
    assert result["data"]["duplicate_rows"] >= 1
    assert result["data"]["invalid_rows"] >= 1
    assert result["provenance"]["legacy_scanner_used"] is False
    json.dumps(result)


def test_daily_context_cannot_promote_60m_trend():
    result = find_vcp_60m(pd.DataFrame(bars(100)), daily_context={"trend_pass": True})
    assert result["trend"]["pass"] is result["trend"]["pass_60m"]


def test_review_lanes_keep_confirmation_separate():
    common = {"freshness": "fresh", "last_close": 100.0, "failure": 90.0}
    assert _review_lane(close_pass=True, volume_confirmed=True, structure_pass=False, distance_pct=2.0, **common) == "PRICE_VOLUME_BREAKOUT"
    assert _review_lane(close_pass=False, volume_confirmed=True, structure_pass=False, distance_pct=0.0, **common) == "PIVOT_TOUCH_VOLUME_WATCH"
    assert _review_lane(close_pass=True, volume_confirmed=False, structure_pass=False, distance_pct=2.0, **common) == "CLOSE_BREAKOUT_VOLUME_PENDING"
    assert _review_lane(close_pass=True, volume_confirmed=True, structure_pass=True, distance_pct=2.0, **common) is None
    assert _review_lane(close_pass=True, volume_confirmed=True, structure_pass=False, distance_pct=2.0, freshness="stale", last_close=100.0, failure=90.0) is None


def test_deterministic_replay():
    frame = pd.DataFrame(bars(100))
    a = find_vcp_60m(frame, as_of=datetime(2026, 8, 5, tzinfo=timezone.utc))
    b = find_vcp_60m(frame, as_of=datetime(2026, 8, 5, tzinfo=timezone.utc))
    assert a == b


def test_sequences_returns_every_confirmed_alternating_window():
    ts = datetime(2026, 8, 1, tzinfo=timezone.utc)
    pivots = [
        {"kind": kind, "idx": 40 + i, "ts": ts + timedelta(hours=i), "price": price}
        for i, (kind, price) in enumerate([
            ("high", 12.0), ("low", 10.0), ("high", 11.8),
            ("low", 10.5), ("high", 11.7), ("low", 10.7),
            ("high", 11.6),
        ])
    ]

    found = _sequences(pivots)

    assert len(found) == 2
    assert found[0][-1]["idx"] == 44
    assert found[1][-1]["idx"] == 46


def test_sequence_diagnostics_records_first_and_latest_sequence(monkeypatch):
    ts = datetime(2026, 8, 1, tzinfo=timezone.utc)
    pivots = [
        {"kind": kind, "idx": 40 + i, "ts": ts + timedelta(hours=i), "price": price}
        for i, (kind, price) in enumerate([
            ("high", 12.0), ("low", 10.0), ("high", 11.8),
            ("low", 10.5), ("high", 11.7), ("low", 10.7),
            ("high", 11.6),
        ])
    ]
    monkeypatch.setattr(vcp_finder, "_pivots", lambda *_: pivots)
    as_of = datetime(2026, 8, 8, tzinfo=timezone.utc)

    result = find_vcp_60m(pd.DataFrame(bars(100)), as_of=as_of)

    diagnostics = result["pattern"]["sequence_diagnostics"]
    assert diagnostics["candidate_count"] == 2
    assert diagnostics["v1_selection_rule"] == "first_confirmed_sequence"
    assert diagnostics["v2_shadow_selection_rule"] == "latest_non_broken_sequence"
    assert diagnostics["v1_final_pivot_ts"] == pivots[4]["ts"].isoformat()
    assert diagnostics["v2_final_pivot_ts"] == pivots[6]["ts"].isoformat()
    assert diagnostics["v2_final_pivot_age_hours"] == 7 * 24 - 6
    assert result["price"]["pivot_high"] == 11.6


def test_sequence_policy_shadow_matches_production_latest_sequence(monkeypatch):
    ts = datetime(2026, 8, 1, tzinfo=timezone.utc)
    pivots = [
        {"kind": kind, "idx": 40 + i, "ts": ts + timedelta(hours=i), "price": price}
        for i, (kind, price) in enumerate([
            ("high", 12.0), ("low", 10.0), ("high", 11.8),
            ("low", 10.5), ("high", 11.7), ("low", 10.7),
            ("high", 11.6),
        ])
    ]
    monkeypatch.setattr(vcp_finder, "_pivots", lambda *_: pivots)
    frame = pd.DataFrame(bars(100))
    as_of = datetime(2026, 8, 8, tzinfo=timezone.utc)

    v1 = find_vcp_60m(frame, as_of=as_of)
    shadowed = find_vcp_60m(
        frame, as_of=as_of, include_sequence_policy_shadow=True,
    )

    assert "sequence_policy_shadow_v2" not in v1
    assert v1["price"]["pivot_high"] == 11.6
    assert shadowed["price"]["pivot_high"] == 11.6
    shadow = shadowed["sequence_policy_shadow_v2"]
    assert shadow["policy_version"] == "signalix/vcp-sequence-policy-shadow-v2"
    assert shadow["selection"]["candidate_count"] == 2
    assert shadow["selection"]["selected_final_pivot_idx"] == 46
    assert shadow["price"]["pivot_high"] == 11.6
    assert shadow["price"]["invalidation"] == 10.7
    json.dumps(shadow)


def test_sequence_policy_shadow_selects_prior_non_broken_candidate(monkeypatch):
    ts = datetime(2026, 8, 1, tzinfo=timezone.utc)
    pivots = [
        {"kind": kind, "idx": 40 + i, "ts": ts + timedelta(hours=i), "price": price}
        for i, (kind, price) in enumerate([
            ("high", 12.0), ("low", 10.0), ("high", 11.8),
            ("low", 10.5), ("high", 11.7), ("low", 10.7),
            ("high", 11.6),
        ])
    ]
    monkeypatch.setattr(vcp_finder, "_pivots", lambda *_: pivots)
    rows = bars(100)
    rows[-1].update({"open": 10.6, "high": 10.65, "low": 10.55, "close": 10.6})

    result = find_vcp_60m(
        pd.DataFrame(rows), as_of=datetime(2026, 8, 8, tzinfo=timezone.utc),
        include_sequence_policy_shadow=True,
    )

    shadow = result["sequence_policy_shadow_v2"]
    assert shadow["selection"]["selected_final_pivot_idx"] == 44
    assert shadow["price"]["pivot_high"] == 11.7
    assert shadow["price"]["invalidation"] == 10.5


def test_sequence_policy_shadow_is_explicit_for_insufficient_history():
    result = find_vcp_60m(
        pd.DataFrame(bars(79)), include_sequence_policy_shadow=True,
    )

    shadow = result["sequence_policy_shadow_v2"]
    assert shadow["state"] == "NO_ACTIVE_SEQUENCE"
    assert shadow["selection"]["reason"] == "insufficient_history"
    assert shadow["standard_entry_eligible"] is False
