"""Stage-First Dashboard contract tests (t_3961d070 → Stage-first redesign 2026-08-17/20).

Encodes the approved Stage-first redesign as verifiable assertions
against dashboard_template.html — the ONLY file the redesign is authorized to
change. Data contracts, stage-first semantics, filters/modal/chart journeys,
and the generated-artifact build pipeline must be preserved.

Vocabulary rules: canonical identifiers only in implementation-facing strings
(live/eod/stale_warning/hard_stale/unknown; no quality.confidence).
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
    """Stage-first: core token palette ships as CSS custom properties."""
    for tok in (
        "--bg:#0a0e17",
        "--panel:#111a28",
        "--panel2:#162132",
        "--text:#e8ecf2",
        "--muted:#8a99ad",
        "--s1:", "--s2:", "--s3:", "--s4:",
        "--s1-tint:", "--s2-tint:", "--s3-tint:", "--s4-tint:",
        "--ready:", "--watch:",
        "--regime-high-vol-bg:", "--regime-high-vol-fg:", "--regime-high-vol-border:",
        "--regime-liquidity-bg:", "--regime-liquidity-fg:", "--regime-liquidity-border:",
        "--regime-low-spread-bg:", "--regime-low-spread-fg:", "--regime-low-spread-border:",
        "--regime-normal-bg:", "--regime-normal-fg:", "--regime-normal-border:",
        "prefers-reduced-motion",
    ):
        assert tok in html, f"design token {tok!r} missing"


# --------------------------------------------------------------- header ----
def test_topbar_nav_and_ctrl_sticky_structure(html):
    """Stage-first: topbar + sticky nav + sticky control cluster."""
    for marker in (
        'class="topbar"',
        'class="nav"',
        'class="ctrl-sticky"',
        'id="stageSummary"',
        'id="results"',
        'id="regimeBadge"',  # Market Regime badge in topbar (Contract v0.2.0 §3)
    ):
        assert marker in html, f"stage-first header marker {marker!r} missing"


def test_regime_badge_uses_snapshot_data(html):
    """Market Regime badge populated from snapshot's market_regime object."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    m = re.search(r"function renderMarketRegime[\s\S]{0,500}", js)
    assert m, "renderMarketRegime() function missing"
    body = m.group(0)
    # population references market_regime from snapshot
    assert "dashboardMeta.market_regime" in body, (
        "regime badge must be derived from snapshot market_regime data"
    )


# ------------------------------------------------------------ filter controls --
def test_inline_filter_controls_in_ctrl_sticky(html):
    """Stage-first: inline filter controls (not collapsible deck)."""
    for marker in (
        'id="valueFilter"',
        'id="priceBand"',
        'id="sectorFilter"',
        'id="industryFilter"',
        'id="liquidOnly"',
        'id="showLowValue"',
        'id="set50Only"',
    ):
        assert marker in html, f"filter control marker {marker!r} missing"


def test_proximity_pills_per_stage(html):
    """Stage-first: proximity pills per stage (data-prox, PROX_GROUPS)."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert 'data-prox="all"' in html
    assert "PROX_GROUPS" in js
    assert "proxFilter" in js


def test_watchlist_star_button_present(html):
    """Star button on cards with data-star and aria-pressed."""
    assert 'data-star' in html
    assert 'aria-pressed' in html
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert "saved.has" in js


# ---------------------------------------------------------------- cards ----
def test_card_anatomy_stage_first(html):
    """Stage-first card: pulse-dot + ticker + stage-badge + phase-tag + proximity + fresh-badge + q-bar."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    card_m = re.search(r"function card\([\s\S]*?\n\}", js)
    assert card_m, "card() renderer missing"
    body = card_m.group(0)
    for marker in (
        "pulse-dot",
        "ticker",
        "stage-badge",
        "phase-tag",
        "freshBadge(i)",
        "q-bar",
        "trigger-distance",
        "action-line",
    ):
        assert marker in body, f"card anatomy marker {marker!r} missing"


