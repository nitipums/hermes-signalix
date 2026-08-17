import os, json
from dotenv import load_dotenv
load_dotenv("/app/.env")
import psycopg2
pg = psycopg2.connect(host=os.getenv("POSTGRES_HOST","postgres"), port=int(os.getenv("POSTGRES_PORT","5432")),
                      user=os.getenv("POSTGRES_USER"), password=os.getenv("POSTGRES_PASSWORD"),
                      dbname=os.getenv("POSTGRES_DB"))
cur = pg.cursor()
# instrument types
cur.execute("SELECT DISTINCT symbol, instrument_type FROM price_data WHERE symbol IN ('SET','SETCLMV','SET50','SET100','sSET') AND market='TH'")
print("INSTRUMENT TYPES:", cur.fetchall())
# active breakout events (mirror active_breakout_events SQL)
cur.execute("""
SELECT DISTINCT ON (e.symbol)
    e.symbol,e.trigger_price,e.origin,e.pre_break_pivot_low,e.qualified_on,o.stage,o.failure_reason
FROM daily_canonical_breakout_events e
LEFT JOIN LATERAL (
    SELECT stage,failure_reason FROM daily_canonical_breakout_event_observations
    WHERE event_id=e.id ORDER BY observed_on DESC, created_at DESC LIMIT 1) o ON TRUE
JOIN daily_canonical_scan_runs er ON er.id=e.scan_run_id
ORDER BY e.symbol,e.qualified_on DESC,e.created_at DESC,e.id DESC
""")
rows=cur.fetchall()
syms=[r[0] for r in rows]
print("ACTIVE EVENT SYMBOLS COUNT:", len(rows))
for s in ['SC','LH','BH','JAS','AAV','CPAXT','M','MAJOR']:
    if s in syms:
        r=[x for x in rows if x[0]==s][0]
        print(" EVENT", s, "trigger=",r[1],"origin=",r[2],"stage=",r[5],"fr=",r[6])
    else:
        print(" EVENT", s, "NONE")
# scan_results.json current groups for target symbols
scan=json.load(open('/app/scan_results.json'))
allrows=[r for v in scan.get('groups',{}).values() for r in v]
print("scan_results groups symbols count:", len(allrows))
for s in ['SET','SETCLMV','SC','LH','BH','JAS','AAV','CPAXT','M','MAJOR']:
    it=[r for r in allrows if r.get('symbol')==s]
    if it:
        r=it[0]
        ds=r.get('daily_state') or {}
        print(" SCAN", s, "group=",r.get('scan_group'),"primary=",ds.get('primary_state'),"stage=",ds.get('stage'))
    else:
        print(" SCAN", s, "NOT IN scan_results groups")
cur.close(); pg.close()
