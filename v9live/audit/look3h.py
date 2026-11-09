# Bağımsız bakış: bot kodunu içe aktarmaz. Veri: Binance USDⓈ-M herkese açık 1h mumları (fapi.binance.com).
import json, sys, time, urllib.request, statistics as st
from concurrent.futures import ThreadPoolExecutor
H = 3600_000
uni = json.load(open(sys.argv[1]))
end = (int(time.time() * 1000) // H) * H          # şu anki saatin açılışı (biten son mum bundan önce)
start = end - 15 * 24 * H
def kl(sym):
    out, s = [], start
    while s < end:
        u = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=1h&startTime={s}&endTime={end-1}&limit=1500"
        d = json.load(urllib.request.urlopen(u, timeout=20))
        if not d: break
        out += d; s = int(d[-1][0]) + H
    return sym, {int(x[0]): (float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in out}
with ThreadPoolExecutor(8) as ex: K = dict(ex.map(kl, uni))
rows = []   # (t, sym, r3, r2, r1, fwd1, up1, dn1, fwd4)
for sym, k in K.items():
    for o in k:
        t = o + H                                  # karar anı = bu mumun kapanışı
        need = [t - 4*H, t - 3*H, t - 2*H, t - H, t, t + H, t + 2*H, t + 3*H]
        if not all(x in k for x in need[:5]): continue
        C = lambda op: k[op][3]
        c0 = C(t - H)
        r1 = c0 / C(t - 2*H) - 1; r2 = C(t - 2*H) / C(t - 3*H) - 1; r3 = C(t - 3*H) / C(t - 4*H) - 1
        if t in k:
            nx = k[t]; fwd1 = nx[3] / c0 - 1; up1 = nx[1] / c0 - 1; dn1 = nx[2] / c0 - 1
        else:
            continue
        fwd4 = k[t + 3*H][3] / c0 - 1 if (t + 3*H) in k else None
        rows.append((t, sym, r3, r2, r1, fwd1, up1, dn1, fwd4))
json.dump(rows, open("rows.json", "w"))
ts = sorted({r[0] for r in rows})
print("veri:", time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts[0]/1000)), "→", time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts[-1]/1000)), "UTC,", len(uni), "coin,", len(rows), "coin-saat")
mkt = {}
for r in rows: mkt.setdefault(r[0], []).append(r[5])
mkt = {t: st.mean(v) for t, v in mkt.items()}
def rep(name, sel):
    n = len(sel)
    if not n: print(name, "yok"); return
    f = [r[5] for r in sel]; ex_ = [r[5] - mkt[r[0]] for r in sel]
    f4 = [r[8] for r in sel if r[8] is not None]
    hours = len({r[0] for r in sel})
    print(f"{name:34s} n={n:5d} (farklı saat {hours:4d})  sonraki1sa ort {100*st.mean(f):+.3f}%  ortanca {100*st.median(f):+.3f}%  "
          f"artı payı {100*sum(x>0 for x in f)/n:4.1f}%  aynı saatin ort.'dan fark {100*st.mean(ex_):+.3f}%  "
          f"sonraki4sa ort {100*st.mean(f4):+.3f}%  1sa içi ort. en yüksek {100*st.mean(r[6] for r in sel):+.2f}% en düşük {100*st.mean(r[7] for r in sel):+.2f}%  "
          f"≥+0,07% {100*sum(x>=0.0007 for x in f)/n:4.1f}%")
rep("hepsi (rastgele coin-saat)", rows)
rep("son 3 saat hep artı", [r for r in rows if r[2] > 0 and r[3] > 0 and r[4] > 0])
rep("son 3 saat artı VE hızlanan", [r for r in rows if r[2] > 0 and r[3] > r[2] and r[4] > r[3]])
rep("  + son saat ≥ %1", [r for r in rows if r[2] > 0 and r[3] > r[2] and r[4] > r[3] and r[4] >= 0.01])
rep("son 3 saat hep eksi (karşılaştırma)", [r for r in rows if r[2] < 0 and r[3] < 0 and r[4] < 0])
