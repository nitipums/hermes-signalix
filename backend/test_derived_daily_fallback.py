import datetime as dt
from contextlib import contextmanager

import mvp_api
import pytest
import trend_map
import update_data as subject


BKK = dt.timezone(dt.timedelta(hours=7))


def session_rows(session=dt.date(2026, 9, 11), count=8):
    rows = []
    for hour in range(9, 9 + count):
        stamp = dt.datetime.combine(session, dt.time(hour), BKK)
        rows.append({"ts": stamp, "open": 100 + hour, "high": 105 + hour,
                     "low": 95 + hour, "close": 102 + hour, "volume": 1000})
    return rows


def test_aggregate_requires_complete_completed_session_and_preserves_lineage():
    cutoff = dt.datetime(2026, 9, 11, 17, 0, tzinfo=BKK)
    result = subject.aggregate_complete_derived_daily(
        "AAA", session_rows(), dt.date(2026, 9, 11), cutoff, "run-1")
    assert result["open"] == 109
    assert result["close"] == 118
    assert result["volume"] == 8000
    assert result["source"] == "settrade"
    assert result["source_timeframe"] == "60m"
    assert result["source_bar_count"] == 8
    assert result["source_run_id"] == "run-1"
    assert result["derivation_method"] == subject.DERIVED_DAILY_METHOD
    assert result["source_first_ts"] == dt.datetime(2026, 9, 11, 2, 0, tzinfo=dt.timezone.utc)
    assert result["source_last_ts"] == dt.datetime(2026, 9, 11, 9, 0, tzinfo=dt.timezone.utc)
    assert result["source_completion_cutoff"] == dt.datetime(2026, 9, 11, 10, 0, tzinfo=dt.timezone.utc)


def test_aggregate_rejects_incomplete_invalid_and_future_rows():
    cutoff = dt.datetime(2026, 9, 11, 17, 0, tzinfo=BKK)
    assert subject.aggregate_complete_derived_daily("AAA", session_rows(count=7), dt.date(2026, 9, 11), cutoff, "r") is None
    invalid = session_rows()
    invalid[0]["low"] = 999
    assert subject.aggregate_complete_derived_daily("AAA", invalid, dt.date(2026, 9, 11), cutoff, "r") is None
    assert subject.aggregate_complete_derived_daily("AAA", session_rows(dt.date(2026, 9, 12)), dt.date(2026, 9, 11), cutoff, "r") is None


@pytest.mark.parametrize("cutoff", (
    dt.datetime(2026, 9, 11, 16, 0, tzinfo=BKK),
    dt.datetime(2026, 9, 11, 16, 1, tzinfo=BKK),
))
def test_aggregate_rejects_before_completed_session_boundary(cutoff):
    assert subject.aggregate_complete_derived_daily(
        "AAA", session_rows(), dt.date(2026, 9, 11), cutoff, "run") is None


@pytest.mark.parametrize(
    ("now", "expected_status", "expected_calls"),
    ((dt.datetime(2026, 9, 11, 16, 0, tzinfo=BKK), "SKIPPED_INCOMPLETE_SESSION", 0),
     (dt.datetime(2026, 9, 11, 17, 0, tzinfo=BKK), "WRITTEN", 1)),
)
def test_writer_enforces_completed_session_boundary(monkeypatch, now, expected_status, expected_calls):
    monkeypatch.setattr(mvp_api, "resolve_universe", lambda pg, value: (["AAA"], {"scope": value}))
    market = FakeMarket()
    result = subject.write_derived_daily_fallback(
        FakePg(), now=now, market_factory=lambda: market)
    assert result["status"] == expected_status
    assert len(market.calls) == expected_calls


def test_writer_at_16_does_not_fetch_or_write_a_partial_session(monkeypatch):
    monkeypatch.setattr(mvp_api, "resolve_universe", lambda pg, value: (["AAA"], {"scope": value}))
    market = FakeMarket()
    pg = FakePg()
    result = subject.write_derived_daily_fallback(
        pg, now=dt.datetime(2026, 9, 11, 16, 0, tzinfo=BKK),
        market_factory=lambda: market)
    assert result["rows_written"] == 0
    assert pg.derived_rows == {}
    assert market.calls == []


def test_quote_exposes_derived_lineage_without_calling_it_official():
    lineage = {"source": "derived_daily_price_data", "source_timeframe": "60m",
               "source_run_id": "run-1", "source_first_ts": "2026-09-11T02:00:00Z",
               "source_last_ts": "2026-09-11T09:00:00Z", "source_bar_count": 8,
               "source_completion_cutoff": "2026-09-11T10:00:00Z",
               "derivation_method": subject.DERIVED_DAILY_METHOD}
    quote = trend_map._quote([{"date": "2026-09-11", "close": 123, "source": "derived_daily_price_data",
                             **{key: value for key, value in lineage.items() if key != "source"}}])
    assert quote["source"] == "derived_daily_price_data"
    assert quote["provisional"] is False
    assert quote["provenance"]["lineage"] == lineage


