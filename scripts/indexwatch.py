"""After the close: every ASX company ranked by market value (data/index.json), to estimate who sits near the
S&P/ASX 200 and 300 lines before each quarterly rebalance. Free source: ASX company directory.
Estimate only: S&P also weighs liquidity and free float, and confirms changes about two weeks before each rebalance."""
from common import *

def page(n):
    d = get(f"https://asx.api.markitdigital.com/asx-research/1.0/companies/directory?page={n}&itemsPerPage=100&order=descending&orderBy=marketCap&includeFilterOptions=false&recentListingsOnly=false&v={bust()}")
    return d.get("data", {}).get("items", [])

if __name__ == "__main__":
    rows = []
    for n in range(5):
        try: items = page(n)
        except Exception as e: print("page", n, e); break
        rows += items
        if len(items) < 100: break
    rows = [r for r in rows if r.get("symbol") and (r.get("marketCap") or 0) > 0]
    rows.sort(key=lambda r: -(r.get("marketCap") or 0))
    if len(rows) >= 300:
        cut = {str(k): int(rows[k - 1]["marketCap"]) for k in (200, 300)}
        r = {x["symbol"]: [i + 1, int(x["marketCap"])] for i, x in enumerate(rows[:420])}
        save("index", {"asof": now_iso(), "src": "ASX company directory (market value ranking)", "cut": cut, "r": r})
    print("index ranks", len(rows))
