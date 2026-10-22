"""Satellite picture of every mine site (data/sites + images/sites/<slug>.jpg).
1. Find the mine on OpenStreetMap near the map coordinate (a named mine/pit first, else the biggest pit nearby).
2. Cut a picture from EOxCloudless 2025 (cloud-free Sentinel-2, 10 m) centred on it.
Licence: EOxCloudless by EOX IT Services GmbH, contains modified Copernicus Sentinel data 2025, CC BY-NC-SA 4.0 (non-commercial)."""
import io, json, math, os, re, sys, time, urllib.parse
from common import get, ROOT, now_iso
from PIL import Image, ImageStat

MINES = json.load(open(os.path.join(os.path.dirname(__file__), "mines.json")))
OUT = os.path.join(ROOT, "images", "sites"); os.makedirs(OUT, exist_ok=True)
IDX = os.path.join(ROOT, "images", "sites.json")
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
STOP = {"mine", "mines", "project", "projects", "gold", "operations", "incl", "and", "the", "north", "south", "east", "west", "hub", "mill", "plant", "lng", "csg", "gas"}

def words(n):
    return [w for w in re.findall(r"[a-z]{4,}", n.lower()) if w not in STOP]

_WD = None
def wikidata():
    """Every mine in Australia that Wikidata has coordinates for (one query)."""
    global _WD
    if _WD is not None:
        return _WD
    q = """SELECT ?l ?c WHERE { ?i wdt:P31/wdt:P279* wd:Q820477; wdt:P17 wd:Q408; wdt:P625 ?c; rdfs:label ?l. FILTER(LANG(?l)="en") }"""
    try:
        r = get("https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q), timeout=90)
        _WD = []
        for x in r["results"]["bindings"]:
            m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", x["c"]["value"])
            if m:
                _WD.append((x["l"]["value"].lower(), float(m.group(2)), float(m.group(1))))
        print("wikidata mines", len(_WD), flush=True)
    except Exception as e:
        print("wikidata failed", e, flush=True); _WD = []
    return _WD

def nominatim(m):
    W = words(m["n"])
    if not W:
        return []
    q = " ".join(W[:2])
    lat, lon = m["lat"], m["lon"]
    url = ("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=10&countrycodes=au&bounded=1"
           f"&viewbox={lon-0.4},{lat+0.3},{lon+0.4},{lat-0.3}&q=" + urllib.parse.quote(q))
    time.sleep(1.1)   # Nominatim fair-use: 1 request a second
    try:
        return get(url, timeout=30, tries=2)
    except Exception as e:
        print("nominatim", m["k"], e, flush=True); return []

def dist(a, b, c, d):
    return math.hypot((a - c) * 111, (b - d) * 111 * math.cos(math.radians(a)))

MINE_KIND = {("landuse", "quarry"), ("industrial", "mine"), ("man_made", "mineshaft"), ("landuse", "industrial"), ("man_made", "adit"), ("historic", "mine")}
def locate(m):
    W = words(m["n"])
    best = None
    for name, lat, lon in wikidata():
        d = dist(lat, lon, m["lat"], m["lon"])
        if d < 30 and W and any(w in name for w in W):
            best = (3 - d / 100, lat, lon, None, "wikidata")
            break
    for r in nominatim(m):
        lat, lon = float(r["lat"]), float(r["lon"]); d = dist(lat, lon, m["lat"], m["lon"])
        kind = (r.get("category") or r.get("class"), r.get("type"))
        if d > 30 or kind not in MINE_KIND:
            continue
        bb = r.get("boundingbox")
        b = {"minlat": float(bb[0]), "maxlat": float(bb[1]), "minlon": float(bb[2]), "maxlon": float(bb[3])} if bb else None
        area = (b["maxlat"] - b["minlat"]) * (b["maxlon"] - b["minlon"]) if b else 0
        score = 2 + min(area * 50, 0.9)
        if best is None or score > best[0]:
            best = (score, lat, lon, b, "osm")
    if not best:
        return None
    return best[1], best[2], best[4], best[3]

def merc(lat, lon):
    x = lon * 20037508.34 / 180
    y = math.log(math.tan((90 + lat) * math.pi / 360)) * 20037508.34 / math.pi
    return x, y

def picture(lat, lon, half_w_km):
    x, y = merc(lat, lon); k = 1 / math.cos(math.radians(lat))   # metres on the map per metre on the ground
    hw = half_w_km * 1000 * k; hh = hw * 9 / 16
    url = ("https://tiles.maps.eox.at/wms?service=WMS&request=GetMap&version=1.1.1&layers=s2cloudless-2025_3857&styles="
           f"&srs=EPSG:3857&bbox={x-hw:.0f},{y-hh:.0f},{x+hw:.0f},{y+hh:.0f}&width=800&height=450&format=image/jpeg")
    im = Image.open(io.BytesIO(get(url, as_json=False, timeout=60))).convert("RGB")
    st = ImageStat.Stat(im)
    if max(st.stddev) < 6:          # blank / all water
        return None
    return im

FIX = json.load(open(os.path.join(os.path.dirname(__file__), "site_fix.json")))
def one(m):
    f = FIX.get(m["k"])
    if f:   # checked by hand: exact spot and picture width
        lat, lon = (m["lat"], m["lon"]) if f.get("use") == "map" else (f["lat"], f["lon"])
        im = picture(lat, lon, f["km"] / 2)
        if im is None:
            return {"ok": False, "why": "blank"}
        im.save(os.path.join(OUT, m["k"] + ".jpg"), quality=80, optimize=True, progressive=True)
        return {"ok": True, "lat": round(lat, 5), "lon": round(lon, 5), "how": "checked", "km": f["km"]}
    coarse = len(str(m["lat"]).split(".")[-1]) <= 1 or len(str(m["lon"]).split(".")[-1]) <= 1
    hit = locate(m) if m["e"] != "oil" else None
    lat, lon, how = (hit[0], hit[1], hit[2]) if hit else (m["lat"], m["lon"], "map")
    half = 2.6
    if hit and hit[3]:
        b = hit[3]
        span = max((b["maxlat"] - b["minlat"]) * 111, (b["maxlon"] - b["minlon"]) * 111 * math.cos(math.radians(lat)))
        half = min(7, max(1.6, span * 0.8))
    if how == "map" and coarse:
        half = 6
    im = picture(lat, lon, half)
    if im is None:
        return {"ok": False, "why": "blank"}
    im.save(os.path.join(OUT, m["k"] + ".jpg"), quality=80, optimize=True, progressive=True)
    return {"ok": True, "lat": round(lat, 5), "lon": round(lon, 5), "how": how, "km": round(half * 2, 1)}

if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor
    idx = {}
    try:
        idx = json.load(open(IDX))
    except Exception:
        pass
    only = set(sys.argv[1:])
    redo = os.environ.get("REDO") == "1"
    todo = ([m for m in MINES if (m["k"] in only) if only] or MINES) if redo else [m for m in MINES if (m["k"] in only) if only] or [m for m in MINES if not (idx.get(m["k"], {}).get("ok") and os.path.exists(os.path.join(OUT, m["k"] + ".jpg")))]
    log = []
    def run(m):
        try:
            return m, one(m)
        except Exception as e:
            return m, {"ok": False, "why": str(e)[:120]}
    with ThreadPoolExecutor(1) as ex:
        for i, (m, r) in enumerate(ex.map(run, todo)):
            idx[m["k"]] = r
            log.append(f'{m["k"]}\t{r.get("how", r.get("why"))}\t{r.get("km", "")}')
            if i % 20 == 0:
                json.dump(idx, open(IDX, "w"), indent=0); print(i, flush=True)
    json.dump(idx, open(IDX, "w"), indent=0)
    open(os.path.join(ROOT, "images", "log.txt"), "w").write(now_iso() + "\n" + "\n".join(log) + "\n")
    print("done", sum(1 for v in idx.values() if v.get("ok")), "of", len(MINES))
