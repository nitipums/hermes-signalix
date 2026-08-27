"""Task 2: Deterministic Daily Shortlist eligibility + ranking tests.

TDD RED->GREEN contract:
- Pure module: no DB, no clock, no regime scoring.
- Hard gates decide eligibility and publication state (READY / PRE_READY).
- Ranking is explainable (40/30/20) with a liquidity gate + tie-breaker.
- Ordering is stable across input permutations.
"""
import pytest

from daily_shortlist import (
    READY_QUEUES,
    PRE_READY_QUEUES,
    MIN_AVG_DAILY_VALUE_20,
    POLICY_VERSION,
    classify_shortlist,
    project_shortlist,
    _CONTRADICTORY_READY_ACTIONS,
)


def card(**kw):
    """Default a fully-valid READY candidate (fresh breakout) then override."""
    base = {
        "symbol": "TEST",
        "stage": "S2_uptrend",
        "phase": "breakout_new",
        "action": "VALIDATE FRESH BREAKOUT",
        "action_queue": "fresh_breakout",
        "avgDailyValue20": 20_000_000.0,
        "close": 52.5,
        "breakoutLevel": 52.0,
        "stop": 50.0,
        "riskStop": 50.0,
        "dataFreshness": "fresh",
        "daily_eod_freshness": {
            "status": "latest_available",
            "source": "price_data",
            "as_of": "2026-08-19",
        },
        "rs": 80.0,
        "rsi": 60.0,
        "setup_quality": {"pass": True, "reasons": ["tight_range"]},
        "setup_proximity": {
            "state": "action", "pivot": 52.0,
            "distance_pct": 0.01,
            "zone": {"lo": 50.0, "hi": 54.0},
        },
    }
    base.update(kw)
    return base


class TestLiquidityHardGate:
    def test_below_threshold_is_excluded(self):
        result = classify_shortlist(card(avgDailyValue20=9_999_999))
        assert result["eligible"] is False
        assert "LIQUIDITY_BELOW_20D_THB_10M" in result["exclusion_reasons"]

    def test_missing_liquidity_is_excluded(self):
        result = classify_shortlist(card(avgDailyValue20=None))
        assert result["eligible"] is False
        assert result["total_score"] is None

    def test_non_numeric_liquidity_is_excluded(self):
        result = classify_shortlist(card(avgDailyValue20="not-a-number"))
        assert result["eligible"] is False

    def test_at_threshold_passes_gate(self):
        # exactly 10M is the floor (>=)
        result = classify_shortlist(card(avgDailyValue20=10_000_000))
        assert result["eligible"] is True


class TestProvenanceExclusion:
    def test_stale_provenance_is_excluded(self):
        result = classify_shortlist(card(dataFreshness="stale"))
        assert result["eligible"] is False
        assert "STALE_PROVENANCE" in result["exclusion_reasons"]

    def test_missing_daily_eod_status_is_excluded(self):
        result = classify_shortlist(card(daily_eod_freshness={"status": None}))
        assert result["eligible"] is False

    def test_unknown_freshness_is_excluded(self):
        result = classify_shortlist(card(dataFreshness="unknown"))
        assert result["eligible"] is False


class TestBrokenInvalidated:
    def test_extended_breakout_is_excluded(self):
        result = classify_shortlist(card(phase="breakout_extended",
                                         action="DO NOT CHASE"))
        assert result["eligible"] is False
        assert "DO_NOT_CHASE" in result["exclusion_reasons"]

    def test_do_not_chase_action_is_excluded(self):
        result = classify_shortlist(card(action="DO NOT CHASE"))
        assert result["eligible"] is False
        assert "DO_NOT_CHASE" in result["exclusion_reasons"]

    def test_s4_down_is_excluded(self):
        result = classify_shortlist(card(stage="S4_down", phase="declining"))
        assert result["eligible"] is False
        assert any(r in result["exclusion_reasons"]
                   for r in ("BROKEN_STRUCTURE", "INVALIDATED"))

    def test_broken_phase_is_excluded(self):
        result = classify_shortlist(card(phase="broken"))
        assert result["eligible"] is False

    def test_declining_phase_is_excluded(self):
        result = classify_shortlist(card(phase="declining"))
        assert result["eligible"] is False


