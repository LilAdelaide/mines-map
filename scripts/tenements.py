"""Mine properties: the registered production leases (mining leases; petroleum production licences for oil & gas)
that cover or touch each mine site on the map, with their outlines and registered holders.
Free state government sources only:
  WA  DMIRS-003 Mining Tenements / DMIRS-011 Petroleum Titles (SLIP public ArcGIS)
  QLD Mines permits current (QSpatial ArcGIS)        NSW Mining & exploration titles (DRG ArcGIS)
  TAS MRT current licences (ArcGIS)                  VIC MINTEN (Vicmap open data WFS)
  SA  SARIG mineral tenements (WFS)                  NT  STRIKE mineral titles (shapefile download)
Writes data/tenements.json. Runs weekly (leases change slowly)."""
import re, io, sys, zipfile, urllib.parse
from common import *
from shapely.geometry import shape, mapping, box, Point
from shapely.ops import unary_union

SITES = json.load(open(os.path.join(os.path.dirname(__file__), "mines.json")))
R = 0.02          # search box half-size in degrees (~2 km): leases that cover or touch the site
SIMP = 0.0004     # outline simplification (~40 m)
LOG = []
def log(*a):
    m = " ".join(str(x) for x in a); LOG.append(m); print(m, flush=True)

def esri(base, layer, bb, where="1=1", fields="*"):
    q = urllib.parse.urlencode({"geometry": ",".join(f"{v:.5f}" for v in bb), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "where": where, "outFields": fields, "returnGeometry": "true", "outSR": 4326, "f": "geojson"})
    d = get(f"{base}/{layer}/query?{q}", timeout=60)
    return d.get("features", [])

def wfs(url, typ, bb):
    q = urllib.parse.urlencode({"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": typ, "outputFormat": "application/json",
        "srsName": "EPSG:4326", "bbox": f"{bb[1]},{bb[0]},{bb[3]},{bb[2]},urn:ogc:def:crs:EPSG::4326", "count": 200})
    return get(f"{url}?{q}", timeout=60).get("features", [])

SEEN = {}
def seen(st, p):
    if st not in SEEN: SEEN[st] = list(p.items())[:18]; log(st, "fields:", SEEN[st])
def pick(p, *keys):
    for k in keys:
        for kk in (k, k.upper(), k.lower()):
            if p.get(kk) not in (None, "", " "): return str(p[kk]).strip()
    return ""

def dstr(v):
    if v in (None, ""): return ""
    if isinstance(v, (int, float)) and v > 1e10: return datetime.fromtimestamp(v / 1000, timezone.utc).date().isoformat()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v)); return m.group(1) if m else str(v)[:10]

# ---- per-state readers: return [(id, type, holder, granted, geometry)] for production leases in the box
WA = "https://public-services.slip.wa.gov.au/public/rest/services/SLIP_Public_Services/Industry_and_Mining/MapServer"
def wa(bb, oil):
    out = []
    for f in esri(WA, 3, bb, "tenstatus='LIVE' AND type IN ('MINING LEASE','GENERAL PURPOSE LEASE')", "fmt_tenid,type,holder1,holder2,holdercnt"):
        p = f["properties"]; h = p.get("holder1") or ""
        if (p.get("holdercnt") or 1) > 1 and p.get("holder2"): h += f" + {p['holdercnt'] - 1} other" + ("s" if p["holdercnt"] > 2 else "")
        out.append((p["fmt_tenid"], p["type"].title(), h, "", f["geometry"]))
    if oil:
        for f in esri(WA, 9, bb, "1=1", "title_id,type,status,holder_1,holder_2,issued"):
            p = f["properties"]
            if not re.search(r"production|retention|lease", p.get("type") or "", re.I): continue
            out.append((p["title_id"], p["type"], " + ".join(x for x in (p.get("holder_1"), p.get("holder_2")) if x), dstr(p.get("issued")), f["geometry"]))
    return out

QLD = "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/Economy/MinesPermitsCurrent/MapServer"
def qld(bb, oil):
    out = []
    for layer, ty in ((43, "Mining Lease"), (55, "Petroleum Lease")) if oil else ((43, "Mining Lease"),):
        for f in esri(QLD, layer, bb):
            p = f["properties"]; seen("QLD", p)
            out.append((pick(p, "displayname", "permitname", "permit_number", "permitid") or ty, ty, pick(p, "authorisedholdername", "holdername", "permitholder", "holder"),
                        dstr(pick(p, "approvedate", "grantdate", "permitstartdate")), f["geometry"]))
    return out

