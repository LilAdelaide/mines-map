"""Bake newly listed companies (data/newcos.json) into the app page: index.base.html -> index.html.
Each company with an Australian project location becomes a company profile + a map site, flagged as auto-added."""
import json, os, re
from common import ROOT, load

BASE = os.path.join(ROOT, "index.base.html"); OUT = os.path.join(ROOT, "index.html")
html = open(BASE, encoding="utf8").read()
dec = json.JSONDecoder()

def grab(marker):
    i = html.index(marker) + len(marker)
    obj, end = dec.raw_decode(html, i)
    return obj, i, end

newcos = {c: p for c, p in (load("newcos", {}) or {}).items() if p.get("lat") is not None}
ALL, a0, a1 = grab(", ALL = ")
COS, c0, c1 = grab(", COS = ")
GOLD, g0, g1 = grab("let GOLD = ")
next_id = 1 + max(m["id"] for ms in ALL.values() for m in ms)
LABEL = {"gold": "gold", "uranium": "uranium", "copper": "copper", "iron": "iron ore", "coal": "coal", "silver": "silver", "tungsten": "tungsten", "oil": "oil & gas", "diamonds": "diamond", "salt": "salt & potash", "lithium": "lithium"}
added = []
for c, p in sorted(newcos.items()):
    if c in COS or p["el"] not in ALL:
        continue
    year = (p.get("listed") or "")[:4]
    COS[c] = {"name": p["name"], "site": p.get("site") or "", "mi": f"https://www.marketindex.com.au/asx/{c.lower()}",
              "mcap": p.get("mcap") or 0, "price": p.get("price"), "h": "flat", "prod": False, "div": 0, "auto": True,
              "why": ("Penny-stock explorer/developer: progress depends on drilling results and funding." if p.get("src") == "penny" else "Newly listed explorer: no production yet; progress depends on drilling results and funding."),
              "bio": (f"{p['name']} is an ASX-listed {LABEL[p['el']]} penny stock (under A$1 when added). " if p.get("src") == "penny" else f"{p['name']} is a newly listed ASX {LABEL[p['el']]} explorer (listed {year}). ")
                     + (f"Its main project{(' (' + p['project'] + ')') if p.get('project') else ''} is about {p['near']}, {p['st']}. " if p.get("near") else "")
                     + (f"In its own words: {p['desc']}" if p.get("desc") else "")
                     + (" Added automatically from its ASX announcements; project location is approximate." if p.get("src") == "penny" else " Added automatically from its ASX listing; details are limited until its first reports."),
              "listed": p.get("listed")}
    if p["el"] == "gold":
        COS[c]["gold"] = True
        GOLD[c] = {"name": p["name"], "mcap": p.get("mcap") or 0, "price": p.get("price")}
    la, lo = p["lat"], p["lon"]
    if "region (approximate)" in (p.get("near") or ""):   # spread region-only placements so they don't stack
        import zlib; h = zlib.crc32(c.encode()); la += ((h % 1000) / 1000 - .5) * .8; lo += (((h // 1000) % 1000) / 1000 - .5) * .8
    site = {"id": next_id, "n": p.get("project") or p["name"], "lat": round(la, 4), "lon": round(lo, 4), "st": p["st"],
            "s": "D", "ow": p["name"], "op": p["name"], "tk": c, "p": 0, "pt": "Exploration", "rs": "Not yet reported",
            "ty": "Exploration", "b": (f"Auto-added ASX penny stock. Location is approximate ({p.get('near') or 'from its announcements'})." if p.get("src") == "penny" else f"Auto-added: {p['name']} listed on the ASX in {year}. Location is approximate ({p.get('near') or 'from its announcements'})."),
            "c": [c], "pc": c, "mk": {}, "auto": True}
    next_id += 1
    ALL[p["el"]].append(site)
    added.append(f"{c} → {site['n']} ({p['st']})")

j = lambda o: json.dumps(o, separators=(",", ":"), ensure_ascii=False)
# replace from the back so earlier offsets stay valid
parts = sorted([(a0, a1, j(ALL)), (c0, c1, j(COS)), (g0, g1, j(GOLD))], key=lambda x: -x[0])
for s, e, txt in parts:
    html = html[:s] + txt + html[e:]
open(OUT, "w", encoding="utf8").write(html)
# mine-picture list: add the new sites so the picture job covers them
mp = os.path.join(ROOT, "scripts", "mines.json"); mines = [m for m in json.load(open(mp)) if not m.get("auto")]
have = {m["k"] for m in mines}
slug = lambda n: re.sub(r"[^a-z0-9]+", "-", n.lower().replace("–", "-")).strip("-")
for ms in ALL.values():
    for m in ms:
        if m.get("auto") and slug(m["n"]) not in have:
            mines.append({"k": slug(m["n"]), "n": m["n"], "lat": m["lat"], "lon": m["lon"], "e": next(k for k, v in ALL.items() if m in v), "s": m["s"], "ty": m["ty"], "auto": True})
json.dump(mines, open(mp, "w"), indent=0, ensure_ascii=False)
print("auto-added on the map:", added or "none")
