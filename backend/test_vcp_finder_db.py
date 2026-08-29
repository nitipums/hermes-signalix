from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

from vcp_finder_db import (
    _classify_types,
    _daily_context_from_rows,
    _daily_metrics_from_rows,
    _apply_52_week_presentation,
    find_vcp_universe_60m,
    load_52_week_context,
    load_latest_vcp_run,
)


def test_type_classification_is_separate_and_deterministic():
    result = {"state": "READY", "price": {"last_close": 100, "pivot_high": 98, "distance_to_pivot_pct": 0.5, "invalidation": 95, "atr14": 2}, "pattern": {"pivots": [{"kind": kind} for kind in ("high", "low", "high", "low", "high")], "base_depth_pct": 10, "latest_contraction_pct": 5}, "evidence": {"prior_trend_pass": True, "price_contraction_pass": True, "base_pass": True, "leg_volume_pass": True}}
    out = _classify_types(result, ath_context={"observed_ath_all_time": 99}, listing_context=None)
    assert out["vcp_type"]["base_type"] == "low_cheat_vcp"
    assert out["vcp_type"]["entry_profile"] == "early_entry"
    assert out["vcp_type"]["overlays"] == ["break_ath"]
    assert out["state"] == "READY"


def test_new_stock_requires_listing_evidence():
    result = {"state": "FORMING", "price": {"last_close": 10}, "pattern": {}, "evidence": {}}
    out = _classify_types(result, ath_context={}, listing_context=None)
    assert "new_stock" not in out["vcp_type"]["types"]


def test_low_cheat_requires_non_failed_early_entry_state():
    result = {
        "state": "FAILED",
        "price": {"last_close": 100, "pivot_high": 98, "distance_to_pivot_pct": 0.5, "invalidation": 95, "atr14": 2},
        "pattern": {"pivots": [{"kind": kind} for kind in ("high", "low", "high", "low", "high")], "base_depth_pct": 10, "latest_contraction_pct": 5},
        "evidence": {"prior_trend_pass": True, "price_contraction_pass": True, "base_pass": True, "leg_volume_pass": True},
    }

    out = _classify_types(result, ath_context={"observed_ath_all_time": 99}, listing_context=None)

    assert out["vcp_type"]["base_type"] == "standard_vcp"
    assert out["vcp_type"]["entry_profile"] == "standard_entry"
    assert out["state"] == "FAILED"


def test_low_cheat_requires_healthy_trend_and_tight_risk():
    result = {
        "state": "READY",
        "price": {"last_close": 100, "pivot_high": 99, "distance_to_pivot_pct": 0.5, "invalidation": 80, "atr14": 2},
        "pattern": {"pivots": [{"kind": kind} for kind in ("high", "low", "high", "low", "high")], "base_depth_pct": 10, "latest_contraction_pct": 5},
        "evidence": {"prior_trend_pass": False, "price_contraction_pass": True, "base_pass": True, "leg_volume_pass": True},
    }

    out = _classify_types(result, ath_context={}, listing_context=None)

    assert out["vcp_type"]["base_type"] is None
    assert out["vcp_type"]["type_evidence"]["healthy_trend_60m"] is False
    assert out["vcp_type"]["type_evidence"]["tight_risk_pass"] is False



