import json
from common import *
for c in ["NST", "FEX"]:
    for ep in ["key-statistics", "header"]:
        try:
            d = asx(c, ep)["data"]; print(f"::notice::{c} {ep}: " + json.dumps(d)[:1700])
        except Exception as e: print(f"::notice::{c} {ep} fail {e}")
