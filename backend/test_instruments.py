"""P0-2 instrument authority tests.

These exercise instruments.py and the build_dashboard taxonomy wiring using
fake (no-DB) cursors so they run in the non-integration suite. Deterministic
calculations only; no network, no secrets.
"""
from __future__ import annotations

import pytest

from instruments import (
    THAI_CURRENCY,
    THAI_VENUES,
    active_ord_symbols,
    instrument_hash,
    instrument_identity,
    instrument_master,
    profile_taxonomy,
)
import build_dashboard as bd


# --- fake pg / cursor fixtures ------------------------------------------------


class FakeCursor:
    """Record executes + params; return queued row batches per query index.

    Rows are consumed one fetchall()/fetchone() batch per execute() call.
    If more calls than queued batches, returns empty (simulating no rows).
    Descriptions are optional; if the list is shorter than calls, falls back
    to None (so .description access doesn't crash).
    """

    def __init__(self, rows_by_call=None, descriptions=None):
        self.rows_by_call = list(rows_by_call or [])
        self.descriptions = descriptions or []
        self.calls = []  # (sql, params)
        self._call_count = 0  # how many execute() calls have happened
        self._fetched = False  # whether current batch already fetched

    @property
    def description(self):
        i = len(self.calls) - 1
        if 0 <= i < len(self.descriptions):
            return self.descriptions[i]
        return None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        self._call_count += 1
        self._fetched = False

    def fetchall(self):
        if self._fetched:
            return []
        self._fetched = True
        i = self._call_count - 1
        if i < len(self.rows_by_call):
            return self.rows_by_call[i]
        return []

    def fetchone(self):
        rows = self.fetchall() if not self._fetched else []
        return rows[0] if rows else None

    def close(self):
        pass


class FakePG:
    """A fake psycopg connection: cursor() returns a queued FakeCursor."""

    def __init__(self, cursor_factory):
        self._cursor_factory = cursor_factory

    def cursor(self):
        cur = self._cursor_factory()
        if not hasattr(self, "cursors"):
            self.cursors = []
        self.cursors.append(cur)
        return cur


def _desc(cols):
    return [(c, None, None, None, None, None, None) for c in cols]


# ---------------------------------------------------------------------------
# instruments.authority
# ---------------------------------------------------------------------------


def test_thai_taxonomy_defaults_are_canonical():
    assert THAI_VENUES == {"SET", "MAI"}
    assert THAI_CURRENCY == "THB"


def test_instrument_master_returns_active_ord_only():
    # SQL filters instrument_type='ORD' AND (status='active' OR NULL), so the
    # fake cursor returns only rows that would pass that filter.
    rows = [
        ("AOT", "ORD", "active", "SET", "equity", "THB", "Asia/Bangkok", "SET",
         "settrade_stock_master", "fresh", "ok", None),
    ]
    desc = _desc(["symbol", "instrument_type", "status", "venue", "asset_class",
                  "currency", "timezone", "session", "source", "freshness",
                  "reason", "marked_at"])
    cur = FakeCursor(rows_by_call=[rows], descriptions=[desc])
    pg = FakePG(lambda: cur)

    master = instrument_master(pg)

    assert [r["symbol"] for r in master] == ["AOT"]
    a = master[0]
    assert a["venue"] == "SET"
    assert a["asset_class"] == "equity"
    assert a["currency"] == "THB"
    assert a["status"] == "active"
    assert a["source"] == "settrade_stock_master"
    # The SQL must restrict to instrument_type='ORD' AND active.
    sql = cur.calls[0][0]
    assert "instrument_type = 'ORD'" in sql


def test_active_ord_symbols_is_bounded_universe():
    rows = [("AOT",), ("BBL",), ("CPALL",)]
    desc = _desc(["symbol"])
    cur = FakeCursor(rows_by_call=[rows], descriptions=[desc])
    pg = FakePG(lambda: cur)
    assert active_ord_symbols(pg) == ["AOT", "BBL", "CPALL"]


