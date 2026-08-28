#!/usr/bin/env bash
# scripts/probe_shortlist.sh — standard probe for Signalix live projection
# Usage: ./scripts/probe_shortlist.sh [output_dir]
# Output: sl8000.json, slcompact.json, dashboard.html + grep report
# Exit 0 = probe ok, 1 = stale wording found, 2 = endpoint unreachable
set -euo pipefail
OUTDIR="${1:-.}"
mkdir -p "$OUTDIR"
echo "== probe :8000/dashboard/shortlist =="
if ! curl -sf http://127.0.0.1:8000/dashboard/shortlist -o "$OUTDIR/sl8000.json" --max-time 10; then
  echo "FAIL: :8000/dashboard/shortlist unreachable" >&2
  exit 2
fi
echo "== probe :8000/dashboard/shortlist/compact =="
curl -sf http://127.0.0.1:8000/dashboard/shortlist/compact -o "$OUTDIR/slcompact.json" --max-time 10 || echo "WARN: compact unreachable"
echo "== probe :3001/dashboard.html =="
curl -sf http://127.0.0.1:3001/dashboard.html -o "$OUTDIR/dashboard.html" --max-time 10 || echo "WARN: :3001 unreachable"
echo "== check stale wording =="
if grep -q "Trigger confirmed" "$OUTDIR/sl8000.json" 2>/dev/null; then
  echo "STALE: 'Trigger confirmed' found in sl8000.json — REVISE stale_runtime"
  grep -o '"why_now":"[^"]*Trigger confirmed[^"]*"' "$OUTDIR/sl8000.json" | head -5 || true
  STALE=1
else
  echo "OK: no 'Trigger confirmed' in sl8000.json"
  STALE=0
fi
if grep -q "quality pass" "$OUTDIR/sl8000.json" 2>/dev/null; then
  echo "STALE: 'quality pass' found — REVISE"
  STALE=1
else
  echo "OK: no 'quality pass'"
fi
echo "== summary =="
READY=$(python3 -c "import json; d=json.load(open('$OUTDIR/sl8000.json')); print(sum(1 for x in d.get('items',[]) if x.get('state')=='READY'))" 2>/dev/null || echo "?")
echo "READY count: $READY"
echo "Artifacts: $OUTDIR/sl8000.json $OUTDIR/slcompact.json $OUTDIR/dashboard.html"
if [ "$STALE" = "1" ]; then exit 1; fi
exit 0
