# Deployment

> **STATUS: CURRENT** · `CANONICAL_FOR: deployment/runbook/timer ownership`. Runtime state must be verified from the host/container, not assumed from this note.

## Stable release

```text
branch: release/signalix-mvp-stable
release: 3ec48f7 (`fix: preserve Daily run lineage in EOD dashboard build`)
source: /root/signalix
MVP server: mvp_server.py
legacy routes: quarantined/404
```

`/root/signalix` is the only registered Signalix worktree and the canonical production bind mount. `signalix_backend` and `signalix_dashboard` mount `/root/signalix/backend`. Former release-candidate/feature worktrees and temporary cleanup copies were retired after stable push; no retired path is treated as current source.


## Reload after edits (CRITICAL)
For this bind-mounted stable worktree, a dashboard-only Python/UI change is
reloaded with:
```bash
docker restart signalix_dashboard
```
Use `docker compose up -d --force-recreate` only when compose configuration,
image dependencies, or environment wiring changes. Verify the served endpoint
after the restart; a successful restart alone is not acceptance evidence.

## Environment (`/root/signalix/.env`)
| Var | Purpose |
|-----|---------|
| `POSTGRES_*` | DB credentials (values kept in host/service environment; never store here) |
| `REDIS_URL` | `redis://redis:6379/0` (docker net name) |
| `REDIS_CHANNEL` | `signals` |
| `TELEGRAM_BOT_TOKEN` | from `/root/.hermes/.env` (reuse, don't regenerate) |
| `TELEGRAM_CHAT_ID` | `7295704669` |
| `DASHBOARD_PUBLIC_URL` | public base for alert links |
| `WEBHOOK_SECRET` | shared secret for `/webhook` (agent-generated) |
| `LLM_API_URL` / `LLM_API_KEY` | Phase 3 (currently empty) |
| `SETTRADE_*` | Settrade Open API creds (in `settradeupdated.env`) |

## systemd timers (host, not docker)
- `signalix-update.timer` — weekday EOD ingestion + Daily scan at 18:30 Bangkok. Its canonical source is `/root/signalix/backend/update_data.service`; the deployed unit must be byte-identical. Daily path does **not** run full intraday; `signalix-intraday.service` owns 60m fetching. `ExecStartPost` runs `verify_mvp_only.py` against the canonical MVP artifact and latest Daily run.
- `signalix-eod-healthcheck.timer` — weekday EOD freshness watchdog at 20:00 Bangkok. It checks the latest `price_data` date, latest Daily scan date, service result, and writes durable JSONL/state evidence to `/root/signalix/eod_healthcheck_log.jsonl` and `/root/signalix/eod_healthcheck_observations.json`.
- `signalix-intraday.timer` — every 30 minutes in guarded Bangkok weekday time blocks; `signalix-intraday.service` fetches/evaluates **active 60m only**. The fetch is active ORD after `intraday_feed_status` cooldown filtering; `--intraday-limit` means bars per symbol, not symbol count. Settrade empty responses are marked feed-unavailable for 24 hours immediately; Daily/EOD remains available. After upsert/evaluation, intraday rebuilds from the latest canonical Daily DB observations and does not run a Daily scan. `ExecStopPost` runs from `/root/signalix` using the package module path. Validate `OnCalendar` with `systemd-analyze calendar` after edits.
- `signalix-intraday-watchdog.timer` — independent freshness monitor. It tolerates expected `partial_success`, checks `intraday_price_data` at a cadence-aware 90-minute threshold, checks evaluator state at 30 minutes, and writes structured JSONL evidence.
- `signalix-profile-refresh.timer` — low-frequency weekday Yahoo fallback metadata cache refresh; `refresh_company_profiles.py` is constrained to active `ORD` rows and records failures/backoff in PostgreSQL. It is context-only and must not feed signal calculations.
- `signalix-factsheet-refresh.timer` — bounded weekday SET factsheet refresh, active ORD only, 20 symbols per run, persisted JSONL progress, upserts `set_factsheet` fields without overwriting stronger existing evidence. It is the authoritative profile-source refresh; Yahoo remains fallback.
- MVP chart contract — `GET /api/chart-db/{symbol}?timeframe=1D|1W|60M|1M`; `1D` reads Daily OHLCV, `1W`/`1M` aggregate Daily bars, and `60M` reads stored intraday 60m bars. Unsupported `15M` returns HTTP 400.
- MVP freshness contract — the header reports `Daily EOD` from the canonical Daily run and `60m updated` from the latest completed `intraday_ingestion_runs` row. A successful intraday fetch/evaluator must advance the latter without changing Daily decision provenance.
- MVP chart safety — timeframe requests are abortable/generation-guarded; unavailable 60m feeds show an explicit `60m unavailable · Daily EOD remains the decision source` state. Mobile chart/filter controls are at least 44px.
- `signalix_delivery` was briefly a host unit; **superseded** by the docker `delivery` service.

## Verify realtime push
```bash
docker exec -t signalix_redis redis-cli pubsub numsub signals   # >=1
docker exec -t signalix_delivery python -c "import os;print(bool(os.getenv('TELEGRAM_BOT_TOKEN')))"
# live send test:
docker exec -t signalix_delivery python -c "import os,requests;r=requests.post(f'https://api.telegram.org/bot{os.getenv(\"TELEGRAM_BOT_TOKEN\")}/sendMessage',json={'chat_id':os.getenv('TELEGRAM_CHAT_ID'),'text':'test'},timeout=10);print(r.status_code,r.json().get('ok'))"
```

## Pitfalls
- **Host consumer fails** (no `redis` in host venv; `redis://redis` unresolvable off docker net).
- **Block-buffered logs** — use `python -u` in the delivery command.
- **Intraday evaluator import** — do not execute `backend/run_intraday_evaluation.py` as a standalone script; `intraday_evaluator.py` uses package-relative imports. Use the module form from `/root/signalix`.
- **LINE** — `notify-api.line.me` is DNS-blocked on this VPS; dropped per user.
- Plain `restart` leaves stale env/code running — always `force-recreate`.

See skill `signalix-delivery-ops` for the ops playbook.
