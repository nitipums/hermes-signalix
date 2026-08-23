# Signalix Decisions

> **STATUS: CURRENT** · Canonical decision ledger. Active work-management rule is recorded below: Markdown pipeline active; Kanban audit/archive only.

Canonical product/architecture decisions for Signalix. Keep concise and cite the reason.

## Work management — final owner decision 2026-08-23

Decision: **Markdown `Execution-Pipeline.md` is the active Signalix work source. Kanban is audit/archive only and must not be used for new dispatches.** Focused executable plans live under `/root/signalix/.hermes/plans/` and must link back to the pipeline row.

Reason: Kanban generated duplicate/blocked graph noise and required more orchestration than the bounded work justified. Keep its history for audit, but use one controlled Markdown sequence for active work.


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