#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import hashlib
import random
import time
import re
import statistics
import urllib.parse
import urllib.request
from pathlib import Path

PRICE_RE = re.compile(r"\$\s?(\d{2,4})(?:\.\d{2})?")


def nth_weekday(year, month, weekday, n):
    d = dt.date(year, month, 1)
    while d.weekday() != weekday:
        d += dt.timedelta(days=1)
    d += dt.timedelta(days=7 * (n - 1))
    return d


def last_weekday(year, month, weekday):
    d = (dt.date(year + (month == 12), 1 if month == 12 else month + 1, 1)
         - dt.timedelta(days=1))
    while d.weekday() != weekday:
        d -= dt.timedelta(days=1)
    return d


def us_holidays(year):
    return {
        "New Year": dt.date(year, 1, 1),
        "MLK Weekend": nth_weekday(year, 1, 0, 3),
        "Presidents Weekend": nth_weekday(year, 2, 0, 3),
        "Memorial Day": last_weekday(year, 5, 0),
        "Juneteenth": dt.date(year, 6, 19),
        "Independence Day": dt.date(year, 7, 4),
        "Labor Day": nth_weekday(year, 9, 0, 1),
        "Indigenous Peoples Day": nth_weekday(year, 10, 0, 2),
        "Veterans Day": dt.date(year, 11, 11),
        "Thanksgiving": nth_weekday(year, 11, 3, 4),
        "Christmas": dt.date(year, 12, 25),
        "New Years Eve": dt.date(year, 12, 31),
    }


def load_events(path: Path):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    return data.get('events', [])


def date_range(start, end):
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    d = s
    while d <= e:
        yield d
        d += dt.timedelta(days=1)


def is_winter_package_date(d: dt.date):
    return d.month in (12, 1, 2, 3) and d.weekday() in (4, 5)


def generate_query_dates(start_date, years=2, events=None):
    end_date = start_date + dt.timedelta(days=365 * years)
    bucket = {}

    def add(d, tag):
        if start_date <= d <= end_date:
            bucket.setdefault(d.isoformat(), set()).add(tag)

    d = start_date
    while d <= end_date:
        if d.month in (6, 7, 8, 9, 10) and d.weekday() in (4, 5):
            if int(d.strftime('%U')) % 2 == 0:
                add(d, 'summer_fall_peak_weekend')
        if is_winter_package_date(d):
            add(d, 'winter_weekend_package')
            add(d, 'min_stay_2_nights')
        d += dt.timedelta(days=1)

    for y in range(start_date.year, end_date.year + 1):
        for name, h in us_holidays(y).items():
            add(h, f'holiday:{name}')
            for delta in (-1, 1, 2):
                add(h + dt.timedelta(days=delta), f'holiday_shoulder:{name}')

    for ev in (events or []):
        for d in date_range(ev['start'], ev['end']):
            add(d, f"event:{ev['name']}")
            for t in ev.get('tags', []):
                add(d, f"event_tag:{t}")

    out = []
    for ds in sorted(bucket.keys()):
        out.append({'check_in': ds, 'tags': sorted(bucket[ds])})
    return out


def fetch_html(query, timeout_seconds=8, retries=3, cache_dir: Path | None = None, min_delay_ms=250):
    url = 'https://html.duckduckgo.com/html/?' + urllib.parse.urlencode({'q': query})
    key = hashlib.sha1(query.encode('utf-8')).hexdigest()[:16]
    cache_path = (cache_dir / f"{key}.html") if cache_dir else None
    if cache_path and cache_path.exists():
        return cache_path.read_text(encoding='utf-8', errors='ignore')

    ua_pool = [
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    ]

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': random.choice(ua_pool), 'Accept-Language': 'en-US,en;q=0.9'})
            with urllib.request.urlopen(req, timeout=timeout_seconds) as r:
                html = r.read().decode('utf-8', errors='ignore')
            if cache_path:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(html, encoding='utf-8')
            time.sleep(min_delay_ms / 1000.0)
            return html
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep((0.4 * attempt) + random.random() * 0.2)
    raise last_err


