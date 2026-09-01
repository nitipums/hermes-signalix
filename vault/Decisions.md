# Signalix Decisions

> **STATUS: CURRENT** · Canonical decision ledger. Markdown is the product/acceptance authority; Kanban is the active durable execution state for the current gated run and is not mirrored into vault notes.

## 2026-09-01 — Session boundary before implementation

Arm instructed: record the complete review/spec/ticket state, stop, switch to a fresh session, then implement. The old VCP todo/blocked cards were archived; no new Kanban cards were published or dispatched. Local ticket drafts are under `.scratch/2026-09-01-signalix-review/issues/`. Next session must re-read the handoff and re-check git/worktrees/runtime before publishing cards.


Arm refined the review contract: distinguish no Daily data from no 60m data; call valid Daily evidence without qualifying 60m anchors `NO_SETUP_DETECTED`/setup-forming; call invalid Fib/risk `RISK_INVALID`; prohibit legacy fallback; use a 1-day legacy deprecation window; and audit code/import reuse before removal.

Arm refined Q5–Q9 and approved the next operating boundary: technical reason-field/enum design is delegated to Lite + Codex, with independent review; canonical fallback is prohibited; valid Daily plus valid 60m without qualifying anchors is user-visible `NO_SETUP_DETECTED`; legacy deprecation is one day; Lite manages Kanban and dispatches Codex per bounded task, then independently reviews the result. Q14 approves updating the focused spec before ticket creation.



Arm approved the four review directions: (1) separate true unavailable/stale/invalid data from incomplete 60m setup; (2) target warm API ≤500ms, cold API ≤3s, first meaningful UI ≤2s, with compact list payload and heavy evidence on detail; (3) add chart-linked Daily Elliott markers and “How this wave was identified”; (4) retire legacy in stages: primary migration → audit-only quarantine → deprecation → removal/410 after rollback sign-off.

These decisions authorize contract/design refinement, not implementation or deployment. The review packet is `docs/current/2026-09-01-signalix-independent-review.md`; next step is close the remaining design frontier, then create bounded Kanban cards.


Decision: Do not fix, delete legacy, deploy, or dispatch implementation cards from the review alone. First take the consolidated review `docs/current/2026-09-01-signalix-independent-review.md` to askmatt, then create bounded Kanban cards for reason-level DATA_BLOCKED semantics, cold-path performance, chart-ready Elliott markers, and staged legacy quarantine.

Evidence: Lite, Ploy, and Codex independently reviewed the same release. All four owner concerns are `REVISE`; runtime transport is PASS but served semantics and public browser acceptance are not closed. Ploy aggregated all 237 rows: 227 DATA_BLOCKED, 10 AVOID, zero positive review/forming/candidate/wait lanes.


The owner-approved current stock-setup authority is the Elliott/Trend/Trade-Setup design and its T1–T9 promoted implementation. `/api/setup-candidates` is primary; VCP Finder notes/routes are compatibility, audit, or replay evidence. Current runtime evidence is partial: the dashboard shell and DB-built API respond, but public desktop/mobile/error browser acceptance and evaluator auto-caller wiring remain open. This entry supersedes older VCP-first wording in this ledger without deleting historical decisions.


Decision: Promote the complete T1–T8 spine plus T7/T9 lifecycle work from `prototype/elliott-state-replay` to `release/signalix-mvp-stable` after Lite source/DB/runtime gates. Served spine acceptance on the public URL (desktop/390px/error journeys) is the next gate before calling the spine production-ready; evaluator-caller wiring for lifecycle persistence stays a separate owner decision.

## 2026-09-01 — Current closeout reconciliation

The public 390px failure→Retry→recovery browser gate passed through an isolated `agent-browser` session against `/mvp`: only `/api/setup-candidates` was intercepted; the failure state showed no stale rows and an actionable Retry; restoring the route and clicking Retry returned HTTP 200 with 50 rows from 237 evaluated. Evidence is retained under `.scratch/2026-09-01-browser-failure-retry-final2/` and summarized in `vault/2026-09-01-Current-Session-Handoff.md`. The evaluator auto-caller decision and broader desktop/drawer acceptance remain separate.

