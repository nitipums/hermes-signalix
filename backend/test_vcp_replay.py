from datetime import datetime, timedelta, timezone

import run_vcp_replay_1m
from run_vcp_replay_1m import (
    attach_replay_evaluation,
    attach_sequence_v2_evaluation,
    append_bounded_diagnostic,
    build_replay_result,
    evaluate_trade,
    insert_replay_run,
    load_replay_rows,
    make_replay_id,
    pending_replay_points,
    point_in_time_rows,
    select_replay_snapshots,
    sequence_v2_trade_plan,
    trade_plan,
    validate_replay_results,
)


def test_replay_run_insert_persists_complete_marginable_manifest():
    class Cursor:
        def __init__(self):
            self.query = None
            self.params = None

        def execute(self, query, params):
            self.query = query
            self.params = params

    cursor = Cursor()
    manifest = {
        "universe_filter": "marginable_long",
        "base_active_ord_count": 931,
        "eligible_count": 237,
        "excluded_count": 694,
        "schema_version": "signalix.marginable.v1",
        "source_document": "SET marginable list",
        "effective_date": "2026-08-01",
    }
    insert_replay_run(
        cursor, replay_id="replay-1",
        window_start="2026-08-03T05:30:00+00:00",
        window_end="2026-08-03T09:45:00+00:00",
        as_of="2026-08-03T05:30:00+00:00", eligible_count=237,
        evaluated_count=237, universe_manifest=manifest,
        cadence="daily", snapshots_per_day=2,
    )

    expected_fields = (
        "universe_filter", "base_active_ord_count", "excluded_count",
        "margin_schema_version", "margin_source_document",
        "margin_effective_date", "cadence", "snapshots_per_day",
    )
    for field in expected_fields:
        assert field in cursor.query
    assert "eligible_count" in cursor.query
    assert "ON CONFLICT (replay_id) DO NOTHING" in cursor.query
    assert "DROP TABLE" not in cursor.query.upper()
    assert cursor.params == (
        "replay-1", "2026-08-03T05:30:00+00:00",
        "2026-08-03T09:45:00+00:00", "2026-08-03T05:30:00+00:00",
        "signalix/vcp-finder-60m-v2-latest-sequence", 237, 237,
        "marginable_long", 931, 694,
        "signalix.marginable.v1", "SET marginable list", "2026-08-01",
        "daily", 2,
    )


def test_replay_ddl_is_additive_and_existing_schema_compatible():
    added_columns = (
        "universe_filter", "base_active_ord_count", "excluded_count",
        "margin_schema_version", "margin_source_document",
        "margin_effective_date", "cadence", "snapshots_per_day",
    )
    ddl = run_vcp_replay_1m.DDL.upper()
    for column in added_columns:
        assert f"ADD COLUMN IF NOT EXISTS {column.upper()}" in ddl
    assert "DROP TABLE" not in ddl
    assert "CREATE TABLE IF NOT EXISTS VCP_FINDER_60M_REPLAY_RUNS" in ddl
    assert "CREATE TABLE IF NOT EXISTS VCP_FINDER_60M_REPLAY_RESULTS" in ddl
    assert "CREATE OR REPLACE" not in ddl


def test_same_config_has_no_pending_points_but_universe_or_frequency_does():
    snapshots = [
        datetime(2026, 8, 3, hour, tzinfo=timezone.utc)
        for hour in (5, 9)
    ]
    existing = {
        make_replay_id("shadow", "daily", as_of, index,
                       universe="marginable_long", snapshots_per_day=2)
        for index, as_of in enumerate(snapshots, 1)
    }

    assert pending_replay_points(
        "shadow", "daily", snapshots, existing,
        universe="marginable_long", snapshots_per_day=2,
    ) == []
    assert len(pending_replay_points(
        "shadow", "daily", snapshots, existing,
        universe="active_ord", snapshots_per_day=2,
    )) == 2
    assert len(pending_replay_points(
        "shadow", "daily", snapshots, existing,
        universe="marginable_long", snapshots_per_day=1,
    )) == 2