def test_universe_keeps_missing_and_insufficient_symbols(monkeypatch):
    pg = MagicMock()
    monkeypatch.setattr("vcp_finder_db.active_ord_symbols", lambda _: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr("vcp_finder_db.load_vcp_60m_rows", lambda *_args, **_kwargs: {
        "AAA": [], "BBB": [], "CCC": []
    })
    result = find_vcp_universe_60m(pg)
    assert result["universe"] == {"eligible": 3, "evaluated": 3, "returned": 3}
    assert [x["symbol"] for x in result["results"]] == ["AAA", "BBB", "CCC"]
    assert all(x["state"] == "NOT_VERIFIED" for x in result["results"])
    assert all(x["provenance"]["legacy_scanner_used"] is False for x in result["results"])
    assert all("vcp_type" in x for x in result["results"])
    assert all("type_policy_version" in x["vcp_type"] for x in result["results"])


def test_daily_watchlist_loads_full_run_but_enriches_only_lane_states(monkeypatch):
    run_as_of = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
    ready = {
        "symbol": "READY1",
        "state": "READY",
        "evidence": {
            "prior_trend_pass": True,
            "price_contraction_pass": True,
            "base_pass": True,
            "leg_volume_pass": True,
        },
        "price": {"last_close": 98.0, "pivot_high": 100.0, "invalidation": 95.0},
        "breakout": {"pivot_level": 100.0, "close_confirmed": False},
        "trend": {"daily_context_pass": True},
        "data": {
            "freshness": "fresh",
            "feed_status": "ok",
            "daily_metrics": {"avg_trade_value_20": 20_000_000},
            "freshness_session_age": 0,
        },
    }
    rejected = {
        "symbol": "FORMING1",
        "state": "FORMING",
        "evidence": {},
        "price": {"last_close": 50.0},
        "data": {},
    }

    class Cursor:
        def __init__(self):
            self.sql = []

        def execute(self, sql, params):
            self.sql.append(sql)

        def fetchone(self):
            if "SELECT run_id" in self.sql[-1]:
                return {
                    "run_id": "run-large",
                    "market": "TH",
                    "interval": "60m",
                    "policy_version": "policy-v1",
                    "as_of": run_as_of,
                    "eligible_count": 2,
                    "evaluated_count": 2,
                    "ingestion_run_id": "ingest-1",
                    "ingestion_status": "full_success",
                    "fetch_completed_at": run_as_of,
                }
            return {"feed_unavailable": 0, "no_data": 0}

        def fetchall(self):
            if "SELECT result FROM vcp_finder_60m_results" in self.sql[-1]:
                return [{"result": ready}, {"result": rejected}]
            return []

        def close(self):
            pass

    class Conn:
        def __init__(self):
            self.cur = Cursor()

        def cursor(self, **kwargs):
            return self.cur

    enriched_symbols = []

    def fake_52_week_context(pg, symbols, as_of=None):
        enriched_symbols.extend(symbols)
        return {}

    monkeypatch.setattr("vcp_finder_db.load_52_week_context", fake_52_week_context)
    monkeypatch.setattr("marginable.lookup", lambda symbol: None)

    out = load_latest_vcp_run(Conn(), market="TH", daily_watchlist=True)

    assert enriched_symbols == ["READY1"]
    assert out["universe"] == {"eligible": 2, "evaluated": 2, "returned": 2}
    assert out["daily_watchlist"]["coverage"]["input"] == 2
    assert out["daily_watchlist"]["coverage"]["rejection_counts"] == {
        "state_not_watchlist_eligible": 1,
    }


def test_latest_vcp_run_attaches_as_of_index_membership_to_vcp_rows(monkeypatch):
    as_of = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
    row = {"symbol": "KCE", "state": "READY", "price": {"last_close": 10}}

    class Cursor:
        def __init__(self): self.sql = []
        def execute(self, sql, params): self.sql.append(sql)
        def fetchone(self):
            if "SELECT run_id" in self.sql[-1]:
                return {"run_id": "run-1", "market": "TH", "interval": "60m", "policy_version": "v1",
                        "as_of": as_of, "eligible_count": 1, "evaluated_count": 1,
                        "ingestion_run_id": "i1", "ingestion_status": "full_success", "fetch_completed_at": as_of}
            return {"feed_unavailable": 0, "no_data": 0}
        def fetchall(self):
            sql = self.sql[-1]
            if "daily_scan_observations" in sql or "company_profiles" in sql or "DISTINCT ON" in sql: return []
            if "vcp_finder_60m_results" in sql: return [{"result": row}]
            if "index_memberships" in sql: return [{"symbol": "KCE", "index_name": "SET50"}, {"symbol": "KCE", "index_name": "SET100"}]
            return []
        def close(self): pass
    class Conn:
        def __init__(self): self.cur = Cursor()
        def cursor(self, **kwargs): return self.cur

    monkeypatch.setattr("vcp_finder_db.load_52_week_context", lambda *args, **kwargs: {})
    monkeypatch.setattr("marginable.lookup", lambda symbol: None)
    out = load_latest_vcp_run(Conn())
    assert out["results"][0]["index_membership"] == ["SET50", "SET100"]


def test_latest_vcp_run_enriches_missing_rr_from_canonical_daily_payload(monkeypatch):
    as_of = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
    row = {"symbol": "KCE", "state": "READY", "price": {"last_close": 100, "invalidation": 95}}

    class Cursor:
        def __init__(self): self.sql = []
        def execute(self, sql, params): self.sql.append(sql)
        def fetchone(self):
            if "SELECT run_id" in self.sql[-1]:
                return {"run_id": "run-rr", "market": "TH", "interval": "60m", "policy_version": "v1",
                        "as_of": as_of, "eligible_count": 1, "evaluated_count": 1,
                        "ingestion_run_id": "i1", "ingestion_status": "full_success", "fetch_completed_at": as_of}
            return {"feed_unavailable": 0, "no_data": 0}
        def fetchall(self):
            sql = self.sql[-1]
            if "x.result" in sql: return []
            if "vcp_finder_60m_results" in sql: return [{"result": row}]
            if "daily_scan_observations" in sql:
                return [{"symbol": "KCE", "raw_payload": {
                    "close": 100,
                    "trade_readiness": {"stop_loss": 95, "targets": {"161": 115}},
                }}]
            return []
        def close(self): pass
    class Conn:
        def __init__(self): self.cur = Cursor()
        def cursor(self, **kwargs): return self.cur

    monkeypatch.setattr("vcp_finder_db.load_52_week_context", lambda *args, **kwargs: {})
    monkeypatch.setattr("marginable.lookup", lambda symbol: None)
    out = load_latest_vcp_run(Conn())
    assert out["results"][0]["rr"] == 3.0


def test_latest_vcp_run_keeps_missing_rr_neutral_without_canonical_value(monkeypatch):
    as_of = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
    row = {"symbol": "HANA", "state": "READY", "price": {"last_close": 100, "invalidation": 95}}

    class Cursor:
        def __init__(self): self.sql = []
        def execute(self, sql, params): self.sql.append(sql)
        def fetchone(self):
            if "SELECT run_id" in self.sql[-1]:
                return {"run_id": "run-none", "market": "TH", "interval": "60m", "policy_version": "v1",
                        "as_of": as_of, "eligible_count": 1, "evaluated_count": 1,
                        "ingestion_run_id": "i1", "ingestion_status": "full_success", "fetch_completed_at": as_of}
            return {"feed_unavailable": 0, "no_data": 0}
        def fetchall(self):
            sql = self.sql[-1]
            if "x.result" in sql: return []
            if "vcp_finder_60m_results" in sql: return [{"result": row}]
            return []
        def close(self): pass
    class Conn:
        def __init__(self): self.cur = Cursor()
        def cursor(self, **kwargs): return self.cur

    monkeypatch.setattr("vcp_finder_db.load_52_week_context", lambda *args, **kwargs: {})
    monkeypatch.setattr("marginable.lookup", lambda symbol: None)
    out = load_latest_vcp_run(Conn())
    assert out["results"][0].get("rr") is None


def test_52_week_context_is_point_in_time_and_uses_price_data():
    class Cursor:
        sql = ""
        params = None
        def execute(self, sql, params):
            self.sql, self.params = sql, params
        def fetchall(self):
            return [{"symbol": "AAA", "high52": 110, "low52": 80, "bars": 252}]
        def close(self): pass
    class Conn:
        def __init__(self): self.cursor_obj = Cursor()
        def cursor(self, **kwargs): return self.cursor_obj

    pg = Conn()
    out = load_52_week_context(pg, ["AAA"], as_of=date(2026, 8, 29))
    assert out["AAA"]["high52"] == 110.0
    assert out["AAA"]["low52"] == 80.0
    assert "date <= %s" in pg.cursor_obj.sql
    assert "CROSS JOIN LATERAL" in pg.cursor_obj.sql
    assert "ROW_NUMBER()" not in pg.cursor_obj.sql
    assert pg.cursor_obj.params[1] == date(2026, 8, 29)


def test_52_week_context_bounds_each_symbol_lookup():
    class Cursor:
        sql = ""
        params = None

        def execute(self, sql, params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return []

        def close(self):
            pass

    class Conn:
        def __init__(self):
            self.cursor_obj = Cursor()

        def cursor(self, **kwargs):
            return self.cursor_obj

    pg = Conn()
    load_52_week_context(pg, ["AAA", "BBB"], lookback=252)

    assert "FROM unnest(%s::text[]) AS requested(symbol)" in pg.cursor_obj.sql
    assert "LIMIT %s" in pg.cursor_obj.sql
    assert pg.cursor_obj.params == (["AAA", "BBB"], 252)


def test_universe_adds_high52_proximity_without_changing_state(monkeypatch):
    pg = MagicMock()
    monkeypatch.setattr("vcp_finder_db.active_ord_symbols", lambda _: ["AAA"])
    monkeypatch.setattr("vcp_finder_db.load_vcp_60m_rows", lambda *_args, **_kwargs: {"AAA": []})
    monkeypatch.setattr("vcp_finder_db.load_52_week_context", lambda *_args, **_kwargs: {"AAA": {"high52": 110.0, "low52": 80.0}})
    result = find_vcp_universe_60m(pg)
    row = result["results"][0]
    assert row["state"] == "NOT_VERIFIED"
    assert row["price"]["high52"] == 110.0
    assert row["price"]["distance_to_52w_high_pct"] is None
    assert "near_52w_high" not in row["vcp_type"]["overlays"]


def test_52_week_proximity_is_presentation_only():
    result = {"state": "EXTENDED", "price": {"last_close": 100.0}, "vcp_type": {"overlays": [], "types": []}}
    out = _apply_52_week_presentation(result, {"high52": 105.0, "low52": 70.0})
    assert out["state"] == "EXTENDED"
    assert out["price"]["distance_to_52w_high_pct"] == (100 / 105 - 1) * 100
    assert "near_52w_high" in out["vcp_type"]["overlays"]


def test_daily_metrics_latest_close_is_newest_independent_of_input_order():
    rows = [
        {"date": date(2026, 8, 27), "close": 47.0, "volume": 10},
        {"date": date(2026, 8, 25), "close": 45.5, "volume": 20},
        {"date": date(2026, 8, 26), "close": 46.0, "volume": 30},
    ]

    out = _daily_metrics_from_rows([rows[1], rows[0], rows[2]])

    assert out["latest_daily_close"] == 47.0
    assert out["as_of"] == "2026-08-27"
    assert out["avg_trade_value_20"] == (45.5 * 20 + 47.0 * 10 + 46.0 * 30) / 3
    assert out["bars"] == 3


def test_daily_context_is_chronological_independent_of_input_order():
    start = date(2026, 6, 1)
    rows = [
        {"date": start + timedelta(days=i), "close": float(100 + i)}
        for i in range(40)
    ]

    out = _daily_context_from_rows(rows[::2] + rows[1::2])

    assert out["as_of"] == str(start + timedelta(days=39))
    assert out["bars"] == 40
    assert out["return_20d_pct"] == (139.0 / 119.0 - 1) * 100
    assert out["recent_avg_20"] == sum(range(120, 140)) / 20
    assert out["prior_avg_20"] == sum(range(100, 120)) / 20
    assert out["trend_pass"] is True
