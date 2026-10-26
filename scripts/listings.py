"""Daily: find newly listed ASX mining / energy companies that fit the map's elements and build their profile
(data/newcos.json). Free sources only: ASX company directory, header, about, announcements; OpenStreetMap Nominatim."""
import json, os, re, time, urllib.parse
from common import *

ELEMENTS = [  # element, keywords (checked in name + description + recent headlines)
    ("uranium", r"uranium|yellowcake|u3o8"), ("lithium", r"lithium|spodumene|lepidolite|petalite"), ("gold", r"\bgold\b|\bau\b"), ("copper", r"copper|\bcu\b"),
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

TOWN_TYPES = ("city", "town", "village", "hamlet", "locality", "suburb", "isolated_dwelling")
TOWNS = json.load(open(os.path.join(os.path.dirname(__file__), "towns.json")))
def geocode(name, prefer_state=None):
    """A town/locality in Australia -> (lat, lon, state code). Known mining towns first, then OpenStreetMap."""
    t = TOWNS.get(name) or TOWNS.get(name.replace("Mt ", "Mount "))
    if t:
        return t[0], t[1], t[2]
    time.sleep(1.1)
    r = get("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=6&countrycodes=au&addressdetails=1&q=" + urllib.parse.quote(name), timeout=30, tries=2)
    best = None
    for x in r:
        if (x.get("category") or x.get("class")) not in ("place", "boundary") or (x.get("type") not in TOWN_TYPES and x.get("addresstype") not in TOWN_TYPES):
            continue
        st = (x.get("address") or {}).get("state", "")
        code = next((k for k, v in STATES.items() if v == st), None)
        if not code:
            continue
        cand = (float(x["lat"]), float(x["lon"]), code)
        if prefer_state and code == prefer_state:
            return cand
        best = best or cand
    return best

FILE = "https://cdn-api.markitdigital.com/apiman-gateway/ASX/asx-research/1.0/file/"
DOCS = re.compile(r"prospectus|quarterly|activities|presentation|project|acquisition|exploration update|investor", re.I)
NEAR = re.compile(r"(?:approximately|about|some|around|~)?\s*(\d{1,3})\s?(?:km|kilometres)\s+(north|south|east|west|north[- ]?east|north[- ]?west|south[- ]?east|south[- ]?west|N|S|E|W|NE|NW|SE|SW)(?:erly)?\s+of\s+(?:the\s+)?(?:town(?:ship)?\s+of\s+|regional\s+(?:centre|city)\s+of\s+)?((?:Mt\.?\s|Mount\s|Port\s)?[A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", re.S)
STATE_RX = {k: re.compile(v + "|\\b" + k + "\\b") for k, v in STATES.items()}
ABROAD = re.compile(r"\b(Sweden|Swedish|Finland|Norway|Namibia|Botswana|Tanzania|Ghana|Mali|Zambia|Canada|Canadian|Nevada|Utah|Wyoming|Arizona|USA|United States|Brazil|Peru|Chile|Argentina|Mexico|Saudi|Kazakhstan|Mongolia|Indonesia|Philippines|Papua New Guinea|PNG|Fiji|Africa|Europe|Spain|Portugal|Serbia|Greenland)\b")
DIRV = {"n": (1, 0), "s": (-1, 0), "e": (0, 1), "w": (0, -1)}

def pdf_text(key):
    import io
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(get(FILE + key, as_json=False, timeout=60)))
    return "\n".join((pg.extract_text() or "") for pg in r.pages[:20])

def place_from_text(txt):
    """'located 35 km north-east of Leonora, Western Australia' -> (lat, lon, state, phrase)."""
    oz = sum(len(rx.findall(txt)) for rx in STATE_RX.values()) + txt.count("Australia")
    if len(ABROAD.findall(txt)) > oz:
        return None
    for m in NEAR.finditer(txt):
        km, town = int(m.group(1)), m.group(3).strip()
        d = m.group(2).lower().replace("-", "").replace(" ", "")
        d = d.replace("north", "n").replace("south", "s").replace("east", "e").replace("west", "w")
        if km > 600 or town.lower() in ("the", "perth city"): continue
        ctx = txt[m.end(): m.end() + 60]
        main_st = max(STATES, key=lambda k: len(STATE_RX[k].findall(txt)))
        st = next((k for k, rx in STATE_RX.items() if rx.search(ctx)), None) or main_st
        try:
            g = geocode(town, st)
        except Exception as e:
            print("geocode", town, e, flush=True); g = None
        # only trust it when the town is in the state the document is about
        if not g or len(STATE_RX[g[2]].findall(txt)) < 2: continue
        dy = sum(DIRV[ch][0] for ch in d if ch in DIRV); dx = sum(DIRV[ch][1] for ch in d if ch in DIRV)
        n = (dy * dy + dx * dx) ** 0.5 or 1
        lat = g[0] + dy / n * km / 111; lon = g[1] + dx / n * km / (111 * max(0.3, abs(__import__("math").cos(__import__("math").radians(g[0])))))
        return lat, lon, g[2], f"{km} km {m.group(2)} of {town}"
    return place_fallback(txt)

