# Deployment

> **STATUS: CURRENT** · `CANONICAL_FOR: deployment/runbook/timer ownership`. Runtime state must be verified from the host/container, not assumed from this note.

## Stack
Docker Compose, 4 services (see [[Architecture]]). All on the VPS host.

## Reload after edits (CRITICAL)
`docker compose restart` does **NOT** re-read `/root/signalix/.env` and does
**NOT** pick up `backend/*.py` changes. After any edit to `.env` or backend code:
```bash
cd /root/signalix && docker compose up -d --force-recreate delivery backend
```
(Build first with `docker compose build backend` only if `requirements.txt`
changed — never needed for pure `.py`/`.env` edits since the image copies `./backend`.)

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
- `signalix-update.timer` — weekday EOD ingestion + Daily scan at 18:30 Bangkok. Its canonical source is `backend/update_data.service`; the deployed unit must be byte-identical. Daily path does **not** run full intraday; `signalix-intraday.service` owns 60m fetching. `ExecStartPost` runs `verify_scan_dashboard.py` against the snapshot contract.
- `signalix-eod-healthcheck.timer` — weekday EOD freshness watchdog at 20:00 Bangkok. It checks the latest `price_data` date, latest Daily scan date, service result, and writes durable JSONL/state evidence to `/root/signalix/eod_healthcheck_log.jsonl` and `/root/signalix/eod_healthcheck_observations.json`.
- `signalix-intraday.timer` — every 15 minutes in Bangkok weekday time blocks; exact continuous-session guard (10:15–12:30 and 14:45–16:30) is in `signalix-intraday.service`, which fetches/evaluates **active 60m only**. The fetch is active ORD after `intraday_feed_status` cooldown filtering; `--intraday-limit` means bars per symbol, not symbol count. Three consecutive empty/fail responses mark only the 60m feed unavailable for 24 hours; Daily/EOD remains available. After upsert/evaluation, intraday rebuilds the dashboard from the existing Daily scan; it does not run a Daily scan. `ExecStopPost` must run `cd /root/signalix && python -m backend.run_intraday_evaluation` so package-relative imports work after both success and fetch failure. Validate `OnCalendar` with `systemd-analyze calendar` after any syntax edit; prior syntax accidentally scheduled every minute.
- `signalix-intraday-watchdog.timer` — independent freshness monitor. It tolerates expected `partial_success`, checks `intraday_price_data` at a cadence-aware 90-minute threshold, checks evaluator state at 30 minutes, and writes structured JSONL evidence.
- `signalix-profile-refresh.timer` — low-frequency weekday Yahoo fallback metadata cache refresh; `refresh_company_profiles.py` is constrained to active `ORD` rows and records failures/backoff in PostgreSQL. It is context-only and must not feed signal calculations.
- `signalix-factsheet-refresh.timer` — bounded weekday SET factsheet refresh, active ORD only, 20 symbols per run, persisted JSONL progress, upserts `set_factsheet` fields without overwriting stronger existing evidence. It is the authoritative profile-source refresh; Yahoo remains fallback.
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
