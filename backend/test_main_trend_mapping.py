"""Owner-labelled diagnostic fixtures for Issue #32 Main Trend calibration."""

import pytest

from main_trend_mapping import (
    MA_PERIODS,
    POLICY_VERSION,
    SLOPE_WINDOW,
    build_trend_history_evidence,
    classify_main_trend,
)


LABELS = {
    1: ("MASTER", "AURA"),
    2: ("SSP", "KCE", "TPIPL", "SPCG", "HANA", "KSL", "AKR", "TC", "GFPT",
        "PR9", "CPF", "AMATA", "CRC", "EKH", "PTT", "TOP",
        "RJH", "KCG", "DELTA", "CPI", "BTG", "ERW", "FUTURERT"),
    3: ("MAJOR", "SPREME", "TFM", "CPAXT", "SAT", "PRM", "DRT", "PTL", "TTB",
        "KKP", "BA", "EPG", "AEONTS", "SCB", "KBANK", "INSET", "FORTH", "GULF", "JAS"),
    4: ("BEM", "MRDIYT", "TURBO"),
}


def diagnostic_fixture(main_trend: int, *, bars: int = 21):
    profiles = {
        1: (90.0, {5: 100.0, 10: 99.0, 20: 98.0, 50: 97.0, 100: 92.0, 200: 93.0}),
        2: (112.0, {5: 110.0, 10: 108.0, 20: 106.0, 50: 104.0, 100: 102.0, 200: 100.0}),
        3: (100.0, {5: 98.0, 10: 100.0, 20: 102.0, 50: 105.0, 100: 100.0, 200: 95.0}),
        4: (90.0, {5: 90.0, 10: 92.0, 20: 94.0, 50: 96.0, 100: 98.0, 200: 100.0}),
    }
    close, current = profiles[main_trend]
    series = {"close": [close] * bars, "ma": {}}
    for period in MA_PERIODS:
        value = current[period]
        prior = value * (0.95 if main_trend == 2 else 1.05 if main_trend == 4 else 0.99)
        prefix = max(bars - SLOPE_WINDOW - 1, 0)
        series["ma"][str(period)] = [value] * prefix + [prior] + [value] * (bars - prefix - 1)
    return {"timeframe": "1D", "as_of": "2026-09-11", "series": series,
            "latest": {"close": close, "ma": {str(k): v for k, v in current.items()}}}


def test_owner_labelled_diagnostic_groups_have_literal_main_trend_labels():
    for expected, symbols in LABELS.items():
        for symbol in symbols:
            result = classify_main_trend(diagnostic_fixture(expected))
            assert result["main_trend"] == expected, symbol
            assert result["evidence_quality"] == "FULL"
            assert result["used_periods"] == [5, 10, 20, 50, 100, 200]
            assert result["slope_window"] == 20
            assert result["source_timeframe"] == "1D"
            assert result["policy_version"] == POLICY_VERSION


def test_missing_ma_is_partial_and_explicitly_diagnostic():
    item = diagnostic_fixture(2)
    del item["latest"]["ma"]["200"]
    del item["series"]["ma"]["200"]
    result = classify_main_trend(item)
    assert result["evidence_quality"] == "PARTIAL"
    assert result["missing_periods"] == ["200"]
    assert "partial_ma_or_slope_evidence" in result["ambiguity_reasons"]


def test_slope_uses_exactly_twenty_completed_bars_without_lookahead():
    item = diagnostic_fixture(2, bars=22)
    # The bar at -21 is the only slope anchor; changing an older bar cannot
    # affect the result, and the newest completed bar is the current endpoint.
    for values in item["series"]["ma"].values():
        values[0] = 1.0  # older than the exact 20-bar slope window
    result = classify_main_trend(item)
    assert result["slopes_20d_pct"]["20"] == pytest.approx(5.263157894736842)
    assert result["slope_window"] == 20


def test_output_is_one_non_actionable_main_trend_and_preserves_as_of():
    result = classify_main_trend(diagnostic_fixture(3))
    assert set(result) >= {"main_trend", "reason", "missing_periods", "as_of", "actionability"}
    assert result["as_of"] == "2026-09-11"
    assert result["actionability"] == "NONE"


