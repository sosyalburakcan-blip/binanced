# G1 — Sembol keşfi ve arşiv doğrulaması

Tarih: 2026-11-02 (UTC 15:20–16:00). Kod: `src/trend/data/s3.py`. Komut:
`python -m uv run python -m trend.data.s3` (tam listeleme 278 sn, 6 eşzamanlı istek).

## Sonuç (onay gereken nokta)

**En kritik varsayım doğrulandı: delist edilmiş semboller arşivde duruyor.** Hepsinin aylık 1d (ve USDT için 1h)
dosyaları S3'te listeleniyor, indirildi, CHECKSUM'ları tuttu ve temiz veriye dönüştü.

| Sembol | Durum (exchangeInfo) | İlk ay | Son ay | Arşivdeki son mum (UTC) | Not |
| --- | --- | --- | --- | --- | --- |
| FTTUSDT | TRADING | 2019-12 | 2026-10 | 2022-11-15 (kapanış 04:29:59.999) | 2022-11-15 → 2023-09-22 askı; aynı sembolle yeniden açılmış, bugün işlem görüyor |
| MATICUSDT | BREAK | 2019-04 | 2024-09 | 2024-09-10 (kapanış 02:59:59.999) | SPEC'teki 03:00 ile birebir |
| RNDRUSDT | BREAK | 2021-11 | 2024-07 | 2024-07-22 (kapanış 02:59:59.999) | SPEC'teki 03:00 ile birebir |
| LUNAUSDT (eski) | — | 2020-08 | 2022-05 | 2022-05-13 (kapanış 00:39:59.999) | SPEC'teki 00:40 ile birebir |
| LUNAUSDT (yeni) | TRADING | 2022-05 | 2026-10 | — | ilk 1h mum 2022-05-31 06:00 (SPEC ile birebir); **aynı sembol, aynı dosya dizisi** → G5'te ASSET_CHANGE ile bölünmeli |
| BTCBUSD | BREAK | 2019-09 | 2023-12 | 2023-12-15 (kapanış 04:59:59.999) | |
| ETHBUSD / BNBBUSD / LUNABUSD / FTTBUSD | BREAK | 2019-10 / 2019-09 / 2020-08 / 2021-06 | 2023-12 / 2023-12 / 2023-12 / 2023-09 | | 378 BUSD çiftinin hepsi sona ermiş |
| BUSDUSDT | BREAK | 2019-09 | 2023-12 | | stable/USDT |
| BTTUSDT → BTTCUSDT | BREAK / TRADING | 2019-01 / 2022-01 | 2022-01 / 2026-10 | | G5: kesin tarih veriden okunacak |
| ERDUSDT → EGLDUSDT, FTMUSDT → SUSDT, OCEAN/AGIX, MKR → SKY, EOS, BNX, GAL, UST, BCHABC, NPXS | | | | | hepsi arşivde (`meta/symbols_raw.csv`) |

**REST'in delist edilmiş çift için dönüşü:** `GET https://data-api.binance.vision/api/v3/klines?symbol=MATICUSDT&interval=1d`
**200 ve veri döndürüyor** (son mum 2024-09-10, close_time 02:59:59.999). BTCBUSD de aynı (son mum 2023-12-15).
Yani SPEC'teki "exchangeInfo'dan kaldırılınca API'den veri alınamaz" bu uç nokta için bugün geçerli değil — delist
edilen çiftler exchangeInfo'da `BREAK` durumuyla kalıyor. Bilinmeyen sembol (`NOPEUSDT`) → HTTP 400 `-1121 Invalid symbol`.
Arşiv ile REST, ETHUSDT 2024-06 için birebir aynı (ağ testi `test_archive_matches_rest_sample`).

## S3 listeleme

- Belgelenmemiş uç nokta çalışıyor; XML yanıt, sayfa başına 1000 kayıt, `IsTruncated` + `NextMarker` sayfalama.
- Arşivde aylık klines altında **3.767** sembol dizini, günlük altında 3.755. Yalnız günlükte olan 1 sembol ailesi
  (`USDSOLD*`) dizinleri boş; dışarıda bırakıldı.
- Günlük dosyalar için büyük günlük önek listelenmedi: her çiftin son aylık ayından sonrası `marker` ile, aylık dizideki
  boş aylar ay önekiyle listelendi. Son aylık ayı global son aydan (2026-10) 1+ ay eski çiftlerde kuyruk listelenmez
  (delist; varsayım).
- 2026-10 aylık dosyaları bugün (ilk pazartesi) 10:54 UTC'de yayımlanmış; bu yüzden gereken günlük dosya yalnız
  2026-11-01 (1.322 dosya).

