"""
Signalix — incremental, idempotent SET EOD updater.

Fetches only trade days STRICTLY AFTER MAX(date) in price_data and inserts them
with ON CONFLICT DO NOTHING, so it is safe to re-run at any time.

SOURCES (priority order, --source to force one)
  1. "local"     : CSV drop directories (/root/signalix/uploads and the seed dir).
                   Files named set-history_EOD_YYYY-MM-DD.csv, same format as ingest.py.
                   Owner pushes files via upload_server.py. Zero deps, most reliable.
  2. "drive"     : re-list the Google Drive archive folder with gdown and pull any
                   file newer than MAX(date) into the drop dir, then ingest it.
  3. "settrade"  : preferred automated source. Uses Settrade Open API v2 SDK
                   get_candlestick(... interval='1d', normalized=True) for
                   active symbols already known in price_data.
  4. "yfinance"  : fallback. Downloads <SYMBOL>.BK daily bars for symbols already
                   present in price_data. Covers ordinary shares well, DR coverage
                   is partial, and it can never discover brand-new listings.

NOT USED: www.set.or.th official API/CSV download. It sits behind Imperva/Incapsula
bot protection (all server-side requests return 403 + an _Incapsula_Resource
challenge page), so it cannot be automated headlessly without a real browser
session/cookie. See report.

Usage:
  python update_data.py --dry-run
  python update_data.py --since 2026-07-28
  python update_data.py --source drive
  python update_data.py --scan          # trigger a rescan after loading (off by default)
"""
import os
import re
import csv
import sys
import glob
import argparse
import datetime as dt
import json
import time
import signal
import random
import uuid
import concurrent.futures
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

# Load Settrade creds from .env (systemd provides PG env vars directly)
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)  # never override systemd Environment=
except Exception:
    pass

# ---------- config ----------
def _pg_config():
    """Read PG config at call time so systemd Environment= takes precedence."""
    return dict(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "signalix"),
        password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
        dbname=os.getenv("POSTGRES_DB", "signalix"),
    )

PG = _pg_config()
DROP_DIRS = [
    os.getenv("UPLOAD_DIR", "/root/signalix/uploads"),
    os.getenv("SEED_DIR", "/root/signalix/seed_data/set-archive_EOD"),
    # Owner-provided 2026 archive extracted from the "New Try.zip" drop.
    # Covers 2026-01-05..2026-07-27 with native Thai EOD data (preferred over yfinance).
    "/root/signalix/seed_zip/extracted",
]
DRIVE_URL = os.getenv(
    "DRIVE_URL",
    "https://drive.google.com/drive/folders/1vpFNBSUsGEKO7uIATwIINnCtuiWN6Nqe",
)
SCAN_URL = os.getenv("SCAN_URL", "http://localhost:8000/scan")
FNAME_RE = re.compile(r"set-history_EOD_(\d{4}-\d{2}-\d{2})\.csv$", re.I)
BANGKOK_TZ = dt.timezone(dt.timedelta(hours=7))
SETTRADE_ENV_KEYS = ("SETTRADE_APP_ID", "SETTRADE_APP_SECRET", "SETTRADE_BROKER_ID", "SETTRADE_APP_CODE")
SETTRADE_INTERVAL = os.getenv("SETTRADE_INTERVAL", "1d")
SETTRADE_NORMALIZED = os.getenv("SETTRADE_NORMALIZED", "true").lower() not in ("0", "false", "no")
SETTRADE_SLEEP_SECONDS = float(os.getenv("SETTRADE_SLEEP_SECONDS", "0.25"))
SETTRADE_REQUEST_TIMEOUT = int(os.getenv("SETTRADE_REQUEST_TIMEOUT", "35"))
SETTRADE_DAILY_WORKERS = int(os.getenv("SETTRADE_DAILY_WORKERS", "10"))
SETTRADE_BATCH_SIZE = int(os.getenv("SETTRADE_BATCH_SIZE", "10"))
SETTRADE_BATCH_DELAY_SECONDS = float(os.getenv("SETTRADE_BATCH_DELAY_SECONDS", "0.5"))
SETTRADE_INTRADAY_WORKERS = int(os.getenv("SETTRADE_INTRADAY_WORKERS", "1"))
SETTRADE_BATCH_JITTER_SECONDS = float(os.getenv("SETTRADE_BATCH_JITTER_SECONDS", "0.25"))
SETTRADE_SESSION_RETRIES = int(os.getenv("SETTRADE_SESSION_RETRIES", "1"))
SETTRADE_RETRY_BACKOFF_SECONDS = float(os.getenv("SETTRADE_RETRY_BACKOFF_SECONDS", "2.0"))


class SettradeRequestTimeout(TimeoutError):
    """A single unreachable Settrade request must not stall the whole market job."""


@contextmanager
def settrade_request_timeout(seconds=SETTRADE_REQUEST_TIMEOUT):
    """Bound synchronous SDK calls in this single-process systemd job."""
    if seconds <= 0:
        yield
        return
    def expire(_signum, _frame):
        raise SettradeRequestTimeout(f"Settrade request exceeded {seconds}s")
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)

# ---------- classify: EXACT copy of ingest.py rules ----------
SUFFIXES = ("-O", "-F", "-M", "-P")
WARRANT_CP_RE = re.compile(r"\d{2}[CP]\d{2}")


def classify(ticker: str):
    """Return (keep: bool, type: 'ORD'|'DR'|None)."""
    if ticker.endswith(SUFFIXES):
        return False, None
    if ticker.startswith(("!", "$")):
        return False, None
    if ticker[0:1].isdigit():
        return False, None
    if "-W" in ticker:
        return False, None
    if WARRANT_CP_RE.search(ticker):
        return False, None
    if ticker.isalpha():
        return True, "ORD"
    return True, "DR"


# ---------- db ----------
def get_pg():
    return psycopg2.connect(**_pg_config())


def get_max_date(pg):
    cur = pg.cursor()
    cur.execute("SELECT MAX(date) FROM price_data")
    d = cur.fetchone()[0]
    cur.close()
    return d


def get_overlap_cutoff(pg, sessions=3):
    """Return the session immediately before the latest N trading sessions."""
    cur = pg.cursor()
    cur.execute(
        "SELECT date FROM (SELECT DISTINCT date FROM price_data "
        "ORDER BY date DESC OFFSET %s LIMIT 1) d", (int(sessions),)
    )
    row = cur.fetchone()
    cur.close()
    return row[0] if row else get_max_date(pg) - dt.timedelta(days=1)


def insert_rows(pg, rows, batch=1000):
    if not rows:
        return 0
    cur = pg.cursor()
    market_rows = [("TH",) + tuple(row) for row in rows]
    try:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO price_data "
            "(market,symbol,date,open,high,low,close,volume,instrument_type) "
            "VALUES %s ON CONFLICT (market,symbol,date) DO NOTHING",
            market_rows,
            page_size=batch,
        )
        pg.commit()
        return len(rows)
    except Exception:
        pg.rollback()
        raise
    finally:
        cur.close()


