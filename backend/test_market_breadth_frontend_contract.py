from pathlib import Path


TEMPLATE = Path(__file__).with_name("market_breadth_template.html")


def test_market_breadth_route_and_template_are_separate_from_trend_map():
    html = TEMPLATE.read_text(encoding="utf-8")
    server = (TEMPLATE.parent / "mvp_server.py").read_text(encoding="utf-8")
    assert "/market-breadth" in html
    assert "/api/market-breadth?range=" in html
    assert "Daily Trend Map" not in html
    assert 'href="/trend-map"' in html
    assert 'template_path = os.path.join(_BACKEND_DIR, "market_breadth_template.html")' in server


def test_market_breadth_template_has_accessible_cross_page_navigation_with_breadth_active():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<nav class="page-nav" aria-label="Primary navigation">' in html
    assert '<a class="page-nav__link" href="/trend-map">Trend Map</a>' in html
    assert '<a class="page-nav__link page-nav__link--active" href="/market-breadth" aria-current="page">Market Breadth</a>' in html
    assert '.page-nav__link:focus-visible' in html
    assert 'overflow-x:hidden' in html


def test_mb3_is_one_editorial_visual_per_metric_with_beginner_copy():
    html = TEMPLATE.read_text(encoding="utf-8")
    for marker in (
        "Daily Market Participation",
        "How many active-ORD stocks advanced, declined, or were unchanged today.",
        "Cumulative Market Participation",
        "The running total of advances minus declines across the selected history.",
        "Main trend composition",
        "The current composition of daily evidence across Main Trend 1–4.",
        "Base / Weak / Damaged (Main 1)",
        "Recovery / Advance (Main 2)",
        "Pullback / Weakening / Distribution (Main 3)",
        "Deterioration / Breakdown (Main 4)",
        "Stocks above moving averages",
        "Above MA50", "Above MA200",
        "New highs and new lows", "prior rolling range",
        "Up-volume and down-volume shares", "percentage share of valid",
        "raw volume", "Stocks above moving averages history",
    ):
        assert marker in html
    assert html.count("Cumulative Market Participation") == 2  # title + chart aria label
    assert 'class="participation-legend"' not in html
    assert "Main Trend Distribution" not in html
    assert "Stocks Above Key Moving Averages" not in html
    assert "Up-Volume vs Down-Volume" not in html
    assert "cards" not in html
    assert "metric-readout" in html


def test_market_breadth_evidence_precedes_system_status_and_keeps_set_context_compact():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert html.index('id="content"') < html.index('id="status"')
    assert html.index('aria-label="SET Index benchmark"') < html.index("01 / The pulse")
    assert html.count('id="status"') == 1
    assert html.count('id="participation"') == 1
    assert html.count('id="trends"') == 1
    assert html.count('id="ma-bars"') == 1
    assert html.count('id="extremes"') == 1
    assert html.count('id="volume"') == 1


def test_market_breadth_local_quality_details_preserve_as_of_and_api_exclusions():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "valid / " in html
    assert "x.coverage_rows" in html
    assert "unchanged_rows" in html
    assert "unchanged_or_blocked_rows" in html
    assert "blocked_rows" in html
    assert "invalid_or_excluded_rows" in html
    assert "As of " in html
    assert "detail(source,asOf)" in html
    assert "02 / Direction" in html
    assert "ad_ratio" not in html


def test_section02_renders_api_owned_direction_without_browser_classification():
    html = TEMPLATE.read_text(encoding="utf-8")
    for marker in (
        "payload.direction", "d.label", "d.status", "Partial coverage",
        "Baseline: ", "Endpoint: ", "Change from baseline: ",
        "d.baseline&&d.baseline.value",
        "d.baseline&&d.baseline.session_date", "d.endpoint&&d.endpoint.value",
        "d.endpoint&&d.endpoint.session_date", "d.delta", "reason(d)",
        'id="direction-summary"', 'id="direction-interpretation"',
    ):
        assert marker in html
    assert "Movement changed direction across the selected history; this is descriptive, not a next-session prediction." in html
    assert "label=val(d.label)" in html
    assert 'esc(label)' in html.split('$("direction-summary").innerHTML', 1)[1].split(';', 1)[0]
    assert '$("direction-summary").textContent=val(d.label)' not in html
    summary = html.split('$("direction-summary").innerHTML', 1)[1].split(';', 1)[0]
    assert "reason(d)" not in summary
    assert "incomplete_input_coverage" not in summary
    assert "ad_ratio" not in html
    assert "threshold" not in html.lower()


def test_mb_ui4_has_monochrome_editorial_tokens_motion_and_mobile_story_contract():
    html = TEMPLATE.read_text(encoding="utf-8")
    for marker in (
        "color-scheme:light", "--black", "--white", "--grey-1", "--grey-2",
        "--grey-3", "--trend-up:#C7F36B", "--trend-down:#F05D5E",
        "--trend-pullback:#F2A65A", "--trend-neutral:#98A1A8", "--benchmark:#6FA8FF",
        "@keyframes rise", "prefers-reduced-motion:reduce",
        "is-refreshing", "SIGNALIX", "Market<br>Breadth", "01 / The pulse",
        "02 / Direction", "03 / Structure", "04 / Breadth of trend", "05 / Range",
        "06 / Conviction", "max-width:390px", "overflow-x:hidden", "Data details",
    ):
        assert marker in html
    for legacy in ("--amber", "--teal", "--red", "--blue", "--navy", "color-scheme:dark", ".card", "border-radius", "linear-gradient"):
        assert legacy not in html
    assert "emoji" not in html.lower()


