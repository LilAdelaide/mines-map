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
    if "error" in d and not d.get("features"):   # some layers only answer the plain Esri JSON format
        q2 = q.replace("f=geojson", "f=json")
        d2 = get(f"{base}/{layer}/query?{q2}", timeout=60)
        if "features" in d2:
            return [{"properties": f.get("attributes", {}), "geometry": {"type": "Polygon", "coordinates": f["geometry"]["rings"]}} for f in d2["features"] if f.get("geometry", {}).get("rings")]
        tcount("ERR", f"{base.split('/services/')[-1]}/{layer}: {str(d['error'])[:160]}")
    return d.get("features", [])

def wfs(url, typ, bb):
    q = urllib.parse.urlencode({"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": typ, "outputFormat": "application/json",
        "srsName": "EPSG:4326", "bbox": f"{bb[1]},{bb[0]},{bb[3]},{bb[2]},urn:ogc:def:crs:EPSG::4326", "count": 200})
    return get(f"{url}?{q}", timeout=60).get("features", [])

SEEN = {}; TYPES = {}
def tcount(st, t): d = TYPES.setdefault(st, {}); d[t] = d.get(t, 0) + 1
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

# ---- per-state readers: return [(id, type, holder, granted, geometry, cls)] in the box.
# cls "M" = mining/production lease, "E" = exploration (exploration / prospecting / retention licences, permits).
# keys=None: mining leases of any holder (used near the site); keys=[...]: every title held by those names (wider box).
def like(fields, keys):
    return "(" + " OR ".join(f"UPPER({f}) LIKE '%{k}%'" for f in fields for k in keys) + ")"
def held(h, keys): return keys is None or any(k in (h or "").upper() for k in keys)

WA = "https://public-services.slip.wa.gov.au/public/rest/services/SLIP_Public_Services/Industry_and_Mining/MapServer"
WA_M = r"MINING LEASE|GENERAL PURPOSE|AGREEMENT|MINERAL LEASE|^ML|STATE"
WA_E = r"EXPLORATION|PROSPECTING|RETENTION"
def wa(bb, oil, keys=None):
    out = []
    fs = []
    for attempt in range(3):   # the WA server sometimes answers busy requests with an empty list
        fs = esri(WA, 3, bb, like(["holder1", "holder2"], keys) if keys else "1=1", "fmt_tenid,type,tenstatus,holder1,holder2,holdercnt")
        if fs or keys: break
        time.sleep(2 + attempt * 3)
    for f in fs:
        p = f["properties"]; h = p.get("holder1") or ""; t = p.get("type") or ""; tcount("WA", f"{t}/{p.get('tenstatus')}")
        if p.get("tenstatus") != "LIVE": continue
        if re.search(WA_E, t, re.I): cls = "E"
        elif re.search(WA_M, t, re.I) and not re.search(r"MISCELLANEOUS", t, re.I): cls = "M"
        else: continue
        if cls == "E" and not keys: continue
        if (p.get("holdercnt") or 1) > 1 and p.get("holder2"): h += f" + {p['holdercnt'] - 1} other" + ("s" if p["holdercnt"] > 2 else "")
        out.append((p["fmt_tenid"], t.title(), h, "", f["geometry"], cls))
    if not out and not keys: tcount("WAEMPTY", f"{bb[0]+R:.3f},{bb[1]+R:.3f}")
    if oil and not keys:
        for f in esri(WA, 9, bb, "1=1", "title_id,type,status,holder_1,holder_2,issued"):
            p = f["properties"]
            if not re.search(r"production|retention|lease", p.get("type") or "", re.I): continue
            out.append((p["title_id"], p["type"], " + ".join(x for x in (p.get("holder_1"), p.get("holder_2")) if x), dstr(p.get("issued")), f["geometry"], "M"))
    return out

