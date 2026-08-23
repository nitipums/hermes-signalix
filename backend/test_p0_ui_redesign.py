"""P0 UI Redesign contract tests (t_3961d070).

Encodes the approved design packet v3 (t_66d2850c) as verifiable assertions
against dashboard_template.html — the ONLY file the redesign is authorized to
change. Data contracts, stage-first semantics, filters/modal/chart journeys,
and the generated-artifact build pipeline must be preserved.

Vocabulary rules: canonical identifiers only in implementation-facing strings
(live/eod/stale_warning/hard_stale/unknown; Event ID; no quality.confidence).
"""
import json
import re
from pathlib import Path

import pytest

HERE = Path(__file__).parent
TEMPLATE = HERE / "dashboard_template.html"


@pytest.fixture(scope="module")
def html():
    return TEMPLATE.read_text(encoding="utf-8")


# ---------------------------------------------------------------- tokens ---
def test_design_token_system_present(html):
    """Packet §2: core token palette ships as CSS custom properties."""
    for tok in (
        "--bg:#080c14",
        "--panel:#0e1622",
        "--panel-elevated:#141f30",
        "--text-dim:",
        "--s1:", "--s2:", "--s3:", "--s4:",
        "--s1-tint:", "--s2-tint:", "--s3-tint:", "--s4-tint:",
        "--ready:", "--watch:", "--caution:",
        "--fresh-live:", "--fresh-eod:", "--fresh-stale-warning:",
        "--fresh-stale:", "--fresh-unknown:",
        "--star-filled:",
        "prefers-reduced-motion",
    ):
        assert tok in html, f"design token {tok!r} missing"


# --------------------------------------------------------------- header ----
def test_cockpit_header_structure(html):
    """Packet §3/§10: Signal Cockpit header with regime badge, coverage,
    freshness pulse."""
    for marker in (
        'class="cockpit"',
        'aria-label="Signal Cockpit"',
        'id="regimeBadge"',
        'id="coverageCount"',
        'id="freshnessPulse"',
        'id="freshText"',
    ):
        assert marker in html, f"cockpit marker {marker!r} missing"


def test_regime_badge_uses_honest_market_session_source(html):
    """No fabricated HIGH_VOLATILITY regime exists in the data layer; the
    badge must be populated from the snapshot's real market-session/freshness
    provenance, never a hardcoded fake taxonomy value."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    m = re.search(r'getElementById\("regimeBadge"\)[^;]{0,300}', js)
    assert m, "regime badge population code missing"
    # population references market_session or freshness status fields
    assert re.search(r"market_session|marketSession|freshness", js[max(0, m.start() - 400):m.end()]), (
        "regime badge must be derived from snapshot session/freshness data"
    )


# ------------------------------------------------------------ filter deck --
def test_filter_deck_toggle_and_aria(html):
    """Packet §6: collapsible deck with aria-expanded/controls + active count."""
    for marker in (
        'id="filterDeck"',
        'id="filterToggle"',
        'aria-expanded="false"',
        'aria-controls="filterDeck"',
        'id="filterBadge"',
    ):
        assert marker in html


def test_watchlist_filter_toggle_in_deck(html):
    """Packet §11.4: Show-Starred-Only boolean toggle with aria-pressed."""
    assert 'id="watchlistToggle"' in html
    assert 'aria-pressed' in html
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    # filter predicate consults watchlist state and the saved set
    assert re.search(r"watchlistOnly|filters\.watchlist|watchlistFilter", js)


def test_filter_apply_transition_open_submitting_open(html):
    """Packet §6 (single authoritative transition): Apply → SUBMITTING → OPEN,
    deck stays open, focus returns to toggle."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert "SUBMITTING" in js or "submitting" in js
    m = re.search(r"applyFilters[\s\S]{0,900}", js)
    assert m, "applyFilters() missing"
    body = m.group(0)
    assert "focus()" in body, "Apply must return focus to the filter toggle"
    # deck must not be closed by apply
    assert "filterDeck).removeAttribute" not in body and 'filterDeck"\).hidden=true' not in body


