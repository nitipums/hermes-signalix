"""Contract tests for the US AI Buildout watchlist and universal market policy."""
import unittest


class USAIBuildoutTests(unittest.TestCase):
  def test_us_ai_buildout_is_a_curated_13f_theme_universe(self):
    from markets import get_universe

    universe = get_universe("us_ai_buildout")

    self.assertEqual(universe.market, "US")
    self.assertEqual(universe.benchmark_symbol, "SPY")
    self.assertEqual(universe.symbols[:5], ("SNDK", "MU", "BE", "TSM", "NBIS"))
    self.assertIn("CORZ", universe.symbols)
    self.assertIn("BTDR", universe.symbols)
    self.assertGreaterEqual(len(universe.symbols), 15)


  def test_us_universe_does_not_inherit_thai_price_or_trade_value_prescreen(self):
    from markets import get_universe

    universe = get_universe("us_ai_buildout")

    self.assertIsNone(universe.min_price)
    self.assertIsNone(universe.min_today_trade_value)


  def test_unknown_universe_is_rejected(self):
    from markets import get_universe

    with self.assertRaisesRegex(ValueError, "unknown universe"):
        get_universe("not-a-market")


if __name__ == "__main__":
    unittest.main()
