"""06.11 ~19:00 kuralının BAĞIMSIZ denetimi (bot.py'yi içe aktarmaz): oynaklığa göre büyüklük + geri çekilme + eşit kâr al/stop.
Her açık pozisyon için (state.json, vol > 0):
  1. VOL60: karar anının 5 dk sınırında, son 1.500 adet gerçek 1 dk mum kapanışıyla 60 dk getirilerin popülasyon std'si (sıfırdan)
  2. geri çekilme fiyatı = aşağı tick(ref_px × (1 − 0,002)); hedef adet = aşağı adım(min(1.500, 12 / VOL60) / geri çekilme fiyatı)
     07.11'den beri "hemen al" (pb_px = 0): ilk emir fiyatı = ref_px (demo en iyi alış); hedef adet = aşağı adım(min(…) / ref_px)
  3. borsada (demo, imzalı GET): pozisyon adedi + giriş = state; kâr al emri = yukarı tick(giriş × (1 + VOL60)), adet = dolan;
     zarar stopu (algo, closePosition, MARK_PRICE) = yukarı tick(giriş × (1 − VOL60)); stopta fiyat kaybı ≤ 12 $
  4. live.db scores: her karar anında en çok 1 yeni giriş (chosen) — 06.11 19:00 sonrası
    /root/binanced/.venv/bin/python /root/binanced/v9live/audit/bracket_check.py
"""
import json, math, sqlite3, sys, time
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

import requests

import base64, urllib.parse  # noqa: E401,E402
from cryptography.hazmat.primitives.serialization import load_pem_private_key  # noqa: E402

env = dict(l.strip().split("=", 1) for l in open("/root/binanced/.env.testnet") if "=" in l and not l.startswith("#"))
_key = load_pem_private_key(open(env["BINANCE_TESTNET_PRIVATE_KEY_PATH"].strip(), "rb").read(), None)
_S = requests.Session()
_S.headers["X-MBX-APIKEY"] = env["BINANCE_TESTNET_API_KEY"].strip()


class X:  # yalnız imzalı GET (kendi Ed25519 imzası, exch_check.py ile aynı yöntem); bot.py değil
    @staticmethod
    def g(path, **p):
        p["timestamp"], p["recvWindow"] = int(time.time() * 1000), 10000
        qs = urllib.parse.urlencode(p)
        sig = base64.b64encode(_key.sign(qs.encode())).decode()
        r = _S.get(f"https://demo-fapi.binance.com{path}?{qs}&signature={urllib.parse.quote(sig)}", timeout=15)
        r.raise_for_status()
        return r.json()

REAL, M, H = "https://fapi.binance.com", 60_000, 3_600_000
PULLBACK, RISK, NOTIONAL, K, FROM_MS = 0.002, 12.0, 1500.0, 1.0, int(sys.argv[1]) if len(sys.argv) > 1 else 0


def q(x, step, mode):
    d, s = Decimal(str(x)), Decimal(str(step))
    return float((d / s).to_integral_value(rounding=mode) * s)


def vol60(sym, t):
    t5 = t // 300_000 * 300_000
    k = requests.get(REAL + "/fapi/v1/klines", params=dict(symbol=sym, interval="1m", startTime=t5 - 1500 * M,
                                                           endTime=t5 - 1, limit=1500), timeout=15).json()
    c = {int(x[0]): float(x[4]) for x in k if int(x[0]) + M <= t5}
    r = [c[o + H] / c[o] - 1 for o in range(t5 - 1500 * M, t5 - H, M) if o in c and o + H in c]
    mu = sum(r) / len(r)
    return math.sqrt(sum((x - mu) ** 2 for x in r) / len(r)), len(r)


