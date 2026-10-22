"""Twice an hour: headlines per element and global price drivers (data/news.json) from Google News RSS (free)."""
import re, html, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from common import *

CODES_SET = set(CODES)
NAMES = {}  # company names → ASX code, for tagging headlines
try:
    NAMES = json.load(open(os.path.join(os.path.dirname(__file__), "names.json")))
except Exception:
    pass
EL = {
 "gold": "ASX gold miners OR \"Northern Star\" OR \"Evolution Mining\" OR Ramelius OR \"Genesis Minerals\" OR Westgold",
 "iron": "ASX iron ore BHP OR \"Rio Tinto\" OR Fortescue OR \"Mineral Resources\"",
 "oil": "ASX Woodside OR Santos OR \"Beach Energy\" oil gas",
 "coal": "ASX Whitehaven OR \"New Hope\" OR Yancoal OR Stanmore coal",
 "uranium": "ASX uranium Paladin OR \"Boss Energy\" OR \"Deep Yellow\" OR Bannerman",
 "copper": "ASX copper Sandfire OR 29Metals OR \"AIC Mines\"",
 "silver": "ASX silver stocks",
 "tungsten": "ASX tungsten",
 "salt": "\"BCI Minerals\" Mardie",
 "diamonds": "Australia diamond mine",
}
DRV = {"gold": "gold price", "iron": "iron ore price", "oil": "oil price Brent", "coal": "coal price Newcastle",
       "uranium": "uranium price", "copper": "copper price", "silver": "silver price"}
UP = re.compile(r"\b(rise|rises|rising|rose|jump|jumps|surge|surges|soar|soars|gain|gains|climb|climbs|rall(y|ies)|record high|higher|up|boost|strong)\b", re.I)
DOWN = re.compile(r"\b(fall|falls|fell|drop|drops|slump|slumps|slide|slides|sink|sinks|plunge|plunges|lower|down|low|lows|weak|weaker|tumble|tumbles|decline|declines)\b", re.I)

def rss(q, days=7):
    url = f"https://news.google.com/rss/search?q={quote(q + f' when:{days}d')}&hl=en-AU&gl=AU&ceid=AU:en"
    root = ET.fromstring(get(url, as_json=False))
    out = []
    for it in root.iter("item"):
        t = html.unescape(it.findtext("title") or "")
        src = it.findtext("source") or ""
        if src and t.endswith(" - " + src):
            t = t[: -len(" - " + src)]
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate")).astimezone(PERTH)
        except Exception:
            dt = None
        out.append({"h": t.strip()[:160], "src": src or "Google News", "url": it.findtext("link") or "", "dt": dt})
    out.sort(key=lambda x: x["dt"] or datetime.min.replace(tzinfo=PERTH), reverse=True)
    return out

def tag(h):
    found = [c for c in re.findall(r"\b[A-Z0-9]{3}\b", h) if c in CODES_SET]
    low = h.lower()
    found += [c for n, c in NAMES.items() if n in low]
    return sorted(set(found))[:4]

def fmt(x):
    return {"h": x["h"], "src": x["src"], "d": x["dt"].strftime("%-d %b %Y") if x["dt"] else "", "url": x["url"], "tk": tag(x["h"])}

if __name__ == "__main__":
    prev = load("news", {}) or {}
    news, macro = {}, {}
    for k, q in EL.items():
        try:
            seen, lst = set(), []
            for x in rss(q):
                key = x["h"].lower()[:60]
                if key in seen or not x["url"]:
                    continue
                seen.add(key); lst.append(fmt(x))
                if len(lst) == 6:
                    break
            if lst:
                news[k] = lst
        except Exception:
            pass
    for k, q in DRV.items():
        try:
            items = rss(q, 3)[:1]
            for x in items:
                fx = "up" if UP.search(x["h"]) and not DOWN.search(x["h"]) else "down" if DOWN.search(x["h"]) and not UP.search(x["h"]) else "mixed"
                d = fmt(x); d["fx"] = fx; d.pop("tk", None)
                macro[k] = [d]
        except Exception:
            pass
    try:
        x = rss("US Federal Reserve OR \"US dollar\" OR China demand commodities", 3)[0]
        fx = "up" if UP.search(x["h"]) and not DOWN.search(x["h"]) else "down" if DOWN.search(x["h"]) and not UP.search(x["h"]) else "mixed"
        macro_all = fmt(x); macro_all["fx"] = fx; macro_all.pop("tk", None)
    except Exception:
        macro_all = prev.get("macroAll")
    for k, v in (prev.get("news") or {}).items():  # keep older headlines for an element with nothing new
        news.setdefault(k, v)
    if len(news) >= 4:
        doc = {"asof": now_iso(), "src": "Google News (free)", "news": news, "macro": macro or prev.get("macro", {})}
        if macro_all:
            doc["macroAll"] = macro_all
        save("news", doc)
    print("news", {k: len(v) for k, v in news.items()}, "drivers", list(macro))