def parse_results(html):
    blocks = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)</div>', html, re.S)
    out = []
    for href, title, tail in blocks[:4]:
        clean = re.sub(r'<.*?>', ' ', (title + ' ' + tail))
        clean = re.sub(r'\s+', ' ', clean).strip()
        prices = [int(m) for m in PRICE_RE.findall(clean)]
        out.append({'url': href, 'snippet': clean[:220], 'prices': prices})
    return out


def pick_rate(candidates):
    vals = [p for c in candidates for p in c['prices'] if 40 <= p <= 1200]
    if not vals:
        return None
    return int(round(statistics.median(vals)))


def build_queries(prop, check_in, checkout):
    pretty_in = dt.date.fromisoformat(check_in).strftime('%b %d %Y')
    pretty_out = dt.date.fromisoformat(checkout).strftime('%b %d %Y')
    return [
        f"{prop['name']} {prop['city']} rates {pretty_in}",
        f"{prop['name']} booking {check_in} to {checkout}",
        f"{prop['name']} weekend package {pretty_in} {pretty_out}",
    ]


def update_rate_map(rate_map_path, rows):
    data = {'generated_at': None, 'entries': []}
    if rate_map_path.exists():
        data = json.loads(rate_map_path.read_text(encoding='utf-8'))

    idx = {(e['property'], e['check_in']): e for e in data.get('entries', [])}
    for r in rows:
        key = (r['property'], r['check_in'])
        prior = idx.get(key)
        cur = int(r['estimated_rate_usd']) if str(r['estimated_rate_usd']).isdigit() else None
        if prior:
            prev = prior.get('current_rate')
            prior['previous_rate'] = prev
            prior['current_rate'] = cur
            prior['last_seen'] = r['timestamp']
            prior['signals_found'] = int(r['signals_found'])
            prior['source'] = r['top_source']
            prior['season_tags'] = r['season_tags']
            prior['checkout_date'] = r['checkout_date']
            if prev and cur:
                prior['pct_change'] = round(((cur - prev) / prev) * 100, 2)
        else:
            idx[key] = {
                'property': r['property'], 'city': r['city'], 'check_in': r['check_in'],
                'checkout_date': r['checkout_date'], 'season_tags': r['season_tags'],
                'current_rate': cur, 'previous_rate': None, 'pct_change': None,
                'signals_found': int(r['signals_found']), 'source': r['top_source'],
                'last_seen': r['timestamp']
            }

    merged = sorted(idx.values(), key=lambda x: (x['check_in'], x['property']))
    out = {'generated_at': dt.datetime.utcnow().isoformat(timespec='seconds') + 'Z', 'entries': merged}
    rate_map_path.parent.mkdir(parents=True, exist_ok=True)
    rate_map_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
    return merged


def write_alerts(alert_path, entries, threshold_pct=12.0):
    rows = []
    for e in entries:
        pct = e.get('pct_change')
        if pct is None:
            continue
        if abs(pct) >= threshold_pct:
            rows.append({
                'property': e['property'], 'city': e['city'], 'check_in': e['check_in'],
                'previous_rate': e['previous_rate'], 'current_rate': e['current_rate'],
                'pct_change': pct, 'season_tags': e.get('season_tags', ''), 'source': e.get('source', '')
            })

    alert_path.parent.mkdir(parents=True, exist_ok=True)
    with alert_path.open('w', newline='', encoding='utf-8') as f:
        fields = ['property','city','check_in','previous_rate','current_rate','pct_change','season_tags','source']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def run(args):
    start = dt.date.today()
    events = load_events(Path(args.events))
    query_dates = generate_query_dates(start, years=args.years, events=events)

    dates_payload = {
        'generated_at': dt.datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'window_start': start.isoformat(),
        'window_end': (start + dt.timedelta(days=365 * args.years)).isoformat(),
        'winter_policy': {
            'effective_months': [12,1,2,3], 'allowed_arrival_days': ['Friday','Saturday'],
            'min_nights': 2, 'notes': 'Weekend packages only Fri-Sat from Dec through Mar'
        },
        'events_file': str(Path(args.events).resolve()),
        'dates': query_dates
    }
    dates_out = Path(args.dates_out)
    dates_out.parent.mkdir(parents=True, exist_ok=True)
    dates_out.write_text(json.dumps(dates_payload, indent=2), encoding='utf-8')

    properties = json.loads(Path(args.config).read_text(encoding='utf-8'))['properties']
    if args.max_properties > 0:
        properties = properties[:args.max_properties]
    filtered_dates = query_dates
    if args.only_tag:
        filtered_dates = [d for d in query_dates if any(args.only_tag in t for t in d['tags'])]
    dates_to_use = filtered_dates if args.max_dates == 0 else filtered_dates[:args.max_dates]

    rows = []
    for qd in dates_to_use:
        check_in = dt.date.fromisoformat(qd['check_in'])
        winter_pkg = is_winter_package_date(check_in)
        min_nights = 2 if winter_pkg else 1
        checkout = check_in + dt.timedelta(days=min_nights)

        for prop in properties:
            candidates = []
            for term in build_queries(prop, check_in.isoformat(), checkout.isoformat()):
                try:
                    candidates.extend(parse_results(fetch_html(term, timeout_seconds=args.query_timeout)))
                except Exception as e:
                    candidates.append({'url':'', 'snippet':f'ERROR: {e}', 'prices':[]})

            nightly = pick_rate(candidates)
            package = (nightly * min_nights) if (nightly is not None and min_nights > 1) else ''
            rows.append({
                'timestamp': dt.datetime.utcnow().isoformat(timespec='seconds') + 'Z',
                'property': prop['name'], 'city': prop['city'],
                'check_in': check_in.isoformat(), 'checkout_date': checkout.isoformat(),
                'min_nights': min_nights,
                'season_tags': '|'.join(qd['tags']),
                'estimated_rate_usd': nightly if nightly is not None else '',
                'package_rate_estimate_usd': package,
                'signals_found': sum(len(c['prices']) for c in candidates),
                'top_source': (candidates[0]['url'] if candidates else '')
            })

    out_csv = Path(args.out)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    entries = update_rate_map(Path(args.rate_map_out), rows)
    alert_count = write_alerts(Path(args.alerts_out), entries, threshold_pct=args.alert_threshold_pct)

    print(f"Query dates generated: {len(query_dates)} -> {dates_out}")
    print(f"Rows written: {len(rows)} -> {out_csv}")
    print(f"Rate map updated: {args.rate_map_out}")
    print(f"Rate-change alerts: {alert_count} -> {args.alerts_out}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Rate aggregation v2.1 with events + package logic + alerts')
    ap.add_argument('--config', default=str(Path(__file__).with_name('competitors_bethel.json')))
    ap.add_argument('--events', default=str(Path(__file__).resolve().parents[1] / 'data' / 'local_events_bethel_region.json'))
    ap.add_argument('--out', default=str(Path(__file__).resolve().parents[1] / 'data' / 'competitor_rates_v2_latest.csv'))
    ap.add_argument('--dates-out', default=str(Path(__file__).resolve().parents[1] / 'data' / 'rate_query_dates_2y.json'))
    ap.add_argument('--rate-map-out', default=str(Path(__file__).resolve().parents[1] / 'data' / 'competitor_rate_map.json'))
    ap.add_argument('--alerts-out', default=str(Path(__file__).resolve().parents[1] / 'data' / 'competitor_rate_alerts.csv'))
    ap.add_argument('--years', type=int, default=2)
    ap.add_argument('--max-dates', type=int, default=16, help='0 = all dates')
    ap.add_argument('--only-tag', default='', help='Optional tag filter (e.g., winter_weekend_package)')
    ap.add_argument('--alert-threshold-pct', type=float, default=12.0)
    ap.add_argument('--query-timeout', type=int, default=8)
    ap.add_argument('--retries', type=int, default=3)
    ap.add_argument('--cache-dir', default=str(Path(__file__).resolve().parents[1] / 'data' / 'rate_cache'))
    ap.add_argument('--min-delay-ms', type=int, default=250)
    ap.add_argument('--max-properties', type=int, default=0, help='0 = all properties')
    run(ap.parse_args())
