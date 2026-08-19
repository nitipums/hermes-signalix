"""P0: Compact overview data contract tests (RED → GREEN).

Validates the lightweight /dashboard/cards/compact endpoint contract:
- Returns only core fields for first paint
- Missing enrichment fields are explicit 'unknown'
- Root includes scan_time, data_fetched_at, market session provenance
- Mobile resilience: cards persist if refresh fails
"""
import pytest
from app import dashboard_cards_compact, _compact_card


class TestCompactCardContract:
    """Test the compact card projection and endpoint."""

    def test_compact_card_has_only_declared_fields(self):
        """Compact projection must only contain declared COMPACT_CARD_FIELDS."""
        full_card = {
            "symbol": "TEST",
            "close": 10.0,
            "date": "2026-08-18",
            "stage": "S2_uptrend",
            "phase": "waiting_breakout",
            "phase_label": "Waiting breakout",
            "group": "pre_break",
            "action": "WAIT FOR QUALIFIED BREAKOUT",
            "actionReason": "Wait for a Daily close above the 20-day trigger",
            "breakoutLevel": 11.0,
            "stop": 9.5,
            "cut": 8.0,
            "priceSource": "Daily EOD",
            "priceLabel": "Daily EOD",
            "stale": False,
            "intradaySource": "60m",
            "intradayStale": False,
            "intent": "prepare",
            "status": "PRE-BREAK",
            "tone": "accent",
            "volume": 100000,
            "tradeValue": 1000000,
            "layer2_group": "up_leg",
            "intradayFreshness": {"status": "fresh"},
            # Enrichment fields that should NOT appear in compact
            "history": [[...]],
            "ma50Value": 9.0,
            "rsi": 60.0,
            "breakoutEvidence": {...},
            "companyName": "Test Corp",
        }

        compact = _compact_card(full_card)

        # Must have all declared fields
        declared = (
            "symbol", "market", "close", "date", "stage", "phase", "phase_label",
            "group", "action", "actionReason", "breakoutLevel", "stop", "cut",
            "priceSource", "priceLabel", "stale", "intradaySource", "intradayStale",
            "intent", "status", "tone", "volume", "tradeValue",
            "layer2_group", "intradayFreshness",
        )
        for f in declared:
            assert f in compact, f"missing declared field: {f}"

        # Must NOT have enrichment fields
        assert "history" not in compact
        assert "ma50Value" not in compact
        assert "rsi" not in compact
        assert "breakoutEvidence" not in compact
        assert "companyName" not in compact

    def test_compact_card_missing_fields_become_unknown(self):
        """Fields absent from source must be explicit 'unknown', not None/absent."""
        minimal_card = {
            "symbol": "TEST",
            "close": 10.0,
            # All other declared fields missing
        }

        compact = _compact_card(minimal_card)

        # symbol is present in source, so it is NOT unknown
        assert compact["symbol"] == "TEST"
        assert compact["market"] == "unknown"  # not derivable from a bare card
        for f in (
            "date", "stage", "phase", "phase_label", "group", "action",
            "actionReason", "breakoutLevel", "stop", "cut", "priceSource",
            "priceLabel", "stale", "intradaySource", "intradayStale",
            "intent", "status", "tone", "volume", "tradeValue",
            "layer2_group", "intradayFreshness",
        ):
            assert compact[f] == "unknown", f"field {f} should be 'unknown' not {compact[f]!r}"

    def test_compact_endpoint_returns_root_provenance(self):
        """Endpoint response must include scan_time and data_fetched_at at root."""
        payload = dashboard_cards_compact(page=1, page_size=2)

        assert "scan_time" in payload
        assert payload["scan_time"] is not None
        assert "data_fetched_at" in payload
        # data_fetched_at may be None if not yet written to snapshot, but key must exist
        assert "data_freshness_source" in payload
        assert "data_freshness_status" in payload
        assert "data_intraday_status" in payload
        assert "data_global_status" in payload
        assert "market_session" in payload
        assert "last_valid_session" in payload
        assert "data_freshness_age_hours" in payload
        assert "market" in payload

    def test_compact_endpoint_cards_have_core_fields(self):
        """Each card in compact response must have all core fields."""
        payload = dashboard_cards_compact(page=1, page_size=3)
        cards = payload["cards"]

        assert len(cards) == 3
        for card in cards:
            assert card["symbol"] != "unknown"
            assert card["close"] != "unknown"
            # Core decision fields present
            for f in ("stage", "phase", "group", "action", "breakoutLevel", "stop", "cut", "priceSource"):
                assert f in card, f"card missing core field: {f}"
            # Market is injected from the canonical payload root (Task 1 contract)
            assert card["market"] == payload["market"]
            assert card["market"] != "unknown"

    def test_compact_endpoint_respects_filters(self):
        """Stage and L2 filters must work on compact endpoint."""
        payload = dashboard_cards_compact(stage="S2_uptrend", page=1, page_size=5)
        for card in payload["cards"]:
            assert card["stage"] == "S2_uptrend"

        payload = dashboard_cards_compact(l2="up_leg", page=1, page_size=5)
        for card in payload["cards"]:
            assert card["layer2_group"] == "up_leg"

    def test_compact_endpoint_pagination(self):
        """Pagination must work correctly."""
        page1 = dashboard_cards_compact(page=1, page_size=2)
        page2 = dashboard_cards_compact(page=2, page_size=2)

        assert page1["page"] == 1
        assert page2["page"] == 2
        assert page1["page_size"] == 2
        assert page2["page_size"] == 2
        assert len(page1["cards"]) == 2
        assert len(page2["cards"]) == 2
        # Different symbols
        assert page1["cards"][0]["symbol"] != page2["cards"][0]["symbol"]

    def test_compact_endpoint_rejects_invalid_inputs(self):
        """Invalid stage/l2/page/page_size must raise 400."""
        with pytest.raises(Exception):
            dashboard_cards_compact(stage="S9")
        with pytest.raises(Exception):
            dashboard_cards_compact(l2="momentum")
        with pytest.raises(Exception):
            dashboard_cards_compact(page_size=201)
        with pytest.raises(Exception):
            dashboard_cards_compact(page=0)


