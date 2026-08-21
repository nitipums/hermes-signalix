"""Live, read-only Signalix dashboard contract checks.

Run with the backend and dashboard already serving:
  /root/.venv_img/bin/python test_signalix_contracts.py
"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
DASH = "http://127.0.0.1:3001/dashboard.html?contract-test=1"


def get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.status, r.read()


def main():
    status, body = get(BASE + "/health")
    health = json.loads(body)
    assert status == 200 and health.get("status") == "ok", health

    status, body = get(BASE + "/dashboard/snapshot")
    snap = json.loads(body)
    assert status == 200 and isinstance(snap.get("items"), list) and snap["items"], "snapshot empty"
    for key in ("data_fetched_at", "data_freshness_source", "data_freshness_status", "market_session", "last_valid_session"):
        assert key in snap, key
    session = snap["market_session"]
    for key in ("status", "is_open", "last_valid_session", "timezone", "source"):
        assert key in session, key
    assert snap["last_valid_session"] == session["last_valid_session"]
    assert session["timezone"] == "Asia/Bangkok"
    assert snap["data_fetched_at"] is None or "T" in snap["data_fetched_at"], snap["data_fetched_at"]
    item = snap["items"][0]
    for key in ("symbol", "close", "athHigh", "athLow", "high52", "low52", "ma10Value", "ma20Value", "ma50Value", "ma200Value"):
        assert key in item, key

    for tf in ("60m", "1D", "1W", "1M"):
        status, body = get(BASE + f"/chart/SIS?timeframe={tf}&limit=30")
        chart = json.loads(body)
        assert status == 200 and chart["bars"], (tf, status)
        assert all("volume" in b for b in chart["bars"]), tf
        assert "latest_time" in chart and "provisional" in chart, tf

    try:
        get(BASE + "/chart/SIS?timeframe=15m&limit=30")
    except urllib.error.HTTPError as exc:
        assert exc.code == 400, exc.code
    else:
        raise AssertionError("15m chart unexpectedly accepted")

    status, body = get(DASH)
    html = body.decode("utf-8")
    assert status == 200
    for marker in ("company-name", "decision-banner", "modal-subtitle", "title-link", "Last data fetched:", "Setup quality", "Risk", "Trigger", "VOL", "data-timeframe=\"1D\"", "Loading Daily chart", "Try again"):
        assert marker in html, marker
    for removed in ("Market session:", "last valid:", "set_market_day_guard", "Evidence provenance", "Canonical event", "confidence"):
        assert removed not in html, removed
    print({"health": health, "items": len(snap["items"]), "dashboard_bytes": len(body), "contracts": "ok"})


if __name__ == "__main__":
    main()