class TestDevelopingImmature:
    def test_base_forming_is_excluded(self):
        result = classify_shortlist(card(stage="S1_basing", phase="base_early",
                                         setup_proximity={"state": "forming"},
                                         action="WAIT"))
        assert result["eligible"] is False
        assert "DEVELOPING_BASE" in result["exclusion_reasons"]

    def test_non_actionable_queue_is_excluded(self):
        # monitor_only / avoid_new_longs / intraday_emerging are never Daily
        for q in ("monitor_only", "avoid_new_longs", "intraday_emerging"):
            result = classify_shortlist(card(action_queue=q))
            assert result["eligible"] is False


class TestPublicationState:
    def test_fresh_breakout_is_ready_when_confirmed(self):
        result = classify_shortlist(
            card(action_queue="fresh_breakout", avgDailyValue20=20_000_000))
        assert result["eligible"] is True
        assert result["publication_state"] == "READY"

    def test_fresh_breakout_unconfirmed_quality_fail_is_excluded(self):
        result = classify_shortlist(
            card(action_queue="fresh_breakout",
                 setup_quality={"pass": False, "reasons": ["range_too_wide"]}))
        assert result["eligible"] is False
        assert "UNCONFIRMED_BREAKOUT" in result["exclusion_reasons"]

    def test_fresh_breakout_unconfirmed_close_below_level_is_excluded(self):
        result = classify_shortlist(
            card(action_queue="fresh_breakout", close=51.0, breakoutLevel=52.0))
        assert result["eligible"] is False
        assert "UNCONFIRMED_BREAKOUT" in result["exclusion_reasons"]

    def test_fresh_breakout_unconfirmed_missing_level_is_excluded(self):
        result = classify_shortlist(
            card(action_queue="fresh_breakout", breakoutLevel=None))
        assert result["eligible"] is False
        assert "UNCONFIRMED_BREAKOUT" in result["exclusion_reasons"]

    def test_fresh_breakout_confirmed_exactly_at_level(self):
        result = classify_shortlist(
            card(action_queue="fresh_breakout", close=52.0, breakoutLevel=52.0))
        assert result["eligible"] is True
        assert result["publication_state"] == "READY"

    def test_pre_breakout_is_pre_ready(self):
        result = classify_shortlist(
            card(action_queue="pre_breakout", avgDailyValue20=20_000_000))
        assert result["eligible"] is True
        assert result["publication_state"] == "PRE_READY"

    def test_qualified_pullback_is_ready(self):
        result = classify_shortlist(card(action_queue="qualified_pullback"))
        assert result["eligible"] is True
        assert result["publication_state"] == "READY"

    def test_retest_watch_is_ready(self):
        result = classify_shortlist(card(action_queue="retest_watch"))
        assert result["eligible"] is True
        assert result["publication_state"] == "READY"

    def test_ineligible_has_no_publication_state(self):
        result = classify_shortlist(card(avgDailyValue20=9_999_999))
        assert result["publication_state"] is None
        assert result["rank_components"] == {}
        assert result["total_score"] is None


class TestPolicyAndComponents:
    def test_policy_version_constant(self):
        assert POLICY_VERSION == "daily-shortlist-v1"

    def test_queues_contract(self):
        assert READY_QUEUES == {"fresh_breakout", "qualified_pullback", "retest_watch"}
        assert PRE_READY_QUEUES == {"pre_breakout"}

    def test_threshold_constant(self):
        assert MIN_AVG_DAILY_VALUE_20 == 10_000_000

    def test_rank_components_present_and_bounded(self):
        result = classify_shortlist(card())
        comps = result["rank_components"]
        for key in ("structure_quality", "entry_readiness", "risk_reward", "liquidity"):
            assert key in comps
            assert 0.0 <= comps[key] <= 1.0

    def test_total_score_is_weighted_sum(self):
        result = classify_shortlist(card())
        comps = result["rank_components"]
        expected = round(
            0.4 * comps["structure_quality"]
            + 0.3 * comps["entry_readiness"]
            + 0.2 * comps["risk_reward"], 4)
        assert result["total_score"] == expected

    def test_no_regime_in_inputs(self):
        # market_regime must never influence the result.
        c = card()
        assert "market_regime" not in c
        r = classify_shortlist({**c, "market_regime": {"regime_state": "HIGH_VOLATILITY"}})
        assert r["eligible"] is True
        r2 = classify_shortlist(c)
        assert r["total_score"] == r2["total_score"]


