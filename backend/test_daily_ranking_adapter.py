from daily_shortlist import (
    RANKING_POLICY_ID,
    RANKING_POLICY_VERSION,
    rank_daily_shortlist,
)
from test_daily_shortlist import card


def test_adapter_hard_gates_before_ranking_and_retains_universe_rows():
    low = card(symbol="LOW", avgDailyValue20=1)
    good = card(symbol="GOOD")
    rows = rank_daily_shortlist([low, good])
    assert [item["symbol"] for item, result in rows[:1]] == ["GOOD"]
    assert {item["symbol"] for item, _ in rows} == {"LOW", "GOOD"}
    assert rows[-1][1]["total_score"] is None


def test_adapter_exposes_explainable_components_and_missing_authoritative_rr():
    item, result = rank_daily_shortlist([card(symbol="A")])[0]
    assert item["symbol"] == "A"
    assert set(("structure_quality", "entry_readiness", "risk_reward", "liquidity")) <= set(result["rank_components"])
    assert "risk_reward" in result["missing_components"]
    assert result["ranking_policy_id"] == RANKING_POLICY_ID
    assert result["ranking_policy_version"] == RANKING_POLICY_VERSION


def test_adapter_order_is_deterministic_with_symbol_tiebreaker():
    a = card(symbol="AAA", avgDailyValue20=20_000_000)
    b = card(symbol="BBB", avgDailyValue20=20_000_000)
    assert [item["symbol"] for item, _ in rank_daily_shortlist([b, a])] == ["AAA", "BBB"]


def test_authoritative_rr_is_consumed_without_recalculation():
    result = rank_daily_shortlist([card(risk_reward_ratio=3.0)])[0][1]
    assert result["missing_components"] == []
    assert result["rank_components"]["risk_reward"] == 0.5
