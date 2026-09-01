"""MVP-only HTTP API dispatch for the Signalix dashboard server.

This module owns only /api/* projection routes. It is read-only: snapshot
projection and chart DB access never run a scan or mutate PostgreSQL.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit

from mvp_snapshot import load_mvp_artifact

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_MVP_SNAPSHOT_PATH = os.getenv("MVP_SNAPSHOT_PATH", os.path.join(_BACKEND_DIR, "mvp_snapshot.json"))

# Short-lived process-local reuse for the default MVP request. This avoids
# duplicate latest-run joins during refresh bursts without becoming storage.
_VCP_WATCHLIST_CACHE_TTL_SECONDS = 2.0
_VCP_WATCHLIST_CACHE_MAX_ENTRIES = 4
_vcp_watchlist_cache = {}
_vcp_watchlist_inflight = {}
_vcp_watchlist_cache_lock = threading.Lock()
_SETUP_CANDIDATES_CACHE_TTL_SECONDS = 300.0
_setup_candidates_cache = None
_setup_candidates_inflight = None
_setup_candidates_cache_lock = threading.Lock()


class SetupCandidatesBuilderContractError(RuntimeError):
    """The canonical builder returned something other than (items, metadata)."""

VCP_AUDIT_DEPRECATION = {
    "status": "audit_only",
    "boundary": "one_day",
    "window": "one_day",
    "message": "VCP is retained for audit/rollback only; use /api/setup-candidates for the canonical decision spine.",
}

LEGACY_ROUTE_DEPRECATION = {
    "status": "audit_only",
    "boundary": "one_day",
    "message": "Legacy MVP projection is retained for audit/replay only; use /api/setup-candidates.",
}


def _legacy_response(payload):
    """Mark compatibility output without changing its historical item shape."""
    if isinstance(payload, dict):
        return {**payload, "audit_only": True,
                "deprecation": dict(LEGACY_ROUTE_DEPRECATION)}
    return payload


def clear_vcp_watchlist_cache():
    """Clear the bounded presentation cache (used by deterministic tests)."""
    with _vcp_watchlist_cache_lock:
        _vcp_watchlist_cache.clear()
        _vcp_watchlist_inflight.clear()


def clear_setup_candidates_cache():
    """Clear the bounded setup-candidate cache (used by deterministic tests)."""
    global _setup_candidates_cache
    with _setup_candidates_cache_lock:
        _setup_candidates_cache = None


def _setup_candidates_source_version(pg):
    """Cheap read-only fingerprint so a completed ingestion expires the cache."""
    cur = pg.cursor()
    try:
        cur.execute("SELECT MAX(date) FROM price_data WHERE market=%s", ("TH",))
        daily = cur.fetchone()
        cur.execute("""SELECT fetch_completed_at FROM intraday_ingestion_runs
                       WHERE status IN ('full_success','partial_success')
                       ORDER BY fetch_completed_at DESC NULLS LAST LIMIT 1""")
        ingestion = cur.fetchone()
        return daily, ingestion
    finally:
        cur.close()


def _load_setup_candidates_cached(builder, pg, *, market="TH"):
    """Reuse one bounded read-only build and coalesce concurrent requests."""
    global _setup_candidates_cache, _setup_candidates_inflight
    request_started = time.monotonic()
    waited = False
    try:
        source_version = _setup_candidates_source_version(pg)
    except (AttributeError, TypeError):
        # Pure unit-test builders need not emulate PostgreSQL. Production
        # connections always use the ingestion-aware fingerprint above.
        source_version = None
    while True:
        now = time.monotonic()
        with _setup_candidates_cache_lock:
            cached = _setup_candidates_cache
            if cached and cached[0] > now and cached[1] == source_version:
                return _setup_candidates_observed(
                    cached[2], "single_flight" if waited else "warm",
                    request_started, wait_started if waited else None,
                )
            waiter = _setup_candidates_inflight
            if waiter is None:
                waiter = threading.Event()
                _setup_candidates_inflight = waiter
                owner = True
            else:
                owner = False
        if owner:
            break
        wait_started = time.monotonic()
        waited = True
        waiter.wait()

    try:
        build_started = time.monotonic()
        built = builder(pg, market=market)
        if (not isinstance(built, tuple) or len(built) != 2
                or not isinstance(built[0], list)
                or not isinstance(built[1], dict)
                or "items" in built[1]):
            raise SetupCandidatesBuilderContractError(
                "setup-candidate builder must return (items, metadata)"
            )
        items, source_meta = built
        payload = {"items": items, **source_meta}
        build_observability = dict(payload.get("build_observability") or {})
        build_observability.setdefault(
            "duration_ms", round((time.monotonic() - build_started) * 1000, 3)
        )
        payload["build_observability"] = build_observability
        with _setup_candidates_cache_lock:
            _setup_candidates_cache = (
                time.monotonic() + _SETUP_CANDIDATES_CACHE_TTL_SECONDS,
                source_version,
                payload,
            )
        return _setup_candidates_observed(payload, "cold", request_started, None)
    finally:
        with _setup_candidates_cache_lock:
            _setup_candidates_inflight = None
            waiter.set()


def _setup_candidates_observed(payload, status, request_started, wait_started):
    """Return request-specific cache metadata without mutating the cached source."""
    observed = dict(payload)
    build_observability = dict(payload.get("build_observability") or {})
    stages_ms = dict(build_observability.get("stages_ms") or {})
    build_observability["stages_ms"] = stages_ms
    build_observability["cache_status"] = status
    build_observability["request_duration_ms"] = round(
        (time.monotonic() - request_started) * 1000, 3
    )
    if wait_started is not None:
        build_observability["single_flight_wait_ms"] = round(
            (time.monotonic() - wait_started) * 1000, 3
        )
    observed["build_observability"] = build_observability
    observed["cache_status"] = status
    return observed




def _load_daily_watchlist_cached(loader, params):
    """Load one daily projection, coalescing concurrent identical requests."""
    # Loader identity also prevents a replaced implementation from reusing an
    # old response during tests or a development reload.
    key = (id(loader), tuple(sorted(params.items())))
    while True:
        now = time.monotonic()
        with _vcp_watchlist_cache_lock:
            cached = _vcp_watchlist_cache.get(key)
            if cached and cached[0] > now:
                return cached[1]
            if cached:
                _vcp_watchlist_cache.pop(key, None)
            waiter = _vcp_watchlist_inflight.get(key)
            if waiter is None:
                waiter = threading.Event()
                _vcp_watchlist_inflight[key] = waiter
                owner = True
            else:
                owner = False
        if owner:
            break
        waiter.wait()

    try:
        pg = _vcp_pg()
        try:
            payload = loader(pg, **params)
        finally:
            pg.close()
        if payload is not None:
            # Preserve universe/freshness metadata, but never cache the large
            # full-universe result list for the compact watchlist contract.
            payload = {**payload, "results": []}
            with _vcp_watchlist_cache_lock:
                if len(_vcp_watchlist_cache) >= _VCP_WATCHLIST_CACHE_MAX_ENTRIES:
                    oldest_key = min(_vcp_watchlist_cache, key=lambda k: _vcp_watchlist_cache[k][0])
                    _vcp_watchlist_cache.pop(oldest_key, None)
                _vcp_watchlist_cache[key] = (time.monotonic() + _VCP_WATCHLIST_CACHE_TTL_SECONDS, payload)
        return payload
    finally:
        with _vcp_watchlist_cache_lock:
            _vcp_watchlist_inflight.pop(key, None)
            waiter.set()


def _vcp_pg():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "signalix"),
        password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
        dbname=os.getenv("POSTGRES_DB", "signalix"),
    )
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def load_payload() -> dict:
    """Load the canonical MVP artifact; no legacy fallback is allowed."""
    if not os.path.exists(_MVP_SNAPSHOT_PATH):
        raise FileNotFoundError("mvp_snapshot.json not found")
    return load_mvp_artifact(_MVP_SNAPSHOT_PATH)


def load_snapshot() -> list[dict]:
    """Compatibility helper returning only MVP items."""
    return load_payload()["items"]


def json_response(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(body)


def _not_found(handler, symbol):
    json_response(handler, {"error": "symbol not found", "symbol": symbol}, status=404)


def handle_mvp_api(path, handler) -> bool:
    """Handle MVP /api routes. Return False only for unknown API paths."""
    parsed = urlsplit(path)
    route = parsed.path
    qs = parse_qs(parsed.query or "")

    if route in ("/api/vcp-finder", "/api/vcp-finder/"):
        interval = (qs.get("interval", ["60m"])[0] or "60m").lower()
        market = (qs.get("market", ["TH"])[0] or "TH").upper()
        if interval != "60m" or market != "TH":
            json_response(handler, {"error": "vcp_finder_60m supports interval=60m and market=TH only"}, status=400)
            return True
        daily_watchlist = (qs.get("daily_watchlist", ["false"])[0] or "false").lower() in {"1", "true", "yes"}
        try:
            from vcp_finder_db import load_latest_vcp_run
            universe = (qs.get("universe", ["marginable_long"])[0] or "marginable_long").strip().lower()
            if universe not in {"marginable_long", "active_ord"}:
                raise ValueError("unknown universe")
            symbol = (qs.get("symbol", [""])[0] or "").upper() or None
            state = (qs.get("state", [""])[0] or "").upper() or None
            limit = int(qs["limit"][0]) if qs.get("limit") else None
            actionable = (qs.get("actionable", ["false"])[0] or "false").lower() in {"1", "true", "yes"}
            focused = (qs.get("focused", ["false"])[0] or "false").lower() in {"1", "true", "yes"}
            review = (qs.get("review", ["false"])[0] or "false").lower() in {"1", "true", "yes"}
            params = {"market": market, "daily_watchlist": daily_watchlist, "state": state,
                      "symbol": symbol, "limit": limit, "actionable": actionable,
                      "focused": focused, "review": review, "universe": universe}
            if daily_watchlist:
                payload = _load_daily_watchlist_cached(load_latest_vcp_run, params)
            else:
                pg = _vcp_pg()
                try:
                    payload = load_latest_vcp_run(pg, **params)
                finally:
                    pg.close()
            if payload is None:
                json_response(handler, {"error": "vcp_finder_unavailable", "reason": "no_usable_run"}, status=503)
                return True
            payload = {**payload, "audit_only": True,
                       "deprecation": dict(VCP_AUDIT_DEPRECATION)}
            if daily_watchlist:
                # The watchlist consumes only capped lanes. Preserve full-universe
                # counts/coverage metadata, but do not serialize audit results.
                payload = {**payload, "results": []}
            json_response(handler, payload)
        except (ValueError, TypeError) as exc:
            json_response(handler, {"error": "invalid_request"}, status=400)
        except Exception as exc:
            json_response(handler, {"error": "vcp_finder_unavailable"}, status=503)
        return True
    if route in ("/api/setup-candidates", "/api/setup-candidates/"):
        pg = None
        try:
            page = int(qs.get("page", ["1"])[0])
            page_size = int(qs.get("page_size", ["50"])[0])
        except (ValueError, TypeError):
            json_response(handler, {"error": "invalid_request"}, status=400)
            return True
        try:
            import mvp_api
            # Canonical serving is always built from authoritative OHLCV. The
            # legacy MVP artifact is neither a source nor a fallback here.
            pg = _vcp_pg()
            payload = _load_setup_candidates_cached(
                mvp_api.build_setup_candidates_from_data, pg, market="TH"
            )
            items = payload["items"]
            result = mvp_api.project_setup_candidates_response(
                items, snapshot_meta=payload,
                lifecycle=(qs.get("lifecycle", [None])[0] or None),
                state=(qs.get("state", [None])[0] or None),
                sector=(qs.get("sector", [None])[0] or None),
                search=(qs.get("search", [None])[0] or None),
                page=page, page_size=page_size,
            )
            json_response(handler, result)
        except (FileNotFoundError, json.JSONDecodeError, ImportError, KeyError, RuntimeError, ConnectionError):
            json_response(handler, {"error": "setup_candidates_unavailable"}, status=503)
        except Exception:
            json_response(handler, {"error": "setup_candidates_unavailable"}, status=503)
        finally:
            if pg is not None:
                pg.close()
        return True
    try:
        payload = load_payload()
        items = payload["items"]
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        json_response(handler, {"error": "snapshot_unavailable"}, status=503)
        return True
    try:
        import mvp_api
    except ImportError as exc:
        json_response(handler, {"error": "mvp_api_unavailable"}, status=503)
        return True

    if route in ("/api/daily-shortlist", "/api/daily-shortlist/"):
        marginable_filter = qs.get("marginable", ["krungsri"])[0] or "krungsri"
        margin_rates = qs.get("margin_rates", [""])[0]
        price_band = qs.get("price_band", ["all"])[0]
        json_response(handler, _legacy_response(mvp_api.project_shortlist_response(
            items, snapshot_meta=payload, marginable_filter=marginable_filter,
            margin_rates=margin_rates, price_band=price_band,
        ))); return True
    if route in ("/api/explorer", "/api/explorer/"):
        result = mvp_api.project_explorer_response(
            items,
            page=int(qs.get("page", ["1"])[0]),
            page_size=int(qs.get("page_size", ["20"])[0]),
            search=qs.get("search", [None])[0],
            stage=qs.get("stage", [None])[0],
            snapshot_meta=payload,
            marginable_filter=(qs.get("marginable", ["krungsri"])[0] or "krungsri"),
            margin_rates=qs.get("margin_rates", [""])[0],
            price_band=qs.get("price_band", ["all"])[0],
        )
        json_response(handler, _legacy_response(result)); return True
    if route.startswith("/api/symbol/"):
        symbol = route[len("/api/symbol/"):].strip().rstrip("/")
        if not symbol:
            json_response(handler, {"error": "symbol required"}, status=400); return True
        result = mvp_api.project_symbol_detail(items, symbol)
        if result is None: _not_found(handler, symbol)
        else: json_response(handler, _legacy_response(result))
        return True
    if route.startswith("/api/chart-db/"):
        symbol = route[len("/api/chart-db/"):].strip().rstrip("/")
        if not symbol:
            json_response(handler, {"error": "symbol required"}, status=400); return True
        import mvp_chart_db
        timeframe = (qs.get("timeframe", ["1D"])[0] or "1D").upper()
        try:
            result = mvp_chart_db.project_chart_db_response(symbol, timeframe=timeframe)
        except ValueError as exc:
            json_response(handler, {"error": "invalid_request"}, status=400); return True
        if result is None: _not_found(handler, symbol)
        else: json_response(handler, _legacy_response(result))
        return True
    if route.startswith("/api/chart/"):
        symbol = route[len("/api/chart/"):].strip().rstrip("/")
        if not symbol:
            json_response(handler, {"error": "symbol required"}, status=400); return True
        import mvp_chart
        result = mvp_chart.project_chart_response(items, symbol)
        if not result or not (result.get("candles") or []):
            import mvp_chart_db
            timeframe = (qs.get("timeframe", ["1D"])[0] or "1D").upper()
            try:
                result = mvp_chart_db.project_chart_db_response(symbol, timeframe=timeframe) or result
            except ValueError as exc:
                json_response(handler, {"error": "invalid_request"}, status=400); return True
        if result is None: _not_found(handler, symbol)
        else: json_response(handler, _legacy_response(result))
        return True
    return False
