#!/usr/bin/env python3
"""Lite gate: auto-block ready cards missing ## Files (fail-closed).
Runs every 30s via cron. Checks signalix board for ready cards without ## Files header.
"""
import sqlite3, pathlib
DB = pathlib.Path("/root/.hermes/kanban/boards/signalix/kanban.db")
import subprocess, sys
if not DB.exists():
    sys.exit(0)
con = sqlite3.connect(str(DB))
con.row_factory = sqlite3.Row
rows = con.execute("SELECT id, title, body FROM tasks WHERE status='ready'").fetchall()
blocked = 0
for r in rows:
    body = r["body"] or ""
    if "## Files" not in body:
        tid = r["id"]
        print(f"BLOCK {tid} missing ## Files")
        subprocess.run(["env","-u","HERMES_DELEGATED_CHILD_CONTEXT","hermes","kanban","--board","signalix","block",tid,"REJECT gate1: missing ## Files — Card-Template-LOCKED (auto-gate 30s)"], timeout=10)
        blocked += 1
print(f"checked {len(rows)} ready, blocked {blocked}")
