import urllib.request, json, re, io, zipfile
H={"User-Agent":"Mozilla/5.0 (MinesMap; github actions)"}
def raw(u, t=60): return urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=t).read()
def get(u): return json.loads(raw(u))
def say(k, m): print(f"::notice::{k} {m}"[:1950])
# QLD layer list + mining lease fields
try:
    d=get("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/Economy/MinesPermitsCurrent/MapServer?f=json")
    L=[(l['id'],l['name']) for l in d.get('layers',[])]
    ml=[i for i,n in L if re.fullmatch(r"mining lease", n, re.I)] or [i for i,n in L if re.search("mining lease",n,re.I)]
    f=get(f"https://spatial-gis.information.qld.gov.au/arcgis/rest/services/Economy/MinesPermitsCurrent/MapServer/{ml[0]}?f=json")
    say("QLD", f"layers={L[:70]} || ML {ml[0]} fields={[x['name'] for x in f.get('fields') or []]}")
except Exception as e: say("QLD", "FAIL "+str(e)[:200])
# WA sample query near Kalgoorlie Super Pit
try:
    q="https://public-services.slip.wa.gov.au/public/rest/services/SLIP_Public_Services/Industry_and_Mining/MapServer/3/query?"+urllib.parse.urlencode({"geometry":"121.49,-30.79,121.53,-30.76","geometryType":"esriGeometryEnvelope","inSR":4326,"spatialRel":"esriSpatialRelIntersects","outFields":"fmt_tenid,type,tenstatus,holder1,holdercnt","returnGeometry":"true","outSR":4326,"maxAllowableOffset":0.0005,"f":"json"})
    d=get(q); fs=d.get("features",[])
    say("WAq", f"{len(fs)} features; types={sorted(set(x['attributes']['type'] for x in fs))}; sample={[ (x['attributes']['fmt_tenid'],x['attributes']['holder1'],x['attributes']['tenstatus']) for x in fs[:6]]}; ringpts={sum(len(r) for x in fs for r in x['geometry']['rings'])}")
except Exception as e: say("WAq", "FAIL "+str(e)[:200])
# VIC WFS capabilities
try:
    x=raw("https://opendata.maps.vic.gov.au/geoserver/wfs?request=GetCapabilities&service=WFS").decode("utf8","ignore")
    names=re.findall(r"<Name>([^<]*(?:minten|tenem|mining|mineral)[^<]*)</Name>", x, re.I)
    say("VIC", f"types={names[:20]}")
except Exception as e: say("VIC", "FAIL "+str(e)[:200])
# NT shapefile zip
try:
    b=raw("https://geoscience.nt.gov.au/contents/prod/Downloads/NT_MineralTitles_shp.zip", 120)
    z=zipfile.ZipFile(io.BytesIO(b)); say("NT", f"{len(b)//1024} KB files={z.namelist()[:30]}")
except Exception as e: say("NT", "FAIL "+str(e)[:200])
# SA: retry geohub + sarig
for k,u in {"SA1":"https://lsa4.geohub.sa.gov.au/server/rest/services/LSA/LocationSAViewerV34/MapServer/70?f=json",
            "SA2":"https://pid.sarig.sa.gov.au/service/mesac795",
            "SA3":"https://services.sarig.sa.gov.au/vector/mineral_tenements/wfs?request=GetCapabilities&service=WFS"}.items():
    try:
        b=raw(u).decode("utf8","ignore"); say(k, f"OK {len(b)} {re.sub(r'\s+',' ',b)[:600]}")
    except Exception as e: say(k, "FAIL "+str(e)[:150])
