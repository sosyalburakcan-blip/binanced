# Bağımsız bakış: bot kodunu içe aktarmaz, önceki sonuç/parametre kullanmaz.
# Veri: Binance USDⓈ-M herkese açık uç noktaları (fapi.binance.com): 1h mumlar + fonlama geçmişi. Son 12 ay.
# Kural (pencere w saat): art arda 3 pencere, hepsi artı ve her biri öncekinden hızlı.
#   r1 = son pencere, r2 = ondan önceki, r3 = en eski.  Şart: r3 > 0, r2 > r3, r1 > r2.
# Giriş: sinyal mumunun kapanış fiyatı (gerçekte biraz sonra girilir → kayma yok sayılıyor, rapora yazılır).
# Çıkış: w saat sonra kapanış. Fonlama: (t, t+w] içindeki fonlama anları, alıcı pozitif oranı öder.
# Kullanım: python win_long.py <evren.json> <önbellek.json>
import json, os, sys, time, urllib.request
import numpy as np, pandas as pd

H = 3600_000
uni = json.load(open(sys.argv[1])); cache = sys.argv[2]
END = (int(time.time() * 1000) // H) * H if not os.path.exists(cache) else json.load(open(cache))["end"]
START = END - (365 + 5) * 24 * H

def get(u):
    for i in range(6):
        try:
            r = urllib.request.urlopen(u, timeout=30)
            w = int(r.headers.get("X-MBX-USED-WEIGHT-1M") or 0)
            d = json.load(r)
            if w > 1000: time.sleep(20)            # botla aynı IP: ağırlık sınırına yaklaşma (2400/dk)
            return d
        except urllib.error.HTTPError as e:
            if e.code in (418, 429): raise SystemExit(f"Binance {e.code}: durdum, IP korunuyor")
            err = e
        except Exception as e:
            err = e
        time.sleep(3 * (i + 1))
    raise err

if os.path.exists(cache):
    D = json.load(open(cache))
else:
    D = {"end": END, "kl": {}, "fr": {}}
    for sym in uni:
        out, s = [], START
        while s < END:
            d = get(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=1h&startTime={s}&endTime={END-1}&limit=1000")
            if not d: break
            out += [[int(x[0]), float(x[4])] for x in d]; s = int(d[-1][0]) + H
        D["kl"][sym] = out
        fo, s = [], START
        while s < END:
            d = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&startTime={s}&endTime={END-1}&limit=1000")
            if not d: break
            fo += [[int(x["fundingTime"]), float(x["fundingRate"])] for x in d]; s = int(d[-1]["fundingTime"]) + 1
            if len(d) < 1000: break
        D["fr"][sym] = fo
        print(sym, len(out), "mum", len(fo), "fonlama", flush=True)
    json.dump(D, open(cache, "w"))

idx = np.arange(START + H, END + H, H)                       # kapanış anları (mum açılışı + 1 sa)
C = pd.DataFrame({s: pd.Series({o + H: c for o, c in v}) for s, v in D["kl"].items()}).reindex(idx)
F = pd.DataFrame(0.0, index=idx, columns=C.columns)
for s, v in D["fr"].items():
    for ft, rate in v:
        t = ((ft + H // 2) // H) * H                          # fonlama anı → en yakın saat
        if t in F.index: F.at[t, s] += rate
CF = F.cumsum()

P12 = END - 365 * 24 * H                                      # son 12 ay
T = C.index.values
print(f"veri: {time.strftime('%Y-%m-%d %H:%M', time.gmtime(P12/1000))} → {time.strftime('%Y-%m-%d %H:%M', time.gmtime(END/1000))} UTC, {C.shape[1]} coin")
print("coin başına ilk mum (geç listelenenler):", {s: time.strftime('%Y-%m-%d', time.gmtime(C[s].first_valid_index()/1000)) for s in C if C[s].first_valid_index() > P12})

def spear(a, b):
    m = a.notna() & b.notna()
    return a[m].rank().corr(b[m].rank()) if m.sum() > 30 else np.nan

FEE = 0.0010   # alış + satış piyasa emri, taker %0,05 × 2 (kötü taraf; kayma hariç)
rows = []
for w in (1, 2, 3, 4, 6, 12, 24):
    r1 = C / C.shift(w) - 1; r2 = C.shift(w) / C.shift(2 * w) - 1; r3 = C.shift(2 * w) / C.shift(3 * w) - 1
    fw = C.shift(-w) / C - 1
    fund = CF.shift(-w) - CF
    ok = r1.notna() & r2.notna() & r3.notna() & fw.notna()
    fwv = fw.where(ok)
    adj = fwv.sub(fwv.mean(axis=1), axis=0)                   # aynı andaki tüm coinlerin ortalamasından fark
    sig = ok & (r3 > 0) & (r2 > r3) & (r1 > r2)
    start_run = sig & ~sig.shift(1, fill_value=False)         # aynı coinde ardışık sinyallerin ilki = olay
    for name, lo, hi in (("son 15 gün", END - 15 * 24 * H, END), ("son 12 ay", P12, END),
                         ("12 ay: 1. çeyrek", P12, P12 + 91 * 24 * H), ("12 ay: 2. çeyrek", P12 + 91 * 24 * H, P12 + 182 * 24 * H),
                         ("12 ay: 3. çeyrek", P12 + 182 * 24 * H, P12 + 273 * 24 * H), ("12 ay: 4. çeyrek", P12 + 273 * 24 * H, END)):
        tm = (T > lo) & (T <= hi)
        S = sig[tm]; st = S.stack(); st = st[st]
        if not len(st): rows.append(dict(w=w, dönem=name, sinyal=0)); continue
        g = fw[tm].stack()[st.index]; a = adj[tm].stack()[st.index]; fu = fund[tm].stack()[st.index]
        allg = fwv[tm].stack()
        net = g - fu - FEE
        # belirsizlik: hafta blokları yeniden örnekleme (çakışan pencereler yüzünden tek tek sayılmaz)
        wk = (st.index.get_level_values(0) // (7 * 24 * H)).values
        u, inv = np.unique(wk, return_inverse=True); rng = np.random.default_rng(0)
        sums = np.bincount(inv, weights=a.values); cnts = np.bincount(inv)
        pick = rng.integers(0, len(u), (2000, len(u)))
        bs = sums[pick].sum(1) / cnts[pick].sum(1)
        lo95, hi95 = np.percentile(bs, [2.5, 97.5])
        rows.append(dict(w=w, dönem=name, sinyal=len(st), olay=int(start_run[tm].values.sum()), hafta=len(u),
                         ort=100 * g.mean(), artı=100 * (g > 0).mean(), herkes=100 * allg.mean(),
                         fark=100 * a.mean(), fark95=f"[{100*lo95:+.2f}, {100*hi95:+.2f}]",
                         fonlama=100 * fu.mean(), net=100 * net.mean(),
                         sp_yuk=spear(r1[tm].where(ok[tm]).stack(), fw[tm].stack()),
                         sp_ivme=spear((r1 - r2)[tm].where(ok[tm]).stack(), fw[tm].stack())))
R = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(R.round(3).to_string(index=False))
R.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "win_long_out.csv"), index=False)

# Çapraz kontrol: önceki win.py ile aynı 15 gün ve aynı sınırlar (son = 2026-11-06 09:00 UTC) → aynı sinyal sayısı çıkmalı
E0 = int(pd.Timestamp("2026-11-06 09:00", tz="UTC").timestamp() * 1000); S0 = E0 - 15 * 24 * H
for w in (1, 3):
    r1 = C / C.shift(w) - 1; r2 = C.shift(w) / C.shift(2 * w) - 1; r3 = C.shift(2 * w) / C.shift(3 * w) - 1
    tm = (T - 3 * w * H >= S0 + H) & (T + w * H <= E0) & (T + H <= E0)
    s = ((r3 > 0) & (r2 > r3) & (r1 > r2))[tm].values.sum()
    f1 = (C.shift(-1) / C - 1)[tm][((r3 > 0) & (r2 > r3) & (r1 > r2))[tm]].stack().mean()
    print(f"çapraz kontrol w={w}: sinyal {s}, sonraki 1 sa ort {100*f1:+.3f}%")
