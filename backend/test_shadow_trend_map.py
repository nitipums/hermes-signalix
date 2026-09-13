import json
from pathlib import Path

import pytest

import shadow_trend_map as subject


def bars(count=45, *, invalid=False):
    rows = []
    for i in range(count):
        close = 100 + i
        rows.append({"date": f"2026-01-{(i % 28) + 1:02d}", "open": close - 1,
                     "high": close + 1, "low": close - 2, "close": close, "volume": 1000})
    if invalid:
        rows[0]["low"] = "bad"
    return rows


def test_policy_window_and_prior_support_excludes_current():
    result = subject.evaluate_symbol("AAA", bars(400), "2026-09-11")
    assert result["bars_used"] == 400
    assert result["support"]["excluded_current_bar"] is True
    assert result["support"]["prior_bars"] == 10


def test_retrieval_cap_fails_closed_when_it_cannot_establish_full_valid_window():
    result = subject.evaluate_symbol("AAA", bars(subject.RETRIEVAL_CAP), "2026-09-11", subject.RETRIEVAL_CAP)
    result_frame = bars(subject.RETRIEVAL_CAP)
    for row in result_frame[:31]:
        row["low"] = "bad"
    blocked = subject.evaluate_symbol("AAA", result_frame, "2026-09-11", subject.RETRIEVAL_CAP)
    assert blocked["status"] == "DATA_BLOCKED"
    assert blocked["retrieval_cap_reached"] is True
    assert blocked["bars_used"] == 0
    assert result["bars_used"] == 0
    assert result["data_quality_status"] == "DATA_BLOCKED"


def test_cap_hit_with_no_selected_invalid_rows_is_not_available():
    frame = bars(subject.RETRIEVAL_CAP + 1)
    for i, row in enumerate(frame):
        row["date"] = f"2025-{i // 28 + 1:02d}-{i % 28 + 1:02d}"
    frame[0]["low"] = "bad"
    result = subject.evaluate_symbol("BTS", frame, "2026-09-11")
    assert result["status"] == "DATA_BLOCKED"
    assert result["data_quality_status"] == "DATA_BLOCKED"
    assert result["invalid_row_count"] == 0
    assert result["retrieval_cap"] == subject.RETRIEVAL_CAP
    assert result["cap"] == subject.RETRIEVAL_CAP
    assert result["cap_reached"] is True
    assert result["retrieval_cap_reached"] is True
    assert "cannot establish the required valid/invalid" in result["note"]
    assert "No fallback or full-history retrieval used" in result["note"]


def test_cap_hit_with_established_zero_invalid_quality_is_available():
    frame = bars(subject.RETRIEVAL_CAP + 1)
    for i, row in enumerate(frame):
        row["date"] = f"2025-{i // 28 + 1:02d}-{i % 28 + 1:02d}"
    result = subject.evaluate_symbol(
        "VALID_LONG_HISTORY", frame, "2026-09-11",
        quality_metadata={"quality_scan": "filtered_daily_source", "invalid_count": 0,
                          "quality_established": True, "full_history_claim": False},
    )
    assert result["status"] == "AVAILABLE"
    assert result["cap_reached"] is True
    assert result["quality_established"] is True
    assert result["invalid_count"] == 0
    assert result["full_history_claim"] is False


def test_invalid_row_outside_selected_cap_remains_blocked_from_quality_aggregate():
    frame = bars(subject.RETRIEVAL_CAP + 1)
    for i, row in enumerate(frame):
        row["date"] = f"2025-{i // 28 + 1:02d}-{i % 28 + 1:02d}"
    frame[0]["low"] = "bad"  # older than the selected newest-430 window
    result = subject.evaluate_symbol(
        "BTS", frame, "2026-09-11",
        quality_metadata={"quality_scan": "filtered_daily_source", "invalid_count": 1,
                          "quality_established": True, "full_history_claim": False},
    )
    assert result["status"] == "DATA_BLOCKED"
    assert result["data_quality_status"] == "INVALID_DATA"
    assert result["invalid_count"] == 1
    assert result["invalid_row_count"] == 1


def test_cap_hit_keeps_selected_invalid_rows_visible():
    frame = bars(subject.RETRIEVAL_CAP)
    frame[-1]["low"] = "bad"
    result = subject.evaluate_symbol("CPN", frame, "2026-09-11")
    assert result["status"] == "DATA_BLOCKED"
    assert result["data_quality_status"] == "INVALID_DATA"
    assert result["invalid_row_count"] == 1
    assert result["retrieval_cap_reached"] is True
    assert "invalid filtered-source row" in result["note"]


