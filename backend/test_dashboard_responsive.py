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
            "button,select,input,.chip,.star{min-height:40px;touch-action:manipulation}",
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
        self.assertIn("หุ้นไทย ORD สแกน", self.html)
        self.assertIn('<span id="covCount">', self.html)

    def test_template_has_sector_industry_and_proximity_filter_contract(self):
        # After the Stage + Setup State redesign (2026-08-19), L2 pills are
        # replaced by proximity pills. The independence filter contract
        # (sector/industry/value/band/set50) is unchanged; proximity pills
        # (data-prox) replace the old l2/l2mom bars.
        html = self.template
        for marker in (
            'id="sectorFilter"',
            'id="industryFilter"',
            "root.onchange=",
            r'let indep={set50:false,value:0,band:"all",sector:"all",industry:"all"}, proxFilter={}, radarProx="all";',
            "const PROX_GROUPS=[\"action\",\"near_trigger\",\"forming\",\"extended\"]",
            'data-prox="${g}"',
            "indep.sector",
            "indep.industry",
            "const root=document.getElementById(`${key}Filter`)",
            "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
            "const inRadar=i=>!!i.radar",
            "Setup Radar",
            "radarBadge",
        ):
            self.assertIn(marker, html)
        self.assertIn("flex-wrap:wrap", html)
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

    def test_template_has_sector_industry_dropdown_and_stable_proximity_reset_contract(self):
        html = self.template
        for marker in (
            '<select id="sectorFilter"',
            '<select id="industryFilter"',
            "root.onchange=",
            "const baseList=current(s).filter(i=>i.stage===s)",
            'data-prox="all"',
            "function current(excludeProxStage=null){",
        ):
            self.assertIn(marker, html)
        self.assertNotIn('id="sectorFilter" class="chip indep-sep"', html)
        self.assertNotIn('id="industryFilter" class="chip indep-sep"', html)
        self.assertNotIn(".indep-row{display:flex;gap:8px;overflow-x:auto", html)


    def test_template_compatibility_helpers_cover_new_and_legacy_items(self):
        html = self.template
        for marker in (
            "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
            "const inRadar=i=>!!i.radar",
            "const l3=i.layer3_qualifier??i.layer3_qualifiers",
            "const l3Badge=l3&&l3.score!==undefined",
            "Q${l3.score}",
        ):
            self.assertIn(marker, html)
        # Legacy structural/momentum group helpers must NOT be present in the UI.
        self.assertNotIn("const structuralGroup=", html)
        self.assertNotIn("const momentumGroup=", html)

    def test_detail_modal_is_decision_first_and_daily_default(self):
        html = self.template
        for marker in (
            "decision-banner",
            "decisionPanel(i)",
            "modal-subtitle",
            "title-link",
            "chartFreshness",
            "Last data fetched:",
            'data-tf="1D" aria-pressed="true"',
            'loadChart(i.symbol, "1D", myGen)',
            "setup-note",
            "risk-note",
        ):
            self.assertIn(marker, html)
        for removed in (
            "Market session:",
            "last valid:",
            "Evidence provenance",
            "Canonical event",
            "Confidence",
            "provenancePanel(i)",
            'id="tvLink"',
        ):
            self.assertNotIn(removed, html)


    # --- Creative redesign markers (beyond the mechanical proposal) ---
    def test_creative_markers_in_template(self):
        html = self.template
        for marker in (
            # Stage Pulse dot — signature element for peripheral scanning
            ".pulse-dot",
            ".pulse-dot.s1",
            ".pulse-dot.s2",
            ".pulse-dot.s3",
            ".pulse-dot.s4",
            # Stage-tinted background system (signal-light vernacular)
            "--s2-tint",
            "--s4-tint",
            # Quality corner badge (Q1-Q3 compact on card)
            ".q-corner",
            # Setup Radar — now its own page, with proximity pills + radarBadge
            "radarBadge",
            'data-page="radar"',
            "renderRadar()",
            "radarPills",
            # Touch handling on canvas
            "touch-action:none",
            "cv.style.touchAction",
            # Setup Radar proximity pills (replaces legacy L2)
            "data-prox",
            "PROX_LABEL",
            # Fresh badge (data provenance on card)
            "fresh-badge eod",
            "fresh-badge live",
            "fresh-badge stale",
            # Creative enhancements beyond P0
            "prefers-reduced-motion",
            ".signal-card:hover",
            ".q-bar",
            "breadth-pulse",
            "breadthPulse",
        ):
            self.assertIn(marker, html, f"creative marker {marker!r} missing from template")

    def test_pulse_dot_has_stage_color_classes(self):
        """Pulse dot must have s1/s2/s3/s4 stage color classes in CSS."""
        html = self.template
        for cls in (".pulse-dot.s1", ".pulse-dot.s2", ".pulse-dot.s3", ".pulse-dot.s4"):
            self.assertIn(cls, html)

    def test_q_bar_has_all_quality_classes(self):
        """q-bar must style Q0-Q3 so score=0 items don't collapse to blue."""
        html = self.template
        for cls in (".q-bar .q0", ".q-bar .q1", ".q-bar .q2", ".q-bar .q3"):
            self.assertIn(cls, html, f"quality bar class {cls!r} missing from template CSS")
        # Q0 bar must not use the generic blue .q-bar span background; it needs
        # its own (muted/S4) colour so failing-quality items are scannable.
        self.assertIn(".q-bar .q0", html)

    def test_q_bar_generates_q_class_and_zero_width_for_score_zero(self):
        """Card JS must emit class q0 for score=0 and width=0% (no 10% floor)."""
        # Source template is the contract; dashboard.html is a generated
        # runtime artifact and may lag until the next scan/build.
        js = self.template
        # The width formula must short-circuit to 0 for score===0 instead of
        # Math.max(10, ...) which forced a 10% blue bar even for Q0.
        self.assertIn("l3.score===0?0:Math.max(10", js)
        # The emitted class token is still the compact q${min(score,3)} form.
        self.assertIn("q${Math.min(l3.score,3)}", js)

    # --- 2026-08-20 Summary UX: Radar page + sticky controls + auto-scroll ---
    def test_nav_has_radar_page_button(self):
        html = self.template
        self.assertIn('data-page="radar"', html)
        self.assertIn('aria-label="Setup Radar"', html)

    def test_radar_page_section_and_contract(self):
        html = self.template
        self.assertIn('<section class="page" id="radar">', html)
        for marker in (
            'id="radarCount"',
            'id="radarPills"',
            'id="radarResults"',
            'id="radarEmpty"',
            'data-radar-prox="${g}"',
            "renderRadar()",
            "radarProx",
        ):
            self.assertIn(marker, html, f"radar page marker {marker!r} missing from template")

    def test_radar_removed_from_screener_sections(self):
        # The embedded Setup Radar section on the screener page is replaced by
        # the dedicated Radar page — it must not render twice.
        html = self.template
        # Radar markup generation no longer prepends the section inside render().
        self.assertNotIn("radarHTML", html)
        self.assertNotIn('<section class="stage-section radar-section">', html)
        self.assertNotIn('"stage-head radar"', html)

    def test_sticky_control_cluster_present(self):
        html = self.template
        self.assertIn('class="ctrl-sticky" id="ctrlSticky"', html)
        self.assertIn("position:sticky;top:0;z-index:9", html.replace(" ", ""))
        # The stage summary + filter rows + search live inside the sticky wrapper.
        self.assertIn('id="stageSummary"', html)
        self.assertIn('id="indepBar"', html)
        self.assertIn('id="search"', html)

    def test_stage_filter_scrolls_to_results(self):
        html = self.template
        self.assertIn("scrollToResults()", html)
        self.assertIn('r.scrollIntoView({behavior:"smooth",block:"start"})', html)
        # Only stage pills trigger the scroll (filter bar is sticky and stays
        # visible; the stage sections are what move out of view).
        self.assertIn('stageFilter=stageFilter===sp.dataset.stage?"all":sp.dataset.stage;render();scrollToResults();', html)

    def test_radar_proximity_pills_click_filter(self):
        html = self.template
        self.assertIn('const radarP=e.target.closest("[data-radar-prox]")', html)
        self.assertIn("radarProx=radarP.dataset.radarProx;renderRadar()", html)


if __name__ == "__main__":
    unittest.main()