def test_select_replay_snapshots_two_points_per_bangkok_day():
    selected = select_replay_snapshots(
        timestamps=[
            "2026-08-03T05:00:00+00:00",
            "2026-08-03T05:30:00+00:00",
            "2026-08-03T09:00:00+00:00",
            "2026-08-03T09:45:00+00:00",
        ],
        end="2026-08-03T10:00:00+00:00",
        cadence="daily",
        snapshots_per_day=2,
    )

    assert [x.isoformat() for x in selected["snapshots"]] == [
        "2026-08-03T05:30:00+00:00",
        "2026-08-03T09:45:00+00:00",
    ]


def test_resolve_replay_universe_uses_marginable_manifest(monkeypatch):
    monkeypatch.setattr(run_vcp_replay_1m, "active_ord_symbols", lambda pg: ["BBB", "AAA"])
    monkeypatch.setattr(
        run_vcp_replay_1m,
        "eligible_symbols",
        lambda symbols: (["AAA"], {"universe_filter": "marginable_long", "eligible_count": 1}),
    )

    symbols, manifest = run_vcp_replay_1m.resolve_replay_universe(object(), "marginable_long")

    assert symbols == ["AAA"]
    assert manifest["eligible_count"] == 1
    validate_replay_results([{"decision_shadow_v2": {}}], len(symbols), "replay-1")


def test_marginable_universe_symbols_are_exact_sql_any_parameter(monkeypatch):
    selected = [f"S{index:03d}" for index in range(237)]
    monkeypatch.setattr(run_vcp_replay_1m, "active_ord_symbols", lambda pg: selected + ["EXCLUDED"])
    monkeypatch.setattr(
        run_vcp_replay_1m, "eligible_symbols",
        lambda symbols: (selected, {
            "universe_filter": "marginable_long",
            "base_active_ord_count": 238,
            "eligible_count": 237,
            "excluded_count": 1,
        }),
    )

    symbols, manifest = run_vcp_replay_1m.resolve_replay_universe(object(), "marginable_long")

    class Cursor:
        def __init__(self):
            self.params = None

        def execute(self, _query, params):
            self.params = params

        def fetchall(self):
            return []

    cursor = Cursor()
    load_replay_rows(
        cursor, symbols, end=datetime(2026, 8, 3, tzinfo=timezone.utc),
        query_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    assert cursor.params[0] == selected
    assert manifest["eligible_count"] == 237
    validate_replay_results([{"decision_shadow_v2": {}}] * 237, 237, "replay-237")
    try:
        validate_replay_results([{"decision_shadow_v2": {}}] * 237, 931, "replay-931")
    except RuntimeError as exc:
        assert "evaluated 237 of 931" in str(exc)
    else:
        raise AssertionError("validator must use the selected eligible count")


def test_select_replay_snapshots_uses_latest_bangkok_dates_not_query_tail():
    timestamps = [
        datetime(2026, 8, 17, 16, 30, tzinfo=timezone.utc),  # Aug 17 BKK
        datetime(2026, 8, 17, 17, 0, tzinfo=timezone.utc),   # Aug 18 BKK
        datetime(2026, 8, 18, 16, 30, tzinfo=timezone.utc),  # Aug 18 BKK
        datetime(2026, 8, 19, 16, 30, tzinfo=timezone.utc),  # Aug 19 BKK
    ]

    selected = select_replay_snapshots(
        timestamps,
        end=datetime(2026, 8, 19, 17, tzinfo=timezone.utc),
        trading_days=2,
        window_start=datetime(2026, 8, 17, tzinfo=timezone.utc),
    )

    assert selected["selected_dates"] == [datetime(2026, 8, 18).date(), datetime(2026, 8, 19).date()]
    assert selected["snapshots"] == timestamps[2:]
    assert selected["window_start"] == timestamps[2]
    assert selected["window_end"] == timestamps[3]


def test_select_replay_snapshots_fails_when_dates_or_snapshot_bound_is_exceeded():
    timestamps = [datetime(2026, 8, day, 10, tzinfo=timezone.utc) for day in (17, 18)]

    try:
        select_replay_snapshots(
            timestamps, end=datetime(2026, 8, 19, tzinfo=timezone.utc),
            trading_days=3,
        )
    except ValueError as exc:
        assert "requested 3 trading dates" in str(exc)
    else:
        raise AssertionError("under-represented trading-day request must fail")

    try:
        select_replay_snapshots(
            timestamps, end=datetime(2026, 8, 19, tzinfo=timezone.utc),
            cadence="60m", max_snapshots=1,
        )
    except ValueError as exc:
        assert "max_snapshots=1" in str(exc)
    else:
        raise AssertionError("snapshot bound must fail clearly")


def test_two_point_cutoffs_use_latest_at_or_before_boundary():
    selected = select_replay_snapshots(
        ["2026-08-03T05:30:00+00:00", "2026-08-03T09:44:00+00:00"],
        end="2026-08-03T10:00:00+00:00", snapshots_per_day=2,
    )
    assert selected["snapshots"] == [
        datetime(2026, 8, 3, 5, 30, tzinfo=timezone.utc),
        datetime(2026, 8, 3, 9, 44, tzinfo=timezone.utc),
    ]


def test_two_point_cutoffs_fail_closed_when_a_cutoff_is_missing():
    try:
        select_replay_snapshots(
            ["2026-08-03T09:00:00+00:00"],
            end="2026-08-03T10:00:00+00:00", snapshots_per_day=2,
        )
    except ValueError as exc:
        assert "no snapshot at or before 12:30 BKK" in str(exc)
    else:
        raise AssertionError("missing cutoff evidence must fail closed")


def test_two_point_selection_preserves_multiple_bangkok_dates():
    selected = select_replay_snapshots(
        [
            "2026-08-02T05:30:00+00:00", "2026-08-02T09:45:00+00:00",
            "2026-08-03T05:30:00+00:00", "2026-08-03T09:45:00+00:00",
        ],
        end="2026-08-03T10:00:00+00:00", snapshots_per_day=2,
    )
    assert selected["selected_dates"] == [
        datetime(2026, 8, 2).date(), datetime(2026, 8, 3).date(),
    ]
    assert len(selected["snapshots"]) == 4


def test_60m_mode_remains_every_stored_snapshot_with_default_one_per_day():
    timestamps = [
        datetime(2026, 8, 3, hour, tzinfo=timezone.utc) for hour in (5, 6, 9)
    ]
    selected = select_replay_snapshots(
        timestamps, end=datetime(2026, 8, 3, 10, tzinfo=timezone.utc),
        cadence="60m",
    )
    assert selected["snapshots"] == timestamps


def test_point_in_time_rows_excludes_future_bars():
    as_of = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)
    rows = [{"ts": as_of - timedelta(hours=1)}, {"ts": as_of},
            {"ts": as_of + timedelta(hours=1)}]

    assert point_in_time_rows(rows, as_of) == rows[:2]


