"""v9 demo botu: ivme + emir defteri puanı, karar 5 DK'DA BİR (06.11 ~18:05'ten beri; son 60 dk, uçlar 5 dk ortalaması, bant ±%0,2),
coin listesi her dakika 24 sa hacme göre ilk 30, 1 saatlik oynaklığı ≤ %2, en fazla 4 pozisyon. Değişiklik 27 (08.11 ~07:10 TR):
giriş şartı PİYASA (listedeki coinlerin ortalaması) son 30 dk ≥ +%0,10, en az 20 coin artıda, son 5 dk artıda, son 30 dk'nın
tepesinden en çok %0,10 aşağıda, sıçrama değil (Değ. 28: son 2 dk ≤ 30 dk yükselişin yarısı) + LC ≥ 2; fiyat adımı > %0,1
coine girilmez (Değ. 25);
pozisyon 1.500 $ sabit, kâr al net +5 $, borsada −5 $ zarar stopu,
"ivme sürüyor mu ve kârda mıyız" kontrolü (girişten 60 dk sonra başlar, 5 dk'da bir; Değ. 29: kârda değil ama coin
yükseliyorsa 3 ek kontrol, en geç 75. dk).
Değişiklik 30 (08.11 ~10:00 TR): SHORT da açılır — piyasa şartlarının aynası (son 30 dk ≤ −%0,10, ≥ 20 coin ekside, son 5 dk
ekside, 30 dk dibinden ≤ %0,10 yukarıda, düşüş sıçrama değil) + LC_DN ≥ 2; her kararda en çok bir yön, 4 yuva ortak. Girişte
coinin son 60 dk hareketinin yarısından fazlası tek 2 dk sıçramasından geldiyse girilmez; açık pozisyonda son 2 dk işlemin
tersine ≥ %0,20 ise hemen kapatılır (ters_sıçrama).
Kurallar: v9live/KURALLAR.md. YALNIZCA DEMO (demo-fapi.binance.com).

    /root/binanced/.venv/bin/python v9live/bot.py            # çalıştır
    /root/binanced/.venv/bin/python v9live/bot.py --dry      # yalnızca şu dakikanın ölçümü + puanı (dry_run.db), emir yok
"""

from __future__ import annotations

import argparse
import json
import lzma
import math
import shutil
import signal
import sqlite3
import sys
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path("/root/binanced")
sys.path.insert(0, str(ROOT / "src"))
from trend.live.notify import Notifier  # noqa: E402
from trend.live.testnet import ExchangeError, SignedRest, read_env  # noqa: E402

HERE = ROOT / "v9live"
REAL, DEMO = "https://fapi.binance.com", "https://demo-fapi.binance.com"
SPOT = "https://api.binance.com"     # yalnızca herkese açık spot mum verisi (etiket için), emir yok
# 06.11 ~11:40 kullanıcı ("b ekle"): yükseliş "short kapatma + spotsuz" ise GİRME, yuva sıradakine. Tanım (son kapanan saat):
# fiyat r_t > 0 VE açık pozisyon adedi OI_1 < 0 VE SPOT_REL_1 < 1 (spot/vadeli $ hacim oranı, kendi önceki 168 saatlik
# ortancasının altında). Spotu olmayan coin (Q, JCT, AGT) ya da ölçülemeyen değer → kural uygulanmaz.
SPOT_FILTER_ON = True
NOTIONAL, SLOTS, LEV = 1500.0, 4, 10    # 06.11 ~14:05 kullanıcı: "açılan işlem sayısını anlık 4 olarak ayarla" (11:50–14:05: 8, önce 3)
# 06.11 ~14:05 kullanıcı: "açılan işlem −5 dolar zarar açıklayınca hemen emir koy ve satış bekle" + seçim "borsaya baştan stop emri",
# "açık pozisyonlara da". Büyük işlemde zarar stopu borsada STOP_MARKET closePosition, MARK_PRICE (Binance'in gösterdiği
# gerçekleşmemiş zarar): tetik = giriş − STOP_USD / adet (tick'e YUKARI yuvarlanır → tetikte zarar ≤ 5 $). Kısmi dolumda adet
# küçükken bu seviye çok uzak/negatif olabilir → hiçbir zaman −%6'dan uzak değil: tetik = max(−5 $ seviyesi, giriş × 0,94).
# Gerçekleşen kayıp piyasa emri ücreti (≈0,6–0,75 $) + giriş ücreti + kayma ile ≈ −6…−7 $ (kullanıcıya söylendi).
# 06.11 ~18:05 kullanıcı: "stop loss −12 dolar olsun" → STOP_USD 5 → 12 (1.500 $'da fiyatta ≈ −%0,8; gerçekleşen ≈ −13…−14 $).
# Kâr al net +5 $ aynı → başa baş için kazanma oranı ≈ %72 gerekir, kayıplar stoptan gelirse (kullanıcıya söylendi).
# 07.11 ~21:00 TR Değişiklik 24 (kullanıcı: "o zaman toplam zarar yazmamızın nedeni stoploss koymayışımız" + seçim "−5 $"):
# STOP_USD 12 → 5 (1.500 $'da fiyatta ≈ −%0,33; gerçekleşen ≈ −6 $). Tetik = max(giriş − 5 $ / dolan adet, giriş × 0,94).
STOP_USD = 5.0
# 06.11 ~14:05 kullanıcı seçimi "listeyi yeniden kur": coin listesi her dakika = TÜM USDT sürekli vadeli coinlerden (gerçek piyasa)
# Binance 24 sa değişimi > 0 olanların 24 sa USDT hacmine göre ilk UNI_N'i; demo'da TRADING olmayan/filtresi olmayan ve sabit
# coinler alınmaz (önce: geçen ayın hacmine göre sabit 30 coin, universe_YYYY-MM.json).
UNI_N = 30
# 07.11 ~04:40 UTC kullanıcı seçimi "Bugünün en büyük 30'u": '24 sa artıda' şartı KALKTI (listede de girişte de);
# liste = 24 sa USDT hacmine göre ilk UNI_N (VOL60 ≤ %2 sınırı sürer). True = eski (06.11 14:13–07.11) davranış.
UNI_REQUIRE_UP = False
# 06.11 ~18:05 kullanıcı seçimi "oynaklık sınırı ekle": listeye yalnızca VOL60 ≤ %2 olan coin alınır, büyükse yerine hacimde sıradaki
# girer. VOL60 = son 1.500 dk'nın 1 dk kapanışlarıyla, üst üste binen 60 dk getirilerinin std'si (popülasyon; "normal 1 saatlik
# oynama"). Sebep (gerçek fapi 1 dk, 05.11 18:59–06.11 17:52 UTC, o anki 30 coin): −12 $ stop = fiyatta −%0,8; pompalanmış küçük
# coinlerde (AKE +%83, CYBER, JCT, BIRB, ONE, ICNT; VOL60 %3–14) rastgele girişte 60 dk içinde −%0,8'e inme %65–91, diğerlerinde
# %3–57. Ölçülemeyen coin (en az VOL_MIN_N getiri yok: yeni listelenmiş / mum eksik) alınmaz. 5 dk önbellek.
VOL_MAX, VOL_EVERY_MS, VOL_MIN_N = 0.02, 5 * 60_000, 1380
STABLES = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "USDE", "USD1", "BUSD", "PYUSD", "RLUSD", "XUSD", "USDS", "EUR", "EURI",
           "AEUR", "USDT", "BFUSD", "USTC"}
# büyüklük: 06.11 10:35 kullanıcı: "işlem teminatı 150 dolar" → pozisyon 1.500 $, 10×; öncesi 150 $ / 10× (teminat 15 $), ondan önce 100 $ / 1×
TP, ESTOP = 0.03, 0.06
# 06.11 ~11:48 kullanıcı: "150 dolar teminatlı büyük işlemde 5 dolar kâr yeterli olur" → hedef büyüklüğü ≥ 1.000 $ olan
# pozisyonda kâr al fiyatı = ücretler (giriş maker + kâr al maker) düşüldükten sonra NET +5 $ (1.500 $'da ≈ +%0,37).
# Küçük (eski 100 $ / 150 $) pozisyonlar +%3'te kalır.
TP_NET_USD, BIG_NOTIONAL = 5.0, 1000.0
# 06.11 ~19:00 UTC kullanıcı seçimleri (sebepleri tersine çevir: "tepeden alma", "alış emri düşüşte doluyor", "4 işlem tek bahis",
# "sinyal saatlik, sonuç dakikalık"):
# (1) "Oynaklığa göre, en çok −12 $": kâr al = giriş × (1 + BRACKET_K × VOL60), zarar stopu = giriş × (1 − BRACKET_K × VOL60)
#     (eşit mesafe = coinin normal 1 saatlik oynaması; ufuk sinyalle aynı). Pozisyon = min(NOTIONAL, RISK_USD / (BRACKET_K × VOL60))
#     → stopta fiyat kaybı en çok RISK_USD (komisyon ayrı). Ör. VOL60 %0,9 → 1.333 $, ±%0,9 ≈ ±12 $; %0,5 → 1.500 $, ±7,5 $.
#     Mesafe yüzde olduğu için kısmi dolumda da aynı (kayıp dolan payla küçülür). Başa baş ≈ %53 kazanma (komisyonlar).
# (2) "Geri çekilmede al": sinyal anındaki demo en iyi alışın PULLBACK (%0,2) altına SABİT post-only alış; yukarı KOVALANMAZ;
#     15 dk'da dolmazsa ya da bir karar anında trend bozulursa (piyasa son 30 dk ≤ 0 [08.11 Değ. 26; önce son 4 sa ≤ 0], LC < 2
#     ya da son 60 dk < −BAND) iptal.
# (3) "5 dk'da en fazla 1 giriş": MAX_NEW_PER_TICK.
# (4) "Eski kurallarıyla bitsin": Pos.vol = 0 olan (bu değişiklikten önce açılmış) pozisyonlar eski kâr al/stop ile sürer.
RISK_USD, BRACKET_K, PULLBACK, MAX_NEW_PER_TICK = 12.0, 1.0, 0.002, 1
# 07.11 ~04:40 UTC kullanıcı seçimi "Hemen al (eski hâli)": giriş yeniden sinyal anındaki demo en iyi alışa post-only, alış
# yükselirse REPRICE_S'de bir yukarı taşınır (kovalama), 15 dk sınırı (22:00 TR öncesi gibi). Sebep: geri çekilme alışı ortanca
# ~1 dk → ~5 dk dolum, 3 yarım dolum. PULLBACK yalnız ENTRY_CHASE=False iken kullanılır. Oynaklığa göre büyüklük ve ±VOL60 kâr al/
# stop AYNEN sürer (Pos.vol > 0); pb_px = 0 → geri çekilme iptali ve sabit fiyat yolu çalışmaz.
ENTRY_CHASE = True
_cost = json.loads((ROOT / "v9" / "data" / "costs.json").read_text())["used"]
MAKER, TAKER = float(_cost["maker"]), float(_cost["taker"])
PROTECT = 1 + 2 * (MAKER + TAKER)                    # 2× masraf: giriş × 1,0014 (saatlik "kârda mıyız" eşiği)
PROTECTION_ON = False   # kullanıcı 06.11 06:37: 2× masraf koruma EMRİ iptal ("1 saat içinde fiyatta salınım olabilir,
                        # araştırılmalı"). Backtest: bu koruma işlemlerin %95'ini ortanca 11 dk'da kapatmıştı.
# 07.11 19:03 TR Değişiklik 23 (kullanıcı: "botun her girdiği işleme direkt +5 dolar karını hesaplayıp direkt emir koyulsun ve
# stoploss kaldırılsın"; seçimler: 60 dk kontrolü KALSIN, açık TA da geçsin): kâr al = komisyonlar (giriş maker + kâr al maker)
# düşüldükten sonra NET +TP_NET_USD (5 $; fonlama hariç, önceden bilinmez), dolan adede göre, yukarı tick. Zarar stopu emri
# (±VOL60 ve −%6 taban) HİÇ konmaz; açık pozisyonun borsadaki stopu iptal edilir. Zarardaki işlemi yalnız 60 dk kontrolü kapatır;
# ondan önce ~−%9'da borsa tasfiye eder (10× tek yönlü). Pozisyon büyüklüğü min(1.500, 12/VOL60) ve 60 dk kontrolü aynen.
# 07.11 ~21:00 TR Değişiklik 24: zarar stopu YENİDEN VAR (STOP_ON = True, −STOP_USD = −5 $, MARK_PRICE). Kâr al net +5 $ aynen.
# Büyüklük sabit NOTIONAL (1.500 $; SIZE_BY_VOL = False → 12 $ / VOL60 kullanılmaz). Yeni pozisyonda Pos.vol = 0 → ±VOL60
# kâr al/stop yolu (volmode) çalışmaz; VOL60 yalnız feats'e yazılır.
TP_NET_ALL, STOP_ON = True, True
SIZE_BY_VOL = False
WIN = (2, 3, 4, 5, 6, 8, 12)
ENTRY_TIMEOUT_S, REPRICE_S, DEPTH_EVERY_S, MIN_DELAY_S, MONITOR_S = 900, 30, 60, 12, 5
# 06.11 13:22–13:23 ölçüm (gerçek fapi, 30 coin, 2 dakika): kapanan 1 dk mum REST'te +3 sn'de 11–13 coinde kapanışı, 16–19 coinde
# en az bir alanı kesin değerden FARKLI; +5 sn 1–3 coin; +8 sn 0. MIN_DELAY_S 3 → 12 (verify.py 12:50–13:19 dakikalarında
# r_t/RET_4/TAKER_1/SMOOTH_4 farkı ve 13:19'da LC farkı buldu). Saatlik modda bekleme 10 sn'ydi.
# 06.11 12:45 kullanıcı: "her saat başı yenilenmesin, her dk 1 saatlik pencere olsun, kayar pencere" → karar her dakika
# (dakika kapanışından MIN_DELAY_S sn sonra), tüm pencereler o dakikadan geriye: "1 saat" = son 60 dk, "N saat" = son N×60 dk.
# Açık pozisyon kontrolü girişten CHECK_AFTER_MS sonra başlar ve her dakika yapılır (kullanıcı seçimi).
# Satılan coine bir sonraki dakikadan itibaren yeniden girilebilir (kullanıcı seçimi: "hemen girebilir").
M = 60_000
CHECK_AFTER_MS = 3_600_000
# 08.11 ~07:55 TR Değişiklik 29 (kullanıcı: "1 saatlik kontrol … eksi değer gittikçe azalıyorsa ve coinin verileri artış yönündeyse
# işlemden çıkış yapılmasın ve … 3 kere daha kontrol etsin"; seçimler "Son 5 dk artıda", "+%0,14'te sat", "Hemen sat", "Sat (en fazla
# 75 dk)"): 60 dk kontrolü satış derken pozisyon +%0,14'ün altında AMA coin yükseliyor (son 60 dk ≥ −BAND ve son 5 dk R_5M > 0) ise
# satılmaz, GRACE_N ek kontrol verilir (65, 70, 75. dk). Ek kontrolde: kâr ≥ +%0,14 → sat (ek_kontrol_kâr); yükseliş bozuldu (son 60 dk
# < −BAND ya da son 5 dk ≤ 0) → sat (ek_kontrol_düştü); son ek kontrolde hâlâ eksi → sat (ek_kontrol_süre). Kâr al/stop borsada aynen.
GRACE_N = 3


def check_decide(grace: int, rise_ok: bool, pnl_ok: bool, up5: bool) -> tuple[bool, str, int]:
    """60 dk kontrolü kararı (Değ. 29). grace = şimdiye kadar verilen ek kontrol (0 = ek sürede değil).
    Döner: (sat mı, çıkış sebebi, yeni grace)."""
    if grace > 0:
        if pnl_ok:
            return True, "ek_kontrol_kâr", grace
        if not (rise_ok and up5):
            return True, "ek_kontrol_düştü", grace
        if grace >= GRACE_N:
            return True, "ek_kontrol_süre", grace
        return False, "", grace + 1
    if rise_ok and pnl_ok:
        return False, "", 0
    if rise_ok and up5:                                    # +%0,14 altında ama coin yükseliyor → satma, ek kontrol başlar
        return False, "", 1
    return True, "kayan_kontrol", 0