TOWN = r"((?:Mt\.?\s|Mount\s|Port\s|Lake\s)?[A-Z][a-z]+(?:\s[A-Z][a-z]+)?)"
FROM = re.compile(r"(\d{1,3})\s?(?:km|kilometres)\s+(?:from|of)\s+(?:the\s+)?(?:town(?:ship)?\s+of\s+)?" + TOWN)
NEARTOWN = re.compile(r"(?:near|adjacent to|outskirts of|close to)\s+(?:the\s+)?(?:(?:historic|regional|mining)\s+)?(?:town(?:ship)?|city|community|locality)\s+of\s+" + TOWN)
NEARST = re.compile(r"(?:near|adjacent to|close to)\s+" + TOWN + r",?\s+(?:in\s+)?(?:Western Australia|Queensland|New South Wales|South Australia|Victoria|Tasmania|the Northern Territory|Northern Territory|WA|QLD|NSW|SA|VIC|TAS|NT)\b")
PROJ = re.compile(TOWN + r"\s(?:Gold|Copper|Uranium|Iron Ore|Coal|Silver|Lithium|Tungsten|Polymetallic|Base Metals?)?\s?(?:Project|Prospect|Deposit)\b")
REGION = {  # last resort: the named mining region (approximate)
    "Pilbara": (-21.7, 118.6, "WA"), "Yilgarn": (-30.0, 119.5, "WA"), "Murchison": (-26.9, 117.8, "WA"), "Eastern Goldfields": (-30.0, 121.5, "WA"),
    "Kimberley": (-17.3, 126.5, "WA"), "Gascoyne": (-24.5, 116.0, "WA"), "Paterson": (-21.6, 122.1, "WA"), "Fraser Range": (-32.0, 123.0, "WA"),
    "Mount Isa": (-20.73, 139.49, "QLD"), "Mt Isa": (-20.73, 139.49, "QLD"), "Cloncurry": (-20.7, 140.5, "QLD"), "Georgetown": (-18.29, 143.55, "QLD"),
    "Charters Towers": (-20.08, 146.26, "QLD"), "Bowen Basin": (-22.5, 148.5, "QLD"), "Lachlan Fold Belt": (-33.0, 148.5, "NSW"), "Cobar": (-31.5, 145.84, "NSW"),
    "Broken Hill": (-31.95, 141.45, "NSW"), "New England": (-30.0, 151.5, "NSW"), "Gawler Craton": (-31.0, 135.5, "SA"), "Curnamona": (-31.5, 140.5, "SA"),
    "Cooper Basin": (-27.5, 140.5, "SA"), "Tennant Creek": (-19.65, 134.19, "NT"), "Pine Creek": (-13.82, 131.83, "NT"), "Arunta": (-22.5, 133.5, "NT"),
    "Tanami": (-20.0, 129.7, "NT"), "McArthur Basin": (-16.5, 135.5, "NT"), "Victorian Goldfields": (-36.8, 144.0, "VIC"), "Bendigo": (-36.76, 144.28, "VIC"),
    "Ballarat": (-37.56, 143.85, "VIC"), "Mount Read": (-41.9, 145.6, "TAS"), "Carnarvon Basin": (-22.0, 114.5, "WA"), "Perth Basin": (-29.5, 115.2, "WA"),
    "Canning Basin": (-19.5, 123.5, "WA"), "Leonora": (-28.88, 121.33, "WA"), "Laverton": (-28.63, 122.4, "WA"), "Kalgoorlie": (-30.75, 121.47, "WA"),
    "Meekatharra": (-26.6, 118.5, "WA"), "Cue": (-27.42, 117.9, "WA"), "Southern Cross": (-31.23, 119.33, "WA"), "Norseman": (-32.2, 121.78, "WA"),
}
def _main_state(txt):
    return max(STATES, key=lambda k: len(STATE_RX[k].findall(txt)))