def test_evaluator_enforces_cap_for_oversized_caller_frame_and_records_selection():
    frame = [{"date": f"2025-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}", "open": 99 + i,
              "high": 101 + i, "low": 98 + i, "close": 100 + i, "volume": 1000}
             for i in range(500)]
    result = subject.evaluate_symbol("AAA", frame, "2026-09-11", retrieval_cap=999)
    assert result["retrieval_cap"] == subject.RETRIEVAL_CAP
    assert result["bars_retrieved"] == subject.RETRIEVAL_CAP
    assert result["bars_used"] == 0
    assert result["status"] == "DATA_BLOCKED"
    assert result["retrieval_cap_reached"] is True
    assert result["retrieval_selection"] == {
        "requested_rows": 500, "selected_rows": subject.RETRIEVAL_CAP,
        "retrieval_cap": subject.RETRIEVAL_CAP, "cap_applied": True,
        "method": "newest_daily_rows", "tie_break": "input_order",
    }


def test_report_policy_has_explicit_quote_representation_revision():
    result = subject._policy()
    assert subject.REPORT_VERSION == "daily-trend-map-shadow-v2-quotes"
    assert subject.REPRESENTATION_REVISION == "quote-envelope-v2"
    assert result["report"] == subject.REPORT_VERSION
    assert result["representation_revision"] == subject.REPRESENTATION_REVISION


def test_report_uses_canonical_production_read_only_envelope():
    class Adapter:
        def resolve_universe(self, conn, value):
            return ["AAA"], {"universe_filter": value}
        def _exec_select(self, conn, sql, params=None):
            return [("2026-09-11",)], ["max_date"]
        def load_daily_pit(self, conn, symbol, as_of):
            return bars(75), as_of
    report = subject.build_shadow_report(Adapter(), object())
    assert report["status"] == subject.PRODUCTION_READ_ONLY
    assert report["research_only"] is False
    assert report["actionability"] == "NONE"


def test_explicit_error_states():
    no_data = subject.evaluate_symbol("A", [], "2026-09-11")
    assert no_data["status"] == "DATA_BLOCKED"
    assert no_data["data_quality_status"] == "NO_DATA"
    assert no_data["quote"]["availability"] == "NOT_VERIFIED"
    short = subject.evaluate_symbol("B", bars(2), "2026-09-11")
    assert short["status"] == "DATA_BLOCKED"
    assert short["data_quality_status"] == "INSUFFICIENT_HISTORY"
    invalid = subject.evaluate_symbol("C", bars(31, invalid=True), "2026-09-11")
    assert invalid["status"] == "DATA_BLOCKED"
    assert invalid["data_quality_status"] == "INVALID_DATA"
    assert invalid["quote"]["availability"] == "NOT_VERIFIED"


def test_quote_is_daily_close_delta_with_positive_negative_and_zero_values():
    for current, previous, expected_amount, expected_pct in ((110, 100, 10, 10), (90, 100, -10, -10), (100, 100, 0, 0)):
        frame = bars(45)
        frame[-2]["close"], frame[-1]["close"] = previous, current
        for row in frame[-2:]:
            row["open"], row["high"], row["low"] = row["close"] - 1, row["close"] + 1, row["close"] - 2
        result = subject.evaluate_symbol("AAA", frame, "2026-09-11")
        quote = result["quote"]
        assert quote["price"] == current
        assert quote["change_amount"] == expected_amount
        assert quote["change_pct"] == expected_pct
        assert quote["change_basis"] == "previous_daily_close"
        assert quote["provenance"]["timeframe"] == "1D"


def test_quote_preserves_price_when_previous_daily_close_is_unavailable():
    frame = [bars(1)[0]]
    result = subject.evaluate_symbol("AAA", frame, "2026-09-11")
    assert result["quote"]["price"] == frame[-1]["close"]
    assert result["quote"]["change_amount"] is None
    assert result["quote"]["change_pct"] is None
    assert result["quote"]["change_availability"] == "NOT_VERIFIED"
    assert result["quote"]["change_basis"] == "NOT_VERIFIED"


