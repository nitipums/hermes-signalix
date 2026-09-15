import datetime as dt
import json

import pytest

import intraday_quote_read_model as subject


NOW = dt.datetime(2026, 9, 15, 9, 30, tzinfo=dt.timezone.utc)


class Adapter:
    def resolve_universe(self, conn, value):
        assert value == "marginable_long"
        return ["AAA", "BBB"], {"scope": value}

    def load_intraday_quotes(self, conn, symbols, now=None):
        assert symbols == ["AAA", "BBB"]
        return {"AAA": {"ts": "2026-09-15T09:00:00+00:00", "close": 110,
                         "daily_close": 100, "daily_date": "2026-09-14",
                         "daily_source": "price_data"},
                "BBB": {"ts": "2026-09-15T09:00:00+00:00", "close": 55,
                         "daily_close": 50, "daily_date": "2026-09-14",
                         "daily_source": "derived_daily_price_data"}}


def test_publish_readback_is_compact_atomic_and_identity_bound(tmp_path):
    result = subject.publish(object(), {"run_id": "run-1", "status": "full_success"},
                             root=tmp_path, adapter=Adapter(), generated_at=NOW)
    pointer = json.loads((tmp_path / "current.json").read_text())
    artifact = subject.read_current(tmp_path, now=NOW)
    assert result["symbol_count"] == 2
    assert pointer["artifact_id"] == artifact["artifact_id"]
    assert artifact["universe"]["symbol_count"] == 2
    assert artifact["query_mode"] == "SELECT_ONLY"
    assert set(artifact["quotes"][0]) <= {
        "symbol", "status", "latest_completed_60m", "price", "change_amount",
        "change_pct", "change_basis", "daily_baseline",
    }
    assert "ohlc" not in artifact["quotes"][0]


def test_official_daily_baseline_wins_and_derived_fills_missing_dates():
    artifact = subject.build_artifact(object(), {"run_id": "run-1"}, adapter=Adapter(), generated_at=NOW)
    assert artifact["quotes"][0]["daily_baseline"]["source"] == "price_data"
    assert artifact["quotes"][1]["daily_baseline"]["source"] == "derived_daily_price_data"


@pytest.mark.parametrize("mutate", [
    lambda a: a["quotes"][0].update(latest_completed_60m="2026-09-15T10:00:00+00:00"),
    lambda a: a.update(generated_at="2026-09-15T06:00:00+00:00"),
    lambda a: a["quotes"].append({"symbol": "CC", "status": "AVAILABLE"}),
])
def test_malformed_future_or_stale_artifact_fails_closed(tmp_path, mutate):
    artifact = subject.build_artifact(object(), {"run_id": "run-1"}, adapter=Adapter(), generated_at=NOW)
    mutate(artifact)
    with pytest.raises((ValueError, KeyError)):
        subject.validate_artifact(artifact, now=NOW)


def test_invalid_pointer_does_not_read_an_unrelated_path(tmp_path):
    (tmp_path / "current.json").write_text(json.dumps({
        "schema_version": subject.SCHEMA_VERSION, "artifact_id": "x",
        "artifact_path": "../outside.json", "content_hash": "x",
    }))
    with pytest.raises((ValueError, FileNotFoundError)):
        subject.read_current(tmp_path, now=NOW)
