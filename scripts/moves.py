"""Daily after the ASX close: "why did this stock move?" (data/moves.json).
For each company it splits recent price moves into: its main commodity price, the ASX sector, dividends paid out,
and company-specific news (the big up/down days matched to that day's ASX announcement or news headline).
Free sources only: Yahoo Finance daily charts, ASX announcements (asx.com.au), Google News RSS."""
import re, math, html, urllib.parse
from zoneinfo import ZoneInfo
from datetime import date as Date
from common import *

SYD = ZoneInfo("Australia/Sydney")
INFO = json.load(open(os.path.join(os.path.dirname(__file__), "coinfo.json")))
try:
    for c, p in (load("newcos", {}) or {}).items():
        if c not in INFO and p.get("lat") is not None:
            INFO[c] = {"n": p.get("name", c), "e": [p.get("e") or "gold"]}
except Exception:
    pass
# what each company's share price really follows (site counts mislead for the majors)
MAIN = {"BHP": ["iron", "copper"], "RIO": ["iron", "copper"], "FMG": ["iron"], "MIN": ["lithium", "iron"], "S32": ["copper"],
        "WDS": ["oil"], "STO": ["oil"], "IGO": ["lithium"], "WES": ["lithium"], "NEM": ["gold"], "NST": ["gold"], "EVN": ["gold", "copper"],
        "SFR": ["copper"], "CMM": ["gold"], "WHC": ["coal"], "YAL": ["coal"], "NHC": ["coal"], "BOE": ["uranium"], "PDN": ["uranium"], "DYL": ["uranium"]}
COM = {"gold": ("GC=F", "gold price"), "silver": ("SI=F", "silver price"), "copper": ("HG=F", "copper price"),
       "iron": ("TIO=F", "iron ore price"), "coal": ("MTF=F", "coal price"), "oil": ("BZ=F", "oil price (Brent)"),
       "uranium": ("URA", "uranium (URA fund)"), "lithium": ("LIT", "lithium (LIT fund)")}
