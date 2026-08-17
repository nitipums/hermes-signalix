# Browser and Freshness Verification

## Durable operating contract

- Level 3 durable facts are stored in Hermes `fact_store`.
- This note is the Level 4 Signalix project handoff for the same knowledge.
- Browser readiness is three separate layers:
  1. Chrome executable
  2. agent-browser daemon
  3. Hermes browser tool
- `/usr/bin/google-chrome` 151.x with `AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/google-chrome` is known-good for standalone Chrome/CDP rendering.
- Standalone Chrome success does **not** prove agent-browser or Hermes browser-tool readiness. UI readiness requires a real `open`/navigation, `snapshot`, and at least one interaction.
- If the browser daemon is stale, restart its owning gateway from an external shell; do not restart the active gateway from inside its own chat session.

## Current evidence boundary

- Standalone Chrome rendered the Signalix dashboard DOM successfully and exposed lifecycle/quality markers.
- The browser-use/Hermes harness previously failed with `chrome-not-running`; this is a tooling/daemon-layer blocker, not evidence that Signalix itself cannot render.
- Until the real browser interaction path passes, do not claim rendered desktop/mobile verification. API, served HTML, and standalone DOM evidence must be reported separately.

## Browser infrastructure fix — verified 2026-08-15 UTC

### Installed/runtime contract

- Node: `v22.23.2` at `/usr/bin/node`
- npm: `10.9.8` at `/usr/bin/npm`
- npm global prefix: `/usr`
- npm global root: `/usr/lib/node_modules`
- Package: `agent-browser@0.34.0`
- npm emitted an `EBADENGINE` warning because this release declares Node `>=24.0.0`; the installed Linux binary and all required local/Hermes verification passed on the current Node `v22.23.2`. Treat this as an upgrade watch item, not a failed browser fix.
- Binary: `/usr/bin/agent-browser` → `/usr/lib/node_modules/agent-browser/bin/agent-browser-linux-x64`
- Binary is executable (`0755`) and visible through the lite service PATH.
- Chrome: `Google Chrome 151.0.7922.137` at `/usr/bin/google-chrome`
- Hermes browser backend: `browser.cloud_provider: local` in `/root/.hermes/profiles/lite/config.yaml`

### Durable lite gateway environment

`hermes-gateway-lite.service` is active and its unit contains:

```ini
Environment="PATH=/usr/bin:/root/hermes-agent/venv/bin:/root/hermes-agent/node_modules/.bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/google-chrome"
Environment="AGENT_BROWSER_ARGS=--no-sandbox,--disable-dev-shm-usage,--disable-gpu"
Environment="HERMES_HOME=/root/.hermes/profiles/lite"
```

This is the correct lite service scope. Do not put these behavioral settings in `.env`. If the unit is ever changed, run `systemctl daemon-reload` and restart it from an external admin shell only.

### Verification transcript/results

Passed in required order:

1. `agent-browser --version` → `agent-browser 0.34.0`
2. `agent-browser doctor --offline --quick --json` → `success: true`, 6 pass, 0 fail; Chrome detected at `/usr/bin/google-chrome`; no active daemons
3. `agent-browser open about:blank` → `about:blank` (empty page)
4. `agent-browser snapshot` → empty-page snapshot
5. `agent-browser --session khim-infra open http://127.0.0.1:3001/dashboard.html` → title `Signalix — Market Intelligence`
6. `agent-browser --session khim-infra snapshot` → Signalix accessibility tree, 85 elements
7. Screenshot saved: `/root/signalix-dashboard.png`
8. Real interaction: clicked `@e57` (`Toggle KCE watchlist`); verified header changed from `หุ้นที่ติดตาม 0` to `หุ้นที่ติดตาม 1` and star changed `☆` → `★`
9. Post-interaction screenshot saved: `/root/signalix-dashboard-interaction.png`
10. Sessions were closed cleanly; `hermes-gateway-lite.service` remained active.

### Hermes browser tool path

Direct real-path test via `/root/hermes-agent/venv/bin/python` importing `tools.browser_tool` passed independently:

- `browser_navigate("http://127.0.0.1:3001/dashboard.html", task_id="hermes-infra")` → success, Signalix title, local feature
- `browser_snapshot(task_id="hermes-infra")` → success, Signalix tree, 85 elements
- `browser_click("@e57", task_id="hermes-infra")` → success
- Follow-up snapshot → `หุ้นที่ติดตาม 1` and `★`
- Session close returned `success: true`.

### Separate browser-use path

- `browser-use --version` → `0.8.0`
- `browser-use doctor --json` → package/Chrome/network passed; expected missing optional `BROWSER_USE_API_KEY` and `cloudflared`
- `browser-use setup --mode local --json` → `status: success`; package import and local Chrome availability passed
- This validates the separate browser-use installation/local setup, not cloud execution (no API key was present).

### Recovery

If the path regresses, run from an external shell (not inside the active gateway):

```bash
export HERMES_HOME=/root/.hermes/profiles/lite
export AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/google-chrome
export AGENT_BROWSER_ARGS=--no-sandbox,--disable-dev-shm-usage,--disable-gpu
agent-browser doctor --offline --quick --json
agent-browser open about:blank
agent-browser snapshot
systemctl is-active hermes-gateway-lite.service
systemctl restart hermes-gateway-lite.service
```

Only use the restart after inspecting stale daemon/Chrome ownership. The exact required external command is `systemctl restart hermes-gateway-lite.service`; it was intentionally **not** run from this chat because the current chat is served by that gateway.

## Freshness contract

- Freshness is market-session-aware.
- On SET market-closed days, data must not be marked globally stale solely because wall-clock age exceeds one hour.
- Separate these concepts:
  - intraday candle age/staleness;
  - global market/session status;
  - Daily EOD freshness;
  - decision source and decision-source timestamp.
- When intraday is stale or unavailable, the product may use Daily EOD as the decision source only if it labels the provenance explicitly; it must not silently present Daily EOD as fresh intraday confirmation.

## Signalix review ownership

- Khim owns implementation, fixes, tests, deployment, and verification.
- Mali and Nida are read-only reviewers: they inspect evidence and return acceptance feedback; they do not modify the product.
- Bee synthesizes feedback, routes the loop, and remains the final quality gate.
- Standard staged loop: Mali review → Bee brief → Khim fix → Nida review/loop → Mali re-review → Bee final verification.

## Related

- [[Product-Feedback]]
- [[Execution-Pipeline]]
- [[Deployment]]
- [[Bee-Handoff-Browser-Infrastructure-2026-08-15]]
