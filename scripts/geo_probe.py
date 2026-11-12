import re, json, urllib.parse, collections
from common import *
def n(m): print("::notice::" + str(m)[:1900], flush=True)
W = "https://services.ga.gov.au/gis/earthresource/wfs"
def wfs(tn, **k):
    q = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": tn, "outputFormat": "application/json"}; q.update(k)
    return get(W + "?" + urllib.parse.urlencode(q), timeout=180)
for tn in ["ama:ExplorationResults", "ama:MineralDeposits", "ama:MineralOccurrencesDiscoveryAndExploration"]:
    try:
        h = get(W + "?" + urllib.parse.urlencode({"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": tn, "resultType": "hits"}), as_json=False, timeout=120).decode("utf8", "ignore")
        d = wfs(tn, count=2)
        n(f"{tn} hits {(re.findall(r'numberMatched=.(\d+)', h) or ['?'])[0]} sample " + json.dumps(d["features"][0]["properties"]) + " geom " + d["features"][0]["geometry"]["type"])
    except Exception as e: n(f"{tn} fail {e}")
# commodity mix + size of the occurrences set
try:
    d = wfs("ama:MineralOccurrences", count=20000, propertyName="COMMODITY_CODES,STATE,CLASS")
    c = collections.Counter(); cl = collections.Counter()
    for f in d["features"]:
        for x in (f["properties"].get("COMMODITY_CODES") or "").split(","): c[x.strip()] += 1
        cl[f["properties"].get("CLASS")] += 1
    n("codes " + str(c.most_common(45))); n("class " + str(cl.most_common(15)))
except Exception as e: n(f"occ fail {e}")
F = "https://services.ga.gov.au/gis/rest/services/GA_Surface_Geology/MapServer"
for L in (1, 7):
    try:
        c = get(F + f"/{L}/query?where=1%3D1&returnCountOnly=true&f=json", timeout=60)
        g = get(F + f"/{L}/query?" + urllib.parse.urlencode({"where": "1=1", "returnGeometry": "false", "groupByFieldsForStatistics": "typename", "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "objectid", "outStatisticFieldName": "c"}]), "f": "json"}), timeout=60)
        r = get(F + f"/{L}/query?" + urllib.parse.urlencode({"where": "1=1", "returnGeometry": "false", "groupByFieldsForStatistics": "plotrank", "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "objectid", "outStatisticFieldName": "c"}]), "f": "json"}), timeout=60)
        n(f"L{L} {c} types " + json.dumps([x["attributes"] for x in g.get("features", [])]) + " rank " + json.dumps([x["attributes"] for x in r.get("features", [])]))
    except Exception as e: n(f"L{L} fail {e}")