def test_valid_classifier_row_is_available_and_has_diagnostic_trace():
    result = subject.evaluate_symbol("AAA", bars(75), "2026-09-11")
    assert result["status"] == "AVAILABLE"
    assert result["classifier_status"] == "AVAILABLE"
    assert result["diagnostic_trace"]["classification"]["machine_lane"] == result["machine_lane"]


def test_report_preserves_canonical_universe_and_as_of():
    class Adapter:
        def resolve_universe(self, conn, value):
            assert value == "marginable_long"
            return ["AAA", "BBB"], {"universe_filter": value, "eligible_count": 2}
        def _exec_select(self, conn, sql, params=None):
            assert sql.startswith("SELECT")
            return [("2026-09-11",)], ["max_date"]
        def load_daily_pit(self, conn, symbol, as_of):
            return (bars(75) if symbol == "AAA" else []), as_of
    report = subject.build_shadow_report(Adapter(), object())
    assert report["as_of"] == "2026-09-11"
    assert [row["symbol"] for row in report["rows"]] == ["AAA", "BBB"]
    assert report["universe"]["scope"] == "marginable_long"
    assert report["policy"]["review_window"] == "current_history_bounded"
    assert report["policy"]["min_valid_bars"] == 30
    assert report["policy"]["max_valid_bars"] == 400
    assert report["policy"]["prior_10d_low"]["prior_bars"] == 10
    assert report["provenance"]["source"] == "price_data+derived_daily_price_data"
    assert report["provenance"]["tables"] == ["price_data", "derived_daily_price_data"]
    assert report["provenance"]["timeframe"] == "1D"
    assert report["provenance"]["query_mode"] == "SELECT_ONLY"
    assert report["provenance"]["point_in_time_filter"] == "date <= as_of"
    assert report["status_by_symbol"] == {"AAA": "AVAILABLE", "BBB": "DATA_BLOCKED"}


def test_report_keeps_every_declared_symbol_and_all_data_quality_reasons():
    class Adapter:
        def resolve_universe(self, conn, value):
            return ["AVAILABLE", "NO_DATA", "INVALID", "SHORT"], {"universe_filter": value}
        def _exec_select(self, conn, sql, params=None):
            return [("2026-09-11",)], ["max_date"]
        def load_daily_pit(self, conn, symbol, as_of):
            if symbol == "AVAILABLE":
                return bars(75), as_of
            if symbol == "INVALID":
                invalid_rows = bars(2)
                for row in invalid_rows:
                    row["low"] = "bad"
                return invalid_rows, as_of
            if symbol == "SHORT":
                return bars(2), as_of
            return [], None

    report = subject.build_shadow_report(Adapter(), object())
    assert set(report["status_by_symbol"]) == {"AVAILABLE", "NO_DATA", "INVALID", "SHORT"}
    assert report["summary"] == {"DATA_BLOCKED": 3, "AVAILABLE": 1}
    assert report["data_quality_summary"]["AVAILABLE"] == 1
    assert report["data_quality_summary"]["NO_DATA"] == 1
    assert report["data_quality_summary"]["INVALID_DATA"] == 1
    assert report["data_quality_summary"]["INSUFFICIENT_HISTORY"] == 1


def test_template_has_lane_grouped_table_filters_drawer_chart_and_shadow_markers():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    shared = Path(__file__).with_name("frontend") / "shared-drawer.js"
    html += shared.read_text()
    for marker in ("<table", "<th>Price</th>", "<th>Change</th>", "<th>% Change</th>", "<th>Daily lane</th>", "quoteValue", "quoteChangePct", "change_amount", "change_pct", "Search symbol", "id=\"lane\"", "id=\"broad-state\"", "All lanes", "All broad states", "setOptions", "laneGroups", "class=\"lane-heading\"", "Machine lane", "row.machine_lane===lane", "!lane||row.machine_lane===lane", "!broad||row.broad_state===broad", "window.SignalixSharedDrawer.openSharedDrawer({", "lane:item.machine_lane", "trend:item.classifier_status", "broad_state:item.broad_state", "source:\"trend-map-shadow\"", "actionability:\"NONE\"", "renderedRows", "/api/trend-map-shadow", "/api/chart-db/", "timeframe=1D", "Chart loading…", "Chart data unavailable", "No chart data available", "DATA_BLOCKED", "machine_lane", "broad_state", "drawChart", "chartRequestSeq"):
        assert marker in html
    assert 'id="status"' not in html
    assert '<th>Status</th>' not in html
    assert '<th>Data quality</th>' not in html
    assert 'r.data_quality_status' not in html
    assert 'r.status===s' not in html


