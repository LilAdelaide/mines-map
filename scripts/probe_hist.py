import json, urllib.request, time
def n(m): print("::notice::" + str(m)[:600], flush=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json"}
for host in ["query2", "query1"]:
    for s in ["NST.AX", "GC=F", "HG=F", "AUDUSD=X"]:
        u = f"https://{host}.finance.yahoo.com/v8/finance/chart/{s}?range=2y&interval=1d"
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read())
            r = d["chart"]["result"][0]; n(f"OK {host} {s} pts {len(r['timestamp'])} last {r['indicators']['quote'][0]['close'][-1]}")
        except Exception as e: n(f"FAIL {host} {s} {e}")
        time.sleep(2)
