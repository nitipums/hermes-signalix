import json

import mvp_routes
from vcp_finder_db import project_daily_vcp_watchlist


class Handler:
    def __init__(self):
        self.status = None
        self.headers = []
        self.body = b""
        self.wfile = self

    def send_response(self, status): self.status = status
    def send_header(self, key, value): self.headers.append((key, value))
    def end_headers(self): pass
    def write(self, body): self.body += body


def _vcp_result(symbol, state, **kw):
    ev = dict(kw.get("evidence", {}))
    base_ev = {
        "prior_trend_pass": True,
        "price_contraction_pass": True,
        "base_pass": True,
        "leg_volume_pass": True,
    }
    base_ev.update(ev)
    price = dict(kw.get("price", {}))
    base_price = {
        "last_close": 52.0,
        "pivot_high": 50.0,
        "invalidation": 48.0,
        "distance_to_pivot_pct": 4.0,
    }
    base_price.update(price)
    breakout = dict(kw.get("breakout", {}))
    base_breakout = {
        "pivot_level": base_price["pivot_high"],
        "close_confirmed": state in {"READY", "CONFIRMED"},
    }
    base_breakout.update(breakout)
    trend = dict(kw.get("trend", {}))
    base_trend = {"daily_context_pass": True}
    base_trend.update(trend)
    data = dict(kw.get("data", {}))
    base_data = {
        "freshness": "fresh",
        "feed_status": "ok",
        "freshness_session_age": 0,
        "daily_metrics": {"avg_trade_value_20": 20_000_000},
    }
    base_data.update(data)
    return {
        "symbol": symbol,
        "state": state,
        "evidence": base_ev,
        "price": base_price,
        "breakout": base_breakout,
        "trend": base_trend,
        "data": base_data,
        "late_watch": kw.get("late_watch", False),
    }


def test_vcp_route_rejects_non_60m_without_db():
    h = Handler()
    assert mvp_routes.handle_mvp_api("/api/vcp-finder?interval=1D", h) is True
    assert h.status == 400
    assert json.loads(h.body)["error"]


def test_vcp_route_evaluates_then_filters(monkeypatch):
    payload = {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "results": [{"symbol": "AAA", "state": "READY"}, {"symbol": "BBB", "state": "FORMING"}],
        "universe": {"eligible": 2, "evaluated": 2, "returned": 2},
    }
    class Conn:
        def close(self): pass
    monkeypatch.setattr(mvp_routes, "_vcp_pg", lambda: Conn())
    def latest(pg, market, state, symbol, limit, actionable, focused, review, daily_watchlist=False):
        filtered = [r for r in payload["results"] if (not state or r["state"] == state) and (not actionable or r["state"] in {"READY", "NEAR_TRIGGER", "CONFIRMED"})]
        return {**payload, "results": filtered, "daily_watchlist": None}
    monkeypatch.setattr("vcp_finder_db.load_latest_vcp_run", latest)
    h = Handler()
    assert mvp_routes.handle_mvp_api("/api/vcp-finder?state=READY", h) is True
    assert h.status == 200
    assert [x["symbol"] for x in json.loads(h.body)["results"]] == ["AAA"]


def test_daily_watchlist_route_passes_flag(monkeypatch):
    payload = {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "run_id": "run-1",
        "universe": {"eligible": 2, "evaluated": 2, "returned": 2},
        "coverage": {"feed_unavailable": 0, "no_data": 0},
        "results": [],
        "daily_watchlist": {
            "policy_version": "signalix/daily-vcp-watchlist-v1",
            "caps": {"ACTION_REVIEW": 10, "NEAR_TRIGGER": 10, "BREAKOUT_WATCH": 5},
            "counts": {"ACTION_REVIEW": 0, "NEAR_TRIGGER": 0, "BREAKOUT_WATCH": 0},
            "action_review": [],
            "near_trigger": [],
            "breakout_watch": [],
        },
    }
    class Conn:
        def close(self): pass
    calls = {}
    monkeypatch.setattr(mvp_routes, "_vcp_pg", lambda: Conn())
    def latest(pg, market, daily_watchlist=False, **kw):
        calls["daily_watchlist"] = daily_watchlist
        return payload
    monkeypatch.setattr("vcp_finder_db.load_latest_vcp_run", latest)
    h = Handler()
    assert mvp_routes.handle_mvp_api("/api/vcp-finder?interval=60m&market=TH&daily_watchlist=true", h) is True
    assert h.status == 200
    body = json.loads(h.body)
    assert body["daily_watchlist"]["policy_version"] == "signalix/daily-vcp-watchlist-v1"
    assert calls["daily_watchlist"] is True


