#!/usr/bin/env python3
import requests

UI_BASE = "http://127.0.0.1:5182"
API_BASE = "http://127.0.0.1:8653/api/motel"

ui_paths = ["/", "/desk", "/manager", "/rates", "/settings"]
api_paths = [
    "/overview",
    "/manager/plan",
    "/manager/recommendations",
    "/manager/automation/settings",
    "/manager/automation/logs",
    "/rates/summary",
    "/rates/snapshot?limit=5",
    "/rates/alerts?limit=5",
    "/rates/calendar",
]

failed = 0
for path in ui_paths:
    r = requests.get(UI_BASE + path, timeout=10)
    ok = r.status_code == 200 and '<div id="root"' in r.text
    print(f"UI {path}: {'PASS' if ok else 'FAIL'} ({r.status_code})")
    if not ok:
        failed += 1

for path in api_paths:
    r = requests.get(API_BASE + path, timeout=10)
    ok = 200 <= r.status_code < 300
    print(f"API {path}: {'PASS' if ok else 'FAIL'} ({r.status_code})")
    if not ok:
        failed += 1

print(f"\nTOTAL FAILURES: {failed}")
raise SystemExit(1 if failed else 0)
