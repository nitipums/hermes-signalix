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
        self.assertIn('class="chip tv-link"', self.html)
        self.assertIn('id="tvLink"', self.html)
        self.assertIn("TradingView", self.html)

    def test_snapshot_and_taxonomy_artifact_match_full_universe(self):
        # Full ORD universe (delisted/inactive excluded) — count reflects the
        # current screened set, not a hard-coded historical number.
        scan = json.loads((HERE / "scan_results.json").read_text(encoding="utf-8"))
        scan_symbols = {r["symbol"] for v in scan.get("groups", {}).values() for r in v}
        snapshot_symbols = {i["symbol"] for i in self.snapshot["items"]}
        self.assertEqual(len(self.snapshot["items"]), len(scan_symbols))
        self.assertEqual(snapshot_symbols, scan_symbols)
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
            # sector/industry chips are generated dynamically in JS via
            # populateIndependenceFilters() using data-indep="${key}" inside a
            # template literal (with escaped quotes) — assert the dynamic
            # pattern rather than a static "sector"/"industry" string.
            'data-indep="${key}"',
            "let indep={set50:false,value:0,band:\"all\",sector:\"all\",industry:\"all\"}, proxFilter={};",
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

    # --- Contracts intentionally NOT yet built (tracked, not silently passing) ---
    def test_detail_modal_renders_badges_and_stale_provenance_contract(self):
        html = self.html
        for marker in (
            "detail-badges",
            "Quality",
            "Latest data fetched:",
            "Market session:",
            "last valid:",
            "Lifecycle",
            "Confidence",
            "Evidence provenance",
            "Canonical event",
        ):
            self.assertIn(marker, html)
        self.assertIn("const fresh=i.dataFreshness||{}", html)
        self.assertIn("freshStatus=fresh.status||", html)

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
            # Setup Radar with proximity pills + radarBadge
            "radar-section",
            "radarBadge",
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


if __name__ == "__main__":
    unittest.main()
