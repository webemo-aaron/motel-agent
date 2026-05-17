#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt
import requests

BASE='http://127.0.0.1:8653/api/motel'

def main():
    rooms = requests.get(BASE + '/rooms?status=available', timeout=20).json()
    if not rooms:
        print('no available rooms for kiosk seed')
        return
    room_id = str(rooms[0]['id'])
    d = dt.date.today() + dt.timedelta(days=1)
    payload = {
        'guest_name': 'Taylor Guest',
        'check_in': d.isoformat(),
        'check_out': (d + dt.timedelta(days=2)).isoformat(),
        'room_id': room_id,
        'rate_per_night': 149,
        'phone': '2075551234',
        'party_size': 2,
    }
    r = requests.post(BASE + '/kiosk/book', json=payload, timeout=20)
    if r.status_code not in (200, 201):
        print('seed booking non-200', r.status_code, r.text[:200])
    else:
        print('kiosk guest seed complete', r.json().get('id'))

if __name__ == '__main__':
    main()
