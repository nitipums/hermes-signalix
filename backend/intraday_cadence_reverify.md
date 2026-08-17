# Signalix intraday cadence — re-verification snapshot (REVIEW CORRECTED)
(task t_4929de63, assigned khim, 2026-08-14 — rework after Bee/lite final review REJECTED t_29dade86)

## Sources inspected (read-only)
- Live deployed unit: `systemctl cat signalix-intraday.service`
  - `/etc/systemd/system/signalix-intraday.service` (unguarded ExecStartPost)
- Drop-in: `/etc/systemd/system/signalix-intraday.service.d/market-calendar.conf`
  - `ExecCondition=/root/.venv_img/bin/python /root/signalix/backend/set_market_day_guard.py`
- Validation: `systemd-analyze verify signalix-intraday.service` → exit 0 (clean).
- Log: `/root/signalix/intraday_update_log.txt` — 1481 lines as of this write (the log is a LIVE production log that grows ~1 line/minute; all counts below are a point-in-time snapshot captured during this review run, not a static assertion).
- Test suite: `backend/test_intraday_cadence.py` → 7/7 OK (see below).
- Backend source (for drift comparison only): `backend/signalix-intraday.service` (uncommitted / not deployed — see config-drift decision below).

## timer
signalix-intraday.timer:
  OnCalendar=Mon..Fri *-*-* *:00/15 Asia/Bangkok  => 4 fires/hour (:00/:15/:30/:45)

Verification (host has systemd-analyze available):
  $ systemd-analyze calendar --iterations=8 'Mon..Fri *-*-* *:00/15 Asia/Bangkok'
  Normalized form: Mon..Fri *-*-* *:00/15:00 Asia/Bangkok
  Iterations land on :00/:15/:30/:45 — confirms 4/hr, NOT every minute.

## Expected vs observed cadence
intraday_update_log.txt = 1481 lines as of this write (the file grew from 1445 to 1481 since the prior review; the log is a LIVE production log that grows ~1 line/minute, so the counts below are a point-in-time snapshot captured during this review run — see the log-as-of note in Sources inspected above).

Expected in-session firing count/day (weekday, not holiday):
- morning continuous: 10:15-12:30  -> 10:15, 10:30, 10:45, 11:00, 11:15, 11:30, 11:45, 12:00, 12:15, 12:30 = 10
- afternoon continuous: 14:45-16:30 -> 14:45, 15:00, 15:15, 15:30, 15:45, 16:00, 16:15, 16:30 = 8 (incl 16:30)
- total expected = 18 live fires/day in-session (10 morning + 8 afternoon = 18).
- The 18 in-session-fires/day invariant is deterministic and correct; left untouched.

Observed counts in log (grep-verified on the live file):
| Marker                                                      | grep pattern                              | Count |
|-------------------------------------------------------------|-------------------------------------------|-------|
| ExecStart runs — `update_data.py` (prints "intraday-only shortlist") | `intraday-only shortlist` (no mode=)     | 7     |
| ExecStartPost runs — `run_intraday_evaluation.py` (prints `{"mode": "active",...}`) | `"mode": "active"`            | 91    |
| Holiday skip — "Signalix market-job skip" (ExecCondition, set_market_day_guard.py) | `Signalix market-job skip`   | 24    |
| Outside-session skip — "outside SET continuous session ... skip" | `outside SET continuous session`          | 79    |

Breakdown of the 91 evaluator (ExecStartPost) runs:
|- 77 are preceded by an "outside SET continuous session ... skip" line → these ran OUTSIDE the SET session window under the LIVE config (un­guarded ExecStartPost). This is the real, measured figure (70 tiered + 7 stale active-60m).
|- 14 are preceded by a data-fetch line ("intraday 60m: ... rows offered") → these ran in-session, after ExecStart produced a shortlist.
|- 77 + 14 = 91 (matches the total in the live log). 0 preceded by anything else.
|- NOTE: of the 79 "outside SET continuous session ... skip" lines, 77 are immediately followed by an evaluator JSON. The 2 that are NOT are L1 (followed by the 2026-08-12 holiday skip) and L1308 (followed by a consecutive 1700 tiered skip). This explains the 79-vs-77 gap and is NOT folded into the evaluator-predecessor count.

