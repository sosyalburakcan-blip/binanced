import json, sys
sys.path.insert(0, "/root/binanced/v9live/audit")
from demo_sign import g
U = json.load(open("/root/binanced/v9live/universe_2026-11.json"))
U = U if isinstance(U, list) else U.get("symbols", U)
bad = []
for b in g("/fapi/v1/leverageBracket"):
    if b["symbol"] not in U: continue
    b0 = b["brackets"][0]
    lev, cap, mmr = b0["initialLeverage"], b0["notionalCap"], b0["maintMarginRatio"]
    liq = (1 - 1/10) / (1 - mmr) - 1
    ok = lev >= 10 and cap >= 150
    if not ok: bad.append(b["symbol"])
    print(f"{b['symbol']:13} ilk basamak en çok {lev:>3}×, sınır {cap:>9} $, mmr {mmr:.3%} → 10× tasfiye ≈ {liq:+.2%}")
print("10× ya da 150 $ olmayan:", bad or "yok")
