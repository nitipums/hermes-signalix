"""Read-only freshness lineage for the canonical setup-candidate read model."""
from __future__ import annotations

import datetime as dt


def overlay_latest_intraday_metadata(payload):
    """Attach published fetch lineage without acquiring/querying PostgreSQL."""
    provenance = payload.get("provenance") or {}
    versions = provenance.get("source_versions") or {}
    if not isinstance(versions.get("intraday"), dict):
        return payload

    # Keep this import at call time so the existing publisher seam remains
    # patchable for compatibility callers and deterministic tests.
    from read_model_publisher import load_intraday_metadata

    metadata = load_intraday_metadata()
    if not metadata:
        return payload
    completed = str(metadata["fetch_completed_at"])
    embedded = versions["intraday"].get("as_of")
    try:
        sidecar_time = dt.datetime.fromisoformat(completed.replace("Z", "+00:00"))
        embedded_time = dt.datetime.fromisoformat(str(embedded).replace("Z", "+00:00")) if embedded else None
        if embedded_time and sidecar_time < embedded_time:
            return payload
    except (TypeError, ValueError):
        return payload
    run_id = str(metadata["run_id"])
    status = metadata["status"]
    freshness = dict(payload.get("freshness") or {})
    freshness.update({"intraday_fetched_at": completed,
                      "intraday_source": "settrade_intraday_60m",
                      "intraday_latest_run_id": str(run_id),
                      "intraday_latest_status": status})
    updated = dict(payload)
    updated["freshness"] = freshness
    updated_provenance = dict(provenance)
    updated_versions = dict(versions)
    updated_versions["intraday"] = {
        **versions["intraday"],
        "run_id": run_id,
        "status": status,
        "as_of": completed,
    }
    updated_provenance["source_versions"] = updated_versions
    updated_provenance["intraday_as_of"] = completed
    updated["provenance"] = updated_provenance
    updated["intraday_latest_run"] = {"run_id": run_id, "status": status,
                                       "fetch_completed_at": completed}
    return updated