Breakdown of the 79 "outside SET continuous session ... skip" lines:
- 7  × `signalix active 60m: ... skip`   (STALE — NOT emitted by the current deployment. Neither the live unit's ExecStartPost nor the backend source emits this wording — grep "evaluator skipped" = 0 in the live log. These 7 lines (log 1268-1280) are leftover from a prior unit revision.)
- 70 × `signalix tiered 60m: ... skip`   (ExecStart update_data outside-session skip)
- 2  × `signalix intraday: ... skip`      (legacy monitor outside-session skip)

NOTE on the prose list in the prior review: the prior doc was internally
inconsistent — it stated a morning-plus-afternoon count of 18 using a
nine-plus-nine split, while simultaneously enumerating ten morning and ten
afternoon timestamp entries. The tested invariant
(backend/test_intraday_cadence.py::test_expected_live_fires_per_day) is
18 = morning 10 + afternoon 8. The narrative enumeration is corrected
here to 10+8=18 so it matches the 10 + 8 breakdown above. The 18 invariant
and the 7/7 test suite are untouched.

### What runs, exactly
LIVE unit (`/etc/systemd/system/signalix-intraday.service`):
- ExecStart = `update_data.py --source settrade --intraday-only ...` wrapped in a
  bash session guard (1015-1230 / 1445-1630 BKK). Outside the window it prints
  "outside SET continuous session ... skip" and exits 0 → 7 in-session shortlists
  observed in the log.
- ExecStartPost = `run_intraday_evaluation.py --mode active --interval 60m`
  with NO bash session guard on the live unit. It fires on every timer tick
  that passes ExecCondition, regardless of SET hours. This is why 91 evaluator
  JSON lines appear, 77 of them outside the SET session window (the log is live;
  see snapshot note above).

## Holiday gate (live deployed mechanism)
- The LIVE drop-in `/etc/systemd/system/signalix-intraday.service.d/market-calendar.conf`
  uses `ExecCondition=/root/.venv_img/bin/python /root/signalix/backend/set_market_day_guard.py`.
- `set_market_day_guard.py` exits 1 on known SET closed dates (e.g. 2026-08-12)
  and prints "Signalix market-job skip: <date> — <reason>". 24 such skip lines
  are present in the log → the ExecCondition drop-in is correct and active.
- There is NO `ConditionPathExists=!` in the deployed unit. The prior doc's
  risk flag about a "no-op ConditionPathExists=!" was WRONG — that form exists
  only in the uncommitted backend source file (`backend/signalix-intraday.service`,
  line 8), which is NOT what systemd is running. On the deployed unit,
  `systemd-analyze verify` passes clean and the holiday skips are empirically
  observed (24 lines on 2026-08-12).
- The false "ConditionPathExists=! no-op" risk is REMOVED from this document.

## Deterministic tests
`backend/test_intraday_cadence.py` run with /root/.venv_img/bin/python3 -m unittest:
  Ran 7 tests OK
  - test_star_frac_15_fires_four_times_hourly  (4/hr invariant)
  - test_star_frac_not_every_minute            (regression vs monitor.timer)
  - test_star_frac_30
  - test_morning_session_bounds
  - test_afternoon_session_bounds
  - test_lunch_gap_is_outside_session
  - test_expected_live_fires_per_day           -> assertEqual(len(live),18)

The 7/7 suite and the 18 in-session-fires/day invariant are correct; left untouched.

## Root-cause fix in effect (on the live unit only)
- ExecStart (update_data.py) carries the bash session guard — it does NOT run
  outside SET hours, and prints "outside SET continuous session ... skip".
- ExecStartPost (evaluator) on the LIVE unit is UNGUARDED — it runs on every
  timer fire that passes ExecCondition, which is exactly what the log shows
  (91 evaluator runs, 75 outside SET hours; log is live, see snapshot note).
  The evaluator does NOT skip itself; it runs with changes=[] when there is
  no new data.

## CONFIG-DRIFT DECISION (RAISED — not auto-resolved)
There is a confirmed drift between the canonical backend source and the live
deployed unit:

  backend/signalix-intraday.service (source, UNCOMMITTED / NOT deployed):
    - [Unit] ConditionPathExists=!/root/signalix/backend/set_market_day_guard.py
      (no-op path-existence check, NOT an executor guard — this is the
       condition the prior worker incorrectly flagged as the live mechanism)
    - ExecStartPost CARRIES the bash session guard (mirrors ExecStart), so the
      evaluator would NOT run outside SET hours.

  /etc/systemd/system/signalix-intraday.service (LIVE deployed):
    - NO ConditionPathExists in [Unit].
    - ExecCondition drop-in (market-calendar.conf) for the holiday gate
      (correct, active — 24 holiday skips observed).
    - ExecStartPost is UNGUARDED — evaluator runs on every tick (91 runs,
      77 outside SET hours; log is live, see snapshot note).

Two options. Bee/lite must choose; khim will not pick silently:

  OPTION A — Reconcile source → match live (unguarded ExecStartPost +
            ExecCondition drop-in). Pros: matches observed production
            behaviour; evaluator runs every tick (cheap, changes=[] when idle).
            Cons: loses the source-level in-session guard on ExecStartPost;
            copy-over from source re-introduces the old bug.

  OPTION B — Reconcile live → match source (add bash session guard to
            ExecStartPost; replace ConditionPathExists=! with the ExecCondition
            drop-in). Pros: evaluator only runs in-session; source and live
            converge. Cons: 75 outside-session evaluator runs currently happen (log
            is live);
            switching to guarded ExecStartPost changes live behaviour
            (fewer evaluator runs / fewer dashboard emissions).

REGRESSION RISK (either way): the backend `signalix-intraday.service` is NOT
symlinked/installed into `/etc/systemd/system/` — it is a hand-maintained copy.
A future `cp backend/signalix-intraday.service /etc/...` would silently revert
the live ExecCondition drop-in to the no-op ConditionPathExists=! AND drop the
bash guard off ExecStartPost, re-introducing both defects at once.
Recommendation (for Bee decision): install the canonical unit via a symlink
or a `systemd-analyze verify` CI gate so source and deploy cannot drift.

## Sandbox note
The agent sandbox cannot run the real systemd timer end-to-end; live cadence
validation was done via `systemd-analyze calendar` (4/hr confirmed) + grep counts
on the real production log + `systemd-analyze verify` (exit 0). The 18-in-session-
fires/day invariant is deterministic and covered by the 7/7 test suite.
