import asyncio
import pytest
from fastapi import HTTPException

from lifecycle_routes import create_lifecycle_router


CID = "candidate_1"
SID = "setup_1"
SNAP = "snapshot_1"


class Cursor:
    def __init__(self):
        self.candidate = {"candidate_id": CID, "symbol": "ABC", "thesis_as_of": "2026-08-31",
                          "policy_version": "p1", "payload": {"symbol": "ABC"},
                          "created_at": "2026-08-31T00:00:00Z"}
        self.snapshot = {"snapshot_id": SNAP, "candidate_id": CID, "setup_id": SID,
                         "observation_as_of": "2026-08-31T10:00:00+07:00",
                         "policy_version": "p1", "source": "test", "setup_plan": {},
                         "machine_payload": {}, "lifecycle_status": "ACTIVE",
                         "expiry_reasons": [], "created_at": "2026-08-31T10:00:00Z"}
        self.reviews = []
        self.sql = []
        self.closed = False

    def execute(self, sql, params=()):
        self.sql.append((sql, params))
        if "INSERT INTO lifecycle_review_events" in sql:
            key = params[7]
            if not any(row["idempotency_key"] == key for row in self.reviews):
                self.reviews.append(dict(zip(
                    ("event_id", "candidate_id", "setup_id", "snapshot_id", "event",
                     "reviewer", "note", "idempotency_key", "created_at"), params)))

    def fetchone(self):
        sql = self.sql[-1][0]
        params = self.sql[-1][1]
        if "FROM lifecycle_candidates" in sql:
            return self.candidate if params[0] == CID else None
        if "FROM lifecycle_snapshots" in sql:
            return self.snapshot if params[0] == SNAP else None
        if "FROM lifecycle_review_events" in sql:
            key = params[0]
            return next((row for row in self.reviews if row["idempotency_key"] == key), None)
        return None

    def fetchall(self):
        sql, params = self.sql[-1]
        if "FROM lifecycle_snapshots" in sql:
            return [self.snapshot] if params[0] == CID else []
        if "FROM lifecycle_review_events" in sql:
            if "snapshot_id" in sql:
                return [row for row in self.reviews if row["snapshot_id"] == params[0]]
            return [row for row in self.reviews if row["candidate_id"] == params[0]]
        return []

    def close(self):
        self.closed = True


class PG:
    def __init__(self):
        self.cur = Cursor()
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **kwargs):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class Request:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


def endpoints(pg):
    router = create_lifecycle_router(lambda: pg)
    return { (route.methods.pop(), route.path): route.endpoint for route in router.routes }


def raises_status(call, status):
    with pytest.raises(HTTPException) as exc:
        call()
    assert exc.value.status_code == status


def test_get_auth_envelope_references_and_read_only_queries(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_OWNER_TOKEN", "owner-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "arm")
    pg = PG(); ep = endpoints(pg)
    raises_status(lambda: ep[("GET", "/api/lifecycle/candidates/{candidate_id}")](CID), 401)
    raises_status(lambda: ep[("GET", "/api/lifecycle/snapshots/{snapshot_id}")](SNAP), 401)
    raises_status(lambda: ep[("GET", "/api/lifecycle/candidates/{candidate_id}")](
        CID, x_authenticated_user="forged", x_portfolio_token="owner-token"), 401)
    raises_status(lambda: ep[("GET", "/api/lifecycle/candidates/{candidate_id}")](
        CID, x_authenticated_user="arm", x_portfolio_token="wrong"), 401)
    result = ep[("GET", "/api/lifecycle/candidates/{candidate_id}")](
        CID, x_authenticated_user="arm", x_portfolio_token="owner-token")
    assert set(result) == {"candidate", "snapshots", "reviews", "provenance"}
    assert result["provenance"]["read_only"] is True
    assert not any(any(token in sql.upper() for token in ("INSERT", "UPDATE", "DELETE")) for sql, _ in pg.cur.sql)
    raises_status(lambda: ep[("GET", "/api/lifecycle/candidates/{candidate_id}")](
        "missing", x_authenticated_user="arm", x_portfolio_token="owner-token"), 404)
    raises_status(lambda: ep[("GET", "/api/lifecycle/snapshots/{snapshot_id}")](
        "missing", x_authenticated_user="arm", x_portfolio_token="owner-token"), 404)


def test_post_auth_payload_reference_validation_and_all_events(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_OWNER_TOKEN", "owner-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "arm")
    pg = PG(); ep = endpoints(pg)
    post = ep[("POST", "/api/lifecycle/reviews")]
    raises_status(lambda: asyncio.run(post(Request({}), x_idempotency_key="k")), 401)
    raises_status(lambda: asyncio.run(post(Request({}), x_authenticated_user="arm")), 401)
    raises_status(lambda: asyncio.run(post(Request({}), x_authenticated_user="forged",
                                             x_portfolio_token="owner-token")), 401)
    raises_status(lambda: asyncio.run(post(Request({"candidate_id": CID, "setup_id": SID,
                                                      "snapshot_id": SNAP, "event": "NOTE",
                                                      "reviewer": "evil"}),
                                             x_authenticated_user="arm", x_portfolio_token="owner-token",
                                             x_idempotency_key="k")), 422)
    raises_status(lambda: asyncio.run(post(Request({"candidate_id": "missing", "setup_id": SID,
                                                      "snapshot_id": SNAP, "event": "NOTE"}),
                                             x_authenticated_user="arm", x_portfolio_token="owner-token",
                                             x_idempotency_key="missing")), 404)
    for index, event in enumerate(("AGREE", "WATCH", "DISAGREE_WAVE", "REJECT_SETUP",
                                   "MISSED_CANDIDATE", "NOTE")):
        result = asyncio.run(post(Request({"candidate_id": CID, "setup_id": SID,
                                            "snapshot_id": SNAP, "event": event}),
                                  x_authenticated_user="arm", x_portfolio_token="owner-token",
                                  x_idempotency_key=f"k-{index}"))
        assert result["event"] == event
        assert result["reviewer"] == "arm"
    assert pg.commits == 6


def test_post_retry_conflict_and_invalid_event(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_OWNER_TOKEN", "owner-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "arm")
    pg = PG(); ep = endpoints(pg)
    post = ep[("POST", "/api/lifecycle/reviews")]
    payload = {"candidate_id": CID, "setup_id": SID, "snapshot_id": SNAP, "event": "NOTE", "note": "one"}
    auth = {"x_authenticated_user": "arm", "x_portfolio_token": "owner-token"}
    first = asyncio.run(post(Request(payload), **auth, x_idempotency_key="retry"))
    again = asyncio.run(post(Request(payload), **auth, x_idempotency_key="retry"))
    assert again["event_id"] == first["event_id"]
    raises_status(lambda: asyncio.run(post(Request({**payload, "note": "two"}),
                                             **auth, x_idempotency_key="retry")), 409)
    raises_status(lambda: asyncio.run(post(Request({**payload, "event": "NOPE"}),
                                             **auth, x_idempotency_key="bad-event")), 422)
