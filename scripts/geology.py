"""Geology layers for the map (free Geoscience Australia services, which compile the state & territory survey databases):
  data/geo/occ_<element>.json   every recorded mineral occurrence / deposit / prospect for that element (points)
  data/geo/occn_<element>.json  names + commodities for those points (loaded only when zoomed in)
  data/geo/hits.json            notable drill intercepts reported by companies (GA 'Exploration results')
  data/geo/faults.json          major faults & thrusts (GA 1:2.5M surface geology)
Runs weekly; the sources change slowly."""
import re, json, os, urllib.parse, collections
from common import *
from shapely.geometry import shape, mapping

W = "https://services.ga.gov.au/gis/earthresource/wfs"
F = "https://services.ga.gov.au/gis/rest/services/GA_Surface_Geology/MapServer/1"
OUT = os.path.join(DATA, "geo"); os.makedirs(OUT, exist_ok=True)
def n(m): print("::notice::" + str(m)[:1900], flush=True)

EL = {   # app element key -> words in the commodity names
    "gold": r"\bgold\b", "silver": r"\bsilver\b", "copper": r"\bcopper\b", "iron": r"\biron\b|hematite|magnetite|goethite",
    "lithium": r"lithium|spodumene|lepidolite|petalite", "coal": r"\bcoal\b|lignite", "uranium": r"uranium",
    "tungsten": r"tungsten|scheelite|wolfram", "salt": r"\bsalt\b|halite|sodium chloride", "diamonds": r"diamond",
    "oil": r"petroleum|\boil\b|natural gas|oil shale"}
ELR = {k: re.compile(v, re.I) for k, v in EL.items()}
def els(names):
    s = names or ""
    return [k for k, r in ELR.items() if r.search(s)]

def wfs(tn, **k):
    q = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": tn, "outputFormat": "application/json"}; q.update(k)
    return get(W + "?" + urllib.parse.urlencode(q), timeout=300, tries=4)

def pages(tn, props, step=25000):
    out, i = [], 0
    while True:
        d = wfs(tn, count=step, startIndex=i, propertyName=props, sortBy="ENO" if "ENO" in props else "")
        fs = d.get("features", [])
        out += fs; i += len(fs)
        if len(fs) < step: break
    return out

def save_json(name, obj):
    p = os.path.join(OUT, name); tmp = p + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, p)

if __name__ == "__main__":
    asof = now_iso()
    # 1. occurrences (state survey data) + deposits
    occ = pages("ama:MineralOccurrences", "ENO,OCCURRENCE_NAME,STATE,COMMODITY_NAMES,OCCURRENCE_LOCATION")
    n(f"occurrences fetched {len(occ)}")
    dep = []
    try: dep = wfs("ama:MineralDeposits", count=10000, propertyName="ENO,DEPOSIT_NAME,STATE,COMMODITY_NAMES,OPERATING_STATUS,COMPANIES,SHAPE").get("features", [])
    except Exception as e:
        try: dep = wfs("ama:MineralDeposits", count=10000).get("features", [])
        except Exception as e2: n(f"deposits failed {e2}")
    n(f"deposits fetched {len(dep)}")
    by = collections.defaultdict(dict)   # el -> (lon,lat) -> [name, commodities, kind]
    def add(lon, lat, name, comm, kind):
        if lon is None or lat is None: return
        if not (105 < lon < 165 and -48 < lat < -8): return
        key = (round(lon, 3), round(lat, 3))
        for e in els(comm):
            cur = by[e].get(key)
            if not cur or kind == "D": by[e][key] = [(name or "").strip()[:48], (comm or "").strip()[:80], kind]
    for f in occ:
        g = f.get("geometry") or {}; p = f.get("properties", {})
        c = g.get("coordinates") if g.get("type") == "Point" else None
        if not c: continue
        add(c[0], c[1], p.get("OCCURRENCE_NAME"), p.get("COMMODITY_NAMES"), "O")
    for f in dep:
        g = f.get("geometry") or {}; p = f.get("properties", {})
        c = g.get("coordinates") if g.get("type") == "Point" else [p.get("LONG_GDA94"), p.get("LAT_GDA94")]
        if not c: continue
        add(c[0], c[1], p.get("DEPOSIT_NAME"), p.get("COMMODITY_NAMES"), "D")
    counts = {}
    for e, pts in by.items():
        items = sorted(pts.items())
        xy = []
        for (lon, lat), _ in items: xy += [int(round(lon * 1000)), int(round(lat * 1000))]
        save_json(f"occ_{e}.json", {"asof": asof, "n": len(items), "xy": xy})
        save_json(f"occn_{e}.json", {"asof": asof, "nm": [v[0] for _, v in items], "c": [v[1] for _, v in items], "k": "".join(v[2] for _, v in items)})
        counts[e] = len(items)
    n("occurrences by element " + json.dumps(counts))
    # 2. drill intercepts reported by companies
    hits = []
    try:
        for f in wfs("ama:ExplorationResults", count=10000).get("features", []):
            p = f.get("properties", {}); g = f.get("geometry") or {}
            c = g.get("coordinates") if g.get("type") == "Point" else [p.get("longitude_dd"), p.get("latitude_dd")]
            if not c or c[0] is None: continue
            es = els(p.get("commodity")) or ["other"]
            hits.append([round(c[0], 4), round(c[1], 4), es, (p.get("deposit") or "").strip()[:60], re.sub(r"\s+", " ", p.get("exploration_results") or "").strip()[:200], p.get("year"), (p.get("company") or "").strip()[:90]])
    except Exception as e: n(f"hits failed {e}")
    if hits: save_json("hits.json", {"asof": asof, "h": hits})
    n(f"drill hits {len(hits)}")
    # 3. major faults
    lines, off = [], 0
    while True:
        d = get(F + "/query?" + urllib.parse.urlencode({"where": "1=1", "outFields": "fltname,typename", "returnGeometry": "true", "outSR": 4326, "resultOffset": off, "resultRecordCount": 2000, "f": "geojson"}), timeout=180, tries=4)
        fs = d.get("features", [])
        for f in fs:
            try:
                g = shape(f["geometry"]).simplify(0.01, preserve_topology=False)
            except Exception: continue
            parts = [g] if g.geom_type == "LineString" else list(getattr(g, "geoms", []))
            nm = (f.get("properties") or {}).get("fltname") or ""
            th = 1 if "thrust" in ((f.get("properties") or {}).get("typename") or "") else 0
            for ln in parts:
                cs = [[round(x, 3), round(y, 3)] for x, y in ln.coords]
                if len(cs) >= 2: lines.append([nm[:40], th, cs])
        off += len(fs)
        if len(fs) < 2000 or not d.get("exceededTransferLimit", len(fs) == 2000): break
    if len(lines) > 500: save_json("faults.json", {"asof": asof, "l": lines})
    n(f"fault lines {len(lines)}; sizes " + ", ".join(f"{x} {os.path.getsize(os.path.join(OUT, x))//1024}KB" for x in sorted(os.listdir(OUT))))
