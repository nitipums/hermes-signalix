"""Run a named curated watchlist through Signalix's shared scanner."""
import json
import os
import sys

from markets import get_universe
from screening import scan_universe


def main(key="us_ai_buildout"):
    universe = get_universe(key)
    rows, near = scan_universe(
        min_conditions=0,
        market=universe.market,
        benchmark_symbol=universe.benchmark_symbol,
        symbols=universe.symbols,
        min_price=universe.min_price,
        min_today_trade_value=universe.min_today_trade_value,
    )
    payload = {
        "universe": universe.key,
        "market": universe.market,
        "benchmark_symbol": universe.benchmark_symbol,
        "source": "yahoo_chart_bootstrap_unverified",
        "symbols_requested": list(universe.symbols),
        "symbols_evaluated": [row["symbol"] for row in rows],
        "results": rows,
        "near_miss_6of8": near,
    }
    path = os.path.join(os.path.dirname(__file__), f"{universe.key}_scan.json")
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2, default=str)
    print(json.dumps({"path": path, "evaluated": len(rows),
                      "latest_dates": sorted({row["last_date"] for row in rows}),
                      "groups": {str(i): sum(row["trend_template"]["conditions_met"] == i for row in rows)
                                 for i in range(9)}}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "us_ai_buildout")
