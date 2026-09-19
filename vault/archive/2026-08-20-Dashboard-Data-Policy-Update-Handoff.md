# 2026-08-20 — Dashboard Data Policy Update (Pull-all + COLOR exclude)

Status: ✅ current
Author: Bee (lite) / Arm directive
Files: `backend/update_data.py`, `backend/symbol_master` (DB)

## What changed

### 1. Removed 15% yfinance price-gap skip (pull ALL)
- `update_data.py` `fetch_yfinance()` no longer compares the first fetched close
  to the last DB close and skips symbols with >15% deviation.
- Removed the `yf_skipped` stat plumbing (init, dry-run print, summary print).
- Docstring updated with the owner directive note (2026-08-20).

Reason (Arm): "เราคุยกันแล้วว่าดึงทั้งหมด" — complete coverage over defensive
skipping. Low-priced stocks showed large % gaps from small absolute changes.

### 2. Excluded COLOR from the ORD master
- `symbol_master` COLOR set to `status='excluded'`, reason
  `Owner override: Settrade Symbol not found [COLOR]` (was `inactive`).
- Drops out of `_active_scan_symbols` → scan + dashboard.
- Official Settrade weekly master sync remains authoritative: if COLOR
  reappears on the official list it will be auto-reactivated.

## Verification (real, not exit-0-only)
- `symbol_master`: 931 active / 1 excluded (COLOR)
- `_active_scan_symbols`: 904 symbols, COLOR NOT in list
- `dashboard.html` + `dashboard_snapshot.json`: 0 occurrences of COLOR
- Backend + dashboard containers recreated; `/health` = ok
- Tests: test_sync_settrade_master, test_symbol_master_exclusion,
  test_screening, test_universal_scanning → 3 passed (6 deselected)

## How to re-run
- yfinance path: `update_data.py --source yfinance` (no more skip)
- COLOR: `UPDATE symbol_master SET status='excluded', reason='...' WHERE symbol='COLOR'`
  (or wait for weekly master sync which will reactivate if official)

## Related
- `vault/Decisions.md` (2 new decisions, 2026-08-20)
- `vault/Architecture.md` (data flow note)
- Commit `bf20af1` (update_data.py)