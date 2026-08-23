"""P1 Action Queue Redesign (t_69ff91c2): canonical 7-queue assignment.

Contract (vault Product-Strategy-Market-to-Action.md v0.2.0 + stage-first UX):
Queues (exactly one per item):
  intraday_emerging, fresh_breakout, pre_breakout, retest_watch,
  qualified_pullback, monitor_only, avoid_new_longs

Hard rules:
  * recovery/base/weak generic labels NEVER enter an actionable queue.
  * setup_quality must PASS for any actionable queue (fresh_breakout,
    pre_breakout, qualified_pullback). Retest Watch keeps its own event-based
    qualification; Intraday Emerging requires an active emerging event.
  * S3/S4, broken/declining phases => avoid_new_longs.
  * extended setups are DO NOT CHASE => monitor_only (queryable, not avoided).
  * every input maps to exactly one queue (FULL coverage, no hidden filter).
"""
import unittest

from action_queue import (
    ACTIONABLE_QUEUES,
    QUEUE_LABELS,
    assign_action_queue,
)


def q(**kw):
    base = {
        "stage": "S2_uptrend",
        "phase": "uptrend_pullback",
        "quality_pass": True,
        "proximity_state": "action",
        "intraday_event": None,
    }
    base.update(kw)
    return base


class ActionQueueTests(unittest.TestCase):
    # ---- coverage: every result is one of the 7 canonical queues ----
    def test_only_canonical_queues_returned(self):
        combos = [
            q(), q(quality_pass=False), q(stage="S1_basing", phase="base_tight",
            proximity_state="forming"),
            q(stage="S3_distributing", phase="topping"),
            q(intraday_event={"confidence": "emerging"}),
        ]
        for c in combos:
            self.assertIn(assign_action_queue(**c),
                          set(QUEUE_LABELS))

    # ---- S3/S4 => Avoid New Longs ----
    def test_s3_topping_is_avoid(self):
        self.assertEqual(assign_action_queue(
            stage="S3_distributing", phase="topping",
            quality_pass=True, proximity_state=None), "avoid_new_longs")

    def test_s4_declining_is_avoid(self):
        self.assertEqual(assign_action_queue(
            stage="S4_down", phase="declining",
            quality_pass=False, proximity_state=None), "avoid_new_longs")

    def test_broken_phase_is_avoid_even_in_s2(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="broken",
            quality_pass=True, proximity_state=None), "avoid_new_longs")

    # ---- Fresh Breakout ----
    def test_fresh_breakout(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="breakout_new",
            quality_pass=True, proximity_state="extended_like_none",
            intraday_event=None), "fresh_breakout")

    def test_fresh_breakout_requires_quality(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="breakout_new",
            quality_pass=False, proximity_state=None), "monitor_only")

    # ---- Retest Watch ----
    def test_breakout_retest(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="breakout_retest",
            quality_pass=True, proximity_state=None,
            intraday_event={"status": "active", "trigger_price": 9.8}),
            "retest_watch")

    # ---- Pre-breakout ----
    def test_waiting_breakout_with_quality_is_pre_breakout(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="waiting_breakout",
            quality_pass=True, proximity_state="near_trigger"), "pre_breakout")

    def test_s1_near_trigger_with_quality_is_pre_breakout(self):
        self.assertEqual(assign_action_queue(
            stage="S1_basing", phase="base_tight",
            quality_pass=True, proximity_state="near_trigger"), "pre_breakout")

    def test_s1_forming_base_is_monitor_only_not_actionable(self):
        # recovery/base generic label must NOT become actionable
        self.assertEqual(assign_action_queue(
            stage="S1_basing", phase="base_early",
            quality_pass=True, proximity_state="forming"), "monitor_only")

    # ---- Qualified Pullback ----
    def test_pullback_in_zone_with_quality(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="uptrend_pullback",
            quality_pass=True, proximity_state="action"), "qualified_pullback")

    def test_pullback_near_zone_with_quality(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="uptrend_pullback",
            quality_pass=True, proximity_state="near_trigger"), "qualified_pullback")

    def test_pullback_without_quality_is_monitor_only(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="uptrend_pullback",
            quality_pass=False, proximity_state="action"), "monitor_only")

    def test_pullback_forming_is_monitor_only(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="uptrend_pullback",
            quality_pass=True, proximity_state="forming"), "monitor_only")

    # ---- Extended => DO NOT CHASE => Monitor Only ----
    def test_extended_breakout_is_monitor_only(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="breakout_extended",
            quality_pass=True, proximity_state="extended"), "monitor_only")

    # ---- Intraday Emerging ----
    def test_active_emerging_event_wins(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="waiting_breakout",
            quality_pass=False, proximity_state=None,
            intraday_event={"confidence": "emerging"}), "intraday_emerging")

    def test_failed_event_does_not_qualify(self):
        self.assertEqual(assign_action_queue(
            stage="S2_uptrend", phase="waiting_breakout",
            quality_pass=True, proximity_state="near_trigger",
            intraday_event={"status": "failed"}), "pre_breakout")

    # ---- Determinism / totality ----
    def test_unknown_inputs_still_map_to_one_queue(self):
        # Unknown/missing data is NOT a risk verdict: explicit non-actionable
        # monitor_only with no false readiness (t_3ae98ae4 R4).
        self.assertEqual(assign_action_queue(
            stage=None, phase=None, quality_pass=None,
            proximity_state=None), "monitor_only")


if __name__ == "__main__":
    unittest.main()