QLD = "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/Economy/MinesPermitsCurrent/MapServer"
QALT = "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/Economy/MineralTenement/MapServer"
def qld(bb, oil, keys=None):
    out = []
    for f in esri(QALT, 0, bb, like(["tenowner"], keys) if keys else "1=1"):
        p = f["properties"]; t = pick(p, "tentype"); tcount("QLD", f"{t}/{pick(p, 'tenstatus')}")
        if not re.search(r"granted", pick(p, "tenstatus"), re.I): continue
        if re.search(r"mining lease", t, re.I): cls = "M"
        elif re.search(r"exploration|development licence", t, re.I): cls = "E"
        else: continue
        if cls == "E" and not keys: continue
        out.append((pick(p, "tenname"), "Mining Lease" if cls == "M" else t[:40], pick(p, "tenowner"), dstr(pick(p, "grantdate")), f["geometry"], cls))
    if oil and not keys:
        for f in esri(QLD, 55, bb):
            p = f["properties"]
            out.append((pick(p, "displayname"), "Petroleum Lease", pick(p, "authorisedholdername"), dstr(p.get("approvedate")), f["geometry"], "M"))
    return out

NSW = "https://mapprod2.environment.nsw.gov.au/arcgis/rest/services/DRG/Mining_Exploration_Titles/MapServer"
NSW_T = {"ML": "Mining Lease", "CL": "Consolidated Mining Lease", "CML": "Consolidated Mining Lease", "MPL": "Mining Purposes Lease", "CCL": "Consolidated Coal Lease", "PPL": "Petroleum Production Lease", "PML": "Petroleum Mining Lease", "EL": "Exploration Licence", "A": "Exploration Authorisation", "AL": "Assessment Lease", "PEL": "Petroleum Exploration Licence"}
def nsw(bb, oil, keys=None):
    out = []
    for layer in ((0, 1, 2) if oil or keys else (0, 1)):
        for f in esri(NSW, layer, bb, like(["COMPANY"], keys) if keys else "1=1"):
            p = f["properties"]; code = pick(p, "TITLE_CODE"); tcount("NSW", code)
            if re.fullmatch(r"ML|CL|MPL|CML|CCL|PPL|PML", code): cls = "M"
            elif re.fullmatch(r"EL|A|AL|PEL", code): cls = "E"
            else: continue
            if cls == "E" and not keys: continue
            out.append((pick(p, "TITLE_REF") or f"{code} {pick(p, 'TITLE_NO')}", NSW_T.get(code, code), pick(p, "COMPANY"), dstr(p.get("GRANT_DATE")), f["geometry"], cls))
    return out

TAS = "https://data.stategrowth.tas.gov.au/ags/rest/services/MRT/TenementsLIST/MapServer"
def tas(bb, oil, keys=None):
    out = []
    for layer, cls in ((44, "M"), (36, "E")):
        if cls == "E" and not keys: continue
        for f in esri(TAS, layer, bb, like(["OWNER"], keys) if keys else "1=1"):
            p = f["properties"]; seen("TAS", p); t = pick(p, "TENEMENTTYPE"); tcount("TAS", t)
            out.append((pick(p, "NAME", "ID"), t or ("Mining Lease" if cls == "M" else "Exploration Licence"), pick(p, "OWNER"), dstr(p.get("GRANTDATE")), f["geometry"], cls))
    return out

VICW = "https://opendata.maps.vic.gov.au/geoserver/wfs"
def vic(bb, oil, keys=None):
    out = []
    for f in wfs(VICW, "open-data-platform:minten", bb):
        p = f["properties"]; seen("VIC", p); t = pick(p, "type"); tcount("VIC", f"{t}/{pick(p, 'active')}")
        if not re.search(r"current|active|granted|^Y", pick(p, "active"), re.I): continue
        if re.search(r"^(MIN|ML|MINP)$", t, re.I): cls = "M"
        elif re.search(r"^(EXP|EL|RL|PL)$", t, re.I): cls = "E"
        else: continue
        h = pick(p, "own_name")
        if (cls == "E" and not keys) or not held(h, keys): continue
        out.append((pick(p, "tno", "tag"), pick(p, "typedesc") or ("Mining Licence" if cls == "M" else "Exploration Licence"), h, dstr(pick(p, "granted", "grant_date", "gdate", "startdate")), f["geometry"], cls))
    return out

