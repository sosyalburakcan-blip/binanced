"""Demo'da verdiğimiz emirler GERÇEK piyasada dolar mıydı? (bot kodunu içe aktarmaz)
Kaynaklar: demo emirlerimiz = demo-fapi /fapi/v1/allOrders (imzalı GET); gerçek defter = v9live/book arşivi
(fapi.binance.com /fapi/v1/depth?limit=1000 yanıtı bayt bayt, dakikada bir); gerçek işlemler = fapi.binance.com
/fapi/v1/aggTrades. Kuyruk kuralı (kötü taraf): defterde bizim fiyatımızda görünen miktarın HEPSİ önümüzde, hiçbiri
iptal etmiyor; bizim fiyattan satıcı (taker) işlemi önce onları, sonra bizi doldurur; fiyatımızın ALTINDA işlem
olursa seviye bitmiş demektir → tamamen dolduk. Bot kuralı: alış = gerçek en iyi alış fiyatı; 30 sn'den sonra
alış fiyatı yükseldiyse yeni fiyata taşı (biz yeni defter görüntüsünde, ≤60 sn gecikmeli görüyoruz); karardan
15 dk sonra dolmayan kısım iptal.
    /root/binanced/.venv/bin/python /root/binanced/v9live/audit/real_fill_check.py
"""
import json, lzma, sqlite3, sys, time
from collections import defaultdict
from pathlib import Path
import requests
sys.path.insert(0, "/root/binanced/src")
from trend.live.testnet import SignedRest, read_env  # yalnız imzalı HTTP istemcisi

REAL = "https://fapi.binance.com"
BOOK = Path("/root/binanced/v9live/book/2026-11-06.db")
SYMS = ["NEARUSDT", "ONDOUSDT", "1000PEPEUSDT", "TAOUSDT", "SANDUSDT", "WLDUSDT", "HYPEUSDT", "STRKUSDT",
        "SOLUSDT", "QNTUSDT", "ZECUSDT", "ENAUSDT"]
_last = [0.0]


def pub(path, **params):
    """Gerçek piyasa, herkese açık. Botla aynı IP: dakikalık ağırlık 900'ü geçerse dakika dolana kadar bekle."""
    time.sleep(max(0.0, 0.35 - (time.time() - _last[0])))
    r = requests.get(REAL + path, params=params, timeout=15)
    _last[0] = time.time()
    r.raise_for_status()
    if int(r.headers.get("X-MBX-USED-WEIGHT-1M", 0)) > 900:
        time.sleep(61 - time.time() % 60)
    return r.json()


def book(db, sym, a, b):
    out = []
    for E, raw in db.execute("select T, raw from book where sym=? and T between ? and ? order by T", (sym, a, b)):
        d = json.loads(lzma.decompress(raw))
        out.append((E, [(float(p), float(q)) for p, q in d["bids"]], [(float(p), float(q)) for p, q in d["asks"]]))
    return out


def trades(sym, a, b):
    """a..b arası tüm gerçek aggTrades (sırayla)."""
    out, start = [], a
    while True:
        x = pub("/fapi/v1/aggTrades", symbol=sym, startTime=start, endTime=min(b, start + 3_599_000), limit=1000)
        out += [t for t in x if not out or t["a"] > out[-1]["a"]]
        if len(x) < 1000:
            if start + 3_599_000 >= b:
                return out
            start += 3_599_000
        else:
            start = x[-1]["T"]


def lvl(side, px):
    return sum(q for p, q in side if p == px)


