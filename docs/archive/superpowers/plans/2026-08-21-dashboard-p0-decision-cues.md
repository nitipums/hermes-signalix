# Signalix Dashboard P0 Decision Cues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add evidence-backed Market Posture, trigger distance, and honest zero-result states to the Signalix dashboard without changing scan logic.

**Architecture:** Keep the change UI-only in `dashboard_template.html`. Compute posture from the existing serialized `items` array in a pure client-side helper, render it above screener controls, and render trigger distance from `breakoutEvidence.trigger` only when valid. Preserve existing load-error/retry behavior and add focused source-contract tests before implementation.

**Tech Stack:** Static HTML template, inline JavaScript, CSS, Python `unittest`/pytest source-contract tests, generated `dashboard.html`, Playwright acceptance harness.

**Spec:** `docs/superpowers/specs/2026-08-21-dashboard-p0-decision-cues-design.md`

## Global Constraints

- Full ORD universe and Stage-first architecture remain unchanged.
- Posture is context, not a trade instruction.
- MA200-unavailable state must never invent a posture metric.
- Trigger distance uses only `breakoutEvidence.trigger` and `close`; no inferred trigger.
- Preserve Radar, proximity filters, watchlist LocalStorage, modal, chart, and retry behavior.
- Do not modify/stage pre-existing dirty backend files.
- No pattern classifier, alerts, account sync, risk-sizing assistant, or skeleton redesign.

---

### Task 1: Add failing source-contract tests

**Files:**
- Modify: `/root/signalix/backend/test_dashboard_responsive.py`

**Interfaces:**
- Tests source markers and executable helper snippets in `dashboard_template.html`.
- Produces regression coverage for `marketPosture`, `triggerDistance`, and explicit empty-state copy.

- [ ] **Step 1: Add tests for posture and trigger contracts**

Add tests that require these exact source-level contracts:

```python
def test_market_posture_contract(self):
    html = self.template
    for marker in (
        'id="marketPosture"',
        "function computeMarketPosture(items)",
        "close > ma200",
        "Favorable",
        "Defensive",
        "MA200 breadth unavailable",
        "id=\"postureMethod\"",
    ):
        self.assertIn(marker, html)


def test_trigger_distance_contract(self):
    html = self.template
    for marker in (
        "function triggerDistance(i)",
        "breakoutEvidence",
        "distance_pct",
        "Trigger",
        "triggerDistance(i)",
    ):
        self.assertIn(marker, html)


def test_empty_states_distinguish_zero_results_from_load_error(self):
    html = self.template
    for marker in (
        'id="emptyReason"',
        'id="radarEmptyReason"',
        "No qualifying setups",
        "โหลดข้อมูลไม่สำเร็จ",
        "ลองใหม่",
    ):
        self.assertIn(marker, html)
```

- [ ] **Step 2: Run the new tests and confirm they fail for missing markers**

Run:

```bash
cd /root/signalix/backend && /root/.venv_img/bin/python -m pytest test_dashboard_responsive.py -k 'market_posture or trigger_distance or empty_states' -q
```

Expected: FAIL because the new IDs/helpers/copy do not yet exist.

---

### Task 2: Implement pure posture and trigger helpers

**Files:**
- Modify: `/root/signalix/backend/dashboard_template.html` near existing JS helpers after `proximityState`

**Interfaces:**
- `computeMarketPosture(items)` returns `{state, constructivePct, ma200Pct, eligibleMa200, reason}`.
- `triggerDistance(i)` returns `{trigger, distance_pct}` or `null`.
- `card(i)` consumes `triggerDistance(i)` and renders one compact `.trigger-distance` line when non-null.

- [ ] **Step 1: Add `computeMarketPosture(items)`**

Implement numeric validation and thresholds exactly:

```javascript
function computeMarketPosture(items){
  const xs=Array.isArray(items)?items:[];
  const total=xs.length||1;
  const constructive=xs.filter(i=>i.stage==="S1_basing"||i.stage==="S2_uptrend").length;
  const constructivePct=constructive/total*100;
  const ma=xs.filter(i=>Number.isFinite(Number(i.close))&&Number.isFinite(Number(i.ma200))&&Number(i.ma200)>0);
  const above=ma.filter(i=>Number(i.close)>Number(i.ma200)).length;
  const ma200Pct=ma.length?above/ma.length*100:null;
  let state="Mixed",reason="MA200 breadth unavailable";
  if(ma.length){
    reason=`Stage breadth ${constructivePct.toFixed(1)}% · MA200 breadth ${ma200Pct.toFixed(1)}%`;
    if(constructivePct>=55&&ma200Pct>=50)state="Favorable";
    else if(constructivePct<40||ma200Pct<35)state="Defensive";
  }
  return {state,constructivePct,ma200Pct,eligibleMa200:ma.length,reason};
}
```

- [ ] **Step 2: Add `triggerDistance(i)`**

Use finite numeric checks and omit invalid evidence:

```javascript
function triggerDistance(i){
  const trigger=Number(i?.breakoutEvidence?.trigger), close=Number(i?.close);
  if(!Number.isFinite(trigger)||trigger<=0||!Number.isFinite(close))return null;
  return {trigger,distance_pct:(close-trigger)/trigger*100};
}
```

