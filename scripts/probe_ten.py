import urllib.request, json, re
H={"User-Agent":"Mozilla/5.0 (MinesMap; github actions)"}
def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=40).read())
ROOTS={
  "QLD":"https://spatial-gis.information.qld.gov.au/arcgis/rest/services/Economy/MinesPermitsCurrent/MapServer",
 "NSW1":"https://spatial.industry.nsw.gov.au/arcgis/rest/services/Minerals/CurrentTitles/MapServer",
 "NSW2":"https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/NSW_Current_Mining_and_Exploration_Titles/FeatureServer",
 "NSW3":"https://mapprod2.environment.nsw.gov.au/arcgis/rest/services/DRG/Mining_Exploration_Titles/MapServer",
 "SA":"https://lsa4.geohub.sa.gov.au/server/rest/services/LSA/LocationSAViewerV34/MapServer",
 "TAS":"https://data.stategrowth.tas.gov.au/ags/rest/services/MRT/TenementsLIST/MapServer",
 "NT1":"https://geoscience.nt.gov.au/arcgis/rest/services",
 "NT2":"https://ntlis.nt.gov.au/arcgis/rest/services",
}
for k,u in ROOTS.items():
    try:
        d=get(u+"/layers?f=json") if not k.startswith("NT") else get(u+"?f=json")
        if k.startswith("NT"):
            print(f"::notice::{k} services {[s['name'] for s in d.get('services',[])][:40]} folders {d.get('folders')}"); continue
        Ls=[l for l in d.get("layers",[]) if re.search(r"ten|lease|title|mining|licen", l.get("name",""), re.I)]
        if k=="SA": Ls=[l for l in Ls if re.search(r"ten|lease|licen", l["name"], re.I)]
        print(f"::notice::{k} " + " || ".join(f"[{l['id']}] {l['name']} {[x['name'] for x in (l.get('fields') or [])][:14]}" for l in Ls[:6])[:1900])
        if not Ls: print(f"::notice::{k} OK but no matching layers; names={[l.get('name') for l in d.get('layers',[])][:30]}")
    except Exception as e:
        print(f"::notice::{k} FAIL {str(e)[:150]}")
