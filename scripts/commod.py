"""Every hour: USD commodity ticker (data/commod.json). Free sources: gold-api.com, frankfurter.dev, Yahoo Finance charts,
with tradingeconomics.com as a fallback. Anything that fails keeps its previous value."""
import re
from common import *

YAHOO = {"gold": "GC=F", "silver": "SI=F", "copper": "HG=F", "brent": "BZ=F", "wti": "CL=F", "iron": "TIO=F", "coal": "MTF=F", "uranium": "UX=F"}
TE = {"lithium": "lithium", "gold": "gold", "silver": "silver", "copper": "copper", "brent": "brent-crude-oil", "wti": "crude-oil", "iron": "iron-ore", "coal": "coal", "uranium": "uranium"}
LB_TO_T = 2204.62
today = lambda: datetime.now(PERTH).strftime("%-d %b")

def yahoo(sym):
    m = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d")["chart"]["result"][0]["meta"]
    p, prev = float(m["regularMarketPrice"]), float(m.get("chartPreviousClose") or m.get("previousClose") or 0)
    return p, (round((p / prev - 1) * 100, 2) if prev else None)

def te_table():
    html = get("https://tradingeconomics.com/commodities", as_json=False).decode("utf8", "ignore")
    out = {}
    for k, slug in TE.items():
        m = re.search(r"href=['\"]/commodity/%s['\"].*?</tr>" % re.escape(slug), html, re.S)
        if not m:
            continue
        row = m.group(0)
        p = re.search(r'id="p"[^>]*>\s*([\d,\.]+)', row)
        c = re.search(r'id="pch"[^>]*>\s*([-+\d\.]+)%', row)
        if p:
            out[k] = (float(p.group(1).replace(",", "")), float(c.group(1)) if c else None)
    return out

if __name__ == "__main__":
    prev = (load("commod", {}) or {}).get("items", {})
    items, fresh = {}, 0
    te = None
    # lithium carbonate (China spot, CNY/t) -> US$/t
    try:
        te = te if te is not None else te_table()
        if te.get("lithium"):
            cny = float(get("https://api.frankfurter.dev/v1/latest?from=USD&to=CNY")["rates"]["CNY"])
            v, ch = te["lithium"]; items["lithium"] = {"v": round(v / cny), "ch": ch, "d": today()}; fresh += 1
    except Exception:
        te = te or {}
    if "lithium" not in items and "lithium" in prev:
        items["lithium"] = prev["lithium"]
    for k, sym in YAHOO.items():
        val = None
        try:
            val = yahoo(sym)
        except Exception:
            try:
                te = te if te is not None else te_table()
                val = te.get(k)
            except Exception:
                te = {}
        if k in ("gold", "silver"):  # spot price is fresher than the futures
            try:
                spot = float(get(f"https://api.gold-api.com/price/{'XAU' if k == 'gold' else 'XAG'}")["price"])
                val = (spot, val[1] if val else None)
            except Exception:
                pass
        if val:
            v, ch = val
            if k == "copper" and v < 50:  # US$/lb -> US$/t
                v = v * LB_TO_T
            items[k] = {"v": round(v, 2) if v < 1000 else round(v), "ch": ch, "d": today()}
            fresh += 1
        elif k in prev:
            items[k] = prev[k]
    try:
        r = get("https://api.frankfurter.dev/v1/latest?from=AUD&to=USD")
        v = round(float(r["rates"]["USD"]), 4)
        old = prev.get("aud", {})
        ch = round((v / old["v"] - 1) * 100, 2) if old.get("v") and old.get("d") != r["date"] else old.get("ch", 0)
        items["aud"] = {"v": v, "ch": ch, "d": r["date"]}
        fresh += 1
    except Exception:
        if "aud" in prev:
            items["aud"] = prev["aud"]
    if fresh >= 3:
        save("commod", {"asof": now_iso(), "src": "gold-api.com, frankfurter.dev, Yahoo Finance, tradingeconomics.com (free)", "items": items})
    print("commodities fresh", fresh, {k: v["v"] for k, v in items.items()})
