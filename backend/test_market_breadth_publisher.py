import json
from datetime import date, datetime, timedelta

from market_breadth_artifact import load_market_breadth_artifact
from market_breadth_publisher import (PostgresMarketBreadthSource, _indicator_observations,
                                      publish_market_breadth_replay)


class Source:
    def __init__(self):
        self.dates = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(520)]
        self.symbols = ["AAA", "BBB"]

    def resolve_universe(self):
        return {"name": "active_ord", "symbols": self.symbols, "count": 2,
                "symbol_hash": "fixture-universe"}

    def completed_sessions(self, **kwargs):
        return self.dates

    def load_daily(self, symbols, **kwargs):
        rows = []
        for symbol in symbols:
            for index, session in enumerate(self.dates):
                close = 100 + index if symbol == "AAA" else 200 - index
                rows.append({"symbol": symbol, "session_date": session, "open": close,
                             "high": close + 1, "low": close - 1, "close": close,
                             "volume": 1000, "source": "price_data"})
        # This derived duplicate must never replace the official observation.
        rows.append({"symbol": "AAA", "session_date": self.dates[-1], "open": 1,
                     "high": 1, "low": 1, "close": 1, "volume": 1,
                     "source": "derived_daily_price_data", "source_origin": "settrade",
                     "source_timeframe": "60m", "source_bar_count": 8,
                     "derivation_method": "settrade_60m_complete_bangkok_session_ohlcv_v1"})
        return rows

    def benchmark(self, **kwargs):
        return {"symbol": "SET", "source": "price_data", "timeframe": "1D",
                "close": 1400, "change_1d_pct": 0.5, "change_20d_pct": -1.25,
                "as_of": self.dates[-1], "quality": {"status": "AVAILABLE", "reason": "fixture"}}


class SourceMissingCurrentSymbol(Source):
    def load_daily(self, symbols, **kwargs):
        return [row for row in super().load_daily(symbols, **kwargs)
                if not (row["symbol"] == "BBB" and row["session_date"] == self.dates[-1])]


def _derived_row(session_date, *, cutoff):
    return {"symbol": "AAA", "session_date": session_date, "open": 100,
            "high": 101, "low": 99, "close": 100, "volume": 1000,
            "source": "derived_daily_price_data", "source_origin": "settrade",
            "source_timeframe": "60m", "source_bar_count": 8,
            "derivation_method": "settrade_60m_complete_bangkok_session_ohlcv_v1",
            "source_completion_cutoff": cutoff}


class CapturingCursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class CapturingConnection:
    def __init__(self, rows=()):
        self.cursor_instance = CapturingCursor(rows)

    def set_session(self, **kwargs):
        pass

    def cursor(self):
        return self.cursor_instance


def test_derived_daily_requires_completed_bangkok_cutoff_and_pit_as_of():
    from market_breadth_publisher import _completed_derived_for_as_of

    as_of = "2025-06-03"
    assert _completed_derived_for_as_of(
        _derived_row(as_of, cutoff="2025-06-03T09:00:00+00:00"), as_of) is False
    assert _completed_derived_for_as_of(
        _derived_row(as_of, cutoff="2025-06-03T10:00:00+07:00"), as_of) is False
    assert _completed_derived_for_as_of(
        _derived_row(as_of, cutoff="2025-06-03T17:00:00+07:00"), as_of) is True
    assert _completed_derived_for_as_of(
        _derived_row("2025-06-04", cutoff="2025-06-04T17:00:00+07:00"), as_of) is False
    assert _completed_derived_for_as_of(
        _derived_row(as_of, cutoff="2025-06-03T17:00:00"), as_of) is False
    assert _completed_derived_for_as_of(
        _derived_row(as_of, cutoff=datetime(2025, 6, 3, 17, 0)), as_of) is False


def test_completed_sessions_captures_explicit_as_of_sql_and_params():
    connection = CapturingConnection(rows=[("2025-06-03",)])
    source = PostgresMarketBreadthSource(connection)

    assert source.completed_sessions(as_of="2025-06-03", limit=520) == ["2025-06-03"]

    cursor = connection.cursor_instance
    assert cursor.sql.count("%s") == len(cursor.params) == 5
    assert cursor.params == ("2025-06-03", "settrade_60m_complete_bangkok_session_ohlcv_v1",
                             "2025-06-03", "2025-06-03", 520)
    assert "source_completion_cutoff <= ((%s::date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')" in cursor.sql
    assert "source_completion_cutoff >= ((session_date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')" in cursor.sql
    assert "session_date <= %s" in cursor.sql


def test_completed_sessions_captures_until_and_implicit_now_paths():
    connection = CapturingConnection()
    source = PostgresMarketBreadthSource(connection)

    source.completed_sessions(until="2025-06-03", limit=10)
    cursor = connection.cursor_instance
    assert cursor.sql.count("%s") == len(cursor.params) == 5
    assert cursor.params[0] == cursor.params[2] == cursor.params[3] == "2025-06-03"
    assert "source_completion_cutoff <= ((%s::date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')" in cursor.sql

    source.completed_sessions(limit=10)
    assert cursor.sql.count("%s") == len(cursor.params) == 2
    assert cursor.params == ("settrade_60m_complete_bangkok_session_ohlcv_v1", 10)
    assert "source_completion_cutoff <= NOW()" in cursor.sql


