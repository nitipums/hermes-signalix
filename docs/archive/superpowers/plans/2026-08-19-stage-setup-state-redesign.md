# Stage + Actionable Setup State (Setup Radar) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old L2 (structural `up_leg/pullback/tight_base/down_leg/bounce` + momentum) as the secondary dashboard axis with a two-layer **setup state** (`setup_quality` gate + `setup_proximity` timing) on S1/S2, and add a **Setup Radar** section that surfaces quality-passed stocks near/at their entry trigger.

**Architecture:** Pure-function module `backend/setup_state.py` computes quality + proximity from existing evidence (readiness/trend fields already produced by the scanner — no new data fetches). `group_scan_results` attaches the result into `daily_state` so every serialization path inherits it; `build_dashboard.serialize` exposes the fields on each item; `dashboard_template.html` swaps L2 pills for proximity pills and renders the Setup Radar section client-side.

**Tech Stack:** Python 3.12 (pandas, psycopg2, fastapi, uvicorn), vanilla JS template `dashboard_template.html`, Docker compose (backend :8000, dashboard :3001), pytest.

**Spec:** `docs/superpowers/specs/2026-08-19-stage-setup-state-redesign-design.md`

## Global Constraints

- **No scoring / composite** this round (Arm decision 2026-08-19). No `setup_score`, `compositeScore`, weighted ranking.
- Fields stay **separate**: `setup_quality` and `setup_proximity` are distinct dicts per item — never a merged string.
- **S3/S4 have no actionable proximity**: `setup_proximity.state = None` (not "forming").
- Every S1/S2 item gets BOTH fields (even quality=fail / proximity=forming). Never omit.
- Legacy `layer2_structural` / `layer2_momentum` / `layer2_group` stay in the payload for backward compat but **the UI must stop using them as the grouping/filter axis**.
- All numerics returned to JSON must be plain `float`/`int`/`None` (numpy scalars raise `TypeError` at the API boundary — cast with `float(...)`).
- Do not touch docker/deploy automatically; run tests in host venv with `POSTGRES_HOST=127.0.0.1` (postgres publishes `127.0.0.1:5432`, password `signalix_pass`).
- Thresholds are Bee-gate v1 (adjustable later): `SETUP_PROXIMITY_PCT=0.05`, `EXTENDED_FROM_TRIGGER_PCT=0.08`, `EXTENDED_RSI=75`, `TIGHT_RANGE_20D_PCT=12.0`, `VOL_CONTRACTION_RATIO=1.0`.

---

### Task 1: `backend/setup_state.py` — pure quality + proximity computation

**Files:**
- Create: `backend/setup_state.py`
- Test: `backend/test_setup_state.py`

**Interfaces:**
- Consumes: nothing (self-contained). Evidence keys produced by `screening.group_scan_results` (see Task 2): `close`, `rolling_trigger` (S1 pivot = `breakout_level_20d`), `buy_zones_90d`, `swing_high_90d`, `range_20d_pct`, `volume_ratio_50`, `rsi_daily`.
- Produces:
  - `compute_setup_quality(evidence: dict) -> dict` → `{"pass": bool, "reasons": list[str], "range_20d_pct": float|None, "vol_ratio_50": float|None}`
  - `compute_setup_proximity(stage: str, evidence: dict) -> dict` → `{"state": str|None, "pivot": float|None, "distance_pct": float|None, "zone": {"lo": float|None, "hi": float|None}|None}`
  - `compute_setup_state(stage: str, evidence: dict) -> dict` → `{"quality": {...}, "proximity": {...}}`

- [ ] **Step 1: Write the failing tests**

`backend/test_setup_state.py`:

```python
"""Setup state (quality gate + proximity) tests — Task 1 of stage-setup-state redesign."""
import pytest
from setup_state import (
    compute_setup_quality,
    compute_setup_proximity,
    compute_setup_state,
    SETUP_PROXIMITY_PCT,
    EXTENDED_FROM_TRIGGER_PCT,
    EXTENDED_RSI,
    TIGHT_RANGE_20D_PCT,
)


def _ev(close=50.0, stage="S1_basing", pivot=52.0, rsi=60.0, range20=8.0,
        vol_ratio=0.6, buy_zones=None, swing_high=None):
    e = {"close": close, "rolling_trigger": pivot, "rsi_daily": rsi,
         "range_20d_pct": range20, "volume_ratio_50": vol_ratio,
         "buy_zones_90d": buy_zones, "swing_high_90d": swing_high}
    return e


def test_quality_pass_all_criteria():
    q = compute_setup_quality(_ev())
    assert q["pass"] is True
    assert "tight_range" in q["reasons"]
    assert "vol_contraction" in q["reasons"]
    assert "not_extended" in q["reasons"]


def test_quality_fail_wide_range():
    q = compute_setup_quality(_ev(range20=25.0))
    assert q["pass"] is False
    assert "range_too_wide" in q["reasons"]


def test_quality_fail_expanding_volume():
    q = compute_setup_quality(_ev(vol_ratio=2.5))
    assert q["pass"] is False
    assert "vol_expanding" in q["reasons"]


def test_quality_fail_extended():
    q = compute_setup_quality(_ev(close=60.0, pivot=52.0))  # +15% above pivot
    assert q["pass"] is False
    assert "extended" in q["reasons"]


def test_quality_fail_overbought_rsi():
    q = compute_setup_quality(_ev(rsi=80.0))
    assert q["pass"] is False
    assert "extended" in q["reasons"]


def test_s1_near_trigger():
    # close 49.8 vs pivot 52.0 => -4.2% => within 5% proximity
    p = compute_setup_proximity("S1_basing", _ev(close=49.8, pivot=52.0))
    assert p["state"] == "near_trigger"
    assert p["pivot"] == 52.0
    assert p["distance_pct"] is not None


def test_s1_action_breakout():
    p = compute_setup_proximity("S1_basing", _ev(close=52.5, pivot=52.0))
    assert p["state"] == "action"


def test_s1_extended():
    p = compute_setup_proximity("S1_basing", _ev(close=57.0, pivot=52.0))  # +9.6%
    assert p["state"] == "extended"


def test_s1_forming():
    p = compute_setup_proximity("S1_basing", _ev(close=45.0, pivot=52.0))  # -13%
    assert p["state"] == "forming"


def test_s1_no_pivot_is_forming():
    p = compute_setup_proximity("S1_basing", _ev(pivot=None))
    assert p["state"] == "forming"
    assert p["pivot"] is None


def test_s2_action_in_zone():
    # buy_zones_90d {"50": 54.0, "62": 50.0} -> zone lo 50.0 hi 54.0
    e = _ev(stage="S2_uptrend", close=52.0, buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0)
    p = compute_setup_proximity("S2_uptrend", e)
    assert p["state"] == "action"
    assert p["zone"] == {"lo": 50.0, "hi": 54.0}


def test_s2_near_trigger_above_zone():
    e = _ev(stage="S2_uptrend", close=55.5, buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0)
    p = compute_setup_proximity("S2_uptrend", e)
    assert p["state"] == "near_trigger"


def test_s2_forming_below_zone():
    e = _ev(stage="S2_uptrend", close=47.0, buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0)
    p = compute_setup_proximity("S2_uptrend", e)
    assert p["state"] == "forming"


def test_s2_extended_rsi():
    e = _ev(stage="S2_uptrend", close=52.0, rsi=78.0, buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0)
    p = compute_setup_proximity("S2_uptrend", e)
    assert p["state"] == "extended"


def test_s2_extended_beyond_leg_high():
    e = _ev(stage="S2_uptrend", close=66.0, buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0)
    p = compute_setup_proximity("S2_uptrend", e)
    assert p["state"] == "extended"


def test_s3_s4_proximity_null():
    assert compute_setup_proximity("S3_distributing", _ev())["state"] is None
    assert compute_setup_proximity("S4_down", _ev())["state"] is None


def test_compute_setup_state_bundle():
    out = compute_setup_state("S1_basing", _ev())
    assert out["quality"]["pass"] is True
    assert out["proximity"]["state"] in ("near_trigger", "action", "forming", "extended")


def test_all_outputs_json_safe():
    import json
    out = compute_setup_state("S2_uptrend", _ev(stage="S2_uptrend", close=52.0,
                                                buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0))
    json.dumps(out)  # must not raise (no numpy scalars)
```

- [ ] **Step 2: Run tests to verify they fail**

Run (host venv):
```bash
cd /root/signalix/backend && POSTGRES_HOST=127.0.0.1 ../.venv/bin/python -m pytest test_setup_state.py -v 2>&1 | tail -20
```
Expected: FAIL with `ModuleNotFoundError: No module named 'setup_state'` (or import errors). Tests must fail because the module does not exist.

- [ ] **Step 3: Write the minimal implementation**

