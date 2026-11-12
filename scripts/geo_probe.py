import re, json, urllib.parse
from common import *
def n(m): print("::notice::" + str(m)[:1800], flush=True)
W = "https://services.ga.gov.au/gis/earthresource/wfs"
try:
    cap = get(W + "?REQUEST=GetCapabilities&SERVICE=WFS&VERSION=2.0.0", as_json=False, timeout=90).decode("utf8", "ignore")
    n("types: " + " ".join(sorted(set(re.findall(r"<(?:wfs:)?Name>([^<]+)</", cap)))))
except Exception as e: n(f"cap fail {e}")
for tn in ["ama:MineralOccurrences", "erl:MineralOccurrenceView", "mo:MinOccView"]:
    try:
        h = get(W + "?" + urllib.parse.urlencode({"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": tn, "resultType": "hits"}), as_json=False, timeout=120).decode("utf8", "ignore")
        n(f"{tn} hits: " + (re.findall(r'numberMatched="(\d+)"', h) or [h[:300]])[0])
        d = get(W + "?" + urllib.parse.urlencode({"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": tn, "count": 2, "outputFormat": "application/json"}), timeout=120)
        n(f"{tn} sample: " + json.dumps(d["features"][0]))
    except Exception as e: n(f"{tn} fail {e}")
F = "https://services.ga.gov.au/gis/rest/services/GA_Surface_Geology/MapServer"
try:
    d = get(F + "?f=json", timeout=60); n("layers: " + "; ".join(f"{l['id']} {l['name']}" for l in d.get("layers", [])))
    i = get(F + "/7?f=json", timeout=60); n("L7 fields: " + ", ".join(f["name"] for f in i.get("fields", [])) + f" maxRec {i.get('maxRecordCount')}")
    c = get(F + "/7/query?where=1%3D1&returnCountOnly=true&f=json", timeout=60); n(f"L7 count {c}")
    s = get(F + "/7/query?where=1%3D1&outFields=*&returnGeometry=false&resultRecordCount=3&f=json", timeout=60); n("L7 sample " + json.dumps([x["attributes"] for x in s.get("features", [])]))
    for fld in ["FEATURETYPE", "TYPE", "NAME"]:
        try:
            g = get(F + "/7/query?" + urllib.parse.urlencode({"where": "1=1", "outFields": fld, "returnGeometry": "false", "groupByFieldsForStatistics": fld, "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "c"}]), "f": "json"}), timeout=60)
            n(f"L7 by {fld}: " + json.dumps([x["attributes"] for x in g.get("features", [])][:40]))
        except Exception as e: n(f"grp {fld} {e}")
except Exception as e: n(f"faults fail {e}")
