"""Read-only presentation projection for the reconciled Signalix taxonomy.

This module deliberately reads the review artifact and never writes scan state,
canonical history, or producer rows.  It is the versioned boundary between the
immutable Daily scan and the dashboard presentation.
"""
from __future__ import annotations
import copy, json, os
from collections import Counter

ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "reconciled_artifacts")
if not os.path.exists(os.path.join(ARTIFACT_DIR, "reconciled_taxonomy.jsonl")):
    ARTIFACT_DIR = os.path.dirname(__file__)
ARTIFACT_PATH = os.path.join(ARTIFACT_DIR, "reconciled_taxonomy.jsonl")
PROJECTION_VERSION = "reconciled-taxonomy-v1"
PRIMARY_GROUPS = (
    ("fresh", "FRESH BREAKOUT — VALIDATE, NOT AN ENTRY", "VALIDATE FRESH", 9),
    ("extended", "EXTENDED BREAKOUT — DO NOT CHASE", "DO NOT CHASE", 9),
    ("pre_break", "PRE-BREAK — WAIT FOR QUALIFIED BREAKOUT", "WAIT FOR QUALIFIED BREAKOUT", 349),
    ("base", "BASE — BUILDING, WAIT FOR CONFIRMATION", "WAIT FOR CONFIRMATION", 113),
    ("pullback_holding", "PULLBACK HOLDING — WATCH REFERENCE", "WATCH / WAIT", 28),
    ("pullback_under_reference", "PULLBACK UNDER REFERENCE — NO ENTRY", "NO LONG / REVIEW REFERENCE", 5),
    ("no_long_setup", "NO LONG SETUP — DO NOT FORCE A TRADE", "NO LONG", 200),
    ("failed_setup_no_event", "FAILED SETUP — NO QUALIFIED EVENT", "NO LONG / WAIT FOR NEW SETUP", 5),
)
PRIMARY_META = {k: {"id": k, "label": label, "action": action, "count": count}
               for k, label, action, count in PRIMARY_GROUPS}
EXPECTED_COUNTS = {k: v["count"] for k, v in PRIMARY_META.items()}


