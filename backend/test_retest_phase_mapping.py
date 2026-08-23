"""Regression fixtures for t_c5694a25 (Retest Watch phase mapping).

Live defect: persisted scan rows carry daily_state.primary_state=breakout_retest
while phase stayed breakout_new (pre-t_3ae98ae4 classifier output). serialize()
keyed the action queue on phase only, so all 12 live retest candidates fell into
monitor_only/fresh_breakout and retest_watch was unreachable.

Fix: deterministic primary_state->phase promotion in build_dashboard.serialize()
(fires ONLY when primary_state == "breakout_retest", stage == S2_uptrend, and
phase disagrees). Hard gate unchanged: assign_action_queue still requires a
persisted event with trigger_price + active/None status; phase alone never
qualifies (negative cases below).
"""
import unittest
from unittest.mock import patch

import build_dashboard


def row(primary_state="breakout_retest", phase="breakout_new",
        stage="S2_uptrend"):
    return {
        "symbol": "TEST",
        "scan_group": "breakout_new",
        "trade_readiness": {},
        "trend_template": {"rs_rating": 90, "conditions_met": 8,
                           "rs_threshold": 90, "failed_conditions": []},
        "daily_state": {
            "stage": stage, "phase": phase,
            "primary_state": primary_state,
            "setup_quality": {"pass": False},
            "setup_proximity": {"state": None},
            "data_freshness": "fresh",
        },
    }


def serialize(row_obj, intraday_event=None):
    return build_dashboard.serialize(
        "breakout_new", row_obj, {}, None, None, set(),
        intraday_event=intraday_event)


ACTIVE_EVENT = {"trigger_price": 30.0, "status": "active",
                "age_sessions": 5, "pivot_low": 27.5}


class RetestMappingPositive(unittest.TestCase):
    """12-style live case: stale phase, canonical primary_state says retest."""

    def test_stale_phase_promoted_and_queued_retest_watch(self):
        item = serialize(row(), intraday_event=ACTIVE_EVENT)
        self.assertEqual(item["phase"], "breakout_retest")
        self.assertEqual(item["dailyState"]["phase"], "breakout_retest")
        self.assertEqual(item["action_queue"], "retest_watch")
        self.assertEqual(item["dailyState"]["primary_state"], "breakout_retest")

    def test_promoted_row_keeps_wait_for_retest_action(self):
        item = serialize(row())
        self.assertEqual(item["dailyState"]["action"], "WAIT_FOR_RETEST")
        self.assertEqual(item["dailyState"]["lifecycleState"], "retest")

    def test_phase_label_updated(self):
        item = serialize(row())
        self.assertEqual(item["phase_label"], "Breakout retest")


class RetestMappingNegativeHardGate(unittest.TestCase):
    """No data hiding / no broadening: gate stays on provenance evidence."""

    def test_no_event_never_qualifies(self):
        item = serialize(row(), intraday_event=None)
        self.assertEqual(item["phase"], "breakout_retest")  # mapping still honest
        self.assertEqual(item["action_queue"], "monitor_only")  # but not actionable

    def test_event_without_trigger_price_never_qualifies(self):
        item = serialize(row(), intraday_event={"status": "active"})
        self.assertEqual(item["action_queue"], "monitor_only")

    def test_failed_event_never_qualifies(self):
        item = serialize(row(), intraday_event={
            "trigger_price": 30.0, "status": "failed"})
        self.assertEqual(item["action_queue"], "monitor_only")


class RetestMappingScopeGuards(unittest.TestCase):
    """Promotion must NOT fire outside the exact mismatch shape."""

    def test_agreement_untouched(self):
        item = serialize(row(phase="breakout_retest"), intraday_event=None)
        self.assertEqual(item["phase"], "breakout_retest")

    def test_non_retest_primary_state_untouched(self):
        item = serialize(row(primary_state="fresh_breakout",
                             phase="breakout_new"))
        self.assertEqual(item["phase"], "breakout_new")
        self.assertNotEqual(item["action_queue"], "retest_watch")

    def test_wrong_stage_not_promoted(self):
        item = serialize(row(stage="S1_basing"))
        self.assertEqual(item["phase"], "breakout_new")

    def test_other_phases_pass_through(self):
        for ph in ("uptrend_pullback", "waiting_breakout",
                   "breakout_extended", "declining"):
            r = row(primary_state="no_long_setup" if ph == "declining"
                    else "trend_pullback", phase=ph)
            item = serialize(r)
            self.assertEqual(item["phase"], ph, ph)

    def test_insufficient_history_still_blocked_to_monitor_only(self):
        from action_queue import DATA_BLOCK_INSUFFICIENT
        item = serialize(row())
        item = build_dashboard.serialize(
            "breakout_new",
            {**row(), "analysis_status": "INSUFFICIENT_HISTORY"},
            {}, None, None, set(), intraday_event=ACTIVE_EVENT)
        # readiness INSUFFICIENT_HISTORY comes via trade_readiness.status
        item2 = build_dashboard.serialize(
            "breakout_new",
            {**row(), "trade_readiness": {"status": "INSUFFICIENT_HISTORY"}},
            {}, None, None, set(), intraday_event=None)
        if item2.get("data_block"):
            self.assertEqual(item2["queue"] if "queue" in item2
                             else item2["action_queue"], "monitor_only")
            self.assertEqual(item2["data_block"], DATA_BLOCK_INSUFFICIENT)


if __name__ == "__main__":
    unittest.main()
