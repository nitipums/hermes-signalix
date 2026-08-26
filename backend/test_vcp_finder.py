import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from vcp_finder import VCP60Config, _review_lane, find_vcp_60m


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
