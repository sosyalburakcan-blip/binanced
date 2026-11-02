# G2–G3 — İndirme, temizleme, REST istemcisi, panel

Tarih: 2026-11-02. Kod: `src/trend/data/` (`_http.py, s3.py, download.py, clean.py, rest.py, panel.py`).
Testler: `tests/test_data_*.py` (57 çevrimdışı birim testi + 8 ağ testi, hepsi yeşil).

## Komutlar

```
# G1 envanteri (indirici gerekirse kendisi de çağırır; bugün listelenmişse yeniden listelemez)
python -m uv run python -m trend.data.s3
# G2 tam indirme (ölçülen hızla ≈ 3,7 saat; Ctrl+C güvenli, tekrar çalıştırma kaldığı yerden devam eder)
python -m uv run python -m trend.data.download --all
# alt küme örneği
python -m uv run python -m trend.data.download --symbols BTCUSDT,ETHUSDT --intervals 1d,1h --since 2024-01
# aylık yeniden kontrol (CHECKSUM'lar yeniden çekilir, yerel dosyalar yeniden hash'lenir)
python -m uv run python -m trend.data.download --all --reverify
# G3 temizleme (artımlı; yalnız defter girdileri değişen semboller yeniden kurulur)
python -m uv run python -m trend.data.clean [--intervals 1d,1h] [--symbols ...] [--force] [--workers N]
```

## G2 — indirici

- Gereken dosyalar S3 envanterinden gelir (aylık dosyalar + aylık dosyanın kapsamadığı ve S3'te gerçekten var olan
  günlük dosyalar). Günlük URL tahmin edilmediği için delist edilmiş çiftlerde 404 fırtınası olmaz; yine de 404 →
  `missing_remote`, tekrar denenmez.
- Her zip `.CHECKSUM` (SHA-256) ile doğrulanır; tutmazsa bir kez daha indirilir, yine tutmazsa `checksum_mismatch`.
  CHECKSUM yoksa `error` (temizleme kullanmaz). Ağ hatası/429/5xx → `data.max_retries` kez üstel bekleme.
- Defter `data/ledger.csv` (CONTRACTS §2 kolonları; `rel_path` = `paths.raw`'a göreli, ör.
  `monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2017-08.zip`). Satırlar anında sona eklenir, açılış/kapanışta `rel_path`
  başına tek satıra sıkıştırılır. Plan: defterde `ok` + yerelde aynı boyut + S3 boyutu değişmemiş → atla.
  Yerelde olup defterde olmayan dosya (sert kesinti) yeniden indirilmez, CHECKSUM ile doğrulanır.
- İlerleme satırı her 15 sn: dosya/toplam, MB, ok/eksik/checksum/hata sayıları, dosya/s, MB/s, kalan süre.

