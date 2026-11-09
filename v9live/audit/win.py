# Bağımsız: Binance fapi 1h mumları, 30 coin, son 15 gün. Kural: art arda 3 pencere, hepsi artı ve her biri öncekinden hızlı.
import json, sys, time, urllib.request, statistics as st
from concurrent.futures import ThreadPoolExecutor
H = 3600_000
uni = json.load(open(sys.argv[1]))
end = (int(time.time() * 1000) // H) * H; start = end - 15 * 24 * H
def kl(sym):
    out, s = [], start
    while s < end:
        d = json.load(urllib.request.urlopen(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=1h&startTime={s}&endTime={end-1}&limit=1500", timeout=20))
        if not d: break
        out += d; s = int(d[-1][0]) + H
    return sym, {int(x[0]) + H: float(x[4]) for x in out}   # kapanış anı → kapanış fiyatı
with ThreadPoolExecutor(8) as ex: K = dict(ex.map(kl, uni))
for w in (1, 2, 3, 4, 6):
    allf, sel, mk = [], [], {}
    for sym, c in K.items():
        for t in c:
            need = [t - i * w * H for i in range(4)]
            if not all(x in c for x in need) or (t + w * H) not in c or (t + H) not in c: continue
            r = [c[need[i]] / c[need[i + 1]] - 1 for i in range(3)]       # r[0] en yeni pencere
            f1 = c[t + H] / c[t] - 1; fw = c[t + w * H] / c[t] - 1
            allf.append((t, f1, fw)); mk.setdefault(t, []).append(f1)
            if r[2] > 0 and r[1] > r[2] and r[0] > r[1]: sel.append((t, f1, fw))
    mk = {t: st.mean(v) for t, v in mk.items()}
    n = len(sel)
    print(f"pencere {w} sa: sinyal {n:4d} (farklı saat {len({s[0] for s in sel}):3d}) | sonraki 1 sa ort {100*st.mean(s[1] for s in sel):+.3f}% "
          f"artı payı {100*sum(s[1]>0 for s in sel)/n:4.1f}% | rastgeleden fark {100*st.mean(s[1]-mk[s[0]] for s in sel):+.3f}% "
          f"| sonraki {w} sa ort {100*st.mean(s[2] for s in sel):+.3f}% (rastgele {100*st.mean(a[2] for a in allf):+.3f}%)")
