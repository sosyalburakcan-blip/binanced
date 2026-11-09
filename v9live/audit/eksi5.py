# Bugünkü büyük (≥1.000 $) işlemler: demo borsanın işlem-işlem fiyatıyla (aggTrades) fiyat kârı/zararı = adet × (fiyat − giriş).
# −5 $'ın altına inenler, ne kadar kaldı, sonunda ne oldu; "N sn −5 $ altında kalırsa piyasadan sat" kuralı ne verirdi.
import json, sqlite3, time, requests, pandas as pd
DEMO = 'https://demo-fapi.binance.com'
S = requests.Session()
db = sqlite3.connect('/root/binanced/v9live/live.db')
ms = lambda s: int(pd.Timestamp(s).value // 10**6)
tr = pd.read_sql("select sym, fill, exit, entry, qty, cost, pnl, reason from trades where cost >= 1000", db)
rows = [dict(sym=r.sym, a=ms(r.fill), b=ms(r.exit), entry=r.entry, qty=r.qty, pnl=r.pnl, reason=r.reason, open=False) for r in tr.itertuples()]
now = int(time.time() * 1000)
for p in json.load(open('/root/binanced/v9live/state.json')):
    if p['status'] == 'open' and p['fill_ms'] and p['filled_qty'] * p['entry'] >= 1000:
        rows.append(dict(sym=p['sym'], a=p['fill_ms'], b=now, entry=p['entry'], qty=p['filled_qty'], pnl=None, reason='AÇIK', open=True))
def agg(sym, a, b):
    out, k = [], S.get(DEMO + '/fapi/v1/aggTrades', params=dict(symbol=sym, startTime=a, endTime=min(b, a + 3_599_000), limit=1000), timeout=15).json()
    while k:
        out += [(int(x['T']), float(x['p'])) for x in k if int(x['T']) <= b]
        if int(k[-1]['T']) >= b or len(k) < 1000: 
            if int(k[-1]['T']) < b and len(k) < 1000 and int(k[-1]['T']) < a + 3_599_000: break
            if int(k[-1]['T']) >= b: break
        k = S.get(DEMO + '/fapi/v1/aggTrades', params=dict(symbol=sym, fromId=int(k[-1]['a']) + 1, limit=1000), timeout=15).json()
        time.sleep(0.1)
    return out
TAKER, MAKER = 0.0005, 0.0002
res = []
for r in rows:
    pts = agg(r['sym'], r['a'], r['b'])
    if not pts: continue
    pl = [(t, r['qty'] * (p - r['entry'])) for t, p in pts]
    mn = min(pl, key=lambda x: x[1])
    # −5 $ altı dönemler
    eps, cur = [], None
    for t, v in pl:
        if v <= -5 and cur is None: cur = t
        if v > -5 and cur is not None: eps.append((cur, t)); cur = None
    if cur is not None: eps.append((cur, pl[-1][0]))
    sim = {}
    for N in (0, 10, 30, 60):
        hit = next(((s, e) for s, e in eps if e - s >= N * 1000), None)
        if hit:
            tx = hit[0] + N * 1000
            px = next(p for t, p in pts if t >= tx) if any(t >= tx for t, _ in pts) else pts[-1][1]
            sim[N] = r['qty'] * (px - r['entry']) - r['qty'] * r['entry'] * MAKER - r['qty'] * px * TAKER
        else:
            sim[N] = None
    res.append(dict(coin=r['sym'][:-4], giris=pd.Timestamp(r['a'], unit='ms').strftime('%H:%M'), sure_dk=round((r['b'] - r['a']) / 60000),
                    sonuc=r['reason'], net=None if r['pnl'] is None else round(r['pnl'], 2),
                    en_dusuk=round(mn[1], 2), en_dusuk_dk=round((mn[0] - r['a']) / 60000, 1),
                    eksi5_kez=len(eps), eksi5_toplam_sn=round(sum(e - s for s, e in eps) / 1000), eksi5_en_uzun_sn=round(max([e - s for s, e in eps], default=0) / 1000),
                    **{f'kural_{N}sn': None if sim[N] is None else round(sim[N], 2) for N in sim}, n_islem=len(pts)))
df = pd.DataFrame(res)
pd.set_option('display.width', 250)
print(df.to_string(index=False))
df.to_csv('/root/binanced/v9live/audit/eksi5_out.csv', index=False)