def load_rows(path: str = ARTIFACT_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    rows.sort(key=lambda r: r["symbol"])
    return rows


def validate_rows(rows: list[dict]) -> None:
    symbols = [r.get("symbol") for r in rows]
    if len(rows) != 718 or len(set(symbols)) != 718:
        raise ValueError(f"reconciled projection requires 718 unique rows, got {len(rows)}")
    counts = Counter(r.get("primary_group") for r in rows)
    if dict(counts) != EXPECTED_COUNTS:
        raise ValueError(f"reconciled primary counts mismatch: {dict(counts)}")
    for r in rows:
        if r.get("primary_group") not in PRIMARY_META:
            raise ValueError(f"unknown primary group for {r.get('symbol')}")


def artifact_map(path: str = ARTIFACT_PATH) -> dict[str, dict]:
    rows = load_rows(path); validate_rows(rows)
    return {r["symbol"]: r for r in rows}


def apply_projection(items: list[dict], path: str = ARTIFACT_PATH) -> list[dict]:
    """Overlay presentation fields while retaining all existing raw/card fields.

    Owner's rule: scan the FULL universe (every ORD with data). Symbols absent
    from the reconciled taxonomy artifact are kept (not dropped) — they simply
    get a neutral default projection so the stage-first dashboard shows them.
    """
    by_symbol = artifact_map(path)
    out = []
    for item in items:
        symbol = item.get("symbol")
        a = by_symbol.get(symbol)
        x = copy.deepcopy(item)
        # The setup-candidate contract is the sole primary decision surface.
        # Reconciled taxonomy data remains available to audit consumers but
        # must not add a competing group/status/action to canonical items.
        canonical = {"symbol", "as_of", "data_status", "trend", "wave", "setup",
                     "context", "bonus_evidence", "decision", "provenance"} <= set(x)
        if canonical:
            from mvp_snapshot import sanitize_mvp_item
            x = sanitize_mvp_item(x)
            if a:
                audit = dict(x.get("audit") or {})
                audit["reconciled_row"] = copy.deepcopy(a)
                x["audit"] = audit
            x.setdefault("projection_version", PROJECTION_VERSION)
            out.append(x)
            continue
        if a:
            group = a["primary_group"]
            x.update({
                "projection_version": PROJECTION_VERSION,
                "group": group, "primary_group": group,
                "primary_label": a["primary_label"], "primary_action": a["primary_action"],
                "status": a["primary_label"], "action": a["primary_action"],
                "quality_badge": a.get("quality_badge", "not_flagged_low_quality"),
                "freshness_badge": a.get("freshness_badge", "unknown"),
                "lifecycle_badge": a.get("lifecycle_badge", group),
                "data_confidence": a.get("data_confidence", "low"),
                "evidence_date": a.get("evidence_date"), "raw_last_date": a.get("raw_last_date"),
                "evidence_summary": a.get("evidence_summary", ""),
                "reconciliation_reason": a.get("reconciliation_reason", "projection default: incomplete artifact row"),
                "old_group_mapping": a.get("old_mapping", {}),
                "nida_producer_fields": a.get("nida_producer_fields", {}),
                "producer": {"nida": a.get("nida_producer_fields", {}),
                             "nida_expected_primary_state": a.get("nida_expected_primary_state"),
                             "ploy_classification": a.get("ploy_proposed_classification"),
                             "mali_quality": a.get("mali_data_quality")},
                "canonical_context": {"event_id": a.get("nida_latest_event_id"),
                                      "stage": a.get("nida_canonical_event_stage"),
                                      "event_count": a.get("nida_canonical_event_count", 0),
                                      "owning_run_id": a.get("nida_owning_run_id"),
                                      "owning_scan_date": a.get("nida_owning_scan_date")},
                "confirmed_failure": False,
            })
            if a.get("freshness_badge") == "stale":
                freshness = {
                    "status": "stale",
                    "source": "price_data",
                    "as_of": a.get("evidence_date") or a.get("raw_last_date"),
                    "reason": a.get("reconciliation_reason") or "source date differs from owning canonical scan date",
                }
                x["dataFreshness"] = freshness
                x.setdefault("dailyState", {})["dataFreshness"] = freshness.copy()
            x["raw_reconciled_row"] = {"nida_expected_primary_state": a.get("nida_expected_primary_state"),
                                        "nida_actual_primary_state": a.get("nida_actual_primary_state"),
                                        "nida_failure_bucket": a.get("nida_failure_bucket"),
                                        "nida_flags": a.get("nida_flags")}
        else:
            # Symbol not in the reconciled taxonomy: keep it with a neutral
            # projection so the stage-first dashboard still shows it.
            x.setdefault("group", x.get("scan_group") or "waiting_breakout")
            x.setdefault("primary_group", x["group"])
            x.setdefault("projection_version", PROJECTION_VERSION)
            x.setdefault("confirmed_failure", False)
        out.append(x)
    return sorted(out, key=lambda x: x["symbol"])


def project_artifact_rows(path: str = ARTIFACT_PATH) -> list[dict]:
    """Minimal deterministic snapshot useful for tests and cache rebuilds."""
    rows = load_rows(path); validate_rows(rows)
    return [{"projection_version": PROJECTION_VERSION, **r, "confirmed_failure": False} for r in rows]


def snapshot_payload(items: list[dict], scan_time=None) -> dict:
    items = sorted(items, key=lambda x: x["symbol"])
    return {"projection_version": PROJECTION_VERSION, "scan_time": scan_time,
            "market": "TH", "refresh": "progressive_cards", "items": items,
            "primary_groups": PRIMARY_META,
            "primary_counts": dict(Counter(x["primary_group"] for x in items)),
            "badge_counts": {name: dict(Counter(x.get(name, "unknown") for x in items)) for name in
                             ("quality_badge", "freshness_badge", "lifecycle_badge", "data_confidence")}}
