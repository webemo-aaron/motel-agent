#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE='http://127.0.0.1:8653/api/motel'
OUT=Path(__file__).resolve().parents[1]/'data'/'historical_rates'
OUT.mkdir(parents=True, exist_ok=True)

now=datetime.now(timezone.utc)
ts=now.isoformat()
day=now.strftime('%Y-%m-%d')

snap=requests.get(f"{BASE}/rates/snapshot?limit=500",timeout=20).json()
alerts=requests.get(f"{BASE}/rates/alerts?limit=500",timeout=20).json()
health=requests.get(f"{BASE}/rates/health",timeout=20).json()

bundle={'captured_at':ts,'snapshot':snap.get('items',[]),'alerts':alerts.get('items',[]),'health':health}
(OUT/f'rates_bundle_{day}.json').write_text(json.dumps(bundle,indent=2))

jsonl=OUT/'rates_history.jsonl'
with jsonl.open('a',encoding='utf-8') as f:
    for r in snap.get('items',[]):
        row={'captured_at':ts,'kind':'snapshot',**r}
        f.write(json.dumps(row)+'\n')
    for r in alerts.get('items',[]):
        row={'captured_at':ts,'kind':'alert',**r}
        f.write(json.dumps(row)+'\n')

print(f"archived snapshot_rows={len(snap.get('items',[]))} alert_rows={len(alerts.get('items',[]))} -> {OUT}")
