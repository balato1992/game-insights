"""One-off: auto-battle genre tags + two reference games."""
import json, re, sys, requests
from pathlib import Path
sys.path.insert(0, "scripts")
import collect

names = ["Auto Battler", "Management", "Physics", "Real Time Tactics", "Sandbox"]
pop = requests.get("https://store.steampowered.com/tagdata/populartags/english", timeout=30).json()
ids = {t["name"]: t["tagid"] for t in pop if t["name"] in names}
print("resolved", ids, file=sys.stderr)
Path("config/tags.json").write_text(json.dumps(ids, indent=2))

# reference games via search term
refs = {}
for term in ["Gladiator Guild Manager", "Totally Accurate Battle Simulator"]:
    r = collect.session.get("https://store.steampowered.com/search/results/",
        params={"term": term, "count": 5, "infinite": 1, "cc": "us", "l": "english", "category1": 998}, timeout=30).json()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r["results_html"], "html.parser")
    out = []
    for a in soup.select("a.search_result_row")[:3]:
        appid = a.get("data-ds-appid")
        tip = a.select_one(".search_review_summary")
        tip = tip.get("data-tooltip-html", "") if tip else ""
        tags = []
        try:
            d = collect.session.get(f"https://store.steampowered.com/app/{appid}/", params={"cc": "us", "l": "english"},
                                    cookies={"birthtime": "0", "mature_content": "1"}, timeout=30).text
            tags = [t.strip() for t in re.findall(r'class="app_tag"[^>]*>\s*([^<]+?)\s*<', d)][:15]
        except Exception as e:
            tags = [f"err {e}"]
        out.append({"appid": appid, "name": a.select_one(".title").get_text(strip=True),
                    "released": a.select_one(".search_released").get_text(strip=True),
                    "reviews_tip": re.sub("<[^>]+>", " ", tip),
                    "price": (a.select_one(".discount_final_price") or a).get_text(strip=True)[:20],
                    "tags": tags})
    refs[term] = out
Path("adhoc/refs.json").write_text(json.dumps(refs, indent=2, ensure_ascii=False))
collect.main()