def test_diagnostics_are_bounded_and_coverage_contract_is_strict():
    diagnostics = []
    for value in range(3):
        append_bounded_diagnostic(diagnostics, value, 2)
    assert diagnostics == [0, 1]

    validate_replay_results([{"decision_shadow_v2": {}}], 1, "replay-1")
    try:
        validate_replay_results([{}], 1, "replay-1")
    except RuntimeError as exc:
        assert "missing decision_shadow_v2" in str(exc)
    else:
        raise AssertionError("missing decision shadow must fail")


def test_low_cheat_trade_plan_uses_close_and_three_r_target():
    plan = trade_plan({
        "vcp_type": {"base_type": "low_cheat_vcp", "entry_profile": "early_entry"},
        "price": {"last_close": 100, "invalidation": 95},
        "breakout": {"required_close": 101},
    })

    assert plan == {
        "base_type": "low_cheat_vcp",
        "entry_profile": "early_entry",
        "entry": 100.0,
        "stop": 95.0,
        "target": 115.0,
        "rr_multiple": 3.0,
    }


def test_standard_trade_plan_uses_breakout_entry_and_three_r_target():
    plan = trade_plan({
        "vcp_type": {"base_type": "standard_vcp", "entry_profile": "standard_entry"},
        "price": {"last_close": 100, "invalidation": 96},
        "breakout": {"required_close": 102},
    })

    assert plan["entry"] == 102.0
    assert plan["stop"] == 96.0
    assert plan["target"] == 120.0
    assert plan["rr_multiple"] == 3.0