def test_instrument_identity_returns_canonical_or_absent():
    # First query: symbol lookup returns the row. Second query: active-ORD
    # recheck returns a row (confirming active ORD status).
    rows_lookup = [
        ("AOT", "ORD", "active", "SET", "equity", "THB", "Asia/Bangkok", "SET",
         "settrade_stock_master", "fresh", "ok", None),
    ]
    rows_active = [("ORD", "active")]

    cur = FakeCursor(rows_by_call=[rows_lookup, rows_active])
    pg = FakePG(lambda: cur)

    ident = instrument_identity(pg, "AOT")
    assert ident is not None
    assert ident["symbol"] == "AOT"
    assert ident["venue"] == "SET"
    assert ident["currency"] == "THB"
    assert ident["status"] == "active"
    # is_active_ord reflects the second (active-ORD gate) query; description is
    # captured before that query so column labels stay aligned with `row`.
    assert ident["is_active_ord"] is True
    assert ident["instrument_type"] == "ORD"

    # symbol not in master at all -> None
    cur2 = FakeCursor(rows_by_call=[[], []])
    pg2 = FakePG(lambda: cur2)
    assert instrument_identity(pg2, "ZZZZZ") is None

    # blank/None symbol -> None
    assert instrument_identity(pg, "") is None


def test_instrument_identity_reports_non_active_records_honestly():
    # Symbol present (ORD/active) but NOT active ORD on the gate -> still
    # returns the authoritative record with is_active_ord=False and its status.
    rows_lookup = [
        ("ZZZ", "ORD", "excluded", "SET", "equity", "THB", "Asia/Bangkok", "SET",
         "settrade_stock_master", "stale", "COLOR excluded by owner", None),
    ]
    rows_active = []  # active-ORD gate finds no active ORD row
    cur = FakeCursor(rows_by_call=[rows_lookup, rows_active])
    pg = FakePG(lambda: cur)
    ident = instrument_identity(pg, "ZZZ")
    assert ident is not None
    assert ident["symbol"] == "ZZZ"
    assert ident["status"] == "excluded"
    assert ident["is_active_ord"] is False


def test_instrument_identity_maps_columns_from_first_query_description():
    """Regression guard: column labels must come from the FIRST query (the
    symbol lookup), not the second active-ORD gate query. With real cursors,
    reading description AFTER the second execute silently misaligned every
    field. This fixture provides per-call descriptions to catch that."""
    lookup_desc = _desc(["symbol", "instrument_type", "status", "venue", "asset_class",
                         "currency", "timezone", "session", "source", "freshness",
                         "reason", "marked_at"])
    active_desc = _desc(["instrument_type", "status"])
    rows_lookup = [("AOT", "ORD", "active", "SET", "equity", "THB", "Asia/Bangkok",
                    "SET", "settrade_stock_master", "fresh", "ok", None)]
    rows_active = [("ORD", "active")]
    cur = FakeCursor(rows_by_call=[rows_lookup, rows_active],
                     descriptions=[lookup_desc, active_desc])
    pg = FakePG(lambda: cur)
    ident = instrument_identity(pg, "AOT")
    assert ident["symbol"] == "AOT"
    assert ident["venue"] == "SET"
    assert ident["currency"] == "THB"
    assert ident["asset_class"] == "equity"
    assert ident["is_active_ord"] is True


def test_profile_taxonomy_prefers_factsheet_over_yahoo():
    # AOT: factsheet row present; YYY: only yahoo (yfinance) row present.
    rows = [
        ("AOT", "SET", "equity", "THB", "Asia/Bangkok", "SET", "settrade_stock_master",
         "active", "Airports of Thailand", "Industrials", "Airport operators",
         "Some summary", "set_factsheet", "2026-08-21"),
        ("YYY", "SET", "equity", "THB", "Asia/Bangkok", "SET", "settrade_stock_master",
         "active", "Yahoo Co", None, None, "short", "yfinance", "2026-08-20"),
    ]
    desc = _desc(["symbol", "venue", "asset_class", "currency", "timezone", "session",
                  "inst_source", "status", "company_name", "sector", "industry",
                  "business_summary", "prof_source", "fetched_at"])
    cur = FakeCursor(rows_by_call=[rows], descriptions=[desc])
    pg = FakePG(lambda: cur)

    tax = profile_taxonomy(pg, ["AOT", "YYY"])

    a = tax["AOT"]
    assert a["venue"] == "SET"
    assert a["currency"] == "THB"
    assert a["sector"] == "Industrials"
    assert a["profile_source"] == "set_factsheet"
    assert a["missing"] is False

    y = tax["YYY"]
    # Yahoo row present but sector/industry null -> still not 'missing' overall
    # because company_name/summary exist, but profile_rank reflects lower priority.
    assert y["profile_source"] == "yfinance"
    # The factsheet-ranked source must outrank yfinance for AOT (set_factsheet
    # index 0 < yfinance index 1) even though both rows come from the same query.
    assert a["profile_rank"] < y["profile_rank"]