def test_canonical_main_trend_evidence_has_no_legacy_ma_periods():
    result = classify_main_trend(diagnostic_fixture(2))
    assert set(result["moving_averages"]) == {"5", "10", "20", "50", "100", "200"}
    assert set(result["slopes_20d_pct"]) == {"5", "10", "20", "50", "100", "200"}
    assert "short_stack_vs_ma50_pct" in result
    assert not any(key in result for key in ("ma60", "ma120", "ma240", "ma260"))


# Literal values copied from /tmp/maintrend_feedback_api.json.  These are
# diagnostic fixtures only; production classification never reads symbols.
FEEDBACK = {
    "CPAXT": (1, 14.7, {5: 14.64, 10: 14.65, 20: 14.725, 50: 14.8383, 100: 14.9775, 200: 15.2},
               {5: -1.3477089, 10: -1.7437961, 20: -1.1081263, 50: -0.5029068, 100: -1.5447825, 200: -2.5582131}),
    "AAV": (4, 1.01, {5: 1.004, 10: 1.009, 20: 1.025, 50: 1.0595, 100: 1.0723, 200: 1.1356},
            {5: -4.5627376, 10: -4.3601896, 20: -3.1190926, 50: -1.5609031, 100: -3.1170943, 200: -1.9174296}),
    "SISB": (4, 9.1, {5: 9.08, 10: 9.095, 20: 9.26, 50: 9.6792, 100: 9.9125, 200: 10.809},
             {5: -5.7113188, 10: -6.3818837, 20: -5.7746121, 50: -1.8834263, 100: -4.2427814, 200: -3.7720228}),
    "TRP": (4, 3.96, {5: 4.0, 10: 4.012, 20: 4.055, 50: 4.174, 100: 4.2695, 200: 4.415},
            {5: -1.7681729, 10: -2.9041626, 20: -4.2276807, 50: -1.4403778, 100: -1.4814131, 200: -2.1064302}),
    "AEONTS": (4, 98.0, {5: 97.95, 10: 98.3, 20: 100.3, 50: 102.4167, 100: 102.4458, 200: 105.0687},
               {5: -5.0872093, 10: -5.7977959, 20: -5.0638902, 50: 2.0637635, 100: 0.7582267, 200: -0.8463887}),
    "AS": (4, 2.26, {5: 2.264, 10: 2.26, 20: 2.278, 50: 2.3267, 100: 2.4747, 200: 2.7728},
           {5: -3.7414965, 10: -4.3993232, 20: -4.7658863, 50: -2.4567140, 100: -4.5144114, 200: -1.4080501}),
    "APO": (4, 1.77, {5: 1.78, 10: 1.781, 20: 1.794, 50: 1.9822, 100: 2.0851, 200: 1.9511},
            {5: -14.4230769, 10: -15.4320988, 20: -15.5367232, 50: -4.0654341, 100: -1.4928899, 200: -0.5251351}),
    "BWG": (4, 0.21, {5: 0.228, 10: 0.221, 20: 0.2265, 50: 0.2492, 100: 0.2772, 200: 0.2783},
            {5: -6.5573770, 10: -11.2449799, 20: -10.4743083, 50: -9.7107140, 100: -4.6439628, 200: 0.3244412}),
    "DOHOME": (4, 3.5, {5: 3.532, 10: 3.528, 20: 3.612, 50: 3.7277, 100: 3.5492, 200: 3.6487},
               {5: -10.0814664, 10: -11.8440779, 20: -8.1850534, 50: 1.5528373, 100: -0.5603497, 200: -0.7291525}),
    "SPCG": (3, 11.2, {5: 10.94, 10: 10.58, 20: 10.5, 50: 9.5842, 100: 9.23, 200: 9.1675},
             {5: 17.2561629, 10: 13.2762313, 20: 12.9032258, 50: 6.1667130, 100: 1.6889398, 200: 1.9676106}),
}


def feedback_fixture(close, ma, slopes):
    series = {"close": [close] * 22, "ma": {}}
    for period in MA_PERIODS:
        current = ma[period]
        prior = current / (1.0 + slopes[period] / 100.0)
        series["ma"][str(period)] = [current, prior] + [current] * 20
    return {"timeframe": "1D", "as_of": "2026-09-11", "series": series,
            "latest": {"close": close, "ma": {str(k): v for k, v in ma.items()}}}


