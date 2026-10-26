"""Find every ASX mining / energy penny stock (under A$1) with an Australian project in one of the map's elements,
and add it to data/newcos.json (merge_new.py then puts it on the map). Free sources: ASX directory/header/about/
announcements, OpenStreetMap Nominatim. Resumable: progress is saved as it goes."""
import threading, sys
from common import *
import listings as L

_lock = threading.Lock(); _geo = L.geocode
def geocode_one_at_a_time(name, st=None):   # Nominatim allows 1 request a second
    with _lock:
        return _geo(name, st)
L.geocode = geocode_one_at_a_time

def directory_all():
    out, page = [], 0
    while page < 40:
        d = get(f"https://asx.api.markitdigital.com/asx-research/1.0/companies/directory?page={page}&itemsPerPage=100&order=ascending&orderBy=companyName&includeFilterOptions=false&recentListingsOnly=false&v={bust()}")
        items = d.get("data", {}).get("items", [])
        out += items
        if len(items) < 100: break
        page += 1
    return out

if __name__ == "__main__":
    MAX = float(os.environ.get("MAXPX", "1"))
    newcos = load("newcos", {}) or {}
    tried = load("pennies_tried", {}) or {}
    redo = os.environ.get("REDO", "")
    if redo:
        tried = {k: v for k, v in tried.items() if v != redo}
    known = set(CODES) | set(newcos)
    dirx = directory_all()
    cand = [it for it in dirx if it.get("symbol") and it["symbol"] not in known and it["symbol"] not in tried
            and it.get("industry") in ("Materials", "Energy") and not L.FOREIGN.search(it.get("displayName", ""))]
    print(f"::notice::directory {len(dirx)} companies, {len(cand)} Materials/Energy to check")
    def price(it):
        p = asx(it["symbol"], "header")["data"].get("priceLast")
        return float(p) if p else None
    px = pmap(lambda i: price(cand[i]), list(range(len(cand))), workers=10)
    pen = [cand[i] for i, p in px.items() if 0 < p < MAX]
    for i, p in px.items():
        if p >= MAX: tried[cand[i]["symbol"]] = "over"
    print(f"::notice::{len(pen)} under A${MAX:g}")
    added, foreign, noel = [], 0, 0
    def one(i):
        it = pen[i]
        try:
            return L.profile(it["symbol"], it) or "noel"
        except Exception as e:
            return "err"
    done = 0
    for start in range(0, len(pen), 30):
        chunk = list(range(start, min(len(pen), start + 30)))
        res = pmap(one, chunk, workers=6)
        for i in chunk:
            c, r = pen[i]["symbol"], res.get(i, "err")
            if isinstance(r, dict):
                r["src"] = "penny"; r.pop("dbg", None)
                if r.get("lat") is not None:
                    newcos[c] = r; added.append(c); tried[c] = "added"
                else:
                    tried[c] = "no-oz-location"; foreign += 1
            elif r == "noel":
                tried[c] = "not-our-elements"; noel += 1
            # errors are retried next run
        save("newcos", newcos); save("pennies_tried", tried)
        done += len(chunk); print(f"progress {done}/{len(pen)} added {len(added)}", flush=True)
    open(os.path.join(DATA, "newcos_found.txt"), "w").write(" ".join(added))
    print(f"::notice::added {len(added)} penny stocks; {foreign} had no Australian project location; {noel} not in the map's elements")