class TestProjectShortlist:
    def test_only_eligible_ready_and_pre_ready(self):
        items = [
            card(),                                            # READY
            card(action_queue="pre_breakout"),                # PRE_READY
            card(avgDailyValue20=5_000_000),                  # excluded low liq
            card(action_queue="monitor_only"),                 # excluded non-actionable
            card(stage="S4_down", phase="declining",
                 action_queue="avoid_new_longs"),              # excluded broken
            card(action_queue="intraday_emerging"),            # excluded intraday-only
            card(stage="S1_basing", phase="base_early",
                 setup_proximity={"state": "forming"},
                 action="WAIT", action_queue="monitor_only"),  # excluded developing
        ]
        out = project_shortlist(items)
        assert len(out) == 2
        assert {r["publication_state"] for r in out} == {"READY", "PRE_READY"}

    def test_result_fields(self):
        out = project_shortlist([card(), card(action_queue="pre_breakout")])
        for r in out:
            assert "rank_components" in r
            assert "policy_version" in r
            assert r["policy_version"] == POLICY_VERSION
            assert "trigger" in r
            assert "invalidation" in r
            assert "source" in r
            assert "as_of" in r
            assert "avgDailyValue20" in r
            # New projection fields from normalization + explainability
            assert "source_action" in r
            assert "why_now" in r
            assert "why_not" in r

    def test_lifecycle_state_and_action_preserved(self):
        # Test that lifecycle_state is preserved and action is normalized.
        # READY candidates keep their non-contradictory action; PRE_READY
        # candidates are normalized to WAIT FOR CONFIRMATION with the
        # original preserved in source_action.
        items = [
            card(symbol="LIFECYCLE_TEST", action="REVIEW FRESH BREAKOUT", lifecycle_state="fresh_breakout", action_queue="fresh_breakout"),
            card(symbol="ACTION_TEST", action="WAIT FOR QUALIFIED BREAKOUT", lifecycle_state="pre_breakout", action_queue="pre_breakout"),
        ]
        out = project_shortlist(items)
        assert len(out) == 2
        for r in out:
            if r["symbol"] == "LIFECYCLE_TEST":
                assert r["lifecycle_state"] == "fresh_breakout"
                assert r["action"] == "REVIEW FRESH BREAKOUT"
            elif r["symbol"] == "ACTION_TEST":
                assert r["lifecycle_state"] == "pre_breakout"
                # PRE_READY normalized to canonical wait action
                assert r["action"] == "WAIT FOR CONFIRMATION"
                # Source action preserved for audit
                assert r["source_action"] == "WAIT FOR QUALIFIED BREAKOUT"

    def test_stable_ordering_under_permutation(self):
        a = card(symbol="A", avgDailyValue20=30_000_000, rs=85.0)
        b = card(symbol="B", avgDailyValue20=25_000_000, rs=80.0)
        c = card(symbol="C", avgDailyValue20=30_000_000, rs=80.0)
        baseline = project_shortlist([a, b, c])
        shuffled = project_shortlist([b, c, a])
        assert [r["symbol"] for r in baseline] == [r["symbol"] for r in shuffled]

    def test_ready_ranks_above_pre_ready(self):
        out = project_shortlist([card(action_queue="pre_breakout", symbol="P"),
                                 card(action_queue="fresh_breakout", symbol="R")])
        states = [r["publication_state"] for r in out]
        assert states.index("READY") < states.index("PRE_READY")

    def test_tie_break_uses_liquidity_then_symbol(self):
        # Equal total_score -> higher liquidity first -> symbol tiebreak.
        hi = card(symbol="AAA", avgDailyValue20=50_000_000, rs=80.0, rsi=60.0)
        lo = card(symbol="ZZZ", avgDailyValue20=30_000_000, rs=80.0, rsi=60.0)
        out = project_shortlist([lo, hi])
        assert [r["symbol"] for r in out] == ["AAA", "ZZZ"]

    def test_no_hidden_filtering_all_eligible_survive(self):
        """Verify no hidden filtering: all 6 valid candidates survive."""
        items = [
            card(symbol="R1", action_queue="fresh_breakout"),
            card(symbol="R2", action_queue="qualified_pullback"),
            card(symbol="R3", action_queue="retest_watch"),
            card(symbol="P1", action_queue="pre_breakout"),
            card(symbol="R4", action_queue="fresh_breakout"),
            card(symbol="P2", action_queue="pre_breakout"),
        ]
        out = project_shortlist(items)
        assert len(out) == 6  # all eligible, none silently dropped
        assert {r["symbol"] for r in out} == {"R1", "R2", "R3", "R4", "P1", "P2"}
        ready = [r for r in out if r["publication_state"] == "READY"]
        pre = [r for r in out if r["publication_state"] == "PRE_READY"]
        assert len(ready) == 4
        assert len(pre) == 2

    def test_ready_candidate_with_no_long_action_is_normalized(self):
        """READY candidate with source action 'NO LONG' must be normalized;
        source_action preserves the original."""
        item = card(symbol="NORM1", action="NO LONG", action_queue="fresh_breakout")
        out = project_shortlist([item])
        assert len(out) == 1
        r = out[0]
        assert r["publication_state"] == "READY"
        assert r["action"] not in _CONTRADICTORY_READY_ACTIONS
        assert r["action"] == "REVIEW FRESH BREAKOUT"
        assert r["source_action"] == "NO LONG"

    def test_ready_candidate_with_avoid_is_normalized(self):
        """READY candidate with source action 'AVOID' must be normalized."""
        item = card(symbol="NORM2", action="AVOID", action_queue="qualified_pullback")
        out = project_shortlist([item])
        assert len(out) == 1
        r = out[0]
        assert r["action"] == "REVIEW SUPPORT DEFENSE"
        assert r["source_action"] == "AVOID"

    def test_ready_candidate_with_do_not_chase_action_still_excluded(self):
        """READY candidate with source action 'DO NOT CHASE' is excluded by
        classify_shortlist hard gate (unchanged scan coverage). The
        normalize_action function is tested separately for action normalization
        on items that DO pass classification."""
        item = card(symbol="NORM3", action="DO NOT CHASE", action_queue="retest_watch")
        result = classify_shortlist(item)
        assert result["eligible"] is False
        assert "DO_NOT_CHASE" in result["exclusion_reasons"]

    def test_pre_ready_exposes_wait_action(self):
        """PRE_READY candidates must expose WAIT FOR CONFIRMATION."""
        item = card(symbol="PRE1", action="BUY", action_queue="pre_breakout")
        out = project_shortlist([item])
        assert len(out) == 1
        r = out[0]
        assert r["publication_state"] == "PRE_READY"
        assert r["action"] == "WAIT FOR CONFIRMATION"
        assert r["source_action"] == "BUY"

    def test_ready_candidate_non_contradictory_action_preserved(self):
        """READY candidate with a non-contradictory action keeps it."""
        item = card(symbol="KEEP1", action="REVIEW FRESH BREAKOUT",
                    action_queue="fresh_breakout")
        out = project_shortlist([item])
        assert len(out) == 1
        r = out[0]
        assert r["action"] == "REVIEW FRESH BREAKOUT"
        assert r["source_action"] == "REVIEW FRESH BREAKOUT"

    def test_ready_candidate_wait_for_qualified_breakout_normalized(self):
        """READY candidate with source action 'WAIT FOR QUALIFIED BREAKOUT' must be normalized per queue."""
        item_fresh = card(symbol="NORM4", action="WAIT FOR QUALIFIED BREAKOUT", action_queue="fresh_breakout")
        item_pullback = card(symbol="NORM5", action="WAIT FOR QUALIFIED BREAKOUT", action_queue="qualified_pullback")
        item_retest = card(symbol="NORM6", action="WAIT FOR QUALIFIED BREAKOUT", action_queue="retest_watch")
        for item, expected in [
            (item_fresh, "REVIEW FRESH BREAKOUT"),
            (item_pullback, "REVIEW SUPPORT DEFENSE"),
            (item_retest, "REVIEW RETEST"),
        ]:
            out = project_shortlist([item])
            assert len(out) == 1
            r = out[0]
            assert r["publication_state"] == "READY"
            assert r["action"] == expected
            assert r["source_action"] == "WAIT FOR QUALIFIED BREAKOUT"

    def test_ready_candidate_watch_wait_normalized(self):
        """READY candidate with source action 'WATCH / WAIT' must be normalized per queue."""
        item_fresh = card(symbol="NORM7", action="WATCH / WAIT", action_queue="fresh_breakout")
        item_pullback = card(symbol="NORM8", action="WATCH / WAIT", action_queue="qualified_pullback")
        item_retest = card(symbol="NORM9", action="WATCH / WAIT", action_queue="retest_watch")
        for item, expected in [
            (item_fresh, "REVIEW FRESH BREAKOUT"),
            (item_pullback, "REVIEW SUPPORT DEFENSE"),
            (item_retest, "REVIEW RETEST"),
        ]:
            out = project_shortlist([item])
            assert len(out) == 1
            r = out[0]
            assert r["publication_state"] == "READY"
            assert r["action"] == expected
            assert r["source_action"] == "WATCH / WAIT"

    def test_normalize_action_directly_ready_contradictory(self):
        """Direct unit test of normalize_action for READY with contradictory action."""
        from daily_shortlist import normalize_action
        item = {"action": "NO LONG", "action_queue": "fresh_breakout"}
        normalized, source = normalize_action(item, "READY")
        assert normalized == "REVIEW FRESH BREAKOUT"
        assert source == "NO LONG"

    def test_normalize_action_directly_ready_wait_for_qualified(self):
        """Direct unit test of normalize_action for READY with WAIT FOR QUALIFIED BREAKOUT."""
        from daily_shortlist import normalize_action
        for queue, expected in [
            ("fresh_breakout", "REVIEW FRESH BREAKOUT"),
            ("qualified_pullback", "REVIEW SUPPORT DEFENSE"),
            ("retest_watch", "REVIEW RETEST"),
        ]:
            item = {"action": "WAIT FOR QUALIFIED BREAKOUT", "action_queue": queue}
            normalized, source = normalize_action(item, "READY")
            assert normalized == expected
            assert source == "WAIT FOR QUALIFIED BREAKOUT"

    def test_normalize_action_directly_ready_watch_wait(self):
        """Direct unit test of normalize_action for READY with WATCH / WAIT."""
        from daily_shortlist import normalize_action
        for queue, expected in [
            ("fresh_breakout", "REVIEW FRESH BREAKOUT"),
            ("qualified_pullback", "REVIEW SUPPORT DEFENSE"),
            ("retest_watch", "REVIEW RETEST"),
        ]:
            item = {"action": "WATCH / WAIT", "action_queue": queue}
            normalized, source = normalize_action(item, "READY")
            assert normalized == expected
            assert source == "WATCH / WAIT"

    def test_normalize_action_directly_pre_ready(self):
        """Direct unit test of normalize_action for PRE_READY."""
        from daily_shortlist import normalize_action
        item = {"action": "BUY", "action_queue": "pre_breakout"}
        normalized, source = normalize_action(item, "PRE_READY")
        assert normalized == "WAIT FOR CONFIRMATION"
        assert source == "BUY"

    def test_shortlist_record_has_required_contract_fields(self):
        """Every shortlist record carries the full compact contract."""
        item = card()
        out = project_shortlist([item])
        assert len(out) == 1
        r = out[0]
        for field in ("symbol", "publication_state", "lifecycle_state", "action",
                      "source_action", "rank_components", "policy_version",
                      "total_score", "trigger", "invalidation", "why_now",
                      "why_not", "source", "as_of", "avgDailyValue20"):
            assert field in r, f"missing field: {field}"
        # READY candidate should have a why_now
        assert r["why_now"] is not None

    def test_why_now_pre_ready(self):
        """PRE_READY candidate should have a why_now message."""
        item = card(action_queue="pre_breakout", setup_proximity={"state": "near_trigger"})
        out = project_shortlist([item])
        assert len(out) == 1
        r = out[0]
        assert r["publication_state"] == "PRE_READY"
        assert r["why_now"] is not None
        assert "confirm" in r["why_now"].lower()

    def test_pullback_why_now_does_not_call_breakout(self):
        """qualified_pullback why_now must not label the setup as a breakout."""
        item = card(symbol="PB", action_queue="qualified_pullback",
                    action="HOLD IF SUPPORT DEFENDS")
        out = project_shortlist([item])
        assert len(out) == 1
        r = out[0]
        assert r["publication_state"] == "READY"
        assert r["why_now"] is not None
        assert "breakout" not in r["why_now"].lower()
        assert "pullback" in r["why_now"].lower()

    def test_retest_why_now_does_not_call_breakout(self):
        """retest_watch why_now must not label the setup as a breakout."""
        item = card(symbol="RT", action_queue="retest_watch",
                    action="WAIT FOR RETEST")
        out = project_shortlist([item])
        assert len(out) == 1
        r = out[0]
        assert r["publication_state"] == "READY"
        assert r["why_now"] is not None
        assert "breakout" not in r["why_now"].lower()
        assert "retest" in r["why_now"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
