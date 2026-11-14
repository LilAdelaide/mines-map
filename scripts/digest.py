"""Monday morning (Perth): the week in one page (data/digest.json). Built from the other free data files.
w: every company's 1-week price change, so the app can pick out the user's own watchlist."""
import datetime
from common import *

def chg(arr, back):
    v = [x for x in arr if x]
    if len(v) <= back: return None
    a, b = v[-1 - back], v[-1]
    return round((b / a - 1) * 100, 2) if a else None

if __name__ == "__main__":
    today = datetime.date.today(); wk = (today - datetime.timedelta(days=7)).isoformat(); nxt = (today + datetime.timedelta(days=7)).isoformat()
    hist = load("hist", {}) or {}; px = (load("prices", {}) or {}).get("px", {}); st = (load("stats", {}) or {}).get("s", {})
    ann = (load("ann", {}) or {}).get("items", {}); sh = (load("shares", {}) or {}).get("s", {}); costs = load("costs", {}) or {}
    com = load("commod", {}) or {}
    w = {}
    for c, arr in (hist.get("px") or {}).items():
        x = chg(arr, 5)
        if x is not None: w[c] = x
    movers = sorted(w.items(), key=lambda kv: -kv[1])
    ps = []
    for c, items in ann.items():
        for a in items:
            if a[1] and (a[0] or "")[:10] >= wk: ps.append([a[0][:10], c, a[2], a[3]])
    ps.sort(reverse=True)
    dil = [[c, v[0], v[1], v[2]] for c, v in sh.items() if v[2] and v[2] >= wk and v[1]]
    hi, lo = [], []
    for c, v in st.items():
        p = (px.get(c) or [None])[0] or v[4]
        if not p: continue
        if v[0] and p >= v[0] * 0.995: hi.append([c, p, v[0]])
        if v[1] and p <= v[1] * 1.005: lo.append([c, p, v[1]])
    vol = []
    for c, v in px.items():
        if len(v) > 3 and v[3] and c in st and st[c][2]:
            r = v[3] / st[c][2]
            if r >= 3: vol.append([c, round(r, 1), v[1]])
    vol.sort(key=lambda x: -x[1])
    cal = [e for e in (costs.get("cal") or []) if today.isoformat() <= e[0] <= nxt]
    doc = {"asof": now_iso(), "week": [wk, today.isoformat()], "w": w,
           "up": movers[:10], "down": movers[::-1][:10], "ps": ps[:40], "dil": dil[:30], "hi": hi[:30], "lo": lo[:30], "vol": vol[:20], "cal": cal[:30],
           "com": com.get("items", {})}
    save("digest", doc)
    print("digest", len(w), "stocks;", len(ps), "price-sensitive;", len(dil), "share changes")
