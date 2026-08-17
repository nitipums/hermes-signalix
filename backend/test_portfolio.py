"""MVP behavior tests for the owner-only Investment Co-pilot module.

Runs inside the backend container:
    python -m unittest -v test_portfolio.py
"""
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(__file__))


class PortfolioAuthTests(unittest.TestCase):
    def test_owner_token_is_required_and_constant_time_checked(self):
        from portfolio import require_owner_token

        self.assertTrue(require_owner_token("secret", "secret"))
        self.assertFalse(require_owner_token("wrong", "secret"))
        self.assertFalse(require_owner_token("", "secret"))
        self.assertFalse(require_owner_token("secret", ""))

    def test_public_registration_cannot_provision_privileged_tiers(self):
        from users import public_registration_tier

        self.assertEqual(public_registration_tier("free"), "free")
        self.assertIsNone(public_registration_tier("owner"))
        self.assertIsNone(public_registration_tier("paid"))

    def test_owner_identity_requires_token_and_bound_chat_id(self):
        from portfolio import require_owner_identity

        self.assertTrue(require_owner_identity("token", "token", "owner-chat", "owner-chat"))
        self.assertFalse(require_owner_identity("wrong", "token", "owner-chat", "owner-chat"))
        self.assertFalse(require_owner_identity("token", "token", "other-chat", "owner-chat"))
        self.assertFalse(require_owner_identity("token", "token", "owner-chat", ""))

    def test_account_health_uses_unknowns_not_fake_zeroes(self):
        from portfolio import _account_health_state, _risk_inputs

        account = {"account_type": "thai_equity", "transaction_count": 0,
                   "latest_snapshot": None, "holdings": []}
        state, limitations = _account_health_state(account)
        self.assertEqual(state, "not_covered")
        self.assertIn("no_current_holding_source", limitations)
        risk = _risk_inputs(account)
        self.assertEqual(risk["coverage"], "not_ready")
        self.assertIn("owner_stop_or_thesis_plan", risk["missing"])


class PortfolioParserTests(unittest.TestCase):
    def test_innovestx_trade_rows_are_normalized(self):
        from portfolio import parse_innovestx_derivatives_text

        text = """
Trading Date 11/08/2026
Settlement Date 13/08/2026
Settlement No. 999-26081100258-00
MGOU26 F260498243 S 1 4,449.500000 0.00 18.00 1.26 0.00 19.26
CBGU26 F260498253 B 10 51.470000 0.00 468.33 32.78 0.00 501.11
STATEMENT OF ACCOUNT
479,613.83 440,071.71 0.00 -37,668.03 -23,345.96 0.00 0.00
423,626.83 416,725.75 397,762.75 279,570.39 18,963.00 0.00
"""
        parsed = parse_innovestx_derivatives_text(text, "innovestx_tfex_main")
        self.assertEqual(parsed["broker"], "innovestx")
        self.assertEqual(parsed["asset_type"], "futures")
        self.assertEqual(len(parsed["transactions"]), 2)
        self.assertEqual(parsed["transactions"][0]["side"], "SELL")
        self.assertEqual(parsed["transactions"][1]["quantity"], 10)
        self.assertEqual(parsed["snapshot"]["cash_excess"], 18963.0)

    def test_krungsri_rows_are_normalized(self):
        from portfolio import parse_krungsri_equity_text

        text = """
Document No. CN-20260811-00557
Trade Date 11/08/2026
Due Date. 11/08/2026
BU-05655 11014828 BBGI 30,000 5.90 277.94 19.46 177,297.40
SE-11053 11022983 AWC 250,000 2.90 1,138.16 79.67 723,782.17
TOTAL BUY : 1,038.46 72.70 662,511.16
TOTAL SELL : 2,529.20 177.04 1,608,293.76
"""
        parsed = parse_krungsri_equity_text(text, "krungsri_equity_main")
        self.assertEqual(parsed["broker"], "krungsri")
        self.assertEqual(parsed["asset_type"], "thai_equity")
        self.assertEqual([t["side"] for t in parsed["transactions"]], ["BUY", "SELL"])
        self.assertEqual(parsed["transactions"][0]["quantity"], 30000)
        self.assertEqual(parsed["transactions"][1]["symbol"], "AWC")


if __name__ == "__main__":
    unittest.main()
