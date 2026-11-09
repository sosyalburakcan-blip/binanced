# UNI 08:00-09:00 gerçek piyasa (fapi.binance.com, herkese açık): ne oldu, piyasa geneli miydi?
import json, time, requests, statistics as st
R = "https://fapi.binance.com"; S = requests.Session()
def g(p, **q):
    r = S.get(R + p, params=q, timeout=15); r.raise_for_status(); time.sleep(0.1); return r.json()
T0 = 1793952000000  # 08:00 UTC
U = json.load(open("/root/binanced/v9live/universe_2026-11.json"))
U = U if isinstance(U, list) else U.get("symbols", U)
# 1) 08:00-09:00 saat mumu: 30 coin
res = {}
for s in U:
    k = g("/fapi/v1/klines", symbol=s, interval="1h", startTime=T0, limit=1)[0]
    o, c, v, tb = float(k[1]), float(k[4]), float(k[5]), float(k[9])
    res[s] = (c / o - 1, tb / v if v else float("nan"), float(k[2]) / o - 1, float(k[3]) / o - 1)
rk = sorted(res, key=lambda s: res[s][0])
print("08:00-09:00 saati, 30 coin getiri sırası (en kötüden):")
for i, s in enumerate(rk):
    r, tk, hi, lo = res[s]
    if s in ("UNIUSDT", "GTCUSDT", "TAOUSDT", "BTCUSDT", "SANDUSDT", "1000PEPEUSDT") or i < 5:
        print(f"  {i+1:2}. {s:13} {r:+.2%}  alıcı payı {tk:.3f}  en yüksek {hi:+.2%} en düşük {lo:+.2%}")
print(f"  30 coin ortanca {st.median(v[0] for v in res.values()):+.2%}, ortalama {st.mean(v[0] for v in res.values()):+.2%}")
# 2) UNI dakika dakika
k = g("/fapi/v1/klines", symbol="UNIUSDT", interval="5m", startTime=T0 - 3600_000, limit=24)
print("\nUNI 5 dk mumlar (07:00-09:00): saat  kapanış  hacim  alıcı payı")
for x in k:
    v = float(x[5]); print(f"  {time.strftime('%H:%M', time.gmtime(x[0]/1000))}  {float(x[4]):.3f}  {v:8.0f}  {float(x[9])/v:.2f}")
# 3) UNI açık pozisyon adedi (5 dk)
oi = g("/futures/data/openInterestHist", symbol="UNIUSDT", period="5m", startTime=T0 - 3600_000, limit=30)
print("\nUNI açık pozisyon adedi (5 dk):", " ".join(f"{time.strftime('%H:%M', time.gmtime(x['timestamp']/1000))}={float(x['sumOpenInterest'])/1e6:.3f}M" for x in oi[::3]))
# 4) UNI önceki 24 saat: saatlik
k = g("/fapi/v1/klines", symbol="UNIUSDT", interval="1h", startTime=T0 - 24*3600_000, limit=25)
print("\nUNI son 24 saat, saatlik getiri:", " ".join(f"{time.strftime('%H', time.gmtime(x[0]/1000))}:{100*(float(x[4])/float(x[1])-1):+.1f}" for x in k))