SECTOR = {"oil": ("^AXEJ", "ASX energy sector"), "coal": ("^AXEJ", "ASX energy sector")}
DEF_SECTOR = ("^AXMJ", "ASX materials sector")
WIN = {"1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 250}

def yahoo(sym):
    r = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=1y&interval=1d&events=div")["chart"]["result"][0]
    ts, cl = r.get("timestamp") or [], r["indicators"]["quote"][0].get("close") or []
    out = {}
    for t, v in zip(ts, cl):
        if v:
            out[datetime.fromtimestamp(t, SYD).date().isoformat()] = float(v)
    dv = [[datetime.fromtimestamp(int(x["date"]), SYD).date().isoformat(), float(x["amount"])] for x in (r.get("events", {}).get("dividends", {}) or {}).values()]
    return {"px": out, "dv": sorted(dv)}

def at_or_before(series, keys, d):
    """value of a benchmark on or just before date d (US markets close after the ASX, so use the prior session)"""
    lo, hi, best = 0, len(keys) - 1, None
    while lo <= hi:
        m = (lo + hi) // 2
        if keys[m] < d: best = keys[m]; lo = m + 1
        else: hi = m - 1
    return series[best] if best else None

def ols(Y, X):
    """least squares, X rows of factors (intercept added). Returns betas (no intercept)."""
    n, k = len(Y), len(X[0]) + 1
    A = [[0.0] * k for _ in range(k)]; b = [0.0] * k
    for y, x in zip(Y, X):
        r = [1.0] + list(x)
        for i in range(k):
            b[i] += r[i] * y
            for j in range(k): A[i][j] += r[i] * r[j]
    for i in range(k): A[i][i] += 1e-9
    for i in range(k):  # gaussian elimination
        p = max(range(i, k), key=lambda r: abs(A[r][i])); A[i], A[p] = A[p], A[i]; b[i], b[p] = b[p], b[i]
        if abs(A[i][i]) < 1e-12: return [0.0] * (k - 1)
        for r in range(i + 1, k):
            f = A[r][i] / A[i][i]
            for j in range(i, k): A[r][j] -= f * A[i][j]
            b[r] -= f * b[i]
    x = [0.0] * k
    for i in range(k - 1, -1, -1):
        x[i] = (b[i] - sum(A[i][j] * x[j] for j in range(i + 1, k))) / A[i][i]
    return x[1:]

KINDS = [  # (regex on the announcement title, kind, plain-English meaning)
    (r"placement|capital raising|entitlement|share purchase plan|\bspp\b|equity raising|institutional offer", "raise", "raised money by issuing new shares (usually at a discount, which dilutes holders)"),
    (r"takeover|scheme|merger|bidder.?s statement|target.?s statement|unsolicited|non-binding indicative|proposal to acquire", "deal", "takeover / merger news"),
    (r"acquisition|acquire|divest|sale of|disposal|binding agreement|farm-?in|joint venture", "deal", "a deal to buy or sell assets"),
    (r"trading halt|suspension|voluntary suspension", "halt", "trading halt (shares paused before big news)"),
    (r"quarterly|activities report|production report|operations update|operational update", "qtr", "quarterly production / cost update"),
    (r"half.?year|full.?year|annual report|financial report|results|appendix 4[de]|earnings", "res", "financial results"),
    (r"guidance|outlook|downgrade|upgrade|revised", "guid", "production or cost guidance change"),
    (r"resource|reserve|\bjorc\b|mineral estimate", "res2", "resource / reserve update"),
    (r"drill|assay|intercept|hits|intersects|discovery|high.?grade|metres? at|m @|\bg/t\b", "drill", "drilling / exploration results"),
    (r"offtake|funding|debt facility|loan|finance|prepayment", "fund", "funding or sales-deal news"),
    (r"feasibility|\bdfs\b|\bpfs\b|scoping|study", "study", "mine study results"),
    (r"approval|permit|licen[cs]e|grant|native title|environmental", "appr", "approvals / permits news"),
    (r"incident|fatal|fire|flood|shutdown|outage|stoppage|suspend operations|force majeure", "op", "an operating problem at a mine"),
    (r"ceo|managing director|resign|appoint|board change|chair", "mgmt", "management change"),
    (r"dividend|distribution|buy-?back", "div", "dividend / buy-back news"),
]
def kind_of(t):
    t = t.lower()
    for rx, k, txt in KINDS:
        if re.search(rx, t): return k, txt
    return "ann", "company announcement"

def ann_day(iso, days):
    """the trading day an announcement hit the share price (after 4:10pm Sydney it is the next session)"""
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(SYD)
    except Exception:
        return None
    d = t.date().isoformat()
    if t.hour * 60 + t.minute > 16 * 60 + 10:
        d = (t.date() + timedelta(days=1)).isoformat()
    for x in days:
        if x >= d: return x
    return None

def announcements(c):
    for path in (f"announcements?count=100&v={bust()}", f"announcements?v={bust()}"):
        try:
            items = get(f"{ASX}{c.lower()}/{path}").get("data", {}).get("items", [])
            if items: return items
        except Exception:
            pass
    return []

def gnews(name, d):
    d0 = Date.fromisoformat(d)
    q = f'"{name}" after:{(d0 - timedelta(days=2)).isoformat()} before:{(d0 + timedelta(days=2)).isoformat()}'
    x = get("https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "en-AU", "gl": "AU", "ceid": "AU:en"}), as_json=False).decode("utf8", "ignore")
    out = []
    for it in re.findall(r"<item>(.*?)</item>", x, re.S)[:3]:
        t = re.search(r"<title>(.*?)</title>", it, re.S); u = re.search(r"<link>(.*?)</link>", it, re.S); s = re.search(r"<source[^>]*>(.*?)</source>", it, re.S)
        if t and u:
            h = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", t.group(1))).strip()
            src = html.unescape(s.group(1)).strip() if s else ""
            if src and h.endswith(" - " + src): h = h[: -len(src) - 3]
            out.append([h, src, u.group(1).strip()])
    return out

if __name__ == "__main__":
    codes = [c for c in CODES if c in INFO]
    bench_syms = {"^AXJO", "^AXMJ", "^AXEJ", "AUDUSD=X"} | {v[0] for v in COM.values()}
    bench = pmap(yahoo, sorted(bench_syms), workers=4)
    print("::notice::benchmarks ok:", ",".join(sorted(bench)))
    stocks = pmap(lambda c: yahoo(c + ".AX"), codes, workers=6)
    anns = pmap(announcements, list(stocks), workers=8)
    if anns:
        earliest = min((a.get("date", "9") for v in anns.values() for a in v), default="?")
        print(f"::notice::stocks {len(stocks)}/{len(codes)}, announcements for {len(anns)} (avg {sum(len(v) for v in anns.values()) / len(anns):.0f} each, earliest {earliest[:10]})")
    out, need_news = {}, []
    for c, s in stocks.items():
        days = sorted(s["px"]); px = [s["px"][d] for d in days]
        if len(days) < 30: continue
        els = MAIN.get(c) or INFO[c]["e"][:2]
        coms = [e for e in els if e in COM and COM[e][0] in bench][:2]
        sec_sym, sec_lab = SECTOR.get(els[0], DEF_SECTOR)
        if sec_sym not in bench: sec_sym, sec_lab = "^AXJO", "ASX 200"
        facs = [(sec_sym, sec_lab)] + [(COM[e][0], COM[e][1]) for e in coms]
        fser = [(bench[f]["px"], sorted(bench[f]["px"])) for f, _ in facs]
        # benchmark levels aligned to this stock's trading days (ASX index same day, US-traded markets prior session)
        lv = [[(ser.get(d) if f.startswith("^AX") else None) or at_or_before(ser, ks, d) for d in days] for (f, _), (ser, ks) in zip(facs, fser)]
        # weekly log returns -> sensitivity of this stock to each factor
        Y, X = [], []
        for i in range(5, len(days), 5):
            if all(l[i] and l[i - 5] for l in lv):
                Y.append(math.log(px[i] / px[i - 5])); X.append([math.log(l[i] / l[i - 5]) for l in lv])
        betas = [min(2.5, max(0.0, b)) for b in ols(Y, X)] if len(Y) >= 12 else [0.0] * len(facs)
        dr = [0.0] + [math.log(px[i] / px[i - 1]) for i in range(1, len(px))]
        sd = (sum(x * x for x in dr[-250:]) / max(1, len(dr[-250:]))) ** .5 or 0.02
        # big days: unusual moves, matched to announcements on that trading day
        ev_by_day = {}
        for a in anns.get(c, []):
            d = ann_day(a.get("date", ""), days)
            if d and a.get("documentKey"):
                ev_by_day.setdefault(d, []).append(a)
        big = []
        for i in range(1, len(days)):
            r = dr[i]
            if abs(r) >= max(0.04, 2.3 * sd):
                secr = (lv[0][i] / lv[0][i - 1] - 1) * 100 if lv[0][i] and lv[0][i - 1] else 0
                a = sorted(ev_by_day.get(days[i], []), key=lambda a: (not a.get("isPriceSensitive"), a.get("date", "")))
                row = [days[i], round((math.exp(r) - 1) * 100, 1), round(secr, 1)]
                if a:
                    k, txt = kind_of(a[0].get("headline", ""))
                    row += ["a", k, txt, a[0].get("headline", "")[:140], a[0]["documentKey"], 1 if a[0].get("isPriceSensitive") else 0]
                big.append(row)
        big.sort(key=lambda r: -abs(r[1])); big = big[:14]
        for r in big:
            if len(r) == 3: need_news.append((c, r))
        # windows
        hi_i = max(range(max(0, len(px) - 250), len(px)), key=lambda i: px[i]); lo_i = min(range(max(0, len(px) - 250), len(px)), key=lambda i: px[i])
        starts = {k: max(0, len(px) - 1 - n) for k, n in WIN.items()}
        if px[-1] < px[hi_i] * 0.92 and hi_i < len(px) - 3: starts["HI"] = hi_i
        if px[-1] > px[lo_i] * 1.08 and lo_i < len(px) - 3: starts["LO"] = lo_i
        W = {}
        for k, i0 in starts.items():
            tot = math.log(px[-1] / px[i0]); parts = []
            for j, b in enumerate(betas):
                if lv[j][-1] and lv[j][i0]:
                    fm = math.log(lv[j][-1] / lv[j][i0]); parts.append([round((math.exp(fm) - 1) * 100, 1), round(b * fm * 100, 1)])
                else: parts.append([None, 0.0])
            dv = [x for x in s["dv"] if days[i0] < x[0] <= days[-1]]
            dpts = -sum(a / (s["px"].get(d) or px[-1]) for d, a in dv) * 100
            W[k] = [days[i0], round(px[i0], 4), round((px[-1] / px[i0] - 1) * 100, 1), parts, round(dpts, 1)]
        out[c] = {"px": round(px[-1], 4), "d": days[-1], "f": [[f, l] for f, l in facs], "b": [round(b, 2) for b in betas], "sd": round(sd * 100, 2),
                  "w": W, "big": big, "dv": [x for x in s["dv"] if x[0] >= days[max(0, len(days) - 250)]]}
    # news for big days with no announcement (most recent / largest first, capped to stay polite)
    need_news.sort(key=lambda t: (-abs(t[1][1]) * (2 if t[1][0] >= (datetime.now(SYD).date() - timedelta(days=95)).isoformat() else 1)))
    need_news = need_news[:160]
    def one(i):
        c, r = need_news[i]
        return gnews(INFO[c]["n"], r[0])
    got = pmap(one, list(range(len(need_news))), workers=4)
    for i, (c, r) in enumerate(need_news):
        n = got.get(i) or []
        if n:
            r += ["n", n[0][0][:160], n[0][1], n[0][2]]
    print(f"::notice::moves for {len(out)} companies; news looked up for {len(need_news)} big days, found {sum(1 for v in got.values() if v)}")
    if len(out) >= 40:
        save("moves", {"asof": now_iso(), "src": "Yahoo Finance daily prices, ASX announcements, Google News (all free)", "m": out})