def test_second_pass_real_evidence_transitions_and_diagnostic_metrics():
    for symbol, (expected, close, ma, slopes) in FEEDBACK.items():
        result = classify_main_trend(feedback_fixture(close, ma, slopes))
        assert result["main_trend"] == expected, symbol
        assert result["evidence_quality"] == "FULL"
        assert result["slope_continuity"]["long_negative_count"] >= 0
        assert result["long_term_distance_median_pct"] is not None


def test_uncertain_mixed_long_term_structure_is_flagged_for_review():
    result = classify_main_trend(feedback_fixture(
        4.88, {5: 4.876, 10: 4.906, 20: 5.038, 50: 5.0433, 100: 4.7857, 200: 4.5982},
        {5: -6.05, 10: -5.38, 20: -3.72, 50: 2.21, 100: 2.25, 200: 1.08}))
    assert result["main_trend"] == 4
    assert "mixed_long_term_and_short_term_evidence_requires_review" in result["ambiguity_reasons"]


def test_bullish_medium_and_long_structure_can_be_main_two_with_short_ma5_lag():
    for close, ma, slopes in (
        (20.0, {5: 19.0, 10: 18.0, 20: 17.0, 50: 16.0, 100: 15.0, 200: 14.0},
         {5: 12.0, 10: 12.5, 20: 11.8, 50: 8.0, 100: 9.4, 200: 6.5}),
        (20.0, {5: 19.0, 10: 18.0, 20: 17.0, 50: 16.0, 100: 15.0, 200: 14.0},
         {5: 7.2, 10: 7.4, 20: 5.4, 50: 4.1, 100: 2.4, 200: 2.2}),
    ):
        result = classify_main_trend(feedback_fixture(close, ma, slopes))
        assert result["main_trend"] == 2
        assert result["reason"] == "bullish_advance_close_above_all_ma_and_positive_20_bar_slopes"


def test_main_three_is_demoted_when_ma100_or_ma200_slope_is_not_bullish():
    result = classify_main_trend(feedback_fixture(
        100.0, {5: 105.0, 10: 104.0, 20: 103.0, 50: 100.0, 100: 95.0, 200: 90.0},
        {5: -2.0, 10: -1.5, 20: -1.0, 50: -0.5, 100: -0.2, 200: -0.1}))
    assert result["main_trend"] == 1
    assert result["reason"] == "main3_rejected_long_ma100_ma200_slope_not_bullish"


def test_main_trend_display_strict_bullish_precedes_broad_bullish():
    result = classify_main_trend(feedback_fixture(
        90.0, {5: 89.0, 10: 88.0, 20: 87.0, 50: 100.0, 100: 95.0, 200: 90.0},
        {5: 2.0, 10: 2.0, 20: 2.0, 50: 1.0, 100: 1.0, 200: 1.0}))
    assert result["main_trend"] == 1
    assert result["main_trend_display"] == "1++"


def test_main_trend_display_broad_bullish_and_neutral_main_one():
    broad = classify_main_trend(feedback_fixture(
        87.5, {5: 88.0, 10: 88.0, 20: 87.0, 50: 100.0, 100: 95.0, 200: 90.0},
        {5: 2.0, 10: 2.0, 20: 2.0, 50: 1.0, 100: 1.0, 200: 1.0}))
    neutral = classify_main_trend(feedback_fixture(
        80.0, {5: 81.0, 10: 82.0, 20: 83.0, 50: 84.0, 100: 85.0, 200: 86.0},
        {5: -1.0, 10: 1.0, 20: 1.0, 50: 1.0, 100: 1.0, 200: 1.0}))
    assert broad["main_trend"] == 1
    assert broad["main_trend_display"] == "1+"
    assert neutral["main_trend"] == 1
    assert neutral["main_trend_display"] == "1"


def test_main_trend_display_strict_and_broad_bearish():
    strict = classify_main_trend(feedback_fixture(
        99.0, {5: 98.0, 10: 100.0, 20: 102.0, 50: 99.5, 100: 100.0, 200: 95.0},
        {5: -1.0, 10: -1.0, 20: -1.0, 50: 1.0, 100: 1.0, 200: 1.0}))
    broad = classify_main_trend(feedback_fixture(
        99.0, {5: 98.0, 10: 100.0, 20: 102.0, 50: 99.5, 100: 100.0, 200: 95.0},
        {5: -1.0, 10: -1.0, 20: 1.0, 50: 1.0, 100: 1.0, 200: 1.0}))
    assert strict["main_trend"] == 3
    assert strict["main_trend_display"] == "3--"
    assert broad["main_trend"] == 3
    assert broad["main_trend_display"] == "3-"


