"""Turn the latest data/<date>/ snapshot into reports/<date>.md (Traditional Chinese)."""

from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"


def load_summary(d: Path) -> dict[tuple[str, str], dict]:
    with open(d / "tag_summary.csv", encoding="utf-8") as f:
        return {(r["tag"], r["cohort"]): r for r in csv.DictReader(f)}


def load_games(d: Path) -> list[dict]:
    with gzip.open(d / "games.csv.gz", "rt", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def delta(cur: float | None, prev: float | None, fmt: str = "{:+.1f}") -> str:
    if cur is None or prev is None:
        return "—"
    return fmt.format(cur - prev)


def main() -> None:
    snaps = sorted(p for p in DATA.iterdir() if p.is_dir() and (p / "tag_summary.csv").exists())
    cur_dir = snaps[-1]
    prev_dir = snaps[-2] if len(snaps) > 1 else None
    meta = json.loads((cur_dir / "meta.json").read_text())
    cur = load_summary(cur_dir)
    prev = load_summary(prev_dir) if prev_dir else {}
    games = load_games(cur_dir)

    tags = [t for (t, c) in cur if c == "matured" and not t.startswith("ALL")]
    allm = cur[("ALL (unique)", "matured")]
    avg = num(allm["pct_ge1000"]) or 0

    L: list[str] = []
    L.append(f"# Steam 市場週報 {meta['date']}\n")
    L.append(f"比較基準：{prev_dir.name if prev_dir else '（第一份，沒有上週資料）'}。"
             f"成熟期：{meta['matured_window'][0]} 至 {meta['matured_window'][1]} 上市（已滿一年）；"
             f"近期：{meta['recent_window'][0]} 至 {meta['recent_window'][1]} 上市。\n")
    L.append(f"成熟期共 {allm['releases']} 款不重複遊戲，{allm['pct_ge1000']}% 累積到 1,000 則評論（約 3.5 萬套），"
             f"{allm['pct_under10']}% 不到 10 則。\n")

    L.append("## 一、各類型成功率（成熟期）\n")
    L.append("成功率 = 評論數 ≥ 1,000 的比例。★ = 全體平均的 2 倍以上。週變化單位為百分點。\n")
    L.append("| 類型 | 新作數 | ≥1,000 評論 | 週變化 | ≥100 評論 | 評論中位數 |")
    L.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    rows = sorted(tags, key=lambda t: -(num(cur[(t, "matured")].get("pct_ge1000")) or 0))
    for t in rows:
        r = cur[(t, "matured")]
        p = prev.get((t, "matured"), {})
        hit = num(r.get("pct_ge1000"))
        star = " ★" if hit is not None and hit >= 2 * avg else ""
        L.append(f"| {t}{star} | {r['releases']} | {r.get('pct_ge1000', '')}% | {delta(hit, num(p.get('pct_ge1000')))} "
                 f"| {r.get('pct_ge100', '')}% | {r.get('median_reviews', '')} |")
    L.append("")

    L.append("## 二、近 90 天新作供給\n")
    L.append("| 類型 | 近 90 天新作 | 週變化 | ≥100 評論 |")
    L.append("| --- | ---: | ---: | ---: |")
    for t in sorted(tags, key=lambda t: -(num(cur.get((t, "recent"), {}).get("releases")) or 0)):
        r = cur.get((t, "recent"), {})
        p = prev.get((t, "recent"), {})
        L.append(f"| {t} | {r.get('releases', 0)} | {delta(num(r.get('releases')), num(p.get('releases')), '{:+.0f}')} "
                 f"| {r.get('pct_ge100') or 0}% |")
    L.append("")

    recent = defaultdict(lambda: {"tags": set()})
    for g in games:
        if g["cohort"] == "recent":
            e = recent[g["appid"]]
            e.update(name=g["name"], released=g["released"], reviews=int(g["reviews"]),
                     pos=g["positive_pct"], price=g["price_usd"])
            e["tags"].add(g["tag"])
    top = sorted(recent.items(), key=lambda kv: -kv[1]["reviews"])[:15]
    L.append("## 三、近 90 天評論最多的新作（值得拆解的競品）\n")
    L.append("| 遊戲 | 上市 | 評論數 | 好評率 | 售價 (USD) | 標籤 |")
    L.append("| --- | --- | ---: | ---: | ---: | --- |")
    for appid, e in top:
        L.append(f"| [{e['name']}](https://store.steampowered.com/app/{appid}/) | {e['released']} | {e['reviews']:,} "
                 f"| {e['pos'] or '—'}% | {e['price'] or '—'} | {', '.join(sorted(e['tags']))} |")
    L.append("")

    matured = {g["appid"]: g for g in games if g["cohort"] == "matured"}.values()
    bands = [("免費", 0, 0.01), ("< $5", 0.01, 5), ("$5–10", 5, 10), ("$10–20", 10, 20), ("$20+", 20, 1e9)]
    L.append("## 四、售價與成功率（成熟期）\n")
    L.append("售價為抓取當天價格，可能含折扣；是相關不是因果。\n")
    L.append("| 售價 | 遊戲數 | ≥100 評論 | ≥1,000 評論 |")
    L.append("| --- | ---: | ---: | ---: |")
    for label, lo, hi in bands:
        grp = [g for g in matured if (num(g["price_usd"]) is not None and lo <= num(g["price_usd"]) < hi)]
        if not grp:
            continue
        n = len(grp)
        ge100 = 100 * sum(int(g["reviews"]) >= 100 for g in grp) / n
        ge1k = 100 * sum(int(g["reviews"]) >= 1000 for g in grp) / n
        L.append(f"| {label} | {n} | {ge100:.1f}% | {ge1k:.1f}% |")
    L.append("")
    L.append("---\n資料來源：Steam 商店公開搜尋結果。標籤由玩家貼上，熱門遊戲較容易被貼上小眾標籤，樣本小的標籤成功率會被高估。\n")

    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"{meta['date']}.md"
    out.write_text("\n".join(L), encoding="utf-8")
    (REPORTS / "LATEST.md").write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
