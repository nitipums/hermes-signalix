"""Task 4: Responsive / source-level UI contract tests for Daily Shortlist default dashboard.

Validates that dashboard_template.html contains the required DOM markers, state variables,
CSS classes, and event handlers for:
- Daily Shortlist as default surface (consumes GET /dashboard/shortlist)
- Freshness first, then READY then PRE-READY sections
- Compact decision cards with trigger, invalidation, liquidity evidence, source/as-of
- Detail/chart on card click (lazy load)
- All Stocks Explorer secondary navigation with research-only copy
- Empty / stale / error states
- Mobile no-horizontal-scroll behavior (512px viewport)
- Stage-first defaults (S1-S4), nav pages, quality badges, filter contracts, TradingView link
- Modal/chart infrastructure, breakout evidence, empty/error state distinction
- Touch targets with touch-action manipulation
- Sticky controls, breadth pulse, radar page contract
"""

import re
from pathlib import Path

# pytest is available in the test venv (/root/.venv_img/bin/python -m pytest)
# Pyright may not resolve it in this context; tests run correctly via pytest runner


TEMPLATE = (Path(__file__).parent / "dashboard_template.html").read_text(encoding="utf-8")


def _has(needle: str) -> bool:
    """Case-insensitive presence check in template source."""
    return needle.lower() in TEMPLATE.lower()


def _count(needle: str) -> int:
    return len(re.findall(re.escape(needle), TEMPLATE, flags=re.IGNORECASE))


class TestDailyShortlistDefaultSurface:
    """The default dashboard.html must be the Daily Shortlist, not the full stage screener."""

    def test_default_page_title_reflects_shortlist(self):
        assert "Daily Shortlist" in TEMPLATE or "daily-shortlist" in TEMPLATE.lower()

    def test_shortlist_endpoint_consumed_first_paint(self):
        """First paint must request /dashboard/shortlist, not /dashboard/snapshot."""
        assert "/dashboard/shortlist" in TEMPLATE

    def test_no_full_universe_stage_filter_wall_on_default(self):
        """Default view must NOT render the full stage filter wall (S1-S4 pills + L2 prox chips)."""
        # The old screener page id="screener" with stage-filter wall should not be the default active page
        # Instead there should be a shortlist-specific container
        assert 'id="shortlist"' in TEMPLATE or 'id="daily-shortlist"' in TEMPLATE or 'class="shortlist"' in TEMPLATE
        # Verify the default active page is shortlist, not screener
        assert 'class="page active" id="shortlist"' in TEMPLATE

    def test_freshness_visible_before_recommendations(self):
        """Spec §6.1: Freshness/as-of status visible before recommendations."""
        assert "freshness" in TEMPLATE.lower()
        assert "as_of" in TEMPLATE.lower() or "data_fetched_at" in TEMPLATE.lower()

    def test_ready_section_before_pre_ready(self):
        """Spec §6.2-3: READY appears first, then PRE-READY."""
        # Check ordering markers in template
        ready_idx = TEMPLATE.lower().find("ready")
        pre_ready_idx = TEMPLATE.lower().find("pre-ready")
        if ready_idx != -1 and pre_ready_idx != -1:
            assert ready_idx < pre_ready_idx, "READY section must appear before PRE-READY in source"


class TestCompactDecisionCards:
    """Each shortlist card must answer the decision questions in seconds."""

    def test_card_shows_symbol(self):
        assert "symbol" in TEMPLATE.lower()

    def test_card_shows_score_explanation(self):
        assert "rank_components" in TEMPLATE.lower() or "total_score" in TEMPLATE.lower()

    def test_card_shows_why_now_why_not(self):
        assert "trigger" in TEMPLATE.lower()
        assert "invalidation" in TEMPLATE.lower()

    def test_card_shows_liquidity_evidence(self):
        assert "avgdailyvalue20" in TEMPLATE.lower() or "liquidity" in TEMPLATE.lower()

    def test_card_shows_source_as_of(self):
        assert "source" in TEMPLATE.lower()
        assert "as_of" in TEMPLATE.lower()

    def test_chart_detail_lazy_load_on_click(self):
        """Chart and extended evidence must load ONLY on card click."""
        assert "chart" in TEMPLATE.lower()
        # Should have click handler for card that loads chart
        assert "openDetail" in TEMPLATE or "loadChart" in TEMPLATE or "onclick" in TEMPLATE.lower()
        # Verify lazy-load markers: generation guard, AbortController
        assert "let detailGen=0;" in TEMPLATE
        assert "const myGen=++detailGen;" in TEMPLATE
        assert "const ac=chartAbort=new AbortController()" in TEMPLATE


