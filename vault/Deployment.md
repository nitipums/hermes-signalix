# Deployment

> **STATUS: CURRENT** · `CANONICAL_FOR: deployment/runbook/timer ownership`.
> **Reconciled:** 2026-09-02 13:08 ICT · release `1573d5c` promoted; intraday metadata sidecar/schema follow-ups verified; evaluator auto-caller separate.

## Stable release

```text
branch: release/signalix-mvp-stable
source: /root/signalix
MVP server: mvp_server.py
legacy routes: quarantined/404
```

## Current runtime scope — 2026-09-02

The promoted Elliott/Trend/Trade-Setup spine is the current product surface. `signalix_backend`, `signalix_dashboard`, PostgreSQL, and Redis are healthy at rebaseline; `/mvp` returns 200, `/api/setup-candidates` returns the live DB-built contract, `/health/readiness` is on backend `:8000`, and retired `/dashboard.html` returns 404. The public 390px failure→Retry→recovery journey is verified. The UI now shows `60m fetched` separately from `latest completed 60m candle`; session evidence was verified after runtime reload. Alerts, auto-trading, and broker execution remain off.

`marginable_long` is 237 eligible symbols; 931 active ORD is explicit audit/rollback coverage. VCP routes/artifacts remain compatibility/audit only.

### 2026-09-02 promotion evidence

- Source/release: `/root/signalix`, branch `release/signalix-mvp-stable`, local and remote SHA `5bf3d9ac3e77b9f139ce2f84e0d6e27546a95fa4`.
- Promotion: installed `backend/signalix-intraday.service` and `.timer` into `/etc/systemd/system/`, ran `systemctl daemon-reload`, restarted the timer, and verified byte parity plus `systemd-analyze verify`.
- Runtime reload: `docker compose up -d --force-recreate backend dashboard`; `signalix_backend` and `signalix_dashboard` healthy; `/health/readiness` returned DB/Redis `ok`.
- Public read-back: `/mvp`, `/api/setup-candidates`, and `/api/chart-db/BBL?timeframe=1D|1W` returned HTTP 200. Day last candle was provisional `2026-09-02`; Week candles were ascending with `latest_time=2026-09-02T05:00:00+00:00`.
- Review boundary: code/tests/runtime/browser are PASS for this slice. Remaining `REVISE` follow-up: bound request-time intraday metadata overlay and persist explicit fetch-universe identity for audit runs.

### Deferred features — 2026-09-01

- Alerts/delivery: `PENDING / FUTURE FEATURE`, OFF.
- Automatic trading/broker execution: `PENDING / FUTURE FEATURE`, OFF and not authorized.
- Evaluator auto-caller: `PENDING / OWNER DECISION`; if approved later, it will append lifecycle evaluation evidence only, not submit orders.

The paused delivery container, Telegram credentials, and alert source are retained for reversible rollback. No secrets are stored in this note.

`/root/signalix` is the canonical production bind mount. Session closeout 2026-09-02 archived the stale R4/R5 Kanban graph; many historical/feature worktrees remain on disk and must be inspected before removal. `signalix_backend` and `signalix_dashboard` mount `/root/signalix/backend`; no retired path is treated as current source.


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
- `signalix-intraday.timer` — 13 weekday rounds in Bangkok: `10:00, 10:30, 11:00, 11:30, 12:00, 12:30, 14:00, 14:30, 15:00, 15:30, 16:00, 16:30, 16:45`. The service guard is `10:00–16:45`; the default fetch scope is canonical `marginable_long`, with explicit `active_ord` retained for audit/rollback runs. It runs with `--no-scan`: each round fetches/evaluates stored 60m data and does not invoke the expensive Daily scan, avoiding overlap. Failed/skipped fetches do not advance VCP.
- `signalix-intraday-watchdog.timer` — independent freshness monitor. It tolerates expected `partial_success`, checks `intraday_price_data` at a cadence-aware 90-minute threshold, checks evaluator state at 30 minutes, and writes structured JSONL evidence.
- `signalix-profile-refresh.timer` — low-frequency weekday Yahoo fallback metadata cache refresh; `refresh_company_profiles.py` is constrained to active `ORD` rows and records failures/backoff in PostgreSQL. It is context-only and must not feed signal calculations.
- `signalix-factsheet-refresh.timer` — bounded weekday SET factsheet refresh, active ORD only, 20 symbols per run, persisted JSONL progress, upserts `set_factsheet` fields without overwriting stronger existing evidence. It is the authoritative profile-source refresh; Yahoo remains fallback.
- MVP chart contract — `GET /api/chart-db/{symbol}?timeframe=1D|1W|60M|1M`; `1D` reads Daily OHLCV with a same-day provisional 60m replacement when available, `1W`/`1M` aggregate those Day bars, and `60M` reads stored intraday 60m bars. Unsupported `15M` returns HTTP 400.
- MVP freshness contract — the header reports `Daily EOD` from the canonical Daily run and `60m updated` from the latest completed `intraday_ingestion_runs` row. A successful intraday fetch/evaluator must advance the latter without changing Daily decision provenance.
- Intraday metadata seam — after a committed successful `marginable_long` ingestion run, the updater atomically publishes `intraday-latest.json` beside the canonical read model. `/api/setup-candidates` and symbol detail read this bounded sidecar without request-time PostgreSQL acquisition; absent, malformed, stale, `active_ord`, or legacy/null identity falls back to embedded read-model metadata. `intraday_ingestion_runs.fetch_universe` is added idempotently by `ensure_intraday_table`; `active_ord` remains audit/rollback-only and is never canonical product metadata.
- MVP timestamp display — the setup-candidate metadata line reports both `60m fetched` from `intraday_ingestion_runs.fetch_completed_at` and `latest completed 60m candle` from the per-item stored candle timestamp; these must not be conflated.
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