- [ ] **Step 3: Render the compact trigger line in `card(i)`**

Insert after the price/basic strip and before optional quality bars:

```javascript
const td=triggerDistance(i);
const triggerLine=td?`<div class="trigger-distance">Trigger ฿${num(td.trigger)} · ${pct(td.distance_pct)}</div>`:"";
```

Then include `${triggerLine}` in the card markup. Do not render a guessed value when evidence is absent.

- [ ] **Step 4: Run the focused tests**

Run the Task 1 pytest selector. Expected: PASS.

---

### Task 3: Add posture presentation and honest empty states

**Files:**
- Modify: `/root/signalix/backend/dashboard_template.html`
- Modify: `/root/signalix/backend/test_dashboard_responsive.py` only if a precise marker needs alignment

**Interfaces:**
- New `#marketPosture` remains in the screener page above `#ctrlSticky`.
- `renderMarketPosture()` renders from `computeMarketPosture(items)`.
- Existing `render()` calls `renderMarketPosture()` without changing filters.

- [ ] **Step 1: Add compact posture markup**

Place immediately before `#ctrlSticky`:

```html
<section id="marketPosture" class="market-posture" aria-label="Market posture">
  <div class="posture-main"><span class="posture-kicker">Market Posture</span><strong id="postureState">Mixed</strong></div>
  <div class="posture-metrics"><span>Stage breadth <b id="postureStagePct">—</b></span><span>Above MA200 <b id="postureMaPct">—</b></span></div>
  <div id="postureMethod" class="posture-method">Context only · not a trade instruction</div>
</section>
```

Add `emptyReason` and `radarEmptyReason` elements inside existing empty containers while retaining reset controls and current IDs.

- [ ] **Step 2: Implement `renderMarketPosture()`**

Render state class and values. For no MA200 eligibility, set `postureMaPct` to `—` and `postureMethod` text to `MA200 breadth unavailable · Stage breadth only is not enough to classify posture`. Otherwise show percentages and methodology. Use `textContent` for data values.

- [ ] **Step 3: Call posture rendering from `render()`**

Call it before rendering results. Keep `renderMarket()` unchanged for its existing Market page output.

- [ ] **Step 4: Improve valid-zero copy without touching load failure UI**

When `vals.length===0`, show `No qualifying setups for the current filters` in `emptyReason`; when Radar list is zero show `No qualifying setups in Radar for this proximity filter` in `radarEmptyReason`. Keep existing error/retry strings untouched.

- [ ] **Step 5: Add compact responsive CSS**

Use the existing variables and wrapping rules. Keep the posture card compact, use state tone classes, and ensure no fixed-width child exceeds the viewport. Preserve `min-height:40px` controls and `overflow-x:hidden` page behavior.

- [ ] **Step 6: Run focused and existing source tests**

Run:

```bash
cd /root/signalix/backend && /root/.venv_img/bin/python -m pytest test_dashboard_responsive.py -q
```

Expected: all responsive/source tests pass.

---

### Task 4: Rebuild generated artifact and run JavaScript checks

**Files:**
- Generated: `/root/signalix/backend/dashboard.html`
- Generated: `/root/signalix/backend/dashboard_snapshot.json` only if rebuild changes it

- [ ] **Step 1: Extract inline script and run syntax check**

Replace template placeholders with current generated values using the repository's existing test/build path, then run `node --check` on the extracted script. Expected: exit 0.

- [ ] **Step 2: Rebuild dashboard artifact**

Use the existing scan-then-build flow from the Signalix dashboard skill. Confirm `dashboard.html` mtime is newer than `dashboard_template.html`.

- [ ] **Step 3: Verify served markers**

Run:

```bash
curl -fsS http://127.0.0.1:3001/dashboard.html -o /tmp/signalix_p0_served.html
python - <<'PY'
from pathlib import Path
s=Path('/tmp/signalix_p0_served.html').read_text()
for x in ('marketPosture','trigger-distance','emptyReason','radarEmptyReason'):
    assert x in s, x
print('served P0 markers PASS')
PY
```

---

### Task 5: Verify real user journeys

**Files:**
- No source changes unless verification finds a concrete defect.

- [ ] **Step 1: Run existing browser acceptance tests**

Run the repository's Playwright acceptance harness against the live dashboard. Record actual pass/fail output and separate environment failures from product failures.

- [ ] **Step 2: Verify desktop and 512px mobile layout**

Use Playwright with viewport widths 1280 and 512. Assert `document.documentElement.scrollWidth <= document.documentElement.clientWidth`, posture visible on screener, trigger line visible on a Radar card with evidence, and zero-result copy appears after a filter produces zero rows.

- [ ] **Step 3: Verify load failure remains an error**

Intercept snapshot/API load and assert the existing Thai error copy plus retry button remain visible; assert the market-condition empty copy is not substituted.

- [ ] **Step 4: Run final focused test suite and inspect diff scope**

Run responsive tests again, `git diff --check`, and `git status --short`. Confirm no unrelated dirty backend files were modified by this task.
