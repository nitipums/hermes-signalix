"""Owner-only Investment Co-pilot MVP.

This module is intentionally separate from Signalix signal-routing. It stores
private broker-document facts in portfolio_* tables and consumes market data
only through existing read-only Signalix endpoints in later phases.
"""
import datetime as dt
import hashlib
import hmac
import os
import re
from io import BytesIO

import psycopg2.extras

PG = dict(
    host=os.getenv("POSTGRES_HOST", "postgres"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    user=os.getenv("POSTGRES_USER", "signalix"),
    password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
    dbname=os.getenv("POSTGRES_DB", "signalix"),
)


def require_owner_token(provided: str, expected: str) -> bool:
    """Fail closed if either value is absent; comparison is constant-time."""
    return bool(provided and expected and hmac.compare_digest(provided, expected))


def require_owner_identity(provided_token: str, expected_token: str,
                           requested_chat_id: str, bound_owner_chat_id: str) -> bool:
    """Require the owner token and its server-configured owner identity together."""
    return bool(
        require_owner_token(provided_token, expected_token)
        and requested_chat_id
        and bound_owner_chat_id
        and hmac.compare_digest(str(requested_chat_id), str(bound_owner_chat_id))
    )


def _number(value: str) -> float:
    return float(value.replace(",", ""))


def _date(value: str) -> str:
    return dt.datetime.strptime(value, "%d/%m/%Y").date().isoformat()


def _base_document(broker, account_alias, asset_type, text):
    # Extracted broker PDFs often put the label and date on different columns/lines.
    date_match = re.search(r"Trading Date[\s\S]{0,180}?(\d{2}/\d{2}/\d{4})", text, re.I)
    if not date_match:
        date_match = re.search(r"Trade Date[\s\S]{0,180}?(\d{2}/\d{2}/\d{4})", text, re.I)
    if not date_match:
        raise ValueError("trade date not found")
    return {"broker": broker, "account_alias": account_alias,
            "asset_type": asset_type, "trade_date": _date(date_match.group(1)),
            "transactions": [], "snapshot": None}


def parse_innovestx_derivatives_text(text: str, account_alias: str) -> dict:
    result = _base_document("innovestx", account_alias, "futures", text)
    settlement = re.search(r"Settlement No\.\s*([A-Z0-9-]+)", text, re.I)
    result["document_ref"] = settlement.group(1) if settlement else None
    # Only read rows in the first transaction block, before closing positions.
    block = re.split(r"POSITION CLOSING", text, maxsplit=1, flags=re.I)[0]
    row = re.compile(
        r"^\s*([A-Z0-9]+)\s+(F\d+)\s+([BS])\s+(\d+)\s+([\d,.]+)\s+"
        r"[\d,.]+\s+([\d,.]+)\s+([\d,.]+)\s+[\d,.]+\s+([\d,.]+)\s*$",
        re.M,
    )
    for symbol, contract, side, qty, price, fee, vat, charge in row.findall(block):
        result["transactions"].append({
            "broker_trade_id": contract, "broker_order_id": None, "symbol": symbol,
            "side": "BUY" if side == "B" else "SELL", "quantity": int(qty),
            "price": _number(price), "fee": _number(fee), "vat": _number(vat),
            "net_amount": _number(charge), "currency": "THB",
        })
    if not result["transactions"]:
        raise ValueError("no InnovestX derivative trade rows found")
    # Headers are interleaved with values in text extraction; take only numeric
    # tokens from the final Statement of Account block, through Cash Excess.
    statement_at = text.upper().rfind("STATEMENT OF ACCOUNT")
    if statement_at >= 0:
        snapshot_block = text[statement_at: statement_at + 2500]
        values = re.findall(r"(?<![A-Za-z0-9])-?[\d,]+\.\d{2}(?![A-Za-z0-9])", snapshot_block)
        if len(values) >= 13:
            n = [_number(x) for x in values[:13]]
            result["snapshot"] = {"begin_cash_balance": n[0], "end_cash_balance": n[1],
                "realized_pnl": n[3], "unrealized_pnl": n[4], "begin_equity": n[7],
                "end_equity": n[8], "initial_margin": n[9], "maintenance_margin": n[10],
                "cash_excess": n[11]}
    return result


def parse_krungsri_equity_text(text: str, account_alias: str) -> dict:
    result = _base_document("krungsri", account_alias, "thai_equity", text)
    doc = re.search(r"Document No\.\s*([A-Z0-9-]+)", text, re.I)
    result["document_ref"] = doc.group(1) if doc else None
    # Contract/order, symbol, units, price, fee, VAT, net amount.
    row = re.compile(
        r"^\s*((?:BU|SE)-\d+)\s+(\d+)\s+([A-Z0-9]+)\s+([\d,]+)\s+([\d,.]+)\s+"
        r"([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s*$", re.M)
    for contract, order, symbol, qty, price, fee, vat, net in row.findall(text):
        result["transactions"].append({
            "broker_trade_id": contract, "broker_order_id": order, "symbol": symbol,
            "side": "BUY" if contract.startswith("BU-") else "SELL", "quantity": int(qty.replace(",", "")),
            "price": _number(price), "fee": _number(fee), "vat": _number(vat),
            "net_amount": _number(net), "currency": "THB",
        })
    if not result["transactions"]:
        raise ValueError("no Krungsri equity trade rows found")
    return result


def extract_pdf_text(data: bytes, password: str | None = None) -> str:
    import pymupdf
    doc = pymupdf.open(stream=data, filetype="pdf")
    if doc.page_count > 10:
        raise ValueError("PDF has too many pages")
    if doc.is_encrypted and not (password and doc.authenticate(password)):
        raise ValueError("PDF password required or invalid")
    text = "\n".join(page.get_text("text") for page in doc)
    if len(text) > 500_000:
        raise ValueError("PDF extracted text is too large")
    return text


def parse_document(data: bytes, broker: str, account_alias: str, password: str | None = None) -> dict:
    text = extract_pdf_text(data, password)
    if broker == "innovestx_derivatives":
        return parse_innovestx_derivatives_text(text, account_alias)
    if broker == "krungsri_equity":
        return parse_krungsri_equity_text(text, account_alias)
    raise ValueError("unsupported broker parser")


def init_portfolio_schema(pg):
    cur = pg.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS portfolio_accounts (
      id SERIAL PRIMARY KEY, user_id INT REFERENCES users(id) ON DELETE CASCADE,
      account_alias TEXT NOT NULL, broker TEXT NOT NULL, account_type TEXT NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(user_id, account_alias)
    );
    CREATE TABLE IF NOT EXISTS portfolio_documents (
      id UUID PRIMARY KEY, user_id INT REFERENCES users(id) ON DELETE CASCADE,
      account_id INT REFERENCES portfolio_accounts(id) ON DELETE CASCADE,
      broker TEXT NOT NULL, source_hash TEXT NOT NULL UNIQUE, document_ref TEXT,
      trade_date DATE, parser_version TEXT NOT NULL, parse_status TEXT NOT NULL,
      received_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS portfolio_transactions (
      id UUID PRIMARY KEY, document_id UUID REFERENCES portfolio_documents(id) ON DELETE CASCADE,
      broker_trade_id TEXT, broker_order_id TEXT, symbol TEXT NOT NULL, side TEXT NOT NULL,
      quantity NUMERIC NOT NULL, price NUMERIC NOT NULL, fee NUMERIC NOT NULL DEFAULT 0,
      vat NUMERIC NOT NULL DEFAULT 0, net_amount NUMERIC, currency TEXT NOT NULL,
      trade_date DATE NOT NULL, UNIQUE(document_id, broker_trade_id)
    );
    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
      id UUID PRIMARY KEY, document_id UUID UNIQUE REFERENCES portfolio_documents(id) ON DELETE CASCADE,
      snapshot JSONB NOT NULL, as_of_date DATE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS portfolio_holding_snapshots (
      id UUID PRIMARY KEY, user_id INT REFERENCES users(id) ON DELETE CASCADE,
      account_id INT REFERENCES portfolio_accounts(id) ON DELETE CASCADE,
      source TEXT NOT NULL, source_ref TEXT NOT NULL, as_of TIMESTAMPTZ NOT NULL,
      currency TEXT NOT NULL, totals JSONB NOT NULL DEFAULT '{}'::jsonb,
      source_hash TEXT NOT NULL UNIQUE, created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS portfolio_holding_items (
      id UUID PRIMARY KEY, snapshot_id UUID REFERENCES portfolio_holding_snapshots(id) ON DELETE CASCADE,
      symbol TEXT NOT NULL, asset_type TEXT NOT NULL, side TEXT, quantity NUMERIC,
      avg_price NUMERIC, last_price NUMERIC, market_value NUMERIC,
      pnl_percent NUMERIC, pnl_amount NUMERIC, allocation_percent NUMERIC,
      currency TEXT NOT NULL, meta JSONB NOT NULL DEFAULT '{}'::jsonb
 );
 CREATE UNIQUE INDEX IF NOT EXISTS portfolio_holding_items_snapshot_symbol_side_uq
 ON portfolio_holding_items(snapshot_id, symbol, COALESCE(side,''));
    CREATE TABLE IF NOT EXISTS portfolio_audit_events (
      id UUID PRIMARY KEY, user_id INT REFERENCES users(id) ON DELETE CASCADE,
      account_id INT REFERENCES portfolio_accounts(id) ON DELETE SET NULL,
      event_type TEXT NOT NULL, payload JSONB NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """)
    cur.close()


def persist_parsed(_pg, user_id: int, parsed: dict, source_hash: str):
    """Atomically persist one parsed document; safe under concurrent retries."""
    import uuid
    pg = psycopg2.connect(**PG)
    try:
        with pg:
            with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""INSERT INTO portfolio_accounts(user_id, account_alias, broker, account_type)
                               VALUES (%s,%s,%s,%s)
                               ON CONFLICT(user_id, account_alias) DO UPDATE SET broker=EXCLUDED.broker
                               RETURNING id""",
                            (user_id, parsed["account_alias"], parsed["broker"], parsed["asset_type"]))
                account_id = cur.fetchone()["id"]
                doc_id = str(uuid.uuid4())
                cur.execute("""INSERT INTO portfolio_documents
                               (id,user_id,account_id,broker,source_hash,document_ref,trade_date,parser_version,parse_status)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                               ON CONFLICT(source_hash) DO NOTHING RETURNING id""",
                            (doc_id, user_id, account_id, parsed["broker"], source_hash, parsed.get("document_ref"),
                             parsed["trade_date"], "mvp-1", "parsed"))
                if not cur.fetchone():
                    return {"status": "duplicate", "transactions": 0}
                seen_trade_ids = set()
                for tx in parsed["transactions"]:
                    trade_id = tx.get("broker_trade_id")
                    if not trade_id or trade_id in seen_trade_ids:
                        raise ValueError("missing or duplicate broker trade ID")
                    seen_trade_ids.add(trade_id)
                stored_transactions = 0
                for tx in parsed["transactions"]:
                    cur.execute("""SELECT 1 FROM portfolio_transactions t
                                   JOIN portfolio_documents d ON d.id=t.document_id
                                   WHERE d.account_id=%s AND t.broker_trade_id=%s""",
                                (account_id, tx["broker_trade_id"]))
                    if cur.fetchone():
                        continue
                    cur.execute("""INSERT INTO portfolio_transactions
                      (id,document_id,broker_trade_id,broker_order_id,symbol,side,quantity,price,fee,vat,net_amount,currency,trade_date)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (str(uuid.uuid4()), doc_id, tx["broker_trade_id"], tx["broker_order_id"], tx["symbol"], tx["side"],
                       tx["quantity"], tx["price"], tx["fee"], tx["vat"], tx["net_amount"], tx["currency"], parsed["trade_date"]))
                    stored_transactions += 1
                if parsed.get("snapshot"):
                    cur.execute("INSERT INTO portfolio_snapshots(id,document_id,snapshot,as_of_date) VALUES (%s,%s,%s,%s)",
                                (str(uuid.uuid4()), doc_id, psycopg2.extras.Json(parsed["snapshot"]), parsed["trade_date"]))
                cur.execute("""INSERT INTO portfolio_audit_events(id,user_id,account_id,event_type,payload)
                               VALUES (%s,%s,%s,%s,%s)""",
                            (str(uuid.uuid4()), user_id, account_id, "document_imported",
                             psycopg2.extras.Json({"document_ref": parsed.get("document_ref"),
                                                   "trade_date": parsed["trade_date"],
                                                   "transactions": stored_transactions,
                                                   "parser_version": "mvp-1"})))
        return {"status": "stored", "document_id": doc_id, "transactions": stored_transactions,
                "snapshot": bool(parsed.get("snapshot"))}
    finally:
        pg.close()


def document_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def persist_manual_snapshot(user_id: int, payload: dict):
    """Persist a user-confirmed screenshot/manual holding snapshot.

    This is intentionally separate from document parser transactions: screenshots
    are observation snapshots, not source-of-truth ledger transactions.
    """
    import json
    import uuid
    canonical = json.dumps(payload, sort_keys=True, default=str).encode()
    source_hash = hashlib.sha256(canonical).hexdigest()
    pg = psycopg2.connect(**PG)
    try:
        with pg:
            with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""INSERT INTO portfolio_accounts(user_id, account_alias, broker, account_type)
                               VALUES (%s,%s,%s,%s)
                               ON CONFLICT(user_id, account_alias) DO UPDATE
                                 SET broker=EXCLUDED.broker, account_type=EXCLUDED.account_type
                               RETURNING id""",
                            (user_id, payload["account_alias"], payload["broker"], payload["account_type"]))
                account_id = cur.fetchone()["id"]
                snapshot_id = str(uuid.uuid4())
                cur.execute("""INSERT INTO portfolio_holding_snapshots
                               (id,user_id,account_id,source,source_ref,as_of,currency,totals,source_hash)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                               ON CONFLICT(source_hash) DO NOTHING RETURNING id""",
                            (snapshot_id, user_id, account_id, payload.get("source", "screenshot"),
                             payload.get("source_ref", payload["account_alias"]), payload["as_of"],
                             payload.get("currency", "THB"), psycopg2.extras.Json(payload.get("totals", {})),
                             source_hash))
                if not cur.fetchone():
                    return {"status": "duplicate", "holdings": 0}
                for item in payload.get("holdings", []):
                    cur.execute("""INSERT INTO portfolio_holding_items
                      (id,snapshot_id,symbol,asset_type,side,quantity,avg_price,last_price,market_value,
                       pnl_percent,pnl_amount,allocation_percent,currency,meta)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (str(uuid.uuid4()), snapshot_id, item["symbol"].upper(), item.get("asset_type", payload["account_type"]),
                       item.get("side"), item.get("quantity"), item.get("avg_price"), item.get("last_price"),
                       item.get("market_value"), item.get("pnl_percent"), item.get("pnl_amount"),
                       item.get("allocation_percent"), item.get("currency", payload.get("currency", "THB")),
                       psycopg2.extras.Json(item.get("meta", {}))))
                cur.execute("""INSERT INTO portfolio_audit_events(id,user_id,account_id,event_type,payload)
                               VALUES (%s,%s,%s,%s,%s)""",
                            (str(uuid.uuid4()), user_id, account_id, "manual_snapshot_imported",
                             psycopg2.extras.Json({"source_ref": payload.get("source_ref"),
                                                   "holdings": len(payload.get("holdings", [])),
                                                   "as_of": payload["as_of"]})))
        return {"status": "stored", "snapshot_id": snapshot_id, "holdings": len(payload.get("holdings", []))}
    finally:
        pg.close()


def _freshness_status(as_of) -> str:
    if not as_of:
        return "unknown"
    now = dt.datetime.now(dt.timezone.utc)
    if getattr(as_of, "tzinfo", None) is None:
        as_of = as_of.replace(tzinfo=dt.timezone.utc)
    age_hours = (now - as_of).total_seconds() / 3600
    if age_hours <= 24:
        return "fresh"
    if age_hours <= 72:
        return "aging"
    return "stale"


def _human_state(state: str) -> str:
    return {
        "unlinked": "ยังไม่ได้ผูกแหล่งข้อมูล",
        "snapshot_only": "มีภาพ snapshot แต่ยังไม่ใช่ ledger",
        "awaiting_statement": "รอ statement/confirmation เพื่อยืนยัน",
        "needs_review": "ต้องตรวจเทียบข้อมูล",
        "incomplete": "ข้อมูลไม่ครบ",
        "not_covered": "ยังไม่มีข้อมูลพอร์ตล่าสุด",
    }.get(state, state)


def _account_health_state(account: dict) -> tuple[str, list[str]]:
    limitations = []
    has_snapshot = bool(account.get("latest_snapshot"))
    has_tx = bool(account.get("transaction_count"))
    if has_snapshot and has_tx:
        limitations.append("ledger_and_snapshot_not_reconciled")
        return "needs_review", limitations
    if has_snapshot:
        limitations.append("screenshot_is_observation_not_ledger")
        if account.get("account_type") in {"us_equity", "futures"}:
            limitations.append("asset_specific_risk_policy_not_configured")
        return "snapshot_only", limitations
    if has_tx:
        limitations.append("current_position_not_calculated_from_ledger")
        return "awaiting_statement", limitations
    limitations.append("no_current_holding_source")
    return "not_covered", limitations


def _risk_inputs(account: dict) -> dict:
    missing = []
    coverage = "partial" if account.get("holdings") else "not_ready"
    if account.get("account_type") == "thai_equity":
        missing += ["owner_stop_or_thesis_plan", "signalix_market_context_join"]
    elif account.get("account_type") == "futures":
        missing += ["contract_multiplier", "margin_buffer_policy", "daily_loss_policy", "max_contract_policy"]
    elif account.get("account_type") == "us_equity":
        missing += ["fx_source_timestamp", "us_market_price_freshness", "us_asset_policy"]
    else:
        missing += ["asset_policy"]
    return {"coverage": coverage, "missing": missing}


def _build_attention(accounts: list[dict]) -> list[dict]:
    items = []
    severity_rank = {"act_now": 0, "decide_today": 1, "watch": 2, "fyi": 3}
    for account in accounts:
        state = account.get("reconciliation_state")
        name = account.get("display_name") or account.get("account_alias")
        holdings = account.get("holdings") or []
        fresh = account.get("freshness", {})
        if state == "needs_review":
            items.append({
                "severity": "act_now", "account": name, "holding": None,
                "title": "Reconciliation required",
                "observed": "Broker ledger and observation snapshot both exist but are not linked/reconciled.",
                "threshold": "Any duplicate real-world account source must be owner-confirmed before use.",
                "action": "Open Inspect and confirm whether document and screenshot represent the same real account.",
                "source": fresh,
            })
        elif state == "snapshot_only":
            items.append({
                "severity": "watch", "account": name, "holding": None,
                "title": "Observation snapshot needs review",
                "observed": f"{len(holdings)} holding(s) from screenshot/manual observation.",
                "threshold": "Screenshot data must not be treated as broker-confirmed ledger.",
                "action": "Attach statement/confirmation or mark fields reviewed before risk decisions.",
                "source": fresh,
            })
        elif state in {"awaiting_statement", "not_covered"}:
            items.append({
                "severity": "watch", "account": name, "holding": None,
                "title": "Current holdings not fully covered",
                "observed": _human_state(state),
                "threshold": "Every monitored account needs a latest source timestamp.",
                "action": "Import or review a broker statement/snapshot.",
                "source": fresh,
            })
        if account.get("account_type") == "futures" and holdings:
            items.append({
                "severity": "decide_today", "account": name, "holding": "TFEX",
                "title": "TFEX margin policy missing",
                "observed": f"{len(holdings)} observed futures position(s).",
                "threshold": "Margin buffer, max contracts, daily loss and overnight policy must exist before action alerts.",
                "action": "Define owner risk policy; execution remains OFF.",
                "source": fresh,
            })
    items.sort(key=lambda x: severity_rank.get(x["severity"], 9))
    return items[:5] or [{
        "severity": "fyi", "account": "Portfolio", "holding": None,
        "title": "No actionable event from verified data",
        "observed": "No account-health rule triggered from currently verified sources.",
        "threshold": "This does not mean the portfolio is safe; it only means the current verified data did not trigger a rule.",
        "action": "Keep source freshness and reconciliation current.",
        "source": {"status": "unknown"},
    }]


def portfolio_summary(user_id: int) -> dict:
    """Owner-safe portfolio summary; excludes raw documents and raw account IDs."""
    pg = psycopg2.connect(**PG)
    try:
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT a.id, a.account_alias, a.broker, a.account_type,
                                  count(DISTINCT t.id) AS transaction_count,
                                  max(d.trade_date) AS latest_trade_date
                           FROM portfolio_accounts a
                           LEFT JOIN portfolio_documents d ON d.account_id=a.id
                           LEFT JOIN portfolio_transactions t ON t.document_id=d.id
                           WHERE a.user_id=%s
                           GROUP BY a.id, a.account_alias, a.broker, a.account_type
                           ORDER BY a.account_alias""", (user_id,))
            accounts = [dict(r) for r in cur.fetchall()]
            cur.execute("""SELECT DISTINCT ON (hs.account_id) hs.account_id, hs.id AS snapshot_id,
                                  hs.source, hs.source_ref, hs.as_of, hs.currency, hs.totals
                           FROM portfolio_holding_snapshots hs
                           WHERE hs.user_id=%s
                           ORDER BY hs.account_id, hs.as_of DESC, hs.created_at DESC""", (user_id,))
            snaps = {r["account_id"]: dict(r) for r in cur.fetchall()}
            for account in accounts:
                snap = snaps.get(account["id"])
                account.pop("id", None)
                account["latest_snapshot"] = None
                account["holdings"] = []
                if not snap:
                    continue
                account["latest_snapshot"] = {k: snap[k] for k in ("source", "source_ref", "as_of", "currency", "totals")}
                cur.execute("""SELECT symbol, asset_type, side, quantity, avg_price, last_price, market_value,
                                      pnl_percent, pnl_amount, allocation_percent, currency, meta
                               FROM portfolio_holding_items WHERE snapshot_id=%s ORDER BY market_value DESC NULLS LAST, symbol""",
                            (snap["snapshot_id"],))
                account["holdings"] = [dict(r) for r in cur.fetchall()]
            return {"accounts": accounts, "state": "observe_only_screenshot_mvp"}
    finally:
        pg.close()


def portfolio_health(user_id: int) -> dict:
    """Normalized Monitor/Inspect contract for Account Health P0.1."""
    summary = portfolio_summary(user_id)
    accounts = []
    for account in summary["accounts"]:
        state, limitations = _account_health_state(account)
        snap = account.get("latest_snapshot") or {}
        latest_as_of = snap.get("as_of")
        freshness = {
            "latest_source_type": snap.get("source") or ("document" if account.get("latest_trade_date") else "unknown"),
            "latest_source_ref": snap.get("source_ref") or None,
            "as_of": latest_as_of or account.get("latest_trade_date"),
            "status": _freshness_status(latest_as_of),
        }
        data_limitations = list(limitations)
        if state in {"awaiting_statement", "not_covered"}:
            data_limitations.append("latest_holdings_unknown")
        if account.get("account_type") == "thai_equity" and account.get("holdings"):
            data_limitations.append("signalix_market_context_not_joined_yet")
        health_account = {
            "display_account_id": account["account_alias"],
            "display_name": account["account_alias"].replace("_", " ").title(),
            "broker": account["broker"],
            "asset_type": account["account_type"],
            "transaction_count": int(account.get("transaction_count") or 0),
            "freshness": freshness,
            "reconciliation_state": state,
            "reconciliation_label": _human_state(state),
            "holdings": account.get("holdings") or [],
            "risk_inputs": _risk_inputs(account),
            "data_limitations": data_limitations,
        }
        accounts.append(health_account)
    return {
        "state": "monitor_p0_1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "accounts": accounts,
        "attention": _build_attention(accounts),
    }
