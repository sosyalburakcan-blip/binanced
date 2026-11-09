"""v9 demo botu, 3 günlük kayıt incelemesi (09.11.2026). bot.py içe aktarılmaz.

Kullanım:
  python v9live/raporlar/inceleme_2026-11-09.py <book_klasörü> [live.db]

<book_klasörü>: Release'teki v9live_book.tar.zst açılınca çıkan 2026-11-06/07/08.db dosyalarının klasörü.
Fiyat yolu: arşivdeki gerçek piyasa defterinin (fapi /depth, dakikada bir) en iyi alış/satış ortası.
Dakikada bir görüntü olduğu için dakika içi uçlar görülmez; karşılaştırmalar aynı yöntemle yapıldığı için
gruplar arası fark geçerli, mutlak değme oranları yaklaşık.
"""
import glob
import json
import lzma
import sqlite3
import sys

import numpy as np
import pandas as pd

BOOK = sys.argv[1]
DB = sys.argv[2] if len(sys.argv) > 2 else "v9live/live.db"
TP, SL = 0.0037, 0.0033          # 1.500 $'da net +5 $ kâr al ≈ +%0,37, −5 $ stop ≈ −%0,33
D13 = pd.Timestamp("2026-11-06 18:09")   # 5 dk karar başlangıcı
D24 = pd.Timestamp("2026-11-07 17:56")   # 1.500 $ sabit, ±5 $ dönemi
REGIMES = [
    ("2026-11-06 00:00", "D0-3   100$ 1x / 150$"),
    ("2026-11-06 10:35", "D4-10  1500$ TP+5, acil -6%"),
    ("2026-11-06 14:13", "D11-12 24sa+ liste, SL-5$"),
    ("2026-11-06 18:09", "D13    5 dk, SL-12$"),
    ("2026-11-06 19:00", "D14    ±VOL60, geri çekilme"),
    ("2026-11-07 04:30", "D15-22 hacim listesi, hemen al"),
    ("2026-11-07 16:11", "D23    stop yok"),
    ("2026-11-07 17:56", "D24-25 4sa>0, ±5$"),
    ("2026-11-08 02:43", "D26    piyasa 30dk>0"),
    ("2026-11-08 04:16", "D27-29 piyasa 4-5 şart"),
    ("2026-11-08 07:01", "D30    LONG+SHORT"),
]


def regime(ts):
    lab = None
    for t, name in REGIMES:
        if ts >= pd.Timestamp(t):
            lab = name
    return lab


def to_ms(s):
    return s.values.astype("datetime64[ms]").astype("int64")


def load_trades():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    df = pd.read_sql("select * from trades", c)
    for k in ("fill", "exit", "decision"):
        df[k] = pd.to_datetime(df[k], format="mixed")
    df["side"] = df["side"].fillna("LONG")
    df["gross"] = df["pnl"] + df["fees"] - df["funding"]
    df["reg"] = df["decision"].apply(regime)
    return df.sort_values("fill").reset_index(drop=True)


def load_mid():
    rows = []
    for f in sorted(glob.glob(BOOK + "/*.db")):
        c = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
        for ts, sym, raw in c.execute("select ts, sym, raw from book"):
            try:
                d = json.loads(lzma.decompress(raw))
                rows.append((ts, sym, float(d["bids"][0][0]), float(d["asks"][0][0])))
            except Exception:
                continue
    m = pd.DataFrame(rows, columns=["ts", "sym", "bid", "ask"])
    m["mid"] = (m.bid + m.ask) / 2
    return m.sort_values("ts")


def section(t):
    print("\n## " + t)


