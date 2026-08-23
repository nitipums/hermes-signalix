"""Source freshness tracking for data sources feeding the portfolio health monitor.

Records and exposes, per dataset in ``data_fetch_status``:
- last successful fetch time (data_fetched_at) — only what the system observed,
- staleness thresholds (from the centralized provenance contract),
- source availability status (observed intraday_feed_status rows).

No freshness value is ever invented: a dataset with no fetch row is reported
as status "unknown" with a null timestamp.
"""
import datetime as dt

from provenance_contract import AGING, FRESH, STALE, UNKNOWN

FRESH_WITHIN_HOURS = 1          # < 1h since last successful fetch
STALE_AFTER_HOURS = 72          # > 72h => stale; between => aging

# Datasets the pipeline writes into data_fetch_status. A dataset in this set
# with no observed row is reported as status "unknown" (never invented) rather
# than silently omitted from the report.
KNOWN_DATASETS = ("dashboard_intraday",)


def record_source_fetch(pg, dataset, fetched_at, source):
    """Persist an observed successful fetch. fetched_at must be a real datetime."""
    if not isinstance(fetched_at, dt.datetime):
        raise ValueError("fetched_at must be a real datetime; never fabricate one")
    cur = pg.cursor()
    cur.execute(
        """INSERT INTO data_fetch_status(dataset,data_fetched_at,source)
           VALUES(%s,%s,%s)
           ON CONFLICT (dataset) DO UPDATE SET
               data_fetched_at=EXCLUDED.data_fetched_at,
               source=EXCLUDED.source""",
        (dataset, fetched_at, source),
    )
    pg.commit()
    cur.close()


def _classify(age_hours):
    if age_hours is None:
        return UNKNOWN
    if age_hours < FRESH_WITHIN_HOURS:
        return FRESH
    if age_hours <= STALE_AFTER_HOURS:
        return AGING
    return STALE


def _iso(value):
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc).isoformat()
    return None


def source_freshness(pg, now=None):
    """Freshness metadata for every observed data source; read-only, no invention."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cur = pg.cursor()
    try:
        cur.execute("""SELECT dataset, data_fetched_at, source FROM data_fetch_status""")
        rows = cur.fetchall() or []
        feeds = {}
        try:
            cur.execute(
                """SELECT symbol, status FROM intraday_feed_status
                   WHERE status <> 'available'"""
            )
            for symbol, status in (cur.fetchall() or []):
                feeds[str(symbol)] = str(status)
        except Exception:
            feeds = {}
    finally:
        cur.close()

    degraded_feeds = bool(feeds)
    sources = {}
    # Seed known datasets so a missing row surfaces as "unknown", not absent.
    for known in KNOWN_DATASETS:
        sources[known] = {
            "status": UNKNOWN, "data_fetched_at": None, "age_hours": None,
            "source": "unknown", "available": False,
            "all_feeds_available": not degraded_feeds,
        }
    for dataset, fetched_at, source in rows:
        if fetched_at is None:
            sources[dataset] = {
                "status": UNKNOWN, "data_fetched_at": None, "age_hours": None,
                "source": str(source or "unknown"),
                "available": False, "all_feeds_available": not degraded_feeds,
            }
            continue
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=dt.timezone.utc)
        age_hours = max(0.0, (now - fetched_at).total_seconds() / 3600.0)
        status = _classify(age_hours)
        sources[dataset] = {
            "status": status,
            "data_fetched_at": _iso(fetched_at),
            "age_hours": round(age_hours, 3),
            "source": str(source or "unknown"),
            "available": True,
            # A degraded feed means the pipeline behind this dataset is not fully healthy.
            "all_feeds_available": not degraded_feeds,
        }

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "thresholds": {"fresh_within_hours": FRESH_WITHIN_HOURS,
                       "stale_after_hours": STALE_AFTER_HOURS},
        "sources": sources,
        "feeds": feeds,
    }


def attach_freshness(health_payload, freshness_payload):
    """Return the health payload with freshness metadata attached alongside it."""
    merged = dict(health_payload or {})
    merged["source_freshness"] = freshness_payload
    return merged