`backend/setup_state.py`:

```python
"""Two-layer actionable setup state for S1/S2 (Stage + Setup State redesign 2026-08-19).

setup_quality  -> VCP/tightness gate (pass/fail)  [Arm decision D2]
setup_proximity-> entry timing: forming / near_trigger / action / extended  [D3]
S3/S4 have NO actionable proximity (state = None)  [D5]
All outputs are JSON-safe plain floats/None (numpy scalars break json.dumps).
"""
from __future__ import annotations

# Bee-gate v1 thresholds (adjustable).
SETUP_PROXIMITY_PCT = 0.05          # near_trigger within 5% of pivot/zone-top
EXTENDED_FROM_TRIGGER_PCT = 0.08    # extended if >8% beyond pivot
EXTENDED_RSI = 75.0
TIGHT_RANGE_20D_PCT = 12.0
VOL_CONTRACTION_RATIO = 1.0         # volume_ratio_50 < 1.0 => recent vol contracting

PROXIMITY_STATES = ("forming", "near_trigger", "action", "extended")
ACTIONABLE_STAGES = ("S1_basing", "S2_uptrend")


def _f(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_setup_quality(evidence: dict) -> dict:
    """VCP/tightness gate. pass = tight range + vol contraction + not extended."""
    range20 = _f(evidence.get("range_20d_pct"))
    vol_ratio = _f(evidence.get("volume_ratio_50"))
    rsi = _f(evidence.get("rsi_daily"))
    close = _f(evidence.get("close"))
    pivot = _f(evidence.get("rolling_trigger"))
    reasons = []

    if range20 is not None and range20 <= TIGHT_RANGE_20D_PCT:
        reasons.append("tight_range")
    else:
        reasons.append("range_too_wide")

    if vol_ratio is not None and vol_ratio < VOL_CONTRACTION_RATIO:
        reasons.append("vol_contraction")
    else:
        reasons.append("vol_expanding")

    extended = False
    if rsi is not None and rsi >= EXTENDED_RSI:
        extended = True
    if pivot and pivot > 0 and close and close / pivot - 1 > EXTENDED_FROM_TRIGGER_PCT:
        extended = True
    reasons.append("not_extended" if not extended else "extended")

    return {
        "pass": all(r not in ("range_too_wide", "vol_expanding", "extended") for r in reasons),
        "reasons": reasons,
        "range_20d_pct": range20,
        "vol_ratio_50": vol_ratio,
    }


def compute_setup_proximity(stage: str, evidence: dict) -> dict:
    """Entry timing per stage. S3/S4 => state None (risk buckets, not actionable)."""
    if stage not in ACTIONABLE_STAGES:
        return {"state": None, "pivot": None, "distance_pct": None, "zone": None}

    close = _f(evidence.get("close"))
    rsi = _f(evidence.get("rsi_daily"))
    empty = {"state": "forming", "pivot": None, "distance_pct": None, "zone": None}

    if stage == "S1_basing":
        pivot = _f(evidence.get("rolling_trigger"))
        if not pivot or pivot <= 0:
            return empty
        dist = (close / pivot - 1) if close else None
        if rsi is not None and rsi >= EXTENDED_RSI:
            state = "extended"
        elif dist is not None and dist > EXTENDED_FROM_TRIGGER_PCT:
            state = "extended"
        elif dist is not None and dist > 0:
            state = "action"
        elif dist is not None and dist >= -SETUP_PROXIMITY_PCT:
            state = "near_trigger"
        else:
            state = "forming"
        return {"state": state, "pivot": pivot,
                "distance_pct": round(dist, 4) if dist is not None else None,
                "zone": None}

    # S2_uptrend
    bz = evidence.get("buy_zones_90d") or {}
    fibs = sorted(float(v) for v in bz.values() if v is not None)
    if len(fibs) < 2:
        return empty
    zone = {"lo": fibs[0], "hi": fibs[-1]}
    swing_high = _f(evidence.get("swing_high_90d"))
    dist = (close / zone["hi"] - 1) if close else None
    if rsi is not None and rsi >= EXTENDED_RSI:
        state = "extended"
    elif swing_high and close and close > swing_high * (1 + EXTENDED_FROM_TRIGGER_PCT):
        state = "extended"
    elif close and zone["lo"] <= close <= zone["hi"]:
        state = "action"
    elif dist is not None and 0 < dist <= SETUP_PROXIMITY_PCT:
        state = "near_trigger"   # above zone top, approaching (<=5% away)
    else:
        state = "forming"
    return {"state": state, "pivot": swing_high,
            "distance_pct": round(dist, 4) if dist is not None else None,
            "zone": zone}


def compute_setup_state(stage: str, evidence: dict) -> dict:
    return {
        "quality": compute_setup_quality(evidence),
        "proximity": compute_setup_proximity(stage, evidence),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /root/signalix/backend && POSTGRES_HOST=127.0.0.1 ../.venv/bin/python -m pytest test_setup_state.py -v 2>&1 | tail -25
```
Expected: all tests PASS (no DB access needed — pure functions).

