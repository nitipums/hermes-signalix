#!/usr/bin/env python3
"""Weekly authoritative Settrade stock master sync.

Settrade's page is WAF-protected, but its browser page exposes the same JSON
endpoint. We first obtain the page cookies, then call /api/set/stock/list with
Referer/User-Agent headers. Only securityType=S (SET/mai stocks, including IFF)
is imported as Signalix ORD; DR/ETF/DW/futures/options stay out of the ORD master.
The official list is the sole authority: official symbols are auto-reactivated;
symbols absent from it are marked inactive.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2
import requests

PAGE_URL = "https://www.settrade.com/th/get-quote"
API_URL = "https://www.settrade.com/api/set/stock/list"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/151 Safari/537.36"


def parse_stock_master(payload: dict) -> list[dict]:
    """Return current SET/mai common-stock records from Settrade payload."""
    out = []
    for item in payload.get("securitySymbols", []):
        if item.get("securityType") != "S":
            continue
        market = str(item.get("market") or "").upper()
        if market not in {"SET", "MAI"}:
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        out.append({
            "symbol": symbol,
            "market": market,
            "nameTH": item.get("nameTH"),
            "nameEN": item.get("nameEN"),
            "isIFF": bool(item.get("isIFF")),
            "source": "settrade_stock_master",
        })
    return sorted({x["symbol"]: x for x in out}.values(), key=lambda x: x["symbol"])


def fetch_master() -> list[dict]:
    session = requests.Session()
    headers = {"User-Agent": UA, "Referer": PAGE_URL, "Accept": "text/html,application/xhtml+xml"}
    page = session.get(PAGE_URL, headers=headers, timeout=30)
    page.raise_for_status()
    api_headers = {**headers, "Accept": "application/json, text/plain, */*"}
    response = session.get(API_URL, headers=api_headers, timeout=30)
    response.raise_for_status()
    return parse_stock_master(response.json())


def rebuild_dashboard_after_master_sync() -> dict:
    """Refresh persisted dashboard artifacts after the universe changes.

    The weekly master sync runs independently from ``/scan``.  Without this
    step, a symbol can be correctly marked inactive in ``symbol_master`` while
    the already-served static dashboard still contains its old scan card until
    the next scan.  ``build()`` applies the same inactive-symbol gate used by
    the live snapshot, so this is a cheap, deterministic cleanup rather than
    another market scan.
    """
    try:
        import build_dashboard
        info = build_dashboard.build()
        return {"dashboard_rebuilt": True, "dashboard_securities": info.get("securities")}
    except Exception as exc:  # pragma: no cover - exercised by deployment
        # Do not hide a successful authoritative master commit.  Surface the
        # failure in the sync result so the timer/log alerts can catch it.
        return {"dashboard_rebuilt": False, "dashboard_error": repr(exc)[:240]}


def sync_db(records: list[dict], dry_run: bool = False) -> dict:
    symbols = [r["symbol"] for r in records]
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER", "signalix"),
        password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
        dbname=os.getenv("POSTGRES_DB", "signalix"),
    )
    try:
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM symbol_master WHERE instrument_type='ORD' AND status='active'")
        previous_active = {row[0] for row in cur.fetchall()}
        missing = sorted(previous_active - set(symbols))
        if dry_run:
            return {"official": len(symbols), "previous_active": len(previous_active), "would_inactivate": missing}
        now_reason = f"Not present in Settrade stock master ({datetime.now(timezone.utc).date().isoformat()})"
        for record in records:
            cur.execute(
                """INSERT INTO symbol_master
                   (symbol,instrument_type,status,venue,asset_class,currency,timezone,session,source,freshness,marked_at)
                   VALUES (%s,'ORD','active',%s,'equity','THB','Asia/Bangkok','SET',%s,'fresh',NOW())
                   ON CONFLICT(symbol) DO UPDATE SET
                     instrument_type='ORD',
                     status='active',
                     venue=EXCLUDED.venue,
                     asset_class=EXCLUDED.asset_class,currency=EXCLUDED.currency,
                     timezone=EXCLUDED.timezone,session=EXCLUDED.session,
                     source=EXCLUDED.source,freshness=EXCLUDED.freshness,
                     reason=NULL,marked_at=NOW()""",
                (record["symbol"], record["market"], record["source"]),
            )
        if missing:
            cur.execute(
                """UPDATE symbol_master
                   SET status='inactive',reason=%s,marked_at=NOW()
                   WHERE instrument_type='ORD' AND status='active' AND symbol = ANY(%s)""",
                (now_reason, missing),
            )
        conn.commit()
        result = {"official": len(symbols), "previous_active": len(previous_active),
                  "activated_or_refreshed": len(symbols), "inactivated": len(missing),
                  "inactivated_symbols": missing}
        result.update(rebuild_dashboard_after_master_sync())
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    records = fetch_master()
    result = sync_db(records, dry_run=args.dry_run)
    print(json.dumps({"status": "dry_run" if args.dry_run else "synced", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
