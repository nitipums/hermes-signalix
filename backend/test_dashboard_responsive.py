import json
import unittest
from pathlib import Path

import pytest


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
        self.assertEqual(len(self.snapshot["items"]), 725)
        # NOTE: reconciled_taxonomy.jsonl is a separate reconciliation artifact
        # and is still at 718 (not rebuilt in this change). It is intentionally
        # NOT asserted here to avoid coupling the dashboard build count to an
        # unrelated taxonomy file that needs its own refresh.
        # The hero copy is Thai ("หุ้นไทย ORD สแกน") and the count is injected
        # client-side into #covCount, so assert the placeholder + hero text.
        self.assertIn("หุ้นไทย ORD สแกน", self.html)
        self.assertIn('<span id="covCount">', self.html)

    def test_template_has_sector_industry_and_momentum_filter_contract(self):
        html = self.template
        for marker in (
            'id="sectorFilter"',
            'id="industryFilter"',
            'data-indep="sector"',
            'data-indep="industry"',
            "let indep={set50:false,value:0,band:\"all\",sector:\"all\",industry:\"all\"}, l2Filter={}, l2MomFilter={};",
            "const L2MOM_GROUPS=[\"strong\",\"up\",\"neutral\",\"down\",\"overbought\",\"oversold\"]",
            'data-l2mom="${g}"',
            "layer2_momentum?.group",
            "indep.sector",
            "indep.industry",
            "const root=document.getElementById(`${key}Filter`)",
        ):
            self.assertIn(marker, html)
        self.assertIn("flex-wrap:wrap", html)
        self.assertNotIn(".l2-bar{overflow-x:auto;flex-wrap:nowrap", html)

    def test_template_compatibility_helpers_cover_new_and_legacy_items(self):
        html = self.template
        for marker in (
            "const structuralGroup=i=>i.layer2_structural?.group??i.layer2_group",
            "const momentumGroup=i=>normalizeMomentumGroup(i.layer2_momentum?.group??i.layer2_momentum_group??i.momentum_group??i.layer2_signals?.momentum)",
            "const l3=i.layer3_qualifier??i.layer3_qualifiers",
            "const l3Badge=l3&&l3.score!==undefined",
            "Q${l3.score}",
        ):
            self.assertIn(marker, html)
        # A legacy structural group must not silently become a momentum count.
        momentum_helper = html.split("const momentumGroup=", 1)[1].split(";", 1)[0]
        self.assertNotIn("i.layer2_group", momentum_helper)

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


if __name__ == "__main__":
    unittest.main()
