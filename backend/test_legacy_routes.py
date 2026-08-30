from fastapi import HTTPException

from app import dashboard_snapshot


def test_legacy_dashboard_snapshot_is_explicitly_retired():
    try:
        dashboard_snapshot()
    except HTTPException as exc:
        assert exc.status_code == 410
        assert "retired" in str(exc.detail)
    else:
        raise AssertionError("legacy dashboard snapshot unexpectedly remained live")
