from pathlib import Path

import eod_healthcheck


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_outputs_live_outside_the_git_worktree():
    update_unit = (ROOT / "backend" / "update_data.service").read_text(encoding="utf-8")
    health_unit = (ROOT / "backend" / "signalix-eod-healthcheck.service").read_text(encoding="utf-8")

    assert "/var/log/signalix/update.log" in update_unit
    assert "/root/signalix/update_log.txt" not in update_unit
    assert "/var/log/signalix/eod_healthcheck.jsonl" in health_unit
    assert "/root/signalix/eod_healthcheck_log.jsonl" not in health_unit
    assert eod_healthcheck.DEFAULT_STATE_FILE == "/var/lib/signalix/eod_healthcheck_observations.json"


def test_backend_api_is_not_bound_to_every_public_interface():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:8000:8000"' in compose
    assert '\n      - "8000:8000"' not in compose
