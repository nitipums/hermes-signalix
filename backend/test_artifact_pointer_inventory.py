import json
import datetime as dt

import artifact_pointer_inventory as inventory
import chart_read_model
import intraday_quote_read_model
import market_breadth_artifact


def _publish_market_breadth(root):
    from test_market_breadth_artifact import publish_fixture
    return publish_fixture(root)


def _publish_chart(root, monkeypatch, timeframe="1D"):
    from test_chart_read_model import _payload
    monkeypatch.setattr(
        "mvp_chart_db.project_chart_db_response",
        lambda symbol, timeframe, connection, canonical_item: _payload(symbol, timeframe),
    )
    return chart_read_model.publish(
        object(), ["AAA"], timeframe=timeframe, root=root,
        generated_at=dt.datetime.now(dt.timezone.utc),
    )


def test_missing_market_breadth_and_chart_pointers_are_explicitly_blocked(tmp_path):
    breadth = inventory.inspect_market_breadth(tmp_path / "breadth")
    charts = inventory.inspect_charts(tmp_path / "charts")
    assert breadth["status"] == "NOT_VERIFIED"
    assert breadth["reason"] == "current_pointer_missing_blocked"
    assert all(item["reason"] == "current_pointer_missing_blocked" for item in charts)


def test_trend_map_and_intraday_valid_fixtures_are_identity_and_hash_bound(tmp_path):
    trend_root = tmp_path / "trend"
    # Use the existing publisher fixture contract, while keeping all writes in tmp_path.
    from test_trend_map_read_model_publisher import publish as publish_trend
    publish_trend(trend_root)
    assert inventory.inspect_trend_map(trend_root)["status"] == "VERIFIED"

    quote_root = tmp_path / "quotes"
    from test_intraday_quote_read_model import Adapter, NOW
    intraday_quote_read_model.publish(object(), {"run_id": "run-1", "status": "full_success"},
                                      root=quote_root, adapter=Adapter(), generated_at=NOW)
    result = inventory.inspect_intraday_quotes(quote_root, now=NOW)
    assert result["status"] == "VERIFIED"
    assert result["freshness_status"] == "FRESH"
    assert result["target_exists"] is True


def test_intraday_integrity_is_verified_separately_from_stale_freshness(tmp_path):
    from test_intraday_quote_read_model import Adapter, NOW
    root = tmp_path / "quotes"
    intraday_quote_read_model.publish(object(), {"run_id": "run-1", "status": "full_success"},
                                      root=root, adapter=Adapter(), generated_at=NOW)
    result = inventory.inspect_intraday_quotes(
        root, now=dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc))
    assert result["status"] == "VERIFIED"
    assert result["freshness_status"] == "STALE"


def test_tampered_target_and_escape_pointer_fail_closed(tmp_path):
    from test_intraday_quote_read_model import Adapter, NOW
    root = tmp_path / "quotes"
    intraday_quote_read_model.publish(object(), {"run_id": "run-1", "status": "full_success"},
                                      root=root, adapter=Adapter(), generated_at=NOW)
    pointer = json.loads((root / "current.json").read_text())
    target = root / pointer["artifact_path"]
    artifact = json.loads(target.read_text())
    artifact["run_id"] = "tampered"
    target.write_text(json.dumps(artifact))
    assert inventory.inspect_intraday_quotes(root)["status"] == "NOT_VERIFIED"

    pointer["artifact_path"] = "../outside.json"
    (root / "current.json").write_text(json.dumps(pointer))
    assert inventory.inspect_intraday_quotes(root)["status"] == "NOT_VERIFIED"


def test_market_breadth_pointer_validates_version_identity_schema_and_exact_bytes(tmp_path):
    root = tmp_path / "breadth"
    published = _publish_market_breadth(root)
    assert inventory.inspect_market_breadth(root)["status"] == "VERIFIED"

    pointer_path = root / "current.json"
    target = root / "versions" / published["path"]

    pointer = json.loads(pointer_path.read_text())
    pointer["artifact_version"] = "bogus"
    pointer_path.write_text(json.dumps(pointer))
    assert inventory.inspect_market_breadth(root)["status"] == "NOT_VERIFIED"

    pointer = json.loads(pointer_path.read_text())
    pointer["artifact_version"] = market_breadth_artifact.ARTIFACT_VERSION
    pointer["path"] = "renamed.json"
    pointer_path.write_text(json.dumps(pointer))
    assert inventory.inspect_market_breadth(root)["status"] == "NOT_VERIFIED"

    pointer["path"] = published["path"]
    pointer["content_hash"] = "0" * 64
    pointer_path.write_text(json.dumps(pointer))
    assert inventory.inspect_market_breadth(root)["status"] == "NOT_VERIFIED"

    pointer["content_hash"] = published["content_hash"]
    pointer_path.write_text(json.dumps(pointer))
    artifact = json.loads(target.read_text())
    artifact["schema_version"] = "bogus"
    target.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":")))
    assert inventory.inspect_market_breadth(root)["status"] == "NOT_VERIFIED"
    target.write_bytes(json.dumps(
        {**artifact, "schema_version": market_breadth_artifact.SCHEMA_VERSION},
        sort_keys=True, separators=(",", ":"),
    ).encode())
    target.write_bytes(target.read_bytes() + b" ")
    assert inventory.inspect_market_breadth(root)["status"] == "NOT_VERIFIED"

    pointer["path"] = "../" + published["path"]
    pointer_path.write_text(json.dumps(pointer))
    assert inventory.inspect_market_breadth(root)["status"] == "NOT_VERIFIED"