def test_same_bar_stop_and_target_is_ambiguous():
    plan = {"entry": 100.0, "stop": 95.0, "target": 115.0}

    result = evaluate_trade(plan, [{"high": 116, "low": 94}])

    assert result["outcome"] == "ambiguous_same_bar"
    assert result["mfe_r"] == 3.2
    assert result["mae_r"] == -1.2


def test_future_outcome_reads_only_bars_after_detection():
    plan = {"entry": 100.0, "stop": 95.0, "target": 115.0}

    result = evaluate_trade(plan, [{"high": 110, "low": 98}, {"high": 116, "low": 105}])

    assert result["outcome"] == "target_hit"
    assert result["bars_observed"] == 2


def test_standard_plan_ignores_stop_before_entry_activation():
    plan = {"base_type": "standard_vcp", "entry": 102.0, "stop": 96.0, "target": 120.0}
    rows = [
        {"ts": "a", "high": 101.0, "low": 95.0},
        {"ts": "b", "high": 103.0, "low": 100.0},
        {"ts": "c", "high": 121.0, "low": 105.0},
    ]

    result = evaluate_trade(plan, rows)

    assert result["entry_activated"] is True
    assert result["entry_ts"] == "b"
    assert result["pre_entry_bars"] == 1
    assert result["outcome"] == "target_hit"


def test_standard_plan_reports_not_activated_when_entry_never_trades():
    plan = {"base_type": "standard_vcp", "entry": 102.0, "stop": 96.0, "target": 120.0}

    result = evaluate_trade(plan, [{"ts": "a", "high": 101.0, "low": 95.0}])

    assert result["entry_activated"] is False
    assert result["outcome"] == "entry_not_activated"
    assert result["bars_observed"] == 0


def test_low_cheat_plan_is_active_from_detection():
    plan = {"base_type": "low_cheat_vcp", "entry": 100.0, "stop": 95.0, "target": 115.0}

    result = evaluate_trade(plan, [{"ts": "a", "high": 101.0, "low": 94.0}])

    assert result["entry_activated"] is True
    assert result["entry_ts"] == "detection"
    assert result["pre_entry_bars"] == 0
    assert result["outcome"] == "stop_hit"


def test_build_replay_result_passes_point_in_time_daily_context(monkeypatch):
    captured = {}

    def fake_find(frame, *, as_of, daily_context, include_sequence_policy_shadow):
        captured["as_of"] = as_of
        captured["daily_context"] = daily_context
        captured["include_sequence_policy_shadow"] = include_sequence_policy_shadow
        return {
            "state": "FORMING", "actionable": False,
            "data": {}, "price": {}, "breakout": {}, "pattern": {},
            "evidence": {}, "provenance": {},
        }

    monkeypatch.setattr(run_vcp_replay_1m, "find_vcp_60m", fake_find)
    monkeypatch.setattr(run_vcp_replay_1m, "_classify_types", lambda result, **_: result)
    as_of = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)

    result = build_replay_result(
        "AAA", [], as_of=as_of, replay_id="replay-1",
        daily_context={"trend_pass": True, "as_of": "2026-08-26"},
        daily_metrics={"avg_trade_value_20": 20_000_000, "as_of": "2026-08-26"},
        marginable_record={"margin_rate_pct": 50},
    )

    assert captured == {
        "as_of": as_of,
        "daily_context": {"trend_pass": True, "as_of": "2026-08-26"},
        "include_sequence_policy_shadow": True,
    }
    assert result["data"]["daily_metrics"]["avg_trade_value_20"] == 20_000_000
    assert result["provenance"]["replay_id"] == "replay-1"
    assert result["decision_shadow_v2"]["policy_version"] == "signalix/vcp-decision-shadow-v2"
    assert result["decision_shadow_v2"]["symbol"] == "AAA"
    assert result["marginable"] == {"is_marginable": True, "margin_rate_pct": 50}
    assert result["decision_shadow_v2"]["tradability"]["marginable_pass"] is True
    assert "sequence_v2_trade_plan" in result


