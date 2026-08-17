# Bee Handoff — Browser Infrastructure Fix (Level 4 → Level 3)

**Date:** 2026-08-15 UTC  
**Owner:** Khim  
**Promote to:** Bee → Level-3 `fact_store` after review

## Canonical facts to promote

1. Lite browser backend is local: `/root/.hermes/profiles/lite/config.yaml` has `browser.cloud_provider: local`.
2. Node/npm: Node `v22.23.2` at `/usr/bin/node`; npm `10.9.8` at `/usr/bin/npm`; global prefix `/usr`; global modules `/usr/lib/node_modules`.
3. Installed package is `agent-browser@0.34.0`; npm emits an `EBADENGINE` warning because it declares Node `>=24.0.0`, but its Linux binary is empirically runnable on the current Node `v22.23.2` and all required checks passed. Upgrade Node to 24 before treating this as a future-proof semver-clean install.
4. Executable `/usr/bin/agent-browser` resolves to `/usr/lib/node_modules/agent-browser/bin/agent-browser-linux-x64` and is executable.
5. Chrome is `/usr/bin/google-chrome`, version `151.0.7922.137`.
6. Active lite service is `hermes-gateway-lite.service`; its durable environment contains:
   - `HERMES_HOME=/root/.hermes/profiles/lite`
   - `AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/google-chrome`
   - `AGENT_BROWSER_ARGS=--no-sandbox,--disable-dev-shm-usage,--disable-gpu`
   - PATH includes `/usr/bin`, `/root/hermes-agent/venv/bin`, and `/root/hermes-agent/node_modules/.bin`.
6. Verified sequence passed: `agent-browser --version`; `agent-browser doctor --offline --quick --json` (`success: true`, 0 failures); `agent-browser open about:blank`; `agent-browser snapshot`.
7. Signalix dashboard URL is `http://127.0.0.1:3001/dashboard.html`. Agent-browser opened it, snapshotted it, saved screenshots, and clicked KCE watchlist `@e57`; header changed `หุ้นที่ติดตาม 0` → `หุ้นที่ติดตาม 1`, proving a real interaction.
8. Hermes `tools.browser_tool` local path independently passed navigate, snapshot, click, and follow-up snapshot using task `hermes-infra`.
9. Separate `browser-use` CLI is installed at version `0.8.0`; `browser-use setup --mode local --json` passed. `browser-use doctor` reports only expected optional cloud API key and cloudflared missing; cloud path was not claimed.
10. Screenshots: `/root/signalix-dashboard.png` and `/root/signalix-dashboard-interaction.png`.

## Exact verification/recovery commands

```bash
npm prefix -g                         # /usr
npm root -g                           # /usr/lib/node_modules
agent-browser --version               # 0.34.0
agent-browser doctor --offline --quick --json
agent-browser open about:blank
agent-browser snapshot
export AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/google-chrome
export AGENT_BROWSER_ARGS=--no-sandbox,--disable-dev-shm-usage,--disable-gpu
agent-browser open http://127.0.0.1:3001/dashboard.html
agent-browser snapshot
agent-browser screenshot /root/signalix-dashboard.png
agent-browser click @e57
agent-browser snapshot
```

If a gateway restart is required, execute only from an external SSH/admin shell:

```bash
systemctl daemon-reload
systemctl restart hermes-gateway-lite.service
systemctl is-active hermes-gateway-lite.service
```

Do **not** run that restart from the current gateway chat. Before restarting, inspect exact stale browser/daemon PIDs and avoid broad `pkill -f` patterns.

## Evidence files

- Level-4 note: `/root/signalix/vault/Browser-and-Freshness-Verification.md`
- Screenshots: `/root/signalix-dashboard.png`, `/root/signalix-dashboard-interaction.png`
- Hermes browser source path: `/root/hermes-agent/tools/browser_tool.py`
- Lite unit: `/etc/systemd/system/hermes-gateway-lite.service`

## Status / limitations

- Fix is complete and verified for local Chrome + agent-browser + Hermes browser tool.
- No Signalix application code was modified.
- No gateway restart was performed because the active chat runs through `hermes-gateway-lite.service`; it was already active and inherited the correct environment.
- Browser-use cloud execution remains untested because `BROWSER_USE_API_KEY` is not configured; local setup is verified.