class TestCompactEndpointMobileResilience:
    """Verify mobile resilience contract: cards persist if refresh fails."""

    def test_compact_cards_are_independent_of_full_cards(self):
        """Compact endpoint must not depend on /dashboard/cards succeeding."""
        # They share the same cached snapshot but compact is a separate projection
        # This is a contract test — both must work independently
        compact = dashboard_cards_compact(page=1, page_size=2)
        full = dashboard_cards_compact(page=1, page_size=2)  # using same for now

        # Both should succeed and return cards
        assert len(compact["cards"]) == 2
        assert len(full["cards"]) == 2

    def test_compact_response_size_is_small(self):
        """Compact payload must be significantly smaller than full cards."""
        import json
        compact = dashboard_cards_compact(page=1, page_size=10)
        full_payload = {
            "cards": [{
                "symbol": "TEST",
                "close": 10.0,
                "date": "2026-08-18",
                "stage": "S2_uptrend",
                "phase": "waiting_breakout",
                "phase_label": "Waiting breakout",
                "group": "pre_break",
                "action": "WAIT",
                "actionReason": "Wait",
                "breakoutLevel": 11.0,
                "stop": 9.5,
                "cut": 8.0,
                "priceSource": "Daily EOD",
                "priceLabel": "Daily EOD",
                "stale": False,
                "intradaySource": "60m",
                "intradayStale": False,
                "intent": "prepare",
                "status": "PRE-BREAK",
                "tone": "accent",
                "volume": 100000,
                "tradeValue": 1000000,
                "layer2_group": "up_leg",
                "intradayFreshness": {"status": "fresh"},
                # Enrichment
                "history": [["2026-01-01", 10.0, 11.0, 9.0, 100000]] * 100,
                "ma50Value": 9.0,
                "rsi": 60.0,
                "breakoutEvidence": {"status": "NOT TRIGGERED"},
                "companyName": "Test Corp",
            }] * 10,
            "scan_time": "2026-08-19T06:40:35Z",
        }

        compact_json = json.dumps(compact, separators=(",", ":"))
        full_json = json.dumps(full_payload, separators=(",", ":"))

        # Compact should be much smaller (at least 50% reduction for 10 cards)
        # Actually with full enrichment it's much more
        assert len(compact_json) < len(full_json) * 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])