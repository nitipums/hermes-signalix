"""Deferred owner-only Portfolio routes, isolated from Signalix MVP app core."""
from __future__ import annotations

import os
import re
from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile


def create_portfolio_router(get_pg):
    router = APIRouter(prefix="/portfolio", tags=["deferred-portfolio"])

    def portfolio_owner(chat_id: str, owner_token: str) -> int:
        from portfolio import require_owner_identity
        expected = os.getenv("PORTFOLIO_OWNER_TOKEN", "")
        bound_owner_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not require_owner_identity(owner_token, expected, str(chat_id), bound_owner_chat_id):
            raise HTTPException(status_code=403, detail="portfolio access denied")
        pg = get_pg(); cur = pg.cursor()
        try:
            cur.execute("SELECT id, tier FROM users WHERE telegram_chat_id=%s", (bound_owner_chat_id,))
            row = cur.fetchone()
        finally:
            cur.close(); pg.close()
        if not row or row[1] != "owner":
            raise HTTPException(status_code=403, detail="portfolio owner account required")
        return row[0]

    @router.post("/documents")
    async def portfolio_document(
        chat_id: str = Form(...), broker: str = Form(...), account_alias: str = Form(...),
        pdf: UploadFile = File(...), pdf_password: str = Form(""),
        x_portfolio_token: str = Header(default=""),
    ):
        user_id = portfolio_owner(chat_id, x_portfolio_token)
        if broker not in {"innovestx_derivatives", "krungsri_equity"}:
            raise HTTPException(status_code=400, detail="unsupported broker parser")
        if not account_alias or len(account_alias) > 64 or not re.fullmatch(r"[a-z0-9_-]+", account_alias):
            raise HTTPException(status_code=400, detail="invalid account alias")
        if not (pdf.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="PDF required")
        data = await pdf.read()
        if not data or len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="empty or oversized PDF")
        from portfolio import document_hash, parse_document, persist_parsed
        try:
            parsed = parse_document(data, broker, account_alias, pdf_password or None)
            result = persist_parsed(get_pg(), user_id, parsed, document_hash(data))
            return {**result, "broker": parsed["broker"], "account_alias": account_alias,
                    "trade_date": parsed["trade_date"]}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @router.post("/snapshots")
    async def portfolio_snapshot(request: Request, chat_id: str, x_portfolio_token: str = Header(default="")):
        user_id = portfolio_owner(chat_id, x_portfolio_token)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="snapshot payload required")
        for key in ("broker", "account_alias", "account_type", "as_of", "holdings"):
            if key not in payload:
                raise HTTPException(status_code=400, detail=f"missing {key}")
        if not re.fullmatch(r"[a-z0-9_-]{1,64}", payload["account_alias"]):
            raise HTTPException(status_code=400, detail="invalid account alias")
        if not isinstance(payload.get("holdings"), list) or len(payload["holdings"]) > 200:
            raise HTTPException(status_code=400, detail="invalid holdings list")
        from portfolio import persist_manual_snapshot
        try:
            return persist_manual_snapshot(user_id, payload)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @router.get("/me")
    def portfolio_me(chat_id: str, x_portfolio_token: str = Header(default="")):
        user_id = portfolio_owner(chat_id, x_portfolio_token)
        from portfolio import portfolio_summary
        return portfolio_summary(user_id)

    @router.get("/health")
    def portfolio_health_route(chat_id: str, x_portfolio_token: str = Header(default="")):
        user_id = portfolio_owner(chat_id, x_portfolio_token)
        from portfolio import portfolio_health
        return portfolio_health(user_id)

    return router
