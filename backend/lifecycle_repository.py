"""Read-only repository seam for lifecycle candidate history and reviews."""

from __future__ import annotations

from typing import Any, Protocol


class LifecycleRepository(Protocol):
    """The small read interface used by lifecycle HTTP adapters."""

    def read_candidate(self, candidate_id: str) -> Any: ...

    def read_snapshot(self, snapshot_id: str) -> Any: ...

    def read_candidate_snapshots(self, candidate_id: str) -> list[Any]: ...

    def read_reviews(
        self, *, candidate_id: str | None = None,
        setup_id: str | None = None, snapshot_id: str | None = None,
    ) -> list[Any]: ...


class PostgresLifecycleRepository:
    """SELECT-only lifecycle adapter over the caller-owned cursor."""

    def __init__(self, cur):
        self._cur = cur

    def read_candidate(self, candidate_id: str):
        self._cur.execute(
            "SELECT candidate_id, symbol, thesis_as_of, policy_version, payload, created_at "
            "FROM lifecycle_candidates WHERE candidate_id = %s",
            (candidate_id,),
        )
        return self._cur.fetchone()

    def read_snapshot(self, snapshot_id: str):
        self._cur.execute(
            "SELECT snapshot_id, candidate_id, setup_id, observation_as_of, policy_version, "
            "source, setup_plan, machine_payload, lifecycle_status, expiry_reasons, created_at "
            "FROM lifecycle_snapshots WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        return self._cur.fetchone()

    def read_candidate_snapshots(self, candidate_id: str):
        self._cur.execute(
            "SELECT snapshot_id, candidate_id, setup_id, observation_as_of, policy_version, "
            "source, setup_plan, machine_payload, lifecycle_status, expiry_reasons, created_at "
            "FROM lifecycle_snapshots WHERE candidate_id = %s "
            "ORDER BY observation_as_of ASC, snapshot_id ASC",
            (candidate_id,),
        )
        return self._cur.fetchall()

    def read_reviews(self, *, candidate_id=None, setup_id=None, snapshot_id=None):
        clauses, params = [], []
        for key, value in (("candidate_id", candidate_id), ("setup_id", setup_id),
                           ("snapshot_id", snapshot_id)):
            if value is not None:
                clauses.append(f"{key} = %s")
                params.append(value)
        sql = (
            "SELECT event_id, candidate_id, setup_id, snapshot_id, event, reviewer, note, "
            "idempotency_key, created_at FROM lifecycle_review_events"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC, event_id ASC"
        self._cur.execute(sql, tuple(params))
        return self._cur.fetchall()
