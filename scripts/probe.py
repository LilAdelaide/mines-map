import urllib.request, json
U=[("y1","https://query1.finance.yahoo.com/v8/finance/chart/BHP.AX?range=1y&interval=1d&events=div",{"User-Agent":"Mozilla/5.0"}),
("y2","https://query2.finance.yahoo.com/v8/finance/chart/BHP.AX?range=1y&interval=1d",{"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36","Accept":"*/*"}),
("y3","https://query1.finance.yahoo.com/v8/finance/chart/%5EAXMJ?range=1y&interval=1d",{"User-Agent":"curl/8.5.0"}),
("stooq","https://stooq.com/q/d/l/?s=bhp.au&i=d",{"User-Agent":"Mozilla/5.0"}),
("asxc1","https://asx.api.markitdigital.com/asx-research/1.0/companies/bhp/charts?period=1Y&v=1",{"User-Agent":"Mozilla/5.0"}),
("asxc2","https://asx.api.markitdigital.com/asx-research/1.0/companies/bhp/chart?period=1Y&v=2",{"User-Agent":"Mozilla/5.0"}),
("asxc3","https://asx.api.markitdigital.com/asx-research/1.0/markets/trade-history?symbol=BHP&v=3",{"User-Agent":"Mozilla/5.0"}),
("ann100","https://asx.api.markitdigital.com/asx-research/1.0/companies/bhp/announcements?count=100&v=4",{"User-Agent":"Mozilla/5.0"}),
]
for k,u,h in U:
    try:
        b=urllib.request.urlopen(urllib.request.Request(u,headers=h),timeout=20).read()
        extra=""
        if k=="ann100":
            it=json.loads(b)["data"]["items"]; extra=f" n={len(it)} last={it[-1]['date']}"
        print(f"::notice::{k} OK {len(b)}B{extra} {b[:150]!r}")
    except Exception as e:
        print(f"::notice::{k} FAIL {e}")
