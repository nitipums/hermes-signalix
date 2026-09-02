"""Owner-only HTTP adapter for the append-only lifecycle persistence seam."""
from __future__ import annotations

import os

import psycopg2
import psycopg2.extras

from fastapi import APIRouter, Header, HTTPException, Request

from lifecycle_persistence import IdempotencyConflict, build_review_event_id, persist_review
from lifecycle_repository import LifecycleRepository, PostgresLifecycleRepository


def _row(value):
    return dict(value) if value is not None else None


def _owner(identity: str | None, token: str | None) -> str:
    """Return the owner identity only after the existing token binding passes.

    Lifecycle routes have no independent gateway-verification middleware in
    this application.  Reuse the portfolio owner seam: the token proves the
    caller has the configured owner credential and the identity must equal the
    server-bound owner identity.  Missing configuration therefore fails closed.
    """
    from portfolio import require_owner_identity

    if not isinstance(identity, str) or not identity.strip() or len(identity) > 256:
        raise HTTPException(status_code=401, detail="missing or invalid owner identity")
    if not require_owner_identity(
        token if isinstance(token, str) else "", os.getenv("PORTFOLIO_OWNER_TOKEN", ""),
        identity.strip(), os.getenv("TELEGRAM_CHAT_ID", ""),
    ):
        raise HTTPException(status_code=401, detail="missing or invalid owner identity")
    return identity.strip()


def create_lifecycle_router(get_pg, repository_factory=None):
    router = APIRouter(prefix="/api/lifecycle", tags=["lifecycle"])
    repository_factory = repository_factory or PostgresLifecycleRepository

    @router.get("/candidates/{candidate_id}")
    def lifecycle_candidate(
        candidate_id: str,
        x_authenticated_user: str | None = Header(default=None),
        x_portfolio_token: str | None = Header(default=None),
    ):
        _owner(x_authenticated_user, x_portfolio_token)
        pg = get_pg()
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        repository: LifecycleRepository = repository_factory(cur)
        try:
            candidate = _row(repository.read_candidate(candidate_id))
            if candidate is None:
                raise HTTPException(status_code=404, detail="candidate not found")
            snapshots = [_row(row) for row in repository.read_candidate_snapshots(candidate_id)]
            reviews = [_row(row) for row in repository.read_reviews(candidate_id=candidate_id)]
            return {"candidate": candidate, "snapshots": snapshots, "reviews": reviews,
                    "provenance": {"source": "postgresql", "read_only": True}}
        finally:
            cur.close()

    @router.get("/snapshots/{snapshot_id}")
    def lifecycle_snapshot(
        snapshot_id: str,
        x_authenticated_user: str | None = Header(default=None),
        x_portfolio_token: str | None = Header(default=None),
    ):
        _owner(x_authenticated_user, x_portfolio_token)
        pg = get_pg()
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        repository: LifecycleRepository = repository_factory(cur)
        try:
            snapshot = _row(repository.read_snapshot(snapshot_id))
            if snapshot is None:
                raise HTTPException(status_code=404, detail="snapshot not found")
            candidate = _row(repository.read_candidate(snapshot["candidate_id"]))
            if candidate is None:
                raise HTTPException(status_code=404, detail="candidate not found")
            reviews = [_row(row) for row in repository.read_reviews(snapshot_id=snapshot_id)]
            return {"candidate": candidate, "snapshots": [snapshot], "reviews": reviews,
                    "provenance": {"source": "postgresql", "read_only": True}}
        finally:
            cur.close()

    @router.post("/reviews")
    async def lifecycle_review(
        request: Request,
        x_authenticated_user: str | None = Header(default=None),
        x_idempotency_key: str | None = Header(default=None),
        x_portfolio_token: str | None = Header(default=None),
    ):
        reviewer = _owner(x_authenticated_user, x_portfolio_token)
        if not isinstance(x_idempotency_key, str) or not x_idempotency_key.strip():
            raise HTTPException(status_code=422, detail="idempotency key is required")
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=422, detail="JSON review payload required") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="review payload must be an object")
        required = ("candidate_id", "setup_id", "snapshot_id", "event")
        if any(not isinstance(payload.get(key), str) or not payload[key].strip() for key in required):
            raise HTTPException(status_code=422, detail="candidate_id, setup_id, snapshot_id, and event are required")
        if "reviewer" in payload:
            # Explicitly reject rather than silently accepting a conflicting
            # client claim; the persisted reviewer is always gateway identity.
            raise HTTPException(status_code=422, detail="reviewer must come from trusted identity")
        pg = get_pg()
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        repository: LifecycleRepository = repository_factory(cur)
        try:
            snapshot = _row(repository.read_snapshot(payload["snapshot_id"]))
            if snapshot is None or snapshot.get("candidate_id") != payload["candidate_id"] or snapshot.get("setup_id") != payload["setup_id"]:
                raise HTTPException(status_code=404, detail="candidate/setup/snapshot reference not found")
            record = {"event_id": build_review_event_id(x_idempotency_key), "candidate_id": payload["candidate_id"],
                      "setup_id": payload["setup_id"], "snapshot_id": payload["snapshot_id"],
                      "event": payload["event"], "reviewer": reviewer,
                      "note": payload.get("note"), "idempotency_key": x_idempotency_key.strip()}
            try:
                result = persist_review(cur, record)
                # The route owns the transaction boundary.  Production's
                # connection is currently autocommit, while explicit callers
                # and realistic fakes can still verify one commit at the
                # boundary; persistence helpers never commit themselves.
                commit = getattr(pg, "commit", None)
                if callable(commit):
                    commit()
                return result
            except IdempotencyConflict as exc:
                rollback = getattr(pg, "rollback", None)
                if callable(rollback):
                    rollback()
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except psycopg2.IntegrityError as exc:
                rollback = getattr(pg, "rollback", None)
                if callable(rollback):
                    rollback()
                raise HTTPException(status_code=409, detail="review conflicts with immutable history") from exc
            except ValueError as exc:
                rollback = getattr(pg, "rollback", None)
                if callable(rollback):
                    rollback()
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            cur.close()

    return router
