"""P1 Action Queue Redesign: serialize() must emit the canonical queue.

build_dashboard.serialize is the single source every card path inherits
(build artifact + snapshot + progressive API). Contract:
  * each item carries top-level `action_queue` (+ label) from
    action_queue.assign_action_queue;
  * recovery/base/weak generic labels never surface as an actionable queue;
  * insufficient-history items are NOT actionable.
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


class SerializeQueueTests(unittest.TestCase):
    def test_actionable_pullback_qualified(self):
        item = serialize("uptrend_pullback", row(), {})
        self.assertEqual(item["action_queue"], "qualified_pullback")

    def test_broken_stage_is_avoid_new_longs(self):
        ds = dict(row()["daily_state"], stage="S4_down", phase="declining",
                  setup_proximity={"state": None})
        r = row(daily_state=ds)
        item = serialize("down_or_broken", r, {})
        self.assertEqual(item["action_queue"], "avoid_new_longs")
        self.assertNotIn(item["action_queue"],
                         ("fresh_breakout", "pre_breakout",
                          "retest_watch", "qualified_pullback"))

    def test_base_forming_is_monitor_only_not_actionable(self):
        # recovery/base generic label must not become actionable from a generic label
        ds = dict(row()["daily_state"], stage="S1_basing", phase="base_early",
                  setup_proximity={"state": "forming"})
        item = serialize("base", row(daily_state=ds), {})
        self.assertEqual(item["action_queue"], "monitor_only")

    def test_insufficient_history_never_actionable(self):
        ds = row()["daily_state"]
        r = row(daily_state=ds)
        item = serialize("base", r, {})
        item2 = serialize("base", r, {})
        # force insufficient-history path via readiness status
        tr = {"status": "INSUFFICIENT_HISTORY", "reason": "thin history"}
        r2 = row(trade_readiness=tr)
        item3 = serialize("base", r2, {})
        self.assertEqual(item3["action_queue"], "monitor_only")
        self.assertIn(item["action_queue"] and item2["action_queue"] and item3["action_queue"],
                      {"intraday_emerging", "fresh_breakout", "pre_breakout",
                       "retest_watch", "qualified_pullback",
                       "monitor_only", "avoid_new_longs"})

    def test_every_item_has_label(self):
        from action_queue import QUEUE_LABELS
        for ds_phase, expect in (("uptrend_pullback", "Qualified Pullback"),):
            item = serialize("uptrend_pullback", row(), {})
            self.assertEqual(item["action_queue_label"], QUEUE_LABELS[item["action_queue"]])


if __name__ == "__main__":
    unittest.main()