Evidence: release commits `8573b9d`..`2f6e790` (T1–T8), `9589fca` (T7), `00dd37c`/`04d6639`/`ddf1a87`/`7b3ed49` (T9), full backend suite green on release after promotion; lifecycle production e2e on :8000 passed (GET/POST/401/409/idempotency, append-only trigger verified); migration `007` applied to the canonical database with owner approval.

## 2026-08-31 — T8 full-universe ranking source (LITE-VERIFIED; served gate held)

Decision: Apply deterministic lexicographic ordering to the complete canonical candidate set before presentation filters/pagination. Preserve all evaluated rows and six lane counts; no legacy positive labels or silent exclusions. Source implementation is complete, but the currently running container is not the prototype artifact: `/api/setup-candidates` returned 404 and served `/app.js` lacked the new grouping function. No restart/deploy was performed; served/public acceptance remains NOT VERIFIED and production promotion is held.

Evidence: Codex gpt-5.6-luna implementation + Lite diff/test gate; full backend suite 622 passed / 2 skipped. Source commit pending with docs sync.

## 2026-08-31 — T7 append-only lifecycle contract (LITE-VERIFIED)

Decision: Candidate thesis identity and setup-attempt identity are separate stable hashes. Machine snapshots and Arm review events are append-only; changed trigger/stop/target structure creates a new setup_id, while stopped/expired/invalidated history remains immutable. Revalidation expires an attempt for structure change, thesis invalidation, non-current data, or target-1 R:R below 2:1. Implemented as pure JSON-safe `backend/lifecycle_contract.py`; database persistence/API wiring is intentionally deferred.

Evidence: commit `c61cf7b`; lifecycle tests pass; full backend suite 619 passed / 2 skipped at closeout. Next T8 is full-universe ranking and served acceptance.

## 2026-08-31 — T6 sector/peer + VCP bonus enrichment (LITE-VERIFIED)

Decision: Sector/peer context remains evidence/ranking only; missing profile data is explicit UNKNOWN. VCP attaches only on explicitly verified positive evidence and never gates a valid candidate.

Evidence: commit `de65be3`; full backend suite 614 passed / 2 skipped.

## 2026-08-31 — T5 MVP decision-first source rendering (LITE-VERIFIED)

Decision: `/mvp` reads canonical `decision_lane`, groups six lanes in primary order, exposes Daily wave primary_state/confidence and 60m setup evidence, and routes unknown lane values to DATA_BLOCKED. Public served/browser acceptance is deferred to T8.

Evidence: commit `0787fca`; full backend suite 611 passed / 2 skipped.

## 2026-08-31 — T4 canonical decision lanes (LITE-VERIFIED)

Decision: `/api/setup-candidates` projects REVIEW_NOW, SETUP_FORMING, DAILY_CANDIDATE, WAIT, AVOID, DATA_BLOCKED with fail-closed confidence, completeness, freshness, and R:R gates.

Evidence: commit `57cd291`; full backend suite 609 passed / 2 skipped.

## 2026-08-31 — T3 60m trade-setup production boundary (LITE-VERIFIED)

Decision: 60m setup status distinguishes PRE_TRIGGER, TESTED_TRIGGER, TRIGGERED, EXTENDED, INVALIDATED, EXPIRED, and DATA_BLOCKED. Entry zone is risk-bounded; target-1 R:R ≥2:1 is the minimum review gate; trade_stop remains separate from Daily thesis_invalidation.

Evidence: commit `347aed5`; full backend suite 600 passed / 2 skipped.

## 2026-08-31 — T2 Elliott production boundary + close-gate (LITE-VERIFIED)

Decision: `EARLY_WAVE_3`/`WAVE_3_CONTINUATION` require a Daily Close above the Wave 1 high; a wick alone is `TESTED_HIGH` and never promotes. Volume/markers are supporting evidence only. Invalid or incomplete Daily OHLC fails closed (no Close-derived substitute evidence).

