"""Dashboard API contract tests.

After the Stage + Setup State redesign (2026-08-19):
- The dashboard serves the full screened ORD universe (count reflects the
  current scan, not a hard-coded historical number).
- Stage-first filtering (S1-S4) is the primary axis.
- The legacy ``l2`` parameter on /dashboard/cards is retained for backward
  compat but the 60m structural/momentum layers no longer produce a
  ``layer2_group`` on daily items — filtering by ``l2`` returns 0 results
  because the stage/phase taxonomy replaced it as the grouping axis.
"""
import pytest

from app import dashboard_cards, dashboard_overview


def test_dashboard_overview_is_small_and_has_coverage():
    payload = dashboard_overview()
    # count reflects the full ORD universe (delisted/inactive excluded).
    assert payload["count"] > 0
    # coverage dashboard_count comes from a separate artifact (coverage_report.json)
    # which may be stale; assert it exists but not its exact value
    assert "dashboard_count" in payload["coverage"]
    assert "legacy_taxonomy_count" in payload["coverage"]
    assert payload["coverage"]["scan_not_in_dashboard_count"] == 0
    assert "items" not in payload


def test_dashboard_cards_stage_filter_bounds_payload():
    # Stage-first filtering is the primary axis after the redesign.
    payload = dashboard_cards(stage="S2_uptrend", page=1, page_size=3)
    assert payload["total"] > 0
    assert len(payload["cards"]) == 3
    assert all(card["stage"] == "S2_uptrend" for card in payload["cards"])


def test_dashboard_cards_legacy_l2_filter_is_compat_no_op():
    # Legacy l2 parameter is accepted for backward compat but the daily
    # stage-first classifier no longer populates layer2_group, so no cards
    # match a specific L2 subgroup.
    payload = dashboard_cards(stage="S2_uptrend", l2="pullback", page=1, page_size=3)
    assert payload["total"] == 0
    assert payload["cards"] == []


def test_dashboard_cards_rejects_invalid_inputs():
    with pytest.raises(Exception):
        dashboard_cards(page_size=201)
    with pytest.raises(Exception):
        dashboard_cards(stage="S9")
    with pytest.raises(Exception):
        dashboard_cards(l2="momentum_strong")
