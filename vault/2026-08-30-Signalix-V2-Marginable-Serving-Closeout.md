# Signalix v2 Marginable-long Serving Closeout — 2026-08-30

> **STATUS: CURRENT EVIDENCE**
> **Owner:** Arm
> **Final gate:** Lite
> **Scope:** current dashboard serving and 2-month replay closeout

## Owner decisions

- Serve `signalix/vcp-decision-shadow-v2` as the decision-facing projection now.
- Use `marginable_long` as the real operational universe: active Thai ORD intersected with the owner-supplied marginable dataset and `can_buy=true`.
- Current universe: 237 eligible symbols; 694 of the 931 active ORD symbols are outside this temporary operational scope.
- Do not expand the replay to three months.
- Do not promote Low-Cheat, enable alerts, or enable auto-trading.
- Do not wait for sequence-v2 A/B superiority evidence; keep sequence-policy shadow research-only.

## Current serving contract

```text
live 60m VCP morphology / raw lifecycle
→ pure decision_shadow_v2 projection
→ structure-first candidate discovery
→ REVIEW_NOW · ACTIONABLE_REVIEW
→ EVENT_WATCH · WATCH_ONLY
```

Incomplete volume is retained as evidence/warning but no longer blocks candidate discovery. It cannot create `CONFIRMED` or `ACTIONABLE_REVIEW` by itself. `REVIEW_NOW` remains the only actionable lane. `EVENT_WATCH` is intentionally uncapped and remains watch-only.

## Verified live evidence

- Public URL: `http://91.98.72.120:3001/mvp`
- `/mvp`: HTTP 200
- `/api/vcp-finder?universe=marginable_long`: HTTP 200
- `/health/readiness`: HTTP 200
- Invalid universe: HTTP 400
- Retired `/dashboard.html`: HTTP 404
- Live API: `eligible=evaluated=returned=237`, `missing_from_run=0`
- Daily Watchlist: `ACTION_REVIEW=2`, `EVENT_WATCH=49`, `accepted=51`, `cap_dropped=0`
- KKP, BCP, and BGRIM are visible in `EVENT_WATCH · WATCH_ONLY`.
- Source policy remains `signalix/vcp-finder-60m-v1`; decision-facing policy is `signalix/vcp-decision-shadow-v2`.
- Alerts remain stopped and no auto-trading path was enabled.

## Replay evidence

- Prefix: `vcp-marginable-long-2m-20260830`
- Window: 2026-07-01 through 2026-08-28
- Cadence: two snapshots per completed trading date
- Runs: 80
- Rows: 18,960 (`80 × 237`)
- Shadow records: 18,960; missing shadow: 0
- Timeline symbols: 237; transitions: 992
- Daily-context lookahead violations: 0
- Idempotent rerun: 80 existing, 0 pending
- Descriptive outcomes: `target_hit=23`, `stop_hit=47`, `entry_not_activated=11`, `open_at_replay_end=30`; `NOT_VERIFIED=18,849` is not a loss population.

These outcomes are descriptive evidence, not a win rate or proof of policy superiority. The replay is complete for the selected operational universe; it does not generalize to the excluded 694 symbols.

## UI/performance verification

- Full relevant pytest suite: `510 passed`, `2 warnings` (FastAPI deprecation warnings).
- Mobile target: 390px.
- Final table is contained; symbols and numeric columns are readable; V2 evidence uses visible ellipsis; drawer/detail path works; browser console had no JS errors.
- Cold shell: approximately 7ms.
- Cold watch API: approximately 1.15s.
- Repeat/filter request after cache: approximately 12–17ms.
- Cold API latency remains a follow-up performance observation, not a hidden PASS claim.

## Final gate

| Gate | Verdict |
|---|---|
| Code contract | PASS |
| Universe/filter | PASS |
| Replay integrity | PASS |
| No-lookahead | PASS |
| Live API | PASS |
| Served dashboard | PASS |
| Mobile/table journey | PASS |
| Repeat-load cache | PASS |
| Cold API latency | PARTIAL / follow-up |
| Low-Cheat promotion | BLOCKED by owner policy |
| Sequence-v2 promotion | NOT PURSUED by owner decision |
| 3-month replay | NOT PURSUED by owner decision |

## Canonical implementation commits

`bebb562`, `6ab224d`, `8e788a5`, `0e092d6`, `b5408ff`, `8c71fae`, `19a7246`, `8cc5a8e`, `c338abc`, `d0b08d1`.

The canonical branch is `release/signalix-mvp-stable`; local worktree was verified clean at closeout. Remote push was not performed.

## Follow-ups intentionally left open

- Cold initial API latency optimization.
- Optional outcome-contract/KPI work if Arm later wants it.
- Threshold tuning is a separate future task and is not included in this closeout.
