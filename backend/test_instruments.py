from __future__ import annotations

from instruments import instrument_hash
from sync_settrade_master import parse_stock_master


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


def test_instrument_hash_is_order_independent_and_changes_on_freshness_drift():
    records = [
        {"symbol": "BBB", "source": "settrade_stock_master", "status": "active", "freshness": "fresh"},
        {"symbol": "AAA", "source": "settrade_stock_master", "status": "active", "freshness": "fresh"},
    ]

    assert instrument_hash(records) == instrument_hash(list(reversed(records)))
    changed = [dict(records[0]), {**records[1], "freshness": "stale"}]
    assert instrument_hash(records) != instrument_hash(changed)
