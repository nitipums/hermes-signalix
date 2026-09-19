"""Run and persist the isolated Signalix VCP Finder 60m scan."""
from __future__ import annotations

import json
import os
import psycopg2

from vcp_finder_db import find_vcp_universe_60m, persist_vcp_run


PG = dict(
    host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    user=os.getenv("POSTGRES_USER", "signalix"),
    password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
    dbname=os.getenv("POSTGRES_DB", "signalix"),
)


def main():
    pg = psycopg2.connect(**PG)
    try:
        payload = find_vcp_universe_60m(pg, market="TH")
        run_id = persist_vcp_run(pg, payload)
        states = {}
        for row in payload["results"]:
            states[row["state"]] = states.get(row["state"], 0) + 1
        print(json.dumps({"run_id": run_id, "universe": payload["universe"], "states": states}))
    finally:
        pg.close()


if __name__ == "__main__":
    main()
