# Signalix Card Template — LOCKED 2026-08-28 (owner approved)

Use this template for every new Signalix card. Orchestrator must reject cards missing `files:`.

```markdown
Title: [P0/P1] <short verb> — <component>

Body:
## Goal
<1 sentence — what user will be able to do>

## Files
- backend/daily_shortlist.py:123-247
- backend/mvp_api.py:160-350
- backend/test_daily_shortlist.py

## Tests
- focused: `pytest backend/test_daily_shortlist.py -q` (expect 51 pass)
- regression: `pytest backend/ -k "not mvp_watch" -q`

## Live endpoints
- curl :8000/dashboard/shortlist → check `Trigger confirmed / quality pass` absent
- curl :8000/dashboard/shortlist/compact
- curl :3001/dashboard.html

## First artifact deadline
15m: attach `sl8000_after.json` or `slcompact_after.json` (probe) — non-empty artifacts required

## Done when
- [ ] code + tests green
- [ ] live probe matches source (no stale runtime)
- [ ] browser desktop 1280 / mobile 512 no overflow
- [ ] kanban_complete with artifacts=[...] + metadata {skill_used, verification, changed_files, artifacts, residual_risk}

## Constraints
- Work only in $HERMES_KANBAN_WORKSPACE
- max_retries=1 if docker/restart
- No parallel workers for docker/full-universe
- Primary QA evidence = curl + read_file, browser = screenshot only
```

## Orchestrator gates (enforce before dispatch)

- [ ] `files:` present → no dispatch otherwise
- [ ] `max_retries=1` for docker/restart/full-universe
- [ ] QA includes `:8000` live probe vs source diff
- [ ] `artifacts` will be non-empty (probe JSON at minimum)
- [ ] No >2 large P0/UI cards concurrently
- [ ] Heartbeat >15m with empty artifacts → checkpoint in 10m

Refs: `vault/Execution-Pipeline.md` Loop prevention (LOCKED), `vault/Lesson-Learned-Full-Board-260-Cards-2026-08-28.md`