def test_chart_pointer_validates_schema_identity_hash_metadata_freshness_and_containment(tmp_path, monkeypatch):
    root = tmp_path / "charts"
    _publish_chart(root, monkeypatch)
    assert inventory.inspect_charts(root)[0]["status"] == "VERIFIED"

    pointer_path = root / "current-1D.json"
    pointer = json.loads(pointer_path.read_text())
    target = root / pointer["artifact_path"]
    original_artifact = target.read_bytes()

    pointer["schema_version"] = "bogus"
    pointer_path.write_text(json.dumps(pointer))
    assert inventory.inspect_charts(root)[0]["status"] == "NOT_VERIFIED"

    pointer = json.loads(pointer_path.read_text())
    pointer["schema_version"] = chart_read_model.SCHEMA_VERSION
    pointer["artifact_id"] = "chart-1d-" + "0" * 24
    pointer_path.write_text(json.dumps(pointer))
    assert inventory.inspect_charts(root)[0]["status"] == "NOT_VERIFIED"

    pointer = json.loads(pointer_path.read_text())
    pointer["artifact_id"] = json.loads(original_artifact)["artifact_id"]
    artifact = json.loads(original_artifact)
    artifact["schema_version"] = "bogus"
    target.write_text(json.dumps(artifact))
    pointer_path.write_text(json.dumps(pointer))
    assert inventory.inspect_charts(root)[0]["status"] == "NOT_VERIFIED"
    target.write_bytes(original_artifact)

    pointer = json.loads(pointer_path.read_text())
    pointer["artifact_id"] = json.loads(original_artifact)["artifact_id"]
    pointer["generated_at"] = "2000-01-01T00:00:00+00:00"
    pointer_path.write_text(json.dumps(pointer))
    assert inventory.inspect_charts(root)[0]["status"] == "NOT_VERIFIED"

    pointer = json.loads(pointer_path.read_text())
    pointer["generated_at"] = json.loads(original_artifact)["generated_at"]
    pointer["as_of"] = "2000-01-01"
    pointer_path.write_text(json.dumps(pointer))
    assert inventory.inspect_charts(root)[0]["status"] == "NOT_VERIFIED"

    pointer = json.loads(pointer_path.read_text())
    pointer["as_of"] = json.loads(original_artifact)["as_of"]
    pointer_path.write_text(json.dumps(pointer))
    artifact = json.loads(original_artifact)
    artifact["entries"]["AAA"]["candles"][0]["close"] = 999
    target.write_text(json.dumps(artifact))
    assert inventory.inspect_charts(root)[0]["status"] == "NOT_VERIFIED"

    target.write_bytes(original_artifact)
    pointer["artifact_path"] = target.name
    (root / target.name).write_bytes(original_artifact)
    pointer_path.write_text(json.dumps(pointer))
    assert inventory.inspect_charts(root)[0]["status"] == "NOT_VERIFIED"


def test_inventory_does_not_create_or_modify_valid_fixture_roots(tmp_path, monkeypatch):
    breadth_root = tmp_path / "breadth"
    _publish_market_breadth(breadth_root)
    chart_root = tmp_path / "charts"
    _publish_chart(chart_root, monkeypatch)
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*") if path.is_file()
    }

    inventory.inventory_active_read_models(roots={"market_breadth": breadth_root, "charts": chart_root})

    after = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*") if path.is_file()
    }
    assert after == before


def test_chart_candidates_exclude_all_current_timeframe_targets(tmp_path, monkeypatch):
    root = tmp_path / "charts"
    current = {}
    for timeframe in ("1D", "60M", "1W", "1M"):
        current[timeframe] = _publish_chart(root, monkeypatch, timeframe)
    extra = root / "versions" / "chart-unused.json"
    extra.write_text("{}")

    results = inventory.inspect_charts(root)
    protected = {item["target"] for item in results}
    assert all(item["status"] == "VERIFIED" for item in results)
    assert all(set(item["candidates"]).isdisjoint(
        {path.rsplit("/", 1)[-1] for path in protected}) for item in results)
    assert all("chart-unused.json" in item["candidates"] for item in results)