def _town(town, txt):
    if town.split()[0].lower() in ("the", "this", "our", "its", "company", "project", "western", "south", "north", "new"): return None
    st = _main_state(txt)
    try:
        g = geocode(town, st)
    except Exception:
        return None
    return g if g and len(STATE_RX[g[2]].findall(txt)) >= 2 else None
def place_fallback(txt):
    for rx, how in ((FROM, "km"), (NEARTOWN, "near"), (NEARST, "near")):
        for m in rx.finditer(txt):
            town = m.group(2) if how == "km" else m.group(1)
            if how == "km" and int(m.group(1)) > 150: continue
            g = _town(town.strip(), txt)
            if g: return g[0], g[1], g[2], (f"{m.group(1)} km from {town}" if how == "km" else f"near {town}")
    seen = set()
    for m in PROJ.finditer(txt):
        n = m.group(1).strip()
        if n in seen or len(seen) > 6: continue
        seen.add(n)
        t = TOWNS.get(n) or TOWNS.get(n.replace("Mt ", "Mount "))
        if t and len(STATE_RX[t[2]].findall(txt)) >= 2: return t[0], t[1], t[2], f"near {n} (project name)"
    best = None
    for k, v in REGION.items():
        n = txt.count(k)
        if n >= 2 and len(STATE_RX[v[2]].findall(txt)) >= 2 and (not best or n > best[1]): best = (k, n)
    if best:
        v = REGION[best[0]]; return v[0], v[1], v[2], f"{best[0]} region (approximate)"
    return None

def profile(c, item):
    hdr = asx(c, "header")["data"]; about = asx(c, "about")["data"]
    anns = asx(c, "announcements").get("data", {}).get("items", [])[:25]
    heads = " ".join(a.get("headline", "") for a in anns)
    desc = (about.get("description") or "").strip()
    el = element_of(f"{item.get('displayName','')} {desc} {heads}")
    if not el:
        return None
    loc, near, proj = None, None, None
    dbg = {"docs": [], "near": [], "oz": 0, "abroad": 0}
    ND = int(os.environ.get("NDOCS", "4"))
    picks = [a for a in anns if DOCS.search(a.get("headline", "")) and a.get("documentKey")][:ND - 1]
    picks += [a for a in anns if a.get("isPriceSensitive") and a.get("documentKey") and a not in picks][:ND - len(picks)]
    for a in picks:
        try:
            txt = pdf_text(a["documentKey"])
            dbg["docs"].append([a.get("headline", "")[:50], len(txt)])
        except Exception as e:
            dbg["docs"].append([a.get("headline", "")[:50], "ERR " + str(e)[:60]])
            continue
        dbg["near"] += [m.group(0)[:70] for m in NEAR.finditer(txt)][:3]
        dbg["oz"] += sum(len(rx.findall(txt)) for rx in STATE_RX.values()) + txt.count("Australia"); dbg["abroad"] += len(ABROAD.findall(txt))
        el = element_of(f"{item.get('displayName','')} {desc} {heads} {txt[:20000]}") or el
        r = place_from_text(txt)
        if r:
            loc = r[:3]; near = r[3]
            pm = re.search(r"([A-Z][a-zA-Z'’]+(?:\s[A-Z][a-zA-Z'’]+){0,2})\s(?:Gold|Copper|Uranium|Iron Ore|Coal|Silver|Tungsten)?\s?Project", txt)
            proj = pm.group(1).strip() + " Project" if pm else None
            break
    name = item.get("displayName", c).title().replace(" Ltd", "").replace(" Limited", "").strip()
    return {"code": c, "name": name, "el": el, "listed": item.get("dateListed"), "desc": desc[:300],
            "site": about.get("websiteUrl") or "", "price": hdr.get("priceLast"), "mcap": hdr.get("marketCap") or 0,
            "directors": [d.get("name") for d in (about.get("directors") or [])][:4],
            "project": proj, "near": near, "lat": loc[0] if loc else None, "lon": loc[1] if loc else None, "st": loc[2] if loc else None,
            "added": now_iso()[:10], "dbg": dbg}

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
    open(os.path.join(DATA, "newcos_found.txt"), "w").write(" ".join(c for c in found if newcos[c].get("lat") is not None))
    print("new companies added:", found or "none")