Evidence: commit `d31a2d2` + OHLC fail-closed remediation; frozen fixtures CRC 85.71%→WAVE_1_ADVANCE, AWC 91.18%→WAVE_1_ADVANCE, BGRIM 29.17%→WAVE_3_CONTINUATION HIGH.

## 2026-08-31 — Elliott grill and AiPASS consultation record
Decision: Preserve the owner-approved Elliott/Trend/Trade-Setup grill decisions, prototype/replay evidence, open gates, and AiPASS routing caveat in `docs/current/2026-08-31-elliott-grill-decision-record.md`. Treat the record as a curated decision/evidence index; it does not promote the prototype, override runtime evidence, or attribute mismatched AiPASS output to Claude Opus 5.
Reason: Keep the latest product reasoning and external challenger input durable and reviewable without confusing advisory output with owner decisions or deterministic production truth.

## 2026-08-30 — Marginable-long v2 serving scope
Decision: Serve `signalix/vcp-decision-shadow-v2` as the decision-facing projection on the owner dashboard, using `marginable_long` as the current operational universe: active Thai ORD intersected with the owner-supplied marginable dataset and `can_buy=true` (currently 237 symbols). Keep the 931-symbol active-ORD path only as an explicit audit/rollback mode; it is not the default dashboard scope. Do not expand replay to three months, promote Low-Cheat, enable alerts, or enable auto-trading.
Reason: Arm wants the new decision version used now on the real trading surface, limited to instruments that can be bought through the current margin workflow. Replay evidence is sufficient for this bounded operational scope; broader-universe generalization and sequence A/B promotion are deferred.

Decision: Use structure-first candidate discovery on the dashboard: incomplete volume is retained as evidence/warning but is not a hard blocker for `EVENT_WATCH`; expose the full uncapped event-watch lane as `WATCH_ONLY`. Keep `REVIEW_NOW` as the only actionable lane and preserve failed/stale/invalidation safety gates.
Reason: Arm wants more structure/event candidates for manual review while keeping confirmation and actionability conservative.

## 2026-08-28 — Dashboard-first scope; alerts paused
Decision: For the current MVP focus, keep only the dashboard surfaces: **Daily VCP Watchlist** for fast actionable review and **All VCP · 60m / Explorer** for full-universe research and audit. Pause alert delivery; the Docker `delivery` service is stopped and assigned to Compose profile `alerts`, so normal `docker compose up -d` does not start it. Backend, dashboard, PostgreSQL, and Redis remain active.

Reason: Generated alert volume made action difficult. Arm explicitly chose to focus on watchlist + explorer before revisiting alerts. This is a reversible operational/product boundary; alert source code and historical evidence remain preserved.

Canonical product/architecture decisions for Signalix. Keep concise and cite the reason.

## 2026-08-27 — VCP type semantics
Decision: Treat `standard_vcp` as the normal valid VCP morphology/entry profile and `low_cheat_vcp` as a stricter early-entry profile that is a subset of valid VCP morphology. Low-Cheat requires healthy 60m trend, valid H-L-H-L-H structure, valid base/contraction/leg-volume evidence, near-pivot price, usable tight invalidation risk, and an early non-confirmed lifecycle state. ATH proximity is not a prerequisite. Type never promotes lifecycle state or actionability.
Reason: The previous shallow/near-pivot heuristic could label trend-failed or structurally incomplete results as Low-Cheat. The owner approved clarifying that “cheat” describes entry timing before confirmation, not a looser pattern class.

Decision: VCP lifecycle `trend_pass` uses 60m evidence only. Daily trend remains supporting context and may produce `DAILY_CONTEXT_WATCH`, but cannot promote `READY`, `CONFIRMED`, or structural VCP state. Re-run after correction showed TWP downgrade from invalid prior `CONFIRMED` to review-only `BREAKOUT_WATCH`.
Reason: Prevent a Daily-context OR fallback from creating a misleading 60m confirmation.

Decision: Add `review_lane` overlays for price/volume breakout, pivot-touch volume watch, close-breakout volume pending, and insurance context. These lanes surface BGRIM/TIPH/AOT/BH-style evidence without changing VCP lifecycle state or `CONFIRMED` requirements.
Reason: Current strict VCP gates were correct but hid useful price-event context from the fast review queue; user needs take-action context without false confirmation.

