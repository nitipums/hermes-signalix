# Khim End-to-End Fix Handoff — last_valid_session + browser path

Date: 2026-08-15 UTC
Owner: Khim
Evidence level: live contract, served asset, rendered real-browser interaction

## A. Signalix defect

The working tree already contains the intended minimal fix (no unrelated scan/state changes):

- `backend/build_dashboard.py`
  - `market_session_status(now, last_valid_session)` returns `status`, `is_open`, `last_valid_session`, `timezone`, and `source`.
  - `dashboard_freshness(pg, now, last_valid_session)` passes the session evidence through under `market_session`.
- `backend/app.py` `/dashboard/snapshot`
  - derives the latest persisted Daily `last_date` without mutating scan state;
  - passes it to `dashboard_freshness`;
  - exposes both nested `market_session` and top-level `last_valid_session`.
- Deterministic tests: `backend/test_dashboard_freshness.py` (10 tests) cover open/closed/weekend/holiday, freshness boundaries, missing timestamps, timezone/source, and the last-valid-session contract.
- Live contract assertions: `backend/test_signalix_contracts.py` checks all required nested fields and top-level parity.

Required live snapshot (2026-08-15 closed weekend):

```json
{
  "market_session": {
    "status": "market_closed",
    "is_open": false,
    "last_valid_session": "2026-08-14",
    "timezone": "Asia/Bangkok",
    "source": "set_market_day_guard"
  },
  "last_valid_session": "2026-08-14",
  "data_freshness_status": "market_closed",
  "data_intraday_status": "stale"
}
```

Deployment and results:

```bash
cd /root/signalix
python -m py_compile backend/build_dashboard.py backend/app.py
docker compose up -d --force-recreate backend
docker exec signalix_backend python -m unittest -v test_dashboard_freshness.py test_signalix_contracts.py
cd backend && python test_signalix_contracts.py
```

Results: 10 deterministic tests passed; live contract passed; `/health` 200 with DB/Redis up; `/dashboard/snapshot` 200 with 718 items; dashboard HTML 200, 2,285,050 bytes. Current persisted groups remain 18 + 33 + 420 + 191 + 56 = 718.

## B. Browser root cause and durable path

Initial root cause was two package/path layers being conflated:

1. `/root/hermes-agent/node_modules/.bin/agent-browser` was missing.
2. An npm package named `browser-use@0.8.0` was installed at `/usr/bin/browser-use`; it is not Hermes' expected Browser Use harness CLI and cannot execute Hermes' stdin Python helper protocol.
3. Hermes resolves its managed CLI first. The correct Python package was installed with uv into the lite profile and is now the managed binary:
   `/root/.hermes/profiles/lite/bin/browser-use` -> browser-harness 0.1.8 / browser-use 0.13.7.
4. The harness needs a dedicated CDP endpoint for local Chrome. A separate non-Snap Chrome is running at `/usr/bin/google-chrome`, port `127.0.0.1:9222`, with a dedicated profile `/tmp/signalix-browser-chrome`. The harness workspace `.env` contains `BU_CDP_URL=http://127.0.0.1:9222` so Hermes' scrubbed subprocess environment and daemon inherit it.
5. `_build_browser_env()` was checked directly and preserves `AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/google-chrome` and `AGENT_BROWSER_ARGS=--no-sandbox,--disable-dev-shm-usage,--disable-gpu`.

Exact Chrome recovery command (external shell; do not use broad process termination):

```bash
/usr/bin/google-chrome --headless=new --no-sandbox --disable-dev-shm-usage --disable-gpu \
  --no-first-run --no-default-browser-check --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 --user-data-dir=/tmp/signalix-browser-chrome about:blank
```

Exact harness environment:

```bash
export HERMES_HOME=/root/.hermes/profiles/lite
export AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/google-chrome
export AGENT_BROWSER_ARGS=--no-sandbox,--disable-dev-shm-usage,--disable-gpu
export BU_CDP_URL=http://127.0.0.1:9222
```

## Browser proof

`agent-browser`:

- `/usr/bin/agent-browser`, version 0.34.0.
- `agent-browser open about:blank` passed.
- `agent-browser snapshot` returned an empty-page accessibility snapshot.
- Opened `http://127.0.0.1:3001/dashboard.html`; snapshot exposed Signalix title, market-session line, 718 shares, and card AX tree.
- Real interaction passed: clicked KCE card (`@e20`) and snapshot exposed `dialog "Security research detail"`, KCE profile, and chart controls.

Hermes `browser_exec`:

- First failed with `chrome-not-running` because no `BU_CDP_URL` was available to the harness daemon.
- After the dedicated Chrome + workspace `.env` endpoint, it passed: `page_info()` returned Signalix dashboard, title `🐴 Signalix — Market Intelligence`, and DOM assertion for `718 Thai ordinary shares screened` was true.
- Real interaction passed through Hermes: clicked `[data-symbol=KCE]`; the returned DOM had a real `[role=dialog]` containing `KCE Company profile pending`, breakout status, and chart controls.

This is a rendered AX/DOM interaction proof, not a visual screenshot claim. No mobile visual pass is claimed.

## Remaining blockers / recovery

- `agent-browser@0.34.0` declares Node >=24; current Node is v22.23.2. It worked end-to-end, but upgrade Node or pin a Node-compatible agent-browser release during maintenance.
- The npm `browser-use@0.8.0` shadow remains on PATH at `/usr/bin/browser-use`; Hermes is safe because managed-first resolution selects `/root/.hermes/profiles/lite/bin/browser-use`. Do not rely on bare PATH resolution outside Hermes; use the managed absolute path or remove the unrelated npm package during a planned maintenance window.
- `browser-use --doctor` reports cloud API key/cloudflared missing; cloud browser features are not required for this local proof.
- No Hermes gateway restart was performed from this chat. If the live service must reload changed service environment, an administrator must run from an independent shell: `systemctl daemon-reload` then `systemctl restart hermes-gateway-lite.service`, followed by `systemctl is-active hermes-gateway-lite.service`. This was not needed for the verified workspace endpoint path.
