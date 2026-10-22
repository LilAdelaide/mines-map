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
        km, d, town = int(m.group(1)), m.group(2).lower().replace("-", "").replace(" ", ""), m.group(3).strip()
        if km > 300 or town.lower() in ("the", "perth city"): continue
        ctx = txt[m.end(): m.end() + 60]
        st = next((k for k, rx in STATE_RX.items() if rx.search(ctx)), None) or max(STATES, key=lambda k: len(STATE_RX[k].findall(txt)))
        try:
            g = geocode(f"{town}, {STATES[st]}")
        except Exception:
            g = None
        if not g: continue
        dy = sum(DIRV[ch][0] for ch in d if ch in DIRV); dx = sum(DIRV[ch][1] for ch in d if ch in DIRV)
        n = (dy * dy + dx * dx) ** 0.5 or 1
        lat = g[0] + dy / n * km / 111; lon = g[1] + dx / n * km / (111 * max(0.3, abs(__import__("math").cos(__import__("math").radians(g[0])))))
        return lat, lon, g[2], f"{km} km {m.group(2)} of {town}"
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
    for a in [a for a in anns if DOCS.search(a.get("headline", "")) and a.get("documentKey")][:3]:
        try:
            txt = pdf_text(a["documentKey"])
        except Exception:
            continue
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
    open(os.path.join(DATA, "newcos_found.txt"), "w").write(" ".join(c for c in found if newcos[c].get("lat") is not None))
    print("new companies added:", found or "none")
