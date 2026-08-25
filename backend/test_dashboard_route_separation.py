"""P1-01 contract: MVP and legacy route ownership are separate modules."""

from pathlib import Path

import pytest


HERE = Path(__file__).parent


def test_mvp_route_module_owns_api_dispatch():
    import mvp_routes
    assert callable(mvp_routes.handle_mvp_api)
    assert callable(mvp_routes.load_snapshot)


def test_mvp_requires_canonical_artifact_without_legacy_fallback(tmp_path, monkeypatch):
    import mvp_routes
    legacy = tmp_path / "dashboard_snapshot.json"
    legacy.write_text('{"items": [{"symbol": "OLD"}]}', encoding="utf-8")
    monkeypatch.setattr(mvp_routes, "_MVP_SNAPSHOT_PATH", str(tmp_path / "missing-mvp.json"))
    with pytest.raises(FileNotFoundError):
        mvp_routes.load_payload()


def test_legacy_route_module_owns_legacy_mapping():
    import legacy_routes
    assert legacy_routes.legacy_file_for_path("/dashboard.html", "/legacy") == "/legacy/dashboard.html"
    assert legacy_routes.legacy_file_for_path("/portal", "/legacy") == "/legacy/portal.html"
    assert legacy_routes.legacy_file_for_path("/portfolio", "/legacy") == "/legacy/portfolio.html"
    assert legacy_routes.legacy_file_for_path("/mvp", "/legacy") is None


def test_legacy_server_is_standalone_entrypoint():
    import legacy_server
    assert hasattr(legacy_server, "LegacyHandler")
    assert legacy_server.LegacyHandler is not None


def test_dashboard_server_is_dispatcher_not_api_owner():
    import dashboard_server
    import mvp_routes
    import legacy_routes
    assert dashboard_server.handle_mvp_api is mvp_routes.handle_mvp_api
    assert dashboard_server.legacy_file_for_path is legacy_routes.legacy_file_for_path
