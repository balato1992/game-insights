"""Weekly Steam market snapshot.

For each tracked Steam tag, scrape the public store search (sorted by release
date) and record every game in two cohorts:

* matured cohort: released 365-730 days ago, so review counts have had a year
  to accumulate. Used for the "hit rate" (share of games with >= 1,000 reviews,
  roughly 35k copies sold at a ~35 sales/review ratio).
* recent cohort: released in the last 90 days, to see what is gaining traction
  now and how much new supply each tag gets.

Writes data/<date>/games.csv.gz and data/<date>/tag_summary.csv, then
reports/<date>.md comparing against the previous snapshot.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
TAGS_FILE = ROOT / "config" / "tags.json"
SEARCH_URL = "https://store.steampowered.com/search/results/"
PAGE = 100
HIT = 1000
SMALL_WIN = 100

session = requests.Session()
session.headers["User-Agent"] = "game-insights weekly snapshot (github.com/balato1992/game-insights)"


@dataclass
class Game:
    appid: str
    name: str
    released: str  # ISO date
    reviews: int
    positive_pct: int | None
    price_usd: float | None
    tag: str
    cohort: str


def parse_date(text: str) -> date | None:
    text = text.strip()
    for fmt in ("%b %d, %Y", "%d %b, %Y", "%B %d, %Y", "%b %Y", "%B %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def parse_price(text: str) -> float | None:
    if not text:
        return None
    if "free" in text.lower():
        return 0.0
    m = re.findall(r"\$([\d,]+\.?\d*)", text)
    return float(m[-1].replace(",", "")) if m else None


def fetch_page(tag_id: int, start: int) -> tuple[int, list[dict]]:
    params = {
        "query": "", "start": start, "count": PAGE, "tags": tag_id,
        "sort_by": "Released_DESC", "category1": 998, "infinite": 1,
        "cc": "us", "l": "english", "ndl": 1,
    }
    for attempt in range(8):
        time.sleep(1.2)
        try:
            r = session.get(SEARCH_URL, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"  network error {e}; retrying", file=sys.stderr)
            time.sleep(30)
            continue
        if r.status_code == 200:
            try:
                j = r.json()
                break
            except ValueError:
                pass
        wait = 60 * (attempt + 1)
        print(f"  HTTP {r.status_code} at tag {tag_id} start {start}; waiting {wait}s", file=sys.stderr)
        time.sleep(wait)
    else:
        raise RuntimeError(f"gave up on tag {tag_id} start {start}")

    soup = BeautifulSoup(j.get("results_html", ""), "html.parser")
    rows = []
    for a in soup.select("a.search_result_row"):
        summary = a.select_one(".search_review_summary")
        tip = summary.get("data-tooltip-html", "") if summary else ""
        m = re.search(r"of the ([\d,]+) user reviews", tip)
        pos = re.search(r"(\d+)%", tip)
        rel = a.select_one(".search_released")
        price = a.select_one(".discount_final_price")
        title = a.select_one(".title")
        rows.append({
            "appid": a.get("data-ds-appid", ""),
            "name": title.get_text(strip=True) if title else "",
            "date": parse_date(rel.get_text(strip=True)) if rel else None,
            "reviews": int(m.group(1).replace(",", "")) if m else 0,
            "positive_pct": int(pos.group(1)) if pos else None,
            "price": parse_price(price.get_text(strip=True) if price else ""),
        })
    return int(j.get("total_count", 0)), rows


def first_index_before(tag_id: int, total: int, cutoff: date) -> int:
    """Approximate first result index whose release date is < cutoff."""
    a, b = 0, total
    while b - a > PAGE:
        mid = (a + b) // 2
        _, rows = fetch_page(tag_id, mid)
        dates = [r["date"] for r in rows if r["date"]]
        if not dates:
            b = mid
        elif dates[-1] >= cutoff:
            a = mid
        else:
            b = mid
    return a


def collect_window(tag_id: int, total: int, lo: date, hi: date) -> list[dict]:
    """All games released in [lo, hi)."""
    start = first_index_before(tag_id, total, hi)
    out, seen = [], set()
    for _ in range(200):
        _, rows = fetch_page(tag_id, start)
        if not rows:
            break
        for r in rows:
            if r["date"] and lo <= r["date"] < hi and r["appid"] not in seen:
                seen.add(r["appid"])
                out.append(r)
        dates = [r["date"] for r in rows if r["date"]]
        if dates and dates[-1] < lo:
            break
        start += PAGE
    return out


def summarise(games: list[Game]) -> dict:
    n = len(games)
    revs = sorted(g.reviews for g in games)
    if not n:
        return {"releases": 0}
    return {
        "releases": n,
        "median_reviews": int(statistics.median(revs)),
        "p90_reviews": revs[min(n - 1, int(n * 0.9))],
        "pct_ge100": round(100 * sum(r >= SMALL_WIN for r in revs) / n, 1),
        "pct_ge1000": round(100 * sum(r >= HIT for r in revs) / n, 1),
        "pct_under10": round(100 * sum(r < 10 for r in revs) / n, 1),
    }


def main() -> None:
    today = date.today()
    tags: dict[str, int] = json.loads(TAGS_FILE.read_text())
    matured = (today - timedelta(days=730), today - timedelta(days=365))
    recent = (today - timedelta(days=90), today + timedelta(days=1))

    games: list[Game] = []
    for name, tag_id in tags.items():
        print(f"{name} ({tag_id})", file=sys.stderr)
        total, _ = fetch_page(tag_id, 0)
        for cohort, (lo, hi) in (("matured", matured), ("recent", recent)):
            for r in collect_window(tag_id, total, lo, hi):
                games.append(Game(r["appid"], r["name"], r["date"].isoformat(), r["reviews"],
                                  r["positive_pct"], r["price"], name, cohort))
        print(f"  total so far {len(games)}", file=sys.stderr)

    out_dir = ROOT / "data" / today.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_dir / "games.csv.gz", "wt", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(games[0]).keys()))
        w.writeheader()
        w.writerows(asdict(g) for g in games)

    summary_rows = []
    for name in tags:
        for cohort in ("matured", "recent"):
            s = summarise([g for g in games if g.tag == name and g.cohort == cohort])
            summary_rows.append({"tag": name, "cohort": cohort, **s})
    for cohort in ("matured", "recent"):
        uniq = {g.appid: g for g in games if g.cohort == cohort}
        summary_rows.append({"tag": "ALL (unique)", "cohort": cohort, **summarise(list(uniq.values()))})

    fields = ["tag", "cohort", "releases", "median_reviews", "p90_reviews", "pct_ge100", "pct_ge1000", "pct_under10"]
    with open(out_dir / "tag_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, restval="")
        w.writeheader()
        w.writerows(summary_rows)

    meta = {"date": today.isoformat(), "matured_window": [d.isoformat() for d in matured],
            "recent_window": [recent[0].isoformat(), today.isoformat()], "games": len(games)}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
