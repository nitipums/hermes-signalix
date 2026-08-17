"""
Signalix — Phase 3 LLM summarization (Nous portal, OpenAI-compatible).

The LLM ONLY summarizes. All deterministic numbers (Trend Template / VCP / RS /
buy zone / stop) are computed in screening.py and passed in verbatim — the LLM
never recomputes them. It receives a compact fact block and writes a short Thai
"why now" note.

Credential handling (privacy + expiry safe):
  We do NOT copy the Nous OAuth token into Signalix .env. Instead we read
  /root/.hermes/shared/nous_auth.json at call time (the Hermes agent's own
  token). The token is cached in-memory for LLM_CACHE_TTL seconds. If it ever
  expires, the caller falls back to the deterministic message (no crash).

Endpoint + model are configurable:
  SIGNALIX_LLM_BASE_URL  (default Nous inference API)
  SIGNALIX_LLM_MODEL     (default upstage/solar-pro4:free — free, Thai-capable,
                          non-reasoning so content is never swallowed by CoT)
  Nous token path:       NOUS_AUTH_JSON (default /root/.hermes/shared/nous_auth.json)
"""
import os
import json
import time
import threading

import requests

BASE_URL = os.getenv(
    "SIGNALIX_LLM_BASE_URL",
    "https://inference-api.nousresearch.com/v1",
)
MODEL = os.getenv("SIGNALIX_LLM_MODEL", "upstage/solar-pro4:free")
NOUS_AUTH_JSON = os.getenv(
    "NOUS_AUTH_JSON", "/root/.hermes/shared/nous_auth.json"
)

LLM_CACHE_TTL = 300  # seconds — re-read token file at most every 5 min

_lock = threading.Lock()
_cached_token = None
_cached_at = 0


def _get_token() -> str:
    """Read the Nous OAuth access token from the Hermes auth file (cached)."""
    global _cached_token, _cached_at
    now = time.time()
    with _lock:
        if _cached_token and (now - _cached_at) < LLM_CACHE_TTL:
            return _cached_token
        try:
            with open(NOUS_AUTH_JSON) as f:
                data = json.load(f)
            tok = data.get("access_token", "")
            if tok:
                _cached_token, _cached_at = tok, now
            return tok
        except Exception as e:
            print(f"  ! LLM: cannot read Nous token from {NOUS_AUTH_JSON}: {repr(e)[:120]}")
            return ""


def _facts_block(result: dict) -> str:
    """Compact deterministic facts for the LLM (numbers come from code, not LLM)."""
    sym = result.get("symbol", "?")
    last = result.get("last_date", "")
    close = result.get("close", "")
    tt = result.get("trend_template", {}) or {}
    vcp = result.get("vcp", {}) or {}
    bz = result.get("buy_zone", {}) or {}
    tr = result.get("trade_readiness", {}) or {}

    met = tt.get("conditions_met", 0)
    rs = tt.get("rs_rating")
    is_vcp = vcp.get("is_vcp")
    vcp_pct = vcp.get("latest_contraction_pct")
    buys = bz.get("buy_zones") or {}
    stop = bz.get("stop_loss")
    readiness = tr.get("status", "-")

    lines = [
        f"SYMBOL={sym} DATE={last} CLOSE={close}",
        f"TREND_TEMPLATE={met}/8 PASS={tt.get('pass')}",
        f"RS_RATING={rs}",
        f"VCP={'yes '+str(vcp_pct)+'%' if is_vcp else 'no'}",
        f"BUY_ZONE={buys}",
        f"STOP={stop}",
        f"READINESS={readiness}",
    ]
    return "\n".join(lines)


def summarize_signal(result: dict) -> str:
    """Return a short Thai summary, or '' if the LLM is unavailable/failed.

    Never raises — a delivery push must not crash on LLM hiccup.
    """
    tok = _get_token()
    if not tok:
        return ""
    facts = _facts_block(result)
    prompt = (
        "คุณคือผู้ช่วยสั้นๆ ภาษาไทยสำหรับนักเทรดแนวโน้ม (Minervini)。\n"
        "ด้านล่างคือข้อมูลที่คำนวณมาแล้วจากโค้ด (ห้ามคำนวณใหม่ ห้ามเปลี่ยนตัวเลข):\n"
        f"{facts}\n\n"
        "เขียนสรุปภาษาไทย 1-2 ประโยค อธิบายว่าทำไมหุ้นตัวนี้ถึงน่าสนใจตอนนี้ "
        "และควรระวังอะไร (รวมโซนซื้อ/จุดตัดถ้ามี)。ไม่ต้องเกริ่นนำ ไม่ต้องลงท้าย。"
    )
    try:
        r = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 220, "temperature": 0.3},
            timeout=45,
        )
        if r.status_code != 200:
            print(f"  ! LLM HTTP {r.status_code}: {r.text[:120]}")
            return ""
        msg = r.json()["choices"][0].get("message", {})
        text = msg.get("content") or ""
        return text.strip()
    except Exception as e:
        print(f"  ! LLM call failed: {repr(e)[:120]}")
        return ""


if __name__ == "__main__":
    import sys
    sample = {
        "symbol": "TRT", "last_date": "2026-08-11", "close": 14.4,
        "trend_template": {"pass": True, "conditions_met": 8, "rs_rating": 99.9},
        "vcp": {"is_vcp": True, "latest_contraction_pct": 21.5},
        "buy_zone": {"buy_zones": {"50": 14.6}, "stop_loss": 13.6},
        "trade_readiness": {"status": "HOLD"},
    }
    out = summarize_signal(sample)
    print("SUMMARY:", out or "(empty — LLM unavailable)")
