"""Australia elevation grid for the 3D Topo view.
Source: AWS Terrain Tiles (Mapzen 'terrarium' encoding; free & open, built from SRTM / GMTED / ETOPO1).
Output: tiles/relief.png — 8-bit grey, equirectangular, lon 110..156, lat -9..-45 at 0.05 deg;
value = elevation (m) / 2300 * 255, sea / below sea level = 0."""
import io, math, os, urllib.request
from PIL import Image
Z = 7
LON0, LON1, LAT0, LAT1, STEP = 110.0, 156.0, -9.0, -45.0, 0.05
def tx(lon): return (lon + 180) / 360 * 2 ** Z
def ty(lat): r = math.radians(lat); return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 2 ** Z
x0, x1 = int(tx(LON0)), int(tx(LON1)); y0, y1 = int(ty(LAT0)), int(ty(LAT1))
tiles = {}
for x in range(x0, x1 + 1):
    for y in range(y0, y1 + 1):
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png"
        for a in range(4):
            try:
                tiles[(x, y)] = Image.open(io.BytesIO(urllib.request.urlopen(url, timeout=60).read())).convert("RGB"); break
            except Exception as e:
                if a == 3: print("::warning::tile failed", url, e)
print(f"::notice::tiles {len(tiles)} of {(x1-x0+1)*(y1-y0+1)}")
W = int(round((LON1 - LON0) / STEP)); H = int(round((LAT0 - LAT1) / STEP))
out = Image.new("L", (W, H)); px = out.load(); mx = 0
for j in range(H):
    lat = LAT0 - (j + 0.5) * STEP
    fy = ty(lat)
    for i in range(W):
        lon = LON0 + (i + 0.5) * STEP
        fx = tx(lon); T = tiles.get((int(fx), int(fy)))
        if not T: continue
        r, g, b = T.getpixel((min(255, int((fx % 1) * 256)), min(255, int((fy % 1) * 256))))
        e = r * 256 + g + b / 256 - 32768
        mx = max(mx, e)
        px[i, j] = 0 if e <= 0 else max(1, min(255, int(round(e / 2300 * 255))))
os.makedirs("tiles", exist_ok=True); out.save("tiles/relief.png", optimize=True)
print(f"::notice::relief {W}x{H}, max {mx:.0f} m, {os.path.getsize('tiles/relief.png')//1024} KB")
