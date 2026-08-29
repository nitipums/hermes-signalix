import json

import mvp_routes
from vcp_finder_db import daily_watchlist_query_states, load_latest_vcp_run, project_daily_vcp_watchlist


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


def test_vcp_route_hides_internal_failure_details(monkeypatch):
    class Conn:
        def close(self): pass
    monkeypatch.setattr(mvp_routes, "_vcp_pg", lambda: Conn())
    def fail(*args, **kwargs):
        raise RuntimeError("password=should-not-leak")
    monkeypatch.setattr("vcp_finder_db.load_latest_vcp_run", fail)
    h = Handler()
    assert mvp_routes.handle_mvp_api("/api/vcp-finder", h) is True
    body = json.loads(h.body)
    assert h.status == 503
    assert body == {"error": "vcp_finder_unavailable"}


def test_latest_run_query_requires_successful_completed_ingestion():
    class Cursor:
        def __init__(self):
            self.sql = ""
        def execute(self, sql, params):
            self.sql = sql
        def fetchone(self):
            return None
        def close(self): pass
    class Conn:
        def __init__(self): self.cur = Cursor()
        def cursor(self, **kwargs): return self.cur
    pg = Conn()
    assert load_latest_vcp_run(pg) is None
    assert "ingestion_status = 'full_success'" in pg.cur.sql
    assert "fetch_completed_at IS NOT NULL" in pg.cur.sql


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


def test_daily_watchlist_response_does_not_serialize_full_vcp_results(monkeypatch):
    payload = {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "run_id": "run-large",
        "universe": {"eligible": 931, "evaluated": 931, "returned": 931},
        "coverage": {"feed_unavailable": 19, "no_data": 16},
        "results": [{"symbol": "A"}] * 931,
        "daily_watchlist": {
            "policy_version": "signalix/daily-vcp-watchlist-v1",
            "caps": {"ACTION_REVIEW": 10, "NEAR_TRIGGER": 10, "BREAKOUT_WATCH": 5},
            "counts": {"ACTION_REVIEW": 0, "NEAR_TRIGGER": 0, "BREAKOUT_WATCH": 1},
            "action_review": [],
            "near_trigger": [],
            "breakout_watch": [{"symbol": "A"}],
        },
    }

    class Conn:
        def close(self): pass

    monkeypatch.setattr(mvp_routes, "_vcp_pg", lambda: Conn())
    monkeypatch.setattr("vcp_finder_db.load_latest_vcp_run", lambda *args, **kwargs: payload)
    h = Handler()
    assert mvp_routes.handle_mvp_api(
        "/api/vcp-finder?interval=60m&market=TH&daily_watchlist=true", h
    ) is True
    body = json.loads(h.body)
    assert body["universe"] == {"eligible": 931, "evaluated": 931, "returned": 931}
    assert body["results"] == []
    assert len(h.body) < 20_000
    assert body["daily_watchlist"]["breakout_watch"] == [{"symbol": "A"}]


