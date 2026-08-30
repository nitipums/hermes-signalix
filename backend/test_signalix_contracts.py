"""Live, read-only Signalix dashboard contract checks.

Run with the backend and dashboard already serving:
  /root/.venv_img/bin/python test_signalix_contracts.py
"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
MVP = "http://127.0.0.1:3001/mvp?contract-test=1"


def get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.status, r.read()


def main():
    status, body = get(BASE + "/health")
    health = json.loads(body)
    assert status == 200 and health.get("status") == "ok", health

    try:
        get(BASE + "/dashboard/snapshot")
    except urllib.error.HTTPError as exc:
        assert exc.code == 410, exc.code
    else:
        raise AssertionError("legacy dashboard snapshot unexpectedly served")

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

    try:
        get("http://127.0.0.1:3001/dashboard.html?contract-test=retired")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404, exc.code
    else:
        raise AssertionError("retired dashboard.html unexpectedly served")

    status, body = get(MVP)
    html = body.decode("utf-8")
    assert status == 200
    for marker in ("Daily VCP Watchlist", "All VCP · 60m", "id=\"daily-vcp-cards\"", "app.js"):
        assert marker in html, marker
    print({"health": health, "contracts": "ok"})


if __name__ == "__main__":
    main()