def test_profile_taxonomy_absent_symbol_reports_missing():
    # only AOT returns; ZZZ not in symbol_master
    rows = [
        ("AOT", "SET", "equity", "THB", "Asia/Bangkok", "SET", "settrade_stock_master",
         "active", "Airports of Thailand", "Industrials", "Airport operators",
         "summary", "set_factsheet", "2026-08-21"),
    ]
    desc = _desc(["symbol", "venue", "asset_class", "currency", "timezone", "session",
                  "inst_source", "status", "company_name", "sector", "industry",
                  "business_summary", "prof_source", "fetched_at"])
    cur = FakeCursor(rows_by_call=[rows], descriptions=[desc])
    pg = FakePG(lambda: cur)

    tax = profile_taxonomy(pg, ["AOT", "ZZZZZ"])

    assert tax["AOT"]["missing"] is False
    assert tax["ZZZZZ"]["status"] == "absent"
    assert tax["ZZZZZ"]["missing"] is True
    assert tax["ZZZZZ"]["venue"] is None  # never fabricated


def test_profile_taxonomy_no_profile_row_still_reports_missing():
    # active ORD in master but NO company_profiles row -> missing=True, no
    # fabricated sector/industry.
    rows = [
        ("AOT", "SET", "equity", "THB", "Asia/Bangkok", "SET", "settrade_stock_master",
         "active", None, None, None, None, None, None),
    ]
    desc = _desc(["symbol", "venue", "asset_class", "currency", "timezone", "session",
                  "inst_source", "status", "company_name", "sector", "industry",
                  "business_summary", "prof_source", "fetched_at"])
    cur = FakeCursor(rows_by_call=[rows], descriptions=[desc])
    pg = FakePG(lambda: cur)

    tax = profile_taxonomy(pg, ["AOT"])
    assert tax["AOT"]["missing"] is True
    assert tax["AOT"]["sector"] is None
    assert tax["AOT"]["industry"] is None


def test_instrument_hash_is_deterministic():
    recs = [
        {"symbol": "AOT", "source": "settrade_stock_master", "status": "active",
         "freshness": "fresh"},
        {"symbol": "BBL", "source": "settrade_stock_master", "status": "active",
         "freshness": "fresh"},
    ]
    h1 = instrument_hash(recs)
    h2 = instrument_hash(list(reversed(recs)))
    assert h1 == h2
    assert len(h1) == 16
    # Adding a new record changes the hash.
    recs2 = recs + [{"symbol": "CPALL", "source": "settrade_stock_master",
                     "status": "active", "freshness": "fresh"}]
    assert instrument_hash(recs2) != h1


def test_refresh_status_handles_missing_table():
    # to_regclass returns None -> table missing branch. The first fetchone
    # returns the row (None,) i.e. a 1-tuple whose [0] is None.
    cur = FakeCursor(rows_by_call=[[(None,)], [], [], []])
    pg = FakePG(lambda: cur)
    refresh = __import__("instruments").refresh_status(pg)
    assert refresh["table"] == "symbol_master"
    assert refresh["exists"] is False
    assert refresh["status"] == "unavailable"


# ---------------------------------------------------------------------------
# build_dashboard.snapshots taxonomy wiring
# ---------------------------------------------------------------------------