def test_explorer_and_watchlist_share_the_same_unified_decision(monkeypatch):
    result = _vcp_result("AAA", "READY")
    result["decision"] = {
        "state": "READY",
        "decision": "WAIT",
        "quality": "PASS",
        "data_sufficient": True,
        "evidence": {
            "timeframe": "60m",
            "trigger": 50.0,
            "invalidation": 48.0,
            "distance_to_trigger_pct": 4.0,
            "volume_confirmation": False,
            "daily_context": {"trend_pass": True},
        },
    }
    raw_state = result["state"]
    payload = {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "run_id": "run-unified",
        "universe": {"eligible": 2, "evaluated": 2, "returned": 2},
        "coverage": {"feed_unavailable": 0, "no_data": 1},
        "results": [result, {**_vcp_result("MISSING", "NOT_VERIFIED"), "decision": {
            "state": None,
            "decision": None,
            "quality": "UNKNOWN",
            "data_sufficient": False,
            "evidence": {"timeframe": "60m"},
        }}],
        "daily_watchlist": {
            "action_review": [result],
            "near_trigger": [],
            "breakout_watch": [],
        },
    }
    class Conn:
        def close(self): pass

    monkeypatch.setattr(mvp_routes, "_vcp_pg", lambda: Conn())

    def latest(pg, **kwargs):
        return payload

    monkeypatch.setattr("vcp_finder_db.load_latest_vcp_run", latest)

    explorer_handler = Handler()
    assert mvp_routes.handle_mvp_api("/api/vcp-finder?interval=60m", explorer_handler) is True
    explorer = json.loads(explorer_handler.body)
    watchlist_handler = Handler()
    assert mvp_routes.handle_mvp_api(
        "/api/vcp-finder?interval=60m&daily_watchlist=true", watchlist_handler
    ) is True
    watchlist = json.loads(watchlist_handler.body)

    assert explorer["results"][0]["decision"] == watchlist["daily_watchlist"]["action_review"][0]["decision"]
    assert explorer["results"][0]["state"] == raw_state == "READY"
    assert explorer["results"][1]["state"] == "NOT_VERIFIED"
    assert watchlist["universe"] == {"eligible": 2, "evaluated": 2, "returned": 2}


def test_watchlist_caps_and_state_filters_do_not_rewrite_raw_vcp_state(monkeypatch):
    results = [_vcp_result(f"A{i}", "READY") for i in range(12)]
    results.append(_vcp_result("INSUFFICIENT", "NOT_VERIFIED"))
    payload = {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "universe": {"eligible": 13, "evaluated": 13, "returned": 13},
        "coverage": {"feed_unavailable": 0, "no_data": 1},
        "results": results,
        "daily_watchlist": {
            "action_review": results[:10],
            "near_trigger": [],
            "breakout_watch": [],
        },
    }
    class Conn:
        def close(self): pass

    monkeypatch.setattr(mvp_routes, "_vcp_pg", lambda: Conn())
    monkeypatch.setattr("vcp_finder_db.load_latest_vcp_run", lambda *args, **kwargs: payload)
    handler = Handler()
    assert mvp_routes.handle_mvp_api(
        "/api/vcp-finder?interval=60m&daily_watchlist=true&state=FAILED&limit=1",
        handler,
    ) is True
    body = json.loads(handler.body)

    assert body["universe"] == {"eligible": 13, "evaluated": 13, "returned": 13}
    assert len(body["daily_watchlist"]["action_review"]) == 10
    assert all(row["state"] == "READY" for row in body["daily_watchlist"]["action_review"])
    assert body["coverage"]["no_data"] == 1
    assert payload["results"][-1]["state"] == "NOT_VERIFIED"


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


def test_daily_watchlist_query_only_needs_lane_eligible_states():
    assert daily_watchlist_query_states() == {
        "READY", "NEAR_TRIGGER", "CONFIRMED", "BREAKOUT_WATCH"
    }


def test_empty_results_are_safe():
    out = project_daily_vcp_watchlist([])
    assert out["counts"] == {"ACTION_REVIEW": 0, "NEAR_TRIGGER": 0, "BREAKOUT_WATCH": 0}
    assert out["action_review"] == []
    assert out["near_trigger"] == []
    assert out["breakout_watch"] == []


def test_watchlist_reports_machine_readable_rejection_coverage():
    rejected = [
        _vcp_result("EXT", "EXTENDED"),
        _vcp_result("FORM", "FORMING"),
        _vcp_result("LIQ", "READY", data={"daily_metrics": {"avg_trade_value_20": 1}}),
        _vcp_result("QUAL", "READY", evidence={"base_pass": False}),
    ]
    out = project_daily_vcp_watchlist(rejected)
    assert out["coverage"]["input"] == 4
    assert out["coverage"]["accepted"] == 0
    assert out["coverage"]["rejected"] == 4
    assert out["coverage"]["rejection_counts"] == {
        "state_not_watchlist_eligible": 2,
        "liquidity_below_minimum": 1,
        "structural_quality_gate": 1,
    }
