# Architecture

> **STATUS: CURRENT** · `CANONICAL_FOR: current system architecture and runtime data flow`.
> **Reconciled:** 2026-09-19 · Daily Trend Mapping and Market Breadth are the active public read-only surfaces. Setup/Elliott paths are historical/audit only; current pointers and validated read-model artifacts are the only serving inputs, with Git history as rollback authority.

## Current routing boundary

The [active-only contract freeze](../docs/current/2026-09-20-active-only-contract-freeze.md)
owns current routing semantics; the [pointer/artifact inventory](../docs/current/2026-09-20-pointer-artifact-inventory.md)
is evidence only. The historical architecture below does not override them.

## Production-served Daily Trend Mapping

The current architecture is:

```text
Daily price_data
→ bounded EOD publisher
→ immutable Trend Map read-model artifact + current pointer
→ GET /api/trend-map
→ GET /trend-map
→ shared chart drawer for evidence review
```

### Read-path prebuild invariant

Every reusable market-data payload used by the public Trend Map must be
prebuilt at the relevant publication boundary as a compact, validated,
content-addressed read model. The drawer chart contract covers all four
supported timeframes: `1D`, `60M`, `1W`, and `1M`.

```text
EOD publication → 1D / 1W / 1M chart artifacts
Intraday commit → 60M chart artifact
request path   → pointer validation → symbol/timeframe selection
              → explicit DB fallback only when artifact is unavailable/stale
```

The request path must not query PostgreSQL, parse raw history, rescan the
universe, or recompute indicators for a valid artifact. Artifact freshness,
source/as-of, pointer identity, and fallback provenance are mandatory. Explicit
DB fallback is permitted only when the validated artifact is unavailable or
stale, and must be provenance-labelled. This is an architectural invariant for
Signalix read-only surfaces, not an optional latency optimization.

Trend Mapping is production-served read-only Daily evidence. It does not create
setup decisions, BUY/alerts, orders, broker actions, or auto-trading. The
publisher and API preserve Daily as-of, provenance, quote basis, data-quality
states, and fail-closed behavior.

## Market Breadth — source/UI slice

Market Breadth is a separate aggregate read-only surface:

```text
active Thai ORD Daily observations
→ deterministic breadth builder
→ immutable Market Breadth artifact/pointer
→ GET /api/market-breadth
→ GET /market-breadth
```

It uses the fixed current active-ORD universe, completed Daily sessions,
Main Trend 1–4 evidence, A/D, moving-average participation, highs/lows, and
raw volume breadth. It does not modify `/api/trend-map`, create symbol setup
decisions, or expose alerts/orders/broker semantics. Source, fixture/API, and
390px/desktop isolated browser checks and the Wave 1 production artifact/public
runtime promotion are verified. The 2026-09-19 read-back showed artifact
`signalix.market-breadth.artifact.v2`, `as_of=2026-09-18`, `929` active symbols,
`841` observed, `88` blocked, `quality=PARTIAL`, and `freshness=AVAILABLE`.
PARTIAL remains explicit: the declared active-ORD denominator includes symbols
without valid current/prior prices; category counts include only valid rows.

The first beginner-facing UI slice adds a `Daily Market Participation` bar
(advancing/declining/unchanged within the active-ORD denominator) and a small
SET Index benchmark context strip from `price_data.symbol='SET'`. SET is
context only and never changes the breadth denominator. SET50 is explicitly
out of scope for this slice.

## HISTORICAL / SUPERSEDED / DROPPED — retained setup/shadow trial flow — 2026-09-01

The 2026-09-11 private signal transition adds a read-only local shadow consumer
after the canonical setup read model:

```text
trailing 7 calendar days of Daily + completed 60m market data
→ point-in-time canonical setup rebuild (no lookahead)
→ actionable_signal_policy.py market-buy projection
→ /api/shadow-buy-signals?days=7
→ /mvp Shadow Buy Signals · 7D tab
→ Arm review and manual execution decision
```

This additive path does not require portfolio data, publish to Redis, send
alerts, write signal state, or submit broker orders. The canonical
`/api/setup-candidates` contract remains unchanged during shadow validation.

```text
marginable_long (237)
→ Daily EOD trend/strength + Elliott evidence
→ verified 60m minor structure / trade setup
→ deterministic trigger + stop + targets + R:R
→ VCP/sector/peer bonus evidence
→ /api/setup-candidates
→ /mvp → Arm chart review
```

