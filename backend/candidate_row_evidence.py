"""Pure evidence assemblies for one canonical setup-candidate row."""

from __future__ import annotations

from typing import Any


def assemble_candidate_data_status(
    *,
    daily_df: Any,
    daily_evidence_valid: bool,
    daily_evidence_usable: bool,
    daily_current: bool,
    daily_freshness: str,
    daily_final_status: str,
    intraday_available: bool,
    intraday_current: bool,
    intraday_freshness: str,
    intraday_as_of: str | None,
    setup: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Assemble data status and its setup/freshness consequences.

    The returned setup is a copy.  Engine data reasons are consumed here so
    they remain part of the data-status contract rather than setup output.
    """
    daily_ok = daily_df is not None and len(daily_df) > 0
    intraday_ok = intraday_current
    if daily_evidence_usable and intraday_current:
        candidate_freshness = "fresh"
    elif "stale" in {daily_freshness, intraday_freshness}:
        candidate_freshness = "stale"
    else:
        candidate_freshness = "unknown"

    data_status = {
        "sufficient": bool(daily_evidence_usable and intraday_current),
        "freshness": candidate_freshness,
        "source": "price_data+intraday_price_data" if daily_ok and intraday_ok else "price_data/intraday_price_data",
        "daily_available": daily_ok,
        "daily_final_session_available": daily_current,
        "daily_final_session_status": daily_final_status,
        "daily_freshness": daily_freshness,
        "intraday_60m_available": intraday_available,
        "intraday_60m_freshness": intraday_freshness,
        "intraday_60m_status": ("provisional" if intraday_current else intraday_freshness),
        "intraday_60m_as_of": intraday_as_of,
    }
    setup_out = dict(setup)
    engine_data_reason = setup_out.pop("data_reason_code", None)
    data_reason_codes = []
    if not daily_ok:
        data_reason_codes.append("NO_DAILY_DATA")
    elif not daily_evidence_valid:
        data_reason_codes.append("INVALID_DAILY_OHLCV")
    elif daily_freshness == "stale":
        data_reason_codes.append("STALE_DAILY_DATA")
    if engine_data_reason:
        data_reason_codes.append(engine_data_reason)
    elif not intraday_available:
        data_reason_codes.append("NO_60M_DATA")
    elif intraday_freshness == "stale":
        data_reason_codes.append("STALE_60M_DATA")
    if data_reason_codes:
        data_status["reason_code"] = data_reason_codes[0]
        data_status["reason_codes"] = list(dict.fromkeys(data_reason_codes))
    if str(data_status.get("reason_code", "")).startswith("INVALID_"):
        data_status["sufficient"] = False
        data_status["freshness"] = "invalid"
        setup_out["status"] = "DATA_BLOCKED"
        candidate_freshness = "invalid"
    if "INVALID_60M_OHLCV" in data_reason_codes:
        data_status["intraday_60m_freshness"] = "invalid"
        data_status["intraday_60m_status"] = "invalid"
    return data_status, setup_out, candidate_freshness


def assemble_candidate_provenance(
    *,
    as_of: str | None,
    intraday_as_of: str | None,
    candidate_freshness: str,
    universe_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Assemble canonical and marginable-universe provenance fields."""
    return {
        "policy_version": "setup-candidates-v1",
        "source": "price_data+intraday_price_data",
        "daily_source": "price_data",
        "intraday_source": "intraday_price_data",
        "as_of": as_of,
        "intraday_as_of": intraday_as_of,
        "freshness": candidate_freshness,
        "universe_filter": universe_manifest["universe_filter"],
        "marginable_schema_version": universe_manifest.get("schema_version"),
        "marginable_source_document": universe_manifest.get("source_document"),
        "marginable_effective_date": universe_manifest.get("effective_date"),
    }
