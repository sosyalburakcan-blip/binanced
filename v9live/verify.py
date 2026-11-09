"""v9 demo botunun BAĞIMSIZ denetimi (bot.py'yi içe aktarmaz, aynı kodu kullanmaz).

    /root/binanced/.venv/bin/python v9live/verify.py features [DAKİKA_MS] # o dakikanın ölçümlerini Binance'ten yeniden hesapla
    /root/binanced/.venv/bin/python v9live/verify.py depth                # defter görüntüsü ±%1'e uzanıyor mu
    /root/binanced/.venv/bin/python v9live/verify.py book [DAKİKA]        # tam defter arşivi (varsayılan son 60 dk)

features: botun live.db/scores tablosuna yazdığı değerleri, Binance gerçek piyasa API'sinden sıfırdan hesaplanan
değerlerle karşılaştırır (R30, MKT_30, MKT_UP, MKT_5, MKT_PEAK, MKT_TOP, MKT_JUMP, LC, r_t, r_prev, ACC_1, TAKER_1, SMOOTH_4, OI_1, TICK_REL;
Değ. 30: MKT_DN, MKT_TROUGH, LC_DN, COIN_J_UP, COIN_J_DN, karar yönü LONG/SHORT ve short puanı). IMB1_1/BIDSHARE_1 geçmişe dönük
alınamaz (Binance geçmiş defter vermez); onlar için `depth` kontrolü var.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import time

import requests

REAL = "https://fapi.binance.com"
H = 3_600_000
GATE24_FROM_MS = 1793974401000   # 06.11 14:13:21 UTC yeniden başlatma: liste 24 sa artıda + şart CHG24 > 0
# 07.11 kullanıcı seçimi "Bugünün en büyük 30'u": bu andan (yeniden başlatma) itibaren '24 sa artıda' şartı yok (liste + giriş)
GATE24_TO_MS = int(os.environ.get("V9_GATE24_TO_MS", "1794025844000"))   # 07.11 04:30:44 UTC yeniden başlatma
# 07.11 kullanıcı: "ivme farkını puandan çıkar" → bu andan (yeniden başlatma) itibaren puan ACC_1'siz 6 bileşen
NOACC_FROM_MS = int(os.environ.get("V9_NOACC_FROM_MS", "1794027411000"))   # 07.11 04:56:51 UTC yeniden başlatma
# 08.11 Değişiklik 26: bu andan (yeniden başlatma) itibaren giriş şartı PİYASA son 30 dk > 0 (MKT_30 = listedeki coinlerin ham
# son 30 dk getirilerinin ortalaması) ve LC ≥ 2. Eski şartların ("son 4 sa > 0", yükseliş sinyali, Değ. 17–23) kodu silindi →
# bu andan önceki kararlarda şart denetlenmez (ölçümler ve puan denetlenir).
D26_FROM_MS = int(os.environ.get("V9_D26_FROM_MS", "1794105790000"))   # 08.11 02:43:10 UTC = 05:43 TR
# 08.11 Değişiklik 27: bu andan (yeniden başlatma) itibaren piyasa şartı = son 30 dk ort. ≥ +%0,10, R30 > 0 coin ≥ 20,
# son 5 dk (ortalama yol idx(t) − idx(t−5)) > 0, son 30 dk tepesine uzaklık (idx(t) − max idx) ≥ −%0,10; ve LC ≥ 2.
D27_FROM_MS = int(os.environ.get("V9_D27_FROM_MS", "1794111396000"))   # 08.11 04:16:36 UTC = 07:16 TR
MKT_MIN, MKT_UP_MIN, MKT_PEAK_MAX = 0.001, 20, 0.001
# 08.11 Değişiklik 28: bu andan itibaren ek şart son 2 dk (idx(t) − idx(t−2)) ≤ 0,5 × son 30 dk ortalaması (sıçrama değil)
D28_FROM_MS = int(os.environ.get("V9_D28_FROM_MS", "1794112590000"))   # 08.11 04:36:30 UTC = 07:36 TR
MKT_JUMP_SHARE = 0.5
# 08.11 Değişiklik 30: bu andan itibaren SHORT da (aynası: son 30 dk ≤ −%0,10, R30 < 0 coin ≥ 20, son 5 dk < 0, 30 dk dibine
# uzaklık idx(t) − min idx ≤ %0,10, son 2 dk ≥ 0,5 × son 30 dk; + LC_DN ≥ 2); short puanı LC_DN, −SMOOTH_4, −TAKER_1, −IMB1_1,
# −BIDSHARE_1, OI_1 sıra yüzdeleri ortalaması. Deneme: V9_D30_FROM_MS=1.
D30_FROM_MS = int(os.environ.get("V9_D30_FROM_MS", "1794121293000"))   # 08.11 07:01:33 UTC = 10:01 TR
# 06.11 ~18:05: 5 dk'da bir karar, pencere uçları = son 5 adet 1 dk kapanışın ortalaması, giriş son 60 dk > +%0,2, liste VOL60 ≤ %2.
# Yeni kurallı satır botun kaydında "r_t_raw" anahtarıyla tanınır (eski satırlarda yok → eski tanım).
SMOOTH_N, BAND, VOL_MAX, VOL_MIN_N = 5, 0.002, 0.02, 1380
DB = os.environ.get("V9_DB", "/root/binanced/v9live/live.db")   # deneme: V9_DB=…/dry_run.db
BOOK = "/root/binanced/v9live/book"
S = requests.Session()
S.headers["User-Agent"] = "v9-verify/1.0"


def get(path, **p):
    r = S.get(REAL + path, params=p, timeout=15)
    if r.status_code in (418, 429):
        raise SystemExit(f"Binance hız sınırı {r.status_code}; dur")
    r.raise_for_status()
    time.sleep(0.15)                       # botla birlikte sınırı zorlamamak için yavaş
    return r.json()


def recompute(sym: str, t: int, smooth: bool = False) -> dict:
    """06.11 12:45'ten beri kayan pencere: t herhangi bir dakika sınırı. P[i] = t − i×60 dk anında biten 1 dk mumun
    kapanışı (1 dk mumlardan, sıfırdan). Saat başı t için eski saatlik tanımla aynı sonucu verir.
    smooth (06.11 ~18:05): P[i] = t − i×60 dk anında biten SON 5 adet 1 dk mumun kapanışlarının ortalaması."""
    m = get("/fapi/v1/klines", symbol=sym, interval="1m", startTime=t - 24 * H - 5 * 60_000, endTime=t - 1, limit=1500)
    by_open = {int(x[0]): x for x in m}
    close = lambda ts: float(by_open[ts - 60_000][4])  # noqa: E731   # ts anında biten mumun kapanışı
    if smooth:
        P = [sum(close(t - i * H - j * 60_000) for j in range(SMOOTH_N)) / SMOOTH_N for i in range(25)]
    else:
        P = [close(t - i * H) for i in range(25)]
    raw_rt = close(t) / close(t - H) - 1
    lc = 0
    for n in (2, 3, 4, 5, 6, 8, 12):
        now_up, prev_up = P[0] / P[n] - 1, P[n] / P[2 * n] - 1
        if now_up > 0 and now_up > prev_up:
            lc = n
        else:
            break
    ld = 0                                                                  # Değ. 30: aynası (düşüş, hızlanarak)
    for n in (2, 3, 4, 5, 6, 8, 12):
        now_up, prev_up = P[0] / P[n] - 1, P[n] / P[2 * n] - 1
        if now_up < 0 and now_up < prev_up:
            ld = n
        else:
            break
    out = {"LC": lc, "LC_DN": ld, "r_t": P[0] / P[1] - 1, "r_prev": P[1] / P[2] - 1}
    c61 = [close(t - H + j * 60_000) for j in range(61)]                    # Değ. 30: son 60 dk içindeki 2 dk hareketleri
    mv2 = [c61[j] / c61[j - 2] - 1 for j in range(2, 61)]
    out["COIN_J_UP"], out["COIN_J_DN"] = max(mv2), min(mv2)
    out["R30"] = close(t) / close(t - 30 * 60_000) - 1                       # Değ. 26: ham son 30 dk
    out["R_5M"] = close(t) / close(t - 5 * 60_000) - 1                       # Değ. 29: ham son 5 dk (60 dk kontrolü ek süresi)
    out["_P30"] = [close(t - 30 * 60_000 + j * 60_000) / close(t - 30 * 60_000) - 1 for j in range(31)]   # Değ. 27: yol
    out["_close_t"] = close(t)                                              # Değ. 25: TICK_REL paydası
    out["ACC_1"] = out["r_t"] - out["r_prev"]
    last60 = [by_open[t - j * 60_000] for j in range(1, 61)]                # son 60 dk
    out["TAKER_1"] = sum(float(x[10]) for x in last60) / sum(float(x[7]) for x in last60)
    # t−4 sa anındaki fiyattan t'ye kadar 240 adım (241 kapanış)
    cl = [float(by_open[t - 4 * H + j * 60_000 - 60_000][4]) for j in range(241)]
    steps = sum(abs(math.log(cl[i] / cl[i - 1])) for i in range(1, len(cl)))
    out["SMOOTH_4"] = math.log(P[0] / P[4]) / steps
    out["_n1m"] = len(cl)
    if smooth:
        out["r_t_raw"] = raw_rt
    oi = get("/futures/data/openInterestHist", symbol=sym, period="5m", startTime=t - H - 900_000, endTime=t)
    v = {int(x["timestamp"]): float(x["sumOpenInterest"]) for x in oi}       # 06.11: OI_1 = pozisyon ADEDİ değişimi
    out["_oi"] = v                         # OI_1 karşılaştırması botun kullandığı OI_TS noktasıyla yapılır (aşağıda)
    return out


def features(t: int | None) -> None:
    db = sqlite3.connect(DB)
    if t is None:
        t = db.execute("select max(ts) from scores").fetchone()[0]
    sc_cols = [r[1] for r in db.execute("pragma table_info(scores)")]
    has30 = "score_s" in sc_cols
    rows = db.execute("select sym, feats, gated, score from scores where ts = ?", (t,)).fetchall()
    side_rows = {r[0]: (r[1], r[2]) for r in db.execute("select sym, side, score_s from scores where ts = ?", (t,))} if has30 else {}
    print(f"dakika {time.strftime('%Y-%m-%d %H:%M', time.gmtime(t / 1000))} UTC, {len(rows)} coin")
    keys = ("R30", "MKT_30", "MKT_UP", "MKT_5", "MKT_PEAK", "MKT_TOP", "MKT_JUMP", "R_5M", "LC", "r_t", "r_prev", "ACC_1", "TAKER_1", "SMOOTH_4", "OI_1", "r_t_raw", "TICK_REL",
            "MKT_DN", "MKT_TROUGH", "LC_DN", "COIN_J_UP", "COIN_J_DN")
    # Değ. 25: fiyat adımı demo borsanın herkese açık exchangeInfo'sundan (botun emir verdiği borsa), sıfırdan
    ticks = {x["symbol"]: float(next(f["tickSize"] for f in x["filters"] if f["filterType"] == "PRICE_FILTER"))
             for x in S.get("https://demo-fapi.binance.com/fapi/v1/exchangeInfo", timeout=15).json()["symbols"]}
    bad, worst = [], {k: 0.0 for k in keys}
    recs_me = {}
    for sym, fj, _, _ in rows:
        b = json.loads(fj)
        recs_me[sym] = recompute(sym, t, "r_t_raw" in b)
    # Değ. 26: piyasa şartı bağımsız — bu kararın listesindeki (scores satırları) coinlerin R30 ortalaması
    r30 = [m["R30"] for m in recs_me.values()]
    mkt = sum(r30) / len(r30) if r30 else None
    # Değ. 27: genişlik, ortalama yol (t−30 … t), son 5 dk, tepeye uzaklık, en büyük tek coin katkısı — sıfırdan
    up_n = sum(1 for v in r30 if v > 0)
    idx = [sum(m["_P30"][j] for m in recs_me.values()) / len(recs_me) for j in range(31)] if recs_me else None
    mkt5 = idx[30] - idx[25] if idx else None
    peak = idx[30] - max(idx) if idx else None
    jump = idx[30] - idx[28] if idx else None                             # Değ. 28: son 2 dk
    top = max(r30, key=abs) / len(r30) if r30 else None
    dn_n = sum(1 for v in r30 if v < 0)                                   # Değ. 30
    trough = idx[30] - min(idx) if idx else None
    if D30_FROM_MS and t >= D30_FROM_MS and idx:
        my_side = ("LONG" if mkt >= MKT_MIN and up_n >= MKT_UP_MIN and mkt5 > 0 and peak >= -MKT_PEAK_MAX and jump <= MKT_JUMP_SHARE * mkt
                   else "SHORT" if mkt <= -MKT_MIN and dn_n >= MKT_UP_MIN and mkt5 < 0 and trough <= MKT_PEAK_MAX
                   and jump >= MKT_JUMP_SHARE * mkt else None)
        bot_sides = {v[0] for v in side_rows.values()}
        print(f"yön (bağımsız): {my_side}, ekside {dn_n}, dipten {trough:+.4%} | bot {bot_sides}")
        if bot_sides != {my_side}:
            bad_side = [("YÖN", "bot", sorted(map(str, bot_sides)), my_side)]
        else:
            bad_side = []
    else:
        my_side, bad_side = None, []
    if idx:
        print(f"piyasa (bağımsız): son 30 dk {mkt:+.4%}, artıda {up_n}/{len(r30)}, son 5 dk {mkt5:+.4%}, tepeden {peak:+.4%}, son 2 dk {jump:+.4%}, "
              f"tek coin en büyük katkı {top:+.4%}")
    for sym, fj, gated, score in rows:
        b = json.loads(fj)
        smooth = "r_t_raw" in b
        me = recs_me[sym]
        if "MKT_30" in b:
            me["MKT_30"] = mkt
        if "MKT_5" in b:
            me.update(MKT_UP=up_n, MKT_5=mkt5, MKT_PEAK=peak, MKT_TOP=top)
        if "MKT_JUMP" in b:
            me["MKT_JUMP"] = jump
        if "MKT_DN" in b:
            me.update(MKT_DN=dn_n, MKT_TROUGH=trough)
        else:
            for k_ in ("LC_DN", "COIN_J_UP", "COIN_J_DN"):
                me.pop(k_, None)
        if "R30" not in b:
            me.pop("R30", None)
        if "R_5M" not in b:
            me.pop("R_5M", None)
        if "TICK_REL" in b and sym in ticks:
            me["TICK_REL"] = ticks[sym] / me["_close_t"]
        # OI_1: kural "1 saatlik değişim". Bot yayımlanan son 5 dk noktasını (OI_TS) kullanır; denetim: OI_TS ≤ t,
        # t'ye en fazla 10 dk uzak ve değer = v[OI_TS] / v[OI_TS − 1 saat] − 1 (tam 60 dk).
        ts = b.get("OI_TS")
        if ts is None:
            bad.append((sym, "OI_TS yok (eski kod: 55/60 dk sorunu)", b.get("OI_1"), None))
            me["OI_1"] = b.get("OI_1")
        else:
            ts = int(ts)
            if not (t - 600_000 <= ts <= t):
                bad.append((sym, "OI_TS t'ye uzak", ts, t))
            v = me["_oi"]
            me["OI_1"] = v[ts] / v[ts - H] - 1 if ts in v and ts - H in v else None
        for k in keys:
            x, y = b.get(k), me.get(k)
            if x is None or y is None:
                if (x is None) != (y is None):
                    bad.append((sym, k, x, y))
                continue
            d = abs(x - y)
            worst[k] = max(worst[k], d)
            if d > 1e-9 + 1e-6 * abs(y):
                bad.append((sym, k, x, y))
        if D30_FROM_MS and t >= D30_FROM_MS:         # Değ. 30: yön + o yönün LC şartı
            my_gate = (my_side == "LONG" and me["LC"] >= 2) or (my_side == "SHORT" and me["LC_DN"] >= 2)
            if bool(gated) != my_gate and score is not None:
                bad.append((sym, "şart", gated, my_gate))
        elif D27_FROM_MS and t >= D27_FROM_MS:       # Değ. 27: dört piyasa şartı ve LC ≥ 2
            my_gate = (mkt is not None and mkt >= MKT_MIN and up_n >= MKT_UP_MIN and mkt5 is not None and mkt5 > 0
                       and peak >= -MKT_PEAK_MAX and me["LC"] >= 2)
            if D28_FROM_MS and t >= D28_FROM_MS:     # Değ. 28: sıçrama değil
                my_gate = my_gate and jump is not None and jump <= MKT_JUMP_SHARE * mkt
            if bool(gated) != my_gate and score is not None:
                bad.append((sym, "şart", gated, my_gate))
        elif D26_FROM_MS and t >= D26_FROM_MS:       # Değ. 26: piyasa son 30 dk > 0 ve LC ≥ 2 (öncesi denetlenmez)
            my_gate = mkt is not None and mkt > 0 and me["LC"] >= 2
            if bool(gated) != my_gate and score is not None:
                bad.append((sym, "şart", gated, my_gate))
    # puan: botun KAYDETTİĞİ bileşenlerden (IMB1_1/BIDSHARE_1 geriye dönük alınamaz) kendi sıra-yüzdesi hesabıyla yeniden
    # (eşitlerde ortalama sıra / n, bileşenlerin ortalaması; bileşeni eksik coin puanlanmaz)
    comps = ["LC", "SMOOTH_4", "TAKER_1", "IMB1_1", "BIDSHARE_1", "OI_1"] + ([] if t >= NOACC_FROM_MS else ["ACC_1"])
    recs = {sym: json.loads(fj) for sym, fj, _, _ in rows}
    ok = [s_ for s_, b in recs.items()
          if all(isinstance(b.get(c), (int, float)) and math.isfinite(b[c]) for c in comps)]
    mine = {s_: 0.0 for s_ in ok}
    for c in comps:
        v = sorted(ok, key=lambda s_: recs[s_][c])
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and recs[v[j + 1]][c] == recs[v[i]][c]:
                j += 1
            for q in range(i, j + 1):
                mine[v[q]] += ((i + j) / 2 + 1) / len(ok) / len(comps)
            i = j + 1
    sworst = 0.0
    for sym, _, _, score in rows:
        if (score is None) != (sym not in mine):
            bad.append((sym, "puan var/yok", score, mine.get(sym)))
        elif score is not None:
            sworst = max(sworst, abs(score - mine[sym]))
            if abs(score - mine[sym]) > 1e-9:
                bad.append((sym, "puan", score, mine[sym]))
    print(f"puan ({len(comps)} bileşen: {'+'.join(comps)}) en büyük fark {sworst:.1e}, puanlanan {len(mine)}")
    if has30 and D30_FROM_MS and t >= D30_FROM_MS:   # Değ. 30: short puanı, aynalanmış bileşenler, aynı sıra-yüzdesi hesabı
        comps_s = {"LC_DN": 1, "SMOOTH_4": -1, "TAKER_1": -1, "IMB1_1": -1, "BIDSHARE_1": -1, "OI_1": 1}
        ok_s = [s_ for s_ in ok if isinstance(recs[s_].get("LC_DN"), (int, float))]
        mine_s = {s_: 0.0 for s_ in ok_s}
        for c, sg in comps_s.items():
            v = sorted(ok_s, key=lambda s_: sg * recs[s_][c])
            i = 0
            while i < len(v):
                j = i
                while j + 1 < len(v) and sg * recs[v[j + 1]][c] == sg * recs[v[i]][c]:
                    j += 1
                for q in range(i, j + 1):
                    mine_s[v[q]] += ((i + j) / 2 + 1) / len(ok_s) / len(comps_s)
                i = j + 1
        ssw = 0.0
        for sym, (sd_, ss_) in side_rows.items():
            if (ss_ is None) != (sym not in mine_s):
                bad.append((sym, "short puanı var/yok", ss_, mine_s.get(sym)))
            elif ss_ is not None:
                ssw = max(ssw, abs(ss_ - mine_s[sym]))
                if abs(ss_ - mine_s[sym]) > 1e-9:
                    bad.append((sym, "short puanı", ss_, mine_s[sym]))
        print(f"short puanı (LC_DN, −SMOOTH_4, −TAKER_1, −IMB1_1, −BIDSHARE_1, OI_1) en büyük fark {ssw:.1e}, puanlanan {len(mine_s)}")
    bad += bad_side
    print("en büyük fark (bot − bağımsız):", {k: f"{v:.2e}" for k, v in worst.items()})
    print("uyuşmayan:", len(bad))
    for r in bad:
        print("  ", r)


def depth() -> None:
    db = sqlite3.connect(DB)
    t = db.execute("select max(ts) from scores").fetchone()[0]
    syms = [r[0] for r in db.execute("select sym from scores where ts = ?", (t,))]
    print(f"{'coin':<14}{'500 basamak alış ucu':>22}{'satış ucu':>12}{'  ±%1 kapsanıyor mu':>22}{'  ±%1 içi alış $ (500 / 1000)':>34}")
    short = 0
    for sym in syms:
        d10 = get("/fapi/v1/depth", symbol=sym, limit=1000)          # ağırlık 20; ilk 500 basamağı = limit=500
        d5 = {"bids": d10["bids"][:500], "asks": d10["asks"][:500]}
        time.sleep(0.5)
        mid = (float(d5["bids"][0][0]) + float(d5["asks"][0][0])) / 2
        lo, hi = float(d5["bids"][-1][0]) / mid - 1, float(d5["asks"][-1][0]) / mid - 1
        ok = lo <= -0.01 and hi >= 0.01
        short += not ok
        b5 = sum(float(p) * float(q) for p, q in d5["bids"] if float(p) >= mid * 0.99)
        b10 = sum(float(p) * float(q) for p, q in d10["bids"] if float(p) >= mid * 0.99)
        print(f"{sym:<14}{lo:>21.2%} {hi:>11.2%}{'evet' if ok else 'HAYIR':>22}{b5:>18,.0f} / {b10:,.0f}")
    print(f"\n{len(syms)} coinden {short} tanesinde 500 basamak ±%1'e uzanmıyor")
    cols = [r[1] for r in db.execute("pragma table_info(depth)")]
    if "band" in cols:
        print("\nbotun son defter görüntüsünde ölçülen band (yeni kod; %1 = kural, daha azı = 1000 basamağın ucu):")
        for sym, band, n in db.execute("select sym, band, count(*) from depth where band is not null and ts = "
                                       "(select max(ts) from depth d2 where d2.sym = depth.sym) group by sym order by band"):
            print(f"  {sym:<14} ±{band:.2%}")


def book(minutes: int) -> None:
    """Tam defter arşivi (06.11): (1) her görüntü açılıyor mu; basamak sayısı ve lastUpdateId kayıtla aynı mı, coin başına
    lastUpdateId hep ileri mi; (2) görüntüden ±band içi alış/satış $ toplamı BURADA sıfırdan hesaplanıp live.db depth
    özetiyle (aynı ts + sym) karşılaştırılır; (3) dakika başına coin sayısı; (4) botun aldığı an − Binance zamanı (E)."""
    import glob
    import lzma
    import os
    files = sorted(glob.glob(f"{BOOK}/*.db"))
    if not files:
        print("arşiv yok")
        return
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cut = int(time.time() * 1000) - minutes * 60_000
    n, bad, worst, lag, nomatch, per_min, last_uid = 0, [], 0.0, [], 0, {}, {}
    for f in files:
        b = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
        for ts, sym, uid, E, T, nb, na, raw in b.execute("select ts, sym, last_update_id, E, T, n_bids, n_asks, raw "
                                                         "from book where ts >= ? order by ts", (cut,)):
            n += 1
            d = json.loads(lzma.decompress(raw))
            if d["lastUpdateId"] != uid or d["E"] != E or len(d["bids"]) != nb or len(d["asks"]) != na:
                bad.append((sym, ts, "kayıt sütunları ham veriyle uyuşmuyor"))
            if sym in last_uid and uid <= last_uid[sym]:
                bad.append((sym, ts, "lastUpdateId ileri gitmedi"))
            last_uid[sym] = uid
            lag.append(ts - E)
            per_min.setdefault(ts // 60_000, set()).add(sym)
            bids = [(float(p), float(q)) for p, q in d["bids"]]
            asks = [(float(p), float(q)) for p, q in d["asks"]]
            mid = (bids[0][0] + asks[0][0]) / 2
            band = min(0.01, 1 - bids[-1][0] / mid, asks[-1][0] / mid - 1)
            b1 = sum(p * q for p, q in bids if p >= mid * (1 - band))
            a1 = sum(p * q for p, q in asks if p <= mid * (1 + band))
            r = db.execute("select b1, a1, band from depth where ts = ? and sym = ?", (ts, sym)).fetchone()
            if r is None:
                nomatch += 1
                continue
            dif = max(abs(r[0] - b1) / b1, abs(r[1] - a1) / a1, abs(r[2] - band))
            worst = max(worst, dif)
            if dif > 1e-9:
                bad.append((sym, ts, "özet farkı", dif))
    size = sum(os.path.getsize(f) for f in files)
    total = sum(sqlite3.connect(f"file:{f}?mode=ro", uri=True).execute("select count(*) from book").fetchone()[0]
                for f in files)
    counts = sorted(len(v) for v in per_min.values())
    lag.sort()
    print(f"arşiv: {len(files)} gün dosyası, {total} görüntü, {size / 1e6:.1f} MB "
          f"({size / max(total, 1) / 1e3:.1f} KB/görüntü)")
    print(f"son {minutes} dk: {n} görüntü, {len(per_min)} dakika, dakika başına coin en az {counts[0] if counts else 0} / "
          f"en çok {counts[-1] if counts else 0}")
    if lag:
        print(f"botun aldığı an − Binance zamanı: ortanca {lag[len(lag) // 2]} ms, en büyük {lag[-1]} ms")
    print(f"özetle karşılaştırma: en büyük fark {worst:.1e}, özeti bulunamayan {nomatch}")
    print("sorun:", len(bad))
    for x in bad[:20]:
        print("  ", x)


def universe(t: int | None) -> None:
    """06.11 ~14:05 liste denetimi: botun o dakika kaydettiği listede (uni24) her coinin 24 sa değişimi bağımsız olarak 1 dk
    mumlardan (kapanış t / kapanış t − 24 sa − 1) yeniden hesaplanır; işaret (> 0) aynı mı, sıra hacme göre mi, sabit coin var mı.
    Not: Binance ticker'ı istek anına göre kayar (bot t + 12 sn'de alır) → 0'a çok yakın coinlerde işaret farkı olabilir."""
    db = sqlite3.connect(DB)
    if t is None:
        t = db.execute("select max(ts) from uni24").fetchone()[0]
    cols = [r[1] for r in db.execute("pragma table_info(uni24)")]
    rows = db.execute(f"select sym, rank, chg24, qv24, {'vol60' if 'vol60' in cols else 'null'} from uni24 where ts = ? "
                      "order by rank", (t,)).fetchall()
    excl = db.execute("select sym, vrank, chg24, qv24, vol60 from uni_excl where ts = ? order by vrank", (t,)).fetchall() \
        if db.execute("select 1 from sqlite_master where name = 'uni_excl'").fetchone() else []
    print(f"dakika {time.strftime('%Y-%m-%d %H:%M', time.gmtime(t / 1000))} UTC, listede {len(rows)} coin, "
          f"oynaklık yüzünden alınmayan {len(excl)}")
    bad, worst, vworst = [], 0.0, 0.0

    t5 = t // 300_000 * 300_000                      # bot VOL60'ı t'nin 5 dk sınırında hesaplar

    def vol60(sym):  # bağımsız: t5'e kadar kapanmış son 1.500 adet 1 dk mum, 60 dk arayla getiriler, popülasyon std
        k = get("/fapi/v1/klines", symbol=sym, interval="1m", startTime=t5 - 1500 * 60_000, endTime=t5 - 1, limit=1500)
        c = {int(x[0]): float(x[4]) for x in k if int(x[0]) + 60_000 <= t5}
        r = [c[o + H] / c[o] - 1 for o in range(t5 - 1500 * 60_000, t5 - H, 60_000) if o in c and o + H in c]
        if len(r) < VOL_MIN_N:
            return None
        mu = sum(r) / len(r)
        return math.sqrt(sum((x - mu) ** 2 for x in r) / len(r))

    for sym, vr, ch, qv, v in excl:                  # alınmayanlar gerçekten > %2 (ya da ölçülemez) mi
        me = vol60(sym)
        if v is None or me is None:
            if (v is None) != (me is None):
                bad.append((sym, "VOL60 ölçülebilirlik farkı", v, me))
        else:
            vworst = max(vworst, abs(v - me))
            if me <= VOL_MAX or abs(v - me) > 1e-9:
                bad.append((sym, "alınmayan VOL60", v, me))
    for sym, rank, ch, qv, v in rows:
        if v is not None:                            # listedekiler ≤ %2 mi
            me = vol60(sym)
            if me is None or me > VOL_MAX or abs(v - me) > 1e-9:
                bad.append((sym, "listedeki VOL60", v, me))
            else:
                vworst = max(vworst, abs(v - me))
        k = get("/fapi/v1/klines", symbol=sym, interval="1m", startTime=t - 24 * H - 60_000, endTime=t - 1, limit=1500)
        c = {int(x[0]) + 60_000: float(x[4]) for x in k}
        if t in c and t - 24 * H in c:
            r = c[t] / c[t - 24 * H] - 1
            worst = max(worst, abs(r - ch))
            if r <= 0 and t < GATE24_TO_MS:          # 07.11'den beri işaret şartı yok (yalnız fark ölçülür)
                bad.append((sym, "1 dk mumla 24 sa ≤ 0", round(ch, 5), round(r, 5)))
        else:
            bad.append((sym, "mum yok (24 sa dolmamış)", ch, None))
    qvs = [r[3] for r in rows]
    if qvs != sorted(qvs, reverse=True):
        bad.append(("SIRA", "hacme göre değil", None, None))
    st = [r[0] for r in rows if r[0][:-4] in ("USDC", "FDUSD", "TUSD", "USDP", "DAI", "USDE", "USD1", "BUSD")]
    if st:
        bad.append(("SABİT", st, None, None))
    if excl and rows:                                # sıra: alınmayan her coin, listenin son coininden daha hacimli olmalı
        if any(e[3] < rows[-1][3] for e in excl):
            bad.append(("SIRA", "alınmayan coin listenin sonundan az hacimli (gereksiz atlama)", None, None))
    print(f"ticker 24 sa ile 1 dk mum 24 sa arasındaki en büyük fark: {worst:.4%}; VOL60 en büyük fark (bot − bağımsız): "
          f"{vworst:.1e}")
    print("uyuşmayan:", len(bad))
    for x in bad:
        print("  ", x)


if __name__ == "__main__":
    if sys.argv[1] == "universe":
        universe(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif sys.argv[1] == "features":
        features(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif sys.argv[1] == "depth":
        depth()
    elif sys.argv[1] == "book":
        book(int(sys.argv[2]) if len(sys.argv) > 2 else 60)