class FakeCursor:
    def __init__(self, pg):
        self.pg = pg
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if "INSERT INTO derived_daily_price_data" in sql:
            key = (params[0], params[1], params[7], params[8])
            self.pg.derived_rows[key] = params

    def fetchall(self):
        return []

    def close(self):
        pass


class FakePg:
    def __init__(self):
        self.derived_rows = {}
        self.cursor_value = FakeCursor(self)
        self.commits = 0

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


class FakeMarket:
    def __init__(self, *, failure=None):
        self.calls = []
        self.failure = failure

    def get_candlestick(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        values = session_rows()
        return {key: [int(row["ts"].timestamp()) for row in values] if key == "time" else
                [row[key] for row in values] for key in ("time", "open", "high", "low", "close", "volume")}


def test_writer_fetches_only_affected_current_session_and_is_idempotent(monkeypatch):
    monkeypatch.setattr(mvp_api, "resolve_universe", lambda pg, value: (["AAA", "BBB"], {"scope": value}))
    market = FakeMarket()
    pg = FakePg()
    now = dt.datetime(2026, 9, 11, 17, 0, tzinfo=BKK)
    first = subject.write_derived_daily_fallback(pg, now=now, market_factory=lambda: market)
    second = subject.write_derived_daily_fallback(pg, now=now, market_factory=lambda: market)
    assert first["symbols_affected"] == 2
    assert first["rows_written"] == 2
    assert second["rows_written"] == 2
    assert len(market.calls) == 4
    assert all(call["interval"] == "60m" and call["limit"] == 8 and call["start"].endswith("T09:00") for call in market.calls)
    schema_sql = [sql for sql, _ in pg.cursor_value.executed
                  if "CREATE TABLE IF NOT EXISTS derived_daily_price_data" in sql]
    assert schema_sql == []
    insert_sql = [sql for sql, _ in pg.cursor_value.executed if "INSERT INTO" in sql.upper()]
    assert len(insert_sql) == 4
    assert all("INSERT INTO derived_daily_price_data" in sql for sql in insert_sql)
    assert len(pg.derived_rows) == 2
    assert pg.commits == 2


def test_fallback_get_candlestick_is_timeout_bounded_on_failure(monkeypatch):
    monkeypatch.setattr(mvp_api, "resolve_universe", lambda pg, value: (["AAA"], {"scope": value}))
    entered = []

    @contextmanager
    def tracked_timeout():
        entered.append(True)
        yield

    monkeypatch.setattr(subject, "settrade_request_timeout", tracked_timeout)
    with pytest.raises(RuntimeError, match="transport failure"):
        subject.write_derived_daily_fallback(
            FakePg(), now=dt.datetime(2026, 9, 11, 17, 0, tzinfo=BKK),
            market_factory=lambda: FakeMarket(failure=RuntimeError("transport failure")),
        )
    assert entered == [True]


def test_report_provenance_lists_lineage_for_every_selected_derived_row():
    derived = []
    for index in range(45):
        close = 100 + index
        row = {"date": f"2026-01-{(index % 28) + 1:02d}", "open": close - 1,
               "high": close + 1, "low": close - 2, "close": close, "volume": 1000}
        row["source"] = "derived_daily_price_data"
        row.update({"source_timeframe": "60m", "source_run_id": f"run-{index}",
                    "source_first_ts": f"2026-01-01T02:{index:02d}:00Z",
                    "source_last_ts": f"2026-01-01T09:{index:02d}:00Z",
                    "source_completion_cutoff": f"2026-01-01T10:{index:02d}:00Z",
                    "source_bar_count": 8,
                    "derivation_method": subject.DERIVED_DAILY_METHOD})
        derived.append(row)

    class Adapter:
        def resolve_universe(self, conn, value):
            return ["AAA"], {"universe_filter": value}

        def _exec_select(self, conn, sql, params=None):
            return [("2026-02-28",)], ["max_date"]

        def load_daily_pit(self, conn, symbol, as_of):
            return derived, as_of

    report = trend_map.build_trend_map_report(Adapter(), object())
    lineage = report["rows"][0]["provenance"]["selected_daily_lineage"]
    assert len(lineage) == 45
    assert [item["source_run_id"] for item in lineage] == [f"run-{index}" for index in range(45)]