- [ ] **Step 5: Commit**

```bash
cd /root/signalix && git add backend/setup_state.py backend/test_setup_state.py && git commit -m "feat: two-layer setup state (quality gate + proximity) for S1/S2"
```

---

### Task 2: Wire setup state into `screening.group_scan_results`

**Files:**
- Modify: `backend/screening.py` — evidence dict (~line 420-445) and after `classify_stage` (~line 447)
- Test: `backend/test_setup_state.py` (append integration tests)

**Interfaces:**
- Consumes: `compute_setup_state(stage, evidence)` from Task 1.
- Produces: every scanned row's `daily_state` gains `setup_quality` + `setup_proximity` dicts (all stages; S3/S4 proximity.state = None). Downstream `serialize()` reads them from `row["daily_state"]` (Task 3).

- [ ] **Step 1: Extend the evidence dict + attach setup state**

In `backend/screening.py`, inside `group_scan_results`:

1. Add two keys to the `evidence` dict (after the existing `"vcp": vcp,` line):

```python
            "buy_zones_90d": readiness.get("buy_zones_90d"),
            "swing_high_90d": readiness.get("swing_high_90d"),
```

2. After `state = classify_stage(evidence, events.get(row["symbol"]))` add:

```python
        # Two-layer actionable setup state (quality gate + proximity timing).
        # Attached at source so every serialization path (build/snapshot) inherits it.
        from setup_state import compute_setup_state
        state["setup_quality"] = compute_setup_state(stage, evidence)["quality"]
        state["setup_proximity"] = compute_setup_state(stage, evidence)["proximity"]
```

(Import at module top instead of inside the loop if preferred — either is fine; the top-level `from setup_state import compute_setup_state` is cleaner. Verify no circular import: `setup_state` imports nothing from `screening`, so top-level import is safe.)

- [ ] **Step 2: Write integration tests (append to `backend/test_setup_state.py`)**

```python
# --- Integration: group_scan_results attaches setup state ---
def _row(close=50.0, stage_hint=None):
    return {
        "symbol": "TEST",
        "close": close,
        "last_date": "2026-08-19",
        "trend_template": {
            "ma": {"ma50": 49.0, "ma150": 45.0, "ma200": 40.0},
            "conditions_met": 8, "rs_rating": 80.0, "rs_threshold": 70.0,
        },
        "trade_readiness": {
            "above_ma50": True, "above_ma150": True, "above_ma200": True,
            "ma50_slope_20d_pct": 1.5, "ma150_slope_20d_pct": 1.0, "ma200_slope_20d_pct": 0.8,
            "rsi_daily": 60.0, "macd": 0.1, "volume_ratio_50": 0.6,
            "breakout_level_20d": 52.0, "range_20d_pct": 8.0, "status": "BUY",
            "buy_zones_90d": {"50": 54.0, "62": 50.0}, "swing_high_90d": 60.0,
        },
        "vcp": {"is_vcp": True},
        "trend_source": "daily",
    }


def test_group_scan_attaches_setup_fields(monkeypatch):
    from screening import group_scan_results
    rows = [_row(close=51.5)]  # S2 uptrend, near_trigger
    groups = group_scan_results(rows, events={})
    flat = [r for values in groups.values() for r in values]
    assert len(flat) == 1
    ds = flat[0]["daily_state"]
    assert "setup_quality" in ds and "setup_proximity" in ds
    assert ds["setup_quality"]["pass"] is True
    assert ds["setup_proximity"]["state"] in ("near_trigger", "action", "forming", "extended")


def test_group_scan_s4_proximity_null(monkeypatch):
    from screening import group_scan_results
    row = _row(close=30.0)
    row["trade_readiness"].update({"above_ma50": False, "above_ma150": False, "above_ma200": False,
                                   "ma200_slope_20d_pct": -1.5})
    groups = group_scan_results([row], events={})
    flat = [r for values in groups.values() for r in values]
    ds = flat[0]["daily_state"]
    assert ds["stage"] == "S4_down"
    assert ds["setup_proximity"]["state"] is None
    assert ds["setup_quality"]["pass"] is False  # quality still computed (never omitted)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /root/signalix/backend && POSTGRES_HOST=127.0.0.1 ../.venv/bin/python -m pytest test_setup_state.py -v 2>&1 | tail -15
```
Expected: the two new integration tests FAIL (`KeyError: 'setup_quality'`) while Task 1 tests still pass.

