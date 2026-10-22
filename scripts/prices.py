"""Every 15 min in ASX hours: share prices + gold (data/prices.json) and announcements (data/ann.json)."""
from common import *

def header(c):
    d = asx(c, "header")["data"]
    p = d.get("priceLast")
    if not p:
        return None
    return [round(float(p), 4), round(float(d.get("priceChangePercent") or 0), 2), int(max(0, d.get("marketCap") or 0))]

def gold():
    try:
        usd = float(get("https://api.gold-api.com/price/XAU")["price"])
        aud = float(get("https://api.frankfurter.dev/v1/latest?from=USD&to=AUD")["rates"]["AUD"])
        return {"usd": round(usd, 2), "audusd": round(1 / aud, 4), "asof": now_iso()}
    except Exception:
        return None

def anns(c):
    items = asx(c, "announcements").get("data", {}).get("items", [])
    return [[a.get("date"), 1 if a.get("isPriceSensitive") else 0, a.get("headline", ""), a.get("documentKey", "")] for a in items[:8] if a.get("documentKey")]

if __name__ == "__main__":
    px = pmap(header, CODES)
    prev = load("prices", {}) or {}
    if len(px) >= 60:
        doc = {"asof": now_iso(), "src": "ASX delayed quotes (asx.com.au)", "n": len(px), "px": px}
        g = gold() or prev.get("gold")
        if g:
            doc["gold"] = g
        save("prices", doc)
    an = pmap(anns, CODES)
    if len(an) >= 20:
        save("ann", {"asof": now_iso(), "src": "ASX announcements (asx.com.au)", "items": an})
    print("prices", len(px), "announcements", len(an))
