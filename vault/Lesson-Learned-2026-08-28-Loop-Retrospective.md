# Lesson Learned — Signalix Loop 2026-08-27 23:05 → 2026-08-28 08:11

> **Incident:** 13 runs across 8 cards produced 4 loop types and 45 min waste. See `hermes-kanban-ops/references/signalix-2026-08-28-loop-retrospective.md` for raw log evidence.
> **Authority:** This note + `vault/Execution-Pipeline.md` define future prevention. Kanban board is execution state only.

## 1. What happened

| Window | Card | Owner | Outcome | Root cause of loop |
|---|---|---|---|---|
| 23:05 | t_30629b77 | Khim | done 8m | initial fail-closed gate — clean |
| 23:13 | t_016ca0cd | Nida | done 6m | QA verified :3001 static only |
| 23:21 | t_8cad24a7 | Ploy | REVISE 13m | caught wording gap (qualified_pullback) |
| 23:34 | t_3ac1203a | Lite | FAIL 10m | stale runtime still live → block release |
| 05:16 | t_e8a856c5 | Khim | blocked 7m → done 0m | `kanban_complete` rejected `artifacts: []` |
| 05:26 | t_cbd7e900 | Nida | reclaimed 10m → reclaimed 1m → blocked → done 4m | `localhost` browser block + missing :8000 check |
| 05:37 | t_925028aa | Khim | 5 runs, 45m total, timed_out 23m | resource gate + instant reclaim without backoff, 262× terminal |
| 06:37 | t_a1a039fb | Ploy | REVISE | same near_trigger gap survived |
| 06:48 | t_c4ead07b | Lite | FAIL | PRM live JSON still false |
| 06:58 | t_4d1088f0 | Nida | done 9m | PASS on :3001, :8000 still stale |
| 07:15 | t_b8c9d6a4 | Ploy | REVISE | caught :8000 stale → proved stale-runtime |
| 07:30 | t_3755a74f | Khim | done 37m, 17 heartbeats | card scope 5 jobs in 1, artifact discovery late |
| 08:11 | t_a371e7dd | Nida | blocked 2m | owner takeover → stop downstream |

## 2. Loop taxonomy (detectable from logs)

1. **Stale runtime loop** — `signalix_backend` uvicorn `--workers 2` no `--reload`, bind-mount updated file not reloaded. Detected by `git show HEAD:daily_shortlist.py:247` vs `curl :8000/dashboard/shortlist | grep 'Trigger confirmed'` mismatch. Hit 3 times (t_3ac1203a, t_a1a039fb, t_cbd7e900).
2. **Resource reclaim loop** — `t_925028aa`: reclaimed → blocked (load>1.8/swap) → timed_out 23m → crashed → completed. Signature: 262× `preparing terminal`, 0 heartbeat for 23m.
3. **Browser locality loop** — Nida `t_cbd7e900` 119× `preparing` for `browser_open localhost` blocked by Hermes; must use `curl + read_file`.
4. **Schema loop** — `t_e8a856c5` 2× `kanban_complete` error `missing list fields artifacts`.
5. **Heartbeat-only loop** — `t_3755a74f` 17 heartbeats with no artifact until orchestrator checkpoint 08:00.
6. **Content REVISE loop** — Ploy REVISE 3 times on same `qualified_pullback / near_trigger / cross-lane dedup` because Khim fixed only `fresh_breakout` first.

## 3. Prevention — enforced going forward

### A. Card design
- One card = one authority: (a) code + focused tests, (b) restart/rebuild, (c) live probe + browser. Never mix 5 jobs in one card.
- Every remediation card must declare `files:`, `tests:`, `live endpoints:`, `artifact deadline: first 15 min`.

### B. Stale runtime gate (mandatory QA step)
After any `backend/daily_shortlist.py | mvp_api.py | app.py` change, QA must before PASS:
```bash
curl -s http://localhost:8000/dashboard/shortlist | python3 -c "import sys,json;print('Trigger confirmed' in open('/tmp/sl.json').read())"
# and
curl -s http://localhost:8000/dashboard/shortlist/compact | grep -c 'Trigger confirmed'
```
If mismatch with source, verdict = REVISE stale_runtime, not PASS. Deploy step is `docker compose up -d --build backend && python build_dashboard.py` — only Lite/approved path, never from worktree scratch.

### C. Resource gate
- Dirty-repo or docker-heavy cards: `max_retries=1`, `max_runtime_seconds` realistic (15m for probe, not 4h).
- On `load>1.8 or swap<500M`: block 10 min with reason, do not instant reclaim. Dispatcher backoff required.

### D. Browser locality
- QA primary evidence = `curl :3001/dashboard.html + curl :8000/compact.json + read_file /worktree/*.json`. Browser is screenshot-only, never for localhost open.

### E. Completion schema
- `kanban_complete` must have non-empty `artifacts` OR at least one probe JSON (`sl8000_after.json`). Pure-logic fixes without file still need a probe artifact.

### F. Heartbeat checkpoint
- Orchestrator (Lite) watches `last_heartbeat_at` + `artifacts empty`. If heartbeat continues >15 min with no artifact, issue bounded checkpoint: complete with artifacts or block with root cause in next 10 min. Heartbeat-only continuation not acceptable (patched in `hermes-kanban-ops`).

### G. No parallel workers for full-universe or docker cards
Arm decision 2026-08-19: parallel workers not production-approved. One worker at a time for docker/rebuild cards.

## 4. Detection queries

```sql
-- loop flag: >2 runs or any waste outcome
SELECT task_id, COUNT(*) c, SUM(CASE WHEN outcome IN ('reclaimed','timed_out','crashed') THEN 1 ELSE 0 END) waste
FROM task_runs GROUP BY task_id HAVING c>2 OR waste>0;

-- heartbeat-only
SELECT id FROM tasks WHERE last_heartbeat_at IS NOT NULL AND result IS NULL AND current_run_id IS NOT NULL;
```

## 5. Follow-up

- [ ] Patch `hermes-kanban-ops` + `kanban-worker-common` (done 2026-08-28)
- [ ] Update `signalix-dashboard-verification` checklist with :8000 live gate
- [ ] Set `kanban.failure_limit` and per-card `max_retries` as above for next run
- [ ] Archive this note in `vault/INDEX` when next gated run passes without loops

## Evidence

- DB: `sqlite /root/.hermes/kanban/boards/signalix/kanban.db` (`task_runs` since 1755250800)
- Logs: `/root/.hermes/kanban/boards/signalix/logs/t_*.log` (613–2966 lines each)
- Reference: `~/.hermes/profiles/lite/skills/.../references/signalix-2026-08-28-loop-retrospective.md`
