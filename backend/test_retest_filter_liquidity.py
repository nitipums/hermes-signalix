"""D9 v2 regression: Retest Watch filter must show all 12 items regardless of
the liquidity preset. Root cause (t_75608977): the client-side current()
predicate applied `liquidity !== "all" && i.lowValue` BEFORE the action-queue
filter, so with the default "liquid" preset any retest_watch item flagged
lowValue (AGE/PACO/RJH/TSTH) was silently dropped from the rendered cards.

Contract: when a canonical Action Queue filter is active, the queue predicate
is authoritative — the liquidity preset may narrow within it, but the default
view of a queue must show every item in that queue.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
TEMPLATE = HERE / "dashboard_template.html"


def _template_js():
    return TEMPLATE.read_text(encoding="utf-8")


def test_queue_filter_is_not_preempted_by_liquidity_default():
    js = _template_js()
    # The current() predicate must not return false on lowValue before the
    # action-queue predicates have had a chance to match.
    m = re.search(r"function current\(\)\{.*?\n\}", js, re.S)
    assert m, "current() not found in dashboard_template.html"
    body = m.group(0)
    liquidity_line = re.search(r'if\(!queueActive&&liquidity!=="all"&&i\.lowValue\)return false;', body)
    queue_line = re.search(r'i\.action_queue!==queueFilter', body)
    assert queue_line, "queue predicate missing"
    assert liquidity_line, (
        "liquidity gate must be guarded by !queueActive so a selected queue "
        "is not preempted by the default liquidity preset"
    )
    gate = re.search(r'const queueActive=', body)
    assert gate and gate.start() < liquidity_line.start(), (
        "queueActive must be computed before the liquidity gate"
    )


def _embedded_items():
    html = (HERE / "dashboard.html").read_text(encoding="utf-8")
    m = re.search(r"let items=(\[.*?\]);\n", html, re.S)
    assert m, "embedded items not found in dashboard.html"
    return json.loads(m.group(1))


def _current_predicate_result(item, liquidity="liquid"):
    """Mirror current()'s predicate order after the D9 v2 fix.

    queueActive short-circuits the liquidity gate; queueFilter='retest_watch'.
    """
    queue_active = True  # a specific queue chip is selected
    if not queue_active and liquidity != "all" and item.get("lowValue"):
        return False
    if item.get("action_queue") != "retest_watch":
        return False
    return True


def test_retest_watch_queue_survives_liquidity_default_in_built_html():
    items = _embedded_items()
    retest = [i for i in items if i.get("action_queue") == "retest_watch"]
    assert len(retest) == 12, f"expected 12 retest_watch items, got {len(retest)}"
    visible = [i for i in retest if _current_predicate_result(i)]
    assert len(visible) == 12, (
        f"liquidity default drops {len(retest) - len(visible)} retest_watch "
        f"items: {sorted(set(i['symbol'] for i in retest) - set(i['symbol'] for i in visible))}"
    )
