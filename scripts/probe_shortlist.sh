#!/usr/bin/env bash
# Canonical live probe for Signalix owner MVP.
# Usage: ./scripts/probe_shortlist.sh [output_dir]
# Exit 0 = all gates pass; 1 = contract/retirement/failure-state gate failed; 2 = endpoint unreachable.
set -euo pipefail

OUTDIR="${1:-.}"
BACKEND_URL="${SIGNALIX_BACKEND_URL:-http://127.0.0.1:8000}"
DASHBOARD_URL="${SIGNALIX_DASHBOARD_URL:-http://127.0.0.1:3001}"
mkdir -p "$OUTDIR"

fetch_code() {
  local url="$1"
  local output="$2"
  curl -sS --max-time 30 -o "$output" -w '%{http_code}' "$url"
}

require_code() {
  local label="$1"
  local expected="$2"
  local actual="$3"
  if [[ "$actual" != "$expected" ]]; then
    printf 'FAIL: %s expected HTTP %s, got %s\n' "$label" "$expected" "$actual" >&2
    exit 2
  fi
}

echo "== readiness =="
code=$(fetch_code "$BACKEND_URL/health/readiness" "$OUTDIR/readiness.json")
require_code "backend readiness" 200 "$code"

echo "== canonical Daily VCP Watchlist (compact) =="
code=$(fetch_code "$DASHBOARD_URL/api/vcp-finder?interval=60m&market=TH&daily_watchlist=true" "$OUTDIR/daily_vcp.json")
require_code "Daily VCP Watchlist" 200 "$code"

echo "== canonical VCP audit coverage =="
code=$(fetch_code "$DASHBOARD_URL/api/vcp-finder?interval=60m&market=TH" "$OUTDIR/vcp.json")
require_code "VCP audit" 200 "$code"

echo "== served MVP =="
code=$(fetch_code "$DASHBOARD_URL/mvp" "$OUTDIR/mvp.html")
require_code "MVP" 200 "$code"
if ! grep -qi "Signalix" "$OUTDIR/mvp.html"; then
  echo "FAIL: served MVP does not contain Signalix marker" >&2
  exit 1
fi

echo "== retired dashboard route =="
code=$(fetch_code "$DASHBOARD_URL/dashboard.html" "$OUTDIR/retired_dashboard_response.txt")
if [[ "$code" != "404" ]]; then
  echo "FAIL: dashboard.html must return 404, got $code" >&2
  exit 1
fi

echo "== explicit missing-symbol state =="
code=$(fetch_code "$DASHBOARD_URL/api/symbol/___SIGNALIX_PROBE_MISSING___" "$OUTDIR/missing_symbol.json")
if [[ "$code" != "404" ]]; then
  echo "FAIL: missing symbol must return 404, got $code" >&2
  exit 1
fi

python3 - "$OUTDIR" <<'PY'
import collections
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
readiness = json.loads((out / "readiness.json").read_text(encoding="utf-8"))
if readiness.get("status") != "ok":
    raise SystemExit(f"FAIL: readiness status is {readiness.get('status')!r}")

payload = json.loads((out / "vcp.json").read_text(encoding="utf-8"))
daily_payload = json.loads((out / "daily_vcp.json").read_text(encoding="utf-8"))
required = {"schema_version", "run_id", "as_of", "universe", "coverage", "results"}
missing = sorted(required - payload.keys())
if missing:
    raise SystemExit(f"FAIL: VCP audit payload missing keys: {missing}")
if payload.get("schema_version") != "signalix.vcp_finder_60m.v1":
    raise SystemExit(f"FAIL: unexpected schema_version {payload.get('schema_version')!r}")

universe = payload["universe"]
for key in ("eligible", "evaluated", "returned"):
    if not isinstance(universe.get(key), int) or universe[key] < 0:
        raise SystemExit(f"FAIL: invalid universe.{key}: {universe.get(key)!r}")
results = payload["results"]
if not isinstance(results, list):
    raise SystemExit("FAIL: audit results must be a list")
if len(results) != universe["returned"]:
    raise SystemExit(
        f"FAIL: audit coverage mismatch: results={len(results)} returned={universe['returned']}"
    )
if universe["evaluated"] != universe["returned"]:
    raise SystemExit(
        f"FAIL: audit coverage mismatch: evaluated={universe['evaluated']} returned={universe['returned']}"
    )
coverage = payload["coverage"]
for key in ("feed_unavailable", "no_data"):
    if key not in coverage:
        raise SystemExit(f"FAIL: coverage missing {key}")

if daily_payload.get("results") != []:
    raise SystemExit("FAIL: Daily VCP Watchlist must not serialize audit results")
watchlist = daily_payload.get("daily_watchlist")
if not isinstance(watchlist, dict) or not isinstance(watchlist.get("counts"), dict):
    raise SystemExit("FAIL: Daily VCP Watchlist contract missing counts")
if daily_payload.get("universe") != universe:
    raise SystemExit("FAIL: Daily VCP Watchlist metadata universe differs from audit")

states = collections.Counter(item.get("state") or "UNKNOWN" for item in results)
report = {
    "status": "PASS",
    "run_id": payload["run_id"],
    "as_of": payload["as_of"],
    "universe": universe,
    "coverage": coverage,
    "state_counts": dict(sorted(states.items())),
    "daily_watchlist_counts": watchlist["counts"],
    "daily_payload_bytes": (out / "daily_vcp.json").stat().st_size,
    "audit_payload_bytes": (out / "vcp.json").stat().st_size,
    "readiness": readiness,
    "retired_dashboard_status": 404,
    "missing_symbol_status": 404,
}
(out / "probe_report.json").write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(f"run_id: {payload['run_id']}")
print(f"as_of: {payload['as_of']}")
print(f"eligible: {universe['eligible']}")
print(f"evaluated: {universe['evaluated']}")
print(f"returned: {universe['returned']}")
print(f"READY count: {states.get('READY', 0)}")
print(f"feed unavailable: {coverage['feed_unavailable']}")
print(f"no data: {coverage['no_data']}")
print(f"Daily VCP Watchlist: {json.dumps(watchlist['counts'], sort_keys=True)}")
print(f"Payload bytes: daily={report['daily_payload_bytes']} audit={report['audit_payload_bytes']}")
print(f"Artifacts: {out / 'readiness.json'} {out / 'daily_vcp.json'} {out / 'vcp.json'} {out / 'mvp.html'} {out / 'missing_symbol.json'} {out / 'probe_report.json'}")
PY