The older flow below is retained as compatibility/history; it must not be read as the current decision authority.

## HISTORICAL / SUPERSEDED — compatibility data flow
```
            ┌─────────────────── EOD INGESTION ───────────────────┐
   Thai EOD │  update_data.py  (local zip → drive → Settrade → yf) │
   zip /    │  incremental, idempotent (ON CONFLICT DO NOTHING)    │
   Drive /  │  yfinance: NO 15% price-gap skip (2026-08-20)        │
   Settrade └───────────────┬──────────────────────────────────────┘
                    ▼
                    PostgreSQL  price_data / intraday_price_data / company_profiles
                        │  (SET index = benchmark for RS)
                        ▼
   ┌───────────────── SCREENING (deterministic) ─────────────────┐
   │  screening.py  scan_universe() → group_scan_results()        │
   │  Trend Template 8/8 · VCP · RS Rating · Buy Zone · Stop      │
   └───────────────┬───────────────────────────┬──────────────────┘
                   │ publish (screen envelope)  │ write scan_results.json
                   ▼                            ▼
              Redis channel              build_dashboard.py
                 'signals'                    │
                   │ subscribe                ▼
   ┌─────────── DELIVERY (signalix_delivery) ─┐   dashboard_server.py
   │  delivery_consumer.py → push_telegram()  │   (static, :3001)
   │  (app.py /scan also pushes batch summary)│
   └───────────────────┬──────────────────────┘
                        ▼
                  Telegram chat (7295704669)
```

## Containers (docker-compose)
| Service | Image | Port | Role |
|---------|-------|------|------|
| `signalix_postgres` | postgres:16-alpine | 5432 | price archive |
| `signalix_redis` | redis:7-alpine | 6379 | pub/sub bus |
| `signalix_backend` | builds `./backend` | 8000 | FastAPI API |
| `signalix_dashboard` | builds `./backend` | 3001 | dashboard service; historical MVP server/routes are not current product routing |
| `signalix_delivery` | builds `./backend` | — | Redis consumer → Telegram |

Backend and delivery share the **same image** (redis + requests preinstalled).
Delivery runs `python -u delivery_consumer.py` (the `-u` avoids block-buffered
logs in the non-TTY container).

## Webhook contract
`POST /webhook` (backend, :8000)
- Requires header `X-Webhook-Secret: <WEBHOOK_SECRET>` (or `?secret=`) → 401 else.
- Body: `{"symbol","source","price", ...}` → stored (dedup by hash) + published.

## Key files

The compatibility entries named `mvp_*`, `build_dashboard.py`, and related
legacy helpers below are historical/audit inventory, not current routing
targets or documentation authorities.
- `backend/app.py` — FastAPI routes (`/webhook`, `/scan`, `/screen/{sym}`, `/chart/{sym}`, `/health`)
- `backend/delivery.py` — `push_telegram()` + envelope formatting (shared by batch + consumer)
- `backend/delivery_consumer.py` — Redis subscriber entrypoint
- `backend/screening.py` — DB-backed Minervini engine
- `backend/update_data.py` — Daily ingestion plus full active-ORD intraday 60m ingestion; `intraday_feed_status` tracks per-symbol Settrade 60m availability without changing Daily eligibility
- `backend/intraday_evaluator.py` / `run_intraday_evaluation.py` — 60m action overlay and transition persistence
- HISTORICAL intraday E2E contract: fetch → `intraday_price_data` upsert (active feed only) → evaluator → MVP snapshot/projection → served `/mvp` on `:3001`; the former `/dashboard.html` artifact is retired and not a public acceptance surface.
- `backend/refresh_company_profiles.py` — non-price cached company context; restrict future refreshes to active ORD universe
- `backend/build_dashboard.py` — HISTORICAL compatibility snapshot builder; not a current route or serving input
- `backend/mvp_server.py` / `mvp_routes.py` — HISTORICAL owner-only MVP server/dispatcher; `/mvp` and `/api/setup-candidates` are not current routes
- `backend/canonical_setup_projection.py` — deep read-only interface for canonical setup-candidate validation, ordering, filters, pagination, lane counts, freshness, and provenance
- `backend/mvp_api.py` — candidate builders plus compatibility projections; re-exports the canonical projection interface for existing callers
- `backend/canonical_freshness_lineage.py` — deep read-only sidecar lineage adapter; compares published intraday fetch time with embedded lineage and preserves Daily/read-model identity
- `backend/mvp_routes.py` — canonical/legacy dispatcher plus compatibility wrapper for freshness overlay
- `backend/read_model_publisher.py` — validates/publishes canonical read-model and intraday sidecar
- `backend/canonical_chart_read.py` — deep read-only chart row retrieval/aggregation seam for SQL shape, provisional current-session data, chronological conversion inputs, labels, and timestamp metadata
- `backend/mvp_chart_db.py` — SELECT-only chart response adapter for `1D`/`1W`/`60M`/`1M` OHLCV + indicators
- `backend/app.py` — FastAPI routes, chart response adapter, and chart aggregation consumers

