"""Phone alerts through ntfy (free, no account): runs after each 15-minute price update.
Each company has its own topic, minesmap-3688cedce5-<CODE>; subscribe to it in the ntfy app (the app's bell button links there).
minesmap-3688cedce5-all carries only the big ones (price-sensitive news, ±10% moves, takeovers) for every company.
Alerts: price-sensitive announcements, new / cancelled shares, takeovers, ±5% moves, 3× volume, new 52-week highs / lows."""
import re, urllib.request
from common import *

BASE = "minesmap-3688cedce5"
TAKE = re.compile(r"takeover|scheme (booklet|implementation|meeting)|bidder'?s statement|target'?s statement|off-market offer|merger|non-binding (indicative )?(offer|proposal)|change of control", re.I)
ISSUE = re.compile(r"placement|capital raising|entitlement|share purchase plan|\bspp\b|proposed issue|quotation of securities", re.I)
ANN = "https://cdn-api.markitdigital.com/apiman-gateway/ASX/asx-research/1.0/file/"
APP = "https://liladelaide.github.io/mines-map/"

def latin(s): return s.encode("latin-1", "ignore").decode("latin-1")

def push(topic, title, body, click="", tags="", prio="default"):
    h = {"Title": latin(title)[:200], "Priority": prio}
    if click: h["Click"] = click
    if tags: h["Tags"] = tags
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode("utf8"), headers=h, method="POST"), timeout=15).read()
        return True
    except Exception as e:
        print("push failed", topic, e); return False

if __name__ == "__main__":
    st = load("alerts_state", {}) or {}
    today = now_iso()[:10]
    first = not st.get("seen")
    if st.get("day") != today: st["day"] = today; st["sent"] = []
    seen, sent = set(st.get("seen", [])), set(st.get("sent", []))
    px = (load("prices", {}) or {}).get("px", {}); stats = (load("stats", {}) or {}).get("s", {})
    ann = (load("ann", {}) or {}).get("items", {}); sh = (load("shares", {}) or {}).get("s", {})
    out = []   # (code, title, body, click, tags, big)
    for c, items in ann.items():
        for a in items[:5]:
            k = a[3]
            if k in seen: continue
            seen.add(k)
            if first or (a[0] or "")[:10] < today: continue
            h = a[2] or ""
            if TAKE.search(h): out.append((c, f"{c} · takeover / deal news", h, ANN + k, "handshake", True))
            elif ISSUE.search(h): out.append((c, f"{c} · capital raising", h, ANN + k, "moneybag", bool(a[1])))
            elif a[1]: out.append((c, f"{c} · price-sensitive", h, ANN + k, "loudspeaker", True))
    for c, v in px.items():
        if not v or len(v) < 2: continue
        p, chg = v[0], v[1] or 0
        if abs(chg) >= 5 and f"{c}:mv{'u' if chg > 0 else 'd'}" not in sent:
            sent.add(f"{c}:mv{'u' if chg > 0 else 'd'}")
            out.append((c, f"{c} {'+' if chg > 0 else ''}{chg:.1f}% today", f"Now A${p:g}", APP, "chart_with_upwards_trend" if chg > 0 else "chart_with_downwards_trend", abs(chg) >= 10))
        s = stats.get(c)
        if s and len(v) > 3 and v[3] and s[2] and v[3] / s[2] >= 3 and f"{c}:vol" not in sent:
            sent.add(f"{c}:vol"); out.append((c, f"{c} · {v[3] / s[2]:.1f}x normal volume", f"{v[3]:,} shares traded so far today ({'+' if chg >= 0 else ''}{chg:.1f}%)", APP, "fire", False))
        if s and s[0] and p > s[0] and f"{c}:hi" not in sent:
            sent.add(f"{c}:hi"); out.append((c, f"{c} · new 52-week high", f"A${p:g} (previous high A${s[0]:g})", APP, "arrow_up", False))
        if s and s[1] and p < s[1] and f"{c}:lo" not in sent:
            sent.add(f"{c}:lo"); out.append((c, f"{c} · new 52-week low", f"A${p:g} (previous low A${s[1]:g})", APP, "arrow_down", False))
    for c, v in sh.items():
        if v[2] == today and v[1] and f"{c}:sh" not in sent:
            sent.add(f"{c}:sh"); d = v[0] - v[1]
            out.append((c, f"{c} · shares on issue {'up' if d > 0 else 'down'} {abs(d) / v[1] * 100:.1f}%", f"{v[1]:,} -> {v[0]:,} shares", APP, "page_facing_up", False))
    n = 0
    for c, t, b, click, tags, big in out[:60]:
        if push(f"{BASE}-{c}", t, b, click, tags, "high" if big else "default"): n += 1
        if big: push(f"{BASE}-all", t, b, click, tags, "default")
    st["seen"] = list(seen)[-2000:]; st["sent"] = list(sent)
    save("alerts_state", st)
    print("alerts sent", n, "of", len(out), "(first run: no announcement alerts)" if first else "")
