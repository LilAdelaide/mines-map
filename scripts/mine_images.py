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

_OSM = None
def osm_all():
    """One Overpass request for every mapped pit / mine feature in Australia (much faster than one per mine)."""
    global _OSM
    if _OSM is not None:
        return _OSM
    q = """[out:json][timeout:600][maxsize:1073741824];
(way["landuse"="quarry"](-44,112,-9,154); relation["landuse"="quarry"](-44,112,-9,154);
 nwr["man_made"="mineshaft"](-44,112,-9,154); nwr["industrial"="mine"](-44,112,-9,154);
 nwr["landuse"="industrial"]["name"~"[Mm]ine|[Gg]old|[Pp]it"](-44,112,-9,154););
out center tags bb;"""
    for url in OVERPASS:
        try:
            _OSM = get(url, as_json=True, timeout=700, tries=2, data=urllib.parse.urlencode({"data": q}).encode())["elements"]
            print("OSM features", len(_OSM), flush=True)
            return _OSM
        except Exception as e:
            print("overpass failed", url, e, flush=True)
    _OSM = []
    return _OSM

def dist(a, b, c, d):
    return math.hypot((a - c) * 111, (b - d) * 111 * math.cos(math.radians(a)))

def locate(m, radius):
    W = words(m["n"])
    best = None
    for e in osm_all():
        c = e.get("center") or ({"lat": e["lat"], "lon": e["lon"]} if "lat" in e else None)
        if not c or dist(c["lat"], c["lon"], m["lat"], m["lon"]) > radius / 1000:
            continue
        tags = e.get("tags", {})
        name = (tags.get("name") or "").lower()
        b = e.get("bounds")
        area = (b["maxlat"] - b["minlat"]) * (b["maxlon"] - b["minlon"]) if b else 0
        if W and any(w in name for w in W):
            score = (2, area)
        elif tags.get("landuse") == "quarry":
            score = (1, area)
        else:
            continue
        if best is None or score > best[0]:
            best = (score, c["lat"], c["lon"], b)
    if not best:
        return None
    (rank, area), lat, lon, b = best
    return lat, lon, ("osm-name" if rank == 2 else "osm-pit"), b

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

def one(m):
    coarse = len(str(m["lat"]).split(".")[-1]) <= 1 or len(str(m["lon"]).split(".")[-1]) <= 1
    hit = None if m["e"] == "oil" else locate(m, 15000 if coarse else 6000)
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
    todo = [m for m in MINES if (m["k"] in only) if only] or [m for m in MINES if not (idx.get(m["k"], {}).get("ok") and os.path.exists(os.path.join(OUT, m["k"] + ".jpg")))]
    osm_all()
    log = []
    def run(m):
        try:
            return m, one(m)
        except Exception as e:
            return m, {"ok": False, "why": str(e)[:120]}
    with ThreadPoolExecutor(6) as ex:
        for i, (m, r) in enumerate(ex.map(run, todo)):
            idx[m["k"]] = r
            log.append(f'{m["k"]}\t{r.get("how", r.get("why"))}\t{r.get("km", "")}')
            if i % 20 == 0:
                json.dump(idx, open(IDX, "w"), indent=0); print(i, flush=True)
    json.dump(idx, open(IDX, "w"), indent=0)
    open(os.path.join(ROOT, "images", "log.txt"), "w").write(now_iso() + "\n" + "\n".join(log) + "\n")
    print("done", sum(1 for v in idx.values() if v.get("ok")), "of", len(MINES))
