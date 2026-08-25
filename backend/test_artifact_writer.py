from pathlib import Path

from artifact_writer import atomic_write_json, atomic_write_text


def test_atomic_write_text_replaces_target(tmp_path: Path):
    target = tmp_path / "dashboard.html"
    target.write_text("old", encoding="utf-8")
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.glob(".*dashboard.html.*")) == []


def test_atomic_write_json_is_valid(tmp_path: Path):
    import json
    target = tmp_path / "snapshot.json"
    atomic_write_json(target, {"items": [1], "source": "test"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"items": [1], "source": "test"}