def ensure_intraday_table(pg):
    cur = pg.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS intraday_price_data (
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            ts TIMESTAMPTZ NOT NULL,
            open DOUBLE PRECISION NOT NULL,
            high DOUBLE PRECISION NOT NULL,
            low DOUBLE PRECISION NOT NULL,
            close DOUBLE PRECISION NOT NULL,
            volume DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (symbol, interval, ts)
        );
        CREATE TABLE IF NOT EXISTS data_fetch_status (
            dataset TEXT PRIMARY KEY,
            data_fetched_at TIMESTAMPTZ NOT NULL,
            source TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS intraday_ingestion_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            symbols_attempted INTEGER NOT NULL,
            symbols_succeeded INTEGER NOT NULL,
            symbols_failed INTEGER NOT NULL,
            retry_count INTEGER NOT NULL,
            fetch_started_at TIMESTAMPTZ NOT NULL,
            fetch_completed_at TIMESTAMPTZ NOT NULL,
            db_upsert_result JSONB NOT NULL,
            failed_symbols JSONB NOT NULL,
            batch_metrics JSONB NOT NULL
        )
    """)
    pg.commit()
    cur.close()


def insert_intraday_rows(pg, rows, batch=1000, source="settrade_intraday_60m", stats=None,
                         record_fetch_status=True):
    """Commit bars and their successful-fetch timestamp atomically."""
    stats = stats if stats is not None else {}
    if not rows:
        stats["intraday_inserted"] = 0
        stats["intraday_updated"] = 0
        return 0
    cur = pg.cursor()
    outcomes = psycopg2.extras.execute_values(
        cur,
        "INSERT INTO intraday_price_data (symbol,interval,ts,open,high,low,close,volume) "
        "VALUES %s ON CONFLICT (symbol,interval,ts) DO UPDATE SET "
        "open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, "
        "close=EXCLUDED.close, volume=EXCLUDED.volume "
        "RETURNING (xmax = 0) AS inserted",
        rows, page_size=batch, fetch=True,
    )
    inserted = sum(1 for outcome in outcomes if outcome[0])
    stats["intraday_inserted"] = inserted
    stats["intraday_updated"] = len(outcomes) - inserted
    if record_fetch_status:
        cur.execute("""INSERT INTO data_fetch_status(dataset,data_fetched_at,source)
                       VALUES('dashboard_intraday',NOW(),%s)
                       ON CONFLICT(dataset) DO UPDATE SET
                       data_fetched_at=EXCLUDED.data_fetched_at, source=EXCLUDED.source""",
                    (source,))
    pg.commit()
    cur.close()
    return len(rows)


def format_intraday_run_log(run_id, timestamp, interval, symbols, offered,
                            inserted, updated, failed):
    """One timestamped, grep-friendly summary for every intraday run."""
    return (
        f"timestamp={timestamp.astimezone(dt.timezone.utc).isoformat()} run_id={run_id} "
        f"intraday interval={interval} symbols={symbols} offered={offered} "
        f"{inserted} inserted / {updated} updated failed={failed}"
    )


def record_intraday_run_summary(pg, summary):
    """Persist run health separately; never changes canonical data_fetched_at."""
    cur = pg.cursor()
    cur.execute(
        """INSERT INTO intraday_ingestion_runs(
               run_id,status,symbols_attempted,symbols_succeeded,symbols_failed,
               retry_count,fetch_started_at,fetch_completed_at,db_upsert_result,
               failed_symbols,batch_metrics)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
           ON CONFLICT(run_id) DO UPDATE SET
               status=EXCLUDED.status,
               symbols_attempted=EXCLUDED.symbols_attempted,
               symbols_succeeded=EXCLUDED.symbols_succeeded,
               symbols_failed=EXCLUDED.symbols_failed,
               retry_count=EXCLUDED.retry_count,
               fetch_started_at=EXCLUDED.fetch_started_at,
               fetch_completed_at=EXCLUDED.fetch_completed_at,
               db_upsert_result=EXCLUDED.db_upsert_result,
               failed_symbols=EXCLUDED.failed_symbols,
               batch_metrics=EXCLUDED.batch_metrics""",
        (
            summary["run_id"], summary["status"], summary["symbols_attempted"],
            summary["symbols_succeeded"], summary["symbols_failed"],
            summary["retry_count"], summary["fetch_started_at"],
            summary["fetch_completed_at"],
            json.dumps({"rows_offered": summary["rows_offered"]}),
            json.dumps(summary["failed_symbols"]), json.dumps(summary["batches"]),
        ),
    )
    pg.commit()
    cur.close()


def ensure_intraday_feed_status_table(pg):
    cur = pg.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS intraday_feed_status (
        symbol TEXT PRIMARY KEY,
        feed TEXT NOT NULL DEFAULT 'settrade_intraday_60m',
        status TEXT NOT NULL DEFAULT 'available',
        consecutive_failures INTEGER NOT NULL DEFAULT 0,
        reason TEXT,
        last_success_at TIMESTAMPTZ,
        last_failure_at TIMESTAMPTZ,
        retry_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    pg.commit()
    cur.close()


def update_intraday_feed_status(pg, summary, cooldown_hours=24):
    """Track per-symbol intraday capability without excluding Daily/EOD data."""
    ensure_intraday_feed_status_table(pg)
    failed = set(summary.get("failed_symbols") or [])
    attempted = set()
    # Summary failed_symbols is authoritative for failures; attempted symbols
    # are read from the active universe so successful symbols can be reset.
    cur = pg.cursor()
    cur.execute("SELECT symbol FROM symbol_master WHERE instrument_type='ORD' AND (status IS NULL OR status='active')")
    attempted.update(row[0] for row in cur.fetchall())
    now = dt.datetime.now(dt.timezone.utc)
    for symbol in sorted(attempted):
        if symbol in failed:
            cur.execute("""INSERT INTO intraday_feed_status
                (symbol,status,consecutive_failures,reason,last_failure_at,retry_at,updated_at)
                VALUES(%s,'unavailable',1,'settrade_empty_or_failed_response',%s,%s,%s)
                ON CONFLICT(symbol) DO UPDATE SET
                  consecutive_failures=intraday_feed_status.consecutive_failures+1,
                  status='unavailable',
                  reason='settrade_empty_or_failed_response', last_failure_at=EXCLUDED.last_failure_at,
                  retry_at=EXCLUDED.retry_at,
                  updated_at=EXCLUDED.updated_at""",
                (symbol, now, now + dt.timedelta(hours=cooldown_hours), now))
        else:
            cur.execute("""INSERT INTO intraday_feed_status
                (symbol,status,consecutive_failures,last_success_at,retry_at,updated_at)
                VALUES(%s,'available',0,%s,NULL,%s)
                ON CONFLICT(symbol) DO UPDATE SET
                  status='available', consecutive_failures=0,
                  reason=NULL, last_success_at=EXCLUDED.last_success_at,
                  retry_at=NULL, updated_at=EXCLUDED.updated_at
                WHERE intraday_feed_status.status <> 'unavailable'""",
                (symbol, now, now))
    pg.commit()
    cur.close()


# ---------- source: local CSV drop dirs ----------
def list_local_files(after: dt.date):
    """Return [(date, path)] for CSVs strictly newer than `after`."""
    found = {}
    for d in DROP_DIRS:
        for p in glob.glob(os.path.join(d, "*.csv")):
            m = FNAME_RE.search(os.path.basename(p))
            if not m:
                continue
            fd = dt.date.fromisoformat(m.group(1))
            if after is None or fd > after:
                found.setdefault(fd, p)
    return sorted(found.items())


def parse_csv(path, stats):
    rows = []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for r in reader:
            if len(r) < 7:
                continue
            tk = r[0].strip()
            keep, itype = classify(tk)
            if not keep:
                stats["dropped"] += 1
                continue
            try:
                d = f"{r[1][:4]}-{r[1][4:6]}-{r[1][6:8]}"
                rows.append((
                    tk, d,
                    float(r[2]), float(r[3]), float(r[4]), float(r[5]),
                    float(r[6]) if r[6] else 0.0, itype,
                ))
            except Exception:
                stats["bad_row"] += 1
    return rows


# ---------- source: google drive ----------
def fetch_drive(after: dt.date, stats):
    """Pull the Drive folder listing into the upload dir (throttled by gdown)."""
    try:
        import gdown
    except ImportError:
        print("  ! gdown not installed; skipping drive source (pip install gdown)")
        return
    out = DROP_DIRS[0]
    os.makedirs(out, exist_ok=True)
    try:
        gdown.download_folder(DRIVE_URL, quiet=True, output=out, remaining_ok=True)
    except Exception as e:
        print(f"  ! drive listing failed: {repr(e)[:160]}")


# ---------- source: Settrade Open API ----------
def _active_db_symbols(pg, instrument_types=None):
    """Return active (symbol, instrument_type) pairs near the latest DB date."""
    cur = pg.cursor()
    params = []
    type_filter = ""
    if instrument_types:
        type_filter = "AND instrument_type = ANY(%s) "
        params.append(instrument_types)
    cur.execute(
        "SELECT DISTINCT symbol, instrument_type FROM price_data "
        "WHERE market = 'TH' AND symbol IN ("
        "  SELECT symbol FROM price_data GROUP BY symbol "
        "  HAVING MAX(date) >= (SELECT MAX(date) FROM price_data) - INTERVAL '10 days'"
        ") " + type_filter + "ORDER BY symbol",
        params,
    )
    syms = cur.fetchall()
    cur.close()
    return syms


def _settrade_credentials():
    creds = {k: os.getenv(k) for k in SETTRADE_ENV_KEYS}
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise RuntimeError("missing Settrade credentials: " + ", ".join(missing))
    return creds


def _settrade_market():
    try:
        from settrade_v2 import Investor
    except ImportError as e:
        raise RuntimeError("settrade-v2 is not installed (pip install settrade-v2)") from e
    creds = _settrade_credentials()
    investor = Investor(
        app_id=creds["SETTRADE_APP_ID"],
        app_secret=creds["SETTRADE_APP_SECRET"],
        broker_id=creds["SETTRADE_BROKER_ID"],
        app_code=creds["SETTRADE_APP_CODE"],
        is_auto_queue=os.getenv("SETTRADE_AUTO_QUEUE", "false").lower() in ("1", "true", "yes"),
    )
    market = investor.MarketData()
    _install_settrade_http_timeout(market)
    return market


def _install_settrade_http_timeout(market):
    """Pass a real requests timeout through settrade-v2, including worker threads."""
    ctx = getattr(market, "_ctx", None)
    if ctx is None or getattr(ctx, "_signalix_timeout_installed", False):
        return market
    original_request = ctx.request

    def request_with_timeout(method, endpoint, headers=None, **kwargs):
        kwargs.setdefault("timeout", SETTRADE_REQUEST_TIMEOUT)
        return original_request(method, endpoint, headers=headers, **kwargs)

    ctx.request = request_with_timeout
    ctx._signalix_timeout_installed = True
    return market


def _bangkok_date_from_settrade_ts(ts):
    """Settrade daily bars are epoch seconds; docs example maps to midnight Bangkok."""
    return dt.datetime.fromtimestamp(int(ts), BANGKOK_TZ).date().isoformat()


def _parse_settrade_candlestick(sym, itype, res, after, stats):
    """Convert Settrade get_candlestick response to price_data rows."""
    rows = []
    if isinstance(res, list) and res:
        payload = res[0]
    elif isinstance(res, dict):
        payload = res
    else:
        stats["settrade_empty"] = stats.get("settrade_empty", 0) + 1
        return rows
    try:
        times = payload.get("time") or []
        opens = payload.get("open") or []
        highs = payload.get("high") or []
        lows = payload.get("low") or []
        closes = payload.get("close") or []
        vols = payload.get("volume") or []
    except AttributeError:
        stats["bad_row"] += 1
        return rows
    n = min(len(times), len(opens), len(highs), len(lows), len(closes), len(vols))
    for i in range(n):
        try:
            d = _bangkok_date_from_settrade_ts(times[i])
            if after and dt.date.fromisoformat(d) <= after:
                continue
            vol = float(vols[i] or 0)
            if vol == 0:
                stats["settrade_zero_vol_dropped"] = stats.get("settrade_zero_vol_dropped", 0) + 1
                continue
            rows.append((
                sym,
                d,
                float(opens[i]),
                float(highs[i]),
                float(lows[i]),
                float(closes[i]),
                vol,
                itype,
            ))
        except Exception:
            stats["bad_row"] += 1
    return rows


def _parse_settrade_intraday(sym, interval, res, stats):
    """Convert Settrade intraday bars to rows keyed by Bangkok timestamp."""
    payload = res[0] if isinstance(res, list) and res else res
    if not isinstance(payload, dict):
        stats["intraday_empty"] = stats.get("intraday_empty", 0) + 1
        return []
    cols = [payload.get(k) or [] for k in ("time", "open", "high", "low", "close", "volume")]
    rows = []
    for ts, o, h, l, c, v in zip(*cols):
        try:
            if float(v or 0) <= 0:
                continue
            stamp = dt.datetime.fromtimestamp(int(ts), BANGKOK_TZ).isoformat()
            rows.append((sym, interval, stamp, float(o), float(h), float(l), float(c), float(v)))
        except (TypeError, ValueError, OverflowError):
            stats["bad_row"] += 1
    return rows


def _intraday_universe(pg, instrument_types=("ORD",)):
    """Return the complete active Settrade universe for every 60m run.

    Intraday follows the current universe contract directly from symbol_master;
    it is independent of scan output, groups, and scan timing.
    """
    ensure_intraday_feed_status_table(pg)
    cur = pg.cursor()
    cur.execute(
        "SELECT sm.symbol FROM symbol_master sm "
        "WHERE sm.instrument_type = ANY(%s) "
        "AND (sm.status IS NULL OR sm.status = 'active') "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM intraday_feed_status fs "
        "  WHERE fs.symbol = sm.symbol AND fs.feed='settrade_intraday_60m' "
        "    AND fs.status='unavailable' AND (fs.retry_at IS NULL OR fs.retry_at > now())"
        ") ORDER BY sm.symbol",
        (list(instrument_types),),
    )
    symbols = [row[0] for row in cur.fetchall() if row[0] != "SET"]
    cur.close()
    return symbols


def fetch_intraday(pg, stats, limit=10, mode="full", interval="60m"):
    """Fetch one timeframe for one dashboard intent bucket."""
    if interval != "60m":
        raise ValueError(f"unsupported intraday interval: {interval}")
    symbols = _intraday_universe(pg)
    market = _settrade_market()
    rows = []
    for sym in symbols:
        try:
            with settrade_request_timeout():
                res = market.get_candlestick(symbol=sym, interval=interval,
                                              limit=limit, normalized=SETTRADE_NORMALIZED)
            rows.extend(_parse_settrade_intraday(sym, interval, res, stats))
        except Exception as e:
            stats["intraday_failed"] = stats.get("intraday_failed", 0) + 1
            msg = repr(e)[:240]
            print(f"  ! intraday {sym} {interval} failed: {msg}")
            # Settrade auth/session errors are shared across the whole MarketData
            # client. Continuing one request per symbol only burns the 15-minute
            # scheduler window while producing no newer bars. Stop this batch and
            # let the next timer invocation retry with a fresh Investor session.
            low = msg.lower()
            if "access token" in low or "token is invalid" in low or "status[kicked]" in low:
                stats["intraday_auth_failed"] = stats.get("intraday_auth_failed", 0) + 1
                print("  ! intraday auth/session failure: aborting batch; next timer run will retry")
                break
        time.sleep(SETTRADE_SLEEP_SECONDS)
    stats["intraday_symbols"] = len(symbols)
    return rows


def _is_settrade_session_error(exc):
    """Recognize shared-session failures without depending on SDK exception types."""
    message = str(exc).lower()
    return any(marker in message for marker in (
        "u-102", "usersession is unavailable", "user session is unavailable",
        "access token", "token is invalid", "status[kicked]",
    ))


def _utc_now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ingest_intraday(
        pg, stats, *, symbols=None, limit=10, mode="full", interval="60m",
        batch_size=SETTRADE_BATCH_SIZE,
        batch_delay=SETTRADE_BATCH_DELAY_SECONDS,
        batch_jitter=SETTRADE_BATCH_JITTER_SECONDS,
        per_symbol_delay=SETTRADE_SLEEP_SECONDS,
        workers=SETTRADE_INTRADAY_WORKERS,
        session_retries=SETTRADE_SESSION_RETRIES,
        retry_backoff=SETTRADE_RETRY_BACKOFF_SECONDS,
        market_factory=_settrade_market, sleep_fn=time.sleep,
        jitter_fn=random.uniform):
    """Fetch and commit one intraday run in rerun-safe, isolated batches."""
    if interval != "60m":
        raise ValueError(f"unsupported intraday interval: {interval}")
    if batch_size <= 0:
        raise ValueError("intraday batch_size must be greater than zero")
    if min(batch_delay, batch_jitter, per_symbol_delay) < 0:
        raise ValueError("intraday delays must not be negative")
    if workers <= 0:
        raise ValueError("intraday workers must be greater than zero")
    if session_retries < 0 or retry_backoff < 0:
        raise ValueError("intraday retry settings must not be negative")

    symbols = list(_intraday_universe(pg) if symbols is None else symbols)
    run_id = uuid.uuid4().hex
    summary = {
        "run_id": run_id, "status": "failure",
        "symbols_attempted": len(symbols), "symbols_succeeded": 0,
        "symbols_failed": 0, "failed_symbols": [], "retry_count": 0,
        "fetch_started_at": _utc_now_iso(), "fetch_completed_at": None,
        "rows_offered": 0, "rows_inserted": 0, "rows_updated": 0,
        "batches": [],
    }
    stats["intraday_symbols"] = len(symbols)
    stats.setdefault("intraday_failed", 0)
    stats.setdefault("intraday_auth_failed", 0)
    if not symbols:
        summary["fetch_completed_at"] = _utc_now_iso()
        return summary

    market = None
    while market is None:
        try:
            market = market_factory()
        except Exception as exc:
            if not _is_settrade_session_error(exc):
                raise
            stats["intraday_auth_failed"] += 1
            if summary["retry_count"] >= session_retries:
                summary["symbols_failed"] = len(symbols)
                summary["failed_symbols"] = list(symbols)
                summary["fetch_completed_at"] = _utc_now_iso()
                stats["intraday_failed"] += len(symbols)
                stats["intraday_retries"] = summary["retry_count"]
                return summary
            summary["retry_count"] += 1
            if retry_backoff:
                sleep_fn(retry_backoff * summary["retry_count"])

    batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    run_has_failure = False
    session_exhausted = False

    for batch_index, batch_symbols in enumerate(batches, 1):
        batch_info = {
            "batch_id": f"{run_id}:{batch_index}",
            "symbols_attempted": len(batch_symbols), "symbols_succeeded": 0,
            "symbols_failed": 0, "failed_symbols": [], "retry_count": 0,
            "fetch_started_at": _utc_now_iso(), "fetch_completed_at": None,
            "db_upsert_result": 0, "rows_inserted": 0, "rows_updated": 0,
            "errors": [],
        }
        batch_rows = []
        completed_symbols = []

        if session_exhausted:
            batch_info["failed_symbols"] = list(batch_symbols)
            batch_info["errors"].append("session unavailable; bounded recovery exhausted")
        else:
            pending_symbols = list(batch_symbols)
            while pending_symbols:
                def fetch_one(sym):
                    return _fetch_one_intraday(
                        sym, interval, market,
                        workers=workers, limit=limit,
                        sleep_fn=sleep_fn, retry_empty=True,
                    )

                if workers > 1:
                    with concurrent.futures.ThreadPoolExecutor(
                            max_workers=min(workers, len(pending_symbols))) as pool:
                        fetched = list(pool.map(fetch_one, pending_symbols))
                else:
                    fetched = []
                    for index, sym in enumerate(pending_symbols):
                        result = fetch_one(sym)
                        fetched.append(result)
                        if result[3] is not None:
                            break
                        if per_symbol_delay and index < len(pending_symbols) - 1:
                            sleep_fn(per_symbol_delay)

                attempt_rows, attempt_succeeded = [], []
                attempt_failed, attempt_errors = [], []
                session_errors = []
                for sym, parsed, error, session_exc in fetched:
                    if session_exc is not None:
                        session_errors.append(session_exc)
                    elif error is not None:
                        attempt_failed.append(sym)
                        attempt_errors.append(f"{sym}: {error}")
                    else:
                        attempt_rows.extend(parsed)
                        attempt_succeeded.append(sym)

                batch_rows.extend(attempt_rows)
                completed_symbols.extend(attempt_succeeded)
                batch_info["errors"].extend(attempt_errors)

                failed_symbols = list(attempt_failed)
                failed_symbols.extend(
                    sym for sym, _parsed, _error, session_exc in fetched
                    if session_exc is not None and sym not in failed_symbols
                )
                if session_errors:
                    fetched_symbols = {sym for sym, _parsed, _error, _session_exc in fetched}
                    failed_symbols.extend(
                        sym for sym in pending_symbols
                        if sym not in fetched_symbols and sym not in failed_symbols
                    )
                if not failed_symbols:
                    batch_info["failed_symbols"] = []
                    break

                batch_info["failed_symbols"] = failed_symbols
                if session_errors:
                    # A session-level failure (U-102) is bounded by the outer
                    # session_retries loop; an empty response is not a session
                    # error, so it must not consume the session retry budget.
                    if summary["retry_count"] >= session_retries:
                        stats["intraday_auth_failed"] += len(session_errors)
                        break
                    summary["retry_count"] += 1
                    batch_info["retry_count"] += 1
                    stats["intraday_auth_failed"] += len(session_errors)
                    market = market_factory()
                elif summary["retry_count"] >= session_retries:
                    break
                else:
                    summary["retry_count"] += 1
                    batch_info["retry_count"] += 1
                if retry_backoff:
                    sleep_fn(retry_backoff * summary["retry_count"])
                pending_symbols = failed_symbols

        batch_info["symbols_succeeded"] = len(completed_symbols)
        batch_info["symbols_failed"] = len(batch_info["failed_symbols"])
        if batch_info["symbols_failed"]:
            run_has_failure = True

        is_last_batch = batch_index == len(batches)
        claim_full_success = is_last_batch and not run_has_failure and bool(batch_rows)
        if batch_rows:
            batch_stats = {}
            batch_info["db_upsert_result"] = insert_intraday_rows(
                pg, batch_rows, stats=batch_stats,
                record_fetch_status=claim_full_success)
            batch_info["rows_inserted"] = batch_stats.get(
                "intraday_inserted", batch_info["db_upsert_result"])
            batch_info["rows_updated"] = batch_stats.get("intraday_updated", 0)
            summary["rows_offered"] += batch_info["db_upsert_result"]
            summary["rows_inserted"] += batch_info["rows_inserted"]
            summary["rows_updated"] += batch_info["rows_updated"]

        batch_info["fetch_completed_at"] = _utc_now_iso()
        summary["symbols_succeeded"] += batch_info["symbols_succeeded"]
        summary["symbols_failed"] += batch_info["symbols_failed"]
        summary["failed_symbols"].extend(batch_info["failed_symbols"])
        summary["batches"].append(batch_info)

        if batch_index < len(batches) and not session_exhausted:
            pause = batch_delay + (jitter_fn(0, batch_jitter) if batch_jitter else 0)
            if pause:
                sleep_fn(pause)

    stats["intraday_failed"] += summary["symbols_failed"]
    stats["intraday_retries"] = summary["retry_count"]
    if summary["symbols_failed"] == 0 and summary["symbols_succeeded"] == len(symbols):
        summary["status"] = "full_success" if summary["rows_offered"] else "failure"
    elif summary["symbols_succeeded"]:
        summary["status"] = "partial_success"
    summary["fetch_completed_at"] = _utc_now_iso()
    return summary


def _parse_settrade_intraday_missing_market(sym, interval, market, *, limit, workers, sleep_fn):
    """Retry a Settrade intraday fetch whose parsed candles came back empty.

    Empty intraday responses are transient (a batch init just before a market
    session needs Settrade to warm its cache), so an immediate single retry
    converts most of them into real candles and shrinks the partial_success
    tail. Session-level errors (U-102) are NOT handled here: they are already
    bounded by the outer session_retries loop in ingest_intraday.
    """
    try:
        call = lambda: market.get_candlestick(
            symbol=sym, interval=interval, limit=limit,
            normalized=SETTRADE_NORMALIZED)
        if workers > 1:
            response = call()
        else:
            with settrade_request_timeout():
                response = call()
        parsed = _parse_settrade_intraday(sym, interval, response, {})
        if parsed:
            return sym, parsed, None, None
        return sym, [], "empty intraday response", None
    except Exception as exc:
        if _is_settrade_session_error(exc):
            return sym, [], None, exc
        return sym, [], repr(exc)[:200], None


def _fetch_one_intraday(sym, interval, market, *, workers, limit, sleep_fn, retry_empty):
    """Fetch one symbol's 60m candles with a bounded empty-response retry.

    Only genuine Settrade empty responses are retried (transient warm-up);
    non-session exceptions (timeouts, HTTP errors) are not retried here and
    fall through to the existing failure accounting.
    """
    result = _parse_settrade_intraday_missing_market(
        sym, interval, market, workers=workers, limit=limit, sleep_fn=sleep_fn)
    if retry_empty and result[2] == "empty intraday response" and result[3] is None:
        if sleep_fn:
            sleep_fn(1.0)
        retried = _parse_settrade_intraday_missing_market(
            sym, interval, market, workers=workers, limit=limit, sleep_fn=sleep_fn)
        if retried[1]:
            # Retry recovered real candles; clear the transient empty error.
            retried = (retried[0], retried[1], None, None)
        return retried
    return result


def fetch_settrade(pg, after: dt.date, stats, limit=30, max_symbols=None, instrument_types=None, flush_batch=0, repair_gaps=False, symbols=None):
    """Preferred automated SET source via Settrade Open API v2.

    Uses get_candlestick(symbol, interval='1d', normalized=True). The API needs
    peer-provided credentials in env variables; this function never prints them.
    """
    stats.setdefault("settrade_failed", 0)
    stats.setdefault("settrade_empty", 0)
    stats.setdefault("settrade_zero_vol_dropped", 0)
    market = _settrade_market()
    syms = _active_db_symbols(pg, instrument_types=instrument_types)
    if symbols:
        wanted = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
        syms = [row for row in syms if row[0].upper() in wanted]
    if max_symbols:
        syms = syms[:max_symbols]
    rows = []
    jobs = []
    for sym, itype in syms:
        # Daily mode re-fetches a small shared session overlap. Long per-symbol
        # catch-up is opt-in so stale symbols never slow daily runs.
        sym_after = _last_date_in_db(pg, sym) if repair_gaps else after
        if repair_gaps and after and sym_after:
            sym_after = min(after, sym_after)
        elif repair_gaps and after:
            sym_after = after
        start = ((sym_after + dt.timedelta(days=1)).strftime("%Y-%m-%dT00:00")
                 if repair_gaps and sym_after else None)
        jobs.append((sym, itype, sym_after, start))

    def fetch_one(job):
        sym, itype, sym_after, start = job
        try:
            if SETTRADE_DAILY_WORKERS <= 1 or repair_gaps:
                with settrade_request_timeout():
                    res = market.get_candlestick(
                        symbol=sym, interval=SETTRADE_INTERVAL, limit=limit,
                        start=start, normalized=SETTRADE_NORMALIZED,
                    )
            else:
                # _install_settrade_http_timeout provides the thread-safe timeout.
                res = market.get_candlestick(
                    symbol=sym, interval=SETTRADE_INTERVAL, limit=limit,
                    start=start, normalized=SETTRADE_NORMALIZED,
                )
            return job, res, None
        except Exception as exc:
            return job, None, exc

    worker_count = 1 if repair_gaps else max(1, SETTRADE_DAILY_WORKERS)
    fetched = (fetch_one(job) for job in jobs)
    if worker_count > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
            fetched = pool.map(fetch_one, jobs)
    for job, res, error in fetched:
        sym, itype, sym_after, _start = job
        if error is not None:
            stats["settrade_failed"] += 1
            print(f"  ! settrade {sym} failed: {repr(error)[:120]}")
            continue
        try:
            parsed = _parse_settrade_candlestick(sym, itype, res, sym_after, stats)
            if parsed:
                stats["settrade_rows_kept"] = stats.get("settrade_rows_kept", 0) + len(parsed)
                rows.extend(parsed)
                if flush_batch and len(rows) >= flush_batch:
                    stats["inserted"] += insert_rows(pg, rows)
                    rows = []
        except Exception as exc:
            stats["settrade_failed"] += 1
            print(f"  ! settrade {sym} failed after response: {repr(exc)[:120]}")
        if worker_count == 1:
            time.sleep(SETTRADE_SLEEP_SECONDS)
    return rows


# ---------- source: yfinance fallback ----------
def _last_close_in_db(pg, sym):
    """Most recent close for a symbol already in price_data (or None)."""
    cur = pg.cursor()
    cur.execute("SELECT close FROM price_data WHERE symbol=%s ORDER BY date DESC LIMIT 1", (sym,))
    row = cur.fetchone()
    cur.close()
    return float(row[0]) if row else None


def _last_date_in_db(pg, sym):
    """Most recent date for a symbol already in price_data (or None)."""
    cur = pg.cursor()
    cur.execute("SELECT MAX(date) FROM price_data WHERE symbol=%s", (sym,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def _fetch_one_yf(ticker, start, stats, retries=3):
    """Fetch one ticker with throttle + retry on rate-limit. Returns df or None."""
    import yfinance as yf
    import time
    for attempt in range(1, retries + 1):
        try:
            df = yf.download(ticker, start=start, progress=False,
                             auto_adjust=False, threads=False)
            return df
        except Exception as e:
            msg = str(e)
            if "Rate" in msg or "Too Many" in msg or "429" in msg:
                wait = 5 * attempt
                print(f"  ! rate-limited on {ticker}; sleep {wait}s (attempt {attempt}/{retries})")
                stats["yf_rate_limited"] = stats.get("yf_rate_limited", 0) + 1
                time.sleep(wait)
                continue
            # other error: don't retry
            return None
    return None


def fetch_yfinance(pg, after: dt.date, stats):
    """Fallback: pull <SYM>.BK bars for symbols already known to the DB.

    GUARDS (per owner's data-quality concern about yfinance Thai prices):
      - DROP any bar with volume == 0 (yfinance pads holidays with a
        zero-volume flat bar that would corrupt moving averages).
      - THROTTLE: fetch ONE ticker at a time with a small delay, and retry
        with backoff on YFRateLimitError (yfinance blocks bulk batches).

    NOTE (2026-08-20, owner directive): the 15% first-close-vs-DB continuity
    skip was REMOVED — Arm decided we pull ALL symbols, no price-gap filter.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("  ! yfinance not installed; cannot use fallback (pip install yfinance)")
        return []
    cur = pg.cursor()
    # Only pull symbols that traded recently (last bar within 10 days of the
    # newest date in the DB). Delisted / dormant names have no recent bars on
    # yfinance anyway, and skipping them cuts the universe ~10x -> fast + cheap.
    cur.execute(
        "SELECT DISTINCT symbol, instrument_type FROM price_data "
        "WHERE symbol <> 'SET' AND symbol IN ("
        "  SELECT symbol FROM price_data GROUP BY symbol "
        "  HAVING MAX(date) >= (SELECT MAX(date) FROM price_data) - INTERVAL '10 days'"
        ")"
    )
    syms = cur.fetchall()
    cur.close()
    start = (after + dt.timedelta(days=1)).isoformat()
    rows = []
    stats.setdefault("yf_zero_vol_dropped", 0)
    stats.setdefault("yf_rate_limited", 0)
    import time
    for sym, itype in syms:
        df = _fetch_one_yf(f"{sym}.BK", start, stats)
        if df is None or len(df) == 0:
            continue
        sub = df.dropna(how="all")
        if len(sub) == 0:
            continue
        last_db = _last_close_in_db(pg, sym)
        for idx, r in sub.iterrows():
            try:
                def _scalar(v):
                    return v.item() if hasattr(v, "item") else v
                # yfinance single-ticker bars return a Series per column;
                # coerce each to a plain float before building the row.
                o = float(_scalar(r["Open"]))
                h = float(_scalar(r["High"]))
                l = float(_scalar(r["Low"]))
                c = float(_scalar(r["Close"]))
                vol = float(_scalar(r["Volume"]))
                if vol == 0:
                    stats["yf_zero_vol_dropped"] += 1
                    continue
                rows.append((sym, idx.date().isoformat(), o, h, l, c, vol, itype))
            except Exception as e:
                print(f"  ! row parse error {sym}: {repr(e)[:80]}")
                stats["bad_row"] += 1
        time.sleep(0.15)  # be gentle with yfinance
    return rows


# ---------- optional rescan ----------
def trigger_scan():
    """Ask the running backend to rescan + publish alerts.

    Robust against the daily timer firing before the backend container is ready
    (e.g. after a host reboot): we poll /health and wait up to SCAN_WAIT_SEC
    before giving up and falling back to an in-process scan.
    """
    import time as _time
    SCAN_WAIT_SEC = int(os.getenv("SCAN_WAIT_SEC", "120"))
    deadline = _time.time() + SCAN_WAIT_SEC
    # wait for backend health
    while _time.time() < deadline:
        try:
            import requests
            h = requests.get(SCAN_URL.replace("/scan", "/health"), timeout=5)
            if h.status_code == 200:
                break
        except Exception:
            pass
        _time.sleep(5)
    try:
        import requests
        r = requests.post(SCAN_URL, timeout=600)
        print(f"  scan triggered: HTTP {r.status_code}")
        return
    except Exception as e:
        print(f"  ! HTTP scan failed ({repr(e)[:100]}); trying in-process scan_universe")
    try:
        from screening import scan_universe
        scan_universe()
        print("  scan_universe() completed (in-process fallback; no Redis publish)")
    except Exception as e:
        print(f"  ! in-process scan failed: {repr(e)[:160]}")


def refresh_dashboard_from_existing_scan():
    """Rebuild artifacts from the latest canonical Daily run plus fresh 60m data.

    Intraday-only never runs a Daily scan. It must preserve the latest canonical
    Daily run_id when rebuilding artifacts; otherwise it can overwrite the MVP
    artifact with run_id=None and break lineage verification.
    """
    import build_dashboard

    pg = get_pg()
    try:
        cur = pg.cursor()
        cur.execute("""
            SELECT r.id
            FROM daily_scan_runs r
            WHERE r.scanner_version = 'signalix/daily-state-v2'
              AND r.source_lineage->>'source' = 'price_data'
              AND COALESCE(r.source_lineage->>'mode', '') <> 'historical_backfill'
            ORDER BY r.run_timestamp DESC, r.id DESC
            LIMIT 1
        """)
        run_row = cur.fetchone()
        if not run_row:
            raise RuntimeError("no canonical Daily run available for intraday artifact refresh")
        daily_run_id = str(run_row[0])
        cur.execute("""
            SELECT raw_payload
            FROM daily_scan_observations
            WHERE run_id = %s
            ORDER BY symbol
        """, (daily_run_id,))
        scanned = [row[0] for row in cur.fetchall() if isinstance(row[0], dict)]
    finally:
        pg.close()
    if not scanned:
        raise RuntimeError("canonical Daily run has no raw scan observations")

    result = build_dashboard.build(scanned=scanned, run_id=daily_run_id)
    print("  dashboard refreshed from canonical Daily run " + daily_run_id + ": " + json.dumps(result, sort_keys=True))
    return result


def run_vcp_after_ingestion(pg, summary):
    """Evaluate/persist VCP only after a committed successful ingestion."""
    if summary.get("status") not in {"full_success", "partial_success"}:
        print("VCP_FINDER_SKIP " + json.dumps({"reason": "ingestion_not_eligible", "status": summary.get("status")}))
        return None
    cur = pg.cursor()
    cur.execute("SELECT pg_try_advisory_lock(hashtext('signalix:vcp-finder-60m'))")
    locked = bool(cur.fetchone()[0])
    cur.close()
    if not locked:
        print("VCP_FINDER_SKIP " + json.dumps({"reason": "run_lock_busy"}))
        return None
    try:
        from vcp_finder_db import find_vcp_universe_60m, persist_vcp_run
        completed = summary.get("fetch_completed_at")
        as_of = dt.datetime.fromisoformat(completed) if completed else dt.datetime.now(dt.timezone.utc)
        payload = find_vcp_universe_60m(
            pg, market="TH", as_of=as_of,
            ingestion_run_id=summary.get("run_id"),
            ingestion_status=summary.get("status"),
            fetch_completed_at=completed,
        )
        persist_vcp_run(pg, payload)
        print("VCP_FINDER_RUN " + json.dumps({
            "run_id": payload["run_id"], "ingestion_run_id": summary.get("run_id"),
            "status": summary.get("status"), "universe": payload["universe"],
        }, sort_keys=True))
        return payload
    finally:
        cur = pg.cursor()
        cur.execute("SELECT pg_advisory_unlock(hashtext('signalix:vcp-finder-60m'))")
        pg.commit()
        cur.close()


# ---------- main ----------
def run(args):
    started_at = dt.datetime.now(dt.timezone.utc)
    run_id = f"intraday-{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    print(f"timestamp={started_at.isoformat()} run_id={run_id} event=run_started")
    stats = {"files": 0, "rows_kept": 0, "dropped": 0, "bad_row": 0, "inserted": 0}
    full_intraday = getattr(args, "intraday_full_universe", getattr(args, "intraday_shortlist", False))
    # Intraday scheduler path: full active ORD universe, no scan-derived filter.
    if args.intraday_only:
        mode = args.intraday_mode
        interval = args.intraday_interval
        pg = get_pg()
        try:
            symbols = _intraday_universe(pg)
            print(f"intraday-only mode=full interval={interval} universe : {len(symbols)} symbols")
            if args.dry_run:
                print("  symbols: " + (", ".join(symbols) if symbols else "none"))
                return 0
            ensure_intraday_table(pg)
            summary = ingest_intraday(
                pg, stats, symbols=symbols, limit=args.intraday_limit,
                mode="full", interval=interval,
                batch_size=args.intraday_batch_size,
                batch_delay=args.intraday_batch_delay,
                batch_jitter=args.intraday_batch_jitter,
                workers=getattr(args, "intraday_workers", SETTRADE_INTRADAY_WORKERS),
                session_retries=args.intraday_session_retries,
                retry_backoff=args.intraday_retry_backoff,
            )
            update_intraday_feed_status(pg, summary)
            record_intraday_run_summary(pg, summary)
            run_vcp_after_ingestion(pg, summary)
            print("INTRADAY_RUN_SUMMARY " + json.dumps(summary, sort_keys=True))
            print(format_intraday_run_log(
                run_id=summary["run_id"],
                timestamp=dt.datetime.now(dt.timezone.utc),
                interval=interval,
                symbols=summary["symbols_attempted"],
                offered=summary["rows_offered"],
                inserted=summary.get("rows_inserted", 0),
                updated=summary.get("rows_updated", 0),
                failed=summary["symbols_failed"],
            ))
            refresh_dashboard_from_existing_scan()
        finally:
            pg.close()
        # Partial coverage is recorded in the run summary and is operationally
        # successful: one bad/empty symbol must not mark the whole timer failed.
        return 0 if summary["status"] in ("full_success", "partial_success") else 1

    pg = get_pg()
    if args.since:
        after = dt.date.fromisoformat(args.since) - dt.timedelta(days=1)
    elif args.repair_gaps:
        after = get_max_date(pg)
    else:
        after = get_overlap_cutoff(pg, args.overlap_sessions)
    print(f"current MAX(date) in price_data : {get_max_date(pg)}")
    print(f"fetching trade days strictly after: {after}")

    if args.source in ("auto", "drive") and not args.dry_run:
        fetch_drive(after, stats)

    rows_all = []
    if args.source in ("auto", "local", "drive"):
        files = list_local_files(after)
        print(f"new CSV files found: {len(files)}")
        for fd, p in files:
            print(f"  - {fd} {p}")
            if not args.dry_run:
                rows = parse_csv(p, stats)
                stats["files"] += 1
                stats["rows_kept"] += len(rows)
                rows_all.extend(rows)
                if len(rows_all) >= 20000:
                    stats["inserted"] += insert_rows(pg, rows_all)
                    rows_all = []
        if args.source == "auto" and not files and not args.dry_run:
            print("no new CSVs -> falling back to Settrade Open API")
            args.source = "settrade"

    if args.source == "settrade":
        try:
            instrument_types = [x.strip().upper() for x in args.instrument_types.split(",") if x.strip()]
            srows = fetch_settrade(
                pg,
                after,
                stats,
                limit=(args.settrade_limit if args.repair_gaps else args.overlap_sessions),
                max_symbols=args.max_symbols,
                instrument_types=instrument_types,
                symbols=(args.symbols.split(",") if args.symbols else None),
                flush_batch=(args.flush_batch if not args.dry_run else 0),
                repair_gaps=args.repair_gaps,
            )
        except RuntimeError as e:
            print(f"  ! settrade unavailable: {e}")
            if args.fallback_yfinance:
                print("  -> falling back to yfinance because --fallback-yfinance was set")
                args.source = "yfinance"
            else:
                pg.close()
                return 2
        else:
            stats["rows_kept"] += stats.get("settrade_rows_kept", len(srows))
            rows_all.extend(srows)
            if args.dry_run:
                print(f"settrade would offer {len(srows)} rows "
                      f"(failed {stats.get('settrade_failed',0)} symbols, "
                      f"dropped {stats.get('settrade_zero_vol_dropped',0)} zero-vol bars)")
                syms = {}
                for r in srows:
                    syms[r[0]] = syms.get(r[0], 0) + 1
                print(f"  symbols: {len(syms)}  e.g. " + ", ".join(sorted(syms)[:8]))

    if args.source == "yfinance":
        yrows = fetch_yfinance(pg, after, stats)
        stats["rows_kept"] += len(yrows)
        rows_all.extend(yrows)
        # dry-run still reports what WOULD be written (without writing)
        if args.dry_run:
            print(f"yfinance would offer {len(yrows)} rows "
                  f"(dropped {stats.get('yf_zero_vol_dropped',0)} zero-vol bars)")
            # distinct symbols preview
            syms = {}
            for r in yrows:
                syms[r[0]] = syms.get(r[0], 0) + 1
            print(f"  symbols: {len(syms)}  e.g. " + ", ".join(sorted(syms)[:8]))

    if rows_all and not args.dry_run:
        stats["inserted"] += insert_rows(pg, rows_all)

    new_max = get_max_date(pg)
    print("---- UPDATE SUMMARY ----")
    print(f"  dry_run       : {args.dry_run}")
    print(f"  source        : {args.source}")
    print(f"  files fetched : {stats['files']}")
    print(f"  rows kept     : {stats['rows_kept']}")
    print(f"  rows offered  : {stats['inserted']} (ON CONFLICT DO NOTHING)")
    print(f"  dropped       : {stats['dropped']}")
    print(f"  bad rows      : {stats['bad_row']}")
    if args.source == "yfinance":
        print(f"  yf zero-vol   : {stats.get('yf_zero_vol_dropped', 0)} bars dropped")
    if args.source == "settrade" or stats.get("settrade_failed"):
        print(f"  stt failed    : {stats.get('settrade_failed', 0)} symbols")
        print(f"  stt zero-vol  : {stats.get('settrade_zero_vol_dropped', 0)} bars dropped")
    print(f"  new MAX(date) : {new_max}")
    pg.close()

    # Optional full-universe intraday refresh after the daily scan.
    if (args.scan or full_intraday) and not args.dry_run:
        trigger_scan()
    if full_intraday and not args.dry_run:
        pg = get_pg()
        try:
            ensure_intraday_table(pg)
            summary = ingest_intraday(
                pg, stats, limit=args.intraday_limit,
                interval=args.intraday_interval,
                batch_size=args.intraday_batch_size,
                batch_delay=args.intraday_batch_delay,
                batch_jitter=args.intraday_batch_jitter,
                workers=getattr(args, "intraday_workers", SETTRADE_INTRADAY_WORKERS),
                session_retries=args.intraday_session_retries,
                retry_backoff=args.intraday_retry_backoff,
            )
            update_intraday_feed_status(pg, summary)
            record_intraday_run_summary(pg, summary)
            print("INTRADAY_RUN_SUMMARY " + json.dumps(summary, sort_keys=True))
        finally:
            pg.close()
        # Partial coverage is recorded in the run summary and is operationally
        # successful: one bad/empty symbol must not mark the whole timer failed.
        if summary["status"] not in ("full_success", "partial_success"):
            return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="Signalix incremental SET EOD updater")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be fetched; never writes to the DB")
    ap.add_argument("--since", help="override start date (YYYY-MM-DD, inclusive)")
    ap.add_argument("--source", default="auto",
                    choices=["auto", "local", "drive", "settrade", "yfinance"])
    ap.add_argument("--settrade-limit", type=int, default=30,
                    help="bars per symbol for --repair-gaps (default 30; daily uses --overlap-sessions)")
    ap.add_argument("--overlap-sessions", type=int, default=1,
                    help="latest trading sessions to re-fetch in normal daily mode (default 1; use 3 for manual repair)")
    ap.add_argument("--repair-gaps", action="store_true",
                    help="backfill per-symbol gaps; use separately from normal daily timer")
    ap.add_argument("--max-symbols", type=int,
                    help="optional cap on symbols fetched (useful for Settrade dry-runs)")
    ap.add_argument("--symbols",
                    help="comma-separated TH symbols to fetch selectively (manual repair/test only)")
    ap.add_argument("--instrument-types", default="ORD",
                    help="comma-separated DB instrument types for Settrade (default ORD; use ORD,DR for both)")
    ap.add_argument("--flush-batch", type=int, default=200,
                    help="insert Settrade rows every N parsed rows during real runs (default 200)")
    ap.add_argument("--fallback-yfinance", action="store_true",
                    help="if Settrade credentials/import fail, fall back to yfinance")
    ap.add_argument("--scan", action="store_true",
                    help="trigger a universe rescan after loading (default off)")
    # Full-universe intraday refresh; legacy flag remains accepted as an alias.
    ap.add_argument("--intraday-full-universe", dest="intraday_full_universe", action="store_true",
                    help="after scan fetch 60m for every active ORD symbol")
    ap.add_argument("--intraday-shortlist", dest="intraday_full_universe", action="store_true",
                    help=argparse.SUPPRESS)
    ap.add_argument("--intraday-only", action="store_true",
                    help="refresh 60m for every active ORD symbol; skips daily fetch and scan")
    ap.add_argument("--intraday-limit", type=int, default=4,
                    help="60m bars per active ORD symbol (default 4)")
    ap.add_argument("--intraday-workers", type=int, default=SETTRADE_INTRADAY_WORKERS,
                    help="parallel fetch workers per intraday batch")
    ap.add_argument("--intraday-batch-size", type=int, default=SETTRADE_BATCH_SIZE,
                    help="symbols committed per intraday batch")
    ap.add_argument("--intraday-batch-delay", type=float, default=SETTRADE_BATCH_DELAY_SECONDS,
                    help="base seconds between intraday batches")
    ap.add_argument("--intraday-batch-jitter", type=float, default=SETTRADE_BATCH_JITTER_SECONDS,
                    help="maximum random seconds added between batches")
    ap.add_argument("--intraday-session-retries", type=int, default=SETTRADE_SESSION_RETRIES,
                    help="bounded U-102/session re-auth attempts per run")
    ap.add_argument("--intraday-retry-backoff", type=float, default=SETTRADE_RETRY_BACKOFF_SECONDS,
                    help="base seconds before session re-auth")
    ap.add_argument("--intraday-mode", choices=("full",), default="full",
                    help="full active ORD universe; retained as an explicit contract")
    ap.add_argument("--intraday-interval", choices=("60m",), default="60m",
                    help="single supported intraday interval")
    ap.add_argument("--no-scan", dest="scan", action="store_false",
                    help="explicitly disable the rescan (default)")
    ap.set_defaults(scan=False)
    args = ap.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
