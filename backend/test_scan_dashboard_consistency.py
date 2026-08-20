import json
import tempfile
import unittest
from pathlib import Path

from verify_scan_dashboard import load_dashboard_items, verify


class ScanDashboardConsistencyTests(unittest.TestCase):
    def _write(self, root, scan_groups, dash_items, snap_items):
        scan = root / "scan.json"
        dashboard = root / "dashboard.html"
        snapshot = root / "snapshot.json"
        scan.write_text(json.dumps({"scan_time": "now", "groups": scan_groups}), encoding="utf-8")
        dashboard.write_text(
            "let items=" + json.dumps(dash_items) + ";\nlet stageMeta={};", encoding="utf-8"
        )
        snapshot.write_text(json.dumps({"scan_time": "now", "items": snap_items}), encoding="utf-8")
        return str(scan), str(dashboard), str(snapshot)

    def test_matching_scan_dashboard_and_db_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scan, dashboard, snapshot = self._write(
                root,
                {"ready": [{"symbol": "AAA"}], "avoid": [{"symbol": "BBB"}]},
                [
                    {"symbol": "AAA", "group": "ready"},
                    {"symbol": "BBB", "group": "avoid"},
                ],
                [
                    {"symbol": "AAA", "primary_group": "ready"},
                    {"symbol": "BBB", "primary_group": "avoid"},
                ],
            )
            result = verify(scan, dashboard, snapshot, None)
            self.assertTrue(result["ok"], result)

    def test_group_count_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scan, dashboard, snapshot = self._write(
                root,
                {"ready": [{"symbol": "AAA"}], "avoid": [{"symbol": "BBB"}]},
                [{"symbol": "AAA", "group": "avoid"}],
                [{"symbol": "AAA", "primary_group": "avoid"}],
            )
            result = verify(scan, dashboard, snapshot, None)
            self.assertFalse(result["ok"])
            self.assertIn("dashboard item count differs from scan group total", result["failures"])

    def test_loader_rejects_missing_assignment(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html") as handle:
            handle.write("<html></html>")
            handle.flush()
            with self.assertRaises(ValueError):
                load_dashboard_items(handle.name)


if __name__ == "__main__":
    unittest.main()