Decision: Preserve `last_watch_event`/`late_watch` separately from current VCP state, and expose `DAILY_CONTEXT_WATCH` for Daily waiting-breakout symbols whose 60m VCP is not qualified. These overlays never promote state/actionability.
Reason: Prevent BA/BGRIM/TIPH-style opportunities from disappearing when current state changes or Daily and 60m evidence diverge.


## 2026-08-26 — Stable v1 closeout checkpoint
Decision: Treat `release/signalix-mvp-stable` commit `e5c7139` as the latest stable checkpoint for today's Signalix MVP. The earlier product baseline `0ab8c44` remains historical; e5c7139 adds the 60m-only confirmation correction and review-lane evidence surface.
Reason: Owner approved closing today's session at the verified pushed stable version; future VCP type/replay refinements branch from this checkpoint.

Decision: Retain only TH ORD/INDEX in `price_data` for the current Signalix product. Delete historical TH DR and US price rows after replay completion, then run `VACUUM FULL`, `REINDEX`, and `ANALYZE`. Preserve VCP replay tables and TH historical source data.
Reason: Current VCP/Watchlist/All VCP workflow is Thai ORD 60m; DR/US rows were unused in the current MVP and consumed storage/index space.

Decision: Preserve a one-month append-only point-in-time VCP replay baseline using 20 daily as-of snapshots and full 931-symbol retention. Use it for logic review only; do not call the forward proxy a win rate or final accuracy. Exact 60m breakout timing remains a follow-up replay pass.
Reason: Establish empirical evidence before locking VCP v1/type thresholds while preserving no-lookahead and live-run isolation.

Decision: Add candidate metadata `vcp_type.base_type`, `vcp_type.overlays`, `vcp_type.types`, `type_evidence`, and `type_policy_version` without changing state/actionability. Historical `price_data` is the observed ATH source. `new_stock` remains unassigned until listing-date provenance exists.
Reason: Enable sample-driven type review while preserving the stable VCP state machine and full-universe evidence.

Decision: Treat `break_ath`, `new_stock`, `low_cheat_vcp`, and `standard_vcp` as candidate VCP types for the next v1 fine-tuning pass. Keep type separate from state/actionability; no type alone can promote READY/CONFIRMED.
Reason: Arm wants distinct VCP archetypes without locking ambiguous rules before reviewing real sample cases.

Decision: Rename Daily VCP Shortlist to Daily VCP Watchlist. Default removable presentation filters are Marginable (all rates), 20-day average trade value > THB 10M, and current 60m price > THB 0.60. Watchlist state review includes actionable setups plus breakout watch.
Reason: Standardize watchlist language and keep the fast review queue focused on tradable/liquid names without changing full-universe scan eligibility.

Decision: Add `BREAKOUT_WATCH` as a review-only state (not `actionable`) when price reaches the 60m pivot and volume evidence passes before the bar closes. Daily VCP Watchlist may display it above confirmed/near/ready lanes; `CONFIRMED` still requires closed-bar close + volume confirmation. Daily trend is supporting context; 60m pivot/trigger remains authoritative.
Reason: Avoid losing intraday timing while preserving the distinction between early watch and confirmed breakout.

Decision: Run active ORD 60m fetch/VCP rounds at `10:00, 10:30, 11:00, 11:30, 12:00, 12:30, 14:00, 14:30, 15:00, 15:30, 16:00, 16:30, 16:45` Bangkok weekday time. The final 16:45 round is an explicit session-close round.
Reason: Align monitoring with the requested SET continuous-session windows `10:00–12:30` and `14:00–16:45`.

Decision: Split the VCP-first MVP into two visible surfaces: `Daily VCP Shortlist` as the fastest default page showing only actionable review (`READY`, `NEAR_TRIGGER`, `CONFIRMED`), and `All VCP · 60m` as the current full-universe table with forming/state filters. Retire the former Daily Shortlist and All Stocks Explorer from visible MVP navigation while preserving backend/history for rollback and audit.
Reason: Arm wants a minimal fast review queue without losing access to the complete VCP universe and evidence.

