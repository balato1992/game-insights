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
    prefs = json.loads((ROOT / "config" / "preferences.json").read_text())
    boost_tags = set(prefs.get("boost_tags", []))
    boost = float(prefs.get("boost", 1.0))
    allm = cur[("ALL (unique)", "matured")]
    avg = num(allm["pct_ge1000"]) or 0

    L: list[str] = []
    L.append(f"# Steam 市場週報 {meta['date']}\n")
    L.append(f"比較基準：{prev_dir.name if prev_dir else '（第一份，沒有上週資料）'}。"
             f"成熟期：{meta['matured_window'][0]} 至 {meta['matured_window'][1]} 上市（已滿一年）；"
             f"近期：{meta['recent_window'][0]} 至 {meta['recent_window'][1]} 上市。\n")
    L.append(f"成熟期共 {allm['releases']} 款不重複遊戲，{allm['pct_ge1000']}% 累積到 1,000 則評論（約 3.5 萬套），"
             f"{allm['pct_under10']}% 不到 10 則。\n")

    avg100 = num(allm["pct_ge100"]) or 1
    L.append("## 〇、推薦排序（偏好類型加分，不過濾）\n")
    L.append(f"基礎分數 = 該類型「≥100 評論」比例 ÷ 全體平均（{avg100}%），1.0 代表和平均一樣。"
             f"你的偏好類型（{', '.join(sorted(boost_tags))}）再乘以 {boost}。"
             "所有類型都列出；分數只是討論起點，樣本小（新作 < 150 款）的標籤會標註。\n")
    L.append("| 排名 | 類型 | 偏好 | ≥100 評論 | 基礎分數 | 最終分數 | 一年新作 | 備註 |")
    L.append("| ---: | --- | --- | ---: | ---: | ---: | ---: | --- |")
    scored = []
    for t in tags:
        r = cur[(t, "matured")]
        base = (num(r.get("pct_ge100")) or 0) / avg100
        final = base * (boost if t in boost_tags else 1.0)
        scored.append((final, base, t, r))
    for i, (final, base, t, r) in enumerate(sorted(scored, key=lambda x: -x[0]), 1):
        note = "樣本小，可能高估" if (num(r.get("releases")) or 0) < 150 else ""
        L.append(f"| {i} | {t} | {'加分' if t in boost_tags else ''} | {r.get('pct_ge100', '')}% | {base:.2f} | {final:.2f} "
                 f"| {r['releases']} | {note} |")
    L.append("")

    L.append("## 一、各類型成功率（成熟期）\n")
    L.append("≥1,000 評論約 3.5 萬套（大成功）；≥100 評論約 3,500 套（接近單人全職的門檻）。★ = ≥1,000 比例是全體平均的 2 倍以上；「加分」= 你的偏好類型。週變化單位為百分點。\n")
    L.append("| 類型 | 新作數 | ≥1,000 評論 | 週變化 | ≥100 評論 | 評論中位數 |")
    L.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    rows = sorted(tags, key=lambda t: -(num(cur[(t, "matured")].get("pct_ge1000")) or 0))
    for t in rows:
        r = cur[(t, "matured")]
        p = prev.get((t, "matured"), {})
        hit = num(r.get("pct_ge1000"))
        star = " ★" if hit is not None and hit >= 2 * avg else ""
        mark = "（加分）" if t in boost_tags else ""
        L.append(f"| {t}{mark}{star} | {r['releases']} | {r.get('pct_ge1000', '')}% | {delta(hit, num(p.get('pct_ge1000')))} "
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
    def tag_cell(ts):
        return ", ".join(f"**{x}**" if x in boost_tags else x for x in sorted(ts))
    for appid, e in top:
        L.append(f"| [{e['name']}](https://store.steampowered.com/app/{appid}/) | {e['released']} | {e['reviews']:,} "
                 f"| {e['pos'] or '—'}% | {e['price'] or '—'} | {tag_cell(e['tags'])} |")
    L.append("")
    L.append("粗體 = 你的偏好類型。上市日是 Steam 顯示的日期：搶先體驗轉正式版（例如 Valheim）會以正式版日期出現，但評論是多年累積的，拆解競品時要留意。\n")

    pref_top = [kv for kv in sorted(recent.items(), key=lambda kv: -kv[1]["reviews"]) if kv[1]["tags"] & boost_tags][:10]
    L.append("### 偏好類型的近期新作\n")
    L.append("| 遊戲 | 上市 | 評論數 | 好評率 | 售價 (USD) | 標籤 |")
    L.append("| --- | --- | ---: | ---: | ---: | --- |")
    for appid, e in pref_top:
        L.append(f"| [{e['name']}](https://store.steampowered.com/app/{appid}/) | {e['released']} | {e['reviews']:,} "
                 f"| {e['pos'] or '—'}% | {e['price'] or '—'} | {tag_cell(e['tags'])} |")
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
