#!/usr/bin/env bash
# Isolated rendered journey for the canonical setup-candidates error/retry contract.
# This harness affects only one agent-browser session and intercepts only the
# setup-candidates fetch. It never changes backend/container state.
#
# Usage:
#   ./scripts/browser_failure_retry_harness.sh [evidence_dir]
#
# Exit 0 = failure + visible Retry + recovery + rows PASS
# Exit 1 = browser journey assertion failed
# Exit 2 = browser/tool/runtime unavailable
set -euo pipefail

EVIDENCE_DIR="${1:-.scratch/browser-failure-retry-$(date +%Y%m%d-%H%M%S)}"
EVIDENCE_DIR="$(realpath -m "$EVIDENCE_DIR")"
PUBLIC_URL="${SIGNALIX_PUBLIC_URL:-http://91.98.72.120:3001/mvp}"
VIEWPORT_W="${SIGNALIX_VIEWPORT_WIDTH:-390}"
VIEWPORT_H="${SIGNALIX_VIEWPORT_HEIGHT:-844}"
SESSION="signalix-failure-retry-$$"
ROUTE='**/api/setup-candidates*'
mkdir -p "$EVIDENCE_DIR"

export AGENT_BROWSER_EXECUTABLE_PATH="${AGENT_BROWSER_EXECUTABLE_PATH:-/usr/bin/google-chrome}"
export AGENT_BROWSER_ARGS="${AGENT_BROWSER_ARGS:---no-sandbox,--disable-dev-shm-usage,--disable-gpu}"

browser() {
  agent-browser --session "$SESSION" "$@"
}

# agent-browser eval prints a JSON string by default. Decode both the wrapper
# and the page JSON so assertions operate on structured values.
eval_json() {
  local expression="$1"
  browser eval "$expression" | python3 -c '
import json, sys
raw = sys.stdin.read().strip()
value = json.loads(raw)
if isinstance(value, str):
    value = json.loads(value)
print(json.dumps(value, ensure_ascii=False))
'
}

cleanup() {
  browser network unroute "$ROUTE" >/dev/null 2>&1 || true
  browser close >/dev/null 2>&1 || true
}
trap cleanup EXIT

browser close >/dev/null 2>&1 || true
browser open about:blank >"$EVIDENCE_DIR/open.txt"
browser network route "$ROUTE" --abort >"$EVIDENCE_DIR/route.txt"
browser set viewport "$VIEWPORT_W" "$VIEWPORT_H" >"$EVIDENCE_DIR/viewport.txt"
browser open "${PUBLIC_URL}?browser-harness=failure-retry" >>"$EVIDENCE_DIR/open.txt"
browser wait 1200 >/dev/null

failure_json=$(eval_json 'JSON.stringify({errorVisible:!document.querySelector("#daily-vcp-error").classList.contains("state--hidden"),errorText:document.querySelector("#daily-vcp-error-msg").textContent,retryVisible:!document.querySelector("#daily-vcp-retry").classList.contains("state--hidden"),contentVisible:!document.querySelector("#daily-vcp-content").classList.contains("state--hidden"),cards:document.querySelectorAll("#daily-vcp-cards [data-symbol]").length})')
printf '%s\n' "$failure_json" >"$EVIDENCE_DIR/failure-state.json"
browser snapshot >"$EVIDENCE_DIR/failure-snapshot.txt"
browser screenshot "$EVIDENCE_DIR/failure.png" >/dev/null
 test -s "$EVIDENCE_DIR/failure.png" || { echo "FAIL: failure screenshot was not created" >&2; exit 1; }
browser network requests --filter 'setup-candidates' >"$EVIDENCE_DIR/failure-requests.txt"

python3 - "$EVIDENCE_DIR/failure-state.json" <<'PY'
import json, sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
checks = {
    "visible error": state["errorVisible"],
    "actionable Retry": state["retryVisible"],
    "content hidden": not state["contentVisible"],
    "no stale cards": state["cards"] == 0,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("FAIL failure state: " + ", ".join(failed))
PY

# Restore only this route, then exercise the real Retry button.
browser network unroute >"$EVIDENCE_DIR/unroute.txt"
browser wait 250 >/dev/null
browser click '#daily-vcp-retry' >"$EVIDENCE_DIR/retry-click.txt"
browser wait 2500 >/dev/null

recovery_json=$(eval_json 'JSON.stringify({errorVisible:!document.querySelector("#daily-vcp-error").classList.contains("state--hidden"),contentVisible:!document.querySelector("#daily-vcp-content").classList.contains("state--hidden"),cards:document.querySelectorAll("#daily-vcp-cards [data-symbol]").length,meta:document.querySelector("#daily-vcp-meta").textContent,scroll:{innerWidth,clientWidth:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,bodyScrollWidth:document.body.scrollWidth}})')
printf '%s\n' "$recovery_json" >"$EVIDENCE_DIR/recovery-state.json"
browser snapshot >"$EVIDENCE_DIR/recovery-snapshot.txt"
browser screenshot "$EVIDENCE_DIR/recovery.png" >/dev/null
 test -s "$EVIDENCE_DIR/recovery.png" || { echo "FAIL: recovery screenshot was not created" >&2; exit 1; }
browser network requests --filter 'setup-candidates' >"$EVIDENCE_DIR/recovery-requests.txt"
browser console >"$EVIDENCE_DIR/console.txt" || true
browser errors >"$EVIDENCE_DIR/errors.txt" || true

python3 - "$EVIDENCE_DIR/recovery-state.json" <<'PY'
import json, sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
checks = {
    "error cleared": not state["errorVisible"],
    "content visible": state["contentVisible"],
    "rows returned": state["cards"] > 0,
    "no horizontal overflow": state["scroll"]["scrollWidth"] <= state["scroll"]["innerWidth"],
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("FAIL recovery: " + ", ".join(failed))
print(json.dumps({"status": "PASS", "failure": json.load(open(sys.argv[1].replace("recovery-state.json", "failure-state.json"), encoding="utf-8")), "recovery": state}, ensure_ascii=False, indent=2))
PY
