"""Canonical setup-candidate response projection.

This is the stable read-only seam for the promoted setup-candidate contract.
Legacy shortlist, explorer, and symbol projections intentionally remain in
``mvp_api`` and are not dependencies of this module.
"""

from __future__ import annotations

import math

from freshness_assessment import (assess_projection_freshness as _resolve_freshness,
                                  daily_eod_status as _daily_eod_status)
from setup_candidate_contract import (
    CANONICAL_METADATA_FIELDS,
    QUOTE_FIELDS,
    WAVE_CONTEXT_FIELDS,
    WAVE_CONTEXT_SECONDARY_MARKERS,
    WAVE_CONTEXT_STATES,
    build_setup_candidate_diagnostic,
    compact_setup_candidate_for_list,
    project_setup_candidate_list,
    sort_setup_candidates,
)


def _validate_canonical_setup_candidate(item: dict) -> dict:
    """Validate a canonical source item without adapting legacy data."""
    required = ("symbol", "as_of", "data_status", "trend", "wave", "setup",
                "context", "bonus_evidence", "decision_lane", "provenance")
    if not all(key in item for key in required):
        raise ValueError("snapshot is not a canonical setup-candidate artifact")
    legacy_aliases = {
        "decision", "group", "action", "status", "primary_state", "primaryState",
    }
    present = sorted(legacy_aliases.intersection(item))
    if present:
        raise ValueError(
            "canonical snapshot contains legacy decision aliases: " + ", ".join(present)
        )
    allowed = set(required) | set(CANONICAL_METADATA_FIELDS) | {"quote"}
    if set(item) - allowed or not set(required).issubset(item):
        raise ValueError("snapshot is not an exact canonical envelope")
    provenance = item.get("provenance") or {}
    provenance_required = {"policy_version", "source", "as_of", "freshness"}
    if not provenance_required.issubset(provenance):
        raise ValueError("canonical snapshot provenance is incomplete")
    quote = item.get("quote")
    if quote is not None:
        if not isinstance(quote, dict) or not {"price", "source", "as_of", "provisional"}.issubset(quote):
            raise ValueError("canonical quote is incomplete")
        if set(quote) - QUOTE_FIELDS:
            raise ValueError("canonical quote is not an exact envelope")
        if quote.get("source") not in {"intraday_price_data", "price_data"}:
            raise ValueError("canonical quote source is invalid")
        expected_provisional = quote["source"] == "intraday_price_data"
        if quote.get("provisional") is not expected_provisional:
            raise ValueError("canonical quote provisional boundary is invalid")
        has_pct = quote.get("change_pct") is not None
        has_amount = quote.get("change_amount") is not None
        if has_pct != (quote.get("change_basis") is not None):
            raise ValueError("canonical quote change basis is incomplete")
        if has_amount != (quote.get("change_amount_basis") is not None):
            raise ValueError("canonical quote amount basis is incomplete")
    wave_context = (item.get("wave") or {}).get("context")
    if wave_context is not None:
        if not isinstance(wave_context, dict):
            raise ValueError("canonical wave context is invalid")
        if set(wave_context) != WAVE_CONTEXT_FIELDS:
            raise ValueError("canonical wave context is not an exact envelope")
        if wave_context.get("mapped_state") not in WAVE_CONTEXT_STATES:
            raise ValueError("canonical wave context state is invalid")
        if wave_context.get("confidence") not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValueError("canonical wave context confidence is invalid")
        if not isinstance(wave_context.get("rule_version"), str):
            raise ValueError("canonical wave context rule version is invalid")
        if not isinstance(wave_context.get("rationale"), str):
            raise ValueError("canonical wave context rationale is invalid")
        if wave_context.get("source_timeframe") != "daily":
            raise ValueError("canonical wave context timeframe is invalid")
        for evidence_field in (
            "supporting_evidence", "contradicting_evidence", "missing_evidence"
        ):
            if not isinstance(wave_context.get(evidence_field), list):
                raise ValueError("canonical wave context evidence is invalid")
        secondary = wave_context.get("secondary_markers")
        if (not isinstance(secondary, list)
                or any(marker not in WAVE_CONTEXT_SECONDARY_MARKERS for marker in secondary)
                or (secondary and wave_context.get("mapped_state") != "WAVE_3_CONTINUATION")):
            raise ValueError("canonical wave context secondary marker is invalid")
    data_status = item.get("data_status") or {}
    freshness = str(data_status.get("freshness", "")).lower()
    if (data_status.get("sufficient") is False
            or freshness in {"stale", "unknown", "invalid", "unavailable"}
            or data_status.get("intraday_60m_freshness") in {"stale", "unknown"}):
        if item.get("decision_lane") != "DATA_BLOCKED":
            raise ValueError("canonical snapshot violates fail-closed data contract")
    return item