def test_replay_id_prefix_is_explicit_and_isolated():
    as_of = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)

    replay_id = make_replay_id("vcp-shadow-v2", "60m", as_of, 3)

    assert replay_id == "vcp-shadow-v2-60m-20260827T060000Z-003"


def test_non_default_replay_configurations_have_unique_ids_and_are_idempotent():
    as_of = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)
    active_default = make_replay_id("shadow", "daily", as_of, 1)
    marginable = make_replay_id(
        "shadow", "daily", as_of, 1, universe="marginable_long",
    )
    twice_daily = make_replay_id(
        "shadow", "daily", as_of, 1, snapshots_per_day=2,
    )
    assert active_default == "shadow-daily-20260827T060000Z-001"
    assert len({active_default, marginable, twice_daily}) == 3
    assert pending_replay_points(
        "shadow", "daily", [as_of], {marginable}, universe="marginable_long",
    ) == []
    assert pending_replay_points(
        "shadow", "daily", [as_of], {active_default}, snapshots_per_day=2,
    )[0][2] == twice_daily


def test_pending_replay_points_skip_already_persisted_ids():
    snapshots = [
        datetime(2026, 8, 27, hour, tzinfo=timezone.utc)
        for hour in (2, 3, 4)
    ]
    existing = {make_replay_id("shadow", "60m", snapshots[0], 1)}

    pending = pending_replay_points("shadow", "60m", snapshots, existing)

    assert pending == [
        (2, snapshots[1], "shadow-60m-20260827T030000Z-002"),
        (3, snapshots[2], "shadow-60m-20260827T040000Z-003"),
    ]


def test_attach_replay_evaluation_persists_descriptive_outcome():
    result = {"symbol": "AAA"}
    plan = {"base_type": "standard_vcp", "entry": 100.0, "stop": 95.0, "target": 115.0}
    future = [{"ts": "next", "high": 116.0, "low": 100.0}]

    evaluation = attach_replay_evaluation(result, plan, future)

    assert evaluation["outcome"] == "target_hit"
    assert result["replay_evaluation"] == evaluation


def test_sequence_v2_trade_plan_uses_shadow_required_close_and_invalidation():
    result = {
        "sequence_policy_shadow_v2": {
            "standard_entry_eligible": True,
            "low_cheat_observed": False,
            "breakout": {"required_close": 102.0},
            "price": {"invalidation": 96.0},
        }
    }

    plan = sequence_v2_trade_plan(result)

    assert plan == {
        "base_type": "standard_vcp",
        "entry_profile": "standard_entry",
        "entry": 102.0,
        "stop": 96.0,
        "target": 120.0,
        "rr_multiple": 3.0,
        "sequence_policy_version": "signalix/vcp-sequence-policy-shadow-v2",
    }


def test_sequence_v2_trade_plan_rejects_incomplete_morphology():
    result = {
        "sequence_policy_shadow_v2": {
            "standard_entry_eligible": False,
            "breakout": {"required_close": 102.0},
            "price": {"invalidation": 96.0},
        }
    }
    assert sequence_v2_trade_plan(result) is None


def test_low_cheat_observation_never_creates_early_entry_plan():
    result = {
        "sequence_policy_shadow_v2": {
            "policy_version": "signalix/vcp-sequence-policy-shadow-v2",
            "standard_entry_eligible": True,
            "low_cheat_observed": True,
            "breakout": {"required_close": 102.0},
            "price": {"last_close": 100.0, "invalidation": 96.0},
        }
    }
    plan = sequence_v2_trade_plan(result)
    assert plan["base_type"] == "standard_vcp"
    assert plan["entry"] == 102.0


def test_attach_sequence_v2_evaluation_uses_separate_namespace():
    result = {
        "sequence_v2_trade_plan": {
            "base_type": "standard_vcp", "entry": 100.0,
            "stop": 95.0, "target": 115.0,
        }
    }
    evaluation = attach_sequence_v2_evaluation(
        result, [{"ts": "next", "high": 116.0, "low": 100.0}],
    )
    assert evaluation["outcome"] == "target_hit"
    assert result["sequence_v2_replay_evaluation"] == evaluation
    assert "replay_evaluation" not in result
