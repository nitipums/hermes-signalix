import json
d = json.load(open('/app/dashboard_snapshot.json'))
items = d.get('items', [])
print("num items:", len(items))
syms = [i.get('symbol') for i in items]
print("SET in items:", 'SET' in syms, "SETCLMV:", 'SETCLMV' in syms)
for s in ['SET', 'SETCLMV', 'SET50', 'SET100', 'sSET', 'JAS', 'AAV', 'CPAXT', 'LH', 'M', 'MAJOR', 'SC', 'BH']:
    if s in syms:
        it = [i for i in items if i.get('symbol') == s][0]
        ds = it.get('dailyState') or {}
        ev = it.get('dailyState') or {}
        print(s, "| group=", it.get('group'), "| primary=", ev.get('primaryState'),
              "| tt=", it.get('tt'), "| rs=", it.get('rs'), "| rsi=", it.get('rsi'),
              "| setupState=", ev.get('setupState'), "| lifecycle=", ev.get('lifecycleState'))
    else:
        print(s, "NOT IN ITEMS")