def test_partial_main_trend_never_receives_a_suffix():
    item = feedback_fixture(
        90.0, {5: 89.0, 10: 88.0, 20: 87.0, 50: 100.0, 100: 95.0, 200: 90.0},
        {5: 2.0, 10: 2.0, 20: 2.0, 50: 1.0, 100: 1.0, 200: 1.0})
    del item["latest"]["ma"]["200"]
    del item["series"]["ma"]["200"]
    result = classify_main_trend(item)
    assert result["evidence_quality"] == "PARTIAL"
    assert result["main_trend_display"] == "1"


def _classified_observations(*values, triggers=False):
    observations = []
    for index, trend in enumerate(values, start=1):
        observation = {"as_of": f"2026-09-{index:02d}", "main_trend": trend}
        if triggers:
            observation.update({"up_trigger": 110.0 + index, "down_trigger": 90.0 - index,
                                "trigger_basis": "supplied_classifier_evidence"})
        observations.append(observation)
    return observations


def test_trend_history_first_session_starts_duration_and_change_date_at_one():
    result = build_trend_history_evidence(_classified_observations(2), symbol="AAA")

    assert result[0]["trend_state"] == 2
    assert result[0]["trend_changed_date"] == "2026-09-01"
    assert result[0]["trend_duration_sessions"] == 1
    assert result[0]["actionability"] == "NONE"


def test_trend_history_continuation_and_transition_reset_duration():
    result = build_trend_history_evidence(_classified_observations(2, 2, 3, 3, 2))

    assert [(item["trend_state"], item["trend_duration_sessions"], item["trend_changed_date"])
            for item in result] == [
                (2, 1, "2026-09-01"), (2, 2, "2026-09-01"),
                (3, 1, "2026-09-03"), (3, 2, "2026-09-03"),
                (2, 1, "2026-09-05"),
            ]


def test_trend_history_uses_only_observations_through_each_eod():
    result = build_trend_history_evidence(_classified_observations(1, 1, 4))

    assert result[0]["trend_state"] == 1
    assert result[0]["trend_duration_sessions"] == 1
    assert result[1]["trend_state"] == 1
    assert result[1]["trend_duration_sessions"] == 2


def test_trend_history_emits_inclusive_trigger_operators_and_basis():
    result = build_trend_history_evidence(_classified_observations(2, triggers=True))

    assert result[0]["up_trigger"] == 111.0
    assert result[0]["down_trigger"] == 89.0
    assert result[0]["up_trigger_operator"] == ">="
    assert result[0]["down_trigger_operator"] == "<="
    assert result[0]["trigger_basis"] == "supplied_classifier_evidence"
    assert result[0]["trigger_quality"] == "VERIFIED"


def test_trend_history_missing_triggers_is_explicitly_not_verified_and_non_actionable():
    result = build_trend_history_evidence(_classified_observations(2))

    assert result[0]["up_trigger"] is None
    assert result[0]["down_trigger"] is None
    assert result[0]["trigger_basis"] == "NOT_VERIFIED"
    assert result[0]["trigger_quality"] == "NOT_VERIFIED"
    assert result[0]["trigger_reason"] == "authoritative_trigger_fields_unavailable"
    assert result[0]["actionability"] == "NONE"


@pytest.mark.parametrize("observations", [
    [],
    [{"as_of": "2026-09-01", "main_trend": 9}],
    [{"as_of": "2026-09-02", "main_trend": 2}, {"as_of": "2026-09-01", "main_trend": 2}],
    [{"as_of": "not-a-date", "main_trend": 2}],
    [{"as_of": "2026-09-01", "main_trend": 2, "up_trigger": "bad"}],
])
def test_trend_history_invalid_inputs_fail_closed_with_quality_and_reason(observations):
    result = build_trend_history_evidence(observations)

    assert result
    assert all(item["quality"] == "NOT_VERIFIED" for item in result)
    assert all(item["reason"] for item in result)
