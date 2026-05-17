#!/usr/bin/env python3
"""Seed local rate intelligence data files with realistic sample rows."""
from __future__ import annotations
from pathlib import Path
import csv, json
from datetime import date, datetime, timedelta, timezone

ROOT = Path('/home/webemo-aaron/projects/webemo-hermes-agent/motel/data')


def seed_snapshot(today: date) -> None:
    path = ROOT / 'competitor_rates_v2_latest.csv'
    headers = [
        'timestamp','property','city','check_in','checkout_date','min_nights',
        'season_tags','estimated_rate_usd','package_rate_estimate_usd','signals_found','top_source'
    ]
    properties = [
        ('The Bethel Inn Resort','Bethel, ME',219),
        ('The Inn at the Rostay','Bethel, ME',179),
        ('Jordan Hotel','Newry, ME',289),
        ('West Bethel Motel','Bethel, ME',149),
    ]
    rows=[]
    for i,(prop,city,base) in enumerate(properties):
        check_in = today + timedelta(days=7+i)
        rows.append({
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'property': prop,
            'city': city,
            'check_in': check_in.isoformat(),
            'checkout_date': (check_in + timedelta(days=2)).isoformat(),
            'min_nights': '2',
            'season_tags': 'summer_weekend|event_pressure',
            'estimated_rate_usd': str(base),
            'package_rate_estimate_usd': str(base + 30),
            'signals_found': '3',
            'top_source': 'booking.com',
        })
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader(); w.writerows(rows)


def seed_alerts(today: date) -> None:
    path = ROOT / 'competitor_rate_alerts.csv'
    headers = ['property','city','check_in','previous_rate','current_rate','pct_change','season_tags','source']
    rows = [
        {
            'property':'Jordan Hotel','city':'Newry, ME','check_in':(today+timedelta(days=8)).isoformat(),
            'previous_rate':'249','current_rate':'289','pct_change':'16.06','season_tags':'event_pressure','source':'expedia'
        },
        {
            'property':'The Bethel Inn Resort','city':'Bethel, ME','check_in':(today+timedelta(days=9)).isoformat(),
            'previous_rate':'239','current_rate':'219','pct_change':'-8.37','season_tags':'promo_drop','source':'booking.com'
        },
    ]
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader(); w.writerows(rows)


def seed_health() -> None:
    path = ROOT / 'competitor_rate_pipeline_health.json'
    payload = {
        'timestamp_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'healthy': True,
        'checks': [
            {'name':'snapshot_csv_present','ok':True},
            {'name':'alerts_csv_present','ok':True},
            {'name':'event_calendar_present','ok':True},
        ]
    }
    path.write_text(json.dumps(payload, indent=2))


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    today = date.today()
    seed_snapshot(today)
    seed_alerts(today)
    seed_health()
    print('Rate intelligence seed complete')


if __name__ == '__main__':
    main()