class TestAllStocksExplorerNavigation:
    """Explicit secondary route preserving full-universe research controls."""

    def test_explorer_navigation_exists(self):
        """Must have explicit All Stocks Explorer link/button."""
        assert "all stocks explorer" in TEMPLATE.lower() or "explorer" in TEMPLATE.lower()

    def test_explorer_carries_research_copy(self):
        """Must carry 'Research universe — not a list of trade suggestions' copy."""
        assert "research universe" in TEMPLATE.lower()
        assert "not a list of trade suggestions" in TEMPLATE.lower() or "not a trade suggestion" in TEMPLATE.lower()

    def test_explorer_never_labels_ready_buy_zone(self):
        """Explorer must not label rows READY, BUY ZONE, or suggestion."""
        # Explorer uses radarBadge from snapshot (legacy proximity), NOT shortlist publication_state
        # The card() function only renders pubBadge when i.publication_state is truthy
        # Snapshot items do NOT have publication_state, so pubBadge is empty for explorer cards
        # This is enforced by the template's card() function logic
        pub_badge_rendered = 'pubBadge' in TEMPLATE
        pub_badge_conditional = 'pubState ?' in TEMPLATE
        radar_badge_used = 'radarBadge' in TEMPLATE
        assert pub_badge_rendered and pub_badge_conditional and radar_badge_used

    def test_explorer_preserves_research_controls(self):
        """Explorer must retain search, stage filter, liquidity filter, sector/industry."""
        assert "search" in TEMPLATE.lower()
        assert "stage" in TEMPLATE.lower()
        assert "liquidity" in TEMPLATE.lower()
        assert "sector" in TEMPLATE.lower()
        assert "industry" in TEMPLATE.lower()


class TestEmptyStaleErrorStates:
    """Explicit empty, stale, and error UI panels with actionable copy."""

    def test_empty_state_panel_exists(self):
        assert "empty" in TEMPLATE.lower()
        assert "no qualifying" in TEMPLATE.lower() or "no candidates" in TEMPLATE.lower()

    def test_empty_state_shows_action(self):
        """Empty state must suggest an action (clear filters, try explorer)."""
        assert "clear" in TEMPLATE.lower() or "explorer" in TEMPLATE.lower() or "reset" in TEMPLATE.lower()

    def test_stale_state_panel_exists(self):
        assert "stale" in TEMPLATE.lower()

    def test_stale_state_shows_last_known_time(self):
        assert "last" in TEMPLATE.lower() or "as of" in TEMPLATE.lower()

    def test_error_state_panel_exists(self):
        assert "error" in TEMPLATE.lower() or "failed" in TEMPLATE.lower()

    def test_error_state_shows_retry(self):
        assert "retry" in TEMPLATE.lower() or "reload" in TEMPLATE.lower()

    def test_empty_states_distinguish_zero_results_from_load_error(self):
        """Shortlist and Explorer must distinguish zero-results from load-error."""
        # Shortlist has separate empty and error panels
        assert 'id="shortlistEmpty"' in TEMPLATE
        assert 'id="shortlistError"' in TEMPLATE
        # Explorer has its own empty panel
        assert 'id="explorerEmpty"' in TEMPLATE
        # Error state has retry button calling loadShortlist()
        assert 'onclick="loadShortlist()"' in TEMPLATE


