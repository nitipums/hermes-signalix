"""R2/R3/R4 remediation tests (t_3ae98ae4).

Contract (vault Product-Strategy-Market-to-Action.md v0.2.0 section 1):
  * READY / ACTION / NEAR TRIGGER / FORMING / EXTENDED are legacy display
    terms; the canonical serialize() output MUST NOT emit them except under
    an explicit `legacy_alias` field.
  * Missing / stale / error rows keep an explicit blocked data state and are
    never silently collapsed into avoid_new_longs.
"""
import unittest

from build_dashboard import serialize


def row(**kw):
    base = {
        "symbol": "TEST",
        "close": 10.0,
        "trend_template": {"ma": {}, "conditions_met": 8, "rs_rating": 90},
        "trade_readiness": {},
        "vcp": {},
        "daily_state": {
            "stage": "S2_uptrend", "phase": "uptrend_pullback",
            "setup_quality": {"pass": True, "reasons": ["tight_range"]},
            "setup_proximity": {"state": "action", "pivot": None,
                                "distance_pct": None, "zone": None},
        },
    }
    base.update(kw)
    return base


LEGACY_TERMS = {"READY", "ACTION", "NEAR TRIGGER", "FORMING", "EXTENDED",
                "READY/WATCH", "WATCH", "Near Trigger"}


class LegacyIsolationTests(unittest.TestCase):
    def _legacy_scan(self, item, path=""):
        """Collect any legacy vocabulary string in top-level serial fields."""
        hits = []
        for key, value in item.items():
            if key == "legacy_alias":
                continue  # explicitly allowed
            if isinstance(value, str) and value in LEGACY_TERMS:
                hits.append(f"{path}{key}={value!r}")
        return hits

    def test_no_legacy_terms_in_top_level_serial_fields(self):
        for ds_state in ("action", "near_trigger", "forming", "extended"):
            ds = dict(row()["daily_state"],
                      setup_proximity={"state": ds_state, "pivot": None,
                                       "distance_pct": None, "zone": None})
            item = serialize("uptrend_pullback", row(daily_state=ds), {})
            self.assertEqual(self._legacy_scan(item), [])

    def test_legacy_values_preserved_only_under_legacy_alias(self):
        ds = dict(row()["daily_state"],
                  setup_proximity={"state": "action", "pivot": None,
                                   "distance_pct": None, "zone": None})
        item = serialize("uptrend_pullback", row(daily_state=ds), {})
        alias = item.get("legacy_alias")
        self.assertIsInstance(alias, dict)
        # migration/audit data keeps the old proximity vocabulary
        self.assertIn(alias.get("proximity_state"), LEGACY_TERMS | {"action"})


class ExplicitDataStateTests(unittest.TestCase):
    def test_insufficient_history_is_blocked_not_avoid(self):
        tr = {"status": "INSUFFICIENT_HISTORY", "reason": "thin history"}
        item = serialize("base", row(trade_readiness=tr), {})
        self.assertEqual(item["action_queue"], "monitor_only")
        self.assertEqual(item["data_block"], "DATA_MISSING_REQUIRED")

    def test_stale_data_gets_explicit_block_code(self):
        ds = dict(row()["daily_state"], data_freshness="stale")
        item = serialize("uptrend_pullback", row(daily_state=ds), {})
        self.assertEqual(item["data_block"], "DATA_STALE")

    def test_fresh_data_has_no_block(self):
        item = serialize("uptrend_pullback", row(), {})
        self.assertIsNone(item["data_block"])

    def test_unknown_inputs_never_become_actionable_or_avoid_by_default(self):
        ds = {"stage": None, "phase": None,
              "setup_quality": {"pass": False},
              "setup_proximity": {"state": None}}
        item = serialize("base", row(daily_state=ds), {})
        self.assertEqual(item["action_queue"], "monitor_only")
        self.assertNotEqual(item["action_queue"], "avoid_new_longs")


if __name__ == "__main__":
    unittest.main()