- [ ] **Step 4: Implement the wiring (the edit from Step 1)**

Apply the evidence keys + attach block. Then run the full file:

```bash
cd /root/signalix/backend && POSTGRES_HOST=127.0.0.1 ../.venv/bin/python -m pytest test_setup_state.py -v 2>&1 | tail -15
```
Expected: ALL pass.

- [ ] **Step 5: Run the stage classifier regression**

```bash
cd /root/signalix/backend && POSTGRES_HOST=127.0.0.1 ../.venv/bin/python -m pytest test_stage_classifier.py test_action_dashboard.py -q 2>&1 | tail -8
```
Expected: all pass (stage/phase logic untouched).

- [ ] **Step 6: Commit**

```bash
cd /root/signalix && git add backend/screening.py backend/test_setup_state.py && git commit -m "feat: attach setup quality/proximity to daily_state in scan"
```

---

### Task 3: Expose fields + sort in `build_dashboard.py`

**Files:**
- Modify: `backend/build_dashboard.py` — `serialize()` (~line 638-760) and `dashboard_sort_key` (~line 815-834)
- Test: `backend/test_compact_cards.py` (append assertions)

**Interfaces:**
- Consumes: `row["daily_state"]["setup_quality"]` / `["setup_proximity"]` (Task 2).
- Produces per item: `setup_quality` (dict), `setup_proximity` (dict), `radar` (bool), `radarBadge` (`"READY"` | `"WATCH"` | None). Sort key = stage → proximity (action > near_trigger > forming > extended) → rs DESC.

- [ ] **Step 1: Write the failing tests**

Append to `backend/test_compact_cards.py`:

```python
def test_item_exposes_setup_state_and_radar():
    from build_dashboard import serialize
    row = {
        "symbol": "TEST", "close": 51.5, "last_date": "2026-08-19",
        "trend_template": {"ma": {"ma200": 40.0}, "conditions_met": 8,
                           "rs_rating": 80.0, "rs_threshold": 70.0},
        "trade_readiness": {"status": "BUY", "buy_zones_90d": {"50": 54.0, "62": 50.0},
                            "swing_high_90d": 60.0, "rsi_daily": 60.0,
                            "volume_ratio_50": 0.6, "range_20d_pct": 8.0,
                            "breakout_level_20d": 52.0},
        "daily_state": {
            "stage": "S2_uptrend", "phase": "uptrend_pullback",
            "setup_quality": {"pass": True, "reasons": ["tight_range"], "range_20d_pct": 8.0, "vol_ratio_50": 0.6},
            "setup_proximity": {"state": "near_trigger", "pivot": 60.0, "distance_pct": 0.02,
                                "zone": {"lo": 50.0, "hi": 54.0}},
        },
    }
    item = serialize("uptrend_pullback", row, {})
    assert item["setup_quality"]["pass"] is True
    assert item["setup_proximity"]["state"] == "near_trigger"
    assert item["radar"] is True
    assert item["radarBadge"] == "WATCH"


def test_item_s3_radar_false():
    from build_dashboard import serialize
    row = {
        "symbol": "TEST", "close": 30.0, "last_date": "2026-08-19",
        "trend_template": {"ma": {"ma200": 40.0}, "conditions_met": 3,
                           "rs_rating": 20.0, "rs_threshold": 70.0},
        "trade_readiness": {"status": "WAIT"},
        "daily_state": {
            "stage": "S3_distributing", "phase": "topping",
            "setup_quality": {"pass": False, "reasons": ["range_too_wide"], "range_20d_pct": 30.0, "vol_ratio_50": 1.5},
            "setup_proximity": {"state": None, "pivot": None, "distance_pct": None, "zone": None},
        },
    }
    item = serialize("down_or_broken", row, {})
    assert item["radar"] is False
    assert item["radarBadge"] is None


def test_dashboard_sort_proximity_before_rs():
    from build_dashboard import dashboard_sort_key
    mk = lambda prox, rs: {"stage": "S2_uptrend", "setup_proximity": {"state": prox}, "rs": rs}
    a = dashboard_sort_key(mk("near_trigger", 90))
    b = dashboard_sort_key(mk("action", 60))
    c = dashboard_sort_key(mk("forming", 99))
    assert b < a < c  # action first, then near_trigger, then forming (rs is last tiebreak)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /root/signalix/backend && POSTGRES_HOST=127.0.0.1 ../.venv/bin/python -m pytest test_compact_cards.py -q 2>&1 | tail -10
```
Expected: new tests FAIL (`KeyError: 'setup_quality'`), existing pass.

