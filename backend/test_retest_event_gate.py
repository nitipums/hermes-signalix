"""R3/R5 remediation tests (t_3ae98ae4).

Contract (vault v0.2.0 sections 4.1 and 6):
  * Qualified Retest requires event/provenance evidence: an active breakout
    event with a trigger price must exist; without it, retest_watch is
    unreachable from generic inputs.
  * Event persistence/readback evidence: immutable event_id, idempotency
    (same key+payload -> same event, no second row), ordering by
    (occurred_at_utc, event_id), corrections via compensating events,
    UTC freshness timestamps.
"""
import unittest

from action_queue import assign_action_queue


class QualifiedRetestGateTests(unittest.TestCase):
    def test_retest_without_event_is_not_qualified(self):
        # phase claims retest but no persisted event evidence -> cannot be
        # surfaced as a qualified retest; falls back to fresh-breakout lane
        # rules => monitor_only unless independently quality-passed.
        q = assign_action_queue(
            stage="S2_uptrend", phase="breakout_retest",
            quality_pass=True, proximity_state=None, intraday_event=None)
        self.assertEqual(q, "monitor_only")

    def test_retest_with_active_event_qualifies(self):
        q = assign_action_queue(
            stage="S2_uptrend", phase="breakout_retest",
            quality_pass=True, proximity_state=None,
            intraday_event={"status": "active", "confidence": "confirmed",
                            "trigger_price": 9.8})
        self.assertEqual(q, "retest_watch")


if __name__ == "__main__":
    unittest.main()
