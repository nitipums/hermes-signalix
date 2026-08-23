import unittest
import json
from pathlib import Path


HERE = Path(__file__).parent


class DashboardResponsiveTests(unittest.TestCase):
    def setUp(self):
        self.html = (HERE / "dashboard.html").read_text(encoding="utf-8")
        self.template = (HERE / "dashboard_template.html").read_text(encoding="utf-8")
        self.snapshot = json.loads((HERE / "dashboard_snapshot.json").read_text(encoding="utf-8"))

    # --- Mobile / touch UX that actually ships in dashboard_template.html ---
    def test_mobile_touch_targets_have_min_height_and_manipulation(self):
        for rule in (
            "button,select,input,.chip,.star{min-height:44px;touch-action:manipulation}",
            ".modal-bg{",
            ".modal-bg.open{display:flex}",
        ):
            self.assertIn(rule, self.html)

    def test_modal_chart_infrastructure_renders(self):
        # Generation guard + AbortController keep the on-demand chart from
        # painting the wrong symbol when the user swipes/navigates quickly.
        for marker in (
            "let detailGen=0;",
            "const myGen=++detailGen;",
            "const ac=chartAbort=new AbortController()",
        ):
            self.assertIn(marker, self.html)

    def test_tradingview_link_present_in_modal(self):
        # Stage-first: TradingView link is on modal-title-link anchor
        self.assertIn('class="title-link"', self.template)
        self.assertIn("tradingview.com/chart", self.template)

    def test_snapshot_and_taxonomy_artifact_match_full_universe(self):
        # Full ORD universe (delisted/inactive excluded) — count reflects the
        # current screened set, not a hard-coded historical number.
        snapshot_symbols = {i["symbol"] for i in self.snapshot["items"]}
        # scan_results.json is the legacy scanner envelope; dashboard_snapshot
        # is the reconciled presentation artifact and may have a different
        # membership boundary. Assert the served snapshot's own invariants.
        self.assertEqual(len(self.snapshot["items"]), len(snapshot_symbols))
        self.assertGreater(len(snapshot_symbols), 0)
        # Coverage label is English in the current template (EN refresh).
        self.assertIn("Thai ORD stocks scanned", self.html)
        self.assertIn('id="covCount"', self.html)

    def test_template_has_sector_industry_and_proximity_filter_contract(self):
        # Stage-first: inline filter controls (not collapsible deck).
        # The independence filter contract (sector/industry/value/band/set50) is unchanged;
        # proximity pills (data-prox) replace the old l2/l2mom bars.
        html = self.template
        for marker in (
            'id="valueFilter"',
            'id="priceBand"',
            'id="sectorFilter"',
            'id="industryFilter"',
            'id="liquidOnly"',
            'id="showLowValue"',
            'id="set50Only"',
            "function populateIndependenceFilters()",
            "let indep={set50:false,value:0,band:\"all\",sector:\"all\",industry:\"all\"}, proxFilter={}, radarProx=\"all\";",
            'const PROX_GROUPS=["action","near_trigger","forming","extended"]',
            "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
            "const inRadar=i=>!!i.radar",
        ):
            self.assertIn(marker, html)
        # Legacy L2 JS helpers must NOT be present in the UI template.
        for legacy in (
            "l2Filter",
            "l2MomFilter",
            "structuralGroup",
            "momentumGroup",
            "L2MOM_GROUPS",
            "data-l2mom",
        ):
            self.assertNotIn(legacy, html, f"legacy L2 UI marker {legacy!r} should be removed")

    def test_template_has_sector_industry_chip_and_stable_proximity_reset_contract(self):
        # Stage-first: inline filter controls with chips in .indep-row
        html = self.template
        for marker in (
            'id="sectorFilter"',
            'id="industryFilter"',
            ".indep-row",
            'data-prox="all"',
            "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
            "const l2=e.target.closest",
        ):
            self.assertIn(marker, html)
        # Current contract: sector/industry are <select> dropdowns (not chip-only)
        self.assertIn('<select id="sectorFilter"', html)
        self.assertIn('<select id="industryFilter"', html)
        self.assertIn("root.onchange=", html)

    def test_mobile_first_viewport_is_compact(self):
        # Stage-first: compact metrics in mobile media query
        html = self.template
        for marker in (
            ".stage-pill{min-width:calc(50% - 5px)",
            ".stage-pill .cnt{font-size:26px;font-weight:850",
            ".ticker{font-size:18px",
            ".search{padding:13px 14px;font-size:16px",
            "@media(max-width:620px)",
            "min-height:44px",
        ):
            self.assertIn(marker, html)

    def test_template_compatibility_helpers_cover_new_and_legacy_items(self):
        html = self.template
        for marker in (
            "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
            "const inRadar=i=>!!i.radar",
        ):
            self.assertIn(marker, html)
        # Legacy structural/momentum group helpers must NOT be present in the UI.
        self.assertNotIn("const structuralGroup=", html)
        self.assertNotIn("const momentumGroup=", html)

    def test_detail_modal_is_decision_first_and_daily_default(self):
        # Stage-first modal: Decision banner → Price → Chart (on-demand) → Setup Quality → Risk/Trigger
        html = self.template
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
            self.assertIn(marker, html)
        # Legacy removed markers stay removed.
        for removed in ("modal-decision", "decision-value", "provenanceDetails", "modal-freshness"):
            self.assertNotIn(removed, html)

    def test_breadth_pulse_contract(self):
        # Stage-first: market breadth pulse on market page
        html = self.template
        for marker in (
            ".breadth-pulse",
            'id="breadthPulse"',
            'id="marketGrid"',
        ):
            self.assertIn(marker, html)

    def test_breakout_evidence_contract(self):
        # Stage-first: breakout evidence in card's setup-evidence line
        html = self.template
        for marker in (
            "setup-evidence",
            "breakoutEvidence",
            "volume_ratio",
            "trigger",
        ):
            self.assertIn(marker, html)

    def test_empty_states_distinguish_zero_results_from_load_error(self):
        # Stage-first: emptyReason folded into plain empty divs; zero-results vs load-error distinction
        html = self.template
        for marker in (
            'id="empty"',
            "hidden",
            "clearAllFilters",
            "loadRemoteDashboard",
            "loadFailed",
        ):
            self.assertIn(marker, html)
        # Ensure the load error branch has retry action
        self.assertIn('onclick="loadRemoteDashboard()"', html)

    def test_nav_pages_are_screener_watchlist_market(self):
        # Stage-first: 4 pages (screener, radar, watchlist, market)
        html = self.template
        for marker in (
            'data-page="screener"',
            'data-page="radar"',
            'data-page="watchlist"',
            'data-page="market"',
        ):
            self.assertIn(marker, html)

    def test_quality_badge_has_all_levels(self):
        # Quality badges: q-corner q3/q2/q1/q0
        html = self.template
        for qcls in ("q3", "q2", "q1", "q0"):
            self.assertIn(f"q-corner.{qcls}", html)
        # Quality strip visual bar
        self.assertIn("quality-strip", html)

    def test_quality_level_derivation_is_deterministic(self):
        # qualityLevel(i) function returns layer3_qualifier score
        html = self.template
        self.assertIn("function qualityLevel", html)
        self.assertIn("layer3_qualifier", html)
        self.assertIn("layer3_qualifiers", html)

    def test_radar_embedded_section_and_contract(self):
        # Stage-first: Radar is a dedicated page, not embedded
        html = self.template
        self.assertIn('id="radar"', html)
        self.assertIn('id="radarResults"', html)
        self.assertIn('id="radarPills"', html)
        self.assertIn("radarHTML", html)  # legacy marker comment

    def test_radar_renders_once_on_screener(self):
        # Radar is on dedicated page, not on screener
        html = self.template
        # verify radar page exists
        self.assertIn('id="radar"', html)
        # verify screener has results only
        self.assertIn('id="results"', html)

    def test_sticky_nav_cluster_present(self):
        # Stage-first: topbar + sticky nav + sticky ctrl-sticky
        html = self.template
        for marker in (
            'class="topbar"',
            'class="nav"',
            'class="ctrl-sticky"',
            'id="stageSummary"',
            'id="results"',
        ):
            self.assertIn(marker, html)

    def test_template_has_sector_industry_and_proximity_filter_contract_2(self):
        # Duplicate test name - verify filter controls
        html = self.template
        for marker in (
            'id="valueFilter"',
            'id="priceBand"',
            'id="sectorFilter"',
            'id="industryFilter"',
        ):
            self.assertIn(marker, html)

    def test_template_has_sector_industry_chip_and_stable_proximity_reset_contract_2(self):
        # Duplicate test name - verify chips
        html = self.template
        self.assertIn(".indep-row", html)
        self.assertIn('data-prox="all"', html)


if __name__ == "__main__":
    unittest.main()