## HISTORICAL / SUPERSEDED / DROPPED — retained trial MVP surface contract — 2026-09-01

The retained owner-only trial surface is the Elliott/Trend/Trade-Setup
decision spine:

```text
/mvp
  └─ Trend + Daily Elliott candidate + 60m Trade Setup
      ├─ REVIEW_NOW
      ├─ SETUP_FORMING
      ├─ DAILY_CANDIDATE
      ├─ WAIT
      ├─ AVOID
      └─ DATA_BLOCKED
```

`/api/setup-candidates` was the setup-trial API. `/api/vcp-finder` and VCP
artifacts are compatibility/audit paths only. This section is preserved as
historical evidence and is not current delivery or acceptance authority.

### Deterministic chart and OHLCV window summary — 2026-09-10

`GET /api/chart-db/{symbol}?timeframe=1D|1W|60M|1M` is a read-only chart adapter over `price_data`/`intraday_price_data`. It returns source OHLCV candles plus canonical `indicators` under policy `technical-indicators-v2`: MA5/10/20/50/100/200, MACD(12,26,9), Wilder RSI(14), Wilder ATR(14), and aligned rolling/window data.

`indicators.latest.window_summary` contains rows for 5/10/20/50/100/200/260 candles with Open, High, Low, Close, total/average volume, Change %, Range %, MA when applicable, availability, and provenance. The 260-candle Daily window is the 52-week trading range, not an MA; other timeframes label it `260 candles`. The adapter fetches at least 260 candles so the 52-week value can be verified when source history exists. The UI consumes this payload without recalculating financial values in JavaScript. Missing/invalid/insufficient input is `NOT_VERIFIED`.

### Team Facts Read API v1 (2026-09-03)

`GET /api/team/setup-candidates` is a public, unauthenticated, read-only
market-data feed over the published canonical `marginable_long` universe. It
contains no secrets or private fields. The feed is facts-only and has no buy,
order, or other trading-action semantics.

Team item identity derives `can_buy=true` from membership in that validated
canonical universe; this is universe membership, not an inferred stock signal.
An explicit per-item `can_buy` value must agree, and non-canonical or unknown
universes fail closed.

The `team-facts-v1` response contains top-level deterministic `momentum`,
`near_high`, and `pullback` views. Items contain only identity, current facts
from the actual latest price timeframe, neutral indicators, the latest
completed 60m bar when available, and provenance; historical arrays are not
included.
`GET /api/team/setup-candidates/{symbol}/history?timeframe=1D|60m&limit=...`
returns one canonical symbol's bounded candles for only the requested
timeframe. Root freshness metadata is preserved,
but freshness and completeness are evaluated per symbol; a partial root status
does not globally exclude valid symbols. It does not expose setup, wave, lane,
trigger, risk, target, mapped labels, or buy
instructions. Daily and 60m sources/timeframes are explicit. Each view is
bounded to 400 Daily and 200 60m rows per symbol; exclusion counts and reasons
are returned for missing, stale, or incomplete data; every applicable view
requires a completed 60m row. `volume_ratio_20` is explicitly
`current_daily_volume / mean(previous_20_daily_volumes)` and is null when 20
prior Daily volume observations are unavailable. Freshness is classified once per symbol from these same rows and response
`now`: item provenance, facts, the 60m detail Daily baseline, and aggregate
envelopes all reuse that result. `overall_status` is authoritative; producer
values are retained only under the explicitly non-authoritative
`source_metadata` shape `{scope: "published_read_model_report", authoritative:
false, reported: {...}}`. Raw producer freshness keys therefore remain
available for audit under `source_metadata.reported` and are never status
aliases at the `source_metadata` top level.
Fresh Daily is required for every view. A Daily date remains a date, while
60m `as_of` is an actual completed candle timestamp; list and detail responses
use the latest timestamp appropriate to their requested source. The handler loads and
validates only the current published read model and performs bounded read-only
OHLCV queries; it does not rebuild/scan, load legacy snapshots, write
PostgreSQL, send alerts, or execute broker/auto-trading actions. Unavailable
data/model is 503. The response states
that values are facts and deterministic indicators for independent review, not
trading truth or orders. Alerts, auto-trading, and broker execution remain
`PENDING / FUTURE FEATURE` and OFF.