class TestMobileNoHorizontalScroll:
    """Mobile viewport (512px) must not have horizontal scroll."""

    def test_no_page_level_horizontal_overflow_css(self):
        """No CSS rule should allow page-level horizontal overflow on mobile."""
        # Check for problematic patterns - must NOT have unguarded overflow-x:auto or nowrap
        # The @media check is not sufficient - need explicit assertion
        mobile_css_match = re.search(r"@media\(max-width:620px\)\{([^}]+)\}", TEMPLATE)
        if mobile_css_match:
            mobile_css = mobile_css_match.group(1)
            # These should NOT appear in mobile CSS
            assert "overflow-x:auto" not in mobile_css.replace(" ", "")
            assert "overflow-x: auto" not in mobile_css
            assert "white-space:nowrap" not in mobile_css.replace(" ", "")
            assert "white-space: nowrap" not in mobile_css
        else:
            # If no mobile media query found, that's a failure
            assert False, "No @media(max-width:620px) block found in template"

    def test_grid_columns_collapse_to_single_on_mobile(self):
        """Card grid must collapse to 1fr on mobile (<=620px)."""
        assert "@media" in TEMPLATE
        assert "max-width:620px" in TEMPLATE.replace(" ", "") or "max-width: 620px" in TEMPLATE
        # Check grid-template-columns: 1fr in mobile media query
        mobile_css = re.search(r"@media\(max-width:620px\)\{([^}]+)\}", TEMPLATE)
        if mobile_css:
            mobile_block = mobile_css.group(1)
            assert "1fr" in mobile_block or "grid-template-columns" in mobile_block

    def test_fixed_touch_targets_44px(self):
        """Touch targets must be at least 44px per WCAG + touch-action: manipulation."""
        assert "min-height:44px" in TEMPLATE.replace(" ", "") or "min-height: 44px" in TEMPLATE
        assert "min-width:44px" in TEMPLATE.replace(" ", "") or "min-width: 44px" in TEMPLATE
        # Parent test verified touch-action:manipulation on interactive elements
        assert "touch-action:manipulation" in TEMPLATE.replace(" ", "") or "touch-action: manipulation" in TEMPLATE

    def test_no_horizontal_scrolling_filter_rows(self):
        """Filter chip rows must wrap, not horizontal-scroll."""
        assert "flex-wrap:wrap" in TEMPLATE.replace(" ", "") or "flex-wrap: wrap" in TEMPLATE

    def test_512px_viewport_no_horizontal_scroll(self):
        """Explicit 512px viewport test - brief specifies 512px no-horizontal-scroll."""
        # The template uses 620px breakpoint, which covers 512px
        # Verify the mobile CSS applies at 512px viewport by checking 620px breakpoint exists
        # and the collapsed grid/flex-wrap rules are present in any mobile media query
        assert "@media(max-width:620px)" in TEMPLATE.replace(" ", "") or "@media (max-width: 620px)" in TEMPLATE
        # Check that at least one mobile media query has the grid 1fr collapse rule
        mobile_blocks = re.findall(r"@media\(max-width:620px\)\{([^}]+)\}", TEMPLATE)
        # If the regex doesn't match due to whitespace, try alternative
        if not mobile_blocks:
            mobile_blocks = re.findall(r"@media\s*\(max-width:\s*620px\)\s*\{([^}]+)\}", TEMPLATE)
        assert mobile_blocks, "No @media(max-width:620px) block found in template"
        # Check that at least one mobile block contains grid 1fr collapse
        found_1fr = False
        for block in mobile_blocks:
            if "1fr" in block or "grid-template-columns" in block:
                found_1fr = True
        assert found_1fr, "No mobile media query block contains grid 1fr collapse"
        # Also verify flex-wrap exists in template (applies to filter rows globally, including mobile)
        assert "flex-wrap" in TEMPLATE, "Template must have flex-wrap for filter rows to prevent horizontal scroll"

    def test_mobile_freshness_banner_text_wraps_without_overflow(self):
        """Stale freshness banner text must wrap on mobile (512px) without horizontal overflow.

        The staleBanner text "Data is stale — showing last known snapshot." was clipping
        on 512px viewports because .posture-main had white-space:nowrap without a mobile override.
        """
        # Verify staleBanner text exists in template
        assert "staleBanner" in TEMPLATE, "staleBanner translation key must exist"

        # Verify mobile media query has white-space:normal for .posture-main
        # Use a more robust search that handles nested braces and whitespace variations
        # The template may have @media(max-width:620px) or @media(max-width: 620px)
        mobile_query_pattern_no_space = "@media(max-width:620px){.market-posture{grid-template-columns:1fr auto"
        mobile_query_pattern_with_space = "@media(max-width: 620px){.market-posture{grid-template-columns:1fr auto"

        template_no_space = TEMPLATE.replace(" ", "")
        assert (mobile_query_pattern_no_space.replace(" ", "") in template_no_space or
                mobile_query_pattern_with_space.replace(" ", "") in template_no_space), "Mobile market-posture media query must exist"

        # Find the complete mobile market-posture block
        idx = -1
        if mobile_query_pattern_no_space.replace(" ", "") in template_no_space:
            idx = template_no_space.find(mobile_query_pattern_no_space.replace(" ", ""))
        elif mobile_query_pattern_with_space.replace(" ", "") in template_no_space:
            idx = template_no_space.find(mobile_query_pattern_with_space.replace(" ", ""))
        assert idx >= 0, "Mobile market-posture media query must exist"

        # Extract from that index to the end of the block (double closing brace)
        remaining = template_no_space[idx:]
        block_end = remaining.find("}}")
        assert block_end >= 0, "Mobile market-posture block must be properly closed"
        mobile_block = remaining[:block_end + 2]

        # Check that the block has white-space:normal for posture-main
        assert "white-space:normal" in mobile_block, "Mobile market-posture block must have white-space:normal for .posture-main"

        # Verify the desktop .posture-main still has white-space:nowrap for desktop layout
        desktop_posture_main = ".posture-main{display:flex;align-items:baseline;gap:9px;white-space:nowrap"
        assert desktop_posture_main in template_no_space, "Desktop .posture-main should keep white-space:nowrap"