Decision: Make VCP Finder · 60m the default/primary owner-only MVP surface. Remove Daily Shortlist from visible MVP navigation; retain backend/routes and historical evidence for rollback. Keep Explorer only as secondary Research / Full Universe. VCP presentation uses compact tables with Symbol, Price, % Change, Distance, and R/R; contraction/breakout volume remain evidence-driven sorting inputs. Price ranges are multi-select; margin rates use Select all/Clear/Apply. Missing index or margin metadata produces no tag, never a `NOT_VERIFIED` placeholder.
Reason: Arm uses VCP Finder as the core workflow and needs dense, sortable opportunity review without oversized cards or refresh-on-every-filter-click.

## 2026-08-26 — VCP auto-run and forming lanes
Decision: Run isolated VCP 60m after each committed full/partial intraday ingestion, with ingestion lineage and overlap lock. Failed/skipped ingestion does not create a new VCP run. Forming presentation lanes are `maturing`, `early`, and `needs_work`; full-universe retention remains mandatory.
Reason: Avoid stale evaluations while preserving opportunities and make the large forming population reviewable.

Decision: Add the owner-provided Krungsri Securities Credit Balance Marginable Securities List as `signalix.marginable.v1`. VCP Finder uses it for optional multi-select margin filtering; legacy Daily/Explorer routes retain their existing filters for secondary/audit use. Cards show compact `%Margin X%`; drawer shows only `Marginable: X%` when present.
Reason: Arm normally trades through this Credit Balance list and wants the decision surface pre-filtered to usable collateral/shorting context. Margin metadata is presentation/filter-only and must not mutate canonical scan eligibility or Daily state. Owner workflow checks for a new PDF monthly; each PDF's effective date is authoritative.

## 2026-08-25 — Drawer stock navigation and cleanup boundary
Decision: The MVP drawer supports previous/next navigation across the currently visible stock cards on the active surface, via buttons, ArrowLeft/ArrowRight, and horizontal touch swipe. Navigation preserves the same authoritative symbol-detail fetch and chart contract. Retired local Signalix quarantine/audit copies are disposable after stable GitHub cutover; source, runtime artifacts, database volumes, and user research files remain protected.
Reason: Restore the legacy review flow without reintroducing a second source/worktree or deleting user-owned research data.

## 2026-08-25 — Canonical MVP source and worktree cutover
Decision: Treat GitHub `nitipums/hermes-signalix`, branch `release/signalix-mvp-stable`, as the current Signalix MVP source. The canonical local worktree is `/root/signalix`; it is the only registered worktree and is the production Docker bind-mount source. Former feature/release worktrees and temporary cleanup copies are retired and must not be treated as current implementation.
Reason: Multiple dirty worktrees and stale vault notes caused source confusion. One clean stable worktree is now the release authority; generated artifacts remain runtime outputs and secrets remain host-only.

## Work management — final owner decision 2026-08-23

Decision: **Markdown `Execution-Pipeline.md` and focused plans define product scope and acceptance. Kanban is the active durable execution/orchestration state for named workers, dependencies, heartbeats, retries, and evidence handoffs; do not mirror live card status into vault notes.**

Reason: The prior audit-only wording caused the monitor to ignore the active gated run and select stale diagnostic blockers. Separate product authority from execution state instead: one explicit active chain in Kanban, no stale-card selection, and no duplicate status copies in documentation.

## 2026-08-28 — Terminal card reporting and REVISE recovery
Decision: Every active-chain Kanban card reaching `PASS`, `DONE`, `REVISE`, `FAIL`, or `BLOCKED` must emit one delivered report to Arm with task/run ID, owner, verdict, evidence, next action, downstream holds, and production readiness. `REVISE`/`FAIL` stops downstream promotion and requires a bounded remediation card for the responsible implementation owner, linked to the failed card, unless explicitly blocked by human input/capability/resource safety.
Reason: A monitor previously missed a completed card and later stopped after `REVISE` without creating the next remediation. This invariant makes terminal delivery and recovery auditable and prevents silent flow breaks.