**Alt küme çalıştırması (gerçek ağ):** BTCUSDT, ETHUSDT, LUNAUSDT, FTTUSDT, MATICUSDT, RNDRUSDT, BTCBUSD, USDCUSDT,
BNBUSDT, XRPUSDT 1d tüm aylar + ilk 6'sının 1h tüm ayları → **1.303 dosya, hepsi `ok`, 0 checksum hatası**.
- Tekrar çalıştırma: "indirilecek 0". Zarif kesme (`interrupt_main`, 68/109'da) → çıkış 130, devamında kalan 41 indi.
  Sert öldürme (`Stop-Process -Force`, 57/103'te) → devamında kalan 46 indi, defterde tekrar/yarım satır yok.
- `--reverify`: elle bozulan bir yerel zip tespit edildi ve yeniden indirildi (224 dosya 29 sn; tamamı ≈ 2,9 saat).
- **Hız:** CloudFront önbellek ıskası (ilk bayt 0,35–0,85 sn) nedeniyle gecikme sınırlı. CHECKSUM ile zip sıralıyken
  4,2 dosya/s; CHECKSUM zip ile paralel çekilince **5,9–6,0 dosya/s** (`data.concurrency = 6`). Kalan 79.333 dosya
  (979 MB) → **≈ 3,7 saat**. Doğrudan S3 uç noktası ~2 kat hızlı (0,3 sn) ama resmi olmayan host olduğu için kullanılmadı.

## G3 — temizleme

- Çıktı `data/clean/{interval}/{SYMBOL}.parquet`, şema CONTRACTS §3 ile birebir (test ediliyor); tz-naive UTC
  `datetime64[ns]`. Zaman: değer > 1e14 → µs, tam sayı ÷1000 (satır bazında). Başlık satırı (ilk karakter rakam
  değilse) atlanır. Aylık dosyası olan ayın günlük dosyaları kullanılmaz.
- Tekrarlanan open_time: aylık > günlük > dosya adı önceliğiyle ilk satır tutulur; `exact`/`conflict` olarak
  `data/clean/{interval}/_duplicates.csv`'ye yazılır (G4 bunu okur). Alt kümede tekrar: 0.
- Belirlenimcilik: `content_hash` = `hash_pandas_object` + dtype listesinin SHA-256'sı; `_manifest.json`'da tutulur.
  `data/clean` silinip sıfırdan kurulunca 16 dosyanın hash'i birebir aynı. İkinci çalıştırma: "kurulan 0".
- Hız: süreç havuzu; alt küme (10 × 1d + 6 × 1h) 4 sn.
- **half_day (varsayım, SPEC'in amacına göre genişletildi):** her işlem diliminin ilk ve son mumu. İşaretlenenler:
  (1) çiftin ilk mumu; (2) kesik mum (close_time + 1 ms < open_time + aralık — arşivde delist/askı mumunun
  close_time'ı kesiliyor); (3) kesik mumdan sonra boşlukla gelen ilk mum; (4) çift sona ermişse son mum (son kapanış <
  defterin aralık için kapsadığı son an). Böylece aktif çiftin en yeni tam mumu işaretlenmez. Alt kümede 1d sonuçları:
  LUNAUSDT {2020-08-21, 2022-05-13, 2022-05-31}, FTTUSDT {2019-12-20, 2022-11-15, 2023-09-22}, USDCUSDT
  {2018-12-15, 2022-09-26, 2023-03-11}, MATICUSDT {2019-04-26, 2024-09-10}. 1h'de bakım pencereleri de işaretlenir.

## Veri bulguları (G4/G5 için)

- 1h verisinde 2017–2018 bakım pencerelerinde **00 dakikaya hizalı olmayan open_time** var (ör. BTCUSDT
  2018-02-09 09:28:14.789, 2018-02-11 03:28:14.789) ve kesik 1h mumları (BTCUSDT'de 15). 1d'de hizasız mum yok.
- Eski LUNA son mum 2022-05-13 00:00 (kapanış 00:39:59.999), yeni LUNA ilk 1h mum 2022-05-31 06:00 — aynı
  `LUNAUSDT` dosyalarında; G5 ASSET_CHANGE ile bölmeli. FTTUSDT 2022-11-15 04:30 → 2023-09-22 askı/yeniden açılış.

## REST istemcisi (`rest.py`) ve panel (`panel.py`)

- `RestClient.klines(symbol, interval, start, end, closed_only=True)`: yalnız `data.rest_base`, limit 1000 + startTime
  sayfalama, `X-MBX-USED-WEIGHT-1M` %80'de dakika başına kadar bekler (limit exchangeInfo'dan; bugün 6000), 429'da
  `Retry-After`, 418'de `IPBannedError` (tekrar yok), `timeZone` asla gönderilmez (hazırlanmış istek üzerinde test),
  dönüşüm `clean.normalize` ile ortak. Kapanmamış güncel mum varsayılan olarak atılır.
- `load_panel(interval, symbols=None, source="merged"|"clean", start=None, end=None)` → CONTRACTS §7. 650 sembol × 1d
  1,2 sn; 100 sembol × 1h tam geçmiş 0,9 sn. `merged` dizini yoksa `FileNotFoundError` (sessizce clean'e düşmez).

## Varsayımlar ve eksik ayarlar

- Eşzamanlılık sınırı dosya başınadır; CHECKSUM paralel çekildiği için açık bağlantı ≤ 2 × `data.concurrency`.
- `missing_remote`/`error`/`checksum_mismatch` dosyalar sonraki çalıştırmada bir kez daha denenir.
- Eksik `settings.yaml` anahtarları (modül sabiti + `TODO(settings)`): `data.http_timeout_s` (10, 60),
  `paths.inventory` (`data/raw/_inventory.csv`), `data.progress_every_s` (15), `data.rest_max_429_retries` (5),
  `paths.merged` (`data/merged`), `data.panel_read_threads` (8).
- experiments.md'ye yazma yetkim yok; G1/G2 çalıştırmalarının kaydını orkestratör eklemeli.