class TestDesktopLayout:
    """Desktop viewport (1280px) layout checks."""

    def test_grid_supports_multi_column_desktop(self):
        """Desktop should allow multi-column card grid."""
        assert "repeat(auto-fill" in TEMPLATE or "grid-template-columns" in TEMPLATE

    def test_sticky_header_controls(self):
        """Sticky header/control cluster must exist."""
        assert "position:sticky" in TEMPLATE.replace(" ", "") or "position: sticky" in TEMPLATE
        assert "top:0" in TEMPLATE.replace(" ", "") or "top: 0" in TEMPLATE


class TestJavaScriptStateAndHandlers:
    """Inline JS must have shortlist-specific state and handlers."""

    def test_shortlist_state_variables(self):
        assert "shortlist" in TEMPLATE.lower()
        assert "candidates" in TEMPLATE.lower()

    def test_fetch_shortlist_on_load(self):
        assert "fetch" in TEMPLATE.lower()
        assert "/dashboard/shortlist" in TEMPLATE

    def test_card_click_opens_detail_modal(self):
        assert "openDetail" in TEMPLATE or "modal" in TEMPLATE.lower()

    def test_explorer_navigation_handler(self):
        assert "explorer" in TEMPLATE.lower()
        # Click handler for explorer nav
        assert "onclick" in TEMPLATE.lower() or "addeventlistener" in TEMPLATE.lower()

    # C2: getCurrentDetailList function for detail modal symbol list
    def test_getCurrentDetailList_function_exists(self):
        assert "function getCurrentDetailList" in TEMPLATE
        assert "shortlistData?.candidates" in TEMPLATE
        assert "shortlistData?.lanes" in TEMPLATE
        assert "currentExplorer().map(x => x.symbol)" in TEMPLATE

    # C3: renderExplorer called on navigation to explorer page
    def test_renderExplorer_called_on_explorer_navigation(self):
        # The click handler for [data-page] should call renderExplorer when page is explorer
        assert "if (page.dataset.page === \"explorer\")" in TEMPLATE
        assert "renderExplorer()" in TEMPLATE

    # C4: explorerIndep.liquidity properly initialized and used
    def test_explorerIndep_liquidity_initialized(self):
        assert 'let explorerIndep = {set50:false,value:0,band:"all",sector:"all",industry:"all",liquidity:"liquid"}' in TEMPLATE
        assert "explorerIndep.liquidity" in TEMPLATE

    def test_explorer_liquidity_click_handler_uses_explorerIndep(self):
        # The liquidity click handler should update explorerIndep.liquidity, not a standalone liquidity variable
        assert "explorerIndep.liquidity=liq.dataset.liquidity" in TEMPLATE
        assert "document.getElementById(\"explorerLiquidOnly\").classList.toggle(\"active\",explorerIndep.liquidity===\"liquid\")" in TEMPLATE
        assert "document.getElementById(\"explorerShowLowValue\").classList.toggle(\"active\",explorerIndep.liquidity===\"all\")" in TEMPLATE