def test_clear_all_resets_filters(html):
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    m = re.search(r"clearAllFilters[\s\S]{0,800}", js)
    assert m, "clearAllFilters() missing"
    body = m.group(0)
    assert "filters.watchlist=false" in body
    assert "render()" in body


def test_active_filter_count_badge_updates(html):
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert re.search(r"activeFilterCount|updateFilterBadge|filterBadge", js)


# ---------------------------------------------------------------- cards ----
def test_card_anatomy_decision_fields(html):
    """Packet §4: star + ticker + stage badge + action label + price/change +
    quality + proximity + trigger/risk + freshness + provenance toggle."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    card_m = re.search(r"function card\([\s\S]*?\n\}", js)
    assert card_m, "card() renderer missing"
    body = card_m.group(0)
    for marker in ("data-star", "ticker", "stage-badge", "action-label",
                   "quality-badge", "proximity-badge", "Trigger:", "Risk:",
                   "freshBadge(i)", 'provenanceDetails(i,"card")'):
        assert marker in body, f"card anatomy marker {marker!r} missing"


def test_freshness_two_tier_canonical_identifiers(html):
    """component-specs §2.9: live/eod/stale_warning/hard_stale/unknown only.
    No uppercase FRESH/DAILY_EOD aliases in the implementation vocabulary."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    m = re.search(r"function freshBadge[\s\S]*?\n\}", js)
    assert m, "freshBadge() missing"
    body = m.group(0)
    for state in ("live", "eod", "stale_warning", "hard_stale", "unknown"):
        assert state in body, f"freshness state {state!r} missing"
    for banned in ('"FRESH"', '"DAILY_EOD"', 'data-fresh="stale"'):
        assert banned not in body


def test_stale_warning_threshold_labels(html):
    """>15min ≤60min amber warning vs >60min red hard stale (packet §8)."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert "Stale Warning" in html or "stale warning" in html.lower()
    assert "Hard Stale" in html or "hard stale" in html.lower()
    # two-tier: stale_warning identifier present in implementation vocabulary
    assert "stale_warning" in html and "hard_stale" in html
    # threshold documentation present (>15min / >60min)
    assert ">15min" in html and ">60min" in html


# ------------------------------------------------------------- provenance --
def test_provenance_details_shape_card_and_modal_unique_ids(html):
    """Packet §7 / component-specs §2.6: identical details/summary pattern on
    card and modal with instance-unique IDs and matching aria-controls; all
    seven canonical fields in order."""
    seven = ["Source Snapshot", "Event ID", "Scan Run", "Data Timestamp (UTC)",
             "Invalidation Condition", "Hard Gate Blocks", "Regime Context"]
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    m = re.search(r"function provenanceDetails[\s\S]*?\n\}", js)
    assert m, "shared provenanceDetails() renderer missing"
    body = m.group(0)
    idx = [body.find(f) for f in seven]
    assert all(i >= 0 for i in idx), f"provenance fields missing: {seven}"
    assert idx == sorted(idx), "provenance field order must match canonical order"
    assert 'prov-${' in body or "prov-" + "${" in body, (
        "provenance DOM id must be instance-unique (symbol-scoped)"
    )
    assert 'aria-controls=' in body and "aria-expanded" in body


def test_no_legacy_vocabulary_in_ui_strings(html):
    """Canonical lock: quality.confidence and 'Canonical Event' must not appear
    as UI-facing implementation vocabulary."""
    assert "quality.confidence" not in html
    assert "Canonical event" not in html
    assert "canonical event" not in html.lower().replace("event id", "")


# ------------------------------------------------------------------ modal --
def test_modal_decision_first_dom_order(html):
    """Packet §11.3 acceptance: Decision block → Chart → Freshness →
    Provenance → Trigger/Risk → Evidence in modal DOM output order."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    m = re.search(r"function openDetail[\s\S]*?\n\}", js) or re.search(
        r"function renderModal[\s\S]*?\n\}", js)
    assert m, "modal renderer missing"
    body = m.group(0)
    order = ["modal-decision", "timeframe-chips", "chart-canvas",
             "modal-freshness", "provenance", "modal-trigger-risk"]
    idx = []
    for marker in order:
        i = body.find(marker)
        assert i >= 0, f"modal section {marker!r} missing"
        idx.append(i)
    assert idx == sorted(idx), f"modal DOM order violates decision-first: {order}"