### Implementation spine history — 2026-08-31 (T1–T9 promoted; current acceptance split above)

- **T1 universe + contract scaffolding: DONE** — commit `8573b9d` (`resolve_universe` 931/237/694, canonical 11-group envelope, session-aware freshness, fail-closed `DATA_BLOCKED`).
- **T2 Elliott engine production boundary: DONE** — commit `d31a2d2`; Daily close-gate + `build_wave_contract` + frozen CRC/BGRIM/AWC evidence fixtures.
- **T3 60m trade-setup production boundary: DONE** — commit `347aed5`; explicit `PRE_TRIGGER`/`TESTED_TRIGGER`/`TRIGGERED` distinction, risk-bounded entry zone, target-1 R:R ≥2 gate, expiry and separate Daily thesis invalidation.
- **T4 canonical decision lanes: DONE** — commit `57cd291`; six fail-closed lanes (`REVIEW_NOW`, `SETUP_FORMING`, `DAILY_CANDIDATE`, `WAIT`, `AVOID`, `DATA_BLOCKED`) and deterministic ordering helper.
- **T5 MVP decision-first rendering: DONE at source** — commit `0787fca`; `/mvp` consumes canonical `/api/setup-candidates`, renders lane groups and honest fallback states. Served browser/public-route evidence is held for T8.
- **T6 context + bonus enrichment: DONE** — commit `de65be3`; sector/peer context is non-gating and VCP is optional bonus evidence.
- **T7 lifecycle contract: DONE** — commit `c61cf7b`; pure JSON-safe append-only candidate/setup IDs, snapshots, owner reviews, and revalidation/expiry. T9 now supplies the separate persistence/API integration at source and test-database level.
- **T8 full-universe ranking source: DONE** — Codex + Lite verified; `project_setup_candidates_response` sorts the complete canonical set before filters/pagination using the T4 lexicographic helper; all six lane counts and evaluated coverage are preserved. Full source suite: 622 passed / 2 skipped.
- **T8 contract remediation: DONE** — commit `2f6e790`; production builder now uses canonical `build_wave_contract`, preserves explicit intraday timeframe metadata, recognizes `decision_lane` in reconciled projection, and completes ranking tie-break dimensions.
- **T8 served acceptance: NARROW PASS / BROADER NOT VERIFIED** — release spine promoted; backend + dashboard reloaded; served `/api/setup-candidates` via `:3001` returns the full 237 universe from the live DB builder with honest lanes. The public 390px failure→Retry→recovery journey passed; broader desktop/drawer/chart semantic acceptance remains a separate gate. This line is retained as implementation history.
- **60m anchor policy: relaxed-1bar-scaled-20260831** — 1-bar legs with scaled 1% significance (3% for 2+ bars); funnel verified: anchors pass 15/237 (was 1/237). Remaining DATA_BLOCKED are honest fail-closed (no qualifying 60m structure in the prior 30 bars).
- **T9 lifecycle persistence/API: SOURCE+DB DONE** — commits `fd22674`..`7b49de3`; PostgreSQL 3-table append-only persistence, canonical 2-decimal plan comparison, owner-token/server-bound identity enforcement, read-only lifecycle projections, owner review events, and completed-60m opt-in persistence adapter. Lite verified `backend/test_lifecycle_postgres.py` against ephemeral PostgreSQL 16: 9 passed.
- **LIFECYCLE-T9 runtime boundary: PARTIAL / OWNER DECISION OPEN** — lifecycle routes have source/test and owner-token-protected route evidence; the evaluator caller does not yet invoke the opt-in persistence hook automatically. This is separate from the completed narrow 390px UI failure/recovery gate.
- **Next:** manual Arm Wave-identification review and any new bounded product feedback; evaluator caller wiring remains a separate owner decision.