def test_confirmed_without_quality_is_excluded_from_action_review():
    confirmed = _vcp_result("CNF", "CONFIRMED", evidence={"base_pass": False})
    assert project_daily_vcp_watchlist([confirmed])["action_review"] == []


def test_near_trigger_without_quality_is_excluded():
    near = _vcp_result("NEAR", "NEAR_TRIGGER", evidence={"leg_volume_pass": False})
    assert project_daily_vcp_watchlist([near])["near_trigger"] == []


def test_extended_state_is_excluded():
    ext = _vcp_result("EXT", "EXTENDED")
    assert project_daily_vcp_watchlist([ext])["action_review"] == []
    assert project_daily_vcp_watchlist([ext])["near_trigger"] == []
    assert project_daily_vcp_watchlist([ext])["breakout_watch"] == []


def test_late_watch_is_excluded():
    late = _vcp_result("LATE", "READY", late_watch=True)
    assert project_daily_vcp_watchlist([late])["action_review"] == []


def test_breakout_watch_is_watch_only_and_not_actionable():
    bw = _vcp_result("BW", "BREAKOUT_WATCH")
    out = project_daily_vcp_watchlist([bw])
    assert len(out["breakout_watch"]) == 1
    assert out["breakout_watch"][0]["symbol"] == "BW"
    assert out["action_review"] == []
    assert out["near_trigger"] == []


def test_action_review_requires_close_trigger_coherent():
    # READY is pre-breakout, so close_confirmed=False is allowed.
    ready = _vcp_result("RNC", "READY", breakout={"close_confirmed": False})
    assert project_daily_vcp_watchlist([ready])["action_review"][0]["symbol"] == "RNC"
    # CONFIRMED must actually have close_confirmed and close >= pivot.
    confirmed_no_close = _vcp_result("CNC", "CONFIRMED", breakout={"close_confirmed": False})
    assert project_daily_vcp_watchlist([confirmed_no_close])["action_review"] == []
    # Close below invalidation is incoherent regardless of state.
    below_stop = _vcp_result("BS", "READY", price={"last_close": 45.0, "pivot_high": 50.0, "invalidation": 48.0, "distance_to_pivot_pct": -10.0})
    assert project_daily_vcp_watchlist([below_stop])["action_review"] == []


def test_caps_limit_each_lane():
    action = [_vcp_result(f"A{i:02d}", "READY", data={"daily_metrics": {"avg_trade_value_20": 30_000_000 - i * 1_000_000}}) for i in range(15)]
    near = [_vcp_result(f"N{i:02d}", "NEAR_TRIGGER", data={"daily_metrics": {"avg_trade_value_20": 30_000_000 - i * 1_000_000}}) for i in range(15)]
    watch = [_vcp_result(f"W{i:02d}", "BREAKOUT_WATCH", data={"daily_metrics": {"avg_trade_value_20": 30_000_000 - i * 1_000_000}}) for i in range(8)]
    out = project_daily_vcp_watchlist(action + near + watch)
    assert len(out["action_review"]) <= 10
    assert len(out["near_trigger"]) <= 10
    assert len(out["breakout_watch"]) <= 5


def test_ranking_orders_by_quality_not_percent_change():
    low_change_high_quality = _vcp_result("GOOD", "READY", price={"last_close": 51.0, "pivot_high": 50.0, "invalidation": 48.0, "distance_to_pivot_pct": 2.0, "change_pct": 0.5}, data={"daily_metrics": {"avg_trade_value_20": 50_000_000}})
    high_change_low_quality = _vcp_result("HYPE", "READY", evidence={"price_contraction_pass": False}, price={"last_close": 55.0, "pivot_high": 50.0, "invalidation": 48.0, "distance_to_pivot_pct": 10.0, "change_pct": 8.0}, data={"daily_metrics": {"avg_trade_value_20": 50_000_000}})
    out = project_daily_vcp_watchlist([high_change_low_quality, low_change_high_quality])
    assert [r["symbol"] for r in out["action_review"]] == ["GOOD"]


def test_no_cross_lane_duplicate_symbols():
    ready = _vcp_result("DUPE", "READY")
    watch = _vcp_result("DUPE", "BREAKOUT_WATCH")
    out = project_daily_vcp_watchlist([watch, ready])
    assert [r["symbol"] for r in out["action_review"]] == ["DUPE"]
    assert [r["symbol"] for r in out["breakout_watch"]] == []


def test_empty_results_are_safe():
    out = project_daily_vcp_watchlist([])
    assert out["counts"] == {"ACTION_REVIEW": 0, "NEAR_TRIGGER": 0, "BREAKOUT_WATCH": 0}
    assert out["action_review"] == []
    assert out["near_trigger"] == []
    assert out["breakout_watch"] == []