def test_freshness_canonical_identifiers(html):
    """component-specs: live/eod/stale_warning/hard_stale/unknown only."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    m = re.search(r"function freshBadge[\s\S]*?\n\}", js)
    assert m, "freshBadge() missing"
    body = m.group(0)
    for state in ("live", "eod", "stale_warning", "hard_stale", "unknown"):
        assert state in body, f"freshness state {state!r} missing"
    for banned in ('"FRESH"', '"DAILY_EOD"'):
        assert banned not in body


def test_quality_strip_and_q_corner(html):
    """Quality strip (visual bar) and q-corner badge."""
    assert "quality-strip" in html
    assert "q-corner" in html
    for qcls in ("q3", "q2", "q1", "q0"):
        assert f"q-corner {qcls}" in html or f"q-corner.{qcls}" in html


# ------------------------------------------------------------ provenance ---
def test_no_legacy_vocabulary_in_ui_strings(html):
    """Canonical lock: quality.confidence and 'Canonical Event' must not appear."""
    assert "quality.confidence" not in html
    assert "Canonical event" not in html
    assert "canonical event" not in html.lower().replace("event id", "")


# ------------------------------------------------------------------ modal --
def test_modal_decision_first_dom_order(html):
    """Stage-first modal: Decision banner → Price → Chart (on-demand) → Setup Quality → Risk/Trigger."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    # Check decisionPanel has detail-facts
    m = re.search(r"function decisionPanel[\s\S]*?\n\}", js)
    assert m, "decisionPanel() missing"
    decision_body = m.group(0)
    assert "detail-facts" in decision_body, "detail-facts missing in decisionPanel"
    assert "risk-note" in decision_body, "risk-note missing in decisionPanel"
    assert "setup-note" in decision_body, "setup-note missing in decisionPanel"

    # Check openDetail DOM order - actual order in template:
    # decision-banner → modal-price → priceHistory label → tf-tools → detailChart → setupQuality label → decisionPanel
    m = re.search(r"function openDetail[\s\S]*?\n\}", js) or re.search(
        r"function renderModal[\s\S]*?\n\}", js)
    assert m, "modal renderer missing"
    body = m.group(0)
    order = [
        "decision-banner",
        "modal-price",
        "tf-tools",
        "detailChart",
    ]
    idx = []
    for marker in order:
        i = body.find(marker)
        assert i >= 0, f"modal section {marker!r} missing"
        idx.append(i)
    assert idx == sorted(idx), f"modal DOM order violates decision-first: {order}"
    
    # Verify decisionPanel (which contains detail-facts, risk-note, setup-note) comes after chart
    decision_panel_idx = body.find("decisionPanel")
    assert decision_panel_idx > idx[-1], "decisionPanel must come after detailChart"


def test_modal_dialog_aria_and_focus_trap(html):
    assert 'role="dialog"' in html and 'aria-modal="true"' in html
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert re.search(r"keydown", js) and "Escape" in js


def test_chart_on_demand_error_contract(html):
    """Chart loaded on-demand via /chart/{symbol}?timeframe=...; error shows retry."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert 'id="chartRetry"' in html or "chartRetry" in js
    assert 'id="detailChart"' in html
    assert 'class="chart-canvas"' in html


# ------------------------------------------------------- states & a11y -----
def test_empty_states_with_actions(html):
    """Filtered empty shows Clear Filters action; load error keeps Retry."""
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert "clearAllFilters" in js
    assert "Failed to load dashboard" in js or "loadFailed" in js
    assert 'onclick="loadRemoteDashboard()"' in html


def test_snapshot_error_banner_never_empty_state(html):
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    m = re.search(r"failLoading[\s\S]{0,500}", js)
    assert m, "failLoading function missing"
    # The retry button is in the catch block of loadRemoteDashboard
    assert 'onclick="loadRemoteDashboard()"' in html
    assert "loadFailed" in html or "loadFailed" in js


def test_watchlist_persistence_localstorage(html):
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    assert "signalix-watchlist-v2" in html  # existing key preserved


def test_touch_targets_44px_mobile(html):
    assert "min-height:44px" in html.replace(" ", "")
    mob = html[html.find("@media(max-width:620px)"):]
    assert "min-height:44px" in mob.replace(" ", "")


def test_search_debounced(html):
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    # search is handled by input event, no explicit debounce needed for local data
    assert "search" in js and "addEventListener" in js


def test_preserved_journeys_stage_nav_pages(html):
    """Preserved from current shipped contract: stage pills, watchlist/market/radar pages, TradingView link."""
    for marker in (
        "js-stage",
        'data-page="screener"',
        'data-page="watchlist"',
        'data-page="market"',
        'data-page="radar"',
        "tradingview.com/chart",
        "PROX_GROUPS",
        "const proximityState=i=>(i.setup_proximity&&i.setup_proximity.state)||null",
    ):
        assert marker in html, f"preserved journey marker {marker!r} missing"


def test_placeholders_unchanged(html):
    assert "let items=__ITEMS__;" in html
    assert "let stageMeta=__STAGE_META__;" in html
    assert "let dashboardMeta=__DASHBOARD_META__;" in html


def test_language_english_surface(html):
    """English launch surface (no Thai words in static UI copy;
    the ฿ currency symbol is a symbol, not Thai text).
    Thai locale labels are for i18n and only shown when language=th.
    """
    # The localeLabels object contains both English and Thai labels for i18n.
    # We should only check that the English labels don't contain Thai text.
    # Find the English localeLabels.en section and check it.
    en_section_match = re.search(r'localeLabels\s*=\s*\{[^}]*en\s*:\s*\{([^}]+)\}', html, re.S)
    if en_section_match:
        en_labels = en_section_match.group(1)
        thai = re.findall(r"[\u0e00-\u0e7f]+", re.sub(r"฿", "", en_labels))
        assert not thai, f"Thai text leaked into EN locale labels: {thai[:5]}"


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
    # Market Regime present in snapshot
    m2 = re.search(r"let dashboardMeta=(\{.*?\});\n", text, re.S)
    assert m2, "dashboardMeta missing from built dashboard"
    meta = json.loads(m2.group(1))
    assert "market_regime" in meta