def test_shadow_page_removes_public_research_copy_but_keeps_read_only_source_contract():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    normalized = html.lower()
    for removed in ("permanent public read-only research surface", "no authentication required", "research only", "no financial calculations"):
        assert removed not in normalized
    assert 'source:"trend-map-shadow"' in html
    assert 'actionability:"NONE"' in html
    for forbidden in ("owner-only", "owner decision", "access control", "auth pending", "authentication pending"):
        assert forbidden not in normalized


def test_shadow_table_contract_sorts_quotes_and_navigates_filtered_rendered_rows():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    assert "groups[lane].sort" in html
    assert "return bv-av||String(a.symbol).localeCompare(String(b.symbol))" in html
    assert 'typeof value==="number"&&Number.isFinite(value)' in html
    assert 'var change=quoteChangePct(row),changeClass=change===null?"neutral":change>0?"positive":change<0?"negative":"neutral"' in html
    assert 'navigation:{symbols:renderedRows.map(function(candidate){return candidate.symbol;}),items:renderedRows,index:renderedRows.indexOf(item)}' in html
    assert 'window.SignalixSharedDrawer.updateNavigation(renderedRows.map(function(candidate){return candidate.symbol;}),renderedRows)' in html
    assert '<th>Broad state</th>' not in html
    assert '<th>Bars used</th>' not in html
    assert '<th>As-of</th>' not in html
    assert 'colspan="8"' not in html


def test_shadow_drawer_removes_wave_evidence_and_chart_prose_but_preserves_markers_and_identity():
    template = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    shared = (Path(__file__).parent / "frontend" / "shared-drawer.js").read_text()
    assert 'dom.drawer.classList.toggle("drawer--shadow", shadow)' in shared
    assert 'if (waveSummary) waveSummary.hidden = shadow' in shared
    assert 'if (dom.drawerChartLegend) dom.drawerChartLegend.hidden = shadow' in shared
    assert 'marker.timestamp != null' in shared and 'marker.price != null' in shared
    assert 'String(item.name).toUpperCase() !== String(item.symbol || "").toUpperCase()' in shared
    assert "drawer-chart-status" not in (template + shared)
    assert "drawer-chart-context" not in (template + shared)
    assert "Evidence details" not in (template + shared)


def test_shadow_adapter_uses_shared_drawer_and_suppresses_action_setup_semantics():
    template = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    shared = Path(__file__).with_name("frontend") / "shared-drawer.js"
    combined = template + shared.read_text()
    assert 'source:"trend-map-shadow"' in combined
    assert 'actionability:"NONE"' in combined
    assert 'dom.drawerAction.hidden = shadow' in combined
    assert 'if (setupSection) setupSection.hidden = shadow' in combined
    assert 'shadow ? "Not applicable · Daily classification"' in combined
    assert 'shadow ? "Production read-only Daily evidence"' in combined


def test_shadow_shared_drawer_does_not_restore_removed_evidence_metadata_nodes():
    shared = (Path(__file__).parent / "frontend" / "shared-drawer.js").read_text()
    for removed in ('drawer-52w', 'drawer-ath', 'drawer-provenance', 'Evidence details and provenance'):
        assert removed not in shared
    assert 'dom.drawer.classList.remove("drawer--hidden");' in shared


def test_shadow_shared_drawer_owns_ohlcv_table_overflow_without_page_overflow():
    shared = (Path(__file__).parent / "frontend" / "shared-drawer.js").read_text()
    css = (Path(__file__).parent / "frontend" / "styles.css").read_text()
    assert '<div class="rolling-high-low__table-wrap"><table>' in shared
    assert '</tbody></table></div></section>' in shared
    assert ".rolling-high-low__table-wrap { width:100%; max-width:100%; min-width:0; overflow-x:auto; }" in css
    assert ".rolling-high-low table { width:100%; min-width:520px;" in css
    assert "font-size:12px" in css
    assert "body {" in css and "overflow-x: hidden;" in css


def test_template_has_mobile_safe_table_overflow_strategy():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    assert ".table-wrap" in html
    assert "overflow-x:auto" in html
    assert "max-width:100%" in html
    assert "min-width:720px" in html
    assert "overflow-x:hidden" in html


