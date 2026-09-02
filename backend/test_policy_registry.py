from types import MappingProxyType

import pytest

from policy_registry import get_policy, policy_registry


def test_registry_has_separate_owned_daily_and_60m_policies():
    registry = policy_registry()
    assert set(registry) == {"daily_eod", "vcp_60m"}
    for timeframe in registry:
        policy = get_policy(timeframe)
        assert policy["timeframe"] == timeframe
        assert policy["policy_id"]
        assert policy["version"]
        assert policy["owner"]
        for key in ("breakout_buffer_pct", "breakout_volume_ratio", "invalidation"):
            assert key in policy["thresholds"]
    assert get_policy("daily_eod")["thresholds"]["breakout_volume_ratio"] == 1.20
    assert get_policy("vcp_60m")["thresholds"]["breakout_volume_ratio"] == 1.50
    assert get_policy("daily_eod")["thresholds"]["breakout_buffer_pct"] == 0.01
    assert get_policy("vcp_60m")["thresholds"]["breakout_buffer_pct"] == 0.005


def test_registry_is_immutable_and_unknown_timeframe_fails():
    policy = get_policy("daily_eod")
    assert isinstance(policy, MappingProxyType)
    with pytest.raises(TypeError):
        policy["version"] = "changed"
    with pytest.raises(TypeError):
        policy["thresholds"]["breakout_volume_ratio"] = 9
    with pytest.raises(KeyError):
        get_policy("60m")
