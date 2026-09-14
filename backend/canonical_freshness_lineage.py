"""Read-only freshness lineage for the canonical setup-candidate read model."""
from __future__ import annotations

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
    run_id = str(metadata["run_id"])
    status = metadata["status"]
    candle_status = metadata.get("candle_status", "unavailable")
    freshness = dict(payload.get("freshness") or {})
    freshness.update({"intraday_fetched_at": completed,
                      "intraday_source": "settrade_intraday_60m",
                      "intraday_latest_run_id": str(run_id),
                      "intraday_latest_status": status})
    if candle_status in {"fresh", "partial", "stale", "unavailable"}:
        freshness["intraday_status"] = candle_status
    updated = dict(payload)
    updated["freshness"] = freshness
    updated_provenance = dict(provenance)
    updated_provenance["source_versions"] = dict(versions)
    if "intraday_as_of" not in updated_provenance:
        updated_provenance["intraday_as_of"] = versions["intraday"].get("as_of")
    updated["provenance"] = updated_provenance
    updated["intraday_latest_run"] = {"run_id": run_id, "status": status,
                                       "fetch_completed_at": completed,
                                       "candle_status": candle_status}
    return updated
