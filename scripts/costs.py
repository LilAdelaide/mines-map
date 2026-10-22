"""Weekdays evening: gold producers' AISC from their quarterly reports + tidy the catalyst calendar (data/costs.json).
Best-effort text extraction from the report PDF; a figure is only replaced when one is found and looks sane."""
import io, re
from common import *

PRODUCERS = "NST EVN GMD VAU RRL RMS CMM WGX PNR OBM BGL CYL GGP ALK BC8".split()
REPORT = re.compile(r"quarter|quarterly|half[- ]year|full[- ]year|annual report|results", re.I)
AISC = re.compile(r"(?:AISC|all[- ]in[- ]sustaining[- ]costs?)[^.\n]{0,90}?A?\$\s?([1-6],?\d{3})(?!\d)", re.I)
GUIDE = re.compile(r"guidance[^.]{0,160}?A?\$\s?([1-6],?\d{3})\s*(?:–|-|to)\s*A?\$?\s?([1-6],?\d{3})", re.I)
FILE = "https://cdn-api.markitdigital.com/apiman-gateway/ASX/asx-research/1.0/file/"

def period(h):
    m = re.search(r"(Mar|Jun|Sep|Dec)\w*\s+(?:\d{4}\s+)?quarter|quarter\w*\s+(?:ended\s+)?\d*\s*(Mar|Jun|Sep|Dec)", h, re.I)
    if m:
        return (m.group(1) or m.group(2))[:3].title() + " Q"
    if re.search(r"half", h, re.I): return "H1"
    if re.search(r"full|annual", h, re.I): return "FY"
    return "Latest"

def pdf_text(key):
    from pypdf import PdfReader
    raw = get(FILE + key, as_json=False, timeout=60)
    r = PdfReader(io.BytesIO(raw))
    return "\n".join((p.extract_text() or "") for p in r.pages[:12])

if __name__ == "__main__":
    doc = load("costs", {}) or {}
    doc.setdefault("aisc", {}); doc.setdefault("cal", []); seen = doc.setdefault("seen", [])
    ann = (load("ann", {}) or {}).get("items", {})
    cutoff = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
    changed = []
    for c in PRODUCERS:
        for d, ps, h, key in ann.get(c, []):
            if not key or key in seen or (d or "") < cutoff or not REPORT.search(h or ""):
                continue
            seen.append(key)
            try:
                txt = pdf_text(key)
            except Exception:
                continue
            vals = [int(v.replace(",", "")) for v in AISC.findall(txt)]
            vals = [v for v in vals if 1000 <= v <= 6000]
            if not vals:
                continue
            g = GUIDE.search(txt)
            old = doc["aisc"].get(c, [None, "", None, None, "", ""])
            lo, hi = (int(g.group(1).replace(",", "")), int(g.group(2).replace(",", ""))) if g else (old[2], old[3])
            doc["aisc"][c] = [vals[0], period(h), lo, hi, FILE + key, old[5] if len(old) > 5 else ""]
            changed.append(f"{c} {old[0]}→{vals[0]}")
            break
    doc["seen"] = seen[-200:]
    keep = (datetime.now(PERTH) - timedelta(days=14)).strftime("%Y-%m-%d")
    doc["cal"] = sorted([e for e in doc["cal"] if e and e[0] >= keep], key=lambda e: e[0])[:40]
    doc["asof"] = now_iso()
    save("costs", doc)
    print("AISC changed:", changed or "none", "| calendar events:", len(doc["cal"]))