## 2026-08-12 — LINE dropped
Decision: Drop LINE delivery for Signalix alerts.
Reason: User decision; `notify-api.line.me` was DNS-blocked on the VPS. Telegram remains the delivery channel.

## 2026-08-12 — Deterministic calculations stay in code
Decision: Trend Template, VCP, RS, position sizing, stops, and targets are deterministic code responsibilities.
Reason: LLM output must not become a source of trading calculations. LLM is allowed only to summarize/explain deterministic results.

## 2026-08-12 — Nous LLM summarization uses non-reasoning free model
Decision: Use Nous portal model `upstage/solar-pro4:free` for Signalix alert summaries.
Reason: `tencent/hy3:free` is reasoning-oriented and can swallow visible content into thinking budget; alert text needs normal content output.

## 2026-08-12 — Alerts are plain text
Decision: Telegram alerts use plain text, not Markdown parse mode.
Reason: Markdown parse errors caused Telegram 400 failures.

## 2026-08-12 — User layer and portal/dashboard glue
Decision: Portal, dashboard, and alert deep-links are connected through backend user/watchlist APIs.
Reason: SaaS workflow needs one account/watchlist source of truth, not dashboard-only localStorage.

## 2026-08-12 — Market View to Action product direction
Decision: Use a shared internal Market View to Action Engine, while presenting separate product language and policies for Stock Alert, DR Follow, TFEX Trigger, Fund Plan, and Investment Copilot.
Reason: These products share signal-to-instrument mechanics but serve different user groups and have materially different execution/allocation rules.

## 2026-08-12 — Fundamental context is a separate evidence layer
Decision: Store sourced basic fundamental snapshots and expose selected fields in the English UI, separately from technical signal and risk calculations.
Reason: Serve value-investor and mixed-style users without allowing stale/undated fundamental data or an LLM to become an executable trading decision.

## 2026-08-12 — Log recommendations and test in a paper portfolio first
Decision: Record immutable recommendation/decision/execution/outcome events and build an isolated paper/pilot portfolio before live auto-trading.
Reason: Measure recommendation quality and test portfolio management, reconciliation, risk limits, and action lifecycle without risking real capital.

## 2026-08-12 — Industry analysis combines taxonomy and behavior
Decision: Add industry/group analysis as a first-class Signalix layer. Start with an authoritative industry taxonomy, then add breadth, dispersion, leadership, and rotation metrics; behavioral clusters are a later complementary layer.
Reason: A group can move together, narrow to a few leaders, or fragment. Market-cap-weighted performance alone can hide this distinction, so group state must show participation and divergence.

## 2026-08-13 — Unified 60m intraday overlay and stored-data chart policy
Decision: Retire 15m from Signalix active fetch/evaluation/UI paths. Use one active-shortlist 60m feed with every-10-minute intended refreshes during SET continuous sessions, updating the open candle on each DB upsert. Daily EOD remains the owner of structural indicators; intraday evaluates action overlays only.
Reason: A split 15m/60m architecture and incorrectly parsed prior timer created data freshness confusion and unnecessary external API pressure. A single stored 60m layer makes data provenance and current-candle behavior understandable.

Decision: Daily/Weekly/Monthly charts aggregate stored Daily/60m data and show a provisional current-period candle; do not issue a new upstream series fetch for those chart views.
Reason: Match TradingView-like current-bar behavior while preserving source discipline and avoiding unnecessary external calls.

## 2026-08-13 — Liquidity-first dashboard and volume context
Decision: Hide stocks below THB 10M 20-session average Daily traded value by default; apply the same default filter to Top Gainers. Flag volume surge only when same-time cumulative current volume is at least 5x prior session, with >=5M shares and liquid-name guards.
Reason: Percent moves and ratios from illiquid names create misleading attention. Same-time cumulative comparison answers the user’s actual intraday question.