# 06.11 ~14:40 UTC kullanıcı seçimi "C" (soru: 1 dk mum oynaklığına karşı ne yapalım): kararlar YENİDEN YALNIZCA SAAT BAŞI (eski sürüm
# gibi). Ölçüm (09:32–17:32 TR, 30 coin): "son 60 dk artıda mı" saatte ortanca 4 kez değişiyor, değişimlerin %27'si 1 dk sonra geri
# dönüyor → her dakika sormak anlık sapmaya yakalatıyordu. Saat başında 1 dk mumlardan hesap = Binance 1 sa mumu (30/30 birebir).
# Liste (24 sa artıda, hacme göre ilk 30) her dakika yenilenir ama yalnızca defter görüntüleri için; karar t = saat başında.
# Saatlik kontrol eski kural: saat başından önce dolmuş her açık pozisyon o saat başında kontrol edilir (sebep saatlik_kontrol).
# Kâr al (+5 $) ve −5 $ zarar stopu borsada beklediği için sürekli çalışır. Boşalan yuva bir sonraki saat başında dolar.
# 06.11 ~18:05 UTC kullanıcı ("bu sistemi yapmak istiyorum": önerilen 5 dk + uçların ortalaması + bant): karar 5 DAKİKADA BİR
# (t = :00, :05, …, kapanıştan MIN_DELAY_S sn sonra). Gürültü ölçümü (gerçek fapi 1 dk, 05.11 18:59–06.11 17:52 UTC, 30 coin):
# "son 60 dk > 0" 5 dk'da bir ham sorulunca saatte 1,77 kez değişiyor, değişimlerin %55'i 15 dk içinde geri dönüyor; uçlar 5 dk
# ortalaması + ±%0,2 bantla 0,92 kez / %18 (saat başı 0,46). Uçların ortalaması: pencere ucu fiyatı = o anda biten SON SMOOTH_N
# adet 1 dk mum kapanışının ortalaması (LC, r_t, r_prev, ACC_1 ve SMOOTH_4'ün payı; yol uzunluğu ve R30 ham kalır).
# Bant: giriş için son 60 dk > +BAND; kontrolde son 60 dk < −BAND ise satılır (arada: önceki durum, yani pozisyon tutulur).
# Kontrol girişten CHECK_AFTER_MS (60 dk) sonra başlar, sonra her 5 dk; (b) kâr ≥ +%0,14 (anlık demo fiyatı) aynen.
# Satılan coine bir sonraki 5 dk'dan itibaren yeniden girilebilir (12:45 kullanıcı seçimi "hemen girebilir" ile aynı mantık).
# 14:39–18:05: saat başı (HOURLY_DECIDE); 12:45–14:39: her dakika ham.
DECIDE_STEP_MS = 5 * M
HOURLY_DECIDE = DECIDE_STEP_MS == 3_600_000
SMOOTH_N, BAND = 5, 0.002
# 06.11 ~13:15 kullanıcı (A): giriş şartına "son 60 dk getirisi > 0" eklenmişti (18:05'ten beri > +BAND).
# 07.11 ~21:00 TR Değişiklik 24: KAPALI (Değ. 17 "yerinde saymış" ve Değ. 18/22 akış şartlarının kodu Değ. 24'te SİLİNDİ).
ENTRY_RT_POSITIVE = False
# 08.11 ~05:40 TR Değişiklik 26 (kullanıcı: "önerini uygula"; öneri: coinin "son 4 sa > 0" şartı yerine piyasanın ŞU ANKİ yönü):
# giriş şartı = PİYASA son 30 dk artıda (MKT_30 > 0) ve LC ≥ 2. MKT_30 = o anki listedeki coinlerin (self.universe) ham son 30 dk
# getirilerinin eşit ağırlıklı ortalaması; coin başına R30 = t'de biten 1 dk mum kapanışı / t − 30 dk'da biten kapanış − 1
# (gerçek piyasa). Ölçülemeyen coin ortalamaya girmez; hiçbiri ölçülemezse giriş yok. "Son 4 sa > 0" şartı (RET_4) ve Değ. 24
# yükseliş sinyalinin kodu Değ. 26'da SİLİNDİ (07.11 gecesi sinyal hiç girmedi: sayaç 5 dk'lık, sürekli yanıp söndüğü için
# "60 dk sönük" hiç oluşmadı).
MKT_WIN_MS = 30 * 60_000
# 08.11 ~07:10 TR Değişiklik 27 (kullanıcı seçimi "Dördü de şart"; eşikler Claude'un seçimi, veriye dayanmıyor): "MKT_30 > 0"
# yerine piyasanın BÜYÜKLÜĞÜ, GENİŞLİĞİ, HIZI ve TEPEYE UZAKLIĞI. Yol: idx(m) = listedeki coinlerin c(m)/c(t−30)−1 ortalaması,
# m = t−30 … t (1 dk kapanışlar, gerçek piyasa). Şart (hepsi): MKT_30 ≥ MKT_MIN, R30 > 0 olan coin sayısı (MKT_UP) ≥ MKT_UP_MIN,
# MKT_5 = idx(t) − idx(t−5) > 0, MKT_PEAK = idx(t) − max idx ≥ −MKT_PEAK_MAX; biri ölçülemezse giriş yok.
# MKT_TOP (en büyük |R30| coinin ortalamaya katkısı = R30 / N) ve MKT_PN (yolu tam coin sayısı) yalnız kayıt.
MKT_MIN, MKT_UP_MIN, MKT_FAST_MS, MKT_PEAK_MAX = 0.001, 20, 5 * 60_000, 0.001
# 08.11 ~07:30 TR Değişiklik 28 (kullanıcı: "sıçrama şartını da ekle"; eşikler Claude'un seçimi, veriye dayanmıyor): koşu yükselişi
# 30 dk'ya yayılır, sıçrama son 1–2 dakikada gelir. MKT_JUMP = idx(t) − idx(t−2 dk); şart MKT_JUMP ≤ MKT_JUMP_SHARE × MKT_30
# (yükselişin yarısından fazlası son 2 dk'da geldiyse giriş yok → sonraki kararda sıçrama tutmuşsa diğer şartlarla yeniden bakılır).
MKT_JUMP_MS, MKT_JUMP_SHARE = 2 * 60_000, 0.5
# 08.11 ~10:00 TR Değişiklik 30 (kullanıcı: "bot aynı zamanda hem long hem de short açma kararını verecek kabiliyete getir çünkü …
# ani ters sıçramaları bilemiyoruz ya da 60 dk'lık pencere içinde bulunan sıçramaları da izleyelim"; seçimler "Girişte coin
# sıçraması", "Açıkken ters sıçramada çık", "4 yer ortak"; eşikler ve short tanımı Claude'un seçimi, veriye dayanmıyor):
# (1) SHORT: Değ. 27/28 piyasa şartının aynası — MKT_30 ≤ −MKT_MIN, R30 < 0 coin sayısı (MKT_DN) ≥ MKT_UP_MIN, MKT_5 < 0,
#     MKT_TROUGH = idx(t) − min idx ≤ +MKT_PEAK_MAX (30 dk dibinden en çok %0,10 sekmiş), MKT_JUMP ≥ MKT_JUMP_SHARE × MKT_30
#     (düşüşün yarısından fazlası son 2 dk'da değil) + coinde LC_DN ≥ 2 (LC'nin aynası: N = 2, 3, 4, … için son N×60 dk
#     düşüşte VE önceki N×60 dk'dan hızlı düşüşte). İki yönün piyasa şartı aynı anda sağlanamaz → her kararda en çok bir yön.
#     Short puanı: LC_DN, −SMOOTH_4, −TAKER_1, −IMB1_1, −BIDSHARE_1, OI_1 sıra yüzdelerinin ortalaması (OI artışı iki yönde de
#     yeni pozisyon). Giriş: demo en iyi satışa post-only SELL; satış fiyatı düşerse REPRICE_S'de aşağı taşınır; 15 dk sınırı.
#     Kâr al net +TP_NET_USD (BUY LIMIT reduceOnly, aşağı tick), zarar stopu −STOP_USD (BUY STOP_MARKET closePosition MARK_PRICE,
#     tetik = min(giriş + STOP_USD / adet → aşağı tick, giriş × 1,06 → yukarı tick)). 60 dk kontrolünün aynası: (a) son 60 dk
#     ≤ +BAND, (b) demo satış ≤ giriş × (2 − PROTECT); ek süre (Değ. 29) son 5 dk < 0 iken. "Short kapatma + spotsuz" engeli
#     yalnız long'da. 4 yuva iki yöne ortak.
# (2) GİRİŞTE COİN SIÇRAMASI: c(t−60) … c(t) ham 1 dk kapanışlarla üst üste binen 2 dk hareketleri c(k)/c(k−2)−1; en büyüğü
#     COIN_J_UP, en küçüğü COIN_J_DN; r_t_raw = c(t)/c(t−60)−1. Long: r_t_raw > 0 ve COIN_J_UP > COIN_JUMP_SHARE × r_t_raw →
#     girilmez; short: r_t_raw < 0 ve COIN_J_DN < COIN_JUMP_SHARE × r_t_raw → girilmez. Son 60 dk işlemin tersindeyse kural
#     uygulanmaz; ölçülemeyen coine girilmez. Yuva sıradakine geçer.
# (3) AÇIKKEN TERS SIÇRAMA: her dakika (kapanıştan MIN_DELAY_S sn sonra) açık pozisyonun coininde son 2 dk ham hareketi
#     c(t)/c(t−2)−1 (gerçek piyasa); yalnız pencere tamamen dolumdan sonraysa (t − 2 dk ≥ dolum). İşlemin tersine ≥ SPIKE_MAX →
#     piyasa emriyle kapatılır (ters_sıçrama). Her ölçüm spike_checks tablosunda (denetim audit/spike_check.py).
SHORT_ON = True
LONG, SHORT = "LONG", "SHORT"
COIN_JUMP_SHARE, SPIKE_MS, SPIKE_MAX = 0.5, 2 * 60_000, 0.002


def sd(side: str) -> int:
    """yön çarpanı: long +1, short −1 (eski kayıtlarda yön yok = long)"""
    return -1 if side == SHORT else 1


def market_side(m30: float, up_n: int, dn_n: int, m5: float, peak: float, trough: float, jump: float) -> str | None:
    """Değ. 27/28 (long) ve Değ. 30 (short, aynası) piyasa şartı; ölçülemeyen değer → None."""
    if not all(np.isfinite(x) for x in (m30, m5, peak, trough, jump)):
        return None
    if m30 >= MKT_MIN and up_n >= MKT_UP_MIN and m5 > 0 and peak >= -MKT_PEAK_MAX and jump <= MKT_JUMP_SHARE * m30:
        return LONG
    if SHORT_ON and m30 <= -MKT_MIN and dn_n >= MKT_UP_MIN and m5 < 0 and trough <= MKT_PEAK_MAX \
            and jump >= MKT_JUMP_SHARE * m30:
        return SHORT
    return None


def coin_spike(side: str, r60: float, j_up: float, j_dn: float) -> bool:
    """Değ. 30 (2): True = son 60 dk hareketi tek 2 dk sıçramasından (ya da ölçülemedi) → girilmez."""
    if not all(np.isfinite(float(x)) for x in (r60, j_up, j_dn)):
        return True
    d, j = sd(side), (j_up if side != SHORT else j_dn)
    return d * r60 > 0 and d * j > COIN_JUMP_SHARE * d * r60


def check_inputs(side: str, r_t: float, px: float, entry: float, r5: float) -> tuple[bool, bool, bool]:
    """60 dk kontrolünün girdileri, yöne göre (Değ. 30 aynası): (a) trend sürüyor, (b) kârda (2× masraf), son 5 dk işlem yönünde.
    px = long'da demo en iyi alış, short'ta demo en iyi satış (kapatma fiyatı)."""
    d = sd(side)
    rise_ok = bool(np.isfinite(r_t) and (d * r_t > 0 if HOURLY_DECIDE else d * r_t >= -BAND))
    pnl_ok = bool(px >= entry * PROTECT) if d > 0 else bool(0 < px <= entry * (2 - PROTECT))
    up5 = bool(np.isfinite(r5) and d * r5 > 0)
    return rise_ok, pnl_ok, up5
# 07.11 ~21:05 TR Değişiklik 25 (kullanıcı seçimi "Bu coinleri alma"): Değ. 24'ün ilk işlemi CYBER'de fiyat adımı 0,001 = fiyatın
# %0,31'i → −5 $ stop tek adım, 2 sn'de −10,27 $. Seçimde TICK_REL = demo fiyat adımı / karar anındaki son 1 dk kapanışı (gerçek
# piyasa) > TICK_MAX_REL (%0,1) olan ya da ölçülemeyen coine GİRİLMEZ, yuva sıradakine geçer.
TICK_MAX_REL = 0.001
KL_KEEP = 2900                     # bellekte tutulan 1 dk vadeli mum (≈ 48 sa 20 dk; DD_48 gözlemi 2.880 ister)
STATUS_EVERY_MS = 15 * 60_000       # demo işlem durumu (TRADING mi) 15 dk'da bir yenilenir
COMPONENTS = ("LC", "ACC_1", "SMOOTH_4", "TAKER_1", "IMB1_1", "BIDSHARE_1", "OI_1")
# 07.11 ~04:55 UTC kullanıcı: "ivme farkını puandan çıkar" → ACC_1 ölçülür ve kaydedilir ama PUANA girmez (puan = kalan 6
# bileşenin sıra yüzdelerinin ortalaması). Gerekçe lossreview/RAPOR.md: 69 işlemde kaybedenlerin ACC_1 ortancası +%0,75,
# kazananların +%0,06 (p 0,008; ~25 ölçüden biri, kanıt değil).
SCORE_EXCLUDE = ("ACC_1",)
SCORE_COMPONENTS = tuple(c for c in COMPONENTS if c not in SCORE_EXCLUDE)
H = 3_600_000
BOOK_DIR = HERE / "book"          # tam emir defteri arşivi (kullanıcı 06.11: "tam defter kayıt ve 3 saate silinmesin")
BOOK_MIN_FREE = 3 * 1024 ** 3       # diskte 3 GB'tan az boş yer kalırsa tam defter yazımı DURUR (hiçbir şey silinmez)

pub = requests.Session()
pub.headers["User-Agent"] = "v9-demo/1.0"
pub.mount("https://", requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16))


_ban_until = 0.0
_ban_lock = threading.Lock()


def pget(path: str, raw: bool = False, **params):
    """Gerçek piyasa (herkese açık) isteği. 429/418'de Retry-After kadar TÜM istekler durur; ağırlık 1.800/dk'yı
    (sınır 2.400) aşınca 20 sn yavaşlanır. 06.11: deneme modunda sınır aşılıp IP 418 aldı → bu koruma eklendi.
    raw=True: Binance'in yanıtı bayt bayt döner (tam defter arşivi için)."""
    global _ban_until
    for i in range(4):
        wait = _ban_until - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            r = pub.get(f"{REAL}{path}", params=params, timeout=15)
        except Exception:  # noqa: BLE001
            time.sleep(2 * (i + 1))
            continue
        used = int(r.headers.get("x-mbx-used-weight-1m", 0) or 0)
        if r.status_code in (418, 429):
            ra = int(r.headers.get("retry-after", 60) or 60)
            with _ban_lock:
                _ban_until = max(_ban_until, time.time() + ra + 5)
            log(f"SINIR {r.status_code}: {ra} sn tüm gerçek piyasa istekleri durdu")
            continue
        if used > 1800:
            with _ban_lock:
                _ban_until = max(_ban_until, time.time() + 20)
        if r.status_code == 200:
            return r.content if raw else r.json()
        if r.status_code in (400, 404):
            r.raise_for_status()
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"gerçek piyasa verisi alınamadı: {path} {params}")


def sget(path: str, **params):
    """Gerçek SPOT piyasa (herkese açık) isteği. 400 → None (böyle bir spot sembolü yok)."""
    for i in range(3):
        try:
            r = pub.get(f"{SPOT}{path}", params=params, timeout=15)
        except Exception:  # noqa: BLE001
            time.sleep(2 * (i + 1))
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 400:
            return None
        if r.status_code in (418, 429):
            time.sleep(min(int(r.headers.get("retry-after", 30) or 30), 60))
            continue
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"spot verisi alınamadı: {path} {params}")


def label_of(f: dict) -> tuple[str, bool]:
    """Yükseliş kimden geliyor (son kapanan saat). Dönüş: (etiket, giriş engeli mi)."""
    fin = lambda x: x is not None and np.isfinite(float(x))  # noqa: E731
    r, oi, rel = f.get("r_t"), f.get("OI_1"), f.get("SPOT_REL_1")
    if not fin(r) or float(r) <= 0:
        return "yukselis_yok", False
    who = "oi_yok" if not fin(oi) else ("short_kapatma" if float(oi) < 0 else "yeni_alici")
    spot = "spot_olcum_yok" if not fin(rel) else ("spotsuz" if float(rel) < 1 else "spotlu")
    return f"{who}+{spot}", (who == "short_kapatma" and spot == "spotsuz")


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), msg, flush=True)


# 06.11 12:15 kullanıcı: Telegram mesajları sade — kaçta girdi/çıktı, komisyon, net kâr; 🟢 giriş ve kârlı çıkış, 🔴 zararlı çıkış.
MSG_TZ = "Europe/Istanbul"                              # mesajlardaki saatler Türkiye saati (journal/DB UTC kalır)
REASON_TR = {"zarar_stop": "zarar stopu", "kayan_kontrol": "60 dk kontrolü", "ek_kontrol_kâr": "ek kontrolde kâr (+%0,14)",
             "ek_kontrol_düştü": "ek kontrolde coin ters döndü", "ek_kontrol_süre": "ek kontrol süresi doldu (75 dk)",
             "ters_sıçrama": "ters sıçrama (2 dk ≥ %0,20)", "saatlik_kontrol": "saatlik çıkış", "kâr_al": "kâr al", "acil_stop": "acil stop", "koruma": "koruma",
             "kullanici_kapatti": "elle kapatıldı", "kırıntı": "kırıntı", "piyasa": "piyasa", "bilinmiyor": "bilinmiyor",
             "tasfiye": "tasfiye (borsa kapattı)"}


def tr_num(x: float, nd: int = 2, sign: bool = False) -> str:
    return (f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}").replace(".", ",")


