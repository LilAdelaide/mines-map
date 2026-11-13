"""Sharper satellite picture of Australia for the 3D view: EOxCloudless 2025 (Copernicus Sentinel-2, CC BY-NC-SA 4.0),
fetched as plain lon/lat images in 4 quarters (each under 4096 px so phones can use them).
Output: tiles/sat3d_<i><j>.jpg  i = west/east (0/1), j = north/south (0/1)."""
import io, os, urllib.request, urllib.parse
from PIL import Image
LON = [112.0, 133.0, 154.5]; LAT = [-9.0, -27.0, -44.5]; RES = 0.0058   # ~600 m per pixel
def wms(layer, bb, w, h):
    q = urllib.parse.urlencode({"service": "WMS", "request": "GetMap", "version": "1.1.1", "layers": layer, "styles": "", "srs": "EPSG:4326",
                                "bbox": ",".join(f"{v:.5f}" for v in bb), "width": w, "height": h, "format": "image/jpeg"})
    req = urllib.request.Request("https://tiles.maps.eox.at/wms?" + q, headers={"User-Agent": "mines-map (github.com/LilAdelaide/mines-map)"})
    return Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=120).read())).convert("RGB")
LAYER = None
for cand in ("s2cloudless-2025", "s2cloudless-2024", "s2cloudless-2023"):
    try: wms(cand, (115, -32, 116, -31), 64, 64); LAYER = cand; break
    except Exception as e: print("::warning::layer", cand, e)
print("::notice::layer", LAYER)
os.makedirs("tiles", exist_ok=True)
for i in range(2):
    for j in range(2):
        lon0, lon1, lat0, lat1 = LON[i], LON[i + 1], LAT[j], LAT[j + 1]
        W, H = int(round((lon1 - lon0) / RES)), int(round((lat0 - lat1) / RES))
        out = Image.new("RGB", (W, H)); step = 1024
        for y in range(0, H, step):
            for x in range(0, W, step):
                w, h = min(step, W - x), min(step, H - y)
                bb = (lon0 + x * RES, lat0 - (y + h) * RES, lon0 + (x + w) * RES, lat0 - y * RES)
                for a in range(4):
                    try: out.paste(wms(LAYER, bb, w, h), (x, y)); break
                    except Exception as e:
                        if a == 3: print("::warning::piece failed", i, j, x, y, e)
        p = f"tiles/sat3d_{i}{j}.jpg"; out.save(p, quality=80, optimize=True, progressive=True)
        print(f"::notice::{p} {W}x{H} {os.path.getsize(p)//1024} KB")
