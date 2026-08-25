"""Deterministic intraday action overlay for Signalix daily scan states.

Daily scan owns structure (Trend Template, RS, daily RSI/MA/VCP). This module
only uses the latest stored intraday price—including an open candle—to
re-evaluate actionable price levels and persist state transitions.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras

from .scan_history import persist_intraday_events

HERE = Path(__file__).parent
SCAN_JSON = HERE / "scan_results.json"
PG = dict(host=os.getenv("POSTGRES_HOST", "127.0.0.1"), port=int(os.getenv("POSTGRES_PORT", "5432")),
          user=os.getenv("POSTGRES_USER", "signalix"), password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
          dbname=os.getenv("POSTGRES_DB", "signalix"))

INTENT_GROUPS = {
    "active": {"breakout_new", "uptrend_pullback", "waiting_breakout", "base", "down_or_broken"},
    "act_prepare": {"breakout_new", "uptrend_pullback", "waiting_breakout"},
    "monitor": {"base", "down_or_broken"},
}
GROUP_META = {
    "ready_validate": ("opportunity", "Ready to Validate", "positive"),
    "retest_watch": ("opportunity", "Retest Watch", "warning"),
    "pullback_watch": ("prepare", "Pullback Watch", "info"),
    "breakout_watch": ("prepare", "Breakout Watch", "accent"),
    "recovery_watch": ("monitor", "Recovery Watch", "warning"),
    "base_building": ("monitor", "Base Building", "neutral"),
    "avoid": ("risk", "Avoid New Longs", "danger"),
}


def init_schema(pg):
    cur = pg.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS intraday_state (
      symbol TEXT PRIMARY KEY, base_group TEXT NOT NULL, effective_group TEXT NOT NULL,
      action TEXT NOT NULL, action_reason TEXT NOT NULL, price DOUBLE PRECISION,
      interval TEXT NOT NULL, candle_ts TIMESTAMPTZ, evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS intraday_transitions (
      id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, from_group TEXT, to_group TEXT NOT NULL,
      from_action TEXT, to_action TEXT NOT NULL, reason TEXT NOT NULL, price DOUBLE PRECISION,
      interval TEXT NOT NULL, candle_ts TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS intraday_transitions_created_idx ON intraday_transitions(created_at DESC);
    """)
    pg.commit(); cur.close()


def classify(base_group: str, row: dict, price: float | None) -> tuple[str, str, str]:
    """Price-only transition; never recomputes daily structure indicators."""
    readiness = row.get("trade_readiness") or {}
    zones = readiness.get("buy_zones_90d") or {}
    stop = readiness.get("stop_loss") or readiness.get("suggested_stop") or readiness.get("cut_level")
    trigger = readiness.get("breakout_level_20d")
    if price is None:
        return base_group, "WAIT", "No fresh stored intraday price. Daily state retained."
    if base_group in {"breakout_new", "uptrend_pullback", "waiting_breakout", "base", "down_or_broken"}:
        return base_group, "WATCH", "Intraday evidence is informational only; it cannot overwrite the official Daily state."
    try:
        price = float(price); stop = float(stop) if stop is not None else None
        lo, hi = sorted((float(zones["50"]), float(zones["62"]))) if zones.get("50") is not None and zones.get("62") is not None else (None, None)
        trigger = float(trigger) if trigger is not None else None
    except (TypeError, ValueError):
        return base_group, "WAIT", "Invalid reference levels; Daily state retained."
    if stop is not None and price <= stop:
        return "avoid", "INVALIDATED", f"Intraday price {price:g} is at or below invalidation {stop:g}."
    if base_group in {"uptrend_pullback"} and lo is not None and lo <= price <= hi:
        return "ready_validate", "READY TO VALIDATE", f"Intraday price {price:g} is inside the Daily reference entry zone {lo:g}–{hi:g}."
    if base_group in {"waiting_breakout", "breakout_new"} and trigger is not None and price >= trigger:
        return "retest_watch", "BREAKOUT WATCH", f"Intraday price {price:g} is at/above the Daily breakout trigger {trigger:g}; wait for controlled retest."
    if base_group == "uptrend_pullback":
        return "pullback_watch", "WAIT FOR ENTRY ZONE", "Price is outside the reference entry zone; Daily structure remains qualified."
    return base_group, "WATCH", "Daily structure retained; intraday price has not crossed a defined action level."


def _scan_rows(pg, mode):
    """Load the latest canonical Daily scan from PostgreSQL, not legacy JSON."""
    cur = pg.cursor()
    cur.execute("""
        SELECT o.raw_payload
        FROM daily_scan_observations o
        JOIN daily_scan_runs r ON r.id=o.run_id
        WHERE r.id = (
            SELECT latest.id
            FROM daily_scan_runs latest
            WHERE latest.scanner_version='signalix/daily-state-v2'
              AND latest.source_lineage->>'source'='price_data'
              AND COALESCE(latest.source_lineage->>'mode','') <> 'historical_backfill'
            ORDER BY latest.run_timestamp DESC, latest.id DESC
            LIMIT 1
        )
    """)
    rows = []
    for (payload,) in cur.fetchall():
        if not isinstance(payload, dict):
            continue
        group = payload.get("scan_group") or (payload.get("daily_state") or {}).get("group")
        if group in INTENT_GROUPS[mode]:
            rows.append((group, payload))
    cur.close()
    return rows


