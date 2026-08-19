# 2026-08-19 — Intraday evaluator ExecStopPost import failure

## Symptom

`signalix-intraday.service` fetched 60m data but ended with `failed`, and the
post-fetch evaluator did not run. This made intraday freshness look stale or
incomplete even when candles had been stored.

## Root Cause

`ExecStopPost` executed `backend/run_intraday_evaluation.py` as a standalone
script. `run_intraday_evaluation.py` imported `intraday_evaluator` as a
top-level module, while `intraday_evaluator.py` uses package-relative imports
such as `.scan_history`. Python therefore raised:

```text
ImportError: attempted relative import with no known parent package
```

The `--intraday-limit 10` flag was not the universe limit; it means 10 bars per
active symbol. The production fetch still used the full active ORD universe.

## Fix

- `backend/run_intraday_evaluation.py` now imports with:
  `from .intraday_evaluator import evaluate`.
- `backend/signalix-intraday.service` now runs the evaluator from the project
  root as:
  `python -m backend.run_intraday_evaluation`.
- The live unit was copied, daemon-reloaded, and verified with
  `systemd-analyze verify`.

## Verification

- `test_intraday_resilience.py`: 4 passed.
- Direct module evaluator run: exit 0; evaluated 920 symbols, priced 725.
- Real systemd service run outside the SET session: fetch skipped cleanly and
  `ExecStopPost` exited 0 with evaluator output.
- `signalix-intraday.service` is no longer failed after the verification run.
- Dashboard/API remained healthy; the same-day EOD scan/dashboard had already
  refreshed successfully.

## Prevention / Skill or Memory Update

- Always run package-relative Signalix CLIs with `python -m backend.<module>`
  from `/root/signalix`, never by executing the `.py` file directly.
- Keep the service unit and `/root/signalix/backend/signalix-intraday.service`
  source synchronized.
- Verify both fetch failure and post-fetch evaluator paths, not only HTTP 200
  or candle upsert counts.
