"""MVP-only artifact verifier; no legacy HTML dependency."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import psycopg2

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "mvp_snapshot.json"
MANIFEST = HERE / "artifact_manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not SNAPSHOT.is_file() or not MANIFEST.is_file():
        raise RuntimeError("canonical MVP artifact or manifest missing")
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if snapshot.get("contract_version") != "signalix.mvp.v1":
        raise RuntimeError("invalid MVP contract")
    items = snapshot.get("items")
    if not isinstance(items, list):
        raise RuntimeError("MVP items is not a list")

    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "signalix"),
        password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
        dbname=os.getenv("POSTGRES_DB", "signalix"),
    )
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, evaluated_symbol_count
            FROM daily_scan_runs
            WHERE scanner_version='signalix/daily-state-v2'
              AND source_lineage->>'source'='price_data'
              AND COALESCE(source_lineage->>'mode','') <> 'historical_backfill'
            ORDER BY run_timestamp DESC, id DESC LIMIT 1
        """)
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise RuntimeError("no canonical Daily run")
    run_id, expected_count = str(row[0]), int(row[1])
    if snapshot.get("run_id") != run_id:
        raise RuntimeError(f"MVP run_id mismatch: artifact={snapshot.get('run_id')} DB={run_id}")
    if len(items) != expected_count:
        raise RuntimeError(f"MVP item count mismatch: artifact={len(items)} DB={expected_count}")
    if manifest.get("run_id") != run_id:
        raise RuntimeError("manifest run_id mismatch")
    entry = manifest.get("files", {}).get("mvp_snapshot.json", {})
    if entry.get("sha256") != _sha256(SNAPSHOT):
        raise RuntimeError("MVP snapshot hash mismatch")
    print(json.dumps({"status": "PASS", "run_id": run_id, "items": len(items)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