def test_load_daily_captures_bangkok_until_bound_and_no_lookahead_param():
    connection = CapturingConnection()
    source = PostgresMarketBreadthSource(connection)

    assert source.load_daily(["AAA"], since="2025-05-01", until="2025-06-03") == []

    cursor = connection.cursor_instance
    assert cursor.sql.count("%s") == len(cursor.params) == 8
    assert cursor.params == (["AAA"], "2025-05-01", "2025-06-03", ["AAA"],
                             "2025-05-01", "2025-06-03",
                             "settrade_60m_complete_bangkok_session_ohlcv_v1", "2025-06-03")
    assert "source_completion_cutoff >= ((session_date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')" in cursor.sql
    assert "source_completion_cutoff <= ((%s::date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')" in cursor.sql
    assert "source_completion_cutoff <= NOW()" not in cursor.sql


def test_official_daily_wins_over_completed_derived_same_symbol_date(tmp_path):
    source = Source()
    source.load_daily = lambda symbols, **kwargs: [
        {"symbol": "AAA", "session_date": source.dates[-1], "open": 100,
         "high": 101, "low": 99, "close": 100, "volume": 1000,
         "source": "price_data"},
        _derived_row(source.dates[-1], cutoff="2025-06-03T17:00:00+07:00"),
    ]
    selected = publish_market_breadth_replay(source=source, root=tmp_path)
    assert selected["observed_count"] == 1
    artifact = load_market_breadth_artifact(tmp_path)
    assert artifact["counts"]["official"] == 1
    assert artifact["counts"]["derived"] == 0


def test_read_only_replay_is_bounded_lineaged_and_compact(tmp_path):
    result = publish_market_breadth_replay(source=Source(), root=tmp_path, run_id="fixture-run")
    artifact = load_market_breadth_artifact(tmp_path)

    assert result["read_only"] is True
    assert result["context_sessions"] == 520
    assert result["report_sessions"] == 260
    assert artifact["as_of"] == "2025-06-03"
    assert len(artifact["history_260"]) == 260
    assert len(artifact["history_all"]) == 260
    assert artifact["provenance"]["query_mode"] == "SELECT_ONLY"
    assert artifact["benchmark"]["symbol"] == "SET"
    assert "SET50" not in json.dumps(artifact)
    assert all("AAA" not in json.dumps(session["new_high_low"]) for session in artifact["history_260"])
    assert artifact["counts"]["official"] == 2
    assert artifact["counts"]["derived"] == 0


def test_replay_publication_is_idempotent(tmp_path):
    first = publish_market_breadth_replay(source=Source(), root=tmp_path, run_id="fixture-run")
    second = publish_market_breadth_replay(source=Source(), root=tmp_path, run_id="fixture-run")
    assert first["content_hash"] == second["content_hash"]
    assert len(list((tmp_path / "versions").glob("*.json"))) == 1


def test_current_coverage_does_not_fill_from_historical_union(tmp_path):
    result = publish_market_breadth_replay(source=SourceMissingCurrentSymbol(), root=tmp_path,
                                           run_id="coverage-fixture")
    artifact = load_market_breadth_artifact(tmp_path)

    universe = artifact["universe"]
    assert universe["observed_count"] == universe["historical_observed_count"] == 2
    assert universe["blocked_count"] == universe["historical_blocked_count"] == 0
    assert universe["current_declared_count"] == 2
    assert universe["current_observed_count"] == 1
    assert universe["current_blocked_count"] == 1
    assert result["observed_count"] == 1
    assert result["blocked_count"] == 1
    assert artifact["quality"]["status"] == "PARTIAL"
    assert artifact["quality"]["status"] != "DATA_BLOCKED"


def test_indicator_observations_project_evidence_and_bound_indicator_window():
    dates = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(260)]
    rows = [{"symbol": "AAA", "session_date": session, "open": close, "high": close + 1,
             "low": close - 1, "close": close, "volume": 1000, "source": "price_data"}
            for index, session in enumerate(dates, 1) for close in [10 + index]]

    observations = _indicator_observations(rows, ["AAA"], dates)

    assert len(observations) == 260
    observation = observations[-1]
    evidence = observation["main_trend_evidence"]
    assert "series" not in observation
    assert "technical_snapshot" not in observation
    assert "moving_averages" not in evidence
    assert "slopes_20d_pct" not in evidence
    assert set(evidence) >= {
        "main_trend", "main_trend_display", "evidence_quality", "as_of",
        "source_timeframe", "policy_version", "reason", "missing_periods",
        "missing_slope_periods",
    }
    assert set(evidence["missing_periods"]) == set()
    assert observation["ma50"] is not None
    assert observation["ma200"] is not None
    assert observation["above_ma50"] is True
    assert observation["above_ma200"] is True


def test_indicator_observations_fixture_scale_stays_compact():
    dates = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(260)]
    symbols = [f"S{i:02d}" for i in range(12)]
    rows = [{"symbol": symbol, "session_date": session, "open": 10, "high": 11,
             "low": 9, "close": 10, "volume": 1000, "source": "price_data"}
            for symbol in symbols for session in dates]

    observations = _indicator_observations(rows, symbols, dates)

    assert len(observations) == len(symbols) * len(dates)
    assert max((len(value) for observation in observations
                for value in observation["main_trend_evidence"].values()
                if isinstance(value, (list, tuple))), default=0) <= 6
    assert all("series" not in observation["main_trend_evidence"]
               for observation in observations)