- [ ] **Step 3: Implement serialize() additions**

In `backend/build_dashboard.py`, inside `serialize()`, after the `daily_state = row.get("daily_state") or {}` / `stage` / `phase` block (line ~638-640), add:

```python
    setup_q = daily_state.get("setup_quality") or {}
    setup_p = daily_state.get("setup_proximity") or {}
    radar_state = setup_p.get("state")
    radar = bool(setup_q.get("pass") and radar_state in ("near_trigger", "action"))
    radar_badge = ("READY" if radar_state == "action"
                   else "WATCH" if radar_state == "near_trigger" else None)
```

And in the return dict (near the other state fields, e.g. after the `"phase_label"` / `"stage_phase"` entries around line 761), add:

```python
        "setup_quality": setup_q,
        "setup_proximity": setup_p,
        "radar": radar,
        "radarBadge": radar_badge,
```

- [ ] **Step 4: Implement dashboard_sort_key replacement**

Replace the current `dashboard_sort_key` body (structural/momentum priorities ~line 826-834) with:

```python
def dashboard_sort_key(item):
    """Stage-first; within stage, actionable proximity first; rs last tiebreak."""
    stage_order = {"S2_uptrend": 0, "S1_basing": 1, "S3_distributing": 2, "S4_down": 3}
    proximity_order = {"action": 0, "near_trigger": 1, "forming": 2, "extended": 3}
    proximity = (item.get("setup_proximity") or {}).get("state")
    rs = item.get("rs") or 0
    return (stage_order.get(item.get("stage"), 99),
            proximity_order.get(proximity, 5),
            -rs)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /root/signalix/backend && POSTGRES_HOST=127.0.0.1 ../.venv/bin/python -m pytest test_compact_cards.py test_independence_expansion.py -q 2>&1 | tail -10
```
Expected: all pass (including pre-existing L2-field assertions — legacy fields still serialized).

- [ ] **Step 6: Commit**

```bash
cd /root/signalix && git add backend/build_dashboard.py backend/test_compact_cards.py && git commit -m "feat: expose setup state + radar flags; stage->proximity->rs sort"
```

---

### Task 4: UI — Setup Radar section + proximity pills (replace L2 pills)

**Files:**
- Modify: `backend/dashboard_template.html`

**Interfaces:**
- Consumes: per-item `setup_quality.pass`, `setup_proximity.state`, `radar`, `radarBadge` (Task 3).
- Produces: Setup Radar section at top of results; per-stage proximity pills (All / action / near_trigger / forming / extended); card chips show proximity state (READY/WATCH badge); L2 structural+momentum pills and their filter logic removed from the UI.

- [ ] **Step 1: Add proximity filter state + helpers (line ~226-231)**

Replace:

```js
let indep={set50:false,value:0,band:"all",sector:"all",industry:"all"}, l2Filter={}, l2MomFilter={};
const structuralGroup=i=>i.layer2_structural?.group??i.layer2_group;
const normalizeMomentumGroup=v=>({ob:"overbought",os:"oversold",neu:"neutral"}[v]||v);
// Legacy snapshots have layer2_group for structure only. Never use it as momentum.
const momentumGroup=i=>normalizeMomentumGroup(i.layer2_momentum?.group??i.layer2_momentum_group??i.momentum_group??i.layer2_signals?.momentum);
```

with:

```js
let indep={set50:false,value:0,band:"all",sector:"all",industry:"all"}, proxFilter={};
const PROX_GROUPS=["action","near_trigger","forming","extended"];
const PROX_LABEL={action:"Ready",near_trigger:"Near",forming:"Forming",extended:"Extended"};
const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null;
const inRadar=i=>!!i.radar;
```

- [ ] **Step 2: Update `current()` filter (line ~285-288)**

Replace:

