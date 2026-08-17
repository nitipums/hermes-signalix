import os, json
from dotenv import load_dotenv
load_dotenv("/app/.env")
import psycopg2
from screening import group_scan_results
from scan_history import active_breakout_events
pg = psycopg2.connect(host=os.getenv("POSTGRES_HOST","postgres"), port=int(os.getenv("POSTGRES_PORT","5432")),
                      user=os.getenv("POSTGRES_USER"), password=os.getenv("POSTGRES_PASSWORD"),
                      dbname=os.getenv("POSTGRES_DB"))
events = active_breakout_events(pg)
print("events has SC:", 'SC' in events, "LH:", 'LH' in events, "MAJOR:", 'MAJOR' in events)
scan=json.load(open('/app/scan_results.json'))
allrows=[r for v in scan.get('groups',{}).values() for r in v]
def test(sym):
    rows=[r for r in allrows if r.get('symbol')==sym]
    if not rows:
        print(sym,"not found"); return
    r=rows[0]
    g = group_scan_results([r], {sym: events[sym]} if sym in events else {})
    flat=[(k, rr.get('daily_state',{}).get('primary_state')) for k,v in g.items() for rr in v]
    print(sym, "with event ->", flat)
    g2 = group_scan_results([r], {})
    flat2=[(k, rr.get('daily_state',{}).get('primary_state')) for k,v in g2.items() for rr in v]
    print(sym, "no event   ->", flat2)
    print("   close=", r.get('close'), "tt=", (r.get('trend_template') or {}).get('conditions_met'), "rs=", (r.get('trend_template') or {}).get('rs_rating'))
for s in ['SC','LH','MAJOR','BH','JAS']:
    test(s)
pg.close()
