"""After the close: how each stock moves with gold, copper, oil and the Australian dollar (data/sens.json).
1 year of daily closes from Yahoo Finance's public chart feed (free; paced with a browser agent).
For each company: multi-factor betas (least squares on daily returns, all in A$), each factor's correlation,
1-year change and volatility. Used by the What-if sliders, the screener and the mine cards."""
import json, math, time, urllib.request
from common import *

YUA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json"}
def chart(sym, rng="1y"):
    for a in range(4):
        try:
            u = f"https://query{1 + a % 2}.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range={rng}&interval=1d"
            r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=YUA), timeout=30).read())["chart"]["result"][0]
            out = {}
            for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]):
                if c: out[datetime.fromtimestamp(t, PERTH).date().isoformat()] = float(c)
            return out
        except Exception as e:
            time.sleep(3 + a * 4)
    return {}

def rets(series, dates):
    v = [series.get(d) for d in dates]; out = []
    for i in range(1, len(v)):
        out.append(math.log(v[i] / v[i - 1]) if v[i] and v[i - 1] else None)
    return out

def ols(y, X):
    """y = a + X b, normal equations (k <= 4)."""
    k = len(X[0]); n = len(y)
    A = [[0.0] * (k + 1) for _ in range(k + 1)]; B = [0.0] * (k + 1)
    for i in range(n):
        row = [1.0] + X[i]
        for p in range(k + 1):
            B[p] += row[p] * y[i]
            for q in range(k + 1): A[p][q] += row[p] * row[q]
    for c in range(k + 1):   # Gauss-Jordan
        piv = max(range(c, k + 1), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-12: return None
        A[c], A[piv] = A[piv], A[c]; B[c], B[piv] = B[piv], B[c]
        for r in range(k + 1):
            if r != c:
                f = A[r][c] / A[c][c]
                for q in range(c, k + 1): A[r][q] -= f * A[c][q]
                B[r] -= f * B[c]
    return [B[i] / A[i][i] for i in range(1, k + 1)]

def corr(a, b):
    n = len(a); ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else 0

if __name__ == "__main__":
    aud = chart("AUDUSD=X"); time.sleep(1.5)
    raw = {"gold": chart("GC=F"), "copper": chart("HG=F"), "oil": chart("CL=F")}
    fac = {k: {d: v / aud[d] for d, v in s.items() if d in aud} for k, s in raw.items()}   # in A$
    fac["aud"] = aud
    names = ["gold", "copper", "oil", "aud"]
    out = {}
    for i, c in enumerate(CODES):
        s = chart(f"{c}.AX"); time.sleep(0.6)
        dates = sorted(d for d in s if all(d in fac[f] for f in names))
        if len(dates) < 120: continue
        y = rets(s, dates); F = {f: rets(fac[f], dates) for f in names}
        idx = [j for j in range(len(y)) if y[j] is not None and all(F[f][j] is not None for f in names) and abs(y[j]) < 0.5]
        if len(idx) < 100: continue
        Y = [y[j] for j in idx]; X = [[F[f][j] for f in names] for j in idx]
        b = ols(Y, X)
        if not b: continue
        first, last = s[dates[0]], s[dates[-1]]
        vol = math.sqrt(sum(v * v for v in Y) / len(Y)) * math.sqrt(252) * 100
        out[c] = {"b": {f: round(b[k], 2) for k, f in enumerate(names)}, "r": {f: round(corr(Y, [x[k] for x in X]), 2) for k, f in enumerate(names)},
                  "ch1y": round((last / first - 1) * 100, 1), "vol": round(vol, 1), "n": len(Y)}
    if len(out) >= 50:
        save("sens", {"asof": now_iso(), "src": "Yahoo Finance daily closes, 1 year; factors in A$", "f": names, "s": out})
    print("sensitivity for", len(out), "stocks")
