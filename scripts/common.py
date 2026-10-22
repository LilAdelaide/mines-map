"""Shared helpers for the free data jobs (run by GitHub Actions; standard library only)."""
import json, os, time, random, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

PERTH = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36 MinesMap/1.0"
CODES = json.load(open(os.path.join(os.path.dirname(__file__), "codes.json")))
try:   # companies added automatically from new ASX listings get live data too
    CODES += [c for c, p in json.load(open(os.path.join(DATA, "newcos.json"))).items() if p.get("lat") is not None and c not in CODES]
except Exception:
    pass
ASX = "https://asx.api.markitdigital.com/asx-research/1.0/companies/"

def now_iso():
    return datetime.now(PERTH).replace(microsecond=0).isoformat()

def get(url, as_json=True, tries=3, timeout=25, data=None):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": "application/json, text/html, */*", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            return json.loads(body) if as_json else body
        except Exception as e:  # network hiccup, rate limit: back off and retry
            last = e
            time.sleep(1.5 * (i + 1) + random.random())
    raise last

def bust():
    return f"{int(time.time())}{random.randint(100, 999)}"

def asx(code, path):
    """ASX delayed data. The 'v' parameter defeats the CDN cache ('t' and '_' are ignored)."""
    return get(f"{ASX}{code.lower()}/{path}?v={bust()}{code.lower()}")

def pmap(fn, items, workers=12):
    out = {}
    def one(x):
        try:
            return x, fn(x)
        except Exception as e:
            return x, None
    with ThreadPoolExecutor(workers) as ex:
        for k, v in ex.map(one, items):
            if v is not None:
                out[k] = v
    return out

def load(name, default=None):
    try:
        return json.load(open(os.path.join(DATA, name + ".json")))
    except Exception:
        return default

def save(name, obj):
    p = os.path.join(DATA, name + ".json"); tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, p)
