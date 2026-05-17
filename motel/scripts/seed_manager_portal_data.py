#!/usr/bin/env python3
"""Seed manager portal demo data via live motel API."""
import datetime as dt
import random
import uuid
import requests

API = "http://127.0.0.1:8653/api/motel"


def post(path, payload):
    r = requests.post(API + path, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def patch(path, payload):
    r = requests.patch(API + path, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def seed():
    suffix = uuid.uuid4().hex[:6]
    today = dt.date.today()
    days30 = 30

    # campaigns
    for i, ch in enumerate(["email", "sms", "meta", "google"]):
        post('/manager/campaigns', {
            'week': f'Week {i+1}',
            'channel': ch,
            'objective': 'drive midweek occupancy',
            'offer': f'{10 + i*5}% off stay-{suffix}',
            'budget': 75 + i * 25,
            'owner': 'manager',
            'status': 'planned',
        })

    # events
    for i in range(4):
        day = (today + dt.timedelta(days=7 + i*7)).isoformat()
        post('/manager/events', {
            'date': day,
            'title': f'Basecamp Group {i+1} {suffix}',
            'event_type': 'group',
            'expected_guests': random.choice([8, 12, 16]),
            'room_block': random.choice([0, 1, 2]),
            'notes': 'seeded event',
            'status': 'planned',
        })

    # leads + stage progression
    lead_ids = []
    for i, seg in enumerate(["wedding", "retreat", "ski", "family"]):
        lead = post('/manager/leads', {
            'name': f'{seg.title()} Lead {suffix}-{i+1}',
            'segment': seg,
            'contact': f'{seg}-{suffix}@example.com',
            'source': 'seed_script',
            'est_value': 800 + i * 300,
            'stage': 'new',
            'notes': 'seeded lead',
        })
        lead_ids.append(lead['id'])

    for idx, lid in enumerate(lead_ids[:3]):
        patch(f'/manager/leads/{lid}', {
            'stage': ['qualified', 'proposal', 'won'][idx],
            'notes': 'auto-progressed by seed script'
        })

    # ebike settings + bookings
    post('/manager/ebike/settings', {
        'fleet_size': 200,
        'half_day_rate': 55,
        'full_day_rate': 85,
    })

    for i in range(3):
        try:
            post('/manager/ebike/bookings', {
                'guest_name': f'Rider {suffix}-{i+1}',
                'date': (today + dt.timedelta(days30+i+1)).isoformat(),
                'duration': random.choice(['half_day', 'full_day']),
                'bikes': 1,
                'status': 'reserved',
            })
        except requests.HTTPError:
            pass

    print('Seed complete:', suffix)


if __name__ == '__main__':
    seed()