def tr_px(x: float) -> str:
    return f"{x:.6g}".replace(".", ",")


def tr_hm(ms: int) -> str:
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").tz_convert(MSG_TZ).strftime("%H:%M")


def tr_dur(ms: int) -> str:
    m = max(0, round(ms / 60_000))
    return (f"{m // 60} sa" + (f" {m % 60} dk" if m % 60 else "")) if m >= 60 else f"{m} dk"


# 07.11 Değişiklik 21 (yalnız KAYIT düzeltmesi; kural/karar değişmez; kullanıcı: "evet düzelt"): Binance fonlama kaydını (FUNDING_FEE)
# fonlama anından birkaç sn sonra yayımlıyor. Çıkış fonlama anından ≈ 25 sn sonra olursa (60 dk kontrolü :00'da satarsa) finalize'daki
# sorgu kaydı göremiyor, fonlama 0 yazılıyordu (ETH 07.11 00:00 UTC, ONDO 08:00 UTC: gerçek −0,15 $). Artık her kapanan işlemin fonlaması
# kapanıştan en az FUND_RECHECK_MIN_MS sonra, [dolum, çıkış] aralığında borsadan BİR KEZ yeniden okunur; farklıysa trades.funding, pnl,
# pnl_pct düzeltilir (yeniden başlatmada son FUND_RECHECK_MAX_MS içindekiler yeniden bakılır; aynıysa dokunulmaz).
FUND_RECHECK_MIN_MS, FUND_RECHECK_MAX_MS = 3 * 60_000, 3 * 3_600_000


