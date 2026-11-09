# Bağımsız: bugün kapanan her işlemin kâr/zararını borsa dolumlarından (userTrades + income) yeniden kur; botun trades tablosuyla kıyasla.
# Açık pozisyonlarda: kâr al fiyatı formülü, acil stop seviyesi, emir adetleri borsayla.
import sys, json, math, sqlite3, time, pandas as pd
sys.path.insert(0, '/root/binanced/v9live/audit'); from demo_sign import g
db = sqlite3.connect('/root/binanced/v9live/live.db')
tr = pd.read_sql("select rowid, sym, fill, exit, entry, qty, cost, value, fees, funding, pnl, reason, lev from trades", db)
day0 = int(pd.Timestamp('2026-11-06 06:00').value // 10**6)
bad = 0
other = []                       # borsada olup botun kaydında olmayan turlar (bot hatası sayılmaz, ayrıca listelenir)
for sym in sorted(tr.sym.unique()):
    fills = []
    start = day0
    while True:
        k = g('/fapi/v1/userTrades', symbol=sym, startTime=start, limit=1000)
        fills += k
        if len(k) < 1000: break
        start = int(k[-1]['time']) + 1
    fills.sort(key=lambda x: (int(x['time']), int(x['id'])))
    inc = g('/fapi/v1/income', symbol=sym, incomeType='FUNDING_FEE', startTime=day0, limit=1000)
    # pozisyonu 0 → >0 → 0 olarak yürüt
    trips, pos, cur = [], 0.0, None
    for x in fills:
        q = float(x['qty']) * (1 if x['side'] == 'BUY' else -1)
        if cur is None and abs(pos) < 1e-12:
            cur = dict(a=int(x['time']), buy=0.0, sell=0.0, fee=0.0, n=0)
        cur['buy' if q > 0 else 'sell'] += float(x['quoteQty']); cur['fee'] += float(x['commission']); cur['n'] += 1
        pos += q
        if abs(pos) < 1e-9:
            cur['b'] = int(x['time']); trips.append(cur); cur = None; pos = 0.0
    for c in trips:
        c['fund'] = sum(float(i['income']) for i in inc if c['a'] <= int(i['time']) <= c['b'])
        c['pnl'] = c['sell'] - c['buy'] - c['fee'] + c['fund']
    mine = tr[tr.sym == sym].sort_values('fill')
    # 07.11: sıraya göre değil ZAMANA göre eşleştir (borsada botun kaydında olmayan turlar var: 06.11 kurulum denemeleri,
    # kullanıcı isteğiyle kayıttan silinen işlemler); her bot işlemi, ilk dolumu bot dolumuna en yakın (≤ 120 sn) tura.
    pairs, used = [], set()
    for _, r in mine.iterrows():
        f_ms = int(pd.Timestamp(r.fill).value // 10**6)
        cand = [(abs(c['a'] - f_ms), i) for i, c in enumerate(trips) if i not in used and abs(c['a'] - f_ms) <= 120_000]
        if not cand:
            print(f"!! {sym} {r.fill[5:16]}: botun işlemi borsada bulunamadı"); bad += 1
            continue
        i = min(cand)[1]; used.add(i); pairs.append((r, trips[i]))
    for i, c in enumerate(trips):
        if i not in used:
            other.append(f"{sym} {pd.Timestamp(c['a'], unit='ms').strftime('%m-%d %H:%M')} (alış {c['buy']:.2f} $, net {c['pnl']:+.3f} $)")
    for r, c in pairs:
        d = r.pnl - c['pnl']
        flag = '' if abs(d) < 0.01 else '  <-- FARK'
        bad += bool(flag)
        print(f"{sym:13s} {r.fill[11:16]} {r.reason:17s} bot net {r.pnl:+8.3f}  borsa {c['pnl']:+8.3f}  fark {d:+.4f}  "
              f"(alış {c['buy']:.2f}/{r.cost:.2f}, satış {c['sell']:.2f}/{r.value:.2f}, ücret {c['fee']:.3f}/{r.fees:.3f}, fon {c['fund']:+.3f}, dolum {c['n']}){flag}")
print(f"botun kaydında olmayan borsa turları ({len(other)}):", "; ".join(other) or "yok")
print("kapanan işlemlerde fark:", bad)
# açık pozisyonlar
st = json.load(open('/root/binanced/v9live/state.json'))
info = {s['symbol']: {f['filterType']: f for f in s['filters']} for s in g('/fapi/v1/exchangeInfo')['symbols']} if False else None
ex = requests = None
import requests as rq
ei = rq.get('https://demo-fapi.binance.com/fapi/v1/exchangeInfo', timeout=15).json()
tick = {s['symbol']: float(next(f for f in s['filters'] if f['filterType'] == 'PRICE_FILTER')['tickSize']) for s in ei['symbols']}
oo = g('/fapi/v1/openOrders'); ao = g('/fapi/v1/openAlgoOrders')
pr = {x['symbol']: x for x in g('/fapi/v2/positionRisk') if float(x['positionAmt']) != 0}
MAKER = 0.0002
for p in st:
    if p['status'] != 'open': continue
    s = p['sym']; t = tick[s]; x = pr.get(s)
    e, q = float(x['entryPrice']), float(x['positionAmt'])
    short = q < 0                                     # 08.11 Değ. 30: short (adet eksi) → aynası
    q = abs(q)
    if short:
        want_tp = math.floor(((e * (1 - MAKER) - 5.0 / q) / (1 + MAKER)) / t + 1e-9) * t
        six = math.ceil(e * 1.06 / t - 1e-9) * t
        want_es = min(math.floor((e + 5.0 / q) / t + 1e-9) * t, six) if q * e >= 1000 else six
    else:
        want_tp = math.ceil(((5.0 / q + e * (1 + MAKER)) / (1 - MAKER)) / t - 1e-9) * t
        six = math.floor(e * 0.94 / t + 1e-9) * t
        want_es = max(math.ceil((e - 5.0 / q) / t - 1e-9) * t, six) if q * e >= 1000 else six   # 06.11 ~14:05: −5 $ zarar stopu
    tps = [o for o in oo if o['symbol'] == s and o['side'] == ('BUY' if short else 'SELL') and o['reduceOnly']]
    ess = [o for o in ao if o['symbol'] == s]
    ok_tp = len(tps) == 1 and abs(float(tps[0]['price']) - want_tp) < t / 2 and abs(float(tps[0]['origQty']) - q) < 1e-9
    ok_es = len(ess) == 1 and abs(float(ess[0]['triggerPrice']) - want_es) < t / 2
    net_at_tp = (q * e * (1 - MAKER) - q * want_tp * (1 + MAKER)) if short else (q * want_tp * (1 - MAKER) - q * e * (1 + MAKER))
    liq = float(x['liquidationPrice'])
    stop_first = (liq > want_es) if short else (liq < want_es)
    print(f"{s:13s} {'SHORT' if short else 'LONG'} adet {q:g} giriş {e:.6g} | kâr al borsa {tps[0]['price'] if tps else '-'} formül {want_tp:.6g} {'✓' if ok_tp else '✗'} "
          f"(net {net_at_tp:+.2f} $) | acil stop borsa {ess[0]['triggerPrice'] if ess else '-'} formül {want_es:.6g} {'✓' if ok_es else '✗'} "
          f"| tasfiye {liq:.6g} {'(stop önce ✓)' if stop_first else '(TASFİYE ÖNCE ✗)'}")
