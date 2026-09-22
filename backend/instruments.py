"""Authoritative active-ORD instrument/taxonomy/profile resolution.

P0-2 of the Signalix data-integrity sequence (Execution-Pipeline.md, Task 3:
"Active ORD instrument master"). This module is the SINGLE source of truth for
the canonical instrument record and the company taxonomy that backs the
dashboard detail cards.

Authority hierarchy (must read in this order):
  1. `symbol_master` — seeded weekly from Settrade's official stock-list JSON
     by `sync_settrade_master.sync_db`. Carries the authoritative taxonomy:
     symbol, venue, asset_class, currency, timezone, session, source, freshness,
     status. For active ORD, venue/currency/timezone/session are constant
     (THB, SET segment, Asia/Bangkok) but are stored explicitly so the master
     is market-portable and auditable.
  2. `company_profiles` — sourced from SET's public factsheet via
     `fetch_fundamentals_subagent` (set_factsheet source), with Yahoo Finance
     (`refresh_company_profiles.py`) as an explicit, non-authoritative FALLBACK
     only for symbols whose factsheet cannot be resolved. Yahoo never drives
     taxonomy decisions; a missing profile is reported as `unknown`, never
     invented.

This module never touches prices/signals. It only resolves identity + taxonomy
with honest provenance. Deterministic calculations stay in scanner.py.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg2

PG_DSN = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "user": os.getenv("POSTGRES_USER", "signalix"),
    "password": os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
    "dbname": os.getenv("POSTGRES_DB", "signalix"),
}

# Canonical taxonomy defaults for the single active Thai market. These back
# the "honest missing data" policy: when symbol_master is the authority, the
# market-level value is concrete rather than left as a per-row guess. A symbol
# not in the master still yields 'unknown' rather than a substituted value.
THAI_VENUES = {"SET", "MAI"}
THAI_ASSET_CLASS = "equity"
THAI_CURRENCY = "THB"
THAI_TIMEZONE = "Asia/Bangkok"
THAI_SESSION = "SET"

# Profile source ranking: authoritative first. Used to pick a taxonomy row
# when both sources exist for a symbol.
SOURCE_PRIORITY = ("set_factsheet", "yfinance", "xlsx", "unknown")

INSTRUMENT_TAXONOMY_FIELDS = (
    "symbol", "instrument_type", "status", "venue", "asset_class",
    "currency", "timezone", "session", "source", "freshness",
)

_CANONICAL_VALUES = {
    "instrument_type": {"ORD"},
    "status": {"active"},
    "venue": THAI_VENUES,
    "asset_class": {THAI_ASSET_CLASS},
    "currency": {THAI_CURRENCY},
    "timezone": {THAI_TIMEZONE},
    "session": {THAI_SESSION},
    "freshness": {"fresh", "stale", "unknown"},
}


def get_pg():
    return psycopg2.connect(**PG_DSN)


def _source_rank(source: str | None) -> int:
    """Lower number = more authoritative."""
    if source is None:
        return len(SOURCE_PRIORITY)
    try:
        return SOURCE_PRIORITY.index(source)
    except ValueError:
        return len(SOURCE_PRIORITY)


def instrument_master(pg) -> list[dict]:
    """Return all active ORD taxonomy records as dicts.

    Each dict carries the canonical authority fields plus `reason` and
    `marked_at` audit fields. Returns one row per active ORD symbol; the
    caller never sees inactive/excluded rows here (they are inspectable via
    `excluded_symbols` in screening.py and the `/symbols/excluded` endpoint).
    """
    cur = pg.cursor()
    try:
        cur.execute(
            """SELECT symbol, instrument_type, status, venue, asset_class,
                      currency, timezone, session, source, freshness,
                      reason, marked_at
               FROM symbol_master
               WHERE instrument_type = 'ORD'
                 AND (status = 'active' OR status IS NULL)
               ORDER BY symbol""")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        cur.close()


def active_ord_symbols(pg) -> list[str]:
    """The bounded active-ORD universe, directly from the authority master."""
    records = instrument_master(pg)
    return [r["symbol"] for r in records]


def validate_instrument_record(record: dict) -> dict:
    """Validate one authoritative active-ORD record without changing it.

    The validator only reports observed data. Missing values are not replaced
    with market defaults, and invalid values are kept visible separately from
    missing values. The contract is intentionally pure so it can be used by
    API serializers, tests, and offline quality checks alike.
    """
    missing_fields = []
    invalid_fields = []
    for field in INSTRUMENT_TAXONOMY_FIELDS:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing_fields.append(field)
            continue
        if field == "symbol":
            if not isinstance(value, str) or value != value.strip() or value != value.upper():
                invalid_fields.append(field)
        elif field == "source":
            if not isinstance(value, str) or not value.strip():
                invalid_fields.append(field)
        elif value not in _CANONICAL_VALUES[field]:
            invalid_fields.append(field)
    if invalid_fields:
        status = "invalid"
    elif missing_fields:
        status = "incomplete"
    else:
        status = "complete"
    return {
        "status": status,
        "missing_fields": missing_fields,
        "invalid_fields": invalid_fields,
    }


def instrument_quality_summary(records: list[dict]) -> dict:
    """Return deterministic completeness counts for the supplied records."""
    qualities = [validate_instrument_record(record) for record in records]
    complete = sum(q["status"] == "complete" for q in qualities)
    incomplete = sum(q["status"] == "incomplete" for q in qualities)
    invalid = sum(q["status"] == "invalid" for q in qualities)
    evaluated = len(records)
    return {
        "evaluated_count": evaluated,
        "complete_count": complete,
        "incomplete_count": incomplete,
        "invalid_count": invalid,
        "completeness_pct": round(complete / evaluated * 100, 1) if evaluated else 0.0,
    }


def instrument_identity(pg, symbol: str) -> dict | None:
    """Return the authoritative taxonomy record for one symbol, or None.

    None means the symbol is NOT an active ORD instrument (delisted,
    excluded, a DR, or absent from the master). Callers must treat None as
    'absent/unknown instrument identity' — not as a signal to fabricate
    taxonomy or to scan the symbol.
    """
    symbol = (symbol or "").upper()
    if not symbol:
        return None
    cur = pg.cursor()
    try:
        cur.execute(
            """SELECT symbol, instrument_type, status, venue, asset_class,
                      currency, timezone, session, source, freshness,
                      reason, marked_at
               FROM symbol_master
               WHERE symbol = %s""", (symbol,))
        cols = [d[0] for d in cur.description] if cur.description else [
            "symbol", "instrument_type", "status", "venue", "asset_class",
            "currency", "timezone", "session", "source", "freshness",
            "reason", "marked_at"]
        row = cur.fetchone()
        if row is None:
            return None
        # Re-check: is this symbol an active ORD? Captured via description
        # BEFORE this query so column mapping stays correct regardless of
        # cursor state. The result is informational — we still return the
        # authoritative record (with its status/reason) so callers can
        # display delisting/exclusion honestly rather than fabricating state.
        cur.execute(
            "SELECT instrument_type, status FROM symbol_master "
            "WHERE symbol = %s AND instrument_type = 'ORD' "
            "AND (status = 'active' OR status IS NULL)", (symbol,))
        active_ORD = cur.fetchone() is not None
        record = dict(zip(cols, row))
        record["is_active_ord"] = active_ORD
        return record
    finally:
        cur.close()


def profile_taxonomy(pg, symbols: list[str] | None = None,
                     limit: int = 0) -> dict[str, dict]:
    """Return company taxonomy for a bounded symbol set.

    Prefers the SET factsheet source (`set_factsheet`) over Yahoo. A symbol
    present in symbol_master but with no profile row at all returns an
    explicit `unknown` provenance dict — never a substituted/fabricated
    sector or industry. If `symbols` is omitted, defaults to the active ORD
    universe (capped by `limit`) so the caller cannot accidentally fan out.

    Returns: {symbol: {company_name, sector, industry, market_cap, business_summary,
                       source, fetched_at, missing}} where `missing` is True
    when NO profile row exists for an active-ORD symbol.
    """
    if symbols is None:
        symbols = active_ord_symbols(pg)
    symbols = [s.upper() for s in symbols if s]
    if limit:
        symbols = symbols[:limit]
    if not symbols:
        return {}
    out: dict[str, dict] = {}
    cur = pg.cursor()
    try:
        # symbol_master join gives authoritative active-ORD status + the
        # source/venue/currency/timezone/session taxonomy in one pass.
        cur.execute(
            """SELECT sm.symbol,
                      sm.venue, sm.asset_class, sm.currency,
                      sm.timezone, sm.session, sm.source AS inst_source,
                      sm.status,
                      cp.company_name, cp.sector, cp.industry, cp.market_cap,
                      cp.business_summary, cp.source AS prof_source,
                      cp.fetched_at
               FROM symbol_master sm
               LEFT JOIN company_profiles cp ON cp.symbol = sm.symbol
               WHERE sm.symbol = ANY(%s)
                 AND sm.instrument_type = 'ORD'
                 AND (sm.status = 'active' OR sm.status IS NULL)
               ORDER BY sm.symbol""", (symbols,))
        for row in cur.fetchall():
            (symbol, venue, asset_class, currency, tz, session, inst_source,
             status, name, sector, industry, market_cap, summary, prof_source,
             fetched_at) = row
            prof_rank = _source_rank(prof_source)
            has_profile = any(v is not None for v in (name, sector, industry, market_cap, summary))
            out[symbol] = {
                "symbol": symbol,
                "venue": venue,
                "asset_class": asset_class,
                "currency": currency,
                "timezone": tz,
                "session": session,
                "source": inst_source,
                "status": status,
                "company_name": name,
                "sector": sector,
                "industry": industry,
                "market_cap": market_cap,
                "business_summary": summary,
                "profile_source": prof_source,
                "profile_fetched_at": fetched_at.isoformat() if hasattr(fetched_at, "isoformat") else (str(fetched_at) if fetched_at else None),
                "profile_rank": prof_rank,
                "missing": not has_profile,
            }
        # Symbols queried but not in symbol_master (absent/inactive/excluded):
        # report explicitly absent so the caller doesn't fabricate identity.
        returned = {r[0] for r in cur.fetchall()} if False else set(out.keys())
        for s in symbols:
            if s not in returned:
                out[s] = {
                    "symbol": s, "venue": None, "asset_class": None,
                    "currency": None, "timezone": None, "session": None,
                    "source": None, "status": "absent",
                    "company_name": None, "sector": None, "industry": None,
                    "market_cap": None,
                    "business_summary": None, "profile_source": None,
                    "profile_fetched_at": None, "profile_rank": len(SOURCE_PRIORITY),
                    "missing": True,
                }
    finally:
        cur.close()
    return out


def instrument_hash(records: list[dict]) -> str:
    """Stable hash of the active-ORD master record for freshness/coverage checks.

    Deterministic: sorted JSON of the canonical field tuple sequence. Used by
    health checks to detect master drift without comparing row counts alone.
    """
    payload = json.dumps(
        sorted({(r["symbol"], r.get("source"), r.get("status"),
                r.get("freshness")) for r in records}, key=lambda t: json.dumps(t, default=str)),
        sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def refresh_status(pg) -> dict:
    """Return a freshness summary of the instrument authority for healthchecks."""
    cur = pg.cursor()
    try:
        cur.execute("SELECT to_regclass('public.symbol_master')")
        if not cur.fetchone()[0]:
            return {"table": "symbol_master", "exists": False, "status": "unavailable"}
        cur.execute(
            "SELECT count(*), bool_or(freshness='fresh') "
            "FROM symbol_master WHERE instrument_type='ORD'")
        total, all_fresh = cur.fetchone()
        cur.execute(
            "SELECT count(*) FROM symbol_master WHERE instrument_type='ORD' "
            "AND (status='active' OR status IS NULL)")
        active = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM symbol_master sm LEFT JOIN company_profiles cp "
            "ON cp.symbol=sm.symbol WHERE sm.instrument_type='ORD' "
            "AND (sm.status='active' OR sm.status IS NULL) "
            "AND cp.source IS NOT NULL")
        with_profile = cur.fetchone()[0]
        return {
            "table": "symbol_master", "exists": True,
            "status": "fresh" if all_fresh else "stale",
            "active_ord_count": active, "total_ord_count": total,
            "active_with_profile": with_profile,
            "profile_coverage_pct": round(with_profile / active * 100, 1) if active else 0.0,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        cur.close()
