"""Regression test for insufficient-history setup state overwrite.

group_scan_results must retain the explicit fail/null setup contracts for
rows with analysis_status == "INSUFFICIENT_HISTORY" and not let the generic
setup-state classifier overwrite them.
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Make backend importable when running pytest from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from screening import group_scan_results


def _insufficient_history_row():
    return {
        "symbol": "TEST",
        "analysis_status": "INSUFFICIENT_HISTORY",
        "close": 10.0,
        "last_date": "2025-01-01",
        "trend_template": {
            "conditions_met": 0,
            "rs_rating": 0.0,
            "rs_threshold": 70,
            "conditions": {},
            "ma": {},
        },
        "trade_readiness": {},
        "vcp": {"is_vcp": False},
        "market_regime": None,
    }


def test_insufficient_history_keeps_explicit_setup_state_contracts():
    row = _insufficient_history_row()

    fake_stage = {
        "stage": "S1_basing",
        "phase": "unused_phase",
        "stage_label": "Stage 1 · Basing",
        "phase_label": "unused phase label",
        "primary_state": "unused_primary_state",
    }

    # Values that the generic classifier would return. The insufficient-history
    # branch must override these and keep its explicit contract.
    override_quality = {"pass": True, "reasons": ["generic_classifier_result"]}
    override_proximity = {
        "state": "UNEXPECTED_STATE",
        "pivot": 999.0,
        "distance_pct": 12.5,
        "zone": "UNEXPECTED_ZONE",
    }

    with patch("screening.classify_stage", return_value=fake_stage), \
         patch("screening.compute_setup_state",
               return_value={"quality": override_quality,
                             "proximity": override_proximity}), \
         patch("screening.compute_symbol_ranking"):
        groups = group_scan_results([row])

    base_group = groups.get("base", [])
    assert base_group, "insufficient-history row should be grouped as base"
    daily_state = base_group[0]["daily_state"]

    assert daily_state["setup_quality"] == {
        "pass": False,
        "reasons": ["insufficient_history"],
    }
    assert daily_state["setup_proximity"] == {
        "state": None,
        "pivot": None,
        "distance_pct": None,
        "zone": None,
    }
