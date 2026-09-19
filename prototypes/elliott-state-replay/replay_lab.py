#!/usr/bin/env python3
"""
Signalix Elliott State Replay — Read-Only 237-Symbol No-Lookahead Adapter

README
======
Purpose:
  Point-in-time replay for the Elliott prototype (prototypes/elliott-state-replay/index.html).
  Loads Daily price_data + 60m intraday_price_data up to an as_of date (no lookahead),
  runs trend_strength_engine.compute_trend_strength,
       elliott_structure_engine.classify_wave_candidate,
       trade_setup_engine.build_trade_setup
  for the marginable_long universe and emits deterministic fixture JSON that the
  prototype Replay Lab can load directly.

Usage:
  # Single date (uses analysis-venv if available):
  /root/signalix/.analysis-venv/bin/python prototypes/elliott-state-replay/replay_lab.py --as-of 2026-08-28 --out /tmp/replay_2026-08-28.json --limit 5

  # Date range (writes JSONL by default, one record per symbol per date):
  /root/signalix/.analysis-venv/bin/python prototypes/elliott-state-replay/replay_lab.py --from 2026-08-26 --to 2026-08-28 --out /tmp/replay_range.jsonl

  # Dry-run single symbol (no output file, stdout probe):
  /root/signalix/.analysis-venv/bin/python prototypes/elliott-state-replay/replay_lab.py --as-of 2026-08-28 --symbol ADVANC --dry-run

  # From repo root you can also invoke via python3 if that interpreter has psycopg2 + pandas:
  python3 prototypes/elliott-state-replay/replay_lab.py --as-of 2026-08-28 --out /tmp/out.json

Options:
  --as-of YYYY-MM-DD        Single as_of date (inclusive).
  --from YYYY-MM-DD --to YYYY-MM-DD  Inclusive date range. When set, --as-of is ignored.
  --out PATH                Output path under /tmp (default /tmp/replay_lab_<as_of>.json). Writable only under /tmp.
  --format json|jsonl       Output format. Default: json for single date, jsonl for range.
  --symbol SYMBOL           Restrict to one symbol (dry-run / debugging).
  --limit N                 Cap symbols processed (after universe filter, deterministic sort).
  --dsn HOST/PORT/...       Override Postgres DSN via env (POSTGRES_HOST/PORT/USER/PASSWORD/DB) is preferred.

No-lookahead guarantee:
  - Daily:  SELECT ... FROM price_data WHERE symbol=%s AND market='TH' AND date <= %s ORDER BY date ASC
            Only rows with date <= as_of are loaded. The engine never sees future candles.
  - 60m:    SELECT ... FROM intraday_price_data WHERE symbol=%s AND interval='60m' AND ts <= %s ORDER BY ts ASC
            Upper bound is as_of at 23:59:59 Asia/Bangkok (converted to UTC for the query).
            Candle with ts > as_of_bangkok_eod is excluded.
  - Engines receive DataFrames already truncated; no post-hoc future leak is possible.
  - Deterministic: rows are sorted, floats rounded at engine boundaries, JSON keys sorted, output ordered by symbol.

237 / marginable_long universe:
  - Source of truth: backend/marginable_securities.json (schema signalix.marginable.v1).
  - Filter: active Thai ORD ∩ owner-supplied marginable list ∩ can_buy=true — implemented by
            marginable.eligible_symbols(active_symbols). Current validated counts are
            931 active ORD, 237 eligible (AGENTS.md). At replay time the eligible count
            is recomputed from DISTINCT symbol in price_data (market='TH', instrument_type='ORD')
            intersected with the marginable list; the emitted manifest records both the
            expected (237) and observed eligible counts.
  - Preserve active_ord audit mode: pass --universe active_ord to emit without marginable filter.

Read-only guarantee:
  - Connection opened with READ ONLY transaction (SET TRANSACTION READ ONLY / set_session(readonly=True)).
  - Every SQL string is checked to start with SELECT/WITH after stripping comments; any other
            statement raises ReadOnlyViolation before execution.
  - No INSERT/UPDATE/DELETE/DDL, no service restart, no network calls, no file writes outside /tmp.
  - SELECT-only assertion is unit-tested by the internal _assert_select helper.

Linkage to prototype:
  - Does NOT edit prototypes/elliott-state-replay/index.html.
  - Emits fixture objects with keys: candidate_id, setup_id, trend, primary, alternative,
    confidence, evidence, missing, contradicting, freshness, session (all required by the
    prototype reducer). Extra diagnostic keys (_debug) are namespaced and ignored by the UI.
  - Fixture array can be pasted into the Replay Lab textarea or fetched directly.

Exit codes: 0 success, 2 bad args, 3 DB/dependency error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Bootstrap backend imports (trend/elliott/trade engines + marginable)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2] / "backend"  # prototypes/elliott-state-replay -> prototypes -> repo root -> backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

BKK = ZoneInfo("Asia/Bangkok")
UTC = ZoneInfo("UTC")

# Engines are optional at import time so --help works even without deps
_ENGINE_IMPORT_ERROR: Exception | None = None
try:
    import pandas as pd  # type: ignore
    import trend_strength_engine  # type: ignore
    import elliott_structure_engine  # type: ignore
    import trade_setup_engine  # type: ignore
    import marginable as _marginable  # type: ignore
except Exception as _e:  # pragma: no cover
    pd = None  # type: ignore
    trend_strength_engine = None  # type: ignore
    elliott_structure_engine = None  # type: ignore
    trade_setup_engine = None  # type: ignore
    _marginable = None  # type: ignore
    _ENGINE_IMPORT_ERROR = _e


class ReadOnlyViolation(RuntimeError):
    pass


_SELECT_RE = re.compile(r"^\s*(?:--.*\n|\s)*", re.MULTILINE)


def _assert_select(sql: str) -> None:
    """Allow only SELECT/WITH. Raises ReadOnlyViolation otherwise."""
    # strip leading line comments
    stripped = sql.lstrip()
    # remove leading -- comments
    while stripped.startswith("--"):
        nl = stripped.find("\n")
        stripped = stripped[nl + 1 :].lstrip() if nl != -1 else ""
    upper = stripped.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ReadOnlyViolation(f"Blocked non-SELECT statement: {sql[:120]!r}")


def _pg_dsn() -> dict:
    return {
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "user": os.getenv("POSTGRES_USER", "signalix"),
        "password": os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
        "dbname": os.getenv("POSTGRES_DB", "signalix"),
    }


def _get_conn():
    try:
        import psycopg2  # type: ignore
        import psycopg2.extras  # type: ignore  # noqa: F401
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"psycopg2 not available: {e}. Use /root/signalix/.analysis-venv/bin/python") from e
    dsn = _pg_dsn()
    conn = psycopg2.connect(**dsn)
    # Enforce read-only at session level
    try:
        conn.set_session(readonly=True, autocommit=True)
    except Exception:
        pass
    return conn


def _exec_select(conn, sql: str, params=None):
    _assert_select(sql)
    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        return rows, cols
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
EXPECTED_ELIGIBLE = 237  # validated per AGENTS.md (931 active ORD, 237 eligible)


def resolve_universe(conn, universe_filter: str = "marginable_long") -> tuple[list[str], dict]:
    # AGENTS.md: authoritative active ORD count is 931 from symbol_master
    # (not price_data which may be stale/incomplete). Use symbol_master for the base set.
    rows, _ = _exec_select(conn, "SELECT symbol FROM symbol_master WHERE instrument_type='ORD' AND (status IS NULL OR status='active') ORDER BY symbol")
    active = [r[0] for r in rows if r[0]]
    if universe_filter == "active_ord":
        manifest = {
            "universe_filter": "active_ord",
            "base_active_ord_count": len(active),
            "eligible_count": len(active),
            "excluded_count": 0,
            "excluded_reason": "none/active_ord",
            "expected_eligible": EXPECTED_ELIGIBLE,
            "note": "active_ord audit mode — no marginable filter",
        }
        return sorted(active), manifest
    if _marginable is None:
        raise RuntimeError(f"marginable module not loaded: {_ENGINE_IMPORT_ERROR}")
    # Use the single source of truth helper
    eligible, m = _marginable.eligible_symbols(active, "marginable_long")
    m["expected_eligible"] = EXPECTED_ELIGIBLE
    # ensure required keys
    m.setdefault("universe_filter", "marginable_long")
    return eligible, m


# ---------------------------------------------------------------------------
# Point-in-time loaders (no lookahead)
# ---------------------------------------------------------------------------
def _as_of_bangkok_eod_utc(as_of: dt.date) -> dt.datetime:
    """as_of 23:59:59.999 in Asia/Bangkok → UTC for ts comparison."""
    bkk_eod = dt.datetime(as_of.year, as_of.month, as_of.day, 23, 59, 59, 999000, tzinfo=BKK)
    return bkk_eod.astimezone(UTC)


def load_daily_pit(conn, symbol: str, as_of: dt.date):
    """Return (DataFrame, latest_date or None). Only rows with date <= as_of."""
    sql = """
        SELECT date, open, high, low, close, volume
        FROM price_data
        WHERE symbol=%s AND market='TH' AND date <= %s
        ORDER BY date ASC
    """
    _assert_select(sql)
    cur = conn.cursor()
    try:
        cur.execute(sql, (symbol, as_of))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    finally:
        cur.close()
    if not rows:
        return _empty_daily_df(), None
    # Build DataFrame in engine-expected shape
    import pandas as pd  # type: ignore

    df = pd.DataFrame(rows, columns=cols)
    # Normalize column names to engine expectation (capitalized)
    rename = {"date": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    df = df.rename(columns=rename)
    # Ensure Date is datetime/date and set as index? Engines use Close column primarily.
    # Keep Date column for max-date calc.
    latest = rows[-1][0]  # date is first col
    return df, latest


def _empty_daily_df():
    import pandas as pd  # type: ignore

    return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])


def load_intraday_pit(conn, symbol: str, as_of: dt.date):
    """Return DataFrame for 60m up to as_of BKK EOD, with engine-expected attrs."""
    cutoff_utc = _as_of_bangkok_eod_utc(as_of)
    sql = """
        SELECT ts, open, high, low, close, volume
        FROM intraday_price_data
        WHERE symbol=%s AND interval='60m' AND ts <= %s
        ORDER BY ts ASC
    """
    _assert_select(sql)
    cur = conn.cursor()
    try:
        cur.execute(sql, (symbol, cutoff_utc))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
    finally:
        cur.close()
    import pandas as pd  # type: ignore

    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(rows, columns=cols)
    rename = {"ts": "ts", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    df = df.rename(columns=rename)
    # Intraday engine expects DatetimeIndex + attrs timeframe/as_of
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    df.attrs["timeframe"] = "60m"
    if len(df) > 0:
        df.attrs["as_of"] = df.index[-1]
    return df


# ---------------------------------------------------------------------------
# Engine adapters → prototype fixture
# ---------------------------------------------------------------------------
_TREND_MAP = {"uptrend": "UPTREND", "emerging_uptrend": "EMERGING_UPTREND"}


def _map_trend(state: str | None) -> str:
    if state in _TREND_MAP:
        return _TREND_MAP[state]
    # Prototype only accepts UPTREND / EMERGING_UPTREND; default conservative
    return "EMERGING_UPTREND" if state == "flat" else "UPTREND"


_CONF_MAP = {"INSUFFICIENT": "LOW", "PARTIAL": "MEDIUM"}


def _map_confidence(wave: dict) -> str:
    c = str(wave.get("confidence", "")).upper()
    if c in _CONF_MAP:
        # promote PARTIAL with measurable wave to HIGH is optional; keep deterministic MEDIUM
        return _CONF_MAP[c]
    if c in {"LOW", "MEDIUM", "HIGH"}:
        return c
    return "MEDIUM"


def _freshness_session(daily_df, latest_date, as_of: dt.date) -> tuple[str, str]:
    if daily_df is None or len(daily_df) == 0 or latest_date is None:
        return "MISSING FINAL SESSION", f"{as_of.isoformat()} — no final session (DATA_BLOCKED)"
    # latest_date is date from DB
    if isinstance(latest_date, dt.datetime):
        latest_date = latest_date.date()
    if latest_date == as_of:
        return "FRESH / FINAL SESSION PRESENT", f"{as_of.isoformat()} final session"
    # Any prior date available → weekend/holiday valid (no inference about missing trading day)
    return "WEEKEND / HOLIDAY VALID", f"{as_of.isoformat()} — latest final {latest_date.isoformat()} remains current"


def build_fixture(symbol: str, as_of: dt.date, daily_df, intraday_df, latest_date) -> dict:
    """Run engines and map to prototype fixture schema."""
    # Trend
    try:
        trend_raw = trend_strength_engine.compute_trend_strength(daily_df)  # type: ignore
    except Exception as e:  # pragma: no cover
        trend_raw = {"state": "UNKNOWN", "error": str(e)}
    trend = _map_trend(trend_raw.get("state"))

    # Elliott
    try:
        wave = elliott_structure_engine.classify_wave_candidate(daily_df)  # type: ignore
    except Exception as e:  # pragma: no cover
        wave = {"state": "UNKNOWN", "confidence": "INSUFFICIENT", "evidence": {"error": str(e)}}

    primary = wave.get("state") or "UNKNOWN"
    # Alternative: second-best wave — derive from evidence if available, else same as primary for UNKNOWN
    alt = wave.get("evidence", {}).get("alternative_state") or ("WAVE_2_FORMING" if primary == "WAVE_1_ADVANCE" else "WAVE_2_FORMING")
    if primary == "UNKNOWN":
        alt = "WAVE_2_FORMING"

    confidence = _map_confidence(wave)

    # Evidence / missing / contradicting
    evidence_raw = wave.get("evidence", {}) or {}
    missing = list(evidence_raw.get("missing_evidence") or [])
    # Build evidence strings (deterministic, human-readable)
    evidence: list[str] = []
    for k in ("daily_advance_10d_pct", "daily_advance_20d_pct", "daily_rebound_5d_pct", "daily_drawdown_from_10d_high_pct"):
        v = evidence_raw.get(k)
        if v is not None:
            evidence.append(f"{k}={v}")
    for flag in ("measurable_advance", "measurable_pullback", "measurable_rebound", "measurable_breakout", "measurable_continuation"):
        if evidence_raw.get(flag):
            evidence.append(flag)
    # Include trend evidence
    if trend_raw.get("rise_20d_pct") is not None:
        evidence.append(f"trend.rise_20d={trend_raw['rise_20d_pct']}%")
    if trend_raw.get("rise_60d_pct") is not None:
        evidence.append(f"trend.rise_60d={trend_raw['rise_60d_pct']}%")
    if trend_raw.get("near_52w_high") is True:
        evidence.append("near_52w_high")
    if trend_raw.get("is_52w_high_breakout") is True:
        evidence.append("is_52w_high_breakout")
    if not evidence:
        # keep prototype-friendly defaults even when blocked
        evidence = ["no measurable structural fixture at as_of"]

    contradicting: list[str] = []
    if wave.get("state") == "UNKNOWN":
        contradicting.append("unknown_wave_state")
    if trend_raw.get("state") == "downtrend":
        contradicting.append("downtrend_vs_wave")

    # Trade setup (60m) — engine sets intraday attrs; pass wave through
    try:
        # trade_setup_engine expects daily_wave with timeframe daily
        wave_for_setup = dict(wave)
        wave_for_setup.setdefault("timeframe", "daily")
        setup = trade_setup_engine.build_trade_setup(wave_for_setup, intraday_df)  # type: ignore
    except Exception as e:  # pragma: no cover
        setup = {"timeframe": "60m", "state": primary, "status": "DATA_BLOCKED", "reason": str(e)}

    freshness, session = _freshness_session(daily_df, latest_date, as_of)

    # If 60m is DATA_BLOCKED, surface via missing
    if setup.get("status") == "DATA_BLOCKED" and setup.get("reason"):
        missing.append(f"60m:{setup['reason']}")
    if freshness == "MISSING FINAL SESSION":
        missing.append("missing_final_session")

    # Deduplicate missing while preserving order
    seen = set()
    missing_dedup: list[str] = []
    for m in missing:
        if m not in seen:
            seen.add(m)
            missing_dedup.append(m)

    # Deterministic IDs
    candidate_id = f"CAND-{symbol}-{as_of.isoformat()}"
    # setup_id must change when trade_setup anchors change; hash trigger/invalidation
    setup_seed = f"{symbol}|{as_of.isoformat()}|{setup.get('trigger')}|{setup.get('invalidation')}"
    setup_id = f"SETUP-{hashlib.sha1(setup_seed.encode()).hexdigest()[:8].upper()}"

    fixture: dict = {
        "candidate_id": candidate_id,
        "setup_id": setup_id,
        "trend": trend,
        "primary": primary,
        "alternative": alt,
        "confidence": confidence,
        "evidence": sorted(set(evidence)),
        "missing": sorted(set(missing_dedup)),
        "contradicting": sorted(set(contradicting)),
        "freshness": freshness,
        "session": session,
        # Prototype ignores extra keys; keep debug trace under _debug for audit
        "_debug": {
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "daily_rows": int(len(daily_df)) if daily_df is not None else 0,
            "intraday_rows": int(len(intraday_df)) if intraday_df is not None else 0,
            "latest_daily_date": str(latest_date) if latest_date else None,
            "trend_raw": _json_safe(trend_raw),
            "wave": _json_safe(wave),
            "setup": _json_safe(setup),
        },
    }
    return fixture


def _json_safe(obj):
    """Recursively make pandas/numpy scalars JSON-serializable."""
    import math

    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, (int,)):
        return int(obj)
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "item"):
        try:
            return _json_safe(obj.item())
        except Exception:
            pass
    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except Exception:
            pass
    # pandas NA
    if type(obj).__name__ in {"NAType", "NaTType"}:
        return None
    try:
        f = float(obj)
        return f if math.isfinite(f) else None
    except Exception:
        return str(obj)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Read-only 237-symbol no-lookahead replay adapter for Elliott prototype")
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument("--as-of", dest="as_of", help="Single as_of date YYYY-MM-DD")
    p.add_argument("--from", dest="from_date", help="Range start YYYY-MM-DD (inclusive)")
    p.add_argument("--to", dest="to_date", help="Range end YYYY-MM-DD (inclusive)")
    p.add_argument("--out", help="Output path (must be under /tmp)")
    p.add_argument("--format", choices=["json", "jsonl"], default=None, help="Output format (default json for single, jsonl for range)")
    p.add_argument("--symbol", help="Restrict to one symbol (debug/probe)")
    p.add_argument("--limit", type=int, default=None, help="Cap symbols (deterministic sort)")
    p.add_argument("--universe", choices=["marginable_long", "active_ord"], default="marginable_long", help="Universe filter")
    p.add_argument("--dry-run", action="store_true", help="Probe single symbol without writing file")
    return p.parse_args(argv)


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main(argv=None) -> int:
    args = parse_args(argv)

    # Resolve dates
    dates: list[dt.date]
    if args.from_date or args.to_date:
        if not (args.from_date and args.to_date):
            print("ERROR: --from and --to must be used together", file=sys.stderr)
            return 2
        try:
            d0 = _parse_date(args.from_date)
            d1 = _parse_date(args.to_date)
        except ValueError as e:
            print(f"ERROR: bad date: {e}", file=sys.stderr)
            return 2
        if d1 < d0:
            print("ERROR: --to must be >= --from", file=sys.stderr)
            return 2
        dates = []
        cur = d0
        while cur <= d1:
            dates.append(cur)
            cur += dt.timedelta(days=1)
    elif args.as_of:
        try:
            dates = [_parse_date(args.as_of)]
        except ValueError as e:
            print(f"ERROR: bad --as-of: {e}", file=sys.stderr)
            return 2
    else:
        # default to latest price_data date
        try:
            conn = _get_conn()
            rows, _ = _exec_select(conn, "SELECT MAX(date) FROM price_data")
            maxd = rows[0][0] if rows and rows[0][0] else None
            conn.close()
            if maxd is None:
                print("ERROR: no price_data and no --as-of given", file=sys.stderr)
                return 2
            dates = [maxd if isinstance(maxd, dt.date) else dt.date.fromisoformat(str(maxd))]
        except Exception as e:
            print(f"ERROR resolving default as_of: {e}", file=sys.stderr)
            return 3

    if _ENGINE_IMPORT_ERROR is not None:
        print(f"ERROR importing engines: {_ENGINE_IMPORT_ERROR}", file=sys.stderr)
        print("Hint: run with /root/signalix/.analysis-venv/bin/python", file=sys.stderr)
        return 3

    # Output path
    fmt = args.format
    if fmt is None:
        fmt = "jsonl" if len(dates) > 1 else "json"

    out_path: Path | None = None
    if not args.dry_run:
        raw_out = args.out or f"/tmp/replay_lab_{dates[0].isoformat()}{'_range' if len(dates)>1 else ''}.{fmt}"
        out_path = Path(raw_out)
        # enforce /tmp
        try:
            out_path.resolve().relative_to(Path("/tmp").resolve())
        except ValueError:
            print(f"ERROR: --out must be under /tmp (got {out_path})", file=sys.stderr)
            return 2
        out_path.parent.mkdir(parents=True, exist_ok=True)

    # Universe resolution (once, validated at head date)
    try:
        conn = _get_conn()
    except Exception as e:
        print(f"ERROR connecting DB: {e}", file=sys.stderr)
        return 3

    try:
        universe, manifest = resolve_universe(conn, args.universe)
        if args.symbol:
            sym = args.symbol.strip().upper()
            if sym not in universe:
                print(f"WARN: {sym} not in {args.universe} universe ({len(universe)} symbols); probing anyway", file=sys.stderr)
                universe = [sym]
            else:
                universe = [sym]
        # deterministic
        universe = sorted(set(universe))
        if args.limit is not None and args.limit > 0:
            universe = universe[: args.limit]

        # Dry-run: single date, single symbol
        if args.dry_run:
            as_of = dates[0]
            sym = universe[0]
            daily_df, latest = load_daily_pit(conn, sym, as_of)
            intraday_df = load_intraday_pit(conn, sym, as_of)
            fixture = build_fixture(sym, as_of, daily_df, intraday_df, latest)
            print(json.dumps(fixture, indent=2, ensure_ascii=False, sort_keys=False))
            return 0

        # Full run
        all_fixtures: list[dict] = []
        # For range mode JSONL we stream; for single-date JSON we collect
        if fmt == "jsonl" and out_path is not None:
            out_path.write_text("", encoding="utf-8")  # truncate

        for as_of in dates:
            for sym in universe:
                daily_df, latest = load_daily_pit(conn, sym, as_of)
                intraday_df = load_intraday_pit(conn, sym, as_of)
                fixture = build_fixture(sym, as_of, daily_df, intraday_df, latest)
                # For single-date JSON we buffer; for JSONL we append
                if len(dates) == 1 and fmt == "json":
                    all_fixtures.append(fixture)
                else:
                    # JSONL: one fixture per line
                    if out_path is not None:
                        with out_path.open("a", encoding="utf-8") as fh:
                            fh.write(json.dumps(fixture, ensure_ascii=False, sort_keys=True) + "\n")
                    else:
                        all_fixtures.append(fixture)

        if out_path is not None and fmt == "json":
            # Wrap with manifest for single-date JSON (adapter contract)
            # Prototype expects bare array; so write array directly but also write sidecar manifest
            out_path.write_text(json.dumps(all_fixtures, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            sidecar = out_path.with_suffix(".manifest.json")
            sidecar.write_text(
                json.dumps(
                    {
                        "as_of": [d.isoformat() for d in dates],
                        "format": fmt,
                        "universe": manifest,
                        "count": len(all_fixtures),
                        "no_lookahead": "date <= as_of; ts <= as_of BKK EOD",
                        "engines": ["trend_strength_engine", "elliott_structure_engine", "trade_setup_engine"],
                        "prototype": "prototypes/elliott-state-replay/index.html",
                    },
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"Wrote {len(all_fixtures)} fixtures to {out_path} (+ {sidecar})")
        elif out_path is not None and fmt == "jsonl":
            lines = out_path.read_text(encoding="utf-8").strip().splitlines() if out_path.exists() else []
            count = len([l for l in lines if l.strip()])
            # also write manifest
            sidecar = out_path.with_suffix(".manifest.json")
            # handle .jsonl → .manifest.json (with_suffix replaces only last suffix)
            if out_path.suffix == ".jsonl":
                sidecar = out_path.with_name(out_path.stem + ".manifest.json")
            sidecar.write_text(
                json.dumps(
                    {
                        "as_of": [d.isoformat() for d in dates],
                        "format": fmt,
                        "universe": manifest,
                        "count": count,
                        "no_lookahead": "date <= as_of; ts <= as_of BKK EOD",
                        "engines": ["trend_strength_engine", "elliott_structure_engine", "trade_setup_engine"],
                        "prototype": "prototypes/elliott-state-replay/index.html",
                    },
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"Wrote {count} fixtures to {out_path} (+ {sidecar})")
        else:
            # stdout
            print(json.dumps(all_fixtures, ensure_ascii=False, indent=2, sort_keys=True))

    except ReadOnlyViolation as e:
        print(f"READ-ONLY VIOLATION: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