VCP runs after committed full/partial 60m ingestion, with ingestion lineage and overlap lock. Failed/skipped ingestion does not create a new VCP run. Missing optional index/margin metadata is omitted from tags; it is never displayed as `NOT_VERIFIED`.

`1D` reads Daily bars, `1W`/`1M` aggregate Daily bars, and `60M` reads stored
intraday 60m bars. Chart controls and indicator legends are below the plot so
they cannot obscure candles, volume, MA, or RSI panes.

Freshness display keeps ownership explicit: `Daily EOD` timestamp is the
official decision provenance, while `60m updated` comes from the latest
completed `intraday_ingestion_runs.fetch_completed_at`. Intraday refresh must
never overwrite the Daily decision timestamp.

Chart timeframe changes use an abortable request generation guard so an older
1D/1W/60M response cannot overwrite the currently selected timeframe. Missing
60m data returns an explicit unavailable state; it never silently replaces the
selected timeframe with Daily candles.

See [[Components]] for detail, [[Deployment]] for ops.

## Market Breadth MB-2 source boundary (2026-09-14)

Market Breadth is a separate deterministic, public read-only artifact line. The
MB-1 builder feeds `backend/market_breadth_artifact.py`, which publishes an
immutable content-addressed v2 version and atomically selected pointer under a
dedicated root. The publisher prebuilds bounded `current`, `history_20`,
`history_60`, `history_260`, and `history_all` aggregate-only slices; raw MB-1
per-symbol detail remains retained as source/audit evidence and is not exposed
by the public route. `mvp_server.py` exposes only `GET /api/market-breadth`;
its `range=20|60|260|all` path validates the referenced artifact and selects
one prebuilt field before serialization. A bounded in-process cache reuses
only unchanged, previously validated content and invalidates on pointer/file
identity changes. It does not rebuild, query, write, scan, or fall back to
Trend Map or marginable-long data.
The envelope is `PRODUCTION_READ_ONLY`, `research_only=false`, and
`actionability=NONE`, with active-ORD universe identity and explicit null
reasons. Source/tests and the Wave 1 runtime/deployment and served endpoint
verification are complete; the artifact retains explicit `PARTIAL` quality.

## Market Breadth MB-4A live replay publisher (2026-09-16)

`backend/market_breadth_publisher.py` adds the bounded read-only Postgres
replay seam. It snapshots active ORD from `symbol_master`, resolves up to 520
completed market sessions, emits only the final 260, applies the existing
official-`price_data`-first then eligible derived-Daily policy, enriches
point-in-time Main Trend v6 evidence, and attaches a `price_data` SET-only
benchmark. It publishes through the MB-2 immutable artifact writer; it does
not query or rebuild on requests, write market data, change Trend Map routes,
or introduce SET50 semantics. `universe.observed_count` remains the historical
union for compatibility; `current_observed_count`, `current_blocked_count`,
and `current_declared_count` are the resolved-as-of coverage contract. Live
Postgres replay and runtime promotion remain **NOT VERIFIED** when no source
container is available.

## Current intraday E2E reliability contract (2026-08-21)

The active 60m path is:

```text
Settrade full active ORD fetch (excluding feed-status cooldown symbols)
→ intraday_price_data upsert
→ intraday_feed_status update (retry/unavailable/available)
→ intraday evaluator
→ dashboard rebuild from existing Daily scan
→ dashboard_snapshot.json + dashboard.html
→ separate dashboard server :3001
```

Per-symbol intraday feed failure must not remove a symbol from Daily/EOD. When a
60m feed is unavailable, the dashboard explicitly shows `60m unavailable · Daily
EOD` and uses Daily EOD as the decision source. `COLOR` is the separate
instrument-master exception: it remains excluded until official Settrade master
sync reactivates it.

It deliberately does not run a Daily scan. Daily membership/classification remains EOD-owned. A run may be `partial_success` when Settrade returns empty data for a bounded symbol tail; that is tolerated by the watchdog when data/evaluator freshness is healthy. Dashboard freshness must be proven at the served browser surface, not only by DB or HTTP 200.

The next product direction is documented in [[Product-Strategy-Market-to-Action]]. Signalix is evolving toward a shared **Market View to Action Engine** with separate DR Follow, TFEX Trigger, Fund Plan, Stock Alert, and private Investment Copilot experiences. The strategy includes sourced fundamental context, immutable recommendation/outcome logging, and an isolated paper/pilot portfolio before live execution.