def funding_recheck(db: sqlite3.Connection, rest, now_ms: int, done: set, lo_ms: int | None = None) -> list[dict]:
    lo = now_ms - FUND_RECHECK_MAX_MS if lo_ms is None else lo_ms
    fixes = []
    for rid, sym, fill_s, exit_s, cost, fund0, pnl0 in db.execute(
            "select rowid, sym, fill, exit, cost, funding, pnl from trades").fetchall():
        if rid in done:
            continue
        fill_ms = int(pd.Timestamp(fill_s).value // 1_000_000)
        exit_ms = int(pd.Timestamp(exit_s).value // 1_000_000)
        if exit_ms < lo or exit_ms > now_ms - FUND_RECHECK_MIN_MS:
            continue
        inc = rest.request("GET", "/fapi/v1/income", {"symbol": sym, "incomeType": "FUNDING_FEE", "startTime": fill_ms,
                                                       "endTime": exit_ms, "limit": 100})
        fund = sum(float(x["income"]) for x in inc)
        done.add(rid)
        f0 = float(fund0 or 0.0)
        if abs(fund - f0) > 1e-9:
            pnl = float(pnl0) + fund - f0
            db.execute("update trades set funding = ?, pnl = ?, pnl_pct = ? where rowid = ?",
                       (fund, pnl, pnl / cost if cost else None, rid))
            db.commit()
            fixes.append({"rowid": rid, "sym": sym, "fill": fill_s, "exit_ms": exit_ms, "funding_old": f0, "funding": fund,
                          "pnl_old": float(pnl0), "pnl": pnl})
    return fixes


@dataclass
class Filt:
    tick: float
    step: float
    mstep: float
    min_notional: float
    mmax: float = 0.0          # 06.11 14:13: piyasa emri en fazla adet (MARKET_LOT_SIZE maxQty; STRK demo 30.000 < 37.128 → −4005)

    def floor(self, x, s):
        return math.floor(x / s + 1e-9) * s

    def ceil(self, x, s):
        return math.ceil(x / s - 1e-9) * s

    def f(self, x, s):
        d = max(0, min(12, -int(math.floor(math.log10(s) + 1e-9))))
        return f"{x:.{d}f}"


@dataclass
class Pos:
    sym: str
    decision_ms: int
    score: float
    feats: dict
    target_qty: float
    status: str = "pending"            # pending → open → closed
    entry_cids: list = field(default_factory=list)
    entry_oids: list = field(default_factory=list)
    cur_cid: str = ""
    cur_price: float = 0.0
    placed_ms: int = 0
    filled_qty: float = 0.0
    filled_val: float = 0.0
    fill_ms: int = 0
    entry: float = 0.0
    tp_cid: str = ""
    es_cid: str = ""
    es_px: str = ""
    pr_cid: str = ""
    protected: bool = False
    exit_cid: str = ""
    exit_reason: str = ""
    checks: list = field(default_factory=list)
    lev: int = 1                       # bu pozisyonun kaldıracı (06.11 09:05'ten önceki kayıtlarda alan yok → 1×)
    liq_px: float = 0.0                # borsanın bildirdiği tasfiye fiyatı (dolumdan sonra positionRisk'ten)
    vol: float = 0.0                   # 06.11 ~19:00: karar anındaki VOL60; > 0 → oynaklık kâr al/stop + geri çekilme (0 = eski kural)
    pb_px: float = 0.0                 # 06.11 ~19:00: geri çekilme alış fiyatı (sabit; kovalama yok)
    ref_px: float = 0.0                # 06.11 ~19:00: sinyal anındaki demo en iyi alış (geri çekilmenin referansı)
    grace: int = 0                     # 08.11 Değ. 29: 60 dk kontrolünde verilen ek kontrol sayısı (0 = ek sürede değil)
    side: str = LONG                   # 08.11 Değ. 30: LONG / SHORT (öncesi hep long)


class BookStore:
    """Tam emir defteri arşivi (kullanıcı 06.11: "tam defter kayıt ve 3 saate silinmesin"). Dakikada bir her coin için
    Binance'in /fapi/v1/depth?limit=1000 yanıtı BAYT BAYT, lzma ile sıkıştırılıp saklanır; bot hiçbir şey silmez.
    Günlük dosya: v9live/book/YYYY-MM-DD.db (dakikalık turun başladığı UTC günü). Tablo book: ts (botun aldığı an, ms;
    live.db depth tablosundaki özetle AYNI değer → eşleştirme), sym, last_update_id, E (Binance mesaj zamanı), T (Binance
    işlem zamanı), n_bids, n_asks, raw (lzma). Açmak: json.loads(lzma.decompress(raw))."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        folder.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.day = ""
        self.db: sqlite3.Connection | None = None

    def begin(self, day: str) -> None:
        with self.lock:
            if day == self.day:
                return
            if self.db is not None:
                self.db.commit()
                self.db.close()
            self.db = sqlite3.connect(self.folder / f"{day}.db", check_same_thread=False)
            self.db.executescript("""
                create table if not exists book(ts integer, sym text, last_update_id integer, E integer, T integer,
                    n_bids integer, n_asks integer, raw blob);
                create index if not exists book_sym_ts on book(sym, ts);
            """)
            self.day = day

    def add(self, ts: int, sym: str, raw: bytes, d: dict) -> None:
        z = lzma.compress(raw)
        with self.lock:
            self.db.execute("insert into book values (?,?,?,?,?,?,?,?)",
                            (ts, sym, int(d["lastUpdateId"]), int(d["E"]), int(d["T"]), len(d["bids"]), len(d["asks"]), z))

    def commit(self) -> None:
        with self.lock:
            if self.db is not None:
                self.db.commit()

    def has_room(self) -> bool:
        return shutil.disk_usage(self.folder).free >= BOOK_MIN_FREE


class Bot:
    def __init__(self, dry: bool = False) -> None:
        self.dry = dry
        self.min_snaps = 3 if dry else 30          # canlıda son saatte en az 30 defter görüntüsü (dakikada bir)
        env = read_env(ROOT / ".env.testnet")
        self.rest = SignedRest(DEMO, env["BINANCE_TESTNET_API_KEY"],
                               private_key_path=env["BINANCE_TESTNET_PRIVATE_KEY_PATH"])
        self.note = Notifier(header="v9 demo") if not dry else None
        if self.note:
            self.note.start()
        # 06.11: deneme modu canlı bot çalışırken live.db / state.json'a YAZMASIN (ayrı dosyalar)
        self.db = sqlite3.connect(HERE / ("dry_run.db" if dry else "live.db"), check_same_thread=False)
        self.dblock = threading.Lock()
        self.db.executescript("""
            create table if not exists events(ts integer, kind text, data text);
            create table if not exists depth(ts integer, sym text, b1 real, a1 real);
            create index if not exists depth_ts on depth(ts);
            create table if not exists outcomes(ts integer, sym text, c0 real, fwd_1 real, fwd_2 real, fwd_4 real,
                fwd_8 real, fwd_12 real, fwd_24 real, rise_hours_after integer, acc_hours_after integer,
                max_up_24 real, max_dn_24 real, hours_to_up3 integer, hours_to_dn6 integer,
                up_streak_at integer, acc_streak_at integer, lc_at integer, primary key (ts, sym));
            create table if not exists scores(ts integer, sym text, feats text, gated integer, score real, chosen integer);
            create index if not exists scores_ts on scores(ts);
            create table if not exists checks(ts integer, sym text, fill_ms integer, entry real, r_t real, bid real,
                rise_ok integer, pnl_ok integer, sold integer);
            create table if not exists labels(ts integer, sym text, r_t real, r_btc real, oi_1 real, taker_1 real,
                spot_share_1 real, spot_rel_1 real, spot_taker_1 real, dd_48 real, bounce_48 real, label text,
                block integer, blocked integer, chosen integer, filter_on integer, primary key (ts, sym));
            create table if not exists uni24(ts integer, sym text, rank integer, chg24 real, qv24 real, primary key (ts, sym));
            create table if not exists trades(sym text, decision text, fill text, exit text, entry real, exit_px real,
                qty real, cost real, value real, fees real, funding real, pnl real, pnl_pct real, reason text,
                score real, feats text, checks text);
        """)
        if "lev" not in [r[1] for r in self.db.execute("pragma table_info(trades)")]:
            self.db.execute("alter table trades add column lev integer")      # 06.11 09:05: boş = 1× (öncesi)
            self.db.commit()
        # 08.11 Değ. 30: işlem yönü (boş = long, öncesi), karar anında yön + short puanı, açık pozisyonun ters sıçrama ölçümleri
        if "side" not in [r[1] for r in self.db.execute("pragma table_info(trades)")]:
            self.db.execute("alter table trades add column side text")
        sc_cols = [r[1] for r in self.db.execute("pragma table_info(scores)")]
        if "side" not in sc_cols:
            self.db.execute("alter table scores add column side text")
        if "score_s" not in sc_cols:
            self.db.execute("alter table scores add column score_s real")
        if "side" not in [r[1] for r in self.db.execute("pragma table_info(checks)")]:
            self.db.execute("alter table checks add column side text")
        self.db.execute("create table if not exists spike_checks(ts integer, sym text, side text, fill_ms integer, c_now real, "
                        "c_2 real, move real, sold integer)")
        self.db.commit()
        if "vol60" not in [r[1] for r in self.db.execute("pragma table_info(uni24)")]:
            self.db.execute("alter table uni24 add column vol60 real")      # 06.11 ~18:05: boş = filtre öncesi
            self.db.commit()
        self.db.execute("create table if not exists uni_excl(ts integer, sym text, vrank integer, chg24 real, qv24 real, "
                        "vol60 real, primary key (ts, sym))")              # oynaklık yüzünden alınmayanlar (vrank = hacim sırası)
        self.db.commit()
        if "band" not in [r[1] for r in self.db.execute("pragma table_info(depth)")]:
            self.db.execute("alter table depth add column band real")     # 06.11: defterin ölçüldüğü ± genişlik
            self.db.commit()
        self.kl: dict[str, list] = {}               # bu saatin 1h mumları (gözlem + spot ortancası, saatte bir)
        # 06.11 12:45 kayan pencere: 1 dk vadeli mumlar, açılış ms → (yüksek, düşük, kapanış, $ hacim, alıcı-taker $ hacim);
        # yalnızca KAPANMIŞ mumlar. Her dakika son birkaç mum yeniden istenir (ağırlık 1), boşluk olursa baştan doldurulur.
        self.m1: dict[str, dict[int, tuple]] = {}
        self.spot_med: dict[str, float] = {}       # spot/vadeli $ hacim oranının önceki 168 saatlik ortancası (saatte bir)
        self.next_status = 0
        self.fund_checked: set[int] = set()        # 07.11 Değ. 21: fonlaması yeniden okunmuş trades.rowid
        self.backfilled = False
        self.state_path = HERE / "state.json"
        self.save_path = HERE / ("dry_state.json" if dry else "state.json")
        self.spot_map: dict[str, str | None] = {}
        self.pos: list[Pos] = [Pos(**p) for p in json.loads(self.state_path.read_text())] \
            if self.state_path.exists() else []
        self.depth: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self.book = BookStore(BOOK_DIR) if not dry else None     # deneme modu arşive yazmaz
        self.book_paused = False
        # yeniden başlatmada son 2 saatin defter görüntüleri diskten geri yüklenir (06.11: restart saatlik veriyi siliyordu)
        # (06.11: yalnızca band'ı kayıtlı = düzeltilmiş kodla alınmış görüntüler; eski limit=500 görüntüleri karışmasın)
        for ts, sym, b1, a1 in self.db.execute("select ts, sym, b1, a1 from depth where ts >= ? and band is not null "
                                               "order by ts", (int(time.time() * 1000) - 2 * H,)):
            self.depth[sym].append((ts, b1, a1))
        self.pool = ThreadPoolExecutor(8)
        self.n = 0
        self.stop = False
        info = self.rest.exchange_info()
        self.filt = {}
        for s in info["symbols"]:
            fs = {f["filterType"]: f for f in s["filters"]}
            try:
                self.filt[s["symbol"]] = Filt(float(fs["PRICE_FILTER"]["tickSize"]), float(fs["LOT_SIZE"]["stepSize"]),
                                              float(fs.get("MARKET_LOT_SIZE", fs["LOT_SIZE"])["stepSize"]),
                                              float(fs.get("MIN_NOTIONAL", {}).get("notional", 5)),
                                              float(fs.get("MARKET_LOT_SIZE", fs["LOT_SIZE"]).get("maxQty", 0) or 0))
            except (KeyError, ValueError):
                continue
        self.demo_status = {s["symbol"]: s["status"] for s in info["symbols"]}   # demo'da işleme açık mı
        self.month = ""
        self.universe: list[str] = []
        self.uni_info: dict[str, tuple[float, float]] = {}   # coin → (24 sa değişim, 24 sa USDT hacmi), bu dakikanın listesi
        self.real_perps: set[str] = set()
        self.real_perps_t = 0
        self.hourly_tried: set[str] = set()                  # bu saat 1 sa mum + spot ortancası denenmiş coinler
        self.vol_cache: dict[str, tuple[int, float]] = {}    # 06.11 ~18:05: coin → (hesaplandığı t, VOL60)

    # ------------------------------------------------------------------ yardımcılar
    def event(self, kind: str, data: dict) -> None:
        with self.dblock:
            self.db.execute("insert into events values (?,?,?)", (int(time.time() * 1000), kind,
                                                                  json.dumps(data, ensure_ascii=False, default=str)))
            self.db.commit()
        if kind.endswith("error"):
            log(f"{kind}: {data}")

    def say(self, text: str) -> None:
        log(text)
        if self.note:
            self.note.send(text)

    def save(self) -> None:
        self.save_path.write_text(json.dumps([asdict(p) for p in self.pos if p.status != "closed"], indent=1))

    def cid(self, kind: str) -> str:
        self.n += 1
        return f"v9d-{kind}-{int(time.time())}-{self.n}"

    def balance_line(self) -> str:
        """06.11 ~14:05 kullanıcı ("demodaki bakiyenin hepsini göster", seçim "sadece göster"): demo hesabın tüm bakiyeleri.
        Bot yalnızca USDT kullanır (çoklu varlık modu kapalı)."""
        try:
            a = self.rest.request("GET", "/fapi/v2/account", {})
            parts = []
            for x in a["assets"]:
                w = float(x["walletBalance"])
                if w:
                    nd = 4 if x["asset"] == "BTC" else 2
                    parts.append(f"{x['asset']} {tr_num(w, nd)}" + (f" (kullanılabilir {tr_num(float(x['availableBalance']))})"
                                                                    if x["asset"] == "USDT" else ""))
            return "Bakiye: " + " · ".join(parts)
        except Exception as e:  # noqa: BLE001
            self.event("balance_error", {"error": str(e)[:200]})
            return ""

    def demo_bid_ask(self, sym: str) -> tuple[float, float]:
        r = self.rest.request("GET", "/fapi/v1/ticker/bookTicker", {"symbol": sym}, signed=False)
        return float(r["bidPrice"]), float(r["askPrice"])

    # ------------------------------------------------------------------ evren
    def refresh_universe(self) -> None:
        m = pd.Timestamp.now(tz="UTC").tz_localize(None).to_period("M")
        if str(m) == self.month:
            return
        cache = HERE / f"universe_{m}.json"
        if cache.exists():
            self.universe, self.month = json.loads(cache.read_text()), str(m)
            log(f"evren {self.month} (dosyadan): {', '.join(self.universe)}")
            return
        prev = m - 1
        a, b = int(prev.start_time.value // 1_000_000), int(m.start_time.value // 1_000_000)
        info = pget("/fapi/v1/exchangeInfo")["symbols"]
        cands = [s["symbol"] for s in info if s.get("contractType") == "PERPETUAL" and s.get("underlyingType") == "COIN"
                 and s["quoteAsset"] == "USDT" and s["status"] == "TRADING" and s["symbol"].isascii()
                 and s["symbol"] in self.filt]
        days = prev.days_in_month

        def qv(sym):
            k = pget("/fapi/v1/klines", symbol=sym, interval="1d", startTime=a, endTime=b - 1, limit=40)
            return (sym, sum(float(x[7]) for x in k)) if len(k) == days else (sym, -1.0)
        vols = sorted(self.pool.map(qv, cands), key=lambda x: (-x[1], x[0]))
        self.universe = [s for s, v in vols if v > 0][:30]
        self.month = str(m)
        cache.write_text(json.dumps(self.universe))
        self.event("universe", {"month": self.month, "symbols": self.universe})
        log(f"evren {self.month}: {', '.join(self.universe)}")

    def universe_24h(self, t: int) -> None:
        """06.11 ~14:05 kullanıcı ("listeyi yeniden kur"): her dakika TÜM USDT sürekli vadeli coinlerden Binance'in 24 saatlik
        değişimi > 0 olanlar, 24 saatlik USDT hacmine göre ilk UNI_N (gerçek piyasa /fapi/v1/ticker/24hr — Binance uygulamasındaki
        24 sa % ile aynı kaynak; ağırlık 40). Demo'da TRADING olmayan / demo filtresi olmayan / sabit coinler alınmaz. Artıda coin
        yoksa liste boş (giriş yok). İstek başarısızsa önceki liste sürer. Her dakikanın listesi `uni24` tablosunda."""
        if t >= self.next_status:                          # demo borsada işleme açık mı (15 dk'da bir; 06.11: PUMP "SETTLING")
            try:
                self.demo_status = {s["symbol"]: s["status"] for s in self.rest.exchange_info()["symbols"]}
                self.next_status = t + STATUS_EVERY_MS
            except Exception as e:  # noqa: BLE001
                self.event("demo_status_error", {"error": str(e)[:200]})
        if not self.real_perps or t >= self.real_perps_t + H:
            info = pget("/fapi/v1/exchangeInfo")["symbols"]
            self.real_perps = {s["symbol"] for s in info if s.get("contractType") == "PERPETUAL"
                               and s.get("underlyingType") == "COIN" and s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
                               and s["symbol"].isascii() and s["baseAsset"] not in STABLES}
            self.real_perps_t = t
        tk = pget("/fapi/v1/ticker/24hr")
        c = [(x["symbol"], float(x["priceChangePercent"]) / 100, float(x["quoteVolume"])) for x in tk
             if x["symbol"] in self.real_perps and x["symbol"] in self.filt and self.demo_status.get(x["symbol"]) == "TRADING"]
        cands = sorted([x for x in c if x[1] > 0 or not UNI_REQUIRE_UP], key=lambda x: (-x[2], x[0]))   # 07.11: işaret şartı yok
        # 06.11 ~18:05: hacim sırasıyla yürü, VOL60 > VOL_MAX ya da ölçülemeyen coini atla, UNI_N dolana kadar
        top, excl, i = [], [], 0
        while len(top) < UNI_N and i < len(cands):
            batch = cands[i:i + UNI_N - len(top) + 4]
            vols = list(self.pool.map(lambda x: self.vol60(x[0], t), batch))
            for j, ((s, ch, qv), v) in enumerate(zip(batch, vols)):
                if len(top) >= UNI_N:
                    break
                if np.isfinite(v) and v <= VOL_MAX:
                    top.append((s, ch, qv, v))
                else:
                    excl.append((s, i + j + 1, ch, qv, v))
            i += len(batch)
        old = set(self.universe)
        self.universe = [s for s, _, _, _ in top]
        self.uni_info = {s: (ch, qv) for s, ch, qv, _ in top}
        fv = lambda v: float(v) if np.isfinite(v) else None  # noqa: E731
        with self.dblock:
            self.db.executemany("insert or replace into uni24(ts, sym, rank, chg24, qv24, vol60) values (?,?,?,?,?,?)",
                                [(t, s, k + 1, ch, qv, fv(v)) for k, (s, ch, qv, v) in enumerate(top)])
            self.db.executemany("insert or replace into uni_excl values (?,?,?,?,?,?)",
                                [(t, s, r, ch, qv, fv(v)) for s, r, ch, qv, v in excl])
            self.db.commit()
        if not old or (set(self.universe) != old and t % (15 * M) == 0):
            log(f"liste {pd.Timestamp(t, unit='ms')}: {len(self.universe)} coin ({'24 sa artıda, ' if UNI_REQUIRE_UP else ''}hacme göre, oynaklık ≤ "
                f"%{VOL_MAX * 100:.0f}): " + ", ".join(f"{s.removesuffix('USDT')} {ch:+.1%}" for s, ch, _, _ in top)
                + (" | oynak, alınmadı: " + ", ".join(f"{s.removesuffix('USDT')} %{v * 100:.1f}" if np.isfinite(v)
                                                      else f"{s.removesuffix('USDT')} ölçülemedi"
                                                      for s, _, _, _, v in excl) if excl else ""))

    def vol60(self, sym: str, t: int) -> float:
        """VOL60 (06.11 ~18:05): t5 = t'nin 5 dk sınırı (:00, :05, …); t5'e kadar kapanmış son 1.500 adet 1 dk mumun
        kapanışlarıyla, 60 dk arayla tüm getiriler c(o + 60 dk) / c(o) − 1 (üst üste binen pencereler), popülasyon std'si.
        En az VOL_MIN_N getiri yoksa NaN. Aynı t5 için bir kez hesaplanır (verify.py universe aynı t5'i yeniden hesaplar).
        Hata → NaN (coin listeye alınmaz, olay yazılır)."""
        t5 = t // VOL_EVERY_MS * VOL_EVERY_MS
        hit = self.vol_cache.get(sym)
        if hit and hit[0] == t5:
            return hit[1]
        try:
            c1 = self.load_m1(sym, t)
            r = [c1[o + H][2] / c1[o][2] - 1 for o in range(t5 - 1500 * M, t5 - H, M) if o in c1 and o + H in c1]
            v = float(np.std(r)) if len(r) >= VOL_MIN_N else float("nan")
        except Exception as e:  # noqa: BLE001
            self.event("vol_error", {"sym": sym, "t": t, "error": str(e)[:200]})
            v = float("nan")
        self.vol_cache[sym] = (t5, v)
        return v

    def hourly_one(self, sym: str, T: int) -> None:
        """1 sa mumlar (gözlem) + spot oranı ortancası, saat başı T için tek coin."""
        k = pget("/fapi/v1/klines", symbol=sym, interval="1h", endTime=T - 1, limit=200)
        self.kl[sym] = [x for x in k if x[0] + H <= T]
        self.spot_median(sym, T)

    # ------------------------------------------------------------------ emir defteri (dakikada bir, gerçek piyasa)
    def sample_depth(self) -> None:
        syms = set(self.universe) | {p.sym for p in self.pos if p.status != "closed"}
        keep = False
        if self.book is not None:
            keep = self.book.has_room()
            if not keep and not self.book_paused:
                free = shutil.disk_usage(BOOK_DIR).free / 1024 ** 3
                self.event("book_disk_low", {"free_gb": round(free, 2)})
                self.say(f"UYARI: diskte {free:.1f} GB boş yer kaldı (< 3 GB); tam defter kaydı DURDU. Özet ve işlemler "
                         f"sürüyor, hiçbir şey silinmedi.")
            elif keep and self.book_paused:
                self.say("tam defter kaydı yeniden başladı (diskte yer açıldı)")
            self.book_paused = not keep
            if keep:
                try:
                    self.book.begin(time.strftime("%Y-%m-%d", time.gmtime()))
                except Exception as e:  # noqa: BLE001         # arşiv açılamazsa özet ölçüm yine sürer
                    self.event("book_error", {"stage": "open", "error": str(e)[:200]})
                    keep = False

        def one(sym):
            try:
                # 06.11 düzeltme: limit=500 BTC/ETH/ZEC/HYPE/BNB'de ±%1'e uzanmıyordu (BTC ±%0,09). Binance en fazla 1000
                # basamak verir (ağırlık 20). Band = min(%1, alış ucu, satış ucu): iki taraf eşit genişlikte; band kaydedilir
                # (kullanıcı kararı: BTC/ETH'de "uzanabildiği kadar ölç").
                raw = pget("/fapi/v1/depth", raw=True, symbol=sym, limit=1000)
                d = json.loads(raw)
                bids = np.array(d["bids"], dtype=float)
                asks = np.array(d["asks"], dtype=float)
                mid = (bids[0, 0] + asks[0, 0]) / 2
                band = min(0.01, 1 - bids[-1, 0] / mid, asks[-1, 0] / mid - 1)
                bm, am = bids[:, 0] >= mid * (1 - band), asks[:, 0] <= mid * (1 + band)
                b1 = float((bids[bm, 0] * bids[bm, 1]).sum())
                a1 = float((asks[am, 0] * asks[am, 1]).sum())
                ts = int(time.time() * 1000)
                self.depth[sym].append((ts, b1, a1))
                with self.dblock:
                    self.db.execute("insert into depth (ts, sym, b1, a1, band) values (?,?,?,?,?)",
                                    (ts, sym, b1, a1, band))
            except Exception as e:  # noqa: BLE001
                self.event("depth_error", {"sym": sym, "error": str(e)[:200]})
                return
            if keep:
                try:
                    self.book.add(ts, sym, raw, d)
                except Exception as e:  # noqa: BLE001         # arşiv hatası özet ölçümü bozmaz
                    self.event("book_error", {"sym": sym, "error": str(e)[:200]})
        list(self.pool.map(one, syms))
        # 06.11 kullanıcı: "3 saate silinmesin" → depth özeti artık SİLİNMEZ (eskiden 3 saatten eskisi siliniyordu)
        with self.dblock:
            self.db.commit()
        if keep:
            try:
                self.book.commit()
            except Exception as e:  # noqa: BLE001
                self.event("book_error", {"stage": "commit", "error": str(e)[:200]})

    # ------------------------------------------------------------------ ölçüm (saat kapanışı t, ms)
    def load_m1(self, sym: str, t: int) -> dict:
        """t anına kadar KAPANMIŞ 1 dk vadeli mumlar (gerçek piyasa). Önbellek boşsa / 1.400 dk'dan eskiyse baştan
        KL_KEEP mum; değilse son kayıtlı mumdan 2 önce başlayarak yeniden (yarım kalmış mum olmasın)."""
        c = self.m1.setdefault(sym, {})
        if not c or max(c) < t - 1400 * M:
            c.clear()
            start = t - KL_KEEP * M
        else:
            start = max(c) - 2 * M
        while start <= t - M:
            lim = 1500 if (t - start) // M > 99 else 99
            k = pget("/fapi/v1/klines", symbol=sym, interval="1m", startTime=start, endTime=t - 1, limit=lim)
            if not k:
                break
            for x in k:
                if int(x[0]) + M <= t:
                    c[int(x[0])] = (float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10]))
            if len(k) < lim:
                break
            start = int(k[-1][0]) + M
        for o in [o for o in c if o < t - KL_KEEP * M]:
            del c[o]
        return c

    def features(self, sym: str, t: int) -> dict:
        """t = dakika sınırı (ms). Bütün pencereler t'den geriye kayar (06.11 12:45; önce saat başı)."""
        c1 = self.load_m1(sym, t)
        close_at = lambda ts: c1[ts - M][2] if (ts - M) in c1 else None  # noqa: E731   # ts anında biten mumun kapanışı

        def sm(ts):   # 06.11 ~18:05: pencere ucu = ts anında biten son SMOOTH_N adet 1 dk mum kapanışının ortalaması
            v = [close_at(ts - j * M) for j in range(SMOOTH_N)]
            return None if any(x is None for x in v) else sum(v) / SMOOTH_N
        c = [sm(t - H * i) for i in range(25)]
        out = {k_: np.nan for k_ in COMPONENTS + ("R30", "r_t", "r_prev", "r_t_raw", "LC_DN", "COIN_J_UP", "COIN_J_DN")}
        c0r, c1r = close_at(t), close_at(t - H)
        if c0r is not None and c1r is not None:
            out["r_t_raw"] = c0r / c1r - 1       # ham son 60 dk (etiket + kayıt; kararlar ortalamalı r_t ile)
        # Değ. 30 (2): son 60 dk içindeki üst üste binen 2 dk hareketlerinin en büyüğü / en küçüğü (ham 1 dk kapanışlar)
        p61 = [close_at(t - H + j * M) for j in range(H // M + 1)]
        if all(v is not None and v > 0 for v in p61):
            mv2 = [p61[j] / p61[j - SPIKE_MS // M] - 1 for j in range(SPIKE_MS // M, len(p61))]
            out["COIN_J_UP"], out["COIN_J_DN"] = max(mv2), min(mv2)
        if any(v is None for v in c):
            return out
        R = lambda w: c[0] / c[w] - 1  # noqa: E731
        Rp = lambda w: c[w] / c[2 * w] - 1  # noqa: E731
        L = 0
        for N in WIN:
            if R(N) > 0 and R(N) > Rp(N):
                L = N
            else:
                break
        LD = 0                                   # Değ. 30: LC'nin aynası (short) — düşüşte VE önceki pencereden hızlı düşüşte
        for N in WIN:
            if R(N) < 0 and R(N) < Rp(N):
                LD = N
            else:
                break
        out.update(LC=L, LC_DN=LD, r_t=R(1), r_prev=Rp(1), ACC_1=R(1) - Rp(1))
        # GÖZLEM (kararı etkilemez): yükseliş ve hızlanma kaç "60 dk" sürüyor (t'den geriye 60'ar dk adımlarla)
        cl_all = []
        for i in range(48):
            v = close_at(t - H * i)
            if v is None:
                break
            cl_all.append(v)
        rr = [cl_all[i] / cl_all[i + 1] - 1 for i in range(len(cl_all) - 1)]
        up = 0
        while up < len(rr) and rr[up] > 0:
            up += 1
        acc = 1 if rr and rr[0] > 0 else 0
        while acc and acc < len(rr) and rr[acc] > 0 and rr[acc] < rr[acc - 1]:
            acc += 1
        out.update(UP_STREAK=up, ACC_STREAK=acc)
        last60 = [c1.get(t - M * j) for j in range(1, 61)]                 # son 60 dk'nın mumları
        if all(x is not None for x in last60):
            qv, tb = sum(x[3] for x in last60), sum(x[4] for x in last60)
            out["FUT_QV_1"] = qv
            out["TAKER_1"] = tb / qv if qv > 0 else np.nan
        cl = [close_at(t - 4 * H + j * M) for j in range(241)]            # t−4 sa'ten t'ye 240 adım
        if all(v is not None for v in cl):
            path = sum(abs(math.log(cl[i] / cl[i - 1])) for i in range(1, len(cl)))
            out["SMOOTH_4"] = math.log(c[0] / c[4]) / path if path > 0 else np.nan
        snaps = [s_ for s_ in self.depth.get(sym, []) if t - H <= s_[0] < t]
        if len(snaps) >= self.min_snaps:
            b = np.array([s_[1] for s_ in snaps])
            a = np.array([s_[2] for s_ in snaps])
            out["IMB1_1"] = float(np.mean((b - a) / (b + a)))
            out["BIDSHARE_1"] = float(np.mean(b > a))
        # 08.11 Değişiklik 26: piyasa şartı için ham son 30 dk (t'de biten kapanış / t − 30 dk'da biten kapanış − 1)
        c5 = close_at(t - 5 * M)                       # Değ. 29: coinin ham son 5 dk'sı (60 dk kontrolü ek süresi)
        if c0r is not None and c5 is not None and c5 > 0:
            out["R_5M"] = c0r / c5 - 1
        c30 = close_at(t - MKT_WIN_MS)
        if c0r is not None and c30 is not None and c30 > 0:
            out["R30"] = c0r / c30 - 1
            # Değ. 27: t−30 … t her dakikanın c/c(t−30)−1 yolu (piyasa yolu için; decide() ortalamayı alıp siler, kayda girmez)
            p30 = [close_at(t - MKT_WIN_MS + j * M) for j in range(MKT_WIN_MS // M + 1)]
            if all(v is not None for v in p30):
                out["_P30"] = [v / c30 - 1 for v in p30]
        try:
            # OI_1: Binance açık pozisyon geçmişini 5 dk'da bir yayımlar → bu bileşen 5 dk adımlarla kayar.
            # Yayımlanan son değer (≤ t) ile TAM 1 saat öncesi; pozisyon ADEDİ (sumOpenInterest); dolar değeri yalnız kayıt.
            oi = pget("/futures/data/openInterestHist", symbol=sym, period="5m", limit=24)
            v = {int(x["timestamp"]): float(x["sumOpenInterest"]) for x in oi}
            val = {int(x["timestamp"]): float(x["sumOpenInterestValue"]) for x in oi}
            pub_ts = [ts for ts in v if ts <= t]
            if pub_ts:
                now_ts = max(pub_ts)
                out["OI_TS"] = now_ts                      # denetim için: hangi 5 dk noktası kullanıldı
                if now_ts - H in v:
                    out["OI_1"] = v[now_ts] / v[now_ts - H] - 1
                    out["OI_VAL_1"] = val[now_ts] / val[now_ts - H] - 1
        except Exception as e:  # noqa: BLE001
            self.event("oi_error", {"sym": sym, "error": str(e)[:200]})
        # GÖZLEM: dipten mi geliyor (son 48 saatin en yükseğine / en düşüğüne göre, 1 dk mumlardan)
        w48 = [x for o, x in c1.items() if o >= t - 48 * H]
        if len(w48) >= 2870:
            out["DD_48"] = c[0] / max(x[0] for x in w48) - 1
            out["BOUNCE_48"] = c[0] / min(x[1] for x in w48) - 1
        try:
            out.update(self.spot_feats(sym, t, out.get("FUT_QV_1", np.nan)))
        except Exception as e:  # noqa: BLE001
            self.event("spot_error", {"sym": sym, "error": str(e)[:200]})
        return out

    def spot_sym(self, sym: str) -> str | None:
        if sym not in self.spot_map:
            found = None
            for cand in [sym] + ([sym[4:]] if sym.startswith("1000") else []):
                info = sget("/api/v3/exchangeInfo", symbol=cand)
                if info and info.get("symbols") and info["symbols"][0].get("status") == "TRADING":
                    found = cand
                    break
            self.spot_map[sym] = found
        return self.spot_map[sym]

    def spot_feats(self, sym: str, t: int, fut_qv: float) -> dict:
        """Son 60 dk spot katılımı (kayan). SPOT_SHARE_1 = spot $ hacmi / vadeli $ hacmi (son 60 dk, 1 dk mumlar);
        SPOT_REL_1 = bu oran / spot_med (önceki 168 tam saatin saatlik oranlarının ortancası, saatte bir hesaplanır);
        SPOT_TAKER_1 = spotta alıcı-başlatan pay."""
        sp = self.spot_sym(sym)
        if sp is None or not (fut_qv > 0):
            return {}
        ks = sget("/api/v3/klines", symbol=sp, interval="1m", startTime=t - H, endTime=t - 1, limit=60) or []
        ks = [x for x in ks if int(x[0]) + M <= t]
        if len(ks) != 60:
            return {}
        sq, stb = sum(float(x[7]) for x in ks), sum(float(x[10]) for x in ks)
        res = {"SPOT_SHARE_1": sq / fut_qv}
        if sq > 0:
            res["SPOT_TAKER_1"] = stb / sq
        med = self.spot_med.get(sym)
        if med and med > 0:
            res["SPOT_REL_1"] = res["SPOT_SHARE_1"] / med
        return res

    def spot_median(self, sym: str, T: int) -> None:
        """Saatte bir (T = saat başı): önceki 168 tam saatin spot/vadeli $ hacim oranı ortancası. Saatler: açılışı
        o − i sa (o = T − 1 sa, i = 1…168); en az 120 saat. Kayan pencere [t−60 dk, t) bu saatlerle hiç örtüşmez."""
        sp = self.spot_sym(sym)
        k = self.kl.get(sym) or []
        if sp is None or not k:
            self.spot_med.pop(sym, None)
            return
        ks = sget("/api/v3/klines", symbol=sp, interval="1h", endTime=T - 1, limit=200) or []
        sq = {int(x[0]): float(x[7]) for x in ks if int(x[0]) + H <= T}
        fq = {int(x[0]): float(x[7]) for x in k}
        o = T - H
        hist = [sq[a] / fq[a] for a in (o - i * H for i in range(1, 169)) if a in sq and fq.get(a, 0) > 0]
        med = float(np.median(hist)) if len(hist) >= 120 else np.nan
        if np.isfinite(med) and med > 0:
            self.spot_med[sym] = med
        else:
            self.spot_med.pop(sym, None)

    # ------------------------------------------------------------------ gözlem: 24 saat önce ne oldu
    def record_outcomes(self, t: int, back_h: int = 0) -> None:
        """GÖZLEM (kararı etkilemez). Karar anı s = t − 24 sa (ilk çalıştırmada geriye back_h saat daha) için her coinde:
        karar anında yükseliş / hızlanma kaç saattir sürüyordu ve LC (yalnızca s'ye kadarki mumlar); sonraki 24 saatte
        fwd_h = C_{s+h}/C_s − 1, rise_hours_after (üst üste yükselen saat), acc_hours_after (hızlanarak yükselen saat),
        max_up/dn_24, hours_to_up3 (+%3) / hours_to_dn6 (−%6) ilk değme saati. Bu saatin 1h mumlarından, ek istek yok."""
        rows = []
        for sym, k in self.kl.items():
            byopen = {int(x[0]): x for x in k}
            for back in range(back_h + 1):
                s = t - (24 + back) * H
                prev = byopen.get(s - H)                          # s'de biten saat
                nxt = [byopen.get(s + j * H) for j in range(24)]  # s'den sonraki 24 saat
                if prev is None or any(x is None for x in nxt):
                    continue
                c0 = float(prev[4])
                past = [float(byopen[s - (i + 1) * H][4]) for i in range(199) if (s - (i + 1) * H) in byopen]
                rr = [past[i] / past[i + 1] - 1 for i in range(len(past) - 1)]
                up_at = 0
                while up_at < len(rr) and rr[up_at] > 0:
                    up_at += 1
                acc_at = 1 if rr and rr[0] > 0 else 0
                while acc_at and acc_at < len(rr) and rr[acc_at] > 0 and rr[acc_at] < rr[acc_at - 1]:
                    acc_at += 1
                lc_at = 0
                if len(past) >= 25:
                    for N in WIN:
                        if past[0] / past[N] - 1 > 0 and past[0] / past[N] > past[N] / past[2 * N]:
                            lc_at = N
                        else:
                            break
                C = [c0] + [float(x[4]) for x in nxt]
                r = [C[j] / C[j - 1] - 1 for j in range(1, 25)]
                r_s = rr[0] if rr else np.nan
                rise = 0
                while rise < 24 and r[rise] > 0:
                    rise += 1
                acc, last = 0, r_s
                while acc < 24 and r[acc] > 0 and np.isfinite(last) and r[acc] > last:
                    last = r[acc]
                    acc += 1
                hi = [float(x[2]) for x in nxt]
                lo = [float(x[3]) for x in nxt]
                up3 = next((j + 1 for j, v in enumerate(hi) if v >= c0 * 1.03), None)
                dn6 = next((j + 1 for j, v in enumerate(lo) if v <= c0 * 0.94), None)
                rows.append((s, sym, c0, *(C[h] / c0 - 1 for h in (1, 2, 4, 8, 12, 24)), rise, acc,
                             max(hi) / c0 - 1, min(lo) / c0 - 1, up3, dn6, up_at, acc_at, lc_at))
        with self.dblock:
            self.db.executemany("insert or replace into outcomes values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            self.db.commit()
        if rows:
            log(f"gözlem: {len(rows)} coin-saatin 24 sa sonucu yazıldı (geriye {back_h} sa)")

    # ------------------------------------------------------------------ saatte bir: gözlem + spot ortancası
    def hour_jobs(self, T: int) -> None:
        """T = saat başı. Karar VERMEZ: 1 sa mumlar (outcomes gözlemi), spot oranı ortancası. 06.11 ~14:05'ten beri liste her
        dakika universe_24h ile; saat içinde listeye yeni giren coinin 1 sa verisi decide'da bir kez alınır (hourly_tried)."""
        syms = sorted(set(self.universe) | {p.sym for p in self.pos if p.status != "closed"})
        # bellek: listede/elde olmayan coinlerin 1 dk mum önbelleği atılır (geri gelirse baştan yüklenir)
        for s_ in [s_ for s_ in self.m1 if s_ not in syms]:
            del self.m1[s_]

        def one(sym_):
            try:
                self.hourly_one(sym_, T)
            except Exception as e:  # noqa: BLE001
                self.event("hour_job_error", {"sym": sym_, "error": str(e)[:200]})
        self.kl = {}
        self.hourly_tried = set(syms)
        list(self.pool.map(one, syms))
        try:
            self.record_outcomes(T, back_h=0 if self.backfilled else 150)
            self.backfilled = True
        except Exception as e:  # noqa: BLE001
            self.event("outcome_error", {"t": T, "error": str(e)[:300]})
        log(f"saat işi {pd.Timestamp(T, unit='ms')}: {len(self.kl)} coin 1 sa mum, spot ortancası {len(self.spot_med)} coin")

    # ------------------------------------------------------------------ dakikalık karar (kayan pencere)
    def decide(self, t: int, pre_sold: set | None = None) -> None:
        try:
            self.universe_24h(t)
        except Exception as e:  # noqa: BLE001                # alınamazsa önceki dakikanın listesi sürer
            self.event("universe_error", {"t": t, "error": str(e)[:200]})
        held = {p.sym for p in self.pos if p.status != "closed"}
        syms = sorted(set(self.universe) | held)
        new = [s_ for s_ in syms if s_ not in self.hourly_tried]
        if new:                                            # saat içinde listeye giren coin: 1 sa mum + spot ortancası bir kez
            self.hourly_tried |= set(new)

            def one_h(sym_):
                try:
                    self.hourly_one(sym_, t // H * H)
                except Exception as e:  # noqa: BLE001
                    self.event("hour_job_error", {"sym": sym_, "error": str(e)[:200]})
            list(self.pool.map(one_h, new))

        def safe(sym_):
            try:
                return self.features(sym_, t)
            except Exception as e:  # noqa: BLE001
                self.event("feature_error", {"sym": sym_, "error": str(e)[:200]})
                return {k_: np.nan for k_ in COMPONENTS + ("R30", "r_t", "r_prev")}
        feats = dict(zip(syms, self.pool.map(safe, syms)))
        # 08.11 Değişiklik 26: piyasa şartı = listedeki coinlerin ham son 30 dk getirilerinin eşit ağırlıklı ortalaması
        r30s = [float(feats[s_]["R30"]) for s_ in self.universe if s_ in feats and np.isfinite(feats[s_].get("R30", np.nan))]
        mkt30 = float(np.mean(r30s)) if r30s else np.nan
        # Değ. 27: genişlik (kaç coin artıda), piyasa yolu → son 5 dk ve son 30 dk tepesine uzaklık, tek coin katkısı (kayıt)
        up_n = sum(1 for v in r30s if v > 0)
        dn_n = sum(1 for v in r30s if v < 0)                           # Değ. 30: short genişliği
        paths = [feats[s_]["_P30"] for s_ in self.universe if s_ in feats and feats[s_].get("_P30") is not None]
        if paths:
            idx = np.mean(np.array(paths, dtype=float), axis=0)        # t−30 … t (31 nokta)
            mkt5, peak = float(idx[-1] - idx[-1 - MKT_FAST_MS // M]), float(idx[-1] - idx.max())
            jump = float(idx[-1] - idx[-1 - MKT_JUMP_MS // M])         # Değ. 28: son 2 dk
            trough = float(idx[-1] - idx.min())                        # Değ. 30: 30 dk dibinden uzaklık (short)
        else:
            mkt5 = peak = jump = trough = np.nan
        top = float(max(r30s, key=abs) / len(r30s)) if r30s else np.nan
        mk = {"MKT_30": mkt30, "MKT_N": len(r30s), "MKT_UP": up_n, "MKT_5": mkt5, "MKT_PEAK": peak, "MKT_TOP": top,
              "MKT_PN": len(paths), "MKT_JUMP": jump, "MKT_DN": dn_n, "MKT_TROUGH": trough}
        for s_ in syms:
            feats[s_].pop("_P30", None)
            feats[s_].update(mk)
        for s_ in syms:                                    # kayıt + şart: Binance 24 sa değişimi ve hacmi (liste dışı: yok)
            ch, qv = self.uni_info.get(s_, (np.nan, np.nan))
            feats[s_]["CHG24"], feats[s_]["QV24"] = ch, qv
            k_ = (self.m1.get(s_) or {}).get(t - M)              # Değ. 25: fiyat adımı / son kapanış
            feats[s_]["TICK_REL"] = self.filt[s_].tick / k_[2] if k_ and k_[2] > 0 and s_ in self.filt else np.nan
        # 1) açık pozisyon kontrolü (yeni girişlerden önce). Girişten ≥ 60 dk geçmiş her pozisyon, 5 dk'da bir:
        # (a) son 60 dk ≥ −BAND, (b) demo fiyatı ≥ giriş × 1,0014. Biri yoksa satılır — Değ. 29: (b) yok ama coin yükseliyorsa
        # (a + son 5 dk > 0) 3 ek kontrol (check_decide).
        sold_now: set[str] = set(pre_sold or ())          # Değ. 30: bu dakika ters sıçramada satılanlar da
        for p in [p for p in self.pos if p.status == "open" and p.fill_ms and not p.exit_cid
                  and (p.fill_ms < t if HOURLY_DECIDE else p.fill_ms <= t - CHECK_AFTER_MS)]:
            try:
                f = feats.get(p.sym, {})
                bid, ask = self.demo_bid_ask(p.sym)
                px = bid if sd(p.side) > 0 else ask            # Değ. 30: kapatma fiyatı (short'ta en iyi satış)
                # 06.11 ~18:05: (a) bantlı: son 60 dk (uçlar 5 dk ort.) ≥ −BAND ise yükseliş "sürüyor" sayılır (short: ≤ +BAND)
                r5 = float(f.get("R_5M", np.nan))
                rise_ok, pnl_ok, up5 = check_inputs(p.side, float(f.get("r_t", np.nan)), px, p.entry, r5)
                g0 = p.grace
                want, why, p.grace = check_decide(g0, rise_ok, pnl_ok, up5)
                if why == "kayan_kontrol" and HOURLY_DECIDE:
                    why = "saatlik_kontrol"
                sell = want and not self.dry
                p.checks = (p.checks + [{"t": t, "r_t": f.get("r_t"), "r_prev": f.get("r_prev"), "bid": px,
                                         "rise_ok": rise_ok, "pnl_ok": pnl_ok, "r5": r5 if np.isfinite(r5) else None,
                                         "grace": g0, "sell": want, "why": why, "side": p.side}])[-60:]   # son 60; tamamı checks tablosunda
                if g0 > 0 or p.grace > 0:                  # Değ. 29: ek süreyle ilgili her kontrol (denetim: audit/grace_check.py)
                    self.event("ek_kontrol", {"sym": p.sym, "t": t, "fill_ms": p.fill_ms, "entry": p.entry, "bid": bid,
                                              "ask": ask, "px": px, "side": p.side,
                                              "r_t": f.get("r_t"), "r5": r5 if np.isfinite(r5) else None, "rise_ok": rise_ok,
                                              "pnl_ok": pnl_ok, "grace_before": g0, "grace_after": p.grace, "sell": want,
                                              "why": why})
                with self.dblock:                          # checks.bid = kapatma fiyatı (short'ta demo en iyi satış)
                    self.db.execute("insert into checks (ts, sym, fill_ms, entry, r_t, bid, rise_ok, pnl_ok, sold, side) "
                                    "values (?,?,?,?,?,?,?,?,?,?)",
                                    (t, p.sym, p.fill_ms, p.entry, None if not np.isfinite(f.get("r_t", np.nan)) else
                                     float(f["r_t"]), px, int(rise_ok), int(pnl_ok), int(sell), p.side))
                if want or len(p.checks) == 1 or g0 > 0 or p.grace > 0:
                    log(f"kontrol {p.side} {p.sym}: {'yükseliş' if sd(p.side) > 0 else 'düşüş'} {'✓' if rise_ok else '✗'} "
                        f"(son 60 dk {f.get('r_t', np.nan):+.3%}), "
                        f"kâr {'✓' if pnl_ok else '✗'} (demo {px} / giriş {p.entry:.6g}), son 5 dk {r5:+.3%}"
                        + (f", ek kontrol {g0} → {p.grace}/{GRACE_N}" if g0 or p.grace else "")
                        + (f" → SAT ({REASON_TR.get(why, why)})" if want else " → tut"))
                if sell:
                    self.exit_market(p, why)
                    sold_now.add(p.sym)
            except Exception as e:  # noqa: BLE001
                self.event("check_error", {"sym": p.sym, "t": t, "error": str(e)[:300]})
        # 1b) 06.11 ~19:00: dolmakta olan geri çekilme alışı, trend bozulduysa iptal (dolan kısım pozisyon olur, kâr al/stop konur)
        for p in [p for p in self.pos if p.pb_px > 0 and not p.tp_cid and not p.exit_cid and p.status in ("pending", "open")]:
            try:
                f = feats.get(p.sym, {})
                vals = [f.get(k_, np.nan) for k_ in ("MKT_30", "LC", "r_t")]
                if not all(np.isfinite(float(v)) for v in vals):
                    continue                               # ölçülemedi: dokunma (15 dk sınırı yine geçerli)
                m30, lc, rt = (float(v) for v in vals)
                if m30 > 0 and lc >= 2 and rt >= -BAND:
                    continue
                try:
                    self.absorb(p, self.rest.cancel_order(p.sym, p.cur_cid))
                except ExchangeError:
                    pass
                self.event("pullback_cancel", {"sym": p.sym, "t": t, "MKT_30": m30, "LC": lc, "r_t": rt,
                                               "filled": p.filled_qty})
                log(f"geri çekilme alışı iptal {p.sym}: trend bozuldu (piyasa son 30 dk {m30:+.2%}, LC {lc:.0f}, son 60 dk {rt:+.2%}); "
                    f"dolan {p.filled_qty:g} adet")
                self.entry_done(p)
            except Exception as e:  # noqa: BLE001
                self.event("pullback_cancel_error", {"sym": p.sym, "t": t, "error": str(e)[:300]})
        self.pos = [p for p in self.pos if p.status != "closed"]
        self.save()
        # 2) puan ve yeni girişler
        df = pd.DataFrame(feats).T
        U = df.loc[[s for s in self.universe if s in df.index]]
        full = U[list(SCORE_COMPONENTS)].astype(float).dropna()   # 07.11: ACC_1 puanda yok
        score = full.rank(pct=True).mean(axis=1) if len(full) else pd.Series(dtype=float)
        # Değ. 30: short puanı = aynı coinler, aynalanmış bileşenler (LC → LC_DN; SMOOTH_4, TAKER_1, IMB1_1, BIDSHARE_1 ters; OI_1 aynı)
        if len(full):
            fs = pd.DataFrame({"LC_DN": U.loc[full.index, "LC_DN"].astype(float), "SMOOTH_4": -full["SMOOTH_4"],
                               "TAKER_1": -full["TAKER_1"], "IMB1_1": -full["IMB1_1"], "BIDSHARE_1": -full["BIDSHARE_1"],
                               "OI_1": full["OI_1"]}).dropna()
            score_s = fs.rank(pct=True).mean(axis=1) if len(fs) else pd.Series(dtype=float)
        else:
            score_s = pd.Series(dtype=float)
        # 06.11 ~13:15 UTC kullanıcı seçimi (A): girişte son 60 dk da artıda olmalı (r_t > 0). Sebep: kontrol (a) "son 60 dk > 0"
        # değilse satıyor; şart yokken FIL/LINK/HYPE/SOL son 60 dk EKSİDEYKEN girmişti (botun kendi satacağı coin).
        # 06.11 ~18:05: son 60 dk (uçlar 5 dk ort.) > +BAND (bant; önce > 0)
        rt_min = 0.0 if HOURLY_DECIDE else BAND
        # 08.11 Değişiklik 27: şart = piyasa son 30 dk ≥ +%0,10, ≥ 20 coin artıda, son 5 dk artıda, tepeden ≤ %0,10 aşağıda
        # (biri ölçülemezse giriş yok) ve LC ≥ 2; Değ. 28: sıçrama değil (son 2 dk ≤ 30 dk yükselişin yarısı)
        # Değ. 30: aynası sağlanırsa SHORT (LC_DN ≥ 2); iki yön aynı anda olamaz
        side = market_side(mkt30, up_n, dn_n, mkt5, peak, trough, jump)
        if side == LONG:
            sc = score
            gated = [s for s in score.index if U.loc[s, "LC"] >= 2
                     and (not ENTRY_RT_POSITIVE or U.loc[s, "r_t"] > rt_min) and (not UNI_REQUIRE_UP or U.loc[s, "CHG24"] > 0)]
        elif side == SHORT:
            sc = score_s
            gated = [s for s in score_s.index if U.loc[s, "LC_DN"] >= 2]
        else:
            sc, gated = score, []
        held = {p.sym for p in self.pos if p.status != "closed"}
        ranked = sorted(gated, key=lambda s: -sc[s])
        free = min(max(SLOTS - len(held), 0), MAX_NEW_PER_TICK)   # 19:00: karar anı başına en fazla 1 yeni giriş (Değ. 30: 4 yuva ortak)
        r_btc = feats.get("BTCUSDT", {}).get("r_t_raw", np.nan)
        # etiket HAM son 60 dk ile (06.11 ~18:05'ten önceki tanım; audit/label_check.py aynı) — kararlar ortalamalı r_t ile
        lab = {s: label_of({**U.loc[s].to_dict(), "r_t": U.loc[s].get("r_t_raw", np.nan)}) for s in U.index}
        chosen, skipped, blocked = [], [], []
        for s in ranked:
            if len(chosen) >= free:
                break
            if s in held:
                continue
            if s in sold_now:                              # bu turda satıldı; bir sonraki turdan (5 dk) itibaren girilebilir
                skipped.append(f"{s}(bu turda satıldı)")
                continue
            if self.demo_status.get(s) != "TRADING":
                skipped.append(f"{s}(demo {self.demo_status.get(s)})")
                continue
            tr_ = float(U.loc[s].get("TICK_REL", np.nan))
            if not tr_ <= TICK_MAX_REL:                    # Değ. 25: fiyat adımı kaba (ya da ölçülemedi) → girme
                skipped.append(f"{s}(fiyat adımı %{tr_ * 100:.2f})")
                continue
            if coin_spike(side, float(U.loc[s].get("r_t_raw", np.nan)), float(U.loc[s].get("COIN_J_UP", np.nan)),
                          float(U.loc[s].get("COIN_J_DN", np.nan))):   # Değ. 30 (2): son 60 dk tek 2 dk sıçramasından
                skipped.append(f"{s}(60 dk sıçrama: son 60 dk {float(U.loc[s].get('r_t_raw', np.nan)):+.2%}, en büyük 2 dk "
                               f"{float(U.loc[s].get('COIN_J_UP' if side == LONG else 'COIN_J_DN', np.nan)):+.2%})")
                continue
            if side == LONG and SPOT_FILTER_ON and lab[s][1]:   # kullanıcı 06.11 "b ekle": short kapatma + spotsuz → girme (yalnız long)
                skipped.append(f"{s}(short kapatma, spotsuz)")
                blocked.append(s)
                continue
            if self.dry or self.enter(s, t, float(sc[s]), {**{k_: float(U.loc[s, k_]) for k_ in COMPONENTS + (
                    "R30", "r_t", "r_t_raw", "LC_DN", "COIN_J_UP", "COIN_J_DN")}, **mk}, self.vol60(s, t), side):
                chosen.append(s)
            else:
                skipped.append(f"{s}(giriş hatası)")
        with self.dblock:
            for s in U.index:
                self.db.execute("insert into scores (ts, sym, feats, gated, score, chosen, side, score_s) values (?,?,?,?,?,?,?,?)",
                                (t, s, json.dumps({k_: (None if not np.isfinite(float(v)) else float(v))
                                                   for k_, v in U.loc[s].items()}), int(s in gated),
                                 float(score.get(s, np.nan)), int(s in chosen), side, float(score_s.get(s, np.nan))))
                g = lambda c_: (None if c_ not in U.columns or not np.isfinite(float(U.loc[s, c_])) else float(U.loc[s, c_]))  # noqa: E731
                self.db.execute("insert or replace into labels values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (t, s, g("r_t_raw"), None if not np.isfinite(r_btc) else float(r_btc), g("OI_1"), g("TAKER_1"),
                                 g("SPOT_SHARE_1"), g("SPOT_REL_1"), g("SPOT_TAKER_1"), g("DD_48"), g("BOUNCE_48"),
                                 lab[s][0], int(lab[s][1]), int(s in blocked), int(s in chosen), int(SPOT_FILTER_ON)))
            self.db.commit()
        msg = (f"dakika {pd.Timestamp(t, unit='ms')}: puanlanan {len(score)}, piyasa son 30 dk {mkt30:+.3%} "
               f"({len(r30s)} coin), artıda {up_n} / ekside {dn_n}, son 5 dk {mkt5:+.3%}, tepeden {peak:+.3%}, dipten {trough:+.3%}, "
               f"son 2 dk {jump:+.3%} → {side or 'yön yok ✗'}, "
               f"şartı sağlayan {len(gated)}, boş yuva {free}, "
               f"seçilen {chosen}, atlanan {skipped} | en iyi 5: " + ", ".join(f"{s} {sc[s]:.2f}" for s in ranked[:5]))
        if chosen or sold_now or t % (15 * M) == 0 or self.dry:   # journal şişmesin: olay varsa ya da 15 dk'da bir
            log(msg)
        self.save()

    # ------------------------------------------------------------------ emirler
    def enter(self, sym: str, t: int, score: float, feats: dict, vol: float = 0.0, side: str = LONG) -> bool:
        """Giriş emri konursa True. 06.11 düzeltmeleri: demo fiyatı 0 (boş defter) → giriş yok; adet 100 $'a EN YAKIN
        (aşağı değil); emir gönderilirken hata olursa pozisyon kaydı silinir (eskiden emirsiz kayıt yuvayı süresiz tutardı;
        GTX konduğu anda dolamaz, bu yüzden silmek güvenli — olası kabul edilmiş emir cid ile iptal edilir)."""
        p = None
        try:
            try:
                self.rest.margin_type(sym, "ISOLATED")
            except ExchangeError as e:
                if e.code not in (-4046,):                     # "değiştirmeye gerek yok"
                    raise
            r = self.rest.leverage(sym, LEV)                   # 06.11: borsanın yanıtı geri okunur; uymazsa giriş yok
            if int(r.get("leverage", 0)) != LEV or float(r.get("maxNotionalValue", 0)) < 1.05 * NOTIONAL:
                raise ValueError(f"kaldıraç geri okuması uymadı (istenen {LEV}×, {NOTIONAL:.0f} $): {r}")
            bid, ask = self.demo_bid_ask(sym)
            ref = bid if side == LONG else ask                 # Değ. 30: short'ta demo en iyi satışa post-only SELL
            if not ref > 0:
                raise ValueError(f"demo defteri boş ({'alış' if side == LONG else 'satış'} {ref})")
            f = self.filt[sym]
            if not (np.isfinite(vol) and 0 < vol <= VOL_MAX):
                raise ValueError(f"VOL60 geçersiz ({vol})")
            # 06.11 ~19:00: geri çekilme fiyatı (aşağı tick) ve oynaklığa göre büyüklük (aşağı adet → stopta kayıp ≤ RISK_USD)
            px = ref if ENTRY_CHASE or side == SHORT else f.floor(bid * (1 - PULLBACK), f.tick)   # 07.11: hemen al (en iyi alış)
            # 07.11 Değişiklik 24: büyüklük sabit NOTIONAL (SIZE_BY_VOL = False); Pos.vol = 0 → −STOP_USD zarar stopu yolu
            notional = min(NOTIONAL, RISK_USD / (BRACKET_K * vol)) if SIZE_BY_VOL else NOTIONAL
            qty = f.floor(notional / px, f.step)
            if qty * px < f.min_notional:
                raise ValueError(f"büyüklük borsa alt sınırının altında ({qty} × {px})")
            feats = {**feats, "VOL60": vol, "PB_REF": ref, "PB_PX": px, "NOTIONAL_T": notional}
            p = Pos(sym=sym, decision_ms=t, score=score, feats=feats, target_qty=qty, lev=LEV, vol=vol if SIZE_BY_VOL else 0.0,
                    pb_px=0.0 if ENTRY_CHASE or side == SHORT else px, ref_px=ref, side=side)
            self.pos.append(p)
            self.place_entry(p, px)
            log(f"GİRİŞ EMRİ {side} {sym}: {qty} adet @ {f.f(px, f.tick)} ("
                + ("demo en iyi satış, düşerse takip; " if side == SHORT else "demo en iyi alış, yükselirse takip; " if ENTRY_CHASE
                   else f"sinyal anı demo alış {bid}, −%{PULLBACK * 100:.1f} geri çekilme; ")
                + f"≈{qty * px:.1f} $), kâr al net +{TP_NET_USD:.0f} $, zarar stopu −{STOP_USD:.0f} $, oynaklık %{vol * 100:.2f}, "
                f"puan {score:.2f}, piyasa son 30 dk {feats.get('MKT_30', np.nan):+.2%} (artıda {feats.get('MKT_UP')} / ekside "
                f"{feats.get('MKT_DN')}, son 5 dk {feats.get('MKT_5', np.nan):+.2%}, tepeden {feats.get('MKT_PEAK', np.nan):+.2%}, "
                f"dipten {feats.get('MKT_TROUGH', np.nan):+.2%}, son 2 dk {feats.get('MKT_JUMP', np.nan):+.2%}), coin son 30 dk "
                f"{feats.get('R30', np.nan):+.2%}, LC {feats['LC']:.0f} / LC_DN {feats.get('LC_DN', np.nan):.0f}, son 60 dk "
                f"{feats.get('r_t', np.nan):+.2%} (ham {feats.get('r_t_raw', np.nan):+.2%}, en büyük 2 dk "
                f"{feats.get('COIN_J_UP' if side == LONG else 'COIN_J_DN', np.nan):+.2%})")   # Telegram'a dolunca gider
            return True
        except Exception as e:  # noqa: BLE001
            self.event("enter_error", {"sym": sym, "error": str(e)[:300]})
            log(f"giriş hatası {sym}: {e}")
            if p is not None and p.filled_qty <= 0:
                if p.cur_cid:
                    try:
                        self.rest.cancel_order(sym, p.cur_cid)
                    except Exception:  # noqa: BLE001
                        pass
                self.pos = [x for x in self.pos if x is not p]
                self.save()
            return False

    def place_entry(self, p: Pos, price: float) -> None:
        f = self.filt[p.sym]
        rem = f.floor(p.target_qty - p.filled_qty, f.step)
        if rem <= 0 or rem * price < f.min_notional:
            return
        c = self.cid("en")
        try:
            r = self.rest.new_order(symbol=p.sym, side="BUY" if sd(p.side) > 0 else "SELL", type="LIMIT", timeInForce="GTX",
                                    price=f.f(price, f.tick),
                                    quantity=f.f(rem, f.step), newClientOrderId=c)
        except Exception:
            try:                                           # yanıt kaybolduysa emir borsada olabilir: aynı cid ile iptal
                self.rest.cancel_order(p.sym, c)
            except Exception:  # noqa: BLE001
                pass
            raise
        p.cur_cid, p.cur_price, p.placed_ms = c, price, int(time.time() * 1000)
        p.entry_cids.append(c)
        p.entry_oids.append(r.get("orderId"))
        self.absorb(p, r)

    def absorb(self, p: Pos, r: dict) -> None:
        """Bir giriş emrinin (son) durumundan dolan miktarı topla. Aynı emri iki kez saymamak için cid başına kayıt."""
        q = float(r.get("executedQty") or 0)
        px = float(r.get("avgPrice") or 0)
        key = r.get("clientOrderId")
        done = p.feats.setdefault("_absorbed", {})
        prev_q = done.get(key, 0.0)
        if q > prev_q and not px > 0:
            # 06.11 13:24 hata: ZEC emri iptal edilirken (yeniden fiyatlama) 0,512 adet doldu; iptal yanıtında avgPrice 0
            # geldi → 677 $ değer 0 sayıldı, ortalama giriş 726,8 (gerçek 1.322,2), acil stop 683'e taşındı. Artık: cumQuote,
            # yoksa emri borsadan yeniden okuyup avgPrice; ikisi de yoksa HATA (yanlış değerle toplamaz).
            cq = float(r.get("cumQuote") or 0)
            if cq > 0:
                px = cq / q
            else:
                r2 = self.rest.request("GET", "/fapi/v1/order", {"symbol": p.sym, "origClientOrderId": key})
                px = float(r2.get("avgPrice") or 0)
                if float(r2.get("executedQty") or 0) != q or not px > 0:
                    raise RuntimeError(f"absorb: {p.sym} {key} dolum fiyatı okunamadı (q={q}, yanıt {r2})")
            self.event("avgprice_zero", {"sym": p.sym, "cid": key, "q": q, "prev_q": prev_q, "px_used": px})
        if q > prev_q:
            p.filled_qty += q - prev_q
            p.filled_val += (q - prev_q) * px
            done[key] = q
            if not p.fill_ms:
                p.fill_ms = int(time.time() * 1000)
                p.status = "open"
                p.entry = p.filled_val / p.filled_qty
                self.place_estop(p)
            p.entry = p.filled_val / p.filled_qty

    def big(self, p: Pos) -> bool:
        return p.target_qty * p.entry >= BIG_NOTIONAL and p.filled_qty > 0

    def volmode(self, p: Pos) -> bool:                    # 06.11 ~19:00 kuralı (eski pozisyonlarda vol = 0)
        return p.vol > 0 and p.filled_qty > 0

    def estop_px(self, p: Pos) -> str:
        """Büyük işlem (06.11 ~14:05): tetik = max(giriş − STOP_USD / dolan adet → tick'e yukarı, giriş × 0,94 → tick'e aşağı).
        Küçük (eski) işlem: giriş × 0,94 (−%6)."""
        f = self.filt[p.sym]
        if sd(p.side) < 0:                                # Değ. 30 short: tetik = min(giriş + 5 $ / adet → aşağı tick, giriş × 1,06)
            six_s = f.ceil(p.entry * (1 + ESTOP), f.tick)
            if self.big(p):
                return f.f(min(f.floor(p.entry + STOP_USD / p.filled_qty, f.tick), six_s), f.tick)
            return f.f(six_s, f.tick)
        six = f.floor(p.entry * (1 - ESTOP), f.tick)
        if self.volmode(p):                               # 19:00: giriş × (1 − k·VOL60), yukarı tick (kayıp ≤ RISK_USD)
            return f.f(max(f.ceil(p.entry * (1 - BRACKET_K * p.vol), f.tick), six), f.tick)
        if self.big(p):
            return f.f(max(f.ceil(p.entry - STOP_USD / p.filled_qty, f.tick), six), f.tick)
        return f.f(six, f.tick)

    def place_estop(self, p: Pos, px: str | None = None) -> None:
        if not STOP_ON:                                   # Değ. 23: zarar stopu emri konmaz
            return
        f = self.filt[p.sym]
        c = self.cid("zs" if (self.big(p) or self.volmode(p)) else "es")   # zs = zarar stopu, es = −%6 acil stop
        px = px or self.estop_px(p)
        self.rest.new_algo(symbol=p.sym, side="SELL" if sd(p.side) > 0 else "BUY", type="STOP_MARKET", triggerPrice=px,
                           closePosition="true", workingType="MARK_PRICE", clientAlgoId=c)
        p.es_cid, p.es_px = c, px

    def reset_estop(self, p: Pos) -> None:
        """Stop seviyesi (estop_px: ortalama giriş ve dolan adede göre) değiştiyse: eski iptal → yeni konur. Yeni reddedilirse
        eski seviye geri konur (pozisyon stopsuz kalmaz). 06.11 ~14:05: yeni seviye "hemen tetiklenir" (−2021) diye
        reddedilirse zarar zaten −5 $'ı geçmiştir → piyasa emriyle satılır (kullanıcı: açık pozisyonlara da uygula);
        satış olmazsa eski stop geri konur."""
        if not STOP_ON:                                   # Değ. 23: stop yok; borsada (eski) stop varsa iptal edilir
            if p.es_cid:
                try:
                    self.rest.cancel_algo(p.es_cid)
                except ExchangeError:
                    pass
                self.event("estop_removed", {"sym": p.sym, "cid": p.es_cid, "px": p.es_px})
                log(f"zarar stopu {p.sym}: {p.es_px} İPTAL (Değ. 23: stop yok)")
                p.es_cid, p.es_px = "", ""
            return
        px = self.estop_px(p)
        if px == p.es_px:
            return
        old_px = p.es_px
        try:
            self.rest.cancel_algo(p.es_cid)
        except ExchangeError:
            pass
        try:
            self.place_estop(p, px)
            log(f"zarar stopu {p.sym}: {old_px} → {px} (ortalama giriş {p.entry:.6g}, {p.filled_qty:g} adet)")
        except Exception as e:  # noqa: BLE001
            self.event("estop_reset_error", {"sym": p.sym, "error": str(e)[:300], "px": px})
            if isinstance(e, ExchangeError) and e.code == -2021:
                log(f"zarar stopu {p.side} {p.sym}: {px} hemen tetiklenirdi (fiyat stop seviyesini geçmiş) → piyasa emriyle kapatılıyor")
                self.exit_market(p, "zarar_stop")
                if p.status == "closed":
                    return
            if old_px:
                self.place_estop(p, old_px)

    def tp_price(self, p: Pos) -> float:
        """Büyük işlem: net = q·tp·(1 − maker) − q·giriş·(1 + maker) = TP_NET_USD → tp; yukarı tick'e yuvarlanır (net ≥ 5 $)."""
        f = self.filt[p.sym]
        if sd(p.side) < 0 and p.filled_qty > 0:           # Değ. 30 short: q·giriş·(1 − maker) − q·tp·(1 + maker) = 5 → aşağı tick
            return f.floor((p.entry * (1 - MAKER) - TP_NET_USD / p.filled_qty) / (1 + MAKER), f.tick)
        if TP_NET_ALL and p.filled_qty > 0:               # Değ. 23: her işlemde net +TP_NET_USD (komisyon sonrası)
            px = (TP_NET_USD / p.filled_qty + p.entry * (1 + MAKER)) / (1 - MAKER)
        elif self.volmode(p):                             # 19:00: giriş × (1 + k·VOL60), yukarı tick
            px = p.entry * (1 + BRACKET_K * p.vol)
        elif p.target_qty * p.entry >= BIG_NOTIONAL and p.filled_qty > 0:
            px = (TP_NET_USD / p.filled_qty + p.entry * (1 + MAKER)) / (1 - MAKER)
        else:
            px = p.entry * (1 + TP)
        return f.ceil(px, f.tick)

    def place_tp(self, p: Pos) -> None:
        f = self.filt[p.sym]
        c = self.cid("tp")
        self.rest.new_order(symbol=p.sym, side="SELL" if sd(p.side) > 0 else "BUY", type="LIMIT", timeInForce="GTC",
                            reduceOnly="true", price=f.f(self.tp_price(p), f.tick),
                            quantity=f.f(f.floor(p.filled_qty, f.step), f.step), newClientOrderId=c)
        p.tp_cid = c

    def cancel_all(self, p: Pos) -> None:
        for c in (p.tp_cid, p.cur_cid if p.status == "pending" else ""):
            if c:
                try:
                    self.rest.cancel_order(p.sym, c)
                except ExchangeError:
                    pass
        for c in (p.pr_cid, p.es_cid):
            if c:
                try:
                    self.rest.cancel_algo(c)
                except ExchangeError:
                    pass

    def position_amt(self, sym: str) -> float:
        for x in self.rest.request("GET", "/fapi/v2/positionRisk", {"symbol": sym}):
            if x["symbol"] == sym:
                return float(x["positionAmt"])
        return 0.0

    def exit_market(self, p: Pos, reason: str) -> None:
        """06.11 ~14:05 denetim düzeltmesi: (a) giriş hâlâ sürüyorsa önce giriş emri durdurulur (sonradan dolup yetim pozisyon
        açmasın); (b) piyasa emri başarısız olursa exit_cid temizlenir (önce: dakikalık kontrol bir daha bakmıyordu) ve iptal
        edilen kâr al emri geri konur; sonraki dakika kontrol / stop yeniden dener."""
        tp_cancelled = False
        try:
            if not p.tp_cid and p.cur_cid:
                try:
                    self.absorb(p, self.rest.cancel_order(p.sym, p.cur_cid))
                except ExchangeError:
                    pass
            if p.tp_cid:
                try:
                    self.rest.cancel_order(p.sym, p.tp_cid)
                    tp_cancelled = True
                except ExchangeError:
                    pass
            amt = self.position_amt(p.sym)
            if sd(p.side) * amt > 0:                       # Değ. 30: short'ta adet eksi, kapatma BUY
                f = self.filt[p.sym]
                c = self.cid("mx")
                p.exit_cid, p.exit_reason = c, reason
                try:                                       # 14:13: piyasa emri sınırını aşan adet parçalara bölünür
                    left, first = f.floor(abs(amt), f.mstep), True
                    cap = f.floor(f.mmax, f.mstep) if f.mmax > 0 else left
                    while left > 0:
                        q = min(left, cap)
                        self.rest.new_order(symbol=p.sym, side="SELL" if sd(p.side) > 0 else "BUY", type="MARKET", reduceOnly="true",
                                            quantity=f.f(q, f.mstep), newClientOrderId=c if first else self.cid("mx"))
                        first = False
                        left = f.floor(left - q + f.mstep / 2, f.mstep) if left - q > f.mstep / 2 else 0
                except Exception:
                    p.exit_cid, p.exit_reason = "", ""
                    if tp_cancelled:
                        try:
                            self.place_tp(p)
                        except Exception as e2:  # noqa: BLE001
                            self.event("tp_restore_error", {"sym": p.sym, "error": str(e2)[:300]})
                    raise
            for c in (p.pr_cid, p.es_cid):
                if c:
                    try:
                        self.rest.cancel_algo(c)
                    except ExchangeError:
                        pass
            self.finalize(p)
        except Exception as e:  # noqa: BLE001
            self.event("exit_error", {"sym": p.sym, "error": str(e)[:300]})
            log(f"çıkış hatası {p.sym}: {e}")

    # ------------------------------------------------------------------ izleme (5 sn)
    def monitor(self) -> None:
        now = int(time.time() * 1000)
        for p in [p for p in self.pos if p.status == "pending" or (p.status == "open" and not p.tp_cid)]:
            try:
                r = self.rest.request("GET", "/fapi/v1/order", {"symbol": p.sym, "origClientOrderId": p.cur_cid})
                self.absorb(p, r)
                if p.filled_qty > 0 and p.es_cid and not p.exit_cid:   # 14:05: dolan adet arttıkça stop −5 $'a taşınır
                    self.reset_estop(p)
                    if p.status == "closed" or p.exit_cid:
                        continue
                st = r.get("status")
                done = p.filled_qty >= p.target_qty - self.filt[p.sym].step / 2   # 14:12: 1e-12 küsurat yüzünden STRK "dolmadı" sayılıyordu
                timeout = now - p.decision_ms >= ENTRY_TIMEOUT_S * 1000
                if done or (timeout and st in ("FILLED", "CANCELED", "EXPIRED")):
                    self.entry_done(p)
                    continue
                if timeout:
                    try:
                        self.absorb(p, self.rest.cancel_order(p.sym, p.cur_cid))
                    except ExchangeError:
                        pass
                    continue
                bid, ask = self.demo_bid_ask(p.sym)
                if p.pb_px > 0:                            # 19:00 geri çekilme: sabit fiyat, yukarı taşınmaz
                    if st in ("CANCELED", "EXPIRED"):      # (yalnız borsa düşürdüyse yeniden; fiyat düştüyse daha aşağıdan)
                        f_ = self.filt[p.sym]
                        self.place_entry(p, min(p.pb_px, f_.floor(bid, f_.tick)) if bid > 0 else p.pb_px)
                    continue
                ref = bid if sd(p.side) > 0 else ask        # Değ. 30: short'ta en iyi satış, düşerse aşağı taşınır
                moved = ref > p.cur_price if sd(p.side) > 0 else 0 < ref < p.cur_price
                if st in ("CANCELED", "EXPIRED") or (moved and now - p.placed_ms >= REPRICE_S * 1000):
                    if st in ("NEW", "PARTIALLY_FILLED"):
                        try:
                            self.absorb(p, self.rest.cancel_order(p.sym, p.cur_cid))
                        except ExchangeError:
                            pass
                    if ref > 0:
                        self.place_entry(p, ref)
            except Exception as e:  # noqa: BLE001
                self.event("monitor_error", {"sym": p.sym, "stage": "entry", "error": str(e)[:300]})
        for p in [p for p in self.pos if p.status == "open" and p.tp_cid]:
            try:
                amt = self.position_amt(p.sym)
                if sd(p.side) * amt <= 0:                  # Değ. 30: short'ta adet eksi
                    self.finalize(p)
                    continue
                if not p.exit_cid:                         # 14:05: stop kurala uymuyorsa (ör. geri konmuş eski stop) yeniden
                    self.reset_estop(p)                    # dene; uyuyorsa istek atmaz
                    if p.status == "closed":
                        continue
                if PROTECTION_ON and not p.protected and sd(p.side) > 0:
                    bid, _ = self.demo_bid_ask(p.sym)
                    lvl = p.entry * PROTECT
                    if bid > lvl:
                        f = self.filt[p.sym]
                        c = self.cid("pr")
                        try:
                            self.rest.new_algo(symbol=p.sym, side="SELL", type="STOP_MARKET",
                                               triggerPrice=f.f(f.ceil(lvl, f.tick), f.tick), reduceOnly="true",
                                               quantity=f.f(f.floor(amt, f.step), f.step), workingType="CONTRACT_PRICE",
                                               clientAlgoId=c)
                            p.pr_cid, p.protected = c, True
                            log(f"koruma {p.sym}: {f.ceil(lvl, f.tick)} seviyesine stop kondu (demo {bid})")
                        except ExchangeError as e:
                            if e.code == -2021:                # hemen tetiklenirdi: fiyat zaten geri döndü
                                self.exit_market(p, "koruma")
                            else:
                                raise
            except Exception as e:  # noqa: BLE001
                self.event("monitor_error", {"sym": p.sym, "stage": "open", "error": str(e)[:300]})
        self.pos = [p for p in self.pos if p.status != "closed"]
        self.save()

    def entry_done(self, p: Pos) -> None:
        f = self.filt[p.sym]
        if p.filled_qty <= 0:
            p.status = "closed"
            self.event("entry_unfilled", {"sym": p.sym, "decision": p.decision_ms})
            log(f"giriş dolmadı {p.sym}, vazgeçildi")
            return
        if p.filled_qty * p.entry < f.min_notional:      # kırıntı: kapat
            self.exit_market(p, "kırıntı")
            return
        p.status = "open"
        self.reset_estop(p)
        if p.status == "closed" or p.exit_cid:            # zarar stopu −5 $'ı geçmişti → satıldı / satılıyor
            return
        self.place_tp(p)
        lv = ""
        try:                                               # 06.11: borsadaki kaldıraç + tasfiye fiyatı geri okunur
            x = next(x for x in self.rest.request("GET", "/fapi/v2/positionRisk", {"symbol": p.sym}) if x["symbol"] == p.sym)
            lev_b, p.liq_px = int(float(x["leverage"])), float(x["liquidationPrice"])
            lv = f", kaldıraç {lev_b}× (teminat {float(x['isolatedMargin']):.2f} $), tasfiye {p.liq_px:.6g}"
            if lev_b != p.lev or (p.es_px and sd(p.side) * (float(p.es_px) - p.liq_px) <= 0):   # tasfiye stoptan önce
                self.event("lev_mismatch", {"sym": p.sym, "lev_borsa": lev_b, "lev_beklenen": p.lev,
                                            "liq": p.liq_px, "es_px": p.es_px})
                self.say(f"UYARI {p.sym}: borsada kaldıraç {lev_b}× (beklenen {p.lev}×), tasfiye {p.liq_px:.6g}, "
                         f"acil stop {p.es_px}")
        except Exception as e:  # noqa: BLE001
            self.event("posrisk_error", {"sym": p.sym, "error": str(e)[:300]})
        tpx = self.tp_price(p)
        d = sd(p.side)
        tnet = (p.filled_qty * (tpx * (1 - MAKER) - p.entry * (1 + MAKER)) if d > 0 else
                p.filled_qty * (p.entry * (1 - MAKER) - tpx * (1 + MAKER)))   # kâr al dolarsa net (komisyon sonrası, fonlama hariç)
        log(f"POZİSYON {p.side} {p.sym}: {p.filled_qty:g} @ {p.entry:.6g} (≈{p.filled_qty * p.entry:.1f} ${lv}) | "
            f"kâr al {tpx:.6g} (net ≈{tnet:+.2f} $), 60 dk kontrol eşiği {p.entry * (PROTECT if d > 0 else 2 - PROTECT):.6g}, "
            + (f"zarar stopu {p.es_px} (≈{d * p.filled_qty * (float(p.es_px) - p.entry):+.2f} $)" if p.es_px else "zarar stopu YOK")
            + (f" | oynaklık %{p.vol * 100:.2f}" + (f", geri çekilme {p.ref_px} → {p.pb_px}" if p.pb_px > 0 else ", hemen alış")
               if self.volmode(p) else ""))
        val = p.filled_qty * p.entry
        if self.note:
            self.note.send(f"🟢 GİRDİ {p.side} {p.sym.removesuffix('USDT')} · {tr_hm(p.fill_ms)}\n"
                           f"{p.filled_qty:g} adet × {tr_px(p.entry)} = {val:.0f} $ ({p.lev}×, teminat {val / p.lev:.0f} $)\n"
                           f"Kâr al {f.f(tpx, f.tick).replace('.', ',')} ({tr_num((tpx / p.entry - 1) * 100, 2, True)}%, "
                           f"net {tr_num(tnet, 2, True)} $) · "
                           + (f"zarar stopu {p.es_px.replace('.', ',')} ({tr_num(d * p.filled_qty * (float(p.es_px) - p.entry), 1, True)} $)"
                              if p.es_px else "zarar stopu yok (60 dk kontrolü)")
                           + (f"\nOynaklık %{tr_num(p.vol * 100, 2)}" + (f" · geri çekilmede alındı ({tr_px(p.ref_px)} → {tr_px(p.pb_px)})"
                                                                          if p.pb_px > 0 else "")
                              if self.volmode(p) else "")
                           + f"\n{self.balance_line()}")

    def finalize(self, p: Pos) -> None:
        d = sd(p.side)
        for _ in range(10):                               # piyasa emrinin işlenmesini en fazla ~5 sn bekle
            if d * self.position_amt(p.sym) <= 0:
                break
            time.sleep(0.5)
        else:
            return                                        # hâlâ pozisyon var; sonraki izleme turunda yeniden
        self.cancel_all(p)
        tr = self.rest.request("GET", "/fapi/v1/userTrades", {"symbol": p.sym, "startTime": p.decision_ms - 60_000,
                                                              "limit": 1000})
        # Değ. 30: buys = GİRİŞ dolumları, sells = ÇIKIŞ dolumları (short'ta giriş SELL, çıkış BUY); cost = giriş $, value = çıkış $
        in_side, out_side = ("BUY", "SELL") if d > 0 else ("SELL", "BUY")
        buys = [x for x in tr if x["side"] == in_side and x["orderId"] in p.entry_oids]
        sells = [x for x in tr if x["side"] == out_side and int(x["time"]) >= p.fill_ms - 1000]
        cost = sum(float(x["quoteQty"]) for x in buys)
        value = sum(float(x["quoteQty"]) for x in sells)
        qty = sum(float(x["qty"]) for x in sells)
        fees = sum(float(x["commission"]) for x in buys + sells)
        reason = p.exit_reason
        if not reason and sells:
            oid = sells[-1]["orderId"]
            o = self.rest.request("GET", "/fapi/v1/order", {"symbol": p.sym, "orderId": oid})
            c = str(o.get("clientOrderId", ""))
            reason = "tasfiye" if c.startswith("autoclose") else (   # Değ. 23: stop yok → borsa tasfiyesi ayrı yazılır
                {"tp": "kâr_al", "pr": "koruma", "es": "acil_stop", "zs": "zarar_stop", "mx": "piyasa"}.get(c.split("-")[1] if
                                                                                              c.startswith("v9d-") else "", "bilinmiyor"))
        inc = self.rest.request("GET", "/fapi/v1/income", {"symbol": p.sym, "incomeType": "FUNDING_FEE",
                                                           "startTime": p.fill_ms, "limit": 100})
        funding = sum(float(x["income"]) for x in inc)
        pnl = d * (value - cost) - fees + funding
        exit_px = value / qty if qty else float("nan")
        feats = {k: v for k, v in p.feats.items() if not k.startswith("_")}
        self.db.execute("insert into trades (sym, decision, fill, exit, entry, exit_px, qty, cost, value, fees, funding, pnl, "
                        "pnl_pct, reason, score, feats, checks, lev, side) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (p.sym, str(pd.Timestamp(p.decision_ms, unit="ms")), str(pd.Timestamp(p.fill_ms, unit="ms")),
                         str(pd.Timestamp.now(tz="UTC").tz_localize(None)), p.entry, exit_px, qty, cost, value, fees, funding,
                         pnl, pnl / cost if cost else float("nan"), reason, p.score, json.dumps(feats),
                         json.dumps(p.checks, default=str), p.lev, p.side))
        self.db.commit()
        p.status = "closed"
        log(f"ÇIKIŞ {p.side} {p.sym} ({reason}): {p.entry:.6g} → {exit_px:.6g}, net {pnl:+.2f} $ "
            f"({(pnl / cost) if cost else float('nan'):+.2%}; {p.lev}×, teminata göre "
            f"{(pnl * p.lev / cost) if cost else float('nan'):+.2%}) [ücret {fees:.3f} $, fonlama {funding:+.3f} $]")
        if self.note:
            fee_in = sum(float(x["commission"]) for x in buys)
            fee_out = sum(float(x["commission"]) for x in sells)
            out_ms = max((int(x["time"]) for x in sells), default=int(time.time() * 1000))
            gross = d * (value - cost)
            lines = [f"{'🟢' if pnl > 0 else '🔴'} ÇIKTI {p.side} {p.sym.removesuffix('USDT')} · {REASON_TR.get(reason, reason)}",
                     f"Giriş {tr_hm(p.fill_ms)} → çıkış {tr_hm(out_ms)} ({tr_dur(out_ms - p.fill_ms)})",
                     f"Fiyat {tr_px(p.entry)} → {tr_px(exit_px)} ({tr_num((exit_px / p.entry - 1) * 100, sign=True)}%)",
                     f"Fiyat kârı {tr_num(gross, sign=True)} $",
                     f"Komisyon -{tr_num(fees)} $ (giriş {tr_num(fee_in)} + çıkış {tr_num(fee_out)})"]
            if abs(funding) >= 0.005:
                lines.append(f"Fonlama {tr_num(funding, sign=True)} $")
            lines.append(f"NET {tr_num(pnl, sign=True)} $ (teminata göre "
                         f"{tr_num((pnl * p.lev / cost * 100) if cost else float('nan'), 1, sign=True)}%)")
            bl = self.balance_line()
            if bl:
                lines.append(bl)
            self.note.send("\n".join(lines))

    # ------------------------------------------------------------------ başlangıç mutabakatı
    def reconcile(self) -> None:
        if self.rest.dual_side().get("dualSidePosition"):
            raise SystemExit("hesap çift yönlü pozisyon modunda; tek yönlü olmalı")
        for p in list(self.pos):
            amt = self.position_amt(p.sym)
            if p.status == "pending":
                try:
                    self.absorb(p, self.rest.cancel_order(p.sym, p.cur_cid))
                except ExchangeError:
                    pass
                self.entry_done(p)
            elif p.status == "open" and sd(p.side) * amt <= 0:
                self.finalize(p)
        self.pos = [p for p in self.pos if p.status != "closed"]
        # 06.11 ~11:48: açık pozisyonun borsadaki kâr al fiyatı kurala (büyükte net +5 $) uymuyorsa taşınır
        for p in [p for p in self.pos if p.status == "open" and p.tp_cid]:
            try:
                f = self.filt[p.sym]
                o = self.rest.request("GET", "/fapi/v1/order", {"symbol": p.sym, "origClientOrderId": p.tp_cid})
                want = f.f(self.tp_price(p), f.tick)
                if o.get("status") == "NEW" and float(o["price"]) != float(want):
                    self.rest.cancel_order(p.sym, p.tp_cid)
                    self.place_tp(p)
                    self.event("tp_moved", {"sym": p.sym, "old": o["price"], "new": want, "cid": p.tp_cid})
                    self.say(f"kâr al {p.sym}: {o['price']} → {want} (giriş {p.entry:.6g}, {p.filled_qty:g} adet; "
                             f"{'net +%.0f $ (Değ. 23)' % TP_NET_USD if TP_NET_ALL else '+%.2f%% (oynaklık)' % (BRACKET_K * p.vol * 100) if self.volmode(p) else ('net +%.0f $' % TP_NET_USD if p.target_qty * p.entry >= BIG_NOTIONAL else '+%3')})")
            except Exception as e:  # noqa: BLE001
                self.event("tp_move_error", {"sym": p.sym, "error": str(e)[:300]})
                log(f"kâr al taşıma hatası {p.sym}: {e}")
        for p in [p for p in self.pos if p.status == "open" and p.tp_cid and not p.exit_cid]:
            try:                                           # 06.11 ~14:05 kullanıcı: −5 $ zarar stopu açık pozisyonlara da
                self.reset_estop(p)
            except Exception as e:  # noqa: BLE001
                self.event("estop_reset_error", {"sym": p.sym, "stage": "reconcile", "error": str(e)[:300]})
        self.pos = [p for p in self.pos if p.status != "closed"]
        others = [x["symbol"] for x in self.rest.positions() if float(x["positionAmt"]) != 0
                  and x["symbol"] not in {p.sym for p in self.pos}]
        if others:
            self.event("foreign_positions", {"symbols": others})
            log(f"UYARI: botun bilmediği demo pozisyonları var (dokunulmuyor): {others}")
        self.save()

    def funding_fix(self) -> None:
        """07.11 Değişiklik 21: kapanan işlemlerin fonlamasını gecikmeli yeniden oku (bkz. funding_recheck); düzeltme olursa
        kayıt + olay + telefona kısa not (ÇIKTI mesajındaki NET eksik fonlamayla gitmişti)."""
        if self.dry:
            return
        try:
            with self.dblock:
                fixes = funding_recheck(self.db, self.rest, int(time.time() * 1000), self.fund_checked)
        except Exception as e:  # noqa: BLE001
            self.event("funding_recheck_error", {"error": str(e)[:300]})
            return
        for x in fixes:
            self.event("funding_fix", x)
            log(f"FONLAMA DÜZELTMESİ {x['sym']} (dolum {x['fill'][:19]} UTC): fonlama {x['funding_old']:+.4f} → {x['funding']:+.4f} $, "
                f"net {x['pnl_old']:+.4f} → {x['pnl']:+.4f} $")
            if self.note:
                self.note.send(f"🔧 FONLAMA DÜZELTMESİ {x['sym'].removesuffix('USDT')} (çıkış {tr_hm(x['exit_ms'])})\n"
                               f"Fonlama {tr_num(x['funding_old'], sign=True)} → {tr_num(x['funding'], sign=True)} $ · "
                               f"NET {tr_num(x['pnl_old'], sign=True)} → {tr_num(x['pnl'], sign=True)} $")

    def spike_check(self, t: int) -> set[str]:
        """Değ. 30 (3): t = dakika sınırı. Açık her pozisyonun coininde son 2 dk ham hareketi (gerçek piyasa 1 dk kapanışlar,
        c(t)/c(t − 2 dk) − 1); pencere tamamen dolumdan sonra olmalı (t − 2 dk ≥ dolum). İşlemin tersine ≥ SPIKE_MAX → piyasa
        emriyle kapat. Döner: bu dakika kapatılan coinler (aynı turda yeniden girilmez)."""
        sold: set[str] = set()
        for p in [p for p in self.pos if p.status == "open" and p.fill_ms and not p.exit_cid and p.fill_ms <= t - SPIKE_MS]:
            try:
                c1 = self.load_m1(p.sym, t)
                a, b = c1.get(t - M), c1.get(t - SPIKE_MS - M)     # t'de ve t − 2 dk'da biten mumlar
                if a is None or b is None or not b[2] > 0:
                    self.event("spike_error", {"sym": p.sym, "t": t, "error": "mum yok"})
                    continue
                mv = a[2] / b[2] - 1
                hit = sd(p.side) * mv <= -SPIKE_MAX
                with self.dblock:
                    self.db.execute("insert into spike_checks values (?,?,?,?,?,?,?,?)",
                                    (t, p.sym, p.side, p.fill_ms, a[2], b[2], mv, int(hit)))
                    self.db.commit()
                if hit:
                    log(f"TERS SIÇRAMA {p.side} {p.sym}: son 2 dk {mv:+.3%} (≥ %{SPIKE_MAX * 100:.2f} işlemin tersine; "
                        f"{b[2]:.6g} → {a[2]:.6g}) → kapat")
                    self.event("spike_exit", {"sym": p.sym, "t": t, "side": p.side, "fill_ms": p.fill_ms, "c_now": a[2],
                                              "c_2": b[2], "move": mv})
                    self.exit_market(p, "ters_sıçrama")
                    sold.add(p.sym)
            except Exception as e:  # noqa: BLE001
                self.event("spike_error", {"sym": p.sym, "t": t, "error": str(e)[:300]})
        if sold:
            self.pos = [p for p in self.pos if p.status != "closed"]
            self.save()
        return sold

    def run(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop", True))
        try:
            self.universe_24h(int(time.time() * 1000) // M * M)
        except Exception as e:  # noqa: BLE001
            self.event("universe_error", {"stage": "start", "error": str(e)[:200]})
        self.reconcile()
        self.say(f"v9 demo botu başladı: liste {'24 sa artıda olanlardan ' if UNI_REQUIRE_UP else ''}24 sa hacme göre ilk {UNI_N} (şu an {len(self.universe)}), "
                 f"oynaklık ≤ %{VOL_MAX * 100:.0f}, puan {'+'.join(SCORE_COMPONENTS)} (ivme farkı puanda yok), "
                 f"giriş şartı PİYASA (listedeki coinlerin ortalaması) son {MKT_WIN_MS // M} dk ≥ +%{MKT_MIN * 100:.2f}, "
                 f"en az {MKT_UP_MIN} coin artıda, son {MKT_FAST_MS // M} dk artıda, {MKT_WIN_MS // M} dk tepesinden en çok "
                 f"%{MKT_PEAK_MAX * 100:.2f} aşağıda, sıçrama değil (son {MKT_JUMP_MS // M} dk ≤ 30 dk yükselişin "
                 f"%{MKT_JUMP_SHARE * 100:.0f}'si) ve LC ≥ 2 → LONG; aynası (≤ −%{MKT_MIN * 100:.2f}, en az {MKT_UP_MIN} coin ekside, "
                 f"son {MKT_FAST_MS // M} dk ekside, dipten en çok %{MKT_PEAK_MAX * 100:.2f} yukarıda, düşüş sıçrama değil) ve "
                 f"LC_DN ≥ 2 → {'SHORT' if SHORT_ON else 'short KAPALI'} (4 yuva ortak); coinin son 60 dk hareketinin "
                 f"%{COIN_JUMP_SHARE * 100:.0f}'sinden fazlası tek {SPIKE_MS // M} dk sıçramasından geldiyse girilmez; açıkken son "
                 f"{SPIKE_MS // M} dk işlemin tersine ≥ %{SPIKE_MAX * 100:.2f} ise hemen kapatılır"
                 f"{', son 60 dk > +%' + format(BAND * 100, '.1f') if ENTRY_RT_POSITIVE else ''}, "
                 + f"{'KARAR SAAT BAŞI (son saat / önceki saat)' if HOURLY_DECIDE else f'KARAR {DECIDE_STEP_MS // M} DK DA BİR (son 60 dk, uçlar {SMOOTH_N} dk ort., bant ±%{BAND * 100:.1f})'}, işlem başı {NOTIONAL:.0f} $ ({LEV}×, teminat {NOTIONAL / LEV:.0f} $), "
                 f"en fazla {SLOTS} pozisyon (karar başına en çok {MAX_NEW_PER_TICK} yeni), "
                 + ("giriş hemen (demo en iyi alış, yükselirse takip, 15 dk)" if ENTRY_CHASE else
                    f"giriş sinyal fiyatının %{PULLBACK * 100:.1f} altına bekleyen alış (kovalama yok)")
                 + (f", kâr al net +{TP_NET_USD:.0f} $ (komisyon sonrası), zarar stopu YOK" if TP_NET_ALL and not STOP_ON else
                    f", kâr al net +{TP_NET_USD:.0f} $ (komisyon sonrası), zarar stopu −{STOP_USD:.0f} $ (MARK, borsada)" if TP_NET_ALL else
                    f", kâr al / zarar stopu ±{BRACKET_K:g}× oynaklık")
                 + (f", pozisyon = min({NOTIONAL:.0f} $, {RISK_USD:.0f} $ / oynaklık), " if SIZE_BY_VOL else f", pozisyon {NOTIONAL:.0f} $ sabit, ")
                 + f"fiyat adımı > %{TICK_MAX_REL * 100:.1f} olan coine girilmez, "
                 + f"{'saatlik kontrol saat başında (son saat > 0' if HOURLY_DECIDE else f'kontrol girişten 60 dk sonra {DECIDE_STEP_MS // M} dk da bir (son 60 dk ≥ −%{BAND * 100:.1f}'} "
                 f"ve kâr ≥ +%{(PROTECT - 1) * 100:.2f}; short'ta aynası; kârda değil ama son 5 dk işlem yönünde ise {GRACE_N} ek kontrol: +%"
                 f"{(PROTECT - 1) * 100:.2f}'te kapat, ters dönerse kapat, en geç {60 + GRACE_N * DECIDE_STEP_MS // M}. dk'da kapat)\n"
                 f"{self.balance_line()}")
        now_ms = int(time.time() * 1000)
        try:
            self.hour_jobs(now_ms // H * H)                # başlangıçta: 1 sa mumlar + spot ortancası hazır olsun
        except Exception as e:  # noqa: BLE001
            self.event("hour_job_error", {"error": str(e)[:300]})
        next_depth = 0.0
        next_min = (now_ms // M + 1) * M
        next_hour_job = (now_ms // H + 1) * H
        next_mon = 0.0
        while not self.stop:
            now = time.time()
            if now >= next_depth:
                next_depth = now + DEPTH_EVERY_S
                self.sample_depth()
            if now * 1000 >= next_min + MIN_DELAY_S * 1000:
                t = next_min
                next_min = (int(now * 1000) // M + 1) * M     # geciken dakika telafi edilmez, sıradakine geçilir
                if t // H * H >= next_hour_job:
                    try:
                        self.hour_jobs(t // H * H)
                    except Exception as e:  # noqa: BLE001
                        self.event("hour_job_error", {"t": t, "error": str(e)[:300]})
                    next_hour_job = t // H * H + H
                pre: set[str] = set()
                try:
                    pre = self.spike_check(t)              # Değ. 30: her dakika, karardan önce
                except Exception as e:  # noqa: BLE001
                    self.event("spike_error", {"t": t, "error": str(e)[:300]})
                try:
                    if t % DECIDE_STEP_MS:
                        self.universe_24h(t)               # liste her dakika (defter görüntüleri için), karar 5 dk'da bir (18:05)
                    else:
                        self.decide(t, pre)
                except Exception as e:  # noqa: BLE001
                    self.event("decide_error", {"t": t, "error": str(e)[:300]})
                    log(f"dakikalık karar hatası: {e}")
                self.funding_fix()
            if now >= next_mon:
                next_mon = now + MONITOR_S
                self.monitor()
            time.sleep(0.5)
        self.save()
        if self.book is not None:
            self.book.commit()
        self.say("v9 demo botu durdu (açık pozisyonların borsadaki kâr al " + ("ve zarar stopu emirleri yerinde)" if STOP_ON else
                                                                               "emirleri yerinde; zarar stopu yok)"))
        if self.note:
            self.note.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="şu dakikanın ölçümü + puan (dry_run.db); emir yok")
    a = ap.parse_args()
    b = Bot(dry=a.dry)
    if a.dry:
        b.universe_24h(int(time.time() * 1000) // M * M)
        log("deneme: 3 defter görüntüsü, 60 sn arayla (canlıda saatte 60)...")
        for i in range(3):
            b.sample_depth()
            if i < 2:
                time.sleep(60)
        t = int(time.time() * 1000) // M * M
        b.hour_jobs(t // H * H)
        # deneme: 3 defter görüntüsü son 60 dk'ya düşsün (canlıda en az 30 gerekir, denemede 3)
        for s in b.depth:
            b.depth[s] = deque([(t - 1, x[1], x[2]) for x in b.depth[s]], maxlen=200)
        b.decide(t)
        return
    b.run()


if __name__ == "__main__":
    main()