info = requests.get("https://demo-fapi.binance.com/fapi/v1/exchangeInfo", timeout=15).json()["symbols"]
filt = {s["symbol"]: {f["filterType"]: f for f in s["filters"]} for s in info}
st = json.load(open("/root/binanced/v9live/state.json"))
pos = {x["symbol"]: x for x in X.g("/fapi/v3/positionRisk") if float(x["positionAmt"]) != 0}
orders = X.g("/fapi/v1/openOrders")
algos = X.g("/fapi/v1/openAlgoOrders")
bad = 0
for p in [p for p in st if p.get("vol", 0) > 0]:
    s, fs = p["sym"], filt[p["sym"]]
    tick, step = float(fs["PRICE_FILTER"]["tickSize"]), float(fs["LOT_SIZE"]["stepSize"])
    v, n = vol60(s, p["decision_ms"])
    chase = p["pb_px"] == 0                          # 07.11: hemen al (geri çekilme yok)
    pb = 0.0 if chase else q(p["ref_px"] * (1 - PULLBACK), tick, ROUND_FLOOR)
    tq = q(min(NOTIONAL, RISK / (K * v)) / (p["ref_px"] if chase else pb), step, ROUND_FLOOR)
    e = p["entry"]
    tp_want, sl_want = q(e * (1 + K * p["vol"]), tick, ROUND_CEILING), q(e * (1 - K * p["vol"]), tick, ROUND_CEILING)
    tp = [o for o in orders if o["symbol"] == s and o["clientOrderId"] == p.get("tp_cid")]
    sl = [a for a in algos if a["symbol"] == s and a.get("clientAlgoId") == p.get("es_cid")]
    bp = pos.get(s)
    rows = [
        ("VOL60 (bot / bağımsız)", p["vol"], v, abs(p["vol"] - v) < 1e-12),
        ("hemen alış (pb_px = 0)" if chase else "geri çekilme fiyatı", p["pb_px"], pb, abs(p["pb_px"] - pb) < tick / 10),
        ("hedef adet", p["target_qty"], tq, abs(p["target_qty"] - tq) < step / 10),
        ("borsa adet / dolan", float(bp["positionAmt"]) if bp else None, p["filled_qty"],
         bp is not None and abs(float(bp["positionAmt"]) - p["filled_qty"]) < step / 10),
        ("borsa giriş / bot", float(bp["entryPrice"]) if bp else None, e, bp is not None and abs(float(bp["entryPrice"]) - e) < 1e-9 * e),
    ]
    if p.get("tp_cid"):
        rows.append(("kâr al fiyatı", float(tp[0]["price"]) if tp else None, tp_want, bool(tp) and abs(float(tp[0]["price"]) - tp_want) < tick / 10))
    rows.append(("zarar stopu tetik", float(sl[0]["triggerPrice"]) if sl else None, sl_want,
                 bool(sl) and abs(float(sl[0]["triggerPrice"]) - sl_want) < tick / 10 and sl[0].get("workingType") == "MARK_PRICE"))
    loss = p["filled_qty"] * (sl_want - e)
    rows.append(("stopta fiyat kaybı ($) ≥ −12", round(loss, 3), -RISK, loss >= -RISK - 1e-9))
    print(f"\n{s}: karar {time.strftime('%H:%M', time.gmtime(p['decision_ms'] / 1000))} UTC, VOL60 için {n} getiri, "
          f"giriş {e:.6g} × {p['filled_qty']:g} = {e * p['filled_qty']:.1f} $")
    for name, a, b_, ok in rows:
        bad += not ok
        print(f"  {'✓' if ok else '✗'} {name:30s} {a!s:>16} | {b_!s:>16}")
db = sqlite3.connect("file:/root/binanced/v9live/live.db?mode=ro", uri=True)
many = db.execute("select ts, count(*) from scores where chosen = 1 and ts >= ? group by ts having count(*) > 1", (FROM_MS,)).fetchall()
print(f"\nkarar anı başına > 1 giriş (ts ≥ {FROM_MS}): {len(many)} {many[:5]}")
bad += len(many)
print("SORUN:", bad)
