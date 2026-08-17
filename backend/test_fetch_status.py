import unittest
from unittest.mock import MagicMock, patch

from update_data import ensure_intraday_table, insert_intraday_rows


class FetchStatusPersistenceTests(unittest.TestCase):
    def test_schema_contains_canonical_fetch_status_table(self):
        pg = MagicMock()

        ensure_intraday_table(pg)

        sql = pg.cursor.return_value.execute.call_args.args[0]
        self.assertIn("CREATE TABLE IF NOT EXISTS data_fetch_status", sql)
        self.assertIn("data_fetched_at TIMESTAMPTZ NOT NULL", sql)
        pg.commit.assert_called_once_with()

    @patch("update_data.psycopg2.extras.execute_values")
    def test_successful_intraday_upsert_records_fetch_time_in_same_commit(self, execute_values):
        pg = MagicMock()
        rows = [("STGT", "60m", "2026-08-13T16:00:00+07:00", 10, 11, 9, 10.9, 1000)]

        offered = insert_intraday_rows(pg, rows)

        self.assertEqual(offered, 1)
        execute_values.assert_called_once()
        metadata_sql = pg.cursor.return_value.execute.call_args.args[0]
        self.assertIn("data_fetch_status", metadata_sql)
        self.assertIn("NOW()", metadata_sql)
        self.assertEqual(pg.cursor.return_value.execute.call_args.args[1], ("settrade_intraday_60m",))
        pg.commit.assert_called_once_with()

    @patch("update_data.psycopg2.extras.execute_values")
    def test_empty_fetch_does_not_claim_success(self, execute_values):
        pg = MagicMock()

        offered = insert_intraday_rows(pg, [])

        self.assertEqual(offered, 0)
        execute_values.assert_not_called()
        pg.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
