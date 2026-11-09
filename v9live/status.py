"""v9 demo botu özeti: açık pozisyonlar, kapanan işlemler, toplam sonuç, son saatin en iyi puanları.
    /root/binanced/.venv/bin/python /root/binanced/v9live/status.py
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path("/root/binanced/v9live")


def balances() -> None:
    """06.11 ~14:05 kullanıcı: demo hesabın tüm bakiyeleri (yalnız okuma; bağımsız imza audit/demo_sign.py)."""
    try:
        import sys
        sys.path.insert(0, str(HERE / "audit"))
        from demo_sign import g
        a = g("/fapi/v2/account")
        print("== Demo bakiye (bot yalnız USDT kullanır)")
        for x in a["assets"]:
            if float(x["walletBalance"]):
                print(f"  {x['asset']:5s} cüzdan {float(x['walletBalance']):,.4f}  kullanılabilir {float(x['availableBalance']):,.4f}")
        print(f"  açık pozisyon teminatı {float(a['totalPositionInitialMargin']):,.2f} $, gerçekleşmemiş "
              f"{float(a['totalUnrealizedProfit']):+,.2f} $\n")
    except Exception as e:  # noqa: BLE001
        print(f"== Demo bakiye okunamadı: {e}\n")


def universe(db) -> None:
    try:
        u = pd.read_sql("select * from uni24 where ts = (select max(ts) from uni24) order by rank", db)
    except Exception:  # noqa: BLE001
        return
    if len(u):
        print(f"\n== Coin listesi ({pd.Timestamp(int(u.ts.iloc[0]), unit='ms')}; 24 sa hacme göre ilk {len(u)}; 07.11'den beri '24 sa artıda' şartı yok)")
        print("  " + ", ".join(f"{r.sym.removesuffix('USDT')} {100 * r.chg24:+.1f}% ({r.qv24 / 1e6:.0f} M$)" for r in u.itertuples()))


def main() -> None:
    balances()
    st = json.loads((HERE / "state.json").read_text()) if (HERE / "state.json").exists() else []
    print("== Açık / bekleyen pozisyonlar")
    if not st:
        print("  yok")
    for p in st:
        try:
            r = requests.get("https://demo-fapi.binance.com/fapi/v1/ticker/bookTicker", params={"symbol": p["sym"]},
                             timeout=10).json()
            short = p.get("side") == "SHORT"              # 08.11 Değ. 30: short'ta kapatma fiyatı = en iyi satış
            bid = float(r["askPrice"] if short else r["bidPrice"])
        except Exception:  # noqa: BLE001
            short, bid = p.get("side") == "SHORT", float("nan")
        e = p["entry"] or float("nan")
        print(f"  {p.get('side', 'LONG'):5s} {p['sym']:12s} {p['status']:8s} giriş {e:.6g}  demo {bid:.6g}  "
              f"işlem yönünde {((bid / e - 1) * (-1 if short else 1)) if e == e else float('nan'):+.2%}  koruma {'✓' if p['protected'] else '-'}  "
              f"kontrol {len(p['checks'])}  {p.get('lev', 1)}×  {('tasfiye %.6g' % p['liq_px']) if p.get('liq_px') else ''}")
    db = sqlite3.connect(HERE / "live.db")
    t = pd.read_sql("select * from trades", db)
    print(f"\n== Kapanan işlemler ({len(t)})")
    if len(t):
        print(t.assign(lev=t["lev"].fillna(1).astype(int) if "lev" in t else 1)[
            ["sym", "fill", "exit", "lev", "entry", "exit_px", "pnl", "pnl_pct", "reason"]
            + (["side"] if "side" in t else [])].assign(
            pnl=lambda d: d.pnl.round(3), pnl_pct=lambda d: (100 * d.pnl_pct).round(2)).to_string(index=False))
        print(f"\n  toplam net {t.pnl.sum():+.2f} $ | kazanan {int((t.pnl > 0).sum())}/{len(t)} | "
              f"ortalama {100 * t.pnl_pct.mean():+.2f}% | ücret {t.fees.sum():.2f} $ | nedenler "
              f"{t.reason.value_counts().to_dict()}")
        breakeven(t)
    s = pd.read_sql("select * from scores where ts = (select max(ts) from scores)", db)
    if len(s):
        print(f"\n== Son dakika ({pd.Timestamp(int(s.ts.iloc[0]), unit='ms')}): şartı sağlayan {int(s.gated.sum())}, "
              f"seçilen {list(s[s.chosen == 1].sym)}")
        print(s.sort_values("score", ascending=False).head(8)[["sym", "gated", "score"]].round(3).to_string(index=False))
    universe(db)
    archive(db)
    observations(db)
    label_effect(db)


def breakeven(t: pd.DataFrame) -> None:
    """Kullanıcı 06.11: "demo testinin amacı önce komisyon ve vergilerle paramızı çıkarabiliyor muyuz; kâr sonra".
    Her işlem borsa kayıtlarından (cost = alış tutarı, value = satış tutarı, funding) GERÇEK hesap ücretiyle yeniden
    hesaplanır: VIP 0, BNB'siz maker %0,02 / taker %0,05 (reports/V4_fees_tax.md; demo bazı coinlerde %0,04 alıyor).
    Giriş her zaman maker (GTX); çıkış kâr al ise maker (limit), 60 dk / saatlik kontrol / acil stop / piyasa ise taker.
    Vergi: yürürlükte işlem vergisi yok (0). Temkinli senaryo: geri çekilen teklif, taraf başına %0,03.
    Belirsizlik: ortalamanın %95 aralığı = 1,96 × std / √n; n < 30 iken std VARSAYIMI %1,76 (geçen haftanın 30 coin
    1 saatlik getiri std'si, live.db outcomes), n ≥ 30 olunca işlemlerin kendi std'si."""
    MK, TK, TAX = 0.0002, 0.0005, 0.0003
    cost, value = t.cost.astype(float), t.value.astype(float)
    gross = (value - cost) / cost                                   # ücret ve fonlama öncesi
    exit_fee = np.where(t.reason == "kâr_al", MK, TK)
    fee = MK + exit_fee * value / cost
    net = gross - fee + t.funding.astype(float) / cost
    net_tax = net - TAX * (1 + value / cost)
    n = len(t)
    sd, sd_src = (float(net.std(ddof=1)), "işlemlerin kendi oynaklığı") if n >= 30 else (0.0176, "VARSAYIM %1,76")
    band = 1.96 * sd / np.sqrt(n)
    m = float(net.mean())
    if m - band > 0:
        verdict = "masrafı ÇIKARIYOR (aralığın alt ucu bile sıfırın üstünde)"
    elif m + band < 0:
        verdict = "masrafı ÇIKARAMIYOR (aralığın üst ucu bile sıfırın altında)"
    else:
        need = int(np.ceil((1.96 * sd / abs(m)) ** 2)) if abs(m) > 1e-9 else None
        verdict = "henüz BELİRSİZ" + (f"; ortalama böyle kalırsa karar için ≈{need} işlem gerekir" if need else "")
    print(f"\n== Masrafı çıkarıyor muyuz? (gerçek hesap ücretiyle yeniden hesap, {n} işlem)")
    print(f"  ücret öncesi ortalama      {100 * gross.mean():+.3f}% / işlem")
    print(f"  gerçek ücret ortalaması    {100 * fee.mean():.3f}% / işlem   (başa baş için ücret öncesi bunu geçmeli)")
    print(f"  net (gerçek ücret)         {100 * m:+.3f}% / işlem, toplam {float((net * cost).sum()):+.2f} $   "
          f"[demo kaydı: {100 * t.pnl_pct.mean():+.3f}%]")
    print(f"  net (+ %0,03/taraf vergi)  {100 * net_tax.mean():+.3f}% / işlem, toplam {float((net_tax * cost).sum()):+.2f} $")
    print(f"  %95 aralık                 {100 * (m - band):+.2f}% … {100 * (m + band):+.2f}%  ({sd_src})")
    print(f"  sonuç: {verdict}")
    print("  not: kazanç vergisi (yıllık beyan %15–40, nitelendirme belirsiz) yalnız kârdan alınır; başa başı etkilemez")


def archive(db) -> None:
    """Defter kayıtları (06.11: tam defter arşivi, hiçbiri silinmez)."""
    n, t0, t1 = db.execute("select count(*), min(ts), max(ts) from depth").fetchone()
    ts = lambda x: pd.Timestamp(int(x), unit="ms") if x else "-"  # noqa: E731
    print(f"\n== Defter kaydı\n  özet (live.db depth): {n} satır, {ts(t0)} → {ts(t1)}")
    files = sorted((HERE / "book").glob("*.db"))
    if not files:
        print("  tam defter (v9live/book): henüz yok")
        return
    size = sum(f.stat().st_size for f in files)
    tot, last, ncoin = 0, None, 0
    for f in files:
        b = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
        tot += b.execute("select count(*) from book").fetchone()[0]
    b = sqlite3.connect(f"file:{files[-1]}?mode=ro", uri=True)
    last, ncoin = b.execute("select max(ts), (select count(*) from book where ts >= (select max(ts) from book) - 30000) "
                            "from book").fetchone()
    free = shutil.disk_usage(HERE).free / 1e9
    print(f"  tam defter (v9live/book): {len(files)} gün, {tot} görüntü, {size / 1e6:.0f} MB, son görüntü {ts(last)} "
          f"({ncoin} coin) | diskte boş {free:.1f} GB (3 GB altında kayıt durur)")


def observations(db) -> None:
    """Gözlem: karar anında yükseliş kaç saattir sürüyordu → sonraki 24 saatte ne oldu (kararı etkilemez)."""
    try:
        o = pd.read_sql("select * from outcomes", db)
        # 06.11 12:45'ten beri scores her dakika; outcomes saatlik → yalnız saat başı satırları eşleşir
        s = pd.read_sql("select ts, sym, feats, gated, chosen from scores where ts % 3600000 = 0", db)
    except Exception:  # noqa: BLE001
        return
    if not len(o):
        print("\n== Gözlem: henüz 24 saati dolan kayıt yok")
        return
    m = o.merge(s.drop(columns="feats"), on=["ts", "sym"], how="left")
    print(f"\n== Gözlem: 24 saati dolan {len(o)} coin-saat ({pd.Timestamp(int(o.ts.min()), unit='ms')} → "
          f"{pd.Timestamp(int(o.ts.max()), unit='ms')})")

    def tab(g):
        return g.agg(n=("sym", "size"), yukselis_saat=("rise_hours_after", "mean"),
                     hizlanma_saat=("acc_hours_after", "mean"), sonra_1sa=("fwd_1", "mean"), sonra_4sa=("fwd_4", "mean"),
                     sonra_24sa=("fwd_24", "mean"), yuzde3_oldu=("hours_to_up3", lambda x: x.notna().mean()),
                     eksi6_oldu=("hours_to_dn6", lambda x: x.notna().mean()), en_dusuk=("max_dn_24", "mean"))
    fmt = lambda d: d.assign(**{c: (100 * d[c]).round(2) for c in ("sonra_1sa", "sonra_4sa", "sonra_24sa",  # noqa: E731
                                                                     "yuzde3_oldu", "eksi6_oldu", "en_dusuk")}).round(2)
    print("  (yüzdeler %; yukselis_saat = sonra üst üste kaç saat yükseldi; yuzde3_oldu = 24 sa içinde +%3'e değme payı)")
    k = m.assign(kac_saattir=pd.cut(m.up_streak_at, [-1, 0, 1, 2, 3, 5, 999], labels=["0", "1", "2", "3", "4-5", "6+"]),
                 hizlanma_kac_saattir=pd.cut(m.acc_streak_at, [-1, 0, 1, 2, 3, 999], labels=["0", "1", "2", "3", "4+"]))
    print("\n  O an yükseliş kaç saattir sürüyordu → sonra:")
    print(fmt(tab(k.groupby("kac_saattir", observed=True))).to_string())
    print("\n  O an hızlanma kaç saattir sürüyordu → sonra:")
    print(fmt(tab(k.groupby("hizlanma_kac_saattir", observed=True))).to_string())
    print("\n  İvme puanı (LC) → sonra:")
    print(fmt(tab(k.groupby("lc_at"))).to_string())
    g = k.dropna(subset=["gated"])
    if len(g):
        print("\n  Bot çalışırken: şart sağlandı mı (1) → sonra:")
        print(fmt(tab(g.groupby("gated"))).to_string())
    print("\n  Tüm coinler:")
    print(fmt(tab(m.assign(hepsi="hepsi").groupby("hepsi"))).to_string())


def label_effect(db) -> None:
    """06.11 kullanıcı ("b ekle ve test et etkileyip etkilemediğini"): "short kapatma + spotsuz" yükselişe girmeme kuralı.
    Ölçü (iki grupta aynı): coinin sonraki 1 saatteki getirisi (bir sonraki saatin r_t'si) ve 24 saati dolunca outcomes
    tablosundan sonraki 4/24 sa, +%3'e / −%6'ya değme payı. 95% aralık = ort ± 1,96 × std / √n."""
    try:
        L = pd.read_sql("select * from labels", db)
        o = pd.read_sql("select ts, sym, fwd_4, fwd_24, hours_to_up3, hours_to_dn6 from outcomes", db)
    except Exception:  # noqa: BLE001
        return
    if not len(L):
        print("\n== Etiket etkisi: henüz kayıt yok")
        return
    # 06.11 12:45'ten beri labels HER DAKİKA (kayan pencere). sonra_1sa = 60 dk sonraki satırın r_t'si (sonraki 60 dk getirisi).
    # Ardışık dakikalar neredeyse aynı ölçümdür (örtüşen pencereler): "yükselen tüm coinler" grupları yalnız SAAT BAŞI
    # satırlarından (eskisi gibi saatte bir örnek); seçim grupları (atlatılan / girilen) her coin için saatte en fazla bir kez.
    nxt = L[["ts", "sym", "r_t"]].assign(ts=lambda d: d.ts - 3_600_000).rename(columns={"r_t": "sonra_1sa"})
    m = L.merge(nxt, on=["ts", "sym"], how="left").merge(o, on=["ts", "sym"], how="left")
    up = m[(m.r_t > 0) & (m.ts % 3_600_000 == 0)]
    print(f"\n== Etiket etkisi (kural: short kapatma + spotsuz → girme; {pd.Timestamp(int(L.ts.min()), unit='ms')} → "
          f"{pd.Timestamp(int(L.ts.max()), unit='ms')}, yükselen {len(up)} coin-saat)")

    def tab(g):
        def ci(x):
            x = x.dropna()
            return 1.96 * x.std() / np.sqrt(len(x)) if len(x) > 1 else np.nan
        d = g.agg(n=("sym", "size"), n_1sa=("sonra_1sa", "count"), sonra_1sa=("sonra_1sa", "mean"),
                  arti_eksi=("sonra_1sa", ci), n_24sa=("fwd_24", "count"), sonra_4sa=("fwd_4", "mean"),
                  sonra_24sa=("fwd_24", "mean"),
                  yuzde3_oldu=("hours_to_up3", lambda x: x.notna().sum()),
                  eksi6_oldu=("hours_to_dn6", lambda x: x.notna().sum()))
        n24 = d["n_24sa"].replace(0, np.nan)
        d["yuzde3_oldu"] = d["yuzde3_oldu"] / n24
        d["eksi6_oldu"] = d["eksi6_oldu"] / n24
        for c in ("sonra_1sa", "arti_eksi", "sonra_4sa", "sonra_24sa", "yuzde3_oldu", "eksi6_oldu"):
            d[c] = (100 * d[c]).round(3)
        return d
    print("  (yüzdeler %; arti_eksi = sonra_1sa'nın 95% aralığı; yuzde3/eksi6 yalnızca 24 saati dolanlarda)")
    print("\n  Etikete göre (yükselen tüm coinler):")
    print(tab(up.groupby("label")).to_string())
    print("\n  Kural engeli (1) / değil (0), yükselen tüm coinler:")
    print(tab(up.groupby("block")).to_string())
    pick = m[(m.blocked == 1) | (m.chosen == 1)].assign(grup=lambda d: np.where(d.blocked == 1, "kural_atlatti", "bot_girdi"))
    pick = pick.sort_values("ts").assign(_h=lambda d: d.ts // 3_600_000).drop_duplicates(["sym", "grup", "_h"])
    if len(pick):
        print("\n  Seçim sırasında: kuralın atlattığı coinler / botun girdiği coinler:")
        print(tab(pick.groupby("grup")).to_string())

    def verdict(a, b, name):
        a, b = a.dropna(), b.dropna()
        if len(a) < 30 or len(b) < 30:
            print(f"  {name}: henüz az kayıt ({len(a)} / {len(b)}; her grupta en az 30 gerekir), karar verme")
            return
        d = a.mean() - b.mean()
        se = np.sqrt(a.var() / len(a) + b.var() / len(b))
        word = "FARK VAR" if abs(d) > 1.96 * se else "fark gürültü içinde"
        print(f"  {name}: engelli − diğer = {100 * d:+.3f}% ± {100 * 1.96 * se:.3f}% → {word}")
    print("\n  Sonuç (sonraki 1 saat):")
    verdict(up.loc[up.block == 1, "sonra_1sa"], up.loc[up.block == 0, "sonra_1sa"], "yükselen tüm coinler")
    verdict(pick.loc[pick.grup == "kural_atlatti", "sonra_1sa"] if len(pick) else pd.Series(dtype=float),
            pick.loc[pick.grup == "bot_girdi", "sonra_1sa"] if len(pick) else pd.Series(dtype=float),
            "atlatılan vs girilen")


if __name__ == "__main__":
    main()
