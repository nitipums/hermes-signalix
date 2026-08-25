"""Fail-closed verifier for the canonical MVP release artifact.

Checks the served MVP artifact against the latest canonical Daily scan run and
paired artifact manifest. This verifier never reads dashboard_snapshot.json or
scan_results.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg2

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "mvp_snapshot.json"
MANIFEST = HERE / "artifact_manifest.json"


def pg_config():
    return {
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "signalix"),
        "password": os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
        "dbname": os.getenv("POSTGRES_DB", "signalix"),
    }


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    for path in (SNAPSHOT, MANIFEST):
        if not path.is_file():
            raise RuntimeError(f"missing canonical MVP artifact: {path.name}")

    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if snapshot.get("contract_version") != "signalix.mvp.v1":
        raise RuntimeError("invalid MVP contract version")
    items = snapshot.get("items")
    if not isinstance(items, list):
        raise RuntimeError("MVP items is not a list")

    conn = psycopg2.connect(**pg_config())
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, evaluated_symbol_count
            FROM daily_scan_runs r
            WHERE r.scanner_version = 'signalix/daily-state-v2'
              AND r.source_lineage->>'source' = 'price_data'
              AND COALESCE(r.source_lineage->>'mode', '') <> 'historical_backfill'
            ORDER BY run_timestamp DESC, id DESC
            LIMIT 1
        """)
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise RuntimeError("no canonical production Daily run")

    expected_run_id, expected_count = str(row[0]), int(row[1])
    if snapshot.get("run_id") != expected_run_id:
        raise RuntimeError(
            f"MVP run_id mismatch: artifact={snapshot.get('run_id')} DB={expected_run_id}"
        )
    if len(items) != expected_count:
        raise RuntimeError(f"MVP item count mismatch: artifact={len(items)} DB={expected_count}")
    if manifest.get("run_id") != expected_run_id:
        raise RuntimeError("artifact manifest run_id mismatch")

    files = manifest.get("files", {})
    for name, path in (("mvp_snapshot.json", SNAPSHOT), ("dashboard.html", HERE / "dashboard.html")):
        entry = files.get(name, {})
        if not path.is_file() or entry.get("sha256") != sha256(path):
            raise RuntimeError(f"artifact hash mismatch: {name}")

    print(json.dumps({
        "status": "PASS",
        "contract_version": snapshot["contract_version"],
        "run_id": expected_run_id,
        "items": len(items),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"MVP_RELEASE_VERIFY_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
