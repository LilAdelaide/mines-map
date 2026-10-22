"""Daily: find newly listed ASX mining / energy companies that fit the map's elements and build their profile
(data/newcos.json). Free sources only: ASX company directory, header, about, announcements; OpenStreetMap Nominatim."""
import re, time, urllib.parse
from common import *

ELEMENTS = [  # element, keywords (checked in name + description + recent headlines)
    ("uranium", r"uranium|yellowcake|u3o8"), ("gold", r"\bgold\b|\bau\b"), ("copper", r"copper|\bcu\b"),
    ("iron", r"iron ore|magnetite|hematite"), ("coal", r"\bcoal\b|coking|metallurgical coal"),
    ("silver", r"\bsilver\b|\bag\b"), ("tungsten", r"tungsten|scheelite|wolfram"),
    ("oil", r"\boil\b|\bgas\b|petroleum|\blng\b|hydrocarbon"), ("diamonds", r"diamond"), ("salt", r"\bsalt\b|potash|sulphate of potash"),
]
MINING = re.compile(r"resources|minerals|mining|metals|gold|uranium|copper|energy|petroleum|exploration|iron|coal|silver", re.I)
FOREIGN = re.compile(r"\b(plc|inc\.?|corp\.?|corporation)\s*$", re.I)
PLACE = re.compile(r"((?:Mt|Mount|Lake|Cape|Port)?\s?[A-Z][a-zA-Z'’]+(?:\s[A-Z][a-zA-Z'’]+){0,2})\s(?:Gold|Copper|Uranium|Iron|Coal|Silver|Tungsten|Project|Prospect|Deposit|Tenement|Mine)\b")
STATES = {"WA": "Western Australia", "NT": "Northern Territory", "SA": "South Australia", "QLD": "Queensland", "NSW": "New South Wales", "VIC": "Victoria", "TAS": "Tasmania"}

def directory():
    out, page = [], 0
    while page < 3:
        d = get(f"https://asx.api.markitdigital.com/asx-research/1.0/companies/directory?page={page}&itemsPerPage=100&order=descending&orderBy=dateListed&includeFilterOptions=false&recentListingsOnly=true&v={bust()}")
        items = d.get("data", {}).get("items", [])
        out += items
        if len(items) < 100: break
        page += 1
    return out

def element_of(text):
    t = text.lower(); best = None
    for e, rx in ELEMENTS:
        n = len(re.findall(rx, t))
        if n and (best is None or n > best[1]): best = (e, n)
    return best[0] if best else None

def geocode(name):
    time.sleep(1.1)
    r = get("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=3&countrycodes=au&addressdetails=1&q=" + urllib.parse.quote(name), timeout=30, tries=2)
    for x in r:
        if (x.get("category") or x.get("class")) in ("place", "natural", "landuse", "boundary", "industrial", "man_made", "historic"):
            st = (x.get("address") or {}).get("state", "")
            code = next((k for k, v in STATES.items() if v == st), None)
            if code:
                return float(x["lat"]), float(x["lon"]), code
    return None

def profile(c, item):
    hdr = asx(c, "header")["data"]; about = asx(c, "about")["data"]
    anns = asx(c, "announcements").get("data", {}).get("items", [])[:25]
    heads = " ".join(a.get("headline", "") for a in anns)
    desc = (about.get("description") or "").strip()
    el = element_of(f"{item.get('displayName','')} {desc} {heads}")
    if not el:
        return None
    places = {}
    for a in anns:
        for p in PLACE.findall(a.get("headline", "")):
            p = p.strip()
            if len(p) > 3 and not re.match(r"(?i)^(the|new|first|quarterly|annual|maiden|high|drilling|major|further|significant|strong)\b", p):
                places[p] = places.get(p, 0) + 1
    loc, proj = None, None
    for p, _ in sorted(places.items(), key=lambda x: -x[1])[:4]:
        try:
            loc = geocode(p)
        except Exception:
            loc = None
        if loc:
            proj = p; break
    name = item.get("displayName", c).title().replace(" Ltd", "").replace(" Limited", "").strip()
    return {"code": c, "name": name, "el": el, "listed": item.get("dateListed"), "desc": desc[:300],
            "site": about.get("websiteUrl") or "", "price": hdr.get("priceLast"), "mcap": hdr.get("marketCap") or 0,
            "directors": [d.get("name") for d in (about.get("directors") or [])][:4],
            "project": proj, "lat": loc[0] if loc else None, "lon": loc[1] if loc else None, "st": loc[2] if loc else None,
            "added": now_iso()[:10]}

if __name__ == "__main__":
    known = set(CODES)
    newcos = load("newcos", {}) or {}
    found = []
    for it in directory():
        c = it.get("symbol", "")
        if not c or c in known or c in newcos: continue
        if it.get("industry") not in ("Materials", "Energy", "Class Pend"): continue
        if not MINING.search(it.get("displayName", "")) or FOREIGN.search(it.get("displayName", "")): continue
        try:
            p = profile(c, it)
        except Exception as e:
            print("skip", c, e); continue
        if p:
            newcos[c] = p; found.append(c)
    save("newcos", newcos)
    open(os.path.join(DATA, "newcos_found.txt"), "w").write("\n".join(found))
    print("new companies added:", found or "none")