def sim_buy(sym, snaps, trs, t0, t_end, qty):
    """Emir, demo emrinden SONRAKİ ilk gerçek defter görüntüsü anında (T) verilmiş sayılır: o anki en iyi alış ve
    önündeki miktar kesin bilinir (eski görüntüyle 'anında doldu' yanılgısı olmasın)."""
    k = next((i for i, s in enumerate(snaps) if s[0] >= t0), None)
    if k is None or snaps[k][0] > t_end:
        return None
    E, bids, asks = snaps[k]
    P, Q = bids[0][0], bids[0][1]
    res = dict(delay_s=(E - t0) / 1000, P0=P, Q0=Q, ask0=asks[0][0], reprices=0)
    placed, filled, val, t_first, t_done, si = E, 0.0, 0.0, None, None, k + 1
    for t in trs:
        if t["T"] <= E:
            continue
        if t["T"] > t_end:
            break
        while si < len(snaps) and snaps[si][0] <= t["T"]:      # yeni defter görüntüsü: alış yükseldiyse taşı
            nb = snaps[si][1][0]
            if nb[0] > P and snaps[si][0] - placed >= 30_000 and filled < qty:
                P, Q, placed = nb[0], nb[1], snaps[si][0]
                res["reprices"] += 1
            si += 1
        if not t["m"]:                                          # alıcı taker: bizi doldurmaz
            continue
        p, q = float(t["p"]), float(t["q"])
        if p < P:
            x = qty - filled
        elif p == P:
            use = min(Q, q); Q -= use; x = min(q - use, qty - filled)
        else:
            continue
        if x > 0:
            filled += x; val += x * P
            t_first = t_first or t["T"]
            if filled >= qty - 1e-12:
                t_done = t["T"]
                break
    res.update(filled=filled, avg=val / filled if filled else None, t_first=t_first, t_done=t_done, P_last=P)
    return res


def sim_sell_limit(snaps, trs, t0, t_end, qty, P):
    E, bids, asks = next(s for s in snaps if s[0] >= t0)       # girişten sonraki ilk gerçek görüntü
    Q = lvl(asks, P)
    Q0, filled, t_done = Q, 0.0, None
    for t in trs:
        if t["T"] <= E or t["m"]:
            continue
        if t["T"] > t_end:
            break
        p, q = float(t["p"]), float(t["q"])
        if p > P:
            x = qty - filled
        elif p == P:
            use = min(Q, q); Q -= use; x = min(q - use, qty - filled)
        else:
            continue
        filled += max(0, x)
        if filled >= qty - 1e-12:
            t_done = t["T"]; break
    hi = max((float(t["p"]) for t in trs if t0 <= t["T"] <= t_end), default=None)
    return dict(Q0=Q0, filled=filled, t_done=t_done, best_ask=asks[0][0], hi=hi)


def walk(side, qty):
    left, val, n = qty, 0.0, 0
    for p, q in side:
        x = min(left, q); val += x * p; left -= x; n += 1
        if left <= 1e-12:
            break
    return (val / (qty - left) if qty > left else None), n, left


def hm(ms):
    return time.strftime("%H:%M:%S", time.gmtime(ms / 1000)) if ms else "-"


