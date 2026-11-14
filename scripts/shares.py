"""Shares on issue for every company (data/shares.json = {asof, s:{CODE:[shares, previous, changed YYYY-MM-DD]}, pend:{CODE: until}}).
Refreshed daily after the close (stats.py) and, within the 15-minute price job, for any company that has just
announced new or cancelled shares (placements, quotation of securities, option exercises, buy-backs ...)."""
import re
from common import *
import datetime as dt

ISSUE = re.compile(r"quotation of securities|appendix 2a|appendix 3b|application for quotation|proposed issue|placement|issue of (shares|securities)|"
                   r"cleansing|share purchase plan|\bspp\b|entitlement|conversion of|exercise of (options|warrants)|cessation of securities|"
                   r"buy-?back|cancellation of|capital raising|raise[sd]? \$|notification of (buy-back|cessation)", re.I)

def num_shares(c):
    n = asx(c, "key-statistics")["data"].get("numOfShares")
    return int(n) if n else None

def merge(found, doc=None):
    doc = doc or load("shares", {}) or {}
    S = doc.setdefault("s", {}); today = now_iso()[:10]; ch = 0
    for c, n in found.items():
        if not n: continue
        cur = S.get(c)
        if not cur: S[c] = [n, None, None]; ch += 1
        elif cur[0] != n: S[c] = [n, cur[0], today]; ch += 1
    doc["asof"] = now_iso(); doc["src"] = "ASX key statistics (asx.com.au)"
    return doc, ch

def watch(ann_items):
    """ann_items = {CODE: [[date, sensitive, headline, key], ...]} -> refresh shares for companies with share-issue news (checked again for 3 days)."""
    doc = load("shares", {}) or {}
    pend = doc.setdefault("pend", {}); seen = set(doc.get("seenAnn", []))
    today = now_iso()[:10]
    for c, items in ann_items.items():
        for a in items[:4]:
            if a[3] in seen: continue
            seen.add(a[3])
            if ISSUE.search(a[2] or ""):
                pend[c] = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    for c in [c for c, u in pend.items() if u < today]: pend.pop(c)
    doc["seenAnn"] = list(seen)[-600:]
    found = pmap(num_shares, list(pend)) if pend else {}
    doc, ch = merge(found, doc)
    save("shares", doc)
    print("shares: watching", len(pend), "changed", ch)
