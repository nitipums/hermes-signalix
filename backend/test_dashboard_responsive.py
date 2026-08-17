import json
import unittest
from pathlib import Path


HERE = Path(__file__).parent


class DashboardResponsiveTests(unittest.TestCase):
    def test_mobile_modal_constraints_are_in_generated_dashboard(self):
        html = (HERE / "dashboard.html").read_text(encoding="utf-8")
        for rule in (
            ".modal{",
            "overflow-x:hidden",
            ".modal>#modalContent",
            ".detail-layout,.detail-layout>*{min-width:0",
            ".chart-wrap canvas{max-width:100%}",
        ):
            self.assertIn(rule, html)

    def test_detail_modal_renders_badges_and_stale_provenance_contract(self):
        html = (HERE / "dashboard.html").read_text(encoding="utf-8")
        for marker in (
            "detail-badges",
            "Quality",
            "Freshness",
            "Lifecycle",
            "Confidence",
            "Evidence provenance",
            "freshness.source",
            "freshness.as_of",
            "freshness.reason",
            "Old group mapping",
            "Canonical event",
        ):
            self.assertIn(marker, html)
        self.assertIn("const freshness=i.dataFreshness&&typeof i.dataFreshness==='object'", html)
        self.assertIn("freshness.status==='stale'", html)

    def test_snapshot_and_taxonomy_artifact_remain_718(self):
        snapshot = json.loads((HERE / "dashboard_snapshot.json").read_text(encoding="utf-8"))
        taxonomy = (HERE / "reconciled_taxonomy.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(snapshot["items"]), 718)
        self.assertEqual(len(taxonomy), 718)
        self.assertIn("Reconciled primary groups", html := (HERE / "dashboard.html").read_text(encoding="utf-8"))
        self.assertIn("Thai ordinary shares screened", html)
        self.assertIn("<b>718</b>", html)


if __name__ == "__main__":
    unittest.main()
