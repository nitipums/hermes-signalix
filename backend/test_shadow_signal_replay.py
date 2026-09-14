import datetime as dt
import json

import mvp_routes
from shadow_signal_replay import build_shadow_buy_replay


def candidate(symbol="AAA", *, price=10.2, status="TRIGGERED", lane="REVIEW_NOW"):
    return {
        "symbol": symbol, "as_of": "2026-09-10", "decision_lane": lane,
        "data_status": {"sufficient": True, "daily_freshness": "fresh",
                        "intraday_60m_freshness": "fresh"},
        "quote": {"price": price}, "trend": {"state": "uptrend"},
        "wave": {"primary_state": "EARLY_WAVE_3", "confidence": "HIGH"},
        "setup": {"status": status, "trigger": 10.0,
                  "entry_zone": {"low": 9.8, "high": 10.5},
                  "trade_stop": 9.0, "target_1": 13.0,
                  "rr": {"to_target_1": 3.0}},
    }


def test_seven_day_replay_uses_each_point_in_time_boundary_and_deduplicates_setup():
    boundaries = [
        (dt.date(2026, 9, 9), dt.datetime(2026, 9, 9, 9, 0, tzinfo=dt.timezone.utc)),
        (dt.date(2026, 9, 10), dt.datetime(2026, 9, 10, 9, 0, tzinfo=dt.timezone.utc)),
    ]
    calls = []

    def builder(pg, *, as_of, completed_60m_as_of):
        calls.append((as_of, completed_60m_as_of))
        return [candidate(), candidate("WAIT", status="FORMING", lane="WAIT")], {"source": "test"}

    result = build_shadow_buy_replay(
        object(), now=dt.datetime(2026, 9, 11, tzinfo=dt.timezone.utc),
        candidate_builder=builder,
        session_loader=lambda pg, **kwargs: boundaries,
    )

    assert calls == boundaries
    assert result["window_days"] == 7
    assert result["session_count"] == 2
    assert result["evaluated_observations"] == 4
    assert result["signal_count"] == 1
    assert result["items"][0]["symbol"] == "AAA"
    assert result["items"][0]["sessions_present"] == 2
    assert result["items"][0]["first_signaled_at"].startswith("2026-09-09")
    assert result["items"][0]["last_signaled_at"].startswith("2026-09-10")
    assert result["provenance"]["no_lookahead"] is True
    assert result["execution"]["authorized"] is False


def test_replay_rejects_any_window_other_than_seven_days():
    import pytest
    with pytest.raises(ValueError, match="seven-day"):
        build_shadow_buy_replay(object(), days=5, session_loader=lambda *a, **k: [])


class Handler:
    def __init__(self):
        self.status = None
        self.body = b""
        self.wfile = self

    def send_response(self, status): self.status = status
    def send_header(self, *_): pass
    def end_headers(self): pass
    def write(self, body): self.body += body


def test_shadow_route_returns_market_replay_without_portfolio(monkeypatch):
    payload = {"schema_version": "shadow-market-buy-signals-v1", "items": []}
    monkeypatch.setattr(mvp_routes, "_load_shadow_buy_replay", lambda: payload)
    handler = Handler()
    assert mvp_routes.handle_mvp_api("/api/shadow-buy-signals?days=7", handler) is True
    assert handler.status == 200
    assert json.loads(handler.body) == payload


def test_shadow_route_rejects_noncanonical_window(monkeypatch):
    handler = Handler()
    mvp_routes.handle_mvp_api("/api/shadow-buy-signals?days=30", handler)
    assert handler.status == 400
    assert json.loads(handler.body)["reason"] == "only_7_days_supported"
