import pytest

from active_universe import resolve_active_universe


ACTIVE = [" bbb ", "", "AAA", "AAA", "  ", "DR_ONLY", "NO_BUY", "UNKNOWN"]

MARGINABLE_RECORDS = {
    "AAA": {"instrument_type": "ORD", "can_buy": True},
    "BBB": {"instrument_type": "ORD", "can_buy": True},
    "DR_ONLY": {"instrument_type": "DR", "can_buy": True},
    "NO_BUY": {"instrument_type": "ORD", "can_buy": False},
}


def marginable_fixture(active):
    eligible = sorted(
        symbol for symbol in set(active)
        if (record := MARGINABLE_RECORDS.get(symbol))
        and record["instrument_type"] == "ORD"
        and record["can_buy"] is True
    )
    return eligible, {
        "universe_filter": "marginable_long",
        "base_active_ord_count": len(set(active)),
        "eligible_count": len(eligible),
        "excluded_count": len(set(active)) - len(eligible),
        "excluded_reason": "not_marginable_long",
        "schema_version": "fixture.marginable.v1",
        "source_document": "fixture-owner-list.pdf",
        "effective_date": "2026-09-19",
    }


def test_marginable_long_is_canonical_and_preserves_literal_manifest():
    symbols, manifest = resolve_active_universe(
        object(), "marginable_long", active_symbols=ACTIVE,
        marginable_resolver=marginable_fixture,
    )

    assert symbols == ["AAA", "BBB"]
    assert manifest == {
        "universe_filter": "marginable_long",
        "base_active_ord_count": 5,
        "eligible_count": 2,
        "excluded_count": 3,
        "excluded_reason": "not_marginable_long",
        "schema_version": "fixture.marginable.v1",
        "source_document": "fixture-owner-list.pdf",
        "effective_date": "2026-09-19",
        "universe_membership": {
            "symbols": ["AAA", "BBB"],
            "digest": "518d1d0ec11d9c4a85cbc86de03771a3cc2b7c35eb40e6b70c08b0c736552490",
        },
        "audit_only": False,
    }


def test_active_ord_is_explicit_audit_mode_with_injected_loader():
    calls = []

    def loader(connection):
        calls.append(connection)
        return [" zzz ", "AAA", "AAA", ""]

    symbols, manifest = resolve_active_universe(object(), "active_ord", active_symbol_loader=loader)

    assert symbols == ["AAA", "ZZZ"]
    assert manifest["audit_only"] is True
    assert manifest["base_active_ord_count"] == 2
    assert manifest["eligible_count"] == 2
    assert manifest["excluded_count"] == 0
    assert manifest["excluded_reason"] is None
    assert manifest["universe_membership"] == {
        "symbols": ["AAA", "ZZZ"],
        "digest": "6f56b319c1d077d07bedc9baaf1a0944cc9ea72f96eec5574c3517827bea1c16",
    }
    assert len(calls) == 1


def test_empty_universe_has_literal_empty_membership_and_repeatable_result():
    first = resolve_active_universe(object(), "active_ord", active_symbols=[])
    second = resolve_active_universe(object(), "active_ord", active_symbols=[])

    assert first == second
    assert first[0] == []
    assert first[1]["base_active_ord_count"] == 0
    assert first[1]["universe_membership"] == {
        "symbols": [],
        "digest": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    }


def test_unknown_filter_fails_closed():
    with pytest.raises(ValueError, match="unknown universe filter"):
        resolve_active_universe(object(), "everything", active_symbols=["AAA"])
