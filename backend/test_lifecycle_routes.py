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


class ReadRepository:
    """Route-level fake proving GETs depend on the read seam, not SQL."""

    def __init__(self, _cur):
        self.calls = []
        self.candidate = {"candidate_id": CID, "symbol": "ABC", "thesis_as_of": "2026-08-31",
                          "policy_version": "p1", "payload": {"symbol": "ABC"},
                          "created_at": "2026-08-31T00:00:00Z"}
        self.snapshots = [
            {"snapshot_id": "snapshot_0", "candidate_id": CID, "setup_id": SID,
             "observation_as_of": "2026-08-31T09:00:00+07:00", "policy_version": "p1",
             "source": "test", "setup_plan": {"trigger": 10}, "machine_payload": {"n": 0},
             "lifecycle_status": "EXPIRED", "expiry_reasons": ["DATA_NOT_CURRENT"],
             "created_at": "2026-08-31T09:00:00Z"},
            {"snapshot_id": SNAP, "candidate_id": CID, "setup_id": SID,
             "observation_as_of": "2026-08-31T10:00:00+07:00", "policy_version": "p1",
             "source": "test", "setup_plan": {"trigger": 11}, "machine_payload": {"n": 1},
             "lifecycle_status": "ACTIVE", "expiry_reasons": [],
             "created_at": "2026-08-31T10:00:00Z"},
        ]
        self.reviews = [{"event_id": "event_1", "candidate_id": CID, "setup_id": SID,
                         "snapshot_id": SNAP, "event": "NOTE", "reviewer": "arm",
                         "note": "historical", "idempotency_key": "key-1",
                         "created_at": "2026-08-31T10:01:00Z"}]

    def read_candidate(self, candidate_id):
        self.calls.append(("candidate", candidate_id))
        return self.candidate if candidate_id == CID else None

    def read_snapshot(self, snapshot_id):
        self.calls.append(("snapshot", snapshot_id))
        return next((row for row in self.snapshots if row["snapshot_id"] == snapshot_id), None)

    def read_candidate_snapshots(self, candidate_id):
        self.calls.append(("candidate_snapshots", candidate_id))
        return [row for row in self.snapshots if row["candidate_id"] == candidate_id]

    def read_reviews(self, *, candidate_id=None, setup_id=None, snapshot_id=None):
        self.calls.append(("reviews", candidate_id, setup_id, snapshot_id))
        return [row for row in self.reviews if (
            (candidate_id is None or row["candidate_id"] == candidate_id)
            and (setup_id is None or row["setup_id"] == setup_id)
            and (snapshot_id is None or row["snapshot_id"] == snapshot_id)
        )]


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


def test_get_routes_use_repository_and_preserve_lossless_history(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_OWNER_TOKEN", "owner-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "arm")
    pg = PG()
    repositories = []

    def factory(cur):
        repository = ReadRepository(cur)
        repositories.append(repository)
        return repository

    ep = endpoints_with_factory(pg, factory)
    result = ep[("GET", "/api/lifecycle/candidates/{candidate_id}")](
        CID, x_authenticated_user="arm", x_portfolio_token="owner-token")
    assert set(result) == {"candidate", "snapshots", "reviews", "provenance"}
    assert result["snapshots"][0]["snapshot_id"] == "snapshot_0"
    assert result["snapshots"][1]["machine_payload"] == {"n": 1}
    assert result["reviews"][0]["note"] == "historical"
    assert result["provenance"] == {"source": "postgresql", "read_only": True}
    assert repositories[0].calls == [("candidate", CID), ("candidate_snapshots", CID),
                                      ("reviews", CID, None, None)]
    assert pg.cur.sql == []


def endpoints_with_factory(pg, factory):
    router = create_lifecycle_router(lambda: pg, repository_factory=factory)
    return {(route.methods.pop(), route.path): route.endpoint for route in router.routes}


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