def test_shadow_module_has_no_database_write_operations():
    source = Path(subject.__file__).read_text()
    for token in ("INSERT", "UPDATE", "DELETE", "CREATE TABLE", "ALTER TABLE", "DROP TABLE"):
        assert token not in source.upper()


def test_backend_local_adapter_uses_select_only_pit_query_and_filters_as_of():
    class Cursor:
        description = [(name,) for name in ("date", "open", "high", "low", "close", "volume")]

        def __init__(self):
            self.sql = None
            self.params = None

        def execute(self, sql, params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return [("2026-09-10", 99, 101, 98, 100, 1234)]

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

    conn = Connection()
    rows, latest = subject.BackendDailyAdapter().load_daily_pit(conn, "AAA", "2026-09-11")
    assert rows[0]["close"] == 100
    assert latest == "2026-09-10"
    assert conn.cursor_instance.sql.lstrip().upper().startswith("WITH")
    assert "date <= %s" in conn.cursor_instance.sql
    assert conn.cursor_instance.params == ("AAA", "2026-09-11", "AAA", "2026-09-11", "2026-09-11")


class _ResultSetCursor:
    def __init__(self, rows):
        self.rows = rows
        self.description = [(f"column_{index}",) for index in range(len(rows[0]))] if rows else []
        self.calls = []

    def execute(self, sql, params):
        self.sql = sql
        self.calls.append((sql, params))

    def fetchall(self):
        if "source_completion_cutoff >=" not in self.sql:
            return self.rows
        official_dates = {row[0] for row in self.rows if row[6] == "price_data"}
        return [row for row in self.rows
                if row[6] == "price_data"
                or (row[0] not in official_dates
                    and row[8] == subject.DERIVED_DAILY_METHOD
                    and "2026-09-11T10:00:00+00:00" <= row[12] <= "2026-09-11T10:00:00+00:00")]

    def close(self):
        pass


class _ResultSetConnection:
    def __init__(self, rows):
        self.cursor_instance = _ResultSetCursor(rows)

    def cursor(self):
        return self.cursor_instance


def _official_row(date, close):
    return (date, close - 1, close + 1, close - 2, close, 1000,
            "price_data", None, None, None, None, None, None)


def _derived_row(date, close, run_id="run-derived"):
    return (date, close - 1, close + 1, close - 2, close, 8000,
            "derived_daily_price_data", "60m", "settrade_60m_complete_bangkok_session_ohlcv_v1",
            run_id, "2026-09-11T02:00:00+00:00", "2026-09-11T09:00:00+00:00",
            "2026-09-11T10:00:00+00:00", 8)


def test_backend_adapter_rejects_pre_completion_and_accepts_17_00_completion():
    before = list(_derived_row("2026-09-11", 109, "run-before"))
    before[12] = "2026-09-11T09:59:59+00:00"
    after = _derived_row("2026-09-11", 110, "run-after")
    late = list(_derived_row("2026-09-11", 111, "run-late"))
    late[12] = "2026-09-11T11:00:00+00:00"
    rows, latest = subject.BackendDailyAdapter().load_daily_pit(
        _ResultSetConnection([tuple(before), after, tuple(late)]), "AAA", "2026-09-11")
    assert [(row["close"], row["source_run_id"]) for row in rows] == [(110, "run-after")]
    assert latest == "2026-09-11"


def test_backend_adapter_selects_official_first_and_fills_missing_dates_from_fake_result_set():
    # The fake result set models PostgreSQL's already-resolved official-first
    # UNION result; assertions below exercise the adapter mapping, not SQL text.
    conn = _ResultSetConnection([
        _official_row("2026-09-10", 100),
        _derived_row("2026-09-11", 110),
    ])
    rows, latest = subject.BackendDailyAdapter().load_daily_pit(
        conn, "AAA", "2026-09-11")
    assert [(row["date"], row["source"]) for row in rows] == [
        ("2026-09-10", "price_data"),
        ("2026-09-11", "derived_daily_price_data"),
    ]
    assert latest == "2026-09-11"
    assert rows[0]["source_run_id"] is None
    assert rows[1]["source_run_id"] == "run-derived"


def test_backend_adapter_official_same_date_wins_in_fake_result_set():
    conn = _ResultSetConnection([
        _official_row("2026-09-11", 100),
        _derived_row("2026-09-11", 110),
    ])
    rows, latest = subject.BackendDailyAdapter().load_daily_pit(
        conn, "AAA", "2026-09-11")
    assert len(rows) == 1
    assert rows[0]["source"] == "price_data"
    assert rows[0]["close"] == 100
    assert latest == "2026-09-11"


def test_backend_adapter_preserves_complete_derived_lineage_from_fake_result_set():
    conn = _ResultSetConnection([_derived_row("2026-09-11", 110, "run-22")])
    rows, _ = subject.BackendDailyAdapter().load_daily_pit(
        conn, "AAA", "2026-09-11")
    assert rows[0] == {
        "date": "2026-09-11", "open": 109, "high": 111, "low": 108,
        "close": 110, "volume": 8000,
        "source": "derived_daily_price_data", "source_timeframe": "60m",
        "derivation_method": "settrade_60m_complete_bangkok_session_ohlcv_v1",
        "source_run_id": "run-22", "source_first_ts": "2026-09-11T02:00:00+00:00",
        "source_last_ts": "2026-09-11T09:00:00+00:00",
        "source_completion_cutoff": "2026-09-11T10:00:00+00:00", "source_bar_count": 8,
    }


def test_backend_local_adapter_batches_symbols_with_exact_as_of_filter():
    class Cursor:
        description = [(name,) for name in ("symbol", "date", "open", "high", "low", "close", "volume", "invalid_count")]

        def __init__(self):
            self.sql = None
            self.params = None

        def execute(self, sql, params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return [("AAA", "2026-09-10", 99, 101, 98, 100, 1234, 0)]

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

    conn = Connection()
    loaded = subject.BackendDailyAdapter().load_daily_pit_batch(conn, ["AAA", "BBB"], "2026-09-11")
    assert list(loaded) == ["AAA", "BBB"]
    assert len(loaded["AAA"][0]) == 1
    assert loaded["BBB"][0:2] == ([], None)
    assert loaded["BBB"][2]["quality_established"] is False
    assert loaded["AAA"][2]["invalid_count"] == 0
    assert conn.cursor_instance.sql.lstrip().upper().startswith("WITH")
    assert "symbol=ANY(%s)" in conn.cursor_instance.sql
    assert "market='TH'" in conn.cursor_instance.sql
    assert "date <= %s" in conn.cursor_instance.sql
    assert "ORDER BY symbol ASC, date ASC" in conn.cursor_instance.sql
    assert conn.cursor_instance.params == (["AAA", "BBB"], "2026-09-11", ["AAA", "BBB"], "2026-09-11", "2026-09-11", subject.RETRIEVAL_CAP)
    assert "row_number() OVER (PARTITION BY filtered.symbol ORDER BY filtered.date DESC)" in conn.cursor_instance.sql
    assert "invalid_count" in conn.cursor_instance.sql


def test_report_uses_one_batch_select_and_preserves_counts():
    class Adapter:
        def __init__(self):
            self.batch_calls = []

        def resolve_universe(self, conn, value):
            return ["AAA", "BBB"], {"universe_filter": value, "eligible_count": 2}

        def _exec_select(self, conn, sql, params=None):
            assert sql.startswith("SELECT")
            return [("2026-09-11",)], ["max_date"]

        def load_daily_pit_batch(self, conn, symbols, as_of):
            self.batch_calls.append((list(symbols), as_of))
            return {"AAA": (bars(75), as_of), "BBB": ([], None)}

    adapter = Adapter()
    report = subject.build_shadow_report(adapter, object())
    assert adapter.batch_calls == [(["AAA", "BBB"], "2026-09-11")]
    assert report["summary"] == {"DATA_BLOCKED": 1, "AVAILABLE": 1}
    assert report["status_by_symbol"] == {"AAA": "AVAILABLE", "BBB": "DATA_BLOCKED"}
    assert report["universe"]["declared_count"] == 2


def test_batch_error_is_visible_as_blocked_and_not_verified():
    class Adapter:
        def resolve_universe(self, conn, value):
            return ["AAA", "BBB"], {"universe_filter": value}

        def _exec_select(self, conn, sql, params=None):
            return [("2026-09-11",)], ["max_date"]

        def load_daily_pit_batch(self, conn, symbols, as_of):
            raise OSError("database unavailable")

    report = subject.build_shadow_report(Adapter(), object())
    assert report["status"] == "DATA_BLOCKED"
    assert report["status_by_symbol"] == {"AAA": "DATA_BLOCKED", "BBB": "DATA_BLOCKED"}
    assert all(row["provenance"]["availability"] == "NOT_VERIFIED" for row in report["rows"])


def test_default_report_cache_reuses_and_invalidates_on_as_of(monkeypatch):
    subject.clear_report_cache()
    adapter = subject.BackendDailyAdapter()
    calls = {"as_of": 0, "batch": 0}

    class Connection:
        def close(self):
            pass

    def fake_get_conn():
        return Connection()

    def resolve(conn, value):
        return ["AAA"], {"universe_filter": value}

    def select(conn, sql, params=None):
        calls["as_of"] += 1
        return [("2026-09-11" if calls["as_of"] < 3 else "2026-09-12",)], ["max_date"]

    def batch(conn, symbols, current_as_of):
        calls["batch"] += 1
        return {"AAA": (bars(75), current_as_of)}

    monkeypatch.setattr(subject, "_adapter", lambda: adapter)
    monkeypatch.setattr(adapter, "_get_conn", fake_get_conn)
    monkeypatch.setattr(adapter, "resolve_universe", resolve)
    monkeypatch.setattr(adapter, "_exec_select", select)
    monkeypatch.setattr(adapter, "load_daily_pit_batch", batch)

    cold = subject.build_shadow_report(source="database")
    warm = subject.build_shadow_report(source="database")
    refreshed = subject.build_shadow_report(source="database")
    assert cold["cache"]["status"] == "cold"
    assert warm["cache"]["status"] == "warm"
    assert warm["cache"]["as_of"] == "2026-09-11"
    assert warm["cache"]["policy_hash"] == warm["policy"]["hash"]
    assert refreshed["as_of"] == "2026-09-12"
    assert refreshed["cache"]["status"] == "cold"
    assert calls["batch"] == 2
    subject.clear_report_cache()


@pytest.mark.parametrize("sql", [
    "UPDATE price_data SET close=1",
    "WITH changed AS (DELETE FROM price_data RETURNING symbol) SELECT * FROM changed",
    "WITH changed AS (UPDATE price_data SET close=1 RETURNING symbol) SELECT * FROM changed",
    "WITH changed AS (INSERT INTO price_data(symbol) VALUES ('AAA') RETURNING symbol) SELECT * FROM changed",
])
def test_backend_local_adapter_rejects_mutating_sql_anywhere(sql):
    with pytest.raises(RuntimeError, match="SELECT/WITH"):
        subject._assert_select(sql)


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "WITH source AS (SELECT 1 AS value) SELECT value FROM source",
])
def test_backend_local_adapter_accepts_read_only_select_and_with(sql):
    subject._assert_select(sql)