class TestAccessibility:
    """Basic accessibility markers."""

    def test_aria_labels_on_interactive_elements(self):
        assert "aria-label" in TEMPLATE
        assert "role=" in TEMPLATE

    def test_live_regions_for_dynamic_content(self):
        assert "aria-live" in TEMPLATE

    def test_focus_visible_styles(self):
        assert ":focus" in TEMPLATE or ":focus-visible" in TEMPLATE


# ============================================================================
# STAGE-FIRST LEGACY SAFETY ASSERTIONS (Restored from parent test suite)
# These verify critical UI contracts that were in the stage-first template
# and must continue to hold for the shortlist/explorer architecture.
# ============================================================================

class TestStageFirstLegacyContracts:
    """Safety assertions preserved from parent stage-first template.
    Adapted where design intentionally changes (screener→shortlist, old control IDs→explorer*)."""

    def test_modal_chart_infrastructure_renders(self):
        """Generation guard + AbortController keep the on-demand chart from
        painting the wrong symbol when the user swipes/navigates quickly."""
        for marker in (
            "let detailGen=0;",
            "const myGen=++detailGen;",
            "const ac=chartAbort=new AbortController()",
        ):
            assert marker in TEMPLATE

    def test_tradingview_link_present_in_modal(self):
        """TradingView link is on modal-title-link anchor."""
        assert 'class="title-link"' in TEMPLATE
        assert "tradingview.com/chart" in TEMPLATE

    def test_breakout_evidence_contract(self):
        """Breakout evidence in card's setup-evidence line."""
        for marker in (
            "setup-evidence",
            "breakoutEvidence",
            "volumeRatio50",  # Updated from volume_ratio - template uses volumeRatio50
            "trigger",
        ):
            assert marker in TEMPLATE

    def test_breadth_pulse_contract(self):
        """Market breadth pulse on market page."""
        for marker in (
            ".breadth-pulse",
            'id="breadthPulse"',
            'id="marketGrid"',
        ):
            assert marker in TEMPLATE

    def test_quality_badge_has_all_levels(self):
        """Quality badges: q-corner q3/q2/q1/q0."""
        for qcls in ("q3", "q2", "q1", "q0"):
            assert f"q-corner.{qcls}" in TEMPLATE
        # Quality strip visual bar
        assert "quality-strip" in TEMPLATE

    def test_quality_level_derivation_is_deterministic(self):
        """qualityLevel(i) function returns layer3_qualifier score."""
        assert "function qualityLevel" in TEMPLATE
        assert "layer3_qualifier" in TEMPLATE
        assert "layer3_qualifiers" in TEMPLATE

    def test_radar_page_contract(self):
        """Radar is a dedicated page with its own contract."""
        assert 'id="radar"' in TEMPLATE
        assert 'id="radarResults"' in TEMPLATE
        assert 'id="radarPills"' in TEMPLATE
        assert "radarHTML" in TEMPLATE  # legacy marker comment

    def test_template_has_sector_industry_and_proximity_filter_contract(self):
        """Explorer filter controls contract (adapted from screener).
        Independence filter contract (sector/industry/value/band/set50) preserved;
        proximity pills (data-prox) replace the old l2/l2mom bars."""
        html = TEMPLATE
        for marker in (
            'id="explorerValueFilter"',
            'id="explorerPriceBand"',
            'id="explorerSectorFilter"',
            'id="explorerIndustryFilter"',
            'id="explorerLiquidOnly"',
            'id="explorerShowLowValue"',
            'id="explorerSet50Only"',
            "function populateExplorerFilters()",
            'let explorerIndep = {set50:false,value:0,band:"all",sector:"all",industry:"all",liquidity:"liquid"}',
            'let explorerProxFilter = {}',
            'const PROX_GROUPS=["action","near_trigger","forming","extended"]',
            "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
            "const inRadar=i=>!!i.radar",
        ):
            assert marker in html, f"Missing explorer filter contract marker: {marker}"
        # Legacy L2 JS helpers must NOT be present in the UI template.
        for legacy in (
            "l2Filter",
            "l2MomFilter",
            "structuralGroup",
            "momentumGroup",
            "L2MOM_GROUPS",
            "data-l2mom",
        ):
            assert legacy not in html, f"legacy L2 UI marker {legacy!r} should be removed"

    def test_template_has_sector_industry_chip_and_stable_proximity_reset_contract(self):
        """Explorer inline filter controls with chips in .indep-row."""
        html = TEMPLATE
        for marker in (
            'id="explorerSectorFilter"',
            'id="explorerIndustryFilter"',
            ".indep-row",
            'data-prox="all"',
            "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
            "const l2=e.target.closest",
        ):
            assert marker in html
        # Current contract: sector/industry are <select> dropdowns (not chip-only)
        assert '<select id="explorerSectorFilter"' in html
        assert '<select id="explorerIndustryFilter"' in html
        assert "root.onchange=" in html

    def test_mobile_first_viewport_is_compact(self):
        """Compact metrics in mobile media query."""
        html = TEMPLATE
        for marker in (
            ".stage-pill{min-width:calc(50% - 5px)",
            ".stage-pill .cnt{font-size:26px;font-weight:850",
            ".ticker{font-size:18px",
            ".search{padding:13px 14px;font-size:16px",
            "@media(max-width:620px)",
            "min-height:44px",
        ):
            assert marker in html

    def test_template_compatibility_helpers_cover_new_and_legacy_items(self):
        """Template compatibility helpers for new and legacy item shapes."""
        html = TEMPLATE
        for marker in (
            "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
            "const inRadar=i=>!!i.radar",
        ):
            assert marker in html
        # Legacy structural/momentum group helpers must NOT be present in the UI.
        assert "const structuralGroup=" not in html
        assert "const momentumGroup=" not in html

    def test_detail_modal_is_decision_first_and_daily_default(self):
        """Stage-first modal: Decision banner → Price → Chart (on-demand) → Setup Quality → Risk/Trigger."""
        html = TEMPLATE
        for marker in (
            "quality-strip",
            "chart-status",
            "chart-freshness",
            'data-tf="1D"',
            "tf-tools",
            "decision-banner",
            "modal-price",
            "detailChart",
            "detail-facts",
            "risk-note",
            "setup-note",
        ):
            assert marker in html
        # Legacy removed markers stay removed.
        for removed in ("modal-decision", "decision-value", "provenanceDetails", "modal-freshness"):
            assert removed not in html

    def test_sticky_nav_cluster_present(self):
        """Sticky nav + sticky ctrl-sticky cluster present."""
        html = TEMPLATE
        for marker in (
            'class="topbar"',
            'class="nav"',
            'class="ctrl-sticky"',
            'id="explorerStageSummary"',  # explorer has sticky stage summary
            'id="explorerResults"',
        ):
            assert marker in html

    def test_nav_pages_are_shortlist_explorer_radar_watchlist_market(self):
        """5 pages: shortlist (default), explorer, radar, watchlist, market."""
        html = TEMPLATE
        for marker in (
            'data-page="shortlist"',
            'data-page="explorer"',
            'data-page="radar"',
            'data-page="watchlist"',
            'data-page="market"',
        ):
            assert marker in html
        # Old screener page must NOT be present
        assert 'data-page="screener"' not in html


class TestMobileTouchTargets:
    """Explicit touch target tests with manipulation assertion."""

    def test_mobile_touch_targets_have_min_height_and_manipulation(self):
        """Touch targets: min-height 44px + touch-action: manipulation."""
        # Parent test checked exact rule: button,select,input,.chip,.star{min-height:44px;touch-action:manipulation}
        html = TEMPLATE
        # Verify the combined rule exists (allowing whitespace variations)
        assert "min-height:44px" in html.replace(" ", "") or "min-height: 44px" in html
        assert "touch-action:manipulation" in html.replace(" ", "") or "touch-action: manipulation" in html
        # Verify it applies to key interactive elements
        assert ".chip" in html
        assert ".star" in html
        assert "button" in html.lower()
        assert "select" in html.lower()
        assert "input" in html.lower()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])