def test_modal_dialog_aria_and_focus_trap(html):
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert 'role="dialog"' in html and 'aria-modal="true"' in html
    assert re.search(r"focusTrap|trapFocus|Tab.*modal|modal.*Tab", js) or \
           re.search(r"keydown", js) and "Tab" in js


def test_chart_error_contract_retry_button(html):
    """Chart failure: inline error + Retry for original TF; fallback chain
    1D→1W→1M→1h preserved (AC-UI-001)."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert 'id="chartRetry"' in html or "chartRetry" in js
    fb = re.search(r"function fallback\(symbol,tf,gen\)\{[\s\S]*?\n\}", js)
    assert fb, "chart fallback chain missing"
    chain = fb.group(0)
    for tf in ('"1D"', '"1W"', '"1M"'):
        assert tf in chain or tf.replace('"', '') in chain


# ------------------------------------------------------- states & a11y -----
def test_empty_states_with_actions(html):
    """Filtered empty shows Clear Filters action; load error keeps Retry."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert "Clear Filters" in js or "clearAllFilters" in js
    assert "Failed to load dashboard" in js
    assert 'onclick="loadRemoteDashboard()"' in html


def test_snapshot_error_banner_never_empty_state(html):
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    m = re.search(r"failLoading[\s\S]{0,500}", js)
    assert m and "Retry" in m.group(0)


def test_watchlist_persistence_localstorage(html):
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert "signalix-watchlist-v2" in html  # existing key preserved


def test_touch_targets_44px_mobile(html):
    assert "min-height:44px" in html.replace(" ", "")
    mob = html[html.find("@media(max-width:620px)"):]
    assert "min-height:44px" in mob.replace(" ", "")


def test_search_debounced_200ms(html):
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert re.search(r"debounce|setTimeout[^)]*200", js), "search debounce missing"


def test_preserved_journeys_stage_nav_queue_chips_presets(html):
    """Preserved from current shipped contract: stage pills, Action Queue chips,
    preset screeners, watchlist/market pages, TradingView link."""
    for marker in (
        "js-stage",
        "data-queue",
        "PRESETS",
        'data-page="screener"',
        'data-page="watchlist"',
        'data-page="market"',
        "tradingview.com/chart",
        "PROX_GROUPS",
        "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
    ):
        assert marker in html, f"preserved journey marker {marker!r} missing"


def test_placeholders_unchanged(html):
    assert "let items=__ITEMS__;" in html
    assert "let stageMeta=__STAGE_META__;" in html


def test_language_english_surface(html):
    """Packet handoff: English launch surface (no Thai words in static UI copy;
    the ฿ currency symbol is a symbol, not Thai text)."""
    thai = re.findall(r"[\u0e00-\u0e7f]+", re.sub(r"฿", "", html))
    assert not thai, f"Thai text leaked into EN surface: {thai[:5]}"


# -------------------------------------------------- built-artifact gate ---
def test_built_dashboard_matches_template_contract():
    """The generated dashboard.html must be rebuilt from the redesigned
    template (build pipeline intact): embedded items parse and stage meta
    exists."""
    built = HERE / "dashboard.html"
    if not built.exists():
        pytest.skip("dashboard.html not built yet")
    text = built.read_text(encoding="utf-8")
    m = re.search(r"let items=(\[.*?\]);\n", text, re.S)
    assert m, "embedded items missing from built dashboard"
    items = json.loads(m.group(1))
    assert len(items) > 0
    assert "__ITEMS__" not in text and "__STAGE_META__" not in text
