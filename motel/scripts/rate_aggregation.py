#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import re
import statistics
import urllib.parse
import urllib.request
from pathlib import Path

PRICE_RE = re.compile(r"\$\s?(\d{2,4})(?:\.\d{2})?")


def fetch_html(query: str) -> str:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def parse_results(html: str):
    blocks = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)</div>', html, re.S)
    out = []
    for href, title, tail in blocks[:8]:
        clean = re.sub(r"<.*?>", " ", (title + " " + tail))
        clean = re.sub(r"\s+", " ", clean).strip()
        prices = [int(m) for m in PRICE_RE.findall(clean)]
        out.append({"url": href, "snippet": clean[:220], "prices": prices})
    return out


def pick_rate(candidates):
    vals = [p for c in candidates for p in c["prices"] if 40 <= p <= 900]
    if not vals:
        return None
    return int(round(statistics.median(vals)))


def run(config_path: Path, out_csv: Path):
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    rows = []
    for prop in cfg["properties"]:
        per_term = []
        for term in prop.get("search_terms", [prop["name"] + " rates"]):
            try:
                html = fetch_html(term)
                parsed = parse_results(html)
                per_term.extend(parsed)
            except Exception as e:
                per_term.append({"url": "", "snippet": f"ERROR: {e}", "prices": []})
        rate = pick_rate(per_term)
        rows.append({
            "timestamp": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "property": prop["name"],
            "city": prop["city"],
            "estimated_rate_usd": rate if rate is not None else "",
            "signals_found": sum(len(x["prices"]) for x in per_term),
            "top_source": (per_term[0]["url"] if per_term else ""),
        })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows -> {out_csv}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Rate aggregation prototype via targeted web searches")
    ap.add_argument("--config", default=str(Path(__file__).with_name("competitors_bethel.json")))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "competitor_rates_latest.csv"))
    args = ap.parse_args()
    run(Path(args.config), Path(args.out))
