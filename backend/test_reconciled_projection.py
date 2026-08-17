import json
import unittest
from collections import Counter
from pathlib import Path

from reconciled_projection import (
    ARTIFACT_PATH, EXPECTED_COUNTS, PROJECTION_VERSION, apply_projection, load_rows,
    project_artifact_rows, snapshot_payload, validate_rows,
)


class ReconciledProjectionTests(unittest.TestCase):
    def test_artifact_is_exact_and_deterministic(self):
        rows = load_rows()
        validate_rows(rows)
        self.assertEqual(len(rows), 718)
        self.assertEqual(Counter(r['primary_group'] for r in rows), Counter(EXPECTED_COUNTS))
        self.assertEqual([r['symbol'] for r in rows], sorted(r['symbol'] for r in rows))
        self.assertEqual([r['symbol'] for r in rows], [r['symbol'] for r in load_rows()])

    def test_orthogonal_badges_do_not_change_primary_counts(self):
        rows = project_artifact_rows()
        primary = Counter(r['primary_group'] for r in rows)
        self.assertEqual(dict(primary), EXPECTED_COUNTS)
        self.assertEqual(Counter(r['freshness_badge'] for r in rows), {'fresh': 689, 'stale': 29})
        self.assertEqual(Counter(r['quality_badge'] for r in rows), {'low_quality': 611, 'not_flagged_low_quality': 107})
        self.assertEqual(Counter(r['data_confidence'] for r in rows), {'high': 350, 'medium': 339, 'low': 29})
        self.assertEqual(sum(r['primary_group'] == 'fresh' for r in rows), 9)
        self.assertEqual(sum(r['primary_group'] == 'extended' for r in rows), 9)

    def test_failure_and_pullback_separation(self):
        rows = project_artifact_rows()
        self.assertEqual(sum(r['primary_group'] == 'no_long_setup' for r in rows), 200)
        self.assertEqual(sum(r['primary_group'] == 'failed_setup_no_event' for r in rows), 5)
        self.assertEqual(sum(r['primary_group'] == 'pullback_holding' for r in rows), 28)
        self.assertEqual(sum(r['primary_group'] == 'pullback_under_reference' for r in rows), 5)
        self.assertEqual(sum(r['confirmed_failure'] for r in rows), 0)

    def test_stale_freshness_propagates_to_card_and_daily_detail(self):
        rows = load_rows()
        stale = [row for row in rows if row["freshness_badge"] == "stale"]
        self.assertEqual(len(stale), 29)
        self.assertEqual(sum(row["data_confidence"] == "low" for row in stale), 29)

        projected = apply_projection([{"symbol": row["symbol"]} for row in rows])
        amar = next(item for item in projected if item["symbol"] == "AMARIN")
        self.assertEqual(amar["freshness_badge"], "stale")
        self.assertEqual(amar["data_confidence"], "low")
        self.assertEqual(amar["dataFreshness"]["status"], "stale")
        self.assertEqual(amar["dailyState"]["dataFreshness"], amar["dataFreshness"])
        self.assertEqual(amar["dataFreshness"]["source"], "price_data")
        self.assertEqual(amar["dataFreshness"]["as_of"], amar["evidence_date"])
        self.assertIn("stale", amar["dataFreshness"]["reason"])

    def test_snapshot_serialization_contains_detail_provenance(self):
        payload = snapshot_payload(project_artifact_rows(), '2026-08-14T00:00:00Z')
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        self.assertIn(PROJECTION_VERSION, encoded)
        self.assertEqual(payload['primary_counts'], EXPECTED_COUNTS)
        for row in payload['items']:
            for key in ('evidence_summary', 'reconciliation_reason', 'nida_producer_fields', 'old_mapping'):
                self.assertIn(key, row)


if __name__ == '__main__':
    unittest.main()