def test_mb_ui5_uses_owner_approved_semantic_trend_tokens_without_legacy_palette():
    html = TEMPLATE.read_text(encoding="utf-8")
    for token in (
        "var(--trend-up)", "var(--trend-down)", "var(--trend-pullback)",
        "var(--trend-neutral)", "var(--benchmark)",
        ".trend-segment.trend-1", ".trend-segment.trend-2",
        ".trend-segment.trend-3", ".trend-segment.trend-4",
        "participation-advancing", "participation-declining",
        "participation-unchanged", "tone:\"trend-up\"", "tone:\"trend-down\"",
    ):
        assert token in html
    for legacy in (
        "--accent", "#c9f04a", ".metric-fill.alt",
        ".trend-segment:nth-child(even)",
        "fill=\"'+(si?\"var(--grey-2)\":\"var(--black)\")",
    ):
        assert legacy not in html
    assert html.count("--trend-up:#C7F36B") == 1
    assert html.count("--trend-down:#F05D5E") == 1
    assert html.count("--trend-pullback:#F2A65A") == 1
    assert html.count("--trend-neutral:#98A1A8") == 1
    assert html.count("--benchmark:#6FA8FF") == 1


def test_market_breadth_template_has_explicit_quality_and_null_states():
    html = TEMPLATE.read_text(encoding="utf-8")
    for marker in (
        "DATA_BLOCKED", "PARTIAL", "Unavailable", "reason_code",
        "Partial coverage", "valid / declared coverage", "stocks observed",
        "null values remain unavailable", "gaps are not connected",
        "FULL / PARTIAL / DATA_BLOCKED", "retry", "status-retry",
    ):
        assert marker in html


def test_market_breadth_header_uses_current_as_of_coverage_fields():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<dt>Freshness</dt><dd id="freshness">' in html
    assert '<dt>Quality</dt><dd id="quality-status">' in html
    assert '$("quality-status").textContent=(payload.quality||{}).status||"Unavailable"' in html
    assert "current_observed_count" in html
    assert "current_blocked_count" in html
    assert "current_declared_count" in html
    assert 'val(u.current_observed_count)+" observed · "+val(u.current_blocked_count)+" blocked · "+val(u.current_declared_count)+" declared"' in html
    assert 'payload.universe&&payload.universe.observed_count' not in html
    assert "MutationObserver" not in html
    assert 'fetch("/api/market-breadth?range=20"' not in html
    assert html.count("fetch(") == 1


def test_market_breadth_template_has_set_context_without_set50():
    html = TEMPLATE.read_text(encoding="utf-8")
    for marker in ("SET Index", "1D change", "20D change", "Source", "price_data"):
        assert marker in html
    assert "SET50" not in html


def test_market_breadth_template_formats_set_benchmark_changes_for_display_only():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "function benchmarkChange" in html
    assert "benchmarkChange(b.change_1d_pct)" in html
    assert "benchmarkChange(b.change_20d_pct)" in html
    assert "String(b.change_1d_pct)" not in html
    assert "String(b.change_20d_pct)" not in html


def test_market_breadth_template_has_exact_range_fetches_and_read_only_safety():
    html = TEMPLATE.read_text(encoding="utf-8")
    for value in ("20", "60", "260", "all"):
        assert f'<option value="{value}"' in html
    assert 'selectedRange="20"' in html
    assert 'fetch("/api/market-breadth?range="+encodeURIComponent(selectedRange)' in html
    assert "actionability!==\"NONE\"" in html
    assert "no previous data is shown" in html
    assert "no calculations, actions, alerts, orders, broker execution, or auto-trading" in html


def test_market_breadth_template_has_no_symbol_level_action_controls():
    html = TEMPLATE.read_text(encoding="utf-8").lower()
    assert "symbol table" not in html
    assert "buy or sell signal" in html
    assert "data-symbol" not in html
    assert "opensharedrawer" not in html
    assert "broker" in html


def test_market_breadth_participation_uses_api_owned_denominator_percentages():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "participation(c.participation,payload.universe||{})" in html
    assert "valid=item.valid_count" in html
    assert "pct=x.percentage" in html
    assert "Number(x.count)/valid*100" not in html


def test_market_breadth_all_visible_percentages_are_api_owned():
    html = TEMPLATE.read_text(encoding="utf-8")
    for marker in (
        "ma.above_ma50&&ma.above_ma50.percentage",
        "ma.above_ma200&&ma.above_ma200.percentage",
        "e.new_high_percentage", "e.new_low_percentage",
        "v.up_percentage", "v.down_percentage",
        'String(n),"percentage"',
        "a.x.percentage",
    ):
        assert marker in html
    for expression in ("v/d*100", "x.total/total*100", "a.x.total/total*100", "v.up+v.down"):
        assert expression not in html