def project_setup_candidates_response(items: list[dict], *, snapshot_meta: dict | None = None,
                                      lifecycle: str | None = None, state: str | None = None,
                                      sector: str | None = None, search: str | None = None,
                                      page: int = 1, page_size: int = 50) -> dict:
    """Project validated canonical candidates with presentation filters only."""
    candidates = sort_setup_candidates([_validate_canonical_setup_candidate(item) for item in items])
    filtered = candidates
    if lifecycle:
        token = lifecycle.upper()
        filtered = [x for x in filtered if str((x.get("setup") or {}).get("status", "")).upper() == token
                    or str(x.get("decision_lane", "")).upper() == token]
    if state:
        token = state.upper()
        filtered = [x for x in filtered if str((x.get("wave") or {}).get("state", "")).upper() == token
                    or str((x.get("setup") or {}).get("state", "")).upper() == token]
    if sector:
        token = sector.strip().casefold()
        filtered = [x for x in filtered if token in str((x.get("context") or {}).get("sector", "")).casefold()]
    if search:
        token = search.strip().casefold()
        filtered = [x for x in filtered if token in str(x.get("symbol", "")).casefold()
                    or token in str((x.get("context") or {}).get("sector", "")).casefold()]
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    total = len(filtered)
    start = (page - 1) * page_size
    page_items = filtered[start:start + page_size]

    projection_provenance = {"policy_version": "setup-candidates-v1"}
    if snapshot_meta:
        stored_provenance = snapshot_meta.get("provenance") or {}
        if isinstance(stored_provenance, dict):
            projection_provenance.update(stored_provenance)
    projected = project_setup_candidate_list(
        [compact_setup_candidate_for_list(item) for item in page_items],
        as_of=(snapshot_meta or {}).get("scan_time"),
        provenance=projection_provenance,
        universe=(snapshot_meta or {}).get("universe_filter") or "marginable_long",
    )
    meta = snapshot_meta or {}
    projected.update({
        "page": page, "page_size": page_size, "total_items": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
        "evaluated_count": len(candidates), "returned_count": len(page_items),
        "counts": {decision: sum(x.get("decision_lane") == decision for x in candidates)
                   for decision in ("REVIEW_NOW", "SETUP_FORMING", "DAILY_CANDIDATE",
                                    "WAIT", "AVOID", "DATA_BLOCKED")},
        "freshness": meta.get("freshness") or _resolve_freshness(items),
        "universe_filter": meta.get("universe_filter") or "marginable_long",
        "base_active_ord_count": meta.get("base_active_ord_count"),
        "eligible_count": meta.get("eligible_count", len(candidates)),
        "excluded_count": meta.get("excluded_count"), "excluded_reason": meta.get("excluded_reason"),
        "marginable_schema_version": meta.get("schema_version"),
        "marginable_source_document": meta.get("source_document"),
        "marginable_effective_date": meta.get("effective_date"),
        "build_observability": meta.get("build_observability"),
        "cache_status": meta.get("cache_status"), "source_version": meta.get("source_version"),
        "published_at": meta.get("published_at"), "read_model_status": meta.get("read_model_status"),
    })
    projected["diagnostic"] = build_setup_candidate_diagnostic(
        candidates, as_of=projected.get("as_of"), universe=projected["universe"],
        returned_count=len(page_items),
    )
    return projected
