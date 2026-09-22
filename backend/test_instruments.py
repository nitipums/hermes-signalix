from __future__ import annotations

from instruments import (
    instrument_hash,
    instrument_quality_summary,
    validate_instrument_record,
)
from sync_settrade_master import parse_stock_master


class _MasterCursor:
    description = [(field,) for field in (
        "symbol", "instrument_type", "status", "venue", "asset_class",
        "currency", "timezone", "session", "source", "freshness",
        "reason", "marked_at")]

    def execute(self, query, params=None):
        self.query = query

    def fetchall(self):
        # Simulate the database applying the authoritative active-ORD filter.
        return [("AAA", "ORD", "active", "SET", "equity", "THB",
                 "Asia/Bangkok", "SET", "settrade_stock_master", "fresh",
                 None, None)]

    def close(self):
        pass


class _MasterConnection:
    def __init__(self):
        self.last_cursor = None

    def cursor(self):
        self.last_cursor = _MasterCursor()
        return self.last_cursor

    def close(self):
        pass


def test_parse_stock_master_keeps_only_set_mai_common_stocks():
    payload = {
        "securitySymbols": [
            {"symbol": "AAA", "market": "SET", "securityType": "S", "nameEN": "A"},
            {"symbol": "BBB", "market": "mai", "securityType": "S", "nameEN": "B"},
            {"symbol": "DR01", "market": "SET", "securityType": "DR"},
            {"symbol": "DW01", "market": "SET", "securityType": "W"},
            {"symbol": "FUT", "market": "TFEX", "securityType": "S"},
            {"symbol": "", "market": "SET", "securityType": "S"},
        ]
    }

    records = parse_stock_master(payload)

    assert [record["symbol"] for record in records] == ["AAA", "BBB"]
    assert records[0]["market"] == "SET"
    assert records[1]["market"] == "MAI"
    assert all(record["source"] == "settrade_stock_master" for record in records)


def test_parse_stock_master_deduplicates_symbol_deterministically():
    payload = {
        "securitySymbols": [
            {"symbol": " AAA ", "market": "SET", "securityType": "S", "nameEN": "first"},
            {"symbol": "AAA", "market": "SET", "securityType": "S", "nameEN": "second"},
        ]
    }

    records = parse_stock_master(payload)

    assert len(records) == 1
    assert records[0]["symbol"] == "AAA"
    assert records[0]["nameEN"] == "second"


def test_active_ord_symbols_uses_only_active_ord_master_query():
    from instruments import active_ord_symbols

    pg = _MasterConnection()
    assert active_ord_symbols(pg) == ["AAA"]
    assert "instrument_type = 'ORD'" in pg.last_cursor.query
    assert "status = 'active'" in pg.last_cursor.query


def test_instrument_hash_is_order_independent_and_changes_on_freshness_drift():
    records = [
        {"symbol": "BBB", "source": "settrade_stock_master", "status": "active", "freshness": "fresh"},
        {"symbol": "AAA", "source": "settrade_stock_master", "status": "active", "freshness": "fresh"},
    ]

    assert instrument_hash(records) == instrument_hash(list(reversed(records)))
    changed = [dict(records[0]), {**records[1], "freshness": "stale"}]
    assert instrument_hash(records) != instrument_hash(changed)


def complete_record(**overrides):
    record = {
        "symbol": "AAA",
        "instrument_type": "ORD",
        "status": "active",
        "venue": "SET",
        "asset_class": "equity",
        "currency": "THB",
        "timezone": "Asia/Bangkok",
        "session": "SET",
        "source": "settrade_stock_master",
        "freshness": "fresh",
    }
    record.update(overrides)
    return record


def test_validate_instrument_record_accepts_complete_active_ord_without_mutation():
    record = complete_record()

    quality = validate_instrument_record(record)

    assert quality == {
        "status": "complete",
        "missing_fields": [],
        "invalid_fields": [],
    }
    assert record["symbol"] == "AAA"


def test_validate_instrument_record_reports_missing_and_invalid_canonical_fields():
    quality = validate_instrument_record(complete_record(
        source=None,
        currency="USD",
        venue="TFEX",
        status="inactive",
    ))

    assert quality["status"] == "invalid"
    assert quality["missing_fields"] == ["source"]
    assert quality["invalid_fields"] == ["status", "venue", "currency"]


def test_quality_summary_is_deterministic_and_counts_incomplete_active_rows():
    records = [
        complete_record(symbol="BBB"),
        complete_record(symbol="AAA", timezone=None),
    ]

    summary = instrument_quality_summary(records)

    assert summary == {
        "evaluated_count": 2,
        "complete_count": 1,
        "incomplete_count": 1,
        "invalid_count": 0,
        "completeness_pct": 50.0,
    }


def test_validator_flags_non_ord_or_non_active_taxonomy_as_invalid():
    quality = validate_instrument_record(complete_record(
        instrument_type="DR",
        status="excluded",
    ))

    assert quality["status"] == "invalid"
    assert quality["invalid_fields"] == ["instrument_type", "status"]


def test_instruments_endpoint_exposes_row_and_aggregate_quality(monkeypatch):
    import app
    import instruments

    record = complete_record()
    monkeypatch.setattr(app, "get_pg", lambda: _MasterConnection())
    monkeypatch.setattr(instruments, "instrument_master", lambda _: [dict(record)])
    monkeypatch.setattr(instruments, "profile_taxonomy", lambda _, symbols: {
        symbol: {"symbol": symbol, "missing": True, "source": None}
        for symbol in symbols
    })

    response = app.list_instruments()

    assert response["quality"] == {
        "evaluated_count": 1,
        "complete_count": 1,
        "incomplete_count": 0,
        "invalid_count": 0,
        "completeness_pct": 100.0,
    }
    assert response["instruments"][0]["quality"] == {
        "status": "complete",
        "missing_fields": [],
        "invalid_fields": [],
    }
    assert response["instruments"][0]["profile"]["missing"] is True