SAW = "https://services.sarig.sa.gov.au/vector/mineral_tenements/wfs"
SA_TYPES = []; SA_E = []
def sa(bb, oil, keys=None):
    out = []
    for typ in SA_TYPES + (SA_E if keys else []):
        cls = "E" if typ in SA_E else "M"
        for f in wfs(SAW, typ, bb):
            p = f["properties"]; seen("SA", p)
            tcount("SA", f"{pick(p, 'TENEMENT_TYPE')}/{pick(p, 'TENEMENT_STATUS')}")
            if re.search(r"ceased|expired|surrender|cancel|determined|applic", pick(p, "TENEMENT_STATUS"), re.I): continue
            h = pick(p, "TENEMENT_HOLDERS", "TENEMENT_OPERATORS")
            if not held(h, keys): continue
            ty = {"ML": "Mineral Lease", "SML": "Special Mining Lease", "PM": "Private Mine", "MPL": "Miscellaneous Purposes Licence", "EL": "Exploration Licence"}.get(pick(p, "TENEMENT_TYPE"), pick(p, "TENEMENT_TYPE") or ("Mineral Lease" if cls == "M" else "Exploration Licence"))
            out.append((pick(p, "TENEMENT_LABEL"), ty, h, dstr(pick(p, "REGISTRATION_GRANT_DATE")), f["geometry"], cls))
    return out

NT_SHAPES = []
def nt(bb, oil, keys=None):
    b = box(bb[0], bb[1], bb[2], bb[3]); out = []
    for tid, ty, h, g, geom, cls in NT_SHAPES:
        if (cls == "E" and not keys) or not held(h, keys): continue
        if geom.intersects(b): out.append((tid, ty, h, g, mapping(geom), cls))
    return out

# ---- who owns each site: names to look for in the registers' holder fields
GENERIC = set("""LIMITED LTD PTY NL INC CORP CORPORATION COMPANY CO GROUP HOLDINGS HOLDING RESOURCES RESOURCE MINING MINES MINE MINERALS MINERAL METALS METAL
GOLD IRON COPPER LITHIUM COAL URANIUM SILVER ENERGY EXPLORATION OPERATIONS OPERATION AUSTRALIA AUSTRALIAN THE AND OF PROJECT PROJECTS JV JOINT VENTURE
INTERNATIONAL GLOBAL NEW WEST WESTERN EAST EASTERN NORTH NORTHERN SOUTH SOUTHERN CENTRAL CAPITAL INVESTMENTS VENTURES PARTNERS ASSETS DEVELOPMENT""".split())
ALIAS = {"RIO": ["RIO TINTO", "HAMERSLEY", "ROBE RIVER"], "FMG": ["FORTESCUE", "CHICHESTER", "PILBARA IRON"], "BHP": ["BHP"],
         "NST": ["NORTHERN STAR", "KALGOORLIE CONSOLIDATED", "SARACEN", "KLV"], "NEM": ["NEWMONT", "NEWCREST"], "GFI": ["GOLD FIELDS", "ST IVES GOLD", "AGNEW GOLD", "GRANNY SMITH", "GRUYERE"],
         "EVN": ["EVOLUTION"], "PLS": ["PILBARA MINERALS"], "MIN": ["MINERAL RESOURCES", "POLARIS"], "IGO": ["TALISON", "IGO"], "S32": ["SOUTH32"], "WHC": ["WHITEHAVEN"],
         "YAL": ["YANCOAL"], "GLEN": ["GLENCORE"], "AGG": ["ANGLOGOLD"], "RRL": ["REGIS"], "RMS": ["RAMELIUS"], "GMD": ["GENESIS"], "WDS": ["WOODSIDE"], "STO": ["SANTOS"]}