```js
    const lf=l2Filter[i.stage];
    if(lf&&lf!=="all"&&structuralGroup(i)!==lf)return false;
    const lmf=l2MomFilter[i.stage];
    if(lmf&&lmf!=="all"&&momentumGroup(i)!==lmf)return false;
```

with:

```js
    const pf=proxFilter[i.stage];
    if(pf&&pf!=="all"&&proximityState(i)!==pf)return false;
```

- [ ] **Step 3: Update card() chip (line ~254)**

Replace:

```js
      ${structuralGroup(i)?`<span class="phase-tag" style="color:var(--slate)">L2: ${esc(l2)}</span>`:""}
```

with:

```js
      ${proximityState(i)?`<span class="phase-tag" style="color:var(--slate)">${esc(PROX_LABEL[proximityState(i)]||proximityState(i))}</span>`:""}
      ${i.radarBadge?`<span class="chip" style="background:${i.radarBadge==="READY"?"var(--green)":"var(--amber)"}22;color:${i.radarBadge==="READY"?"var(--green)":"var(--amber)"};border-color:${i.radarBadge==="READY"?"var(--green)":"var(--amber)"};font-size:10px;padding:2px 8px;margin-left:6px">${i.radarBadge}</span>`:""}
```

(Remove the now-unused `const l2=STAGE_L2_LABEL[structuralGroup(i)]||structuralGroup(i);` line at ~244.)

- [ ] **Step 4: Replace per-stage pills + add Setup Radar section (lines ~306-327)**

Replace the section-rendering block (`results.innerHTML=STAGE_ORDER.map(...)` through the `.join("")`) with:

```js
  const vals=current();
  const results=document.getElementById("results");
  const radar=vals.filter(inRadar);
  const radarHTML=radar.length?`<section class="stage-section radar-section"><div class="stage-head radar">
    <h2>Setup Radar</h2><span class="badge">${radar.length}</span>
    <span class="desc">คุณภาพผ่าน + ใกล้/ถึงจุดเข้า</span></div>
    <div class="cards">${radar.map(card).join("")}</div></section>`:"";
  results.innerHTML=radarHTML+STAGE_ORDER.map(s=>{
    if(stageFilter!=="all"&&stageFilter!==s)return "";
    const list=vals.filter(i=>i.stage===s);
    if(!list.length)return "";
    const m=stageMeta[s]||{count:list.length};
    const counts={}; PROX_GROUPS.forEach(g=>counts[g]=list.filter(i=>proximityState(i)===g).length);
    const subpills=PROX_GROUPS.map(g=>`<button class="chip l2sub ${proxFilter[s]===g?"active":""}" data-stage="${s}" data-prox="${g}">${PROX_LABEL[g]} <b>${counts[g]}</b></button>`).join("");
    const proxEmpty=proxFilter[s]&&proxFilter[s]!=="all"&&!list.some(i=>proximityState(i)===proxFilter[s]);
    return `<section class="stage-section"><div class="stage-head ${s.split("_")[0]}">
      <h2>${esc(STAGE_LABEL[s])}</h2><span class="badge">${list.length}</span>
      <span class="desc">${esc(STAGE_DESC[s])}</span></div>
      <div class="l2-bar">${subpills}<button class="chip l2sub ${!proxFilter[s]?"active":""}" data-stage="${s}" data-prox="all">All <b>${list.length}</b></button></div>
      <div class="cards">${list.map(card).join("")}</div>${proxEmpty?`<div class="l2-empty">No symbols in this subgroup</div>`:""}</section>`;
  }).join("");
```

- [ ] **Step 5: Update the pill click handler (line ~543-544)**

Replace:

```js
  const l2=e.target.closest(".l2sub"); if(l2){const st=l2.dataset.stage,g=l2.dataset.l2; l2Filter[st]=(l2Filter[st]===g?undefined:g); render();}
  const l2mom=e.target.closest(".l2mom"); if(l2mom){const st=l2mom.dataset.stage,g=l2mom.dataset.l2mom; l2MomFilter[st]=(l2MomFilter[st]===g?undefined:g); render();}
```

with:

```js
  const l2=e.target.closest(".l2sub"); if(l2){const st=l2.dataset.stage,g=l2.dataset.prox; proxFilter[st]=(proxFilter[st]===g?undefined:g); render();}
```

- [ ] **Step 6: Verify no L2 references remain in the UI**