def test_report_builds_with_injected_backend_local_adapter(monkeypatch):
    adapter = subject.BackendDailyAdapter()
    monkeypatch.setattr(adapter, "resolve_universe", lambda conn, value: (["AAA"], {"universe_filter": value}))
    monkeypatch.setattr(adapter, "_exec_select", lambda conn, sql, params=None: ([("2026-09-11",)], ["max_date"]))
    monkeypatch.setattr(adapter, "load_daily_pit", lambda conn, symbol, as_of: (bars(75), as_of))
    report = subject.build_shadow_report(adapter=adapter, conn=object())
    assert report["status_by_symbol"] == {"AAA": "AVAILABLE"}
    assert report["provenance"]["adapter"] == "BackendDailyAdapter"


def test_api_route_is_same_origin_read_only_envelope(monkeypatch):
    class Handler:
        def __init__(self):
            self.headers = {}
            self.body = bytearray()
            self.wfile = self
        def send_response(self, status):
            self.status = status
        def send_header(self, key, value):
            self.headers[key] = value
        def end_headers(self):
            pass
        def write(self, body):
            self.body.extend(body)
    handler = Handler()
    monkeypatch.setattr(subject, "build_shadow_report", lambda: {"status": subject.PRODUCTION_READ_ONLY, "research_only": False, "actionability": "NONE", "rows": []})
    assert subject.handle_shadow_trend_map_api("/api/trend-map-shadow", handler)
    assert handler.status == 200
    payload = json.loads(bytes(handler.body))
    assert payload["status"] == subject.PRODUCTION_READ_ONLY
    assert payload["research_only"] is False
    assert payload["actionability"] == "NONE"
