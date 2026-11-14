import json, urllib.request
from common import *
def n(m): print("::notice::" + str(m)[:900], flush=True)
tries = ["https://asx.api.markitdigital.com/asx-research/1.0/companies/NST/chart?period=1Y",
         "https://asx.api.markitdigital.com/asx-research/1.0/companies/NST/chart-data?period=1Y",
         "https://asx.api.markitdigital.com/asx-research/1.0/markets/charts/NST/price?interval=1D&range=1Y",
         "https://stooq.com/q/d/l/?s=xauusd&i=d", "https://stooq.com/q/d/l/?s=hg.f&i=d", "https://stooq.com/q/d/l/?s=audusd&i=d", "https://stooq.com/q/d/l/?s=nst.au&i=d",
         "https://query1.finance.yahoo.com/v8/finance/chart/NST.AX?range=1y&interval=1d"]
for u in tries:
    try:
        r = get(u, as_json=False, timeout=40).decode("utf8", "ignore"); n(f"OK {u} :: {r[:300]!r}")
    except Exception as e: n(f"FAIL {u} :: {e}")