def main():
    env = read_env(Path("/root/binanced/.env.testnet"))
    demo = SignedRest("https://demo-fapi.binance.com", env["BINANCE_TESTNET_API_KEY"],
                      private_key_path=env["BINANCE_TESTNET_PRIVATE_KEY_PATH"])
    db = sqlite3.connect(f"file:{BOOK}?mode=ro", uri=True)
    a0 = db.execute("select min(E) from book").fetchone()[0]
    now = int(time.time() * 1000)
    ent, mx, tp = [], [], []
    for sym in SYMS:
        os_ = demo.request("GET", "/fapi/v1/allOrders", {"symbol": sym, "startTime": a0, "limit": 1000})
        g = defaultdict(list)
        for o in os_:
            c = o["clientOrderId"]
            if c.startswith("v9d-en-"):
                g[o["time"] // 3_600_000].append(o)
            elif c.startswith("v9d-mx-") and float(o["executedQty"]) > 0:
                mx.append((sym, o))
            elif c.startswith("v9d-tp-") and o["status"] == "FILLED":
                tp.append((sym, o))
        for h, L in g.items():
            L.sort(key=lambda o: o["time"])
            fq = sum(float(o["executedQty"]) for o in L)
            if fq <= 0:
                continue
            fv = sum(float(o["executedQty"]) * float(o["avgPrice"]) for o in L)
            ent.append(dict(sym=sym, dec=h * 3_600_000, t0=L[0]["time"], qty=float(L[0]["origQty"]), n=len(L),
                            demo_px=fv / fq, demo_fill=max(o["updateTime"] for o in L if float(o["executedQty"]) > 0),
                            demo_first_px=float(L[0]["price"])))
    print("== GİRİŞLER (gerçek defter + gerçek işlemlerle, kötü taraf kuyruk)")
    sims = {}
    for e in sorted(ent, key=lambda e: e["t0"]):
        t_end = e["dec"] + 900_000
        snaps = book(db, e["sym"], e["t0"] - 120_000, t_end)
        trs = trades(e["sym"], e["t0"], min(t_end, now))
        r = sim_buy(e["sym"], snaps, trs, e["t0"], t_end, e["qty"])
        if r is None:
            print(e["sym"], "defter görüntüsü yok"); continue
        sims[(e["sym"], e["dec"])] = (e, r, trs)
        usd = e["qty"] * r["P0"]
        print(f"{e['sym']:13s} emir {hm(e['t0'])} {usd:6.0f}$ | gerçek alış {r['P0']:.6g} (emir +{r['delay_s']:.0f} sn sonraki görüntüde), "
              f"önümüzde {r['Q0'] * r['P0']:9.0f}$ = {r['Q0'] * r['P0'] / usd:6.1f}× emrimiz | "
              f"dolan %{100 * r['filled'] / e['qty']:.0f}, ilk {hm(r['t_first'])}, tam {hm(r['t_done'])}, taşıma {r['reprices']} | "
              f"demo: {hm(e['demo_fill'])} @ {e['demo_px']:.6g} ({e['n']} emir); gerçek ort {r['avg'] or float('nan'):.6g} "
              f"→ fark {((r['avg'] / e['demo_px'] - 1) * 1e4) if r['avg'] else float('nan'):+.1f} bps (+ = gerçekte pahalı)")
    print("\n== KÂR AL (limit satış) — gerçek giriş fiyatından aynı uzaklıkta")
    for sym, o in tp:
        k = next((k for k in sims if k[0] == sym and k[1] < o["time"]), None)
        e, r, _ = sims[k]
        if not r["avg"]:
            print(sym, "gerçekte giriş dolmadı"); continue
        ratio = float(o["price"]) / e["demo_px"]
        tick = next(float(f["tickSize"]) for s in pub("/fapi/v1/exchangeInfo")["symbols"] if s["symbol"] == sym
                    for f in s["filters"] if f["filterType"] == "PRICE_FILTER")
        P = round(-(-r["avg"] * ratio // tick) * tick, 10)
        t0 = r["t_done"] or r["t_first"]
        t_end = (e["dec"] // 3_600_000 + 1) * 3_600_000 + 10_000          # sonraki saatlik kontrol
        snaps = book(db, sym, t0, t_end)
        trs = trades(sym, t0, min(t_end, now))
        s = sim_sell_limit(snaps, trs, t0, min(t_end, now), r["filled"], P)
        print(f"{sym}: demo kâr al {o['price']} doldu {hm(o['updateTime'])} | gerçek kâr al {P:.6g} (en iyi satış {s['best_ask']:.6g}), "
              f"önümüzde {s['Q0'] * P:.0f}$ | dolan %{100 * s['filled'] / r['filled']:.0f}, tam {hm(s['t_done'])}, "
              f"o sürede en yüksek gerçek fiyat {s['hi']}")
    print("\n== PİYASA SATIŞLARI (saatlik çıkış / elle) — gerçek defterde ne kadar kayardı")
    for sym, o in sorted(mx, key=lambda x: x[1]["updateTime"]):
        snaps = book(db, sym, o["updateTime"] - 90_000, o["updateTime"])
        if not snaps:
            print(sym, "görüntü yok"); continue
        E, bids, asks = snaps[-1]
        q = float(o["executedQty"]); avg, n, left = walk(bids, q)
        print(f"{sym:13s} {hm(o['updateTime'])} {q * bids[0][0]:6.0f}$ | gerçek en iyi alış {bids[0][0]:.6g} ({(o['updateTime'] - E) / 1000:.0f} sn eski), "
              f"o fiyatta {bids[0][1] * bids[0][0]:.0f}$ | {n} basamak, ort {avg:.6g}, kayma {(1 - avg / bids[0][0]) * 1e4:.1f} bps "
              f"= {(bids[0][0] - avg) * q:.2f} $ | demo ort {float(o['avgPrice']):.6g} ({(float(o['avgPrice']) / avg - 1) * 1e4:+.1f} bps gerçeğe göre)")


if __name__ == "__main__":
    main()