def _latest_prices(pg, symbols, interval):
    if not symbols: return {}
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT DISTINCT ON (symbol) symbol, close, ts FROM intraday_price_data
                   WHERE symbol=ANY(%s) AND interval=%s ORDER BY symbol, ts DESC""", (symbols, interval))
    out = {r["symbol"]: dict(r) for r in cur.fetchall()}; cur.close(); return out


def evaluate(mode: str, interval: str) -> dict:
    if mode not in INTENT_GROUPS or interval != "60m": raise ValueError("unsupported mode/interval")
    pg = psycopg2.connect(**PG)
    try:
        rows = _scan_rows(pg, mode); symbols = [r["symbol"] for _, r in rows]
        init_schema(pg); prices = _latest_prices(pg, symbols, interval)
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        changed=[]; evaluated=0

        # Track intraday emerging events for persistence
        intraday_events = []

        for base, row in rows:
            sym=row["symbol"]; quote=prices.get(sym); price=float(quote["close"]) if quote else None
            group, action, reason = classify(base,row,price); evaluated += 1
            cur.execute("SELECT effective_group, action FROM intraday_state WHERE symbol=%s", (sym,)); old=cur.fetchone()
            is_change=bool(old and (old["effective_group"] != group or old["action"] != action))
            if is_change:
                cur.execute("""INSERT INTO intraday_transitions(symbol,from_group,to_group,from_action,to_action,reason,price,interval,candle_ts)
                               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (sym,old["effective_group"],group,old["action"],action,reason,price,interval,quote["ts"] if quote else None))
                changed.append({"symbol":sym,"from_group":old["effective_group"],"to_group":group,"from_action":old["action"],"to_action":action,"reason":reason})
            cur.execute("""INSERT INTO intraday_state(symbol,base_group,effective_group,action,action_reason,price,interval,candle_ts,evaluated_at,updated_at)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
                           ON CONFLICT(symbol) DO UPDATE SET base_group=EXCLUDED.base_group,effective_group=EXCLUDED.effective_group,
                           action=EXCLUDED.action,action_reason=EXCLUDED.action_reason,price=EXCLUDED.price,interval=EXCLUDED.interval,
                           candle_ts=EXCLUDED.candle_ts,evaluated_at=NOW(),updated_at=NOW()""",
                        (sym,base,group,action,reason,price,interval,quote["ts"] if quote else None))

            # Detect and persist intraday emerging breakout events
            # When intraday price crosses the daily breakout trigger, create an emerging event
            readiness = row.get("trade_readiness") or {}
            trigger = readiness.get("breakout_level_20d")
            if price is not None and trigger is not None and price >= float(trigger):
                # Intraday price is at/above the daily breakout trigger
                # Create an emerging event if this is a breakout-related group
                if base in {"breakout_new", "waiting_breakout"}:
                    intraday_events.append({
                        "symbol": sym,
                        "origin": "intraday_breakout",
                        "trigger_price": float(trigger),
                        "first_candle_ts": quote["ts"],
                        "interval": interval,
                        "qualification_close": price,
                        "qualification_volume_ratio": readiness.get("volume_ratio_50"),
                        "pre_break_pivot_low": readiness.get("pre_break_pivot_low"),
                        "failure_level": readiness.get("stop_loss") or readiness.get("suggested_stop"),
                        "trend_template_conditions": row.get("trend_template", {}).get("conditions_met"),
                        "rs_rating": row.get("trend_template", {}).get("rs_rating"),
                        "observations": [{
                            "candle_ts": quote["ts"],
                            "stage": group,
                            "close": price,
                            "distance_from_trigger_pct": (price / float(trigger) - 1) if trigger else None,
                            "rsi_daily": readiness.get("rsi_daily"),
                            "volume_ratio_50": readiness.get("volume_ratio_50"),
                            "failure_reason": None,
                            "raw_evidence": {"base_group": base, "action": action, "reason": reason}
                        }]
                    })

        pg.commit(); cur.close()

        # Persist intraday emerging events (append-only).  Attach provenance:
        # the most recent intraday ingestion run id (if any) so the events link
        # back to the candle batch that produced them.
        if intraday_events:
            provenance_run_id = None
            try:
                prov = pg.cursor()
                prov.execute(
                    "SELECT run_id FROM intraday_ingestion_runs "
                    "WHERE status IN ('full_success','partial_success') "
                    "ORDER BY fetch_completed_at DESC NULLS LAST LIMIT 1"
                )
                row = prov.fetchone()
                provenance_run_id = row[0] if row else None
                prov.close()
            except Exception:
                pass
            persist_intraday_events(pg, intraday_events,
                                    intraday_run_id=provenance_run_id,
                                    source_lineage={"source": "intraday_evaluator", "mode": mode})

        return {"mode":mode,"interval":interval,"evaluated":evaluated,"priced":len(prices),"changes":changed}
    finally: pg.close()


def recent_transitions(limit=30):
    pg=psycopg2.connect(**PG)
    try:
        init_schema(pg); cur=pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT symbol,from_group,to_group,from_action,to_action,reason,price,interval,candle_ts,created_at FROM intraday_transitions ORDER BY created_at DESC LIMIT %s", (max(1,min(int(limit),100)),))
        return [dict(r) for r in cur.fetchall()]
    finally: pg.close()


def overlay_map():
    pg=psycopg2.connect(**PG)
    try:
        init_schema(pg); cur=pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT symbol,base_group,effective_group,action,action_reason,price,interval,candle_ts,evaluated_at FROM intraday_state")
        return {r["symbol"]:dict(r) for r in cur.fetchall()}
    finally: pg.close()