```bash
cd /root/signalix && grep -n "l2Filter\|l2MomFilter\|structuralGroup\|momentumGroup\|data-l2\b\|L2GROUPS\|L2MOM_GROUPS\|l2-momentum-bar" backend/dashboard_template.html
```
Expected: no output (all removed). The legacy payload fields (`layer2_structural` etc.) may still appear in data JSON, but no UI code references them.

- [ ] **Step 7: Build the dashboard to smoke-test the template**

```bash
cd /root/signalix/backend && POSTGRES_HOST=127.0.0.1 ../.venv/bin/python -c "
from build_dashboard import build
# Standalone rebuild reads scan_results.json; template placeholders must be replaced.
out = build()
print(out['securities'], out['out'])
"
```
Expected: prints security count and `.../dashboard.html` path without exceptions (template renders).

- [ ] **Step 8: Commit**

```bash
cd /root/signalix && git add backend/dashboard_template.html && git commit -m "feat: UI Setup Radar section + proximity pills, drop L2 pills"
```

---

### Task 5: End-to-end verification (Bee gate) + deploy

**Files:** none (verification only).

- [ ] **Step 1: Full test suite (host venv)**

```bash
cd /root/signalix/backend && POSTGRES_HOST=127.0.0.1 ../.venv/bin/python -m pytest -q 2>&1 | tail -8
```
Expected: all green (existing stage/action/dashboard/scan-history tests + new setup-state tests).

- [ ] **Step 2: Rebuild backend + dashboard containers**

```bash
cd /root/signalix && docker compose up -d --force-recreate backend dashboard 2>&1 | tail -5
```

- [ ] **Step 3: Trigger a real scan + verify snapshot contract**

```bash
curl -s -X POST http://127.0.0.1:8000/scan -H 'Content-Type: application/json' -d '{}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('securities:', d.get('securities'), 'groups:', d.get('groups'))"
curl -s http://127.0.0.1:8000/dashboard/snapshot -o /tmp/snap.json && python3 - <<'EOF'
import json
d = json.load(open('/tmp/snap.json'))
items = d.get('items', [])
missing_q = [i['symbol'] for i in items if 'setup_quality' not in i]
missing_p = [i['symbol'] for i in items if 'setup_proximity' not in i]
s34 = [i for i in items if i.get('stage') in ('S3_distributing','S4_down') and (i.get('setup_proximity') or {}).get('state') is not None]
radar = [i for i in items if i.get('radar')]
print('items:', len(items), 'missing_quality:', len(missing_q), 'missing_proximity:', len(missing_p), 's3s4_with_state:', len(s34))
print('radar_count:', len(radar), 'radar_example:', radar[0]['symbol'] if radar else '-', radar[0]['radarBadge'] if radar else '-')
EOF
```
Expected: `missing_quality=0`, `missing_proximity=0`, `s3s4_with_state=0`, radar_count > 0 with valid badges.

- [ ] **Step 4: Served UI check (curl the built dashboard for Radar + pills)**

```bash
curl -s http://127.0.0.1:3001/ -o /tmp/dash.html
grep -c "Setup Radar" /tmp/dash.html
grep -c 'data-prox' /tmp/dash.html
grep -c 'l2Filter\|l2MomFilter' /tmp/dash.html || echo "no legacy L2 UI refs"
```
Expected: `Setup Radar` present, `data-prox` present, no `l2Filter`/`l2MomFilter` in served HTML.

- [ ] **Step 5: Browser journey (happy path + filter)**

Use browser_exec to load `http://127.0.0.1:3001/`:
1. Wait for page load; assert "Setup Radar" heading + badge count > 0.
2. Click a card in the Radar section → modal opens (`.modal-bg.open`), chart canvas renders.
3. Click a proximity pill (e.g. `action`) in a stage section → only matching cards remain.
4. Confirm S3/S4 sections have NO proximity chip on cards (`state` is None).
Capture a screenshot of the Radar section for the record.

- [ ] **Step 6: Update INDEX + final report**

- Update `/root/signalix/vault/INDEX.md` (stage-setup-state entry) and the Kanban board (`~/.hermes/kanban/boards/signalix/kanban.db` via `env -u HERMES_DELEGATED_CHILD_CONTEXT hermes kanban`) — move tasks to DONE with verified evidence.
- Report to Arm: working/blocked/not-yet-verified split (evidence-first per his preference), PASS/FAIL per check.

- [ ] **Step 7: Final commit (if any residual template/docs change)**

```bash
cd /root/signalix && git add -A && git commit -m "docs: setup radar verification evidence" 2>&1 | tail -2
```