def main():
    pd.set_option("display.width", 200)
    df = load_trades()
    section("1. Toplam ve dönemler")
    print("işlem %d (LONG %d, SHORT %d), kazanan %d, net %.2f $, ücret %.2f $, fonlama %.2f $, brüt %.2f $" % (
        len(df), (df.side == "LONG").sum(), (df.side == "SHORT").sum(), (df.pnl > 0).sum(),
        df.pnl.sum(), df.fees.sum(), df.funding.sum(), df.gross.sum()))
    g = df.groupby("reg", sort=False).agg(
        n=("pnl", "size"), kazanma=("pnl", lambda x: (x > 0).mean()), net=("pnl", "sum"),
        ucret=("fees", "sum"), brut=("gross", "sum"))
    print(g.round(2).to_string())

    d = df[df.decision >= D24]
    w, lo = d[d.pnl > 0].pnl.mean(), -d[d.pnl <= 0].pnl.mean()
    section("2. D24+ (1.500 $ sabit, +5/−5 $): çıkış türleri")
    print(d.groupby("reason").agg(n=("pnl", "size"), ort_net=("pnl", "mean"), ort_brut=("gross", "mean"),
                                  ort_ucret=("fees", "mean")).round(2).to_string())
    print("ort. kazanç %.2f $, ort. kayıp %.2f $ -> başa baş kazanma %%%.1f, gerçekleşen %%%.1f" % (
        w, lo, 100 * lo / (w + lo), 100 * (d.pnl > 0).mean()))

    m = load_mid()
    ser = {s: (x.ts.values, x.mid.values) for s, x in m.groupby("sym")}
    print("\n(defter arşivi: %d görüntü, %d coin)" % (len(m), m.sym.nunique()))

    def near(sym, t):
        if sym not in ser:
            return np.nan
        ts, mid = ser[sym]
        i = np.searchsorted(ts, t)
        k = min([k for k in (i - 1, i) if 0 <= k < len(ts)], key=lambda k: abs(ts[k] - t))
        return mid[k] if abs(ts[k] - t) < 40000 else np.nan

    section("3. Zararın kaynağı: gerçek fiyat hareketi / demo farkı / ücret")
    df["mid_in"] = [near(s, t) for s, t in zip(df.sym, to_ms(df.fill))]
    df["mid_out"] = [near(s, t) for s, t in zip(df.sym, to_ms(df.exit))]
    sg = np.where(df.side == "LONG", 1, -1)
    df["real"] = sg * (df.mid_out / df.mid_in - 1) * df.cost
    df["demo"] = df.gross - df.real
    for name, x in (("tümü", df), ("D24+", df[df.decision >= D24])):
        x = x.dropna(subset=["mid_in", "mid_out"])
        print("%-5s ölçülen %d işlem: net %.1f = gerçek fiyat %.1f + demo/zamanlama %.1f + ücret %.1f + fonlama %.1f" % (
            name, len(x), x.pnl.sum(), x.real.sum(), x.demo.sum(), -x.fees.sum(), x.funding.sum()))

    section("4. Giriş şartı rastgeleden iyi mi? (her 5 dk karar × listedeki 30 coin)")
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    s = pd.read_sql("select ts, sym, gated, score, chosen, side from scores", c)
    s = s[s.ts >= D13.value // 10**6]
    s["side"] = s.side.fillna("LONG")

    def path(sym, t, side):
        if sym not in ser:
            return None
        ts, mid = ser[sym]
        i = np.searchsorted(ts, t + 12000)
        if i >= len(ts) or ts[i] > t + 102000:
            return None
        j = np.searchsorted(ts, ts[i] + 75 * 60000, side="right")
        p, tt = mid[i:j], ts[i:j]
        if len(p) < 45:
            return None
        r = (p / mid[i] - 1) * (1 if side == "LONG" else -1)
        up, dn = np.where(r >= TP)[0], np.where(r <= -SL)[0]
        fu = up[0] if len(up) else 10**9
        fd = dn[0] if len(dn) else 10**9
        k60 = min(np.searchsorted(tt, ts[i] + 3600000), len(r) - 1)
        return ("TP" if fu < fd else "SL" if fd < fu else "yok"), r[k60]

    out = []
    for r in s.itertuples():
        for side in ("LONG", "SHORT"):
            st = path(r.sym, r.ts, side)
            if st:
                out.append((r.ts, r.sym, r.gated, r.chosen, r.side, r.score, side, st[0], st[1]))
    o = pd.DataFrame(out, columns=["ts", "sym", "gated", "chosen", "dside", "score", "side", "first", "r60"])
    o["reg"] = pd.to_datetime(o.ts, unit="ms").apply(regime)

    def by_time(x, name):
        gt = x.groupby("ts").agg(r60=("r60", "mean"), tp=("first", lambda f: (f == "TP").mean()),
                                 sl=("first", lambda f: (f == "SL").mean()))
        n = len(gt)
        print("%-34s karar %4d | kâr al önce %%%.1f, stop önce %%%.1f | 60 dk sonra %+.3f%% (se %.3f)" % (
            name, n, 100 * gt.tp.mean(), 100 * gt.sl.mean(), 100 * gt.r60.mean(), 100 * gt.r60.std() / np.sqrt(n)))

    L, S = o[o.side == "LONG"], o[o.side == "SHORT"]
    gl = L[(L.gated == 1) & (L.dside == "LONG")]
    gs = S[(S.gated == 1) & (S.dside == "SHORT")]
    by_time(L, "LONG, rastgele (tüm coinler)")
    by_time(gl, "LONG, şartı geçen")
    by_time(L[(L.chosen == 1) & (L.dside == "LONG")], "LONG, seçilen")
    by_time(S, "SHORT, rastgele (tüm coinler)")
    by_time(gs, "SHORT, şartı geçen")
    print("dönem dönem (LONG şartı geçen / aynı dönem rastgele):")
    for reg in [n for _, n in REGIMES]:
        a, b = gl[gl.reg == reg], L[L.reg == reg]
        if len(a):
            print("   %-30s %+.3f%% / %+.3f%%  (%d karar)" % (reg, 100 * a.groupby("ts").r60.mean().mean(),
                                                         100 * b.groupby("ts").r60.mean().mean(), a.ts.nunique()))
    diff = []
    for t, x in L.groupby("ts"):
        a = x[(x.gated == 1) & (x.dside == "LONG")]
        b = x[~((x.gated == 1) & (x.dside == "LONG"))]
        if len(a) and len(b):
            diff.append((t // 3600000, a.r60.mean() - b.r60.mean()))
    dd = pd.DataFrame(diff, columns=["h", "d"])
    hb = dd.groupby("h").d.mean()
    print("aynı anda şartı geçen − geçmeyen coin, 60 dk: %+.3f%% (karar %d); saatlik bloklarla %+.3f%% (se %.3f, %d blok)" % (
        100 * dd.d.mean(), len(dd), 100 * hb.mean(), 100 * hb.std() / np.sqrt(len(hb)), len(hb)))
    rho = []
    for t, x in L.groupby("ts"):
        x = x.dropna(subset=["score"])
        if len(x) > 10:
            rho.append(x.score.rank().corr(x.r60.rank()))
    print("puan ↔ sonraki 60 dk sıra korelasyonu (karar başına ort.): %.3f (%d karar)" % (np.nanmean(rho), len(rho)))

    section("5. Piyasa şartları (Değ. 27–28 long, Değ. 30 short) 3 güne sabit kural olarak")
    m["mn"] = m.ts // 60000
    P = m.drop_duplicates(["mn", "sym"]).pivot(index="mn", columns="sym", values="mid")
    P = P.reindex(range(P.index.min(), P.index.max() + 1))
    rows = []
    for t, x in s.groupby("ts"):
        mn = t // 60000
        syms = [y for y in x.sym if y in P.columns]
        if mn - 30 not in P.index or mn + 60 not in P.index:
            continue
        pth = P.loc[mn - 30:mn, syms].div(P.loc[mn - 30, syms]) - 1
        ok = pth.notna().all()
        if ok.sum() < 20:
            continue
        idx = pth.loc[:, ok].mean(axis=1).values
        r30 = pth.loc[mn, ok]
        fut = P.loc[[mn, mn + 30, mn + 60], syms].loc[:, ok]
        f = (fut.iloc[1:] / fut.iloc[0] - 1).mean(axis=1).values
        rows.append(dict(m30=idx[-1], up=(r30 > 0).sum(), dn=(r30 < 0).sum(), m5=idx[-1] - idx[-6],
                         peak=idx[-1] - idx.max(), trough=idx[-1] - idx.min(), jump=idx[-1] - idx[-3],
                         f30=f[0], f60=f[1]))
    k = pd.DataFrame(rows)
    lg = (k.m30 >= 0.001) & (k.up >= 20) & (k.m5 > 0) & (k.peak >= -0.001) & (k.jump <= 0.5 * k.m30)
    sh = (k.m30 <= -0.001) & (k.dn >= 20) & (k.m5 < 0) & (k.trough <= 0.001) & (k.jump >= 0.5 * k.m30)
    print("geçmiş 30 dk ↔ sonraki 30 dk piyasa korelasyonu: %.3f (%d karar)" % (k.m30.corr(k.f30), len(k)))
    for name, mask, sgn in (("tüm kararlar (long yönü)", k.index == k.index, 1),
                            ("LONG piyasa şartı", lg, 1), ("SHORT piyasa şartı", sh, -1)):
        x = k[mask]
        print("%-26s karar %3d | işlem yönünde sonraki 30 dk %+.3f%%, 60 dk %+.3f%%" % (
            name, len(x), 100 * sgn * x.f30.mean(), 100 * sgn * x.f60.mean()))

    section("6. Erken çıkışlar doğru muydu? (D24+, çıkıştan sonraki 120 dk: önce hangi seviye)")
    res = []
    for r in df[(df.decision >= D24) & df.reason.isin(["kayan_kontrol", "ek_kontrol_düştü", "ters_sıçrama"])].itertuples():
        if r.sym not in ser:
            continue
        ts, mid = ser[r.sym]
        t0 = int(np.datetime64(r.exit, "ms").astype("int64"))
        p = mid[np.searchsorted(ts, t0):np.searchsorted(ts, t0 + 7200000)]
        if len(p) < 30:
            continue
        rr = (1 if r.side == "LONG" else -1) * (p / r.entry - 1)
        up, dn = np.where(rr >= TP)[0], np.where(rr <= -SL)[0]
        fu = up[0] if len(up) else 1e9
        fd = dn[0] if len(dn) else 1e9
        res.append((r.reason, "sonra kâr al" if fu < fd else "sonra stop" if fd < fu else "ikisi de yok"))
    x = pd.DataFrame(res, columns=["sebep", "sonra"])
    print(pd.crosstab(x.sebep, x.sonra, margins=True).to_string())


if __name__ == "__main__":
    main()
