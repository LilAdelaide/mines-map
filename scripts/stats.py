"""Weekdays after the close: 52-week range, volume, yield (data/stats.json) and the daily close history (data/hist.json)."""
from common import *

def ks(c):
    d = asx(c, "key-statistics")["data"]
    return [d.get("priceFiftyTwoWeekHigh"), d.get("priceFiftyTwoWeekLow"), int(d.get("volumeAverage") or 0),
            round(float(d.get("yieldAnnual") or 0), 2), d.get("priceClose")]

if __name__ == "__main__":
    s = pmap(ks, CODES)
    px = (load("prices", {}) or {}).get("px", {})
    for c, v in s.items():  # today's close = latest delayed price after the close
        if c in px:
            v[4] = px[c][0]
    if len(s) >= 60:
        save("stats", {"asof": now_iso(), "src": "ASX key statistics (asx.com.au)", "s": s})
    h = load("hist", {"d": [], "px": {}}) or {"d": [], "px": {}}
    today = now_iso()[:10]
    n = len(h["d"])
    if not h["d"] or h["d"][-1] != today:
        h["d"].append(today)
        for arr in h["px"].values():
            arr.append(None)
    for c, v in s.items():
        close = v[4]
        arr = h["px"].setdefault(c, [None] * len(h["d"]))
        while len(arr) < len(h["d"]):
            arr.insert(0, None)
        arr[-1] = round(float(close), 4) if close else None
    if len(h["d"]) > 400:
        cut = len(h["d"]) - 400
        h["d"] = h["d"][cut:]
        h["px"] = {k: v[cut:] for k, v in h["px"].items()}
    if s:
        save("hist", h)
    print("stats", len(s), "history days", len(h["d"]))
