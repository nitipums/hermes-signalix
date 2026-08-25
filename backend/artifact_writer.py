"""Atomic artifact writes shared by dashboard projections."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_json(path: str | Path, payload: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, separators=(",", ":"), default=str),
    )


def write_artifact_manifest(path: str | Path, run_id: str | None, snapshot_path: str | Path, html_path: str | Path | None = None) -> dict:
    """Write a compact manifest for canonical MVP artifacts.

    ``html_path`` remains optional for legacy callers/tests, but the MVP
    production build passes only mvp_snapshot.json and must not depend on the
    quarantined dashboard.html artifact.
    """
    files = {}
    candidates = [Path(snapshot_path)]
    if html_path is not None:
        candidates.append(Path(html_path))
    for candidate in candidates:
        data = candidate.read_bytes()
        files[candidate.name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    manifest = {"run_id": run_id, "files": files}
    atomic_write_json(path, manifest)
    return manifest
