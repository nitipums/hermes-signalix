import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from vcp_finder_db import (
    _classify_types,
    _daily_context_from_rows,
    _daily_metrics_from_rows,
    _apply_52_week_presentation,
    _presentation_fields,
    find_vcp_universe_60m,
    load_52_week_context,
    load_latest_vcp_run,
    persist_vcp_run,
    resolve_serving_universe,
    validate_vcp_run_provenance,
)


def test_serving_universe_defaults_to_marginable_long_and_reports_manifest(monkeypatch):
    monkeypatch.setattr("vcp_finder_db.active_ord_symbols", lambda _: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(
        "vcp_finder_db.eligible_symbols",
        lambda symbols, mode: (["AAA", "CCC"], {
            "universe_filter": mode, "base_active_ord_count": 3,
            "eligible_count": 2, "excluded_count": 1,
            "schema_version": "signalix.marginable.v1",
            "source_document": "margin.pdf", "effective_date": "2026-08-25",
        }),
    )
    symbols, manifest = resolve_serving_universe(object())
    assert symbols == ["AAA", "CCC"]
    assert manifest["universe_filter"] == "marginable_long"
    assert manifest["eligible_count"] == 2
    assert manifest["excluded_count"] == 1


def test_serving_universe_supports_explicit_active_ord_and_fails_closed(monkeypatch):
    monkeypatch.setattr("vcp_finder_db.active_ord_symbols", lambda _: ["BBB", "AAA"])
    symbols, manifest = resolve_serving_universe(object(), universe="active_ord")
    assert symbols == ["AAA", "BBB"]
    assert manifest["universe_filter"] == "active_ord"
    assert manifest["eligible_count"] == 2
    with pytest.raises(ValueError, match="unknown universe"):
        resolve_serving_universe(object(), universe="everything")


def test_v2_shadow_projection_preserves_raw_v1_evidence():
    result = {
        "symbol": "AAA", "state": "READY", "policy_version": "finder-v1",
        "evidence": {"prior_trend_pass": True, "price_contraction_pass": True,
                     "base_pass": True, "leg_volume_pass": True},
        "price": {"last_close": 10, "pivot_high": 10, "invalidation": 9,
                   "distance_to_pivot_pct": 0},
        "breakout": {"close_confirmed": True, "volume_confirmed": True},
        "data": {"freshness": "fresh", "feed_status": "ok",
                 "daily_metrics": {"avg_trade_value_20": 20_000_000}},
        "marginable": {"is_marginable": True},
    }
    from vcp_finder_db import _attach_decision_shadow_v2
    out = _attach_decision_shadow_v2(result)
    assert out["source_policy_version"] == "finder-v1"
    assert out["policy_version"] == "finder-v1"
    assert out["decision_policy_version"] == "signalix/vcp-decision-shadow-v2"
    assert out["evidence"] == result["evidence"]
    assert out["decision_shadow_v2"]["policy_version"] == "signalix/vcp-decision-shadow-v2"
    assert out["decision_lane"] == out["decision_shadow_v2"]["decision_lane"]
    assert out["actionability"] == out["decision_shadow_v2"]["actionability"]


@pytest.mark.parametrize(
    ("provenance", "expected"),
    [
        ({"ingestion_run_id": None, "ingestion_status": "full_success", "fetch_completed_at": "2026-08-29T09:00:00+00:00"}, "missing_ingestion_run_id"),
        ({"ingestion_run_id": "i1", "ingestion_status": "unknown", "fetch_completed_at": "2026-08-29T09:00:00+00:00"}, "invalid_ingestion_status"),
        ({"ingestion_run_id": "i1", "ingestion_status": "full_success", "fetch_completed_at": "not-a-timestamp"}, "invalid_fetch_completed_at"),
    ],
)
def test_vcp_provenance_validation_is_fail_closed(provenance, expected):
    assert validate_vcp_run_provenance(**provenance) == expected


@pytest.mark.parametrize("status", ["full_success", "partial_success"])
def test_vcp_provenance_accepts_complete_ingestion(status):
    assert validate_vcp_run_provenance(
        ingestion_run_id="ingest-1",
        ingestion_status=status,
        fetch_completed_at="2026-08-29T09:00:00+00:00",
    ) is None


def test_persist_vcp_run_rejects_incomplete_provenance_before_db_write():
    pg = MagicMock()
    with pytest.raises(ValueError, match="incomplete provenance"):
        persist_vcp_run(pg, {
            "run_id": "vcp-1", "market": "TH", "interval": "60m",
            "policy_version": "v1", "as_of": "2026-08-29T09:00:00+00:00",
            "universe": {"eligible": 1, "evaluated": 1}, "results": [],
        })
    pg.cursor.assert_not_called()


@pytest.mark.parametrize(
    ("state", "expected_decision"),
    [
        ("FORMING", "WAIT"),
        ("READY", "WAIT"),
        ("NEAR_TRIGGER", "WAIT"),
        ("BREAKOUT_WATCH", "WAIT"),
        ("CONFIRMED", "REVIEW"),
        ("EXTENDED", "WAIT"),
        ("FAILED", "AVOID"),
        ("STALE", None),
        ("NOT_VERIFIED", None),
    ],
)
def test_presentation_attaches_decision_without_changing_raw_vcp_fields(state, expected_decision):
    raw_fields = {
        "state": state,
        "actionable": state in {"READY", "NEAR_TRIGGER", "CONFIRMED"},
        "review_lane": "PRICE_VOLUME_BREAKOUT",
        "pattern": {"base_depth_pct": 8.0, "pivots": [{"kind": "high"}]},
        "breakout": {"close_confirmed": state == "CONFIRMED", "volume_confirmed": True},
        "provenance": {"run_id": "run-1", "source": "vcp_finder_60m"},
        "daily_context_watch": True,
        "insurance_context_watch": False,
        "last_watch_event": {"state": "BREAKOUT_WATCH"},
        "late_watch": False,
        "index_membership": ["SET50"],
        "rr": 2.5,
    }
    result = {
        **raw_fields,
        "data": {"freshness": "fresh", "feed_status": "ok"},
        "trend": {"daily_context": {"trend_pass": True, "as_of": "2026-08-29"}},
        "evidence": {
            "prior_trend_pass": True,
            "price_contraction_pass": True,
            "base_pass": True,
            "leg_volume_pass": True,
        },
        "price": {"pivot_high": 10.0, "invalidation": 9.0, "distance_to_pivot_pct": 0.0},
    }

    out = _presentation_fields(result)

    for key, value in raw_fields.items():
        assert out[key] == value
    assert out["decision"]["decision"] == expected_decision
    assert out["decision"]["evidence"]["daily_context"] == result["trend"]["daily_context"]
    json.dumps(out["decision"], allow_nan=False)


def test_one_symbol_unified_decision_cannot_be_overridden_by_legacy_fields():
    result = {
        "symbol": "AAA",
        "state": "READY",
        "actionable": False,
        "trade_readiness": {"status": "BREAK", "stop_loss": 1.0},
        "daily_state": {"primary_state": "broken"},
        "setup_proximity": {"state": "extended"},
        "action_queue": "avoid_chase",
        "shortlist_lane": "CAUTION",
        "data": {"freshness": "fresh", "feed_status": "ok"},
        "trend": {"daily_context": {"trend_pass": True}},
        "evidence": {
            "prior_trend_pass": True,
            "price_contraction_pass": True,
            "base_pass": True,
            "leg_volume_pass": True,
        },
        "price": {"pivot_high": 10.0, "invalidation": 9.0},
    }

    out = _presentation_fields(result)

    assert out["decision"] == {
        "state": "READY",
        "decision": "WAIT",
        "quality": "PASS",
        "data_sufficient": True,
        "evidence": {
            "timeframe": "60m",
            "trigger": 10.0,
            "invalidation": 9.0,
            "distance_to_trigger_pct": None,
            "volume_confirmation": None,
            "daily_context": {"trend_pass": True},
        },
    }
    assert out["actionable"] is False
    assert out["trade_readiness"]["status"] == "BREAK"
    assert out["daily_state"]["primary_state"] == "broken"
    assert out["setup_proximity"]["state"] == "extended"
    assert out["action_queue"] == "avoid_chase"
    assert out["shortlist_lane"] == "CAUTION"


def test_task5_vcp_call_site_inventory_and_legacy_ruling():
    """Record the Task 5 serving boundary and retained rollback/audit paths.

    Visible VCP MVP serving is vcp_finder_db._presentation_fields ->
    project_unified_vcp_decision, and the VCP frontend consumes ``decision``.
    The legacy consumers in app.py, screening.py, daily_shortlist.py, and
    build_dashboard.py are compatibility/retired Daily paths. They remain
    available for rollback and audit and must not be deleted or refactored as
    part of this VCP boundary change.
    """
    from pathlib import Path

    backend = Path(__file__).parent
    vcp_db = (backend / "vcp_finder_db.py").read_text(encoding="utf-8")
    frontend = (backend / "frontend" / "app.js").read_text(encoding="utf-8")

    assert "def _presentation_fields(result):" in vcp_db
    assert "return _attach_unified_decision(result)" in vcp_db
    assert "result[\"decision\"] = project_unified_vcp_decision" in vcp_db
    assert "decision" in frontend

    retained_legacy = {
        "app.py": ("trade_readiness", "classify_daily_state", "setup_proximity"),
        "screening.py": ("trade_readiness", "classify_daily_state", "classify_stage"),
        "daily_shortlist.py": ("setup_proximity", "action_queue", "shortlist_lane"),
        "build_dashboard.py": ("trade_readiness", "setup_proximity", "assign_action_queue", "action_queue"),
    }
    for filename, markers in retained_legacy.items():
        source = (backend / filename).read_text(encoding="utf-8")
        assert all(marker in source for marker in markers), filename


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
            if "SELECT symbol FROM vcp_finder_60m_results" in self.sql[-1]:
                return [{"symbol": "READY1"}, {"symbol": "FORMING1"}]
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
    monkeypatch.setattr("vcp_finder_db.active_ord_symbols", lambda _: ["READY1", "FORMING1"])

    out = load_latest_vcp_run(Conn(), market="TH", daily_watchlist=True, universe="active_ord")

    assert enriched_symbols == ["READY1"]
    assert out["universe"] == {
        "eligible": 2, "evaluated": 2, "returned": 2,
        "missing_from_run": 0, "missing_symbols": [],
    }
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
            if "SELECT symbol FROM vcp_finder_60m_results" in sql: return [{"symbol": "KCE"}]
            if "vcp_finder_60m_results" in sql: return [{"result": row}]
            if "index_memberships" in sql: return [{"symbol": "KCE", "index_name": "SET50"}, {"symbol": "KCE", "index_name": "SET100"}]
            return []
        def close(self): pass
    class Conn:
        def __init__(self): self.cur = Cursor()
        def cursor(self, **kwargs): return self.cur

    monkeypatch.setattr("vcp_finder_db.load_52_week_context", lambda *args, **kwargs: {})
    monkeypatch.setattr("marginable.lookup", lambda symbol: {
        "instrument_type": "ORD", "margin_rate_pct": 50, "marker": "**",
        "can_buy": True, "can_add_collateral": True, "can_short": False,
    })
    monkeypatch.setattr("vcp_finder_db.active_ord_symbols", lambda _: ["KCE"])
    out = load_latest_vcp_run(Conn())
    assert out["results"][0]["index_membership"] == ["SET50", "SET100"]
    margin = out["results"][0]["marginable"]
    assert margin == {
        "is_marginable": True, "instrument_type": "ORD", "margin_rate_pct": 50,
        "marker": "**", "can_buy": True, "can_add_collateral": True,
        "can_short": False, "schema_version": "signalix.marginable.v1",
        "source_document": "Marginable_Securities_List_25082026_1787658633_copy.pdf",
        "effective_date": "2026-08-25",
        "source": "Krungsri Securities Credit Balance Marginable Securities List",
    }


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
            if "SELECT symbol FROM vcp_finder_60m_results" in sql: return [{"symbol": "KCE"}]
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
    monkeypatch.setattr("vcp_finder_db.active_ord_symbols", lambda _: ["KCE"])
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
            if "SELECT symbol FROM vcp_finder_60m_results" in sql: return [{"symbol": "HANA"}]
            if "vcp_finder_60m_results" in sql: return [{"result": row}]
            return []
        def close(self): pass
    class Conn:
        def __init__(self): self.cur = Cursor()
        def cursor(self, **kwargs): return self.cur

    monkeypatch.setattr("vcp_finder_db.load_52_week_context", lambda *args, **kwargs: {})
    monkeypatch.setattr("marginable.lookup", lambda symbol: None)
    monkeypatch.setattr("vcp_finder_db.active_ord_symbols", lambda _: ["HANA"])
    out = load_latest_vcp_run(Conn())
    assert out["results"][0].get("rr") is None


@pytest.mark.parametrize("run_row_count", [237, 236])
def test_latest_vcp_run_reports_observed_rows_and_missing_selected_coverage(monkeypatch, run_row_count):
    as_of = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
    selected = [f"S{index:03d}" for index in range(237)]
    present = selected[:run_row_count]

    class Cursor:
        def __init__(self):
            self.sql = ""

        def execute(self, sql, params):
            self.sql = sql

        def fetchone(self):
            if "SELECT run_id" in self.sql:
                return {
                    "run_id": "run-coverage", "market": "TH", "interval": "60m",
                    "policy_version": "finder-v1", "as_of": as_of,
                    "eligible_count": 237, "evaluated_count": run_row_count,
                    "ingestion_run_id": "i1", "ingestion_status": "full_success",
                    "fetch_completed_at": as_of,
                }
            return {"feed_unavailable": 0, "no_data": 0}

        def fetchall(self):
            if "SELECT symbol FROM vcp_finder_60m_results" in self.sql:
                return [{"symbol": symbol} for symbol in present]
            if "SELECT result FROM vcp_finder_60m_results" in self.sql:
                return [{"result": {"symbol": symbol, "state": "FORMING", "data": {}}}
                        for symbol in present]
            return []

        def close(self):
            pass

    class Conn:
        def __init__(self):
            self.cur = Cursor()

        def cursor(self, **kwargs):
            return self.cur

    monkeypatch.setattr("vcp_finder_db.active_ord_symbols", lambda _: selected)
    monkeypatch.setattr("vcp_finder_db.load_52_week_context", lambda *args, **kwargs: {})
    monkeypatch.setattr("marginable.lookup", lambda symbol: None)

    out = load_latest_vcp_run(Conn(), universe="active_ord")
    assert out["universe"]["eligible"] == 237
    assert out["universe"]["evaluated"] == run_row_count
    assert out["universe"]["returned"] == run_row_count
    assert out["universe"]["missing_from_run"] == 237 - run_row_count
    assert out["universe"]["missing_symbols"] == selected[run_row_count:]


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