LEGAL = set("LIMITED LTD PTY NL INC CORP CORPORATION GROUP HOLDINGS HOLDING RESOURCES RESOURCE MINING MINERALS METALS JV JOINT VENTURE PROJECT".split())
def owner_keys(m):
    keys = list(ALIAS.get((m.get("tk") or "").upper(), []))
    for nm in (m.get("ow"), m.get("op")):
        for part in re.split(r"[/,;&()+]|\band\b|\d+%", nm or "", flags=re.I):
            w = [x for x in re.findall(r"[A-Z0-9']+", part.upper()) if x not in LEGAL]
            k = " ".join(w[:3]).replace("'", "")
            if not ((len(k) >= 5 or (len(k) >= 4 and len(w) == 1)) and k not in GENERIC):
                k = " ".join(re.findall(r"[A-Z0-9]+", part.upper())[:3])   # short names: use the full name ("ROX RESOURCES")
                if len(k) < 7 or " " not in k: continue
            if k not in keys: keys.append(k)
    return keys[:5]

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
    try:
        d = get("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/Economy/MineralTenement/MapServer?f=json")
        L = [(l["id"], l["name"]) for l in d.get("layers", [])]
        pass
        log("QLD alt layers:", L[:40], "using", QLD_ALT)
    except Exception as e: log("QLD alt failed:", e)
    try:
        d = get(TAS + "?f=json"); log("TAS layers:", [(l["id"], l["name"]) for l in d.get("layers", [])][:60])
    except Exception as e: log("TAS layers failed:", e)
    # SA: feature type names from the WFS capabilities
    try:
        x = get(f"{SAW}?request=GetCapabilities&service=WFS", as_json=False).decode("utf8", "ignore")
        names = re.findall(r"<(?:wfs:)?Name>([^<]+)</(?:wfs:)?Name>", x)
        SA_TYPES.extend([n for n in ("mineral_tenements:mineral_leases", "mineral_tenements:olympic_dam_sml", "mineral_tenements:private_mines") if n in names])
        SA_E.extend([n for n in names if re.search(r"exploration|retention", n, re.I) and not re.search(r"applic", n, re.I)][:2])
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
            if not re.search(r"GRNT", b, re.I): continue
            r = shapefile.Reader(shp=io.BytesIO(z.read(b + ".shp")), dbf=io.BytesIO(z.read(b + ".dbf")), shx=io.BytesIO(z.read(b + ".shx")))
            flds = [f[0] for f in r.fields[1:]]
            n0 = len(NT_SHAPES)
            for sr in r.iterShapeRecords():
                p = dict(zip(flds, sr.record))
                try: g = shape(sr.shape.__geo_interface__)
                except Exception: continue
                tcount("NT", pick(p, "TI_TYPE_CD"))
                tt = pick(p, "TI_TYPE_CD")
                cls = "M" if tt in ("ML", "MLN", "MLC", "MLS", "MA", "MCC", "MCN", "MCS") else "E" if re.match(r"E", tt) else None
                if not cls: continue
                NT_SHAPES.append((f"{tt} {pick(p, 'TI_NUMBER')}".strip(), {"ML": "Mineral Lease", "MLN": "Mineral Lease", "MA": "Mineral Authority", "MLA": "Mineral Lease", "MLC": "Mineral Lease", "MCN": "Mineral Claim", "MCS": "Mineral Claim", "MCC": "Mineral Claim", "EL": "Exploration Licence", "ELR": "Exploration Licence in Retention", "ERL": "Exploration Retention Licence"}.get(tt, tt or "Mineral Lease"), pick(p, "PTY_NAME"), dstr(pick(p, "DT_GRNT")), g, cls))
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
    WIDE = 0.25   # the owner's own titles: look ~25 km around the site
    def one(m):
        st = state_of(m)
        if not st: return m, st, [], []
        oil = m.get("e") == "oil"
        bb = (m["lon"] - R, m["lat"] - R, m["lon"] + R, m["lat"] + R)
        rows = READ[st](bb, oil)
        if not rows and not m.get("auto"):   # map points can be a few km off the lease: look wider
            W = 0.055; bb = (m["lon"] - W, m["lat"] - W, m["lon"] + W, m["lat"] + W)
            rows = READ[st](bb, oil)
        keys = owner_keys(m); own = []
        if keys:
            own = READ[st]((m["lon"] - WIDE, m["lat"] - WIDE, m["lon"] + WIDE, m["lat"] + WIDE), oil, [k.replace("'", "''") for k in keys])
        return m, st, rows, own
    START = time.time()
    def safe(i):
        for a in range(4):   # state servers drop some requests when busy: try again
            if a and time.time() - START > 80 * 60: break   # time budget: keep the last good copy instead
            try: return one(SITES[i])
            except Exception as e:
                last = e; time.sleep(4 + a * 6)
        raise last if "last" in locals() else RuntimeError("time budget")
    res = pmap(safe, list(range(len(SITES))), workers=4)
    MATCH = {"own": 0, "near": 0, "none": 0}
    for i, r in res.items():
        m, st, rows, own = r
        s = stats.setdefault(st or "?", [0, 0, 0]); s[0] += 1
        pt = Point(m["lon"], m["lat"])
        def dist(geom):
            try: return shape(geom).distance(pt)
            except Exception: return 9
        keys = owner_keys(m)
        # 1. titles registered to the site's owner (mining leases + exploration licences)
        mine_own = [x for x in own if x[5] == "M" and dist(x[4]) < 0.12]
        expl_own = [x for x in own if x[5] == "E"]
        near_own = [x for x in rows if x[5] == "M" and held(x[2], keys)] if keys else []
        if mine_own or near_own:
            keepM = {x[0]: x for x in near_own + mine_own}.values(); MATCH["own"] += 1
        else:
            # 2. owner not found under its own name (subsidiaries etc.): only leases the site sits in or right next to
            scored = sorted(((dist(x[4]), x) for x in rows if x[5] == "M"), key=lambda q: q[0])
            keepM = [x for d, x in scored if d <= 0.008][:12]
            MATCH["near" if keepM else "none"] += 1
        keepE = sorted(expl_own, key=lambda x: dist(x[4]))[:30]
        if keepM or keepE: s[1] += 1
        for tid, ty, h, g, geom, cls in list(keepM)[:25] + keepE:
            key = f"{st}|{tid}"
            if key not in T:
                rings = clean(geom)
                if not rings: continue
                T[key] = {"id": tid, "ty": ty, "h": h[:120], "g": g, "st": st, "c": cls, "r": rings, "s": []}
                s[2] += 1
            if m["k"] not in T[key]["s"]: T[key]["s"].append(m["k"])
    log("owner matched", MATCH)
    print(f"::notice::owner matched {MATCH}; mining {sum(1 for t in T.values() if t['c']=='M')}, exploration {sum(1 for t in T.values() if t['c']=='E')}")
    failed = [i for i in range(len(SITES)) if i not in res]
    # sites whose state server failed this run keep their leases from the last good run
    try:
        old = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "tenements.json")))
        fk = {SITES[i]["k"] for i in failed}
        for t in old.get("t", []):
            ks = [k for k in t.get("s", []) if k in fk]
            if not ks: continue
            key = f"{t.get('st')}|{t['id']}"
            if key not in T: T[key] = dict(t, s=[]); T[key].setdefault("c", "M")
            for k in ks:
                if k not in T[key]["s"]: T[key]["s"].append(k)
        log("kept from last run for", len(fk), "failed sites")
    except Exception as e: log("no previous copy:", e)
    for k, v in sorted(stats.items()): log(f"{k}: {v[0]} sites, {v[1]} with leases found, {v[2]} leases")
    print(f"::notice::tenements: {len(T)} leases for {sum(v[1] for v in stats.values())}/{len(SITES)} sites; " + "; ".join(f"{k} {v[1]}/{v[0]}" for k, v in sorted(stats.items())) + f"; errors {len(failed)}")
    for k, v in TYPES.items(): print(f"::notice::{k} types: " + str(sorted(v.items(), key=lambda x: -x[1])[:25])[:1500])
    for l in LOG:
        if l.startswith(("QLD L43", "QLD alt0")): print("::notice::" + l[:1500])
    if len(T) > 50:
        save("tenements", {"asof": now_iso(), "src": "State government tenement registers (WA DMIRS, QLD DNRMMRRD, NSW MEG, TAS MRT, VIC ERV, SA SARIG, NT STRIKE)", "t": list(T.values())})
