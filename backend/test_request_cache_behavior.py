"""Behavioral tests for dashboard payload cache ownership and refresh races."""
from pathlib import Path
import subprocess


def test_request_cache_behavior():
    result = subprocess.run(
        ["node", str(Path(__file__).with_suffix(".js"))],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
