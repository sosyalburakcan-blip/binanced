# -*- coding: utf-8 -*-
"""
Bağımsız kontrol betiği (Spesifikasyon v3, "Zorunlu testler" madde 6).

Bu betik SADECE şu iki kaynaktan yazılmıştır:
  * "Trend Takip Sistemi Spesifikasyon v3 (tek kaynak).md"
  * data/merged/1d ve data/merged/1h altındaki parquet dosyaları
Motor koduna (src/), testlere, raporlara, ayar ve meta dosyalarına bakılmamıştır.

Her varlık için tek coinlik basit bir kontrol portföyü kurulur:
  * Sinyal: üç EMA (20/50/100), h = 0,5 tamponlu durum makinesi, S = ortalama.
  * Tutma: S > 0 ise coin tutulmak istenir; yeni giriş sadece pazar kapanışındaki
    kararla (dolum pazartesi), çıkış her gün.
  * Tutulurken ağırlık %100, değilse %100 nakit (%0 getiri).
  * Dolum: t+1 günü 00:00–02:00 UTC VWAP'ı (1 saatlik mumlardan), kayma + %0,10 komisyon.

Çalıştırma (proje kökünden):
    python -m uv run python independent/check.py

Çıktı: independent/out/{VARLIK}.csv. Yorumlama kararları independent/README.md'de.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Sabitler (hepsi spesifikasyondan; kaynak cümleler README.md'de)
# ---------------------------------------------------------------------------
KOK = Path(__file__).resolve().parent.parent
GUNLUK_DIZIN = KOK / "data" / "merged" / "1d"
SAATLIK_DIZIN = KOK / "data" / "merged" / "1h"
CIKTI_DIZIN = Path(__file__).resolve().parent / "out"

SON_GUN = pd.Timestamp("2023-12-31")                  # geliştirme döneminin son günü
SON_AN = pd.Timestamp("2023-12-31 23:59:59.999999")   # bundan sonraki hiçbir satır okunmaz

# Varlık -> likidite kademesi (görev tanımı: BTC/ETH = A, diğerleri = B)
VARLIKLAR = {
    "BTCUSDT": "A",
    "ETHUSDT": "A",
    "SOLUSDT": "B",
    "LINKUSDT": "B",
    "KAIAUSDT": "B",
    "LUNAUSDT_until_20220513": "B",
    "FTTUSDT": "B",
}

VADELER = (20, 50, 100)        # EMA vadeleri
H = 0.5                        # tampon çarpanı (temel ayar)
MIN_TEMIZ_BAR = 200            # sinyal üretmek için gereken temiz bar sayısı
TABAN = 0.30                   # yıllık oynaklık tabanı
YILLIK = math.sqrt(365)        # yıllıklandırma çarpanı
KOMISYON = 0.0010              # her yönde %0,10
DELIST_CEZASI = 0.05           # temel delist cezası %5
KAYMA_A = 0.0005               # A kademesi kayması (her yönde)
KAYMA_BILINMIYOR = 0.0020      # kademe hesaplanamazsa en kötümser B kayması
PAZAR = 6                      # pandas day_of_week: pazartesi=0 ... pazar=6


def kayma_b(medyan_likidite: float) -> float:
    """B kademesi kayması: 30 günlük medyan likiditeye (USDT) göre."""
    if medyan_likidite >= 100e6:
        return 0.0005
    if medyan_likidite >= 20e6:
        return 0.0010
    return 0.0020


# ---------------------------------------------------------------------------
# Veri okuma (2024 ve sonrası satırlar parquet filtresiyle hiç yüklenmez)
# ---------------------------------------------------------------------------
def gunluk_oku(varlik: str) -> pd.DataFrame:
    df = pd.read_parquet(GUNLUK_DIZIN / f"{varlik}.parquet",
                         filters=[("open_time", "<=", SON_AN)])
    assert (df["open_time"] <= SON_AN).all()
    df = df.sort_values("open_time").reset_index(drop=True)
    df["tarih"] = df["open_time"].dt.normalize()
    assert (df["open_time"] == df["tarih"]).all(), "günlük mum 00:00 UTC'de açılmıyor"
    assert not df["tarih"].duplicated().any(), "tekrarlanan günlük kayıt"
    return df.set_index("tarih")


def saatlik_oku(varlik: str) -> pd.DataFrame:
    df = pd.read_parquet(SAATLIK_DIZIN / f"{varlik}.parquet",
                         filters=[("open_time", "<=", SON_AN)],
                         columns=["open_time", "volume", "quote_volume"])
    assert (df["open_time"] <= SON_AN).all()
    return df.sort_values("open_time").reset_index(drop=True)


def dolum_vwap(saatlik: pd.DataFrame) -> pd.Series:
    """Her gün için dolum fiyatı: 00:00–02:00 UTC arasında açılan 1 saatlik mumların
    VWAP'ı = Σ quote_volume / Σ volume. Pencerede hacim sıfırsa (veya mum yoksa)
    pencere birer saat uzatılır ("bir sonraki saat kullanılır"); gün içinde hiç hacim
    yoksa o gün dolum fiyatı yoktur (NaN)."""
    s = saatlik.copy()
    s["tarih"] = s["open_time"].dt.normalize()
    s["saat"] = (s["open_time"] - s["tarih"]) / pd.Timedelta(hours=1)
    sonuc = {}
    for tarih, grup in s.groupby("tarih"):
        bitis = 2.0
        while bitis <= 24.0:
            pencere = grup[grup["saat"] < bitis]
            hacim = pencere["volume"].sum()
            if hacim > 0:
                sonuc[tarih] = pencere["quote_volume"].sum() / hacim
                break
            bitis += 1.0
    return pd.Series(sonuc, dtype=float)


def dondur(seri: pd.Series, gercek: pd.Series) -> pd.Series:
    """Boşluk günlerinde değeri son gerçek günün değerinde dondurur
    (son gerçek gün NaN ise boşlukta da NaN kalır)."""
    return seri.where(gercek).groupby(gercek.cumsum()).transform("first")


# ---------------------------------------------------------------------------
# Tek varlık hesabı
# ---------------------------------------------------------------------------
def varlik_hesapla(varlik: str, kademe: str) -> pd.DataFrame:
    gunluk = gunluk_oku(varlik)
    saatlik = saatlik_oku(varlik)

    ilk_bar = gunluk.index.min()
    son_bar = gunluk.index.max()                 # filtre nedeniyle <= SON_GUN
    # Seri geliştirme döneminin sonundan önce bitiyorsa delist edilmiş sayılır
    # (spesifikasyon: "Backtestte son mumun tarihi kullanılır").
    delist = son_bar < SON_GUN

    # Takvim: ilk bardan son bara kadar her gün bir satır; eksik günler = boşluk
    takvim = pd.date_range(ilk_bar, son_bar, freq="D", name="date")
    g = gunluk.reindex(takvim)
    gercek = g["close"].notna()                  # o gün gerçek bir mum var mı
    kapanis = g["close"].ffill()                 # boşlukta son fiyat taşınır
    yarim_gun = g["half_day"].eq(True)

    # --- Temiz bar sayacı -------------------------------------------------
    # Temiz bar = gerçek mum, yarım gün değil, art arda 3+ günlük sıfır hacim
    # döneminin parçası değil.
    sifir = g["volume"].eq(0) | g["number_of_trades"].eq(0)
    blok = (sifir != sifir.shift()).cumsum()
    uzun_sifir = sifir & (sifir.groupby(blok).transform("size") >= 3)
    temiz = gercek & ~yarim_gun & ~uzun_sifir
    temiz_sayac = temiz.cumsum()
    uygun = temiz_sayac >= MIN_TEMIZ_BAR

    # --- EMA'lar: close.ewm(span=n, adjust=False) sadece gerçek barlar üzerinde;
    # boşluk günlerinde son değerde donar.
    ema = {}
    for n in VADELER:
        e = gunluk["close"].ewm(span=n, adjust=False).mean()
        ema[n] = e.reindex(takvim).ffill()

    # --- Oynaklık ----------------------------------------------------------
    # Günlük log getiri takvim üzerinde; boşluğa komşu getiriler NaN ("dolu değil").
    logret = np.log(g["close"]).diff()
    rv30_g = dondur(logret.rolling(30, min_periods=20).std(), gercek)   # günlük
    rv90_g = dondur(logret.rolling(90, min_periods=60).std(), gercek)   # günlük
    sigma_d = rv30_g                                  # tampon için günlük σ_d
    rv30 = rv30_g * YILLIK
    rv90 = rv90_g * YILLIK
    sigma = np.maximum(np.maximum(rv30, rv90), TABAN)  # biri NaN ise NaN

    # --- Kayma ---------------------------------------------------------------
    if kademe == "A":
        kayma_karar = pd.Series(KAYMA_A, index=takvim)
    else:
        # Likidite = USDT çiftinin quote hacmi; işlem görmeyen gün = 0.
        likidite = g["quote_volume"].fillna(0.0)
        medyan30 = likidite.rolling(30, min_periods=1).median()
        ay_sonu = takvim.is_month_end
        # Ay sonu kapanışında belirlenir, o kapanıştaki karardan itibaren bir ay geçerli
        kayma_karar = medyan30[ay_sonu].map(kayma_b).reindex(takvim).ffill()
    # t günündeki dolum, t-1 kapanışındaki kararın kademesini kullanır
    kayma_dolum = kayma_karar.shift(1).fillna(KAYMA_BILINMIYOR)

    # --- Dolum fiyatı ------------------------------------------------------
    vwap = dolum_vwap(saatlik).reindex(takvim)

    # --- Ham (tamponsuz) sinyal: ortalama_n 1[C > EMA_n]; uygun olmadan NaN
    ham = sum((kapanis > ema[n]).astype(float) for n in VADELER) / len(VADELER)
    ham = ham.where(uygun.cummax())   # ilk uygun günden sonra (boşlukta donar)

    # --- Günlük döngü: durum makinesi + tek coinlik portföy ----------------
    N = len(takvim)
    C = kapanis.to_numpy()
    E = {n: ema[n].to_numpy() for n in VADELER}
    SD = sigma_d.to_numpy()
    G = gercek.to_numpy()
    U = uygun.to_numpy()
    VW = vwap.to_numpy()
    KY = kayma_dolum.to_numpy()
    PZ = (takvim.day_of_week == PAZAR)

    s = {n: np.nan for n in VADELER}          # vade bazında tamponlu durum
    s_kayit = {n: np.full(N, np.nan) for n in VADELER}
    durum = np.full(N, np.nan)                # S = ortalama_n s_n
    hedef = np.zeros(N, dtype=int)            # t kapanışındaki karar (t+1'de dolar)
    tutulan = np.zeros(N, dtype=int)          # t kapanışında elde coin var mı
    islem = np.zeros(N, dtype=int)            # t günü dolum: +1 alış, -1 satış, -2 delist satışı
    islem_px = np.full(N, np.nan)             # kayma dahil gerçekleşen fiyat
    nav = np.zeros(N)                         # birincil: alımda tüm nakit kullanılır
    nav_adet = np.zeros(N)                    # varyant: Adet = NAV(t-1)/kapanış(t-1)

    nakit, adet = 1.0, 0.0
    nakit2, adet2 = 1.0, 0.0
    poz = 0
    baslatildi = False
    onceki_hedef = 0

    for i in range(N):
        # 1) t-1 kapanışındaki kararı t günü VWAP'ından gerçekleştir
        #    (boşluk günü veya dolum fiyatı yoksa işlem yapılmaz)
        if G[i] and not np.isnan(VW[i]) and onceki_hedef != poz:
            if onceki_hedef == 1:                       # alış (giriş)
                px = VW[i] * (1 + KY[i])
                adet = nakit / (px * (1 + KOMISYON))
                nakit = 0.0
                hedef_adet = nav_adet[i - 1] / C[i - 1]
                adet2 = min(hedef_adet, nakit2 / (px * (1 + KOMISYON)))
                nakit2 -= adet2 * px * (1 + KOMISYON)
                poz, islem[i] = 1, 1
            else:                                       # satış (çıkış her zaman tam)
                px = VW[i] * (1 - KY[i])
                nakit += adet * px * (1 - KOMISYON)
                nakit2 += adet2 * px * (1 - KOMISYON)
                adet = adet2 = 0.0
                poz, islem[i] = 0, -1
            islem_px[i] = px

        # 2) Delist kuralı: son işlem günü hâlâ tutuluyorsa o günün VWAP'ı × (1 − ceza)
        if delist and i == N - 1 and poz == 1:
            taban_px = VW[i] if not np.isnan(VW[i]) else C[i]   # VWAP yoksa son fiyat
            px = taban_px * (1 - KY[i]) * (1 - DELIST_CEZASI)
            nakit += adet * px * (1 - KOMISYON)
            nakit2 += adet2 * px * (1 - KOMISYON)
            adet = adet2 = 0.0
            poz, islem[i] = 0, -2
            islem_px[i] = px

        # 3) t kapanışında değerle (boşlukta taşınan son fiyatla)
        nav[i] = nakit + adet * C[i]
        nav_adet[i] = nakit2 + adet2 * C[i]
        tutulan[i] = poz

        # 5) t kapanışına kadarki veriyle karar
        if not G[i]:
            # Boşluk: sinyal ve hedef donar
            hedef[i] = onceki_hedef
        elif not U[i]:
            # Henüz 200 temiz bar yok: sinyal yok, pozisyon yok
            hedef[i] = 0
        elif not baslatildi:
            # İlk uygun gün: tamponsuz kural (C > EMA ise 1)
            for n in VADELER:
                s[n] = 1 if C[i] > E[n][i] else 0
            baslatildi = True
            hedef[i] = 1 if (sum(s.values()) > 0 and PZ[i]) else 0
        elif np.isnan(SD[i]):
            # σ_d hesaplanamıyor (30 günün 20'si dolu değil): karar donar
            hedef[i] = onceki_hedef
        else:
            for n in VADELER:
                ust = E[n][i] * (1 + H * SD[i])
                alt = E[n][i] * (1 - H * SD[i])
                if C[i] > ust:
                    s[n] = 1
                elif C[i] < alt:
                    s[n] = 0
                # aksi halde önceki durum korunur
            S = sum(s.values()) / len(VADELER)
            if S == 0:
                hedef[i] = 0                  # çıkış: her gün
            elif poz == 1:
                hedef[i] = 1                  # tutmaya devam
            elif PZ[i]:
                hedef[i] = 1                  # yeni giriş: sadece pazar kapanışı
            else:
                hedef[i] = 0

        if delist and i == N - 1:
            hedef[i] = 0                      # seri bitti, sonraki gün yok

        if baslatildi:
            for n in VADELER:
                s_kayit[n][i] = s[n]
            durum[i] = sum(s.values()) / len(VADELER)
        onceki_hedef = hedef[i]

    # --- Çıktı tablosu -------------------------------------------------------
    out = pd.DataFrame(index=takvim)
    out["close"] = kapanis
    for n in VADELER:
        out[f"ema{n}"] = ema[n]
    out["signal_raw"] = ham
    out["state"] = durum
    out["held"] = tutulan
    out["sigma"] = sigma
    out["fill_px"] = vwap
    nav_s = pd.Series(nav, index=takvim)
    out["ret_net"] = nav_s.pct_change().fillna(0.0)
    out["nav"] = nav_s
    # Ek kolonlar
    out["gap"] = (~gercek).astype(int)
    out["half_day"] = yarim_gun.astype(int)
    out["clean_bars"] = temiz_sayac.astype(int)
    out["eligible"] = uygun.astype(int)
    out["sunday"] = PZ.astype(int)
    for n in VADELER:
        out[f"s{n}"] = s_kayit[n]
    out["sigma_d"] = sigma_d
    out["rv30"] = rv30
    out["rv90"] = rv90
    out["target"] = hedef
    out["trade"] = islem
    out["exec_px"] = islem_px
    out["slippage"] = kayma_dolum
    nav2_s = pd.Series(nav_adet, index=takvim)
    out["ret_net_adet"] = nav2_s.pct_change().fillna(0.0)
    out["nav_adet"] = nav2_s
    out["delisted"] = int(delist)
    out = out.reset_index()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    assert out["date"].max() <= "2023-12-31"
    return out


def ozet(varlik: str, df: pd.DataFrame) -> str:
    uygun = df[df["eligible"] == 1]
    ilk_uygun = uygun["date"].iloc[0] if len(uygun) else "-"
    girisler = int((df["trade"] == 1).sum())
    cikislar = int((df["trade"] < 0).sum())
    tutma_orani = df.loc[df["eligible"] == 1, "held"].mean() if len(uygun) else float("nan")
    return (f"{varlik:<26} satır={len(df):5d}  {df['date'].iloc[0]}..{df['date'].iloc[-1]}  "
            f"ilk_uygun={ilk_uygun}  giriş={girisler:3d}  çıkış={cikislar:3d}  "
            f"tutma={tutma_orani:6.1%}  nav={df['nav'].iloc[-1]:.4f}  "
            f"nav_adet={df['nav_adet'].iloc[-1]:.4f}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")   # Windows konsolunda Türkçe karakterler
    t0 = time.perf_counter()
    CIKTI_DIZIN.mkdir(parents=True, exist_ok=True)
    for varlik, kademe in VARLIKLAR.items():
        df = varlik_hesapla(varlik, kademe)
        assert np.isfinite(df["nav"]).all() and np.isfinite(df["nav_adet"]).all()
        df.to_csv(CIKTI_DIZIN / f"{varlik}.csv", index=False)
        print(ozet(varlik, df))
    print(f"Süre: {time.perf_counter() - t0:.1f} sn")


if __name__ == "__main__":
    main()