## 2026-08-13 — Company context cache is non-decision data
Decision: Add `company_profiles` cache for company name, sector, industry, and short business description; current fallback is Yahoo Finance metadata. Settrade quote endpoint remains the source for supported quote/fundamental ratio fields but does not provide this taxonomy.
Reason: Detail UI needs business context, but metadata must not contaminate deterministic technical/risk decisions. An official SET instrument master/taxonomy remains the P0 target.

## 2026-08-13 — ATH semantics
Decision: Compute 52-week high/low from the latest 252 sessions and ATH from the full local stored archive; label/understand ATH as local-history coverage until source coverage provenance is available.
Reason: 52W and ATH had accidentally shared the same window, creating incorrect identical values.

## 2026-08-12 — MiroFish is an external UX/UI feedback lab

Decision: Evaluate MiroFish as a scenario-based, multi-persona UX/UI critic and ideation tool for Signalix.
Reason: Simulated technical-trader, VI, DR, TFEX, fund, beginner, and risk-conscious personas may reveal workflow friction and terminology ideas before implementation. Outputs remain hypotheses requiring Arm/Bee/Ploy review and must not affect deterministic trading logic or live execution.

## 2026-08-14 — Daily screener: five one-level decision groups

Decision: The dashboard uses exactly five mutually exclusive display groups: **เบรกใหม่** (`breakout_new`), **ย่อในขาขึ้น** (`uptrend_pullback`), **รอเบรก** (`waiting_breakout`), **สร้างฐาน** (`base`), and **ขาลง / หลุด** (`down_or_broken`). Fresh/retest/extended and base/continuation/reversal remain internal stage/origin attributes, not extra display groups.

Reason: Prior labels conflated “not an immediate entry” with a broken trend. Strong or repairing names outside an exact setup window (for example IRPC, SMT, FORTH, CRC, CCET) must remain visible as **รอเบรก**; a base/repair above MA200 with a 20D range up to 20% may be **สร้างฐาน** (e.g. WHA). **ขาลง / หลุด** is reserved for genuinely weak/broken structure.

## 2026-08-14 — Immutable breakout lifecycle v2

Decision: A breakout event stores a canonical `NUMERIC(18,4)` original trigger and append-only observations linked to immutable scan runs. Fresh confirmation requires close >=1% above trigger and volume >=1.2x. Setup window is <=5% below trigger (near <=3%, watch >3–5%); retest is +/-3%. Persist the 5-session pre-break pivot low and use `max(pivot_low, trigger × 0.96)` as the failure level.

Reason: Rolling 20D highs cannot reliably distinguish fresh break, retest, extension, and failure. A development event baseline created before the direct 5-session pivot calculation was backed up and reset; the clean baseline scan started after the corrected calculation.

## 2026-08-20 — Pull ALL symbols: remove 15% price-gap skip (owner directive)

Decision: Remove the yfinance-fallback price-continuity guard entirely. `fetch_yfinance` no longer skips a symbol whose first fetched close deviates >15% from the last DB close. Pull every known symbol; no price-gap filter.

Reason: Arm: “เราคุยกันแล้วว่าดึงทั้งหมด”. The 15% guard was a yfinance data-quality safety net but also silently dropped real names (especially low-priced stocks where a 0.01→0.02 change is a 50% gap). Owner wants complete coverage over defensive skipping.

## 2026-08-21 — Intraday feed availability is separate from instrument eligibility

Decision: Track Settrade 60m availability in `intraday_feed_status`, not in `symbol_master`. After three consecutive empty/failed responses, a symbol is skipped only by the 60m fetch for a 24-hour cooldown. Successful fetch resets the status.

Reason: Eleven symbols repeatedly returned no Settrade intraday bars, but removing them from `symbol_master` would incorrectly remove valid Daily/EOD history and scan coverage. The dashboard must show `60m unavailable · Daily EOD` and keep Daily EOD as the decision source. `COLOR` remains the separate instrument-master exception because Settrade reports the symbol itself as not found.

## 2026-08-20 — Exclude COLOR from ORD master (owner override)

Decision: Mark `COLOR` as `status='excluded'` in `symbol_master` with reason `Owner override: Settrade Symbol not found [COLOR]`. It drops out of the scan universe and dashboard. Official Settrade weekly master sync remains the authority: if COLOR reappears on the official list, the sync auto-reactivates it.

