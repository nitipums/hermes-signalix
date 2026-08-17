#!/usr/bin/env python3
"""Exit non-zero for known SET market holidays so systemd ExecCondition skips jobs."""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from zoneinfo import ZoneInfo

# Maintain this calendar when SET publishes annual trading holidays.
SET_CLOSED_DATES = {
    "2026-08-12": "SET market holiday (Her Majesty Queen Sirikit The Queen Mother's Birthday)",
}


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--date", help="test a Bangkok YYYY-MM-DD date")
    args = parser.parse_args()
    today = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(ZoneInfo("Asia/Bangkok")).date()
    reason = SET_CLOSED_DATES.get(today.isoformat())
    if reason:
        print(f"Signalix market-job skip: {today.isoformat()} — {reason}")
        return 1  # ExecCondition=1 skips the service without marking it failed.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