NSW = "https://mapprod2.environment.nsw.gov.au/arcgis/rest/services/DRG/Mining_Exploration_Titles/MapServer"
def nsw(bb, oil):
    out = []
    for layer in ((0, 1, 2) if oil else (0, 1)):
        for f in esri(NSW, layer, bb):
            p = f["properties"]; code = pick(p, "TITLE_CODE")
            if not re.fullmatch(r"ML|CL|MPL|CML|CCL|PPL|PML|ML\(A\)", code): continue
            out.append((pick(p, "TITLE_REF") or f"{code} {pick(p, 'TITLE_NO')}", {"ML": "Mining Lease", "CL": "Consolidated Mining Lease", "CML": "Consolidated Mining Lease", "MPL": "Mining Purposes Lease", "CCL": "Consolidated Coal Lease", "PPL": "Petroleum Production Lease", "PML": "Petroleum Mining Lease"}.get(code, code),
                        pick(p, "COMPANY"), dstr(p.get("GRANT_DATE")), f["geometry"]))
    return out

TAS = "https://data.stategrowth.tas.gov.au/ags/rest/services/MRT/TenementsLIST/MapServer"
def tas(bb, oil):
    out = []
    for f in esri(TAS, 36, bb):
        p = f["properties"]; seen("TAS", p); t = pick(p, "TENEMENTTYPE")
        if not re.search(r"^ML|mining lease|^M$|^1M|^2M|^3M|^4M", t, re.I) and not re.search(r"mining", pick(p, "CATEGORY"), re.I): continue
        out.append((pick(p, "NAME", "ID"), t or "Mining Lease", pick(p, "OWNER"), dstr(p.get("GRANTDATE")), f["geometry"]))
    return out

VICW = "https://opendata.maps.vic.gov.au/geoserver/wfs"
def vic(bb, oil):
    out = []
    for f in wfs(VICW, "open-data-platform:minten", bb):
        p = f["properties"]; seen("VIC", p); t = pick(p, "tentype", "tenement_type", "type", "tntype")
        if t and not re.search(r"^MIN|mining licen|^ML", t, re.I): continue
        out.append((pick(p, "tenement", "tno", "tenement_no", "tenid", "id") , "Mining Licence", pick(p, "holder", "owner", "applicant", "company", "hname"), dstr(pick(p, "granted", "grant_date", "gdate")), f["geometry"]))
    return out

SAW = "https://services.sarig.sa.gov.au/vector/mineral_tenements/wfs"
SA_TYPES = []
def sa(bb, oil):
    out = []
    for typ in SA_TYPES:
        for f in wfs(SAW, typ, bb):
            p = f["properties"]; seen("SA", p)
            out.append((pick(p, "tenement_label", "tenement", "tenno", "name", "id"), pick(p, "tenement_type", "type") or "Mining Lease", pick(p, "holder", "holders", "owner", "company", "tenement_holder"), dstr(pick(p, "grant_date", "granted", "start_date")), f["geometry"]))
    return out

NT_SHAPES = []
def nt(bb, oil):
    b = box(bb[0], bb[1], bb[2], bb[3]); out = []
    for tid, ty, h, g, geom in NT_SHAPES:
        if geom.intersects(b): out.append((tid, ty, h, g, mapping(geom)))
    return out

READ = {"WA": wa, "QLD": qld, "NSW": nsw, "TAS": tas, "VIC": vic, "SA": sa, "NT": nt}
STATE_BOX = {"WA": (112, -36, 129, -13), "NT": (129, -26, 138, -10.5), "SA": (129, -38.2, 141, -26), "QLD": (138, -29.2, 154, -9),
             "NSW": (141, -37.6, 154, -28.1), "VIC": (140.9, -39.2, 150.1, -33.9), "TAS": (143.5, -43.8, 148.6, -39.5)}
def state_of(m):
    st = (m.get("st") or "").upper()
    if st in READ: return st
    for k, (x0, y0, x1, y1) in STATE_BOX.items():
        if x0 <= m["lon"] <= x1 and y0 <= m["lat"] <= y1: return k
    return None

