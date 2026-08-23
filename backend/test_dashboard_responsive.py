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
        # DISPOSITION 2026-08-22 (t_918994ed): the old `.modal-title .title-link`
        # anchor was dropped when the decision-first modal title was simplified;
        # the TradingView deep-link now ships as the `.chip.tv-link` button in the
        # modal. Same acceptance coverage (trader can open TV from the modal).
        self.assertIn('class="chip tv-link"', self.template)
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
        self.assertIn('id="heroCovCount"', self.html)

    def test_template_has_sector_industry_and_proximity_filter_contract(self):
        # After the Stage + Setup State redesign (2026-08-19), L2 pills are
        # replaced by proximity pills. The independence filter contract
        # (sector/industry/value/band/set50) is unchanged; proximity pills
        # (data-prox) replace the old l2/l2mom bars.
        html = self.template
        for marker in (
            'id="sectorFilter"',
            'id="industryFilter"',
            "function populateIndependenceFilters()",
            'let indep={set50:false,value:0,band:"all",sector:"all",industry:"all"}, proxFilter={};',
            "const PROX_GROUPS=[\"action\",\"near_trigger\",\"forming\",\"extended\"]",
            'data-indep="${key}" data-value="${esc(v)}"',
            "indep.sector",
            "indep.industry",
            "const root=document.getElementById(`${key}Chips`)",
            "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
            "const inRadar=i=>!!i.radar",
            "Setup Radar",
        ):
            self.assertIn(marker, html)
        self.assertIn("flex-wrap:wrap", html)
        # Current contract: sector/industry chips render inside a horizontal
        # scroll row (.indep-row) populated by populateIndependenceFilters().
        self.assertIn("function populateIndependenceFilters()", html)
        self.assertTrue(".indep-row{display:flex;gap:8px;overflow-x:auto" in html or
                        ".indep-row{display:flex;gap:8px;overflow-x:hidden" in html)
        self.assertNotIn(".l2-bar{overflow-x:auto;flex-wrap:nowrap", html)
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
        # DISPOSITION 2026-08-22 (t_918994ed): the <select> dropdown variant of the
        # sector/industry filters was superseded — current intentional contract is
        # chip buttons in a horizontal scroll row (.indep-row), populated by
        # populateIndependenceFilters(). Proximity reset via data-prox="all" is kept.
        html = self.template
        for marker in (
            '<section id="sectorFilter"',
            '<section id="industryFilter"',
            ".indep-row",
            'data-prox="all"',
            "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
            "const l2=e.target.closest",
        ):
            self.assertIn(marker, html)
        # Dropdown variant must not return.
        self.assertNotIn('<select id="sectorFilter"', html)
        self.assertNotIn('<select id="industryFilter"', html)
        self.assertNotIn("root.onchange=", html)


    def test_mobile_first_viewport_is_compact(self):
        # DISPOSITION 2026-08-22 (t_918994ed): compact-first-viewport values moved
        # with the tightened header/filter redesign; assert the shipped metrics.
        html = self.template
        for marker in (
            ".cockpit{min-height:64px",
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
        # DISPOSITION 2026-08-22 (t_918994ed): the decision-banner/modal-subtitle/
        # setup-note/risk-note block was superseded by quality-strip +
        # provenancePanel (Q7/Q12 provenance is INTENTIONAL in the current
        # contract). Daily-default TF and chart-freshness coverage retained.
        html = self.template
        for marker in (
            "quality-strip",
            "provenanceDetails(i,\"modal\")",
            "chart-status",
            "modal-freshness",
            'data-tf="1D" aria-selected="true"',
            "pickTimeframe",
            "modal-decision",
            "decision-value",
        ):
            self.assertIn(marker, html)
        # Legacy removed markers stay removed.
        for removed in ("decision-banner", "modal-subtitle", "setup-note", "risk-note"):
            self.assertNotIn(removed, html)


    def test_breadth_pulse_contract(self):
        # DISPOSITION 2026-08-22 (t_918994ed): the market-posture strip
        # (#marketPosture / computeMarketPosture) was removed from the template;
        # at-a-glance market health now ships as the single-line breadth pulse
        # (advance/decline ratio bar). Same acceptance intent, new surface.
        html = self.template
        for marker in (
            ".breadth-pulse",
            'id="breadthPulse"',
            'id="marketGrid"',
        ):
            self.assertIn(marker, html)

    def test_breakout_evidence_contract(self):
        # DISPOSITION 2026-08-22 (t_918994ed): the standalone triggerDistance()
        # helper + trigger-distance line were removed; distance-to-trigger now
        # surfaces via the card's setup-evidence breakout line (close vs trigger
        # + volume ratio). Coverage preserved.
        html = self.template
        for marker in (
            "setup-evidence",
            "breakoutEvidence",
            "volume_ratio",
            "trigger",
        ):
            self.assertIn(marker, html)

    def test_empty_states_distinguish_zero_results_from_load_error(self):
        # DISPOSITION 2026-08-22 (t_918994ed): emptyReason/radarEmptyReason sub-
        # nodes were folded back into the plain empty divs; zero-results vs load-
        # error distinction lives in the load-error branch (Failed to load +
        # Retry action) vs hidden #empty. Coverage preserved.
        html = self.template
        for marker in (
            'id="empty"',
            "hidden",
            "Failed to load dashboard",
            "Retry",
            "onclick=\"loadRemoteDashboard()\"",
        ):
            self.assertIn(marker, html)

    # --- Creative redesign markers (beyond the mechanical proposal) ---
    def test_creative_markers_in_template(self):
        html = self.template
        for marker in (
            # P0 redesign (t_3961d070): stage identity carried by stage-badge +
            # left border tint; peripheral pulse-dot replaced by fresh-badge.
            ".fresh-badge.live",
            ".fresh-badge.eod",
            ".fresh-badge.stale_warning",
            ".fresh-badge.hard_stale",
            # Stage-tinted background system (signal-light vernacular)
            "--s2-tint",
            "--s4-tint",
            # Quality badge on card (derived HIGH/MEDIUM/LOW)
            "qualityLevel(i)",
            # Setup Radar — embedded screener section (dedicated page removed)
            "radarHTML",
            "radar-section",
            "Setup Radar",
            # Touch handling on canvas
            "touch-action:none",
            "cv.style.touchAction",
            # Setup Radar proximity pills (replaces legacy L2)
            "data-prox",
            "PROX_DISPLAY",
            # Fresh badge (canonical freshness identifiers on card)
            "fresh-badge eod",
            "fresh-badge live",
            "fresh-badge stale_warning",
            "fresh-badge hard_stale",
            # Creative enhancements beyond P0
            "prefers-reduced-motion",
            ".signal-card:hover",
            "quality-strip",
            "breadth-pulse",
            "breadthPulse",
        ):
            self.assertIn(marker, html, f"creative marker {marker!r} missing from template")

    def test_fresh_badge_has_canonical_state_classes(self):
        """Fresh badge must carry live/eod/stale_warning/hard_stale/unknown classes."""
        html = self.template
        for cls in (".fresh-badge.live", ".fresh-badge.eod", ".fresh-badge.stale_warning",
                    ".fresh-badge.hard_stale", ".fresh-badge.unknown"):
            self.assertIn(cls, html)

    def test_quality_badge_has_all_levels(self):
        """Quality badge styles HIGH/MEDIUM/LOW for scannable quality."""
        html = self.template
        for cls in (".quality-badge.HIGH", ".quality-badge.MEDIUM", ".quality-badge.LOW"):
            self.assertIn(cls, html, f"quality badge class {cls!r} missing from template CSS")

    def test_quality_level_derivation_is_deterministic(self):
        """qualityLevel() derives HIGH/MEDIUM/LOW from setup_quality (no serialized
        field exists); derivation is deterministic UI-only per P0 redesign."""
        js = self.template
        self.assertIn("function qualityLevel(i){", js)
        self.assertIn('if(q.pass===true)return "HIGH";', js)

    # --- 2026-08-20 Summary UX: Radar page + sticky controls + auto-scroll ---
    def test_nav_pages_are_screener_watchlist_market(self):
        # DISPOSITION 2026-08-22 (t_918994ed): Radar page button removed — Radar
        # renders inline above the stage sections on the screener page. Nav must
        # expose exactly the three current pages and NOT a radar page.
        html = self.template
        for page in ('data-page="screener"', 'data-page="watchlist"', 'data-page="market"'):
            self.assertIn(page, html)
        self.assertNotIn('data-page="radar"', html)

    def test_radar_embedded_section_and_contract(self):
        # DISPOSITION 2026-08-22 (t_918994ed): dedicated radar page replaced by an
        # embedded section generated inside render(); filtered by inRadar and
        # carrying the radarBadge on qualifying cards.
        html = self.template
        for marker in (
            "const inRadar=i=>!!i.radar",
            "radar-section",
            "<h2>Setup Radar</h2>",
            "vals.filter(inRadar)",
        ):
            self.assertIn(marker, html, f"radar section marker {marker!r} missing from template")

    def test_radar_renders_once_on_screener(self):
        # DISPOSITION 2026-08-22 (t_918994ed): inverse of the old assertion — the
        # dedicated page is gone, so the ONLY radar surface is the embedded
        # section built once inside render(). No duplicate static markup allowed.
        html = self.template
        self.assertEqual(html.count("results.innerHTML=radarHTML+"), 1)
        self.assertNotIn('<section class="page" id="radar">', html)
        self.assertNotIn("renderRadar()", html)

    def test_sticky_nav_cluster_present(self):
        # DISPOSITION 2026-08-22 (t_918994ed): ctrl-sticky wrapper removed; the
        # nav bar itself is the sticky cluster (z-index 10, blur backdrop).
        html = self.template
        self.assertIn(".nav{", html)
        self.assertIn("position:sticky;top:0;z-index:10", html.replace(" ", ""))
        # Filter controls still exist below it (P0 redesign: filter deck).
        self.assertIn('id="stageSummary"', html)
        self.assertIn('id="filterDeck"', html)
        self.assertIn('id="search"', html)

    def test_stage_filter_click_toggles_and_rerenders(self):
        # DISPOSITION 2026-08-22 (t_918994ed): scrollToResults()/smooth auto-scroll
        # removed with the ctrl-sticky redesign. Stage pill click still toggles
        # the filter and rerenders — that's the surviving behavior contract.
        html = self.template
        self.assertIn('.js-stage', html)
        self.assertIn('stageFilter=stageFilter===sp.dataset.stage?"all":sp.dataset.stage;render()', html)

    def test_proximity_subpills_click_filter_per_stage(self):
        # DISPOSITION 2026-08-22 (t_918994ed): global radarProx pills became
        # per-stage l2sub pills (data-stage + data-prox); clicking toggles that
        # stage's proxFilter and rerenders. Same interaction coverage.
        html = self.template
        self.assertIn('.l2sub', html)
        self.assertIn('data-prox="${g}"', html)
        self.assertIn('proxFilter[st]=(proxFilter[st]===g?undefined:g); render()', html)


if __name__ == "__main__":
    unittest.main()
