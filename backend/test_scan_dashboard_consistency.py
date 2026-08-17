import json
import tempfile
import unittest
from pathlib import Path

from verify_scan_dashboard import load_dashboard_items, verify


class ScanDashboardConsistencyTests(unittest.TestCase):
    def test_matching_scan_dashboard_and_db_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scan = root / "scan.json"
            dashboard = root / "dashboard.html"
            scan.write_text(json.dumps({"scan_time": "now", "groups": {
                "ready": [{"symbol": "AAA"}],
                "avoid": [{"symbol": "BBB"}],
            }}), encoding="utf-8")
            dashboard.write_text(
                "let items=" + json.dumps([
                    {"symbol": "AAA", "group": "ready"},
                    {"symbol": "BBB", "group": "avoid"},
                ]) + ";const meta={}", encoding="utf-8"
            )
            result = verify(str(scan), str(dashboard), {
                "evaluated_symbol_count": 2, "observation_count": 2,
                "scan_date": "2026-08-14", "run_timestamp": "now",
            })
            self.assertTrue(result["ok"], result)

    def test_group_count_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scan = root / "scan.json"
            dashboard = root / "dashboard.html"
            scan.write_text(json.dumps({"groups": {"ready": [{"symbol": "AAA"}]}}), encoding="utf-8")
            dashboard.write_text(
                "let items=" + json.dumps([{ "symbol": "AAA", "group": "avoid" }]) + ";const meta={}",
                encoding="utf-8",
            )
            result = verify(str(scan), str(dashboard), None)
            self.assertFalse(result["ok"])
            self.assertIn("dashboard group counts differ from scan group counts", result["failures"])

    def test_loader_rejects_missing_assignment(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html") as handle:
            handle.write("<html></html>")
            handle.flush()
            with self.assertRaises(ValueError):
                load_dashboard_items(handle.name)


if __name__ == "__main__":
    unittest.main()
