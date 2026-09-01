# Signalix T9 — Lifecycle Persistence + Owner-Review API

> **STATUS: OWNER-APPROVED DESIGN — IMPLEMENTED + PROMOTED; RUNTIME ACCEPTANCE PARTIAL**
> **Reconciled:** 2026-09-01 · Lifecycle source/DB integration is complete; evaluator auto-caller and public browser journey remain open.
> **Date:** 2026-08-31
> **Owner confirmation:** Q1–Q22 confirmed by Arm
> **Scope:** PostgreSQL persistence and owner-only API integration for the already-verified pure lifecycle contract.

> **Implementation status (2026-08-31):** Gates 1–5 are satisfied at source/test level, including real PostgreSQL 16 integration evidence. Gate 2 producer automatic invocation remains NOT VERIFIED because persistence is exposed through an opt-in completed-60m adapter. Gate 7 owner-only GETs are implemented with server-bound owner identity, but served acceptance is pending. Canonical migration application and the public served desktop/mobile/error journey remain deployment-gated and require owner approval.

## 1. Goal

Wire `backend/lifecycle_contract.py` into the canonical Trend/Elliott/Trade-Setup path without changing the machine decision contract. Persist machine snapshots and owner reviews as append-only historical records. Provide owner-only read/write lifecycle APIs. No broker, order, alert, or auto-trading side effects.

## 2. Locked design decisions

### 2.1 Persistence

PostgreSQL is the canonical source of truth. Use three separate tables:

- `lifecycle_candidates`: one Daily trend/Elliott thesis identity.
- `lifecycle_snapshots`: immutable machine observations/setup plans under a candidate.
- `lifecycle_review_events`: immutable Arm review events attached to exact snapshots.

Add an idempotent SQL migration under `backend/migrations/`. Apply through the canonical migration/deploy path; do not create schema by hidden application startup side effects.

### 2.2 Identity

```text
candidate_id = stable identity of (symbol, thesis_as_of, policy_version)
setup_id     = stable identity of (candidate_id, trigger, trade_stop, targets)
snapshot_id  = stable identity of (candidate_id, setup_id, observation as_of, policy/source lineage)
```

Canonical setup prices use **2 decimal places** before identity comparison. A changed trigger, trade_stop, target_1, or target list creates a new setup_id. Current price, freshness, status progression, and other observations do not create a new setup_id.

Repeated evaluation of the same canonical snapshot is idempotent and must not create a duplicate row.

### 2.3 Append-only enforcement

Application validation and database enforcement are both required:

- existing snapshot/review identity cannot be rewritten;
- historical rows cannot be updated or deleted;
- duplicate identical insert returns/uses the existing record;
- conflicting reuse of an immutable ID returns HTTP 409.

Use primary/unique keys, foreign keys, and DB mutation-blocking triggers/permissions appropriate to the existing project migration conventions.

### 2.4 Lifecycle truth and review

Latest canonical machine snapshot plus deterministic revalidation is lifecycle truth. Owner review is optional and does not alter machine lane/status.

If no review exists, the response omits the review field; do not synthesize `UNREVIEWED`, `WATCH`, or `WAIT`.

Valid review events:

```text
AGREE | WATCH | DISAGREE_WAVE | REJECT_SETUP | MISSED_CANDIDATE | NOTE
```

Every review event references exact `candidate_id`, `setup_id`, and `snapshot_id`. A later change of mind appends a new event; it never edits the prior event.

### 2.5 Revalidation

The canonical completed-60m evaluation transaction persists candidate/setup/snapshot atomically, then records revalidation result. A setup is `ACTIVE` unless one or more explicit reasons apply:

```text
STRUCTURE_CHANGED
THESIS_INVALIDATED
DATA_NOT_CURRENT
RR_BELOW_MINIMUM
```

`RR_BELOW_MINIMUM` means target-1 R:R is below 2:1 or missing/invalid. Changed plan values are compared after 2-decimal canonicalization. GET endpoints must not perform writes or revalidation side effects.

### 2.6 Authentication and errors

GET lifecycle and POST review require trusted owner identity from gateway/request context (for example `X-Authenticated-User`). The reviewer is never accepted from the request body. Missing/invalid identity → HTTP 401.

- `401` missing/invalid trusted identity
- `404` candidate/setup/snapshot reference not found
- `409` idempotency-key conflict or immutable rewrite
- `422` invalid event or payload

Review POST requires a client/gateway idempotency key. Retrying the same key returns the original event. Reusing a key with a different payload returns 409.

### 2.7 API

```text
GET  /api/lifecycle/candidates/{candidate_id}
GET  /api/lifecycle/snapshots/{snapshot_id}
POST /api/lifecycle/reviews
```

Lifecycle GET responses use an explicit envelope:

```json
{
  "candidate": {},
  "snapshots": [],
  "reviews": [],
  "provenance": {}
}
```

Lifecycle history is owner-only. It must preserve stopped/expired/invalidated attempts and never silently drop records.

## 3. Explicit non-goals

- No automatic trading or broker integration.
- No alerts/notifications.
- No public lifecycle history.
- No rewrite of legacy VCP history.
- No replacement of `/api/setup-candidates` with lifecycle endpoints.
- No hidden DB writes from GET requests.

## 4. Acceptance gates

1. Migration is idempotent and creates three tables, constraints, append-only guards, and indexes.
2. Canonical setup producer can persist one candidate/setup/snapshot atomically; repeat is idempotent.
3. 2-decimal identity behavior is tested: display/observation noise preserves setup_id; plan changes create a new setup_id.
4. Snapshot/review mutation and invalid references fail closed.
5. All six review events work; invalid event and idempotency conflicts return specified errors.
6. Revalidation covers all four expiry reasons and retains historical records.
7. GET APIs are owner-only, read-only, envelope-shaped, and lossless.
8. No alerts, broker, order, or auto-trading side effects.
9. Full backend tests, DB integration tests, and served API/error journey are separately reported.

## 5. Implementation boundary

Initial implementation may add a focused lifecycle service/adapter and migration, plus tests and API route wiring. It must preserve the existing canonical 11-group setup-candidate envelope. Runtime migration application and served public acceptance require a separate explicit deployment gate after source review.
