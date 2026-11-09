"""Ön kayıtlı deney: az komisyon + yüksek yön isabeti (deney_2026-11-09_onkayit.md). bot.py içe aktarılmaz.

Kullanım: python v9live/raporlar/deney_2026-11-09.py <book_klasörü> [live.db] [çıktı.pkl]
"""
import glob
import itertools
import json
import lzma
import sqlite3
import sys

import numpy as np
import pandas as pd

BOOK = sys.argv[1]
DB = sys.argv[2] if len(sys.argv) > 2 else "v9live/live.db"
OUT = sys.argv[3] if len(sys.argv) > 3 else None
SPLIT = pd.Timestamp("2026-11-08 00:00").value // 60_000_000_000   # bekletme başlangıcı (dakika)
NOTIONAL, MAKER, TAKER, SLIP = 1500.0, 0.0002, 0.0005, 0.0001
FEATS, SIGNS, THRS, MODES = ["r30x", "r60x", "r240x", "combo", "imb"], ["mom", "rev"], [1.5, 2.0, 2.5], ["L", "S", "LS"]
XS, HS = [0.005, 0.008, 0.012], [60, 120, 240]
MAXPOS = 4


def load_prices():
    rows = []
    for f in sorted(glob.glob(BOOK + "/*.db")):
        c = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
        for ts, sym, raw in c.execute("select ts, sym, raw from book"):
            try:
                d = json.loads(lzma.decompress(raw))
                rows.append((ts // 60000, ts, sym, float(d["bids"][0][0]), float(d["asks"][0][0])))
            except Exception:
                continue
    m = pd.DataFrame(rows, columns=["mn", "ts", "sym", "bid", "ask"]).sort_values("ts").drop_duplicates(["mn", "sym"])
    m["mid"] = (m.bid + m.ask) / 2
    idx = range(m.mn.min(), m.mn.max() + 1)
    piv = {k: m.pivot(index="mn", columns="sym", values=k).reindex(idx) for k in ("bid", "ask", "mid")}
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dp = pd.read_sql("select ts, sym, b1, a1 from depth", c)
    dp["mn"] = dp.ts // 60000
    dp["imb"] = (dp.b1 - dp.a1) / (dp.b1 + dp.a1)
    imb = dp.drop_duplicates(["mn", "sym"]).pivot(index="mn", columns="sym", values="imb")
    piv["imb"] = imb.reindex(index=idx, columns=piv["mid"].columns)
    return piv


def zs(s):
    sd = s.std()
    return (s - s.mean()) / sd if sd and np.isfinite(sd) and sd > 0 else s * np.nan


def build_decisions(piv):
    mid = piv["mid"]
    first, last = mid.index.min(), mid.index.max()
    dec = {}
    for mn in range(first + 240, last - 61):
        if mn % 5:
            continue
        ok = mid.loc[[mn, mn - 30, mn - 60, mn - 240, mn + 1]].notna().all()
        syms = ok[ok].index
        if len(syms) < 20:
            continue
        now = mid.loc[mn, syms]
        f = pd.DataFrame(index=syms)
        for lb in (30, 60, 240):
            r = now / mid.loc[mn - lb, syms] - 1
            f[f"r{lb}x"] = r - r.mean()
        f["combo"] = zs(zs(f.r60x) + zs(f.r240x))
        f["imb"] = piv["imb"].loc[mn, syms]
        dec[mn] = f
    return dec


def outcomes(piv, dec):
    """(mn, sym, yön, x, H, giriş) → (brüt, çıkış dk, tür, ücret oranı çıkış). Yol eksikse kayıt yok."""
    mid, bid, ask = (piv[k].values for k in ("mid", "bid", "ask"))
    cols = {s: i for i, s in enumerate(piv["mid"].columns)}
    base = piv["mid"].index.min()
    nrow = mid.shape[0]
    res = {}
    for mn, f in dec.items():
        i0 = mn + 1 - base
        for sym in f.index:
            j = cols[sym]
            for side in (1, -1):
                for ent in ("maker", "taker"):
                    if ent == "maker":
                        p0 = mid[i0, j]
                    else:
                        p0 = ask[i0, j] if side == 1 else bid[i0, j]
                    for H in HS:
                        if i0 + H >= nrow:
                            continue
                        seg_m, seg_b, seg_a = mid[i0 + 1:i0 + H + 1, j], bid[i0 + 1:i0 + H + 1, j], ask[i0 + 1:i0 + H + 1, j]
                        avail = ~np.isnan(seg_m)
                        if avail.mean() < 0.8 or not avail[-10:].any():
                            continue
                        last_k = np.where(avail)[0][-1]
                        for x in XS:
                            if side == 1:
                                tp_hit = np.where(seg_b >= p0 * (1 + x))[0]
                                sl_hit = np.where(seg_m <= p0 * (1 - x))[0]
                            else:
                                tp_hit = np.where(seg_a <= p0 * (1 - x))[0]
                                sl_hit = np.where(seg_m >= p0 * (1 + x))[0]
                            kt = tp_hit[0] if len(tp_hit) else 10**9
                            ks = sl_hit[0] if len(sl_hit) else 10**9
                            if ks <= kt and ks < 10**9:
                                lvl = p0 * (1 - side * x)
                                px = (min(seg_b[ks], lvl) * (1 - SLIP)) if side == 1 else (max(seg_a[ks], lvl) * (1 + SLIP))
                                k, typ, fo = ks, "SL", TAKER
                            elif kt < 10**9:
                                px, k, typ, fo = p0 * (1 + side * x), kt, "TP", MAKER
                            else:
                                k = last_k
                                px = seg_b[k] if side == 1 else seg_a[k]
                                typ, fo = "time", TAKER
                            gross = side * (px / p0 - 1)
                            fin = MAKER if ent == "maker" else TAKER
                            net = NOTIONAL * (gross - fin - fo * px / p0)
                            res[(mn, sym, side, x, H, ent)] = (gross, mn + 1 + k + 1, typ, net)
    return res


def zmaps(dec, shuffle_seed=None):
    """Her özellik ve karar için z (en uç long / short adayı ve z'si). Karıştırma: tohumla, özellik başına bir kez."""
    rng = np.random.default_rng(shuffle_seed) if shuffle_seed is not None else None
    zm = {}
    for feat in FEATS:
        zm[feat] = {}
        for mn in sorted(dec):
            v = dec[mn][feat].dropna()
            if len(v) < 20:
                continue
            if rng is not None:
                v = pd.Series(rng.permutation(v.values), index=v.index)
            z = zs(v)
            if z.notna().sum() < 20:
                continue
            zm[feat][mn] = (z.max(), z.idxmax(), z.min(), z.idxmin())
    return zm


def run(dec, out, zf, sign, thr, mode, x, H, ent="maker", override=None):
    """Portföy: 4 yuva, coin başına 1. zf = zmaps()[özellik]. override = [(mn, side, sym)] → o girişler (rastgele kıyas)."""
    open_pos, trades = [], []
    plan = None
    if override is not None:
        plan = {}
        for mn, side, sym in override:
            plan.setdefault(mn, []).append((side, sym))
    for mn in sorted(dec):
        open_pos = [p for p in open_pos if p[1] > mn]
        if plan is not None:
            for side, sym in plan.get(mn, []):
                o = out.get((mn, sym, side, x, H, ent))
                if o:
                    open_pos.append((sym, o[1]))
                    trades.append((mn, sym, side) + o)
            continue
        if mn not in zf:
            continue
        zmax, imax, zmin, imin = zf[mn]
        if sign == "rev":      # yüksek z → short: long adayı en düşük z, short adayı en yüksek z
            zmax, imax, zmin, imin = -zmin, imin, -zmax, imax
        cands = []
        if mode in ("L", "LS") and zmax >= thr:
            cands.append((zmax, 1, imax))
        if mode in ("S", "LS") and zmin <= -thr:
            cands.append((-zmin, -1, imin))
        for _, side, sym in sorted(cands, reverse=True):
            if len(open_pos) >= MAXPOS or any(p[0] == sym for p in open_pos):
                continue
            o = out.get((mn, sym, side, x, H, ent))
            if not o:
                continue
            open_pos.append((sym, o[1]))
            trades.append((mn, sym, side) + o)
    return pd.DataFrame(trades, columns=["mn", "sym", "side", "gross", "exit_mn", "typ", "net"])


def summ(t, days):
    if len(t) == 0:
        return dict(n=0, gun=0.0, net=0.0, isabet=np.nan, tp=np.nan, ucret=0.0)
    return dict(n=len(t), gun=len(t) / days, net=t.net.sum(), isabet=(t.gross > 0).mean(),
                tp=(t.typ == "TP").mean(), ucret=(NOTIONAL * t.gross - t.net).sum())


def grid(dec, out, zm):
    mins = sorted(dec)
    dd = (SPLIT - mins[0]) / 1440
    rows = []
    for feat, sign, thr, mode, x, H in itertools.product(FEATS, SIGNS, THRS, MODES, XS, HS):
        t = run(dec, out, zm[feat], sign, thr, mode, x, H)
        a, b = t[t.mn < SPLIT], t[t.mn >= SPLIT]
        hd = (max(m for m in mins if m + 1 + H < max(mins) + 61) - SPLIT) / 1440
        sa, sb = summ(a, dd), summ(b, hd)
        rows.append(dict(feat=feat, sign=sign, thr=thr, mode=mode, x=x, H=H,
                         **{"t_" + k: v for k, v in sa.items()}, **{"h_" + k: v for k, v in sb.items()}))
    return pd.DataFrame(rows)


def main():
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    piv = load_prices()
    dec = build_decisions(piv)
    mins = sorted(dec)
    print("karar: %d (tasarım %d, bekletme %d)" % (len(mins), sum(m < SPLIT for m in mins), sum(m >= SPLIT for m in mins)))
    out = outcomes(piv, dec)
    print("sonuç kaydı:", len(out))
    zm = zmaps(dec)
    G = grid(dec, out, zm)
    R = grid(dec, out, zmaps(dec, shuffle_seed=1))
    if OUT:
        pd.to_pickle(dict(G=G, R=R), OUT)

    print("\n## Izgara geneli (810 yapılandırma; bekletmede en az 5 işlemi olanlar)")
    for name, g in (("gerçek sinyal", G), ("rastgele sinyal", R)):
        gg = g[g.h_n >= 5]
        print("%-16s tasarım net>0: %d/%d | bekletme net>0: %d/%d | bekletme net ortanca %.1f $ | bekletme isabet ortanca %.1f%%" % (
            name, (g.t_net > 0).sum(), len(g), (gg.h_net > 0).sum(), len(gg), gg.h_net.median(), 100 * gg.h_isabet.median()))

    elig = G[G.t_n >= 20].sort_values("t_net", ascending=False)
    print("\n## Tasarımda en iyi 10 (seçim yalnız tasarımla) ve bekletme sonuçları")
    cols = ["feat", "sign", "thr", "mode", "x", "H", "t_n", "t_gun", "t_net", "t_isabet", "h_n", "h_gun", "h_net", "h_isabet", "h_ucret"]
    print(elig[cols].head(10).round(3).to_string(index=False))

    best = elig.iloc[0]
    print("\n## Seçilen yapılandırma:", dict(best[["feat", "sign", "thr", "mode", "x", "H"]]))
    t = run(dec, out, zm[best.feat], best.sign, best.thr, best["mode"], best.x, int(best.H))
    th = t[t.mn >= SPLIT]
    print("tasarım: n %d, net %.1f $, isabet %.1f%% | bekletme: n %d, net %.1f $, isabet %.1f%%, kâr al payı %.1f%%" % (
        (t.mn < SPLIT).sum(), t[t.mn < SPLIT].net.sum(), 100 * (t[t.mn < SPLIT].gross > 0).mean(),
        len(th), th.net.sum(), 100 * (th.gross > 0).mean() if len(th) else np.nan, 100 * (th.typ == "TP").mean() if len(th) else np.nan))
    tk = run(dec, out, zm[best.feat], best.sign, best.thr, best["mode"], best.x, int(best.H), ent="taker")
    print("duyarlılık (taker giriş): tasarım net %.1f $, bekletme net %.1f $" % (tk[tk.mn < SPLIT].net.sum(), tk[tk.mn >= SPLIT].net.sum()))

    rng = np.random.default_rng(2026)
    sims = []
    X, H = best.x, int(best.H)
    for _ in range(1000):
        ov, held = [], []          # held: (sym, çıkış dk) — bu tekrarın kendi açık pozisyonları
        for r in th.itertuples():
            held = [h for h in held if h[1] > r.mn]
            busy = {h[0] for h in held}
            pool = [s for s in dec[r.mn].index if s not in busy and (r.mn, s, r.side, X, H, "maker") in out]
            if not pool:
                continue
            s = pool[rng.integers(len(pool))]
            ov.append((r.mn, r.side, s))
            held.append((s, out[(r.mn, s, r.side, X, H, "maker")][1]))
        sims.append(run(dec, out, None, None, None, None, X, H, override=ov).net.sum())
    sims = np.array(sims)
    p = (sims >= th.net.sum()).mean()
    print("rastgele giriş (aynı an/yön/çıkış, 1000 tekrar): ortanca %.1f $, %%95 %.1f $ → p = %.3f" % (
        np.median(sims), np.quantile(sims, 0.95), p))
    c1, c2 = best.t_net > 0, th.net.sum() > 0
    c3 = (th.gross > 0).mean() > 0.5 if len(th) else False
    c4 = p < 0.05
    print("şartlar: tasarım net>0 %s | bekletme net>0 %s | bekletme isabet>%%50 %s | p<0,05 %s → %s" % (
        c1, c2, c3, c4, "GEÇTİ" if all((c1, c2, c3, c4)) else "GEÇMEDİ"))

    print("\n## Bilgi (seçimde kullanılmadı): komisyonun etkisi — ızgarada x ve H'ye göre tasarım + bekletme toplamı")
    G["net"] = G.t_net + G.h_net
    G["ucret"] = G.t_ucret + G.h_ucret
    G["n"] = G.t_n + G.h_n
    agg = G.groupby(["x", "H"]).agg(islem=("n", "median"), net=("net", "median"), ucret=("ucret", "median"))
    print(agg.round(1).to_string())


if __name__ == "__main__":
    main()