def test_snapshots_returns_taxonomy_fields_from_authority_join():
    # Single symbol, rn=1 row (daily) carrying taxonomy columns.
    rows = [(
        "AOT", "2026-08-21", 52.5, 20_000_000, 1,
        "Industrials", "Airport operators", 5_000_000_000,
        0.60, 0.20, "Airports of Thailand", "settrade_stock_master",
        "2026-08-21",
        "SET", "equity", "THB", "Asia/Bangkok", "SET", "settrade_stock_master",
    )]
    desc = _desc(["symbol", "date", "close", "volume", "rn", "sector", "industry",
                  "market_cap", "free_float_pct", "foreign_limit_pct",
                  "company_name", "profile_source", "profile_fetched_at",
                  "venue", "asset_class", "currency", "timezone", "session",
                  "inst_source"])
    cur_main = FakeCursor(rows_by_call=[rows], descriptions=[desc])

    def cursor_factory():
        return cur_main

    pg = FakePG(cursor_factory)

    snap = bd.snapshots(pg, ["AOT"])
    aot = snap["AOT"]

    # Price + daily fields preserved
    assert aot["close"] == 52.5
    assert aot["volume"] == 20_000_000
    assert aot["sector"] == "Industrials"
    assert aot["industry"] == "Airport operators"

    # P0-2 taxonomy fields wired from symbol_master authority
    assert aot["venue"] == "SET"
    assert aot["asset_class"] == "equity"
    assert aot["currency"] == "THB"
    assert aot["timezone"] == "Asia/Bangkok"
    assert aot["session"] == "SET"
    assert aot["instrument_source"] == "settrade_stock_master"
    assert aot["companyName"] == "Airports of Thailand"
    assert aot["profileSource"] == "settrade_stock_master"


def test_snapshots_falls_back_to_company_profiles_without_clobbering():
    """When symbol_master is absent, company_profiles still enriches but does
    NOT inject invented taxonomy (venue/asset_class remain None)."""
    # rn=1 row: no sm join -> all taxonomy None, but company_profiles has name.
    rows = [(
        "AOT", "2026-08-21", 52.5, 20_000_000, 1,
        None, None, 5_000_000_000, None, None, "Airports of Thailand", "yfinance",
        "2026-08-20",
        None, None, None, None, None, None,
    )]
    desc = _desc(["symbol", "date", "close", "volume", "rn", "sector", "industry",
                  "market_cap", "free_float_pct", "foreign_limit_pct",
                  "company_name", "profile_source", "profile_fetched_at",
                  "venue", "asset_class", "currency", "timezone", "session",
                  "inst_source"])
    cur_main = FakeCursor(rows_by_call=[rows], descriptions=[desc])
    pg = FakePG(lambda: cur_main)

    snap = bd.snapshots(pg, ["AOT"])
    aot = snap["AOT"]
    assert aot["close"] == 52.5
    # company_profiles enrichment fills companyName even without symbol_master
    assert aot["companyName"] == "Airports of Thailand"
    assert aot["profileSource"] == "yfinance"
    # Taxonomy must NOT be fabricated — venue stays None.
    assert aot["venue"] is None
    assert aot["asset_class"] is None
    assert aot["currency"] is None


def test_snapshots_previous_close_from_rn2():
    rows = [
        ("AOT", "2026-08-21", 52.5, 20_000_000, 1,
         "Industrials", "Airport operators", 5_000_000_000, 0.6, 0.2, "Co",
         "settrade_stock_master", "2026-08-21",
         "SET", "equity", "THB", "Asia/Bangkok", "SET", "settrade_stock_master"),
        ("AOT", "2026-08-20", 52.0, 18_000_000, 2,
         "Industrials", "Airport operators", None, None, None, "Co",
         "settrade_stock_master", "2026-08-20",
         "SET", "equity", "THB", "Asia/Bangkok", "SET", "settrade_stock_master"),
    ]
    desc = _desc(["symbol", "date", "close", "volume", "rn", "sector", "industry",
                  "market_cap", "free_float_pct", "foreign_limit_pct",
                  "company_name", "profile_source", "profile_fetched_at",
                  "venue", "asset_class", "currency", "timezone", "session",
                  "inst_source"])
    cur = FakeCursor(rows_by_call=[rows], descriptions=[desc])
    pg = FakePG(lambda: cur)

    snap = bd.snapshots(pg, ["AOT"])
    aot = snap["AOT"]
    assert aot["daily_close"] == 52.5
    assert aot["previous_close"] == 52.0
    assert aot["daily_previous_close"] == 52.0
    # taxonomy from rn=1 row
    assert aot["venue"] == "SET"
    assert aot["currency"] == "THB"
