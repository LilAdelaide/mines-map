import sys, json, urllib.parse
from common import *
from shapely.geometry import shape
WA = "https://public-services.slip.wa.gov.au/public/rest/services/SLIP_Public_Services/Industry_and_Mining/MapServer/3/query?"
for kw in ["FENIX", "IRON RIDGE", "VALIANT"]:
    q = urllib.parse.urlencode({"where": f"UPPER(holder1) LIKE '%{kw}%' AND tenstatus='LIVE'", "outFields": "fmt_tenid,type,holder1", "returnGeometry": "true", "outSR": 4326, "f": "geojson", "resultRecordCount": 60})
    d = get(WA + q, timeout=90)
    rows = []
    for f in d.get("features", []):
        c = shape(f["geometry"]).centroid; p = f["properties"]
        rows.append(f"{p['fmt_tenid']} {p['type'][:12]} {p['holder1'][:28]} {c.y:.3f},{c.x:.3f}")
    print(f"::notice::{kw} {len(rows)}: " + " | ".join(rows)[:1800])