Reason: Settrade API consistently returns `Symbol not found [COLOR]` (was already `inactive` from the 60m run). Arm: “color exclude ไปเลยก็ได้ครับ”.

## 2026-08-21 — Exclude persistent intraday-empty tail

Decision: Mark ACAP, BLISS, GSTEEL, KKC, NWR, TAPAC, and WELL as `symbol_master.status='excluded'` with an owner-override reason. All seven returned empty Settrade 60m responses persistently and had no EOD data or EOD latest date older than one year as of 2026-08-21. The nine remaining persistent intraday-empty symbols were not excluded because their EOD data was newer than one year.

Reason: Retry fixes transient Settrade warm-up misses, but these seven have zero intraday rows across repeated runs and stale/no EOD evidence. Excluding them prevents repeated partial-success noise and removes them from the scan/dashboard universe. If an official master sync reactivates a symbol, re-evaluate it rather than silently assuming the gap is fixed.

## 2026-08-21 — Intraday fetch-to-dashboard E2E contract

Decision: Intraday `--no-scan` remains separate from Daily classification, but every completed 60m ingestion/evaluation must rebuild `dashboard.html` and `dashboard_snapshot.json` from the existing Daily scan. Watchdog treats expected `partial_success` as tolerated, identifies `intraday_price_data` explicitly, and uses a 90-minute 60m candle threshold plus 30-minute evaluator-state threshold.

Reason: A healthy DB fetch previously left the static served dashboard stale. Process exit 0/1 and HTTP 200 are not sufficient; acceptance is Settrade fetch → DB run/rows → evaluator → dashboard artifacts → served dashboard → browser `Last Scanned`.

## 2026-08-23 — Daily Shortlist default; All Stocks Explorer retained
Decision: Make **Daily Shortlist** the default Signalix surface for trustworthy Thai Daily swing-trade setups. Retain the current stage-first dashboard as a secondary **All Stocks Explorer** for full-ORD research; label it clearly as research rather than suggestions.

Daily Shortlist eligibility: all active Thai ORD are scanned, while publication requires 20-day average daily traded value of at least **THB 10,000,000**. Publish only `READY` and `PRE_READY`; exclude developing/base-building, broken, invalidated, low-liquidity, and `DO NOT CHASE` names. Ranking is deterministic and explainable: structure 40%, entry readiness 30%, risk/reward 20%, liquidity as hard gate/tie-breaker. Market regime is visible context only and must not suppress, rank-penalize, or otherwise modify candidates.

Reason: Owner confirmed the next version must be a trustworthy daily shortlist, not a filter-heavy full-market terminal. Keeping Explorer preserves broad research and FULL ORD coverage without diluting the decision surface.

## 2026-08-25 — Watch-only movers and canonical MVP cleanup
Decision: Keep `READY`/`PRE_READY` gates unchanged. Add separate `RISING MOVERS`
(`WATCH ONLY`) and `CAUTION` (`DO NOT CHASE`) lanes for strong Daily price/volume
moves that are not actionable setups. S1/S2 context can enter Rising Movers;
S3/S4, topping, or extended structures enter Caution. Neither lane receives
shortlist rank or entry permission.

Decision: Explorer Stage and Search filters apply immediately without an Apply
step. The owner-only MVP chart exposes real `1D`, `1W`, and `60M` views (plus
`1M` API support); 1W/1M aggregate stored Daily bars and 60M reads stored
intraday 60m bars. Chart controls/indicator values must remain below the plot.

Decision: Remove legacy projection labels (`evidence_summary`,
`old_group_mapping`, `lifecycle_badge`) at the canonical MVP artifact boundary.
Current Stage/Phase/provenance is the only decision-facing state.

Reason: A price move is not equivalent to an actionable setup, while hidden
movers reduce decision quality. Separate watch/caution lanes preserve both
truthful context and a trustworthy shortlist; canonical sanitization prevents
old dates/groups from contradicting current Daily evidence.