#!/usr/bin/env python3
from __future__ import annotations
import csv
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "motel" / "scripts"
DATA = ROOT / "motel" / "data"
RUNNER = SCRIPTS / "rate_aggregation_v2.py"


def run_case(name: str, max_dates: int, only_tag: str = ""):
    out_csv = DATA / f"competitor_rates_exp_{name}.csv"
    dates_out = DATA / f"rate_query_dates_exp_{name}.json"
    alerts_out = DATA / f"competitor_rate_alerts_exp_{name}.csv"
    cmd = [
        str(ROOT / '.venv' / 'bin' / 'python'), str(RUNNER),
        '--out', str(out_csv),
        '--dates-out', str(dates_out),
        '--alerts-out', str(alerts_out),
        '--max-dates', str(max_dates),
        '--max-properties', '2',
        '--query-timeout', '5',
        '--retries', '3',
        '--min-delay-ms', '300',
    ]
    if only_tag:
        cmd += ['--only-tag', only_tag]

    
    timed_out = False
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as e:
        timed_out = True
        proc = subprocess.CompletedProcess(cmd, 124, stdout=(e.stdout or ""), stderr=(e.stderr or "timeout"))
    rows = []
    if out_csv.exists():
        with out_csv.open(newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))

    non_null = [r for r in rows if str(r.get('rate_estimate_usd') or '').strip() not in ('', 'None', 'null')]
    signals = sum(int(float(r.get('signals_found') or 0)) for r in rows) if rows else 0
    return {
        'name': name,
        'max_dates': max_dates,
        'only_tag': only_tag,
        'exit_code': proc.returncode,
        'timed_out': timed_out,
        'rows': len(rows),
        'non_null_rate_rows': len(non_null),
        'coverage_pct': round((len(non_null) / len(rows) * 100.0), 2) if rows else 0.0,
        'signals_found_total': signals,
        'stdout_tail': '\n'.join(proc.stdout.splitlines()[-6:]),
        'stderr_tail': '\n'.join(proc.stderr.splitlines()[-6:]),
        'out_csv': str(out_csv),
        'alerts_csv': str(alerts_out),
    }


def main():
    cases = [
        ('7d', 3, ''),
        ('30d', 6, ''),
        ('90d', 8, ''),
        ('winter_pkg', 6, 'winter_weekend_package'),
    ]
    results = [run_case(*c) for c in cases]
    out = {
        'best_practices_applied': [
            'retry_with_backoff',
            'request_throttling',
            'html_response_caching',
            'small-batch first (max_properties=4) for stability',
            'coverage metrics by timeframe',
        ],
        'results': results,
    }
    out_path = DATA / 'rate_scrape_experiment_report.json'
    out_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(json.dumps(out, indent=2))
    print(f"report: {out_path}")


if __name__ == '__main__':
    main()