def setup():
    # SA: feature type names from the WFS capabilities
    try:
        x = get(f"{SAW}?request=GetCapabilities&service=WFS", as_json=False).decode("utf8", "ignore")
        names = re.findall(r"<(?:wfs:)?Name>([^<]+)</(?:wfs:)?Name>", x)
        SA_TYPES.extend([n for n in names if re.search(r"mining|lease|production|ml", n, re.I) and not re.search(r"appl|explor|retention|misc", n, re.I)][:3] or [n for n in names if re.search(r"tenement", n, re.I)][:1])
        log("SA types:", SA_TYPES, "of", names[:20])
    except Exception as e:
        log("SA setup failed:", e)
    # NT: granted mineral leases from the STRIKE shapefile
    try:
        import shapefile
        z = zipfile.ZipFile(io.BytesIO(get("https://geoscience.nt.gov.au/contents/prod/Downloads/NT_MineralTitles_shp.zip", as_json=False, timeout=180)))
        bases = sorted({n.rsplit(".", 1)[0] for n in z.namelist() if n.lower().endswith(".shp")})
        log("NT layers:", bases)
        for b in bases:
            if not re.search(r"_(ML|MLN|MLS|MLA|MLC|MCN|MCS|MCC|MA)_?GRNT|MIN_TITLE_M[LC]\w*_GRNT", b, re.I): continue
            r = shapefile.Reader(shp=io.BytesIO(z.read(b + ".shp")), dbf=io.BytesIO(z.read(b + ".dbf")), shx=io.BytesIO(z.read(b + ".shx")))
            flds = [f[0] for f in r.fields[1:]]
            n0 = len(NT_SHAPES)
            for sr in r.iterShapeRecords():
                p = dict(zip(flds, sr.record))
                try: g = shape(sr.shape.__geo_interface__)
                except Exception: continue
                NT_SHAPES.append((pick(p, "TITLE", "TITLEID", "TITLE_ID", "NAME"), pick(p, "TITLETYPE", "TYPE") or "Mineral Lease", pick(p, "HOLDER", "HOLDERS", "OWNER", "HOLDER1"), dstr(pick(p, "GRANTDATE", "GRANTED", "DATE_GRANT")), g))
            log("NT", b, "fields", flds[:16], "kept", len(NT_SHAPES) - n0)
    except Exception as e:
        log("NT setup failed:", e)

def clean(geom):
    try:
        g = shape(geom)
        if not g.is_valid: g = g.buffer(0)
        g = g.simplify(SIMP, preserve_topology=True)
        if g.is_empty or g.area <= 0: return None
        polys = [g] if g.geom_type == "Polygon" else [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"]
        return [[[round(x, 4), round(y, 4)] for x, y in p.exterior.coords] for p in polys if p.area > 1e-8]
    except Exception:
        return None

if __name__ == "__main__":
    setup()
    T = {}           # tenement id -> record
    stats = {}
    def one(m):
        st = state_of(m)
        if not st: return m, st, []
        bb = (m["lon"] - R, m["lat"] - R, m["lon"] + R, m["lat"] + R)
        return m, st, READ[st](bb, m.get("e") == "oil")
    res = pmap(lambda i: one(SITES[i]), list(range(len(SITES))), workers=6)
    for i, r in res.items():
        m, st, rows = r
        s = stats.setdefault(st or "?", [0, 0, 0]); s[0] += 1
        if rows: s[1] += 1
        pt = Point(m["lon"], m["lat"])
        # keep the leases that contain the site, else the nearest few touching the search box
        scored = []
        for tid, ty, h, g, geom in rows:
            try: d = shape(geom).distance(pt)
            except Exception: d = 9
            scored.append((d, tid, ty, h, g, geom))
        scored.sort(key=lambda x: x[0])
        keep = [x for x in scored if x[0] < 0.012][:25]
        for d, tid, ty, h, g, geom in keep:
            key = f"{st}|{tid}"
            if key not in T:
                rings = clean(geom)
                if not rings: continue
                T[key] = {"id": tid, "ty": ty, "h": h[:120], "g": g, "st": st, "r": rings, "s": []}
                s[2] += 1
            if m["k"] not in T[key]["s"]: T[key]["s"].append(m["k"])
    failed = [i for i in range(len(SITES)) if i not in res]
    for k, v in sorted(stats.items()): log(f"{k}: {v[0]} sites, {v[1]} with leases found, {v[2]} leases")
    print(f"::notice::tenements: {len(T)} leases for {sum(v[1] for v in stats.values())}/{len(SITES)} sites; " + "; ".join(f"{k} {v[1]}/{v[0]}" for k, v in sorted(stats.items())) + f"; errors {len(failed)}")
    for l in LOG:
        if l.startswith(("SA", "NT", "QLD", "VIC", "TAS")): print("::notice::" + l[:1500])
    if len(T) > 50:
        save("tenements", {"asof": now_iso(), "src": "State government tenement registers (WA DMIRS, QLD DNRMMRRD, NSW MEG, TAS MRT, VIC ERV, SA SARIG, NT STRIKE)", "t": list(T.values())})
