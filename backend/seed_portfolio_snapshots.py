"""Seed owner Investment Co-pilot MVP from Arm's broker screenshots.

The source is user-supplied screenshots in the Signalix Discord thread. These are
observation snapshots, not broker-confirmed ledger transactions.
"""
import datetime as dt
import os

import psycopg2

from portfolio import init_portfolio_schema, persist_manual_snapshot

PG = dict(
    host=os.getenv("POSTGRES_HOST", "postgres"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    user=os.getenv("POSTGRES_USER", "signalix"),
    password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
    dbname=os.getenv("POSTGRES_DB", "signalix"),
)
OWNER_CHAT = "7295704669"
AS_OF = "2026-08-12T16:41:00+07:00"


def item(symbol, asset_type, qty=None, avg=None, last=None, pnl_pct=None, mv=None, alloc=None, ccy="THB", side=None, **meta):
    if mv is None and qty is not None and last is not None:
        mv = round(float(qty) * float(last), 2)
    return {
        "symbol": symbol,
        "asset_type": asset_type,
        "side": side,
        "quantity": qty,
        "avg_price": avg,
        "last_price": last,
        "market_value": mv,
        "pnl_percent": pnl_pct,
        "allocation_percent": alloc,
        "currency": ccy,
        "meta": {k: v for k, v in meta.items() if v is not None},
    }


def main():
    pg = psycopg2.connect(**PG)
    try:
        init_portfolio_schema(pg)
        pg.commit()
        cur = pg.cursor()
        cur.execute("SELECT id FROM users WHERE telegram_chat_id=%s AND tier='owner'", (OWNER_CHAT,))
        row = cur.fetchone()
        if not row:
            raise SystemExit("owner user not found")
        user_id = row[0]
    finally:
        pg.close()

    snapshots = [
        {
            "broker": "krungsri",
            "account_alias": "krungsri_equity_screenshot",
            "account_type": "thai_equity",
            "source": "screenshot",
            "source_ref": "krungsri_efin_trade_plus_2026-08-12_1640",
            "as_of": "2026-08-12T16:40:00+07:00",
            "currency": "THB",
            "totals": {"total_unrealized_percent_visible": 2.10, "set_index": 1612.62, "set_change_percent": -0.72, "notes": "Account identifier hidden from public summary; screenshot showed Krungsri eFin Trade+ portfolio."},
            "holdings": [
                item("AH", "thai_equity", 1500, 16.53, 15.70, -5.01),
                item("AWC", "thai_equity", None, 2.97, 2.92, None, note="quantity not visible in screenshot"),
                item("BBGI", "thai_equity", 70000, 5.71, 5.85, 2.46),
                item("CRC", "thai_equity", 5000, 24.64, 25.75, 4.52),
                item("CREDIT", "thai_equity", 20000, 24.24, 23.70, -2.23),
                item("ERW", "thai_equity", 250000, 3.57, 3.64, 1.85),
                item("FORTH", "thai_equity", 15000, 17.53, 16.30, -7.01),
                item("GULF", "thai_equity", 10000, 67.11, 65.00, -3.15),
                item("GUNKUL", "thai_equity", None, 5.18, 4.88, None, note="quantity not visible in screenshot"),
                item("KBANK", "thai_equity", 5000, 240.40, 249.00, 3.58),
                item("MEGA", "thai_equity", 15000, 38.48, 38.50, 0.05),
                item("MEITUAN80", "thai_equity", 82600, 3.89, 3.92, 0.83),
                item("MRDIYT", "thai_equity", None, 10.32, 9.80, None, note="quantity not visible in screenshot"),
                item("NCAP", "thai_equity", 160000, 3.95, 3.82, -3.39),
                item("RCL", "thai_equity", 30000, 35.06, 39.25, 11.95),
                item("SJWD", "thai_equity", 100000, 9.79, 9.90, 1.12),
                item("STGT", "thai_equity", 30000, 10.88, 10.80, -0.78),
                item("THANI", "thai_equity", 400000, 2.18, 2.30, 5.33),
            ],
        },
        {
            "broker": "innovestx",
            "account_alias": "innovestx_derivatives_screenshot",
            "account_type": "futures",
            "source": "screenshot",
            "source_ref": "innovestx_tfex_2026-08-12_1640",
            "as_of": "2026-08-12T16:40:34+07:00",
            "currency": "THB",
            "totals": {"total_unrealized_percent_visible": -0.47, "line_available": 700363.15, "excess_equity": 18723.04, "set_index": 1612.62, "notes": "Trading account identifier hidden from public summary."},
            "holdings": [
                item("ADVANCU26X", "futures", 3, 371.99, 367.31, -1.26, ccy="THB", side="LONG", contract_month="U26"),
                item("BBLU26", "futures", 4, 193.60, 190.24, -1.74, ccy="THB", side="LONG", contract_month="U26"),
                item("CBGU26", "futures", 15, 51.64, 50.82, -1.58, ccy="THB", side="LONG", contract_month="U26"),
                item("COM7U26", "futures", 20, 30.54, 29.50, -3.41, ccy="THB", side="LONG", contract_month="U26"),
                item("CPNU26", "futures", 0, 0.00, 66.25, 0.00, ccy="THB", side="LONG", contract_month="U26"),
                item("GULFU26X", "futures", 0, 0.00, 65.27, 0.00, ccy="THB", side="LONG", contract_month="U26"),
                item("MGOU26", "futures", 4, 4231.70, 4401.00, 4.00, ccy="THB", side="LONG", contract_month="U26"),
                item("TOPU26", "futures", 8, 64.64, 67.21, 3.98, ccy="THB", side="LONG", contract_month="U26"),
            ],
        },
        {
            "broker": "webull_thailand",
            "account_alias": "webull_us_screenshot",
            "account_type": "us_equity",
            "source": "screenshot",
            "source_ref": "webull_thailand_us_positions_2026-08-12_1641",
            "as_of": AS_OF,
            "currency": "USD",
            "totals": {"positions_visible": 5, "previous_day_interest_usd": 0.27},
            "holdings": [
                item("XLV", "us_equity", 48, 165.78, 167.89, None, 8058.72, ccy="USD", name="State Street Health Care Select Sector SPDR Fund"),
                item("ARKG", "us_equity", 80, 40.36, 44.36, None, 3548.80, ccy="USD", name="ARK Genomic Revolution ETF"),
                item("FSLY", "us_equity", 115, 26.80, 28.48, None, 3275.20, ccy="USD", name="Fastly"),
                item("SPCX", "us_equity", 16, 126.49, 134.73, None, 2155.68, ccy="USD", name="Space Exploration Technology ETF"),
                item("SMH", "us_equity", 3, 567.47, 583.00, None, 1749.00, ccy="USD", name="VanEck Semiconductor ETF"),
            ],
        },
        {
            "broker": "dime",
            "account_alias": "dime_us_screenshot",
            "account_type": "us_equity",
            "source": "screenshot",
            "source_ref": "dime_us_assets_2026-08-12_1641",
            "as_of": AS_OF,
            "currency": "USD",
            "totals": {"total_asset_value_usd": 8708.75, "total_asset_value_thb": 287127.47, "total_cost_usd": 7190.33, "day_change_percent": 2.67, "unrealized_pl_percent": 21.12, "unrealized_pl_usd": 1518.42, "fx_usd_thb": 32.97},
            "holdings": [
                item("FSLY", "us_equity", None, None, 28.78, None, 6483.66, 74.45, ccy="USD", thb_value=213766.17, one_day_change_percent=3.71),
                item("XLV", "us_equity", None, None, 168.01, None, 2225.09, 25.55, ccy="USD", thb_value=73361.30, one_day_change_percent=-0.26),
            ],
        },
    ]

    for payload in snapshots:
        result = persist_manual_snapshot(user_id, payload)
        print(payload["account_alias"], result)


if __name__ == "__main__":
    main()