## Gereken set ve sonek ayrıştırma

- Kural: sembol `USDT` ile bitiyorsa quote USDT (`BUSDUSDT` → base BUSD), değilse FDUSD/BUSD/TUSD/USDC uzundan kısaya.
- **Bulgu:** Binance artık USD quote'lu çiftler açmış (`BTCUSD, BNBUSD, ETHUSD, SOLUSD, USDCUSD, USDTUSD, UUSD`).
  Sonek kuralı `BNBUSD`'yi BNB/BUSD, `USDTUSD`'yi USD/TUSD sanıyordu. Çözüm: sembol exchangeInfo'da (TRADING + BREAK,
  3.742 çift) varsa gerçek `quoteAsset` kullanılır; gereken 1.755 sembolün 1.752'si exchangeInfo'da, kalan 3'ü
  (`NBTUSDT, USDSTUSD, USDSUSDC`) sonek kuralıyla doğru. Kontrol her çalıştırmada yazdırılır.
- Stable/USDT çiftleri USDT çifti olduğu için 1h de iner (SPEC "tüm USDT çiftleri 1d ve 1h").

| Quote | Sembol | Aralık | Hâlâ aktif (son ay 2026-10) | Sona ermiş |
| --- | --- | --- | --- | --- |
| USDT | 775 | 1d + 1h | 522 | 253 |
| BUSD | 378 | 1d | 0 | 378 |
| USDC | 338 | 1d | 258 | 80 |
| FDUSD | 197 | 1d | 32 | 165 |
| TUSD | 67 | 1d | 0 | 67 |

Toplam 1.755 sembol, 2.530 sembol × aralık satırı (`meta/symbols_raw.csv`). USDT çiftlerinin ilk ay dağılımı:
2017: 6, 2018: 18, 2019: 68, 2020: 158, 2021: 127, 2022: 41, 2023: 58, 2024: 63, 2025: 102, 2026: 134.
Sona eren USDT çiftleri (son ay yılı): 2018: 2, 2019: 3, 2020: 18, 2021: 20, 2022: 38, 2023: 24, 2024: 46, 2025: 51, 2026: 51.

## Gerçek dosya sayısı ve boyut (S3 `Size`, tahmin değil)

| Tür | Aralık | Zip | Sıkıştırılmış |
| --- | --- | --- | --- |
| aylık | 1h (USDT) | 28.767 | 912,57 MB |
| aylık | 1d (tüm quote'lar) | 50.547 | 84,88 MB |
| günlük (2026-11-01) | 1h + 1d | 1.322 | 0,78 MB |
| **Toplam** | | **80.636** | **998.229.388 bayt (0,998 GB)** |

Her zip'in `.CHECKSUM` dosyası var (eksik 0). İstek sayısı = 2 × 80.636 = 161.272 (SPEC tahmini 125–235 bin aralığında).

**Süre:** arşiv istekleri CloudFront önbellek ıskası, ilk bayt 0,35–0,85 sn; indirme bant genişliği değil gecikme sınırlı
(0,2 MB/s yetiyor). Ölçülen hız `data.concurrency = 6` ile **5,9–6,0 dosya/s** (CHECKSUM zip ile paralel) →
tam indirme **≈ 3,7 saat**. Concurrency 8 (SPEC üst sınırı) ile ≈ 2,8 saat beklenir (ölçülmedi).

## Aylık dizideki boşluklar (50 çift × aralık; G4/G5 için)

Öne çıkanlar: `FTTUSDT` 2022-12…2023-08 (askı); `USDCUSDT, TUSDUSDT, USDPUSDT` ve birçok `*USDC/*TUSD` 2022-10…2023-02
(BUSD otomatik dönüşüm dönemi); `USDSUSDT` 2020-07…2026-03 (69 ay; eski USDS ile yeni USDS — ASSET_CHANGE adayı);
`BCHUP/BCHDOWNUSDT` 2020-12…2021-03; `VENUSDT` 2018-08…09; `CVCUSDT` 2023-01…04. Boş aylar için günlük dosya da yok.
Tam liste: `data/raw/_inventory_summary.json` (`gaps`).

## Çıktılar

- `meta/symbols_raw.csv` (CONTRACTS §2), `meta/exchange_info_20261102.json` (ham, 17,8 MB; rateLimits:
  REQUEST_WEIGHT 6000/dk — `settings.yaml` varsayılanıyla aynı).
- `data/raw/_inventory.csv` (indirici girdisi: her zip'in yolu, URL, boyut, LastModified) ve `_inventory_summary.json`.
