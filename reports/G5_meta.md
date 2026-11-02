# G5 — Meta tablolar (symbol_map, fee_promotions, delist_announcements)

## Onay bekliyor

**SPEC'e göre bu tablolar kullanıcı onaylamadan hiçbir backtest başlamaz. Hiçbir satır onaylanmış değil.**
`verified=yes`, satırın birincil ya da güvenilir bir kaynakla (çoğunlukla binance.com duyurusu) doğrulandığı anlamına
gelir; kullanıcı onayı yerine geçmez. Aşağıdaki otomatik bölüm her satırı durumu ve kaynağıyla listeler. Onay
verildiğinde bu bölüme tarih ve onaylayan yazılmalı ve `experiments.md`'ye kayıt düşülmelidir.

Kullanıcının karar vermesi gerekenler:

1. `symbol_map.csv` içindeki 33 satırın tamamı (SPEC'teki 14 doğrulanmış satır + SPEC adaylarından 8 satır + G5'te
   bulunan 9 ek satır + oran yönü veriden doğrulanacak 2 aday).
2. `BTCSTUSDT` ve `DREPUSDT` (`candidate`): duyurular "1:10" ve "100:1" diyor ama hangi tarafın eski olduğunu açıkça
   yazmıyor. Veri inince bölünme kontrolü (`split_candidate` işaretinin `k` değeri) yönü gösterecek.
3. Veriden bulunan adaylar (`meta/symbol_map_candidates.csv`, veri inince üretilir).
4. `fee_promotions.csv` kapsamı: yalnız maker **ve** taker ücretinin herkes için sıfır olduğu kampanyalar alındı
   (aşağıya bakın). Sadece maker'ı sıfır olan kampanyaların da eklenip eklenmeyeceği.
5. FDUSD kampanya bitişi: kötümser seçim 2026-01-29 00:00 (VIP2–9 için sıfır ücretin bittiği tarih). Normal
   kullanıcılar için taker ücreti 2024-04-25 06:00'da geri gelmişti.

## Araştırma sonuçları: SPEC'in doğrulanmamış adayları

| Aday | Sonuç | Tür, oran | Eski son işlem → yeni ilk işlem (UTC) | Kaynak |
| --- | --- | --- | --- | --- |
| MC→BEAMX | doğrulandı | REDENOM, 1 MC = 100 BEAMX | 2023-11-07 03:00 → 2023-11-14 08:00 | [Binance](https://www.binance.com/en/support/announcement/0b171519f1824ee288af7343ec91ce33) |
| TOMO→VIC | doğrulandı | RENAME, 1:1 | 2023-11-20 03:00 → 2023-11-24 08:00 | [Binance](https://www.binance.com/en/support/announcement/034eee2293964e26b915b1ec5c42972a) |
| ALPHA→STELLA | **satır yok** | Proje adı Stella oldu ama Binance'te ticker **ALPHA kaldı** (çift `ALPHAUSDT` değişmedi) | — | [Binance Research "Stella (ALPHA)"](https://www.binance.com/en/research/projects/stella), [fiyat sayfası](https://www.binance.com/en/price/alpha-finance-lab). Binance'te bir ticker değişikliği duyurusu bulunamadı |
| NPXS→PUNDIX | doğrulandı | REDENOM, 1000 NPXS = 1 PUNDIX (oran 0,001) | 2021-04-05 04:00 → 2021-04-09 04:00 | [Binance](https://www.binance.com/en/support/announcement/8bdcb060635b491d912247fb00603d4d) |
| LEND→AAVE | doğrulandı | REDENOM, 100 LEND = 1 AAVE (oran 0,01) | 2020-10-12 03:00 → 2020-10-15 03:00 | [Binance](https://www.binance.com/en/support/announcement/17595222999545348c8acdd5dc41c00a) |
| BCHABC→BCH | doğrulandı | RENAME, 1:1 | 2019-11-28 02:00 → 2019-11-28 10:00 | [Binance](https://www.binance.com/en/support/announcement/360037219511) |
| STRAT→STRAX | doğrulandı | RENAME, 1:1 | 2020-11-12 08:00 → 2020-11-18 03:00 | [Binance](https://www.binance.com/en/support/announcement/1937b7781c5043efa66c07141be3bdc2). Duyuru STRAT çiftlerini saymıyor; STRATUSDT'nin var olup olmadığı veriden görülecek |
| BQX→VGX | doğrulandı, **USDT etkisi yok** | RENAME, 1:1 | 2021-08-16 04:00 → 2021-08-20 04:00 | [Binance](https://www.binance.com/en/support/announcement/25e17090279543948c8c7d27ab1668d1). Yalnız BTC ve ETH çiftleri vardı |
| BCHA→XEC | doğrulandı, **USDT etkisi yok** | REDENOM, 1 BCHA = 1.000.000 XEC | 2021-08-02 04:00 → 2021-08-06 04:00 | [Binance](https://www.binance.com/en/support/announcement/55803feab78342f596c1eca9f26f3d71). Yalnız BUSD çifti vardı |
| BTT→BTTC (kesin tarih) | doğrulandı | REDENOM, 1 BTT = 1000 BTTC | 2022-01-17 04:00 → 2022-01-25 04:00 | [Binance](https://www.binance.com/en/support/announcement/2722e6da4f5141dd9b2fb07b5b1f3f75). Açılış saati 2022-01-20'de güncellenmiş; sayfadaki son değer kullanıldı |

SPEC'te "—" olan alanlar kaynaktan dolduruldu: ERD son işlem 2020-08-31 03:00
([Binance](https://www.binance.com/en/support/announcement/aa864b2d4db24379b606249d0cba87fb)), GAL son işlem
2024-07-15 03:00 ve G açılışı 2024-07-19 08:00
([Binance](https://www.binance.com/en/support/announcement/27449abd481b473493b9c058350b4e2e)), BNX bölünmesi
2023-02-16 03:00 → 2023-02-22 08:00 ([duyuru](https://www.binance.com/en/support/announcement/4d23ada51a2e4fa182835c77d51ba1a9),
[açılış güncellemesi](https://www.binance.com/en/support/announcement/fb6c6a1c6a9947b0bd30d58314ab862c)).
MKR→SKY için binance.com duyurusu doğrudan açılamadı. Tarihler, duyuruyu aktaran
[U.Today](https://u.today/binance-to-delist-all-pairs-of-this-popular-cryptocurrency-heres-why) haberinden, oran
[Binance.US](https://support.binance.us/en/articles/12270478-binance-us-will-support-the-maker-mkr-token-swap-and-rebranding-to-sky-sky) sayfasından alındı.

**Arşivle çapraz kontrol** (`meta/symbols_raw.csv`, G1'in S3 listesi, 1d): tablodaki çiftlerin hepsi arşivde var.
İstisnalar `BQXUSDT` ve `BCHAUSDT`; ikisinin de USDT çifti hiç olmadı, beklenen durum. Farklı sembollü her satırda
eski çiftin son ayı ve yeni çiftin ilk ayı duyuru tarihleriyle tutuyor (MERGE satırları dahil). Tek fark `LUNAUSDT`;
aynı sembol yeni LUNA'ya verildiği için bu da beklenen durum. 10 Ekim 2025 iğneleri REST'te de görünüyor:
WBETHUSDT low 430,65 / close 4000, BNSOLUSDT low 34,90 / close 197,4 (ikisi de low < 0,3 × close kuralına takılıyor);
USDEUSDT low 0,65 / close 0,9978 kurala takılmıyor.

## G5'te bulunan ek satırlar (binance.com duyuruları açılarak doğrulandı)

| Satır | Tür, oran | Tarihler (UTC) | Not |
| --- | --- | --- | --- |
| STRAXUSDT bölünmesi | REDENOM (aynı sembol), 1 eski = 10 yeni | 2024-03-20 03:00 → 2024-03-28 08:00 | STRAT→STRAX zinciriyle birleşir; asset_id `STRAXUSDT` |
| BZRX→OOKI | REDENOM, 1:10 | 2021-12-20 04:00 → 2021-12-24 04:00 | |
| MFT→HIFI | REDENOM, 1 MFT = 0,01 HIFI | 2023-01-03 03:00 → 2023-01-12 08:00 | |
| TVK→VANRY | RENAME | 2023-11-27 03:00 → 2023-12-01 08:00 | |
| XZC→FIRO | RENAME | 2021-01-25 02:00 → 2021-01-29 02:00 | |
| QUICKUSDT bölünmesi | REDENOM (aynı sembol), 1:1000 | 2023-07-17 03:00 → 2023-07-21 08:00 | |
| SUNUSDT bölünmesi | REDENOM (aynı sembol), 1:1000 | 2021-06-14 04:00 → 2021-06-18 04:00 | |
| COCOSUSDT bölünmesi | REDENOM (aynı sembol), 1000 eski = 1 yeni | 2021-01-19 02:00 → 2021-01-23 02:00 | |
| COCOS→COMBO | RENAME | 2023-05-29 08:00 → 2023-06-02 08:00 | COCOS bölünmesiyle zincir; asset_id `COMBOUSDT` |

Aynı sembolde yapılan bölünmeler tabloya girmezse seride sahte −%99,9'luk düşüşler oluşur. Bu yüzden veri inince
`split_candidate` (boşluk öncesi/sonrası oran ≈ 10^k, tolerans 0,02) ve `return_check` (boşluklu aşırı getiri ≈ 10^k,
tolerans 0,05) adaylarının mutlaka incelenmesi gerekir.

**Bilinen ama tabloya eklenmeyen olası adaylar** (kaynak sayfası açılmadı ya da USDT çifti yok; veriden kontrol edilecek):
- BCC→BCHABC (Kasım 2018): yeniden adlandırma değil, BCH çatallanmasıydı. BCC sahiplerine hem BCHABC hem BCHSV
  verildi, birleştirilirse getiri yanlış olur. Ayrıca ısınma dönemine düşüyor.
- VEN→VET (Temmuz 2018, 1:100): ısınma dönemine düşüyor, veriden aday olarak çıkması beklenir.
- PHB (Kasım 2021, 100 eski = 1 yeni) ve BOT→AUCTION (Şubat 2021, 1:100) yalnız BTC, TUSD ve BUSD çiftlerinde
  vardı, USDT etkisi yok.
- Diğer token dönüşümleri `find_candidates` çıktısında görülecek. Bu çıktı isim önekini (ör. DAR→D, GAL→G) ve
  yuvarlak fiyat oranını kontrol eder.

## fee_promotions.csv kapsamı

Bu dosyaya yalnız **maker ve taker ücretinin herkes için sıfır olduğu** dönemler alındı:
- 13 BTC çifti: 2022-07-08 14:00 ile 2023-03-22 00:00 arası
  ([başlangıç](https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329),
  [bitiş](https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36)). BTC/TUSD sıfır ücrette
  2023-09-07 00:00'a kadar kaldı
  ([kaynak](https://www.binance.com/en/support/announcement/9f438c4249ff45deb34cb9f727f99f83)).
- ETH/BUSD: 2022-08-26 ile 2022-09-26 arası. Uzatma duyurusu bulunamadı ama 2023-03 duyurusu ETH/BUSD'nin
  2023-03-22'de "standart ücrete döndüğünü" yazıyor. Aradaki dönem belirsiz.
- Stablecoin/stablecoin çiftleri (TUSD/USDT, USDC/USDT, USDP/USDT 2023-03-11'den; FDUSD/USDT ve FDUSD/BUSD
  2023-07-26'dan): bitiş bulunamadı, bu yüzden `end` boş, yani kampanya sürüyor sayılır. Bu çiftler likidite için
  değil, kur çevirmek için kullanılıyor.
- BTC/FDUSD (2023-08-04'ten) ve 6 FDUSD çifti (BNB, DOGE, ETH, LINK, SOL, XRP; 2023-12-08'den): bitiş olarak
  kötümser 2026-01-29 00:00 seçildi.

**Dahil edilmeyenler (kullanıcı kararı):** yalnız maker'ı sıfır olan kampanyalar. Bunlar BUSD (2023-12-31'e
kadar tüm BUSD çiftleri), TUSD (2023-06-30'dan itibaren tüm TUSD çiftleri) ve FDUSD (2023-07-26'dan itibaren tüm
FDUSD çiftleri) kampanyalarıdır. Eklenirlerse evrenin max-likidite kuralı o dönemlerde fiilen yalnız USDT hacmine
dayanır.

## delist_announcements.csv kapsamı

Ucuza kaynaklanabilen satırlar alındı: eski LUNA (2022-05-13 00:40), FTT/USDT (duyuru 2022-11-14, kaldırma 2022-11-15
04:30; FTT/BUSD açık kaldı), OCEAN ve AGIX (duyuru 2024-06-14 10:30, kaldırma 2024-07-01 03:00). Monitoring Tag
geçmişi (2023-07-26'dan itibaren) ve diğer delist duyuruları **derlenmedi**. Duyurusu tabloda olmayan çiftlerde motor,
SPEC'e göre son işlem günü VWAP × (1 − ceza) kuralını uygular.

## Birleştirme kuralları ve varsayımlar

Ayrıntılar `src/trend/meta.py` başında. Kısaca:
- `build_merged` yalnız `verified=yes` satırları uygular. `candidate` satırlar ancak `--include-candidates` ile denenir.
- Eski fiyat oranla bölünür. Taban hacim ve taker_buy_base oranla çarpılır. Quote hacim, taker_buy_quote ve işlem
  sayısı değişmez. Zincirlerde oranlar çarpılır.
- Aynı sembolde mumlar şöyle atanır: open_time ≤ eski son işlem ise eski parça, open_time ≥ floor(yeni ilk işlem)
  ise yeni parça. İki sınır arasında kalan mumlar uyarıyla düşürülür (`meta/merge_log_{interval}.txt`).
- Farklı sembollerde sınırı veri belirler. Çakışan mumlarda yeni çift tercih edilir. Tablo zamanlarıyla uyuşmazlık
  uyarı olarak yazılır.
- ASSET_CHANGE'de eski parçanın kimliği `{SYMBOL}_until_{YYYYMMDD}` olur (ör. `LUNAUSDT_until_20220513`).
- `meta/asset_segments.csv` 1d çalıştırmasından, `meta/asset_segments_1h.csv` 1h çalıştırmasından yazılır.

## Komutlar (data/clean hazır olduğunda)

```
python -m uv run python -m trend.meta validate
python -m uv run python -m trend.quality flags          # önce: candidates bölünme işaretlerini kullanır
python -m uv run python -m trend.meta candidates        # meta/symbol_map_candidates.csv
python -m uv run python -m trend.meta merged --interval 1d
python -m uv run python -m trend.meta merged --interval 1h
python -m uv run python -m trend.meta report            # bu dosyanın otomatik bölümünü yeniler
```

## Otomatik bölüm

<!-- AUTO:BEGIN (python -m trend.meta report ile yeniden üretilir) -->

### Doğrulama

- `meta/symbol_map.csv`: geçerli
- `meta/fee_promotions.csv`: geçerli
- `meta/delist_announcements.csv`: geçerli

### symbol_map.csv (33 satır; yes: 31, candidate: 2)

| # | old_symbol | new_symbol | type | ratio | old_last_trade_utc | new_first_trade_utc | source | verified | onay |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ERDUSDT | EGLDUSDT | REDENOM | 0.001 | 2020-08-31 03:00 | 2020-09-03 03:00 | Binance duyurusu (1000 ERD = 1 EGLD; ERD işlemi 2020-08-31 03:00 durdu, EGLD/USDT 2020-09-03 03:00 açıldı) https://www.binance.com/en/support/announcement/aa864b2d4db24379b606249d0cba87fb ; tamamlanma https://www.binance.com/en/support/articles/24feffc4fccf446f9c97fe527cf379be | yes | Onay bekliyor |
| 2 | BTTUSDT | BTTCUSDT | REDENOM | 1000 | 2022-01-17 04:00 | 2022-01-25 04:00 | Binance duyurusu (1 BTT eski = 1000 BTTC; BTT çiftleri 2022-01-17 04:00 delist, BTTC/USDT 2022-01-25 04:00, açılış saati 2022-01-20 güncellemesiyle) https://www.binance.com/en/support/announcement/2722e6da4f5141dd9b2fb07b5b1f3f75 ; tamamlanma https://www.binance.com/en/support/announcement/1fe6400982cd41fcaefe8a88172af0f8 | yes | Onay bekliyor |
| 3 | LUNAUSDT |  | DELIST |  | 2022-05-13 00:40 |  | Decrypt: Binance LUNA ve UST çiftlerini 2022-05-13 00:40 UTC'de spot ve marjından kaldırdı https://decrypt.co/100290/binance-halts-trading-terra-delists-luna-ust (eski LUNA sonra LUNC adını aldı; eski USDT serisi delist kuralıyla kapanır) | yes | Onay bekliyor |
| 4 | LUNAUSDT | LUNAUSDT | ASSET_CHANGE |  | 2022-05-13 00:40 | 2022-05-31 06:00 | Binance: Terra 2.0 (LUNA) LUNA/USDT 2022-05-31 06:00 açıldı, eski LUNA → LUNC https://www.binance.com/en/support/announcement/d044a6742e484b77a170111460b0eed3 ; eski seri sonu: https://decrypt.co/100290/binance-halts-trading-terra-delists-luna-ust | yes | Onay bekliyor |
| 5 | BNXUSDT | BNXUSDT | REDENOM | 100 | 2023-02-16 03:00 | 2023-02-22 08:00 | Binance (1 eski BNX = 100 yeni BNX; spot 2023-02-16 03:00 delist) https://www.binance.com/en/support/announcement/4d23ada51a2e4fa182835c77d51ba1a9 ; açılış 2023-02-24'ten 2023-02-22 08:00'a alındı https://www.binance.com/en/support/announcement/fb6c6a1c6a9947b0bd30d58314ab862c ; arşiv boşluğu https://dev.binance.vision/t/missing-data-in-binances-bnxusdt-1d-klines/15877 | yes | Onay bekliyor |
| 6 | OCEANUSDT | FETUSDT | MERGE_INTO_EXISTING | 0.433226 | 2024-07-01 03:00 |  | Binance (1 OCEAN = 0.433226 FET; OCEAN spot 2024-07-01 03:00 delist; duyuru 2024-06-14) https://www.binance.com/en/support/announcement/e485541c370240adba3929fded74f269 ; https://beincrypto.com/binance-to-delist-ai-cryptos-ocean-agix/ | yes | Onay bekliyor |
| 7 | AGIXUSDT | FETUSDT | MERGE_INTO_EXISTING | 0.43335 | 2024-07-01 03:00 |  | Binance (1 AGIX = 0.433350 FET; AGIX spot 2024-07-01 03:00 delist; duyuru 2024-06-14) https://www.binance.com/en/support/announcement/e485541c370240adba3929fded74f269 ; https://beincrypto.com/binance-to-delist-ai-cryptos-ocean-agix/ | yes | Onay bekliyor |
| 8 | GALUSDT | GUSDT | REDENOM | 60 | 2024-07-15 03:00 | 2024-07-19 08:00 | Binance (1 GAL = 60 G; GAL spot 2024-07-15 03:00 delist; G/USDT 2024-07-19 08:00) https://www.binance.com/en/support/announcement/27449abd481b473493b9c058350b4e2e ; tamamlanma https://www.binance.com/en/support/announcement/6df074e0264648448c260b1430240e2f | yes | Onay bekliyor |
| 9 | RNDRUSDT | RENDERUSDT | RENAME | 1 | 2024-07-22 03:00 | 2024-07-26 08:00 | Binance duyurusu (SPEC Kaynaklar) https://www.binance.com/en/support/announcement/d1f2ae8d99b24439a7a900caa9bb6b3b | yes | Onay bekliyor |
| 10 | MATICUSDT | POLUSDT | RENAME | 1 | 2024-09-10 03:00 | 2024-09-13 10:00 | Binance duyurusu (SPEC Kaynaklar) https://www.binance.com/en/support/articles/6a6de383727f4659a3050f7982e1620f | yes | Onay bekliyor |
| 11 | FTMUSDT | SUSDT | RENAME | 1 | 2025-01-13 03:00 | 2025-01-16 08:00 | Binance duyurusu (SPEC Kaynaklar) https://www.binance.com/en/support/announcement/aec6fcbc84b749eeab6690e6bcac2f3d | yes | Onay bekliyor |
| 12 | BNXUSDT | FORMUSDT | RENAME | 1 | 2025-03-18 03:00 | 2025-03-19 08:00 | Binance duyurusu (SPEC Kaynaklar) https://www.binance.com/en/support/announcement/2f963977c7274e0583f16f2e26987b61 | yes | Onay bekliyor |
| 13 | EOSUSDT | AUSDT | RENAME | 1 | 2025-05-26 03:00 | 2025-05-28 08:00 | Binance duyurusu (SPEC Kaynaklar) https://www.binance.com/en/support/announcement/1e89a9ca957c4b0ca7502e60b993e201 | yes | Onay bekliyor |
| 14 | MKRUSDT | SKYUSDT | REDENOM | 24000 | 2025-09-15 03:00 | 2025-09-17 08:00 | U.Today (Binance duyurusunu aktarır: MKR spot 2025-09-15 03:00 kaldırılır, SKY/USDT 2025-09-17 08:00) https://u.today/binance-to-delist-all-pairs-of-this-popular-cryptocurrency-heres-why ; oran 1 MKR = 24000 SKY: Binance.US https://support.binance.us/en/articles/12270478-binance-us-will-support-the-maker-mkr-token-swap-and-rebranding-to-sky-sky (binance.com duyurusu doğrudan bulunamadı) | yes | Onay bekliyor |
| 15 | MCUSDT | BEAMXUSDT | REDENOM | 100 | 2023-11-07 03:00 | 2023-11-14 08:00 | Binance (1 MC = 100 BEAMX; MC spot 2023-11-07 03:00 delist; BEAMX/USDT 2023-11-14 08:00) https://www.binance.com/en/support/announcement/0b171519f1824ee288af7343ec91ce33 ; tamamlanma https://www.binance.com/en/support/announcement/c8705b752c7c47fc814a373a0f1856ee | yes | Onay bekliyor |
| 16 | TOMOUSDT | VICUSDT | RENAME | 1 | 2023-11-20 03:00 | 2023-11-24 08:00 | Binance (1 TOMO = 1 VIC; TOMO spot 2023-11-20 03:00 delist; VIC/USDT 2023-11-24 08:00) https://www.binance.com/en/support/announcement/034eee2293964e26b915b1ec5c42972a ; tamamlanma https://www.binance.com/en/support/announcement/0491a610ab2d4ab3af6d15dce961c5ae | yes | Onay bekliyor |
| 17 | NPXSUSDT | PUNDIXUSDT | REDENOM | 0.001 | 2021-04-05 04:00 | 2021-04-09 04:00 | Binance (1000 NPXS = 1 PUNDIX; NPXS/USDT 2021-04-05 04:00 delist; PUNDIX/USDT 2021-04-09 04:00) https://www.binance.com/en/support/announcement/8bdcb060635b491d912247fb00603d4d | yes | Onay bekliyor |
| 18 | LENDUSDT | AAVEUSDT | REDENOM | 0.01 | 2020-10-12 03:00 | 2020-10-15 03:00 | Binance (100 LEND = 1 AAVE; LEND işlemi 2020-10-12 03:00 durdu; AAVE/USDT 2020-10-15 03:00) https://www.binance.com/en/support/announcement/17595222999545348c8acdd5dc41c00a | yes | Onay bekliyor |
| 19 | BCHABCUSDT | BCHUSDT | RENAME | 1 | 2019-11-28 02:00 | 2019-11-28 10:00 | Binance (1 BCHABC = 1 BCH; BCHABC işlemi 2019-11-28 02:00 durdu; BCH/USDT 2019-11-28 10:00) https://www.binance.com/en/support/announcement/360037219511 | yes | Onay bekliyor |
| 20 | STRATUSDT | STRAXUSDT | RENAME | 1 | 2020-11-12 08:00 | 2020-11-18 03:00 | Binance (1 STRAT = 1 STRAX; STRAT işlemi 2020-11-12 08:00 durdu; STRAX/USDT 2020-11-18 03:00) https://www.binance.com/en/support/announcement/1937b7781c5043efa66c07141be3bdc2 (duyuru STRAT çiftlerini saymıyor; STRATUSDT'nin varlığı veriden görülecek) | yes | Onay bekliyor |
| 21 | BQXUSDT | VGXUSDT | RENAME | 1 | 2021-08-16 04:00 | 2021-08-20 04:00 | Binance (1 BQX = 1 VGX; yalnız BQX/BTC ve BQX/ETH → VGX/BTC ve VGX/ETH: USDT çifti yoktu, birleştirmede etkisiz) https://www.binance.com/en/support/announcement/25e17090279543948c8c7d27ab1668d1 | yes | Onay bekliyor |
| 22 | BCHAUSDT | XECUSDT | REDENOM | 1000000 | 2021-08-02 04:00 | 2021-08-06 04:00 | Binance (1 BCHA = 1000000 XEC; yalnız BCHA/BUSD → XEC/BUSD: USDT çifti yoktu, birleştirmede etkisiz) https://www.binance.com/en/support/announcement/55803feab78342f596c1eca9f26f3d71 | yes | Onay bekliyor |
| 23 | STRAXUSDT | STRAXUSDT | REDENOM | 10 | 2024-03-20 03:00 | 2024-03-28 08:00 | Binance (1 eski STRAX = 10 yeni STRAX; STRAX/USDT 2024-03-20 03:00 delist, 2024-03-28 08:00 yeniden açıldı) https://www.binance.com/en/support/announcement/2e6eb8e644664a6ca7b6659a226c41b0 ; tamamlanma https://www.binance.com/en/support/announcement/033618992939455aa64fd113a2c1e76f | yes | Onay bekliyor |
| 24 | BZRXUSDT | OOKIUSDT | REDENOM | 10 | 2021-12-20 04:00 | 2021-12-24 04:00 | Binance (1 BZRX = 10 OOKI; BZRX/USDT 2021-12-20 04:00 delist; OOKI/USDT 2021-12-24 04:00) https://www.binance.com/en/support/announcement/dff27dc6bcbb432c902bcbea5e24ddfa | yes | Onay bekliyor |
| 25 | MFTUSDT | HIFIUSDT | REDENOM | 0.01 | 2023-01-03 03:00 | 2023-01-12 08:00 | Binance (1 MFT = 0.01 HIFI; MFT/USDT 2023-01-03 03:00 delist; HIFI/USDT 2023-01-12 08:00) https://www.binance.com/en/support/announcement/8d28d328f7b94cf89850fe7e796881d7 | yes | Onay bekliyor |
| 26 | TVKUSDT | VANRYUSDT | RENAME | 1 | 2023-11-27 03:00 | 2023-12-01 08:00 | Binance (1 TVK = 1 VANRY; TVK/USDT 2023-11-27 03:00 delist; VANRY/USDT 2023-12-01 08:00) https://www.binance.com/en/support/announcement/1493a2222fa549ce93f7101abe0941bf | yes | Onay bekliyor |
| 27 | XZCUSDT | FIROUSDT | RENAME | 1 | 2021-01-25 02:00 | 2021-01-29 02:00 | Binance (1 XZC = 1 FIRO; XZC işlemi 2021-01-25 02:00 durdu; FIRO/USDT 2021-01-29 02:00) https://www.binance.com/en/support/announcement/4a06d6ab6abb4f08b12bb93d6fec30ec | yes | Onay bekliyor |
| 28 | QUICKUSDT | QUICKUSDT | REDENOM | 1000 | 2023-07-17 03:00 | 2023-07-21 08:00 | Binance (1 eski QUICK = 1000 yeni QUICK; QUICK/USDT 2023-07-17 03:00 delist, 2023-07-21 08:00 yeniden açıldı) https://www.binance.com/en/support/announcement/50b38ae7b25a45a7854c94ab67a1e7d0 | yes | Onay bekliyor |
| 29 | SUNUSDT | SUNUSDT | REDENOM | 1000 | 2021-06-14 04:00 | 2021-06-18 04:00 | Binance (1 SUN eski = 1000 SUN yeni; SUN/USDT 2021-06-14 04:00 delist, 2021-06-18 04:00 yeniden açıldı) https://www.binance.com/en/support/announcement/f923f2e4056843a9a9b87beb2aaa2f31 | yes | Onay bekliyor |
| 30 | COCOSUSDT | COCOSUSDT | REDENOM | 0.001 | 2021-01-19 02:00 | 2021-01-23 02:00 | Binance (eski:yeni = 1000:1; COCOS/USDT 2021-01-19 02:00 durdu, 2021-01-23 02:00 yeniden açıldı) https://www.binance.com/en/support/announcement/f555f8013eff42bc9c91eaa48b9da24b | yes | Onay bekliyor |
| 31 | COCOSUSDT | COMBOUSDT | RENAME | 1 | 2023-05-29 08:00 | 2023-06-02 08:00 | Binance (1 COCOS = 1 COMBO; COCOS spot 2023-05-29 08:00 delist; COMBO/USDT 2023-06-02 08:00) https://www.binance.com/en/support/announcement/45852dc155b641bc9e1c23bc41d8ded6 | yes | Onay bekliyor |
| 32 | BTCSTUSDT | BTCSTUSDT | REDENOM | 10 | 2021-03-15 07:00 | 2021-03-19 07:00 | Binance ('1:10 redenomination'; BTCST/USDT 2021-03-15 07:00 durdu, 2021-03-19 07:00 yeniden açıldı) https://www.binance.com/en/support/announcement/2c08ba9e1a1b409fb6a4a2cb2f5ed58b — oranın yönü (1 eski = 10 yeni) metinde açık değil, bölünme kontrolüyle doğrulanmalı | candidate | Onay bekliyor |
| 33 | DREPUSDT | DREPUSDT | REDENOM | 0.01 | 2021-03-29 04:00 | 2021-04-02 04:00 | Binance ('100:1 redenomination'; güncel takvim: DREP/USDT 2021-03-29 04:00 durdu, 2021-04-02 04:00 açıldı) https://www.binance.com/en/support/announcement/a2c87d5944cd4856af5aabd2cb8f68b4 — yön (100 eski = 1 yeni) başlıktan çıkarıldı, bölünme kontrolüyle doğrulanmalı | candidate | Onay bekliyor |

### fee_promotions.csv (26 satır)

| symbol | start | end | source |
| --- | --- | --- | --- |
| BTCAUD | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCBIDR | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCBRL | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCBUSD | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCEUR | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCGBP | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCRUB | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCTRY | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCUAH | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCUSDC | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCUSDP | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCUSDT | 2022-07-08 14:00 | 2023-03-22 00:00 | Sıfır ücretli BTC (maker+taker), 13 çift: başlangıç https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 00:00'da standart ücrete döndü https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 |
| BTCTUSD | 2022-07-08 14:00 | 2023-09-07 00:00 | 13 çiftlik kampanya https://www.binance.com/en/support/announcement/10435147c55d4a40b64fcbf43cb46329 ; 2023-03-22 sonrası yalnız BTC/TUSD sıfır kaldı https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36 ; 2023-09-07 00:00'da taker ücreti döndü, maker sıfır kaldı https://www.binance.com/en/support/announcement/9f438c4249ff45deb34cb9f727f99f83 (not: TUSD çiftleri 2022-09-29 ile 2023-03-11 arasında işlem görmedi) |
| ETHBUSD | 2022-08-26 00:00 | 2022-09-26 00:00 | ETH/BUSD sıfır ücret (maker+taker) https://www.binance.com/en/support/announcement/5d8f9c0a68e24b82bff743a342dfa9b9 (uzatma duyurusu bulunamadı; 2023-03-15 duyurusu ETH/BUSD'nin 2023-03-22'de standart ücrete döndüğünü yazıyor https://www.binance.com/en/support/announcement/be13a645cca643d28eab5b9b34f2dc36, arada sıfır maker olabilir) |
| TUSDUSDT | 2023-03-11 14:00 |  | Stablecoin çiftleri sıfır ücret (maker+taker), until further notice https://www.binance.com/en/support/announcement/dd331bed50bb44f485e47aed132bfc02 ; 2023-06-30'da tüm USD stablecoin çiftlerine genişledi https://www.binance.com/en/support/announcement/a376bf14673044e0a1fae8fe60cb0700 (bitiş bulunamadı) |
| USDCUSDT | 2023-03-11 14:00 |  | Stablecoin çiftleri sıfır ücret (maker+taker), until further notice https://www.binance.com/en/support/announcement/dd331bed50bb44f485e47aed132bfc02 ; 2023-06-30'da tüm USD stablecoin çiftlerine genişledi https://www.binance.com/en/support/announcement/a376bf14673044e0a1fae8fe60cb0700 (bitiş bulunamadı) |
| USDPUSDT | 2023-03-11 14:00 |  | Stablecoin çiftleri sıfır ücret (maker+taker), until further notice https://www.binance.com/en/support/announcement/dd331bed50bb44f485e47aed132bfc02 ; 2023-06-30'da tüm USD stablecoin çiftlerine genişledi https://www.binance.com/en/support/announcement/a376bf14673044e0a1fae8fe60cb0700 (bitiş bulunamadı) |
| FDUSDUSDT | 2023-07-26 08:00 |  | FDUSD listeleme: FDUSD/USDT ve FDUSD/BUSD sıfır maker+taker, until further notice https://www.binance.com/en/support/announcement/065a0d561cc147ffaa74554360b9a042 (bitiş bulunamadı) |
| FDUSDBUSD | 2023-07-26 08:00 |  | FDUSD listeleme: FDUSD/USDT ve FDUSD/BUSD sıfır maker+taker, until further notice https://www.binance.com/en/support/announcement/065a0d561cc147ffaa74554360b9a042 (bitiş bulunamadı) |
| BTCFDUSD | 2023-08-04 08:00 | 2026-01-29 00:00 | BTC/FDUSD sıfır maker+taker https://www.binance.com/en/support/announcement/0e4155610e6f4e8bbaaa332545dc43a2 ; 2024-04-25 06:00'da normal ve VIP1 kullanıcılar için taker ücreti döndü; VIP2-9 ve SLP için sıfır ücret 2026-01-29 00:00'a kadar sürdü https://www.binance.com/en/support/announcement/3d8514bbc817423eba52fb23483bcbed — bitiş olarak kötümser 2026-01-29 seçildi |
| BNBFDUSD | 2023-12-08 00:00 | 2026-01-29 00:00 | Altı FDUSD çifti sıfır maker+taker https://www.binance.com/en/support/announcement/d0976bedd0b942efaa9f4f1624abd95d ; 2024-04-25 06:00'da normal ve VIP1 kullanıcılar için taker ücreti döndü; VIP2-9 ve SLP için sıfır ücret 2026-01-29 00:00'a kadar sürdü https://www.binance.com/en/support/announcement/3d8514bbc817423eba52fb23483bcbed — bitiş olarak kötümser 2026-01-29 seçildi |
| DOGEFDUSD | 2023-12-08 00:00 | 2026-01-29 00:00 | Altı FDUSD çifti sıfır maker+taker https://www.binance.com/en/support/announcement/d0976bedd0b942efaa9f4f1624abd95d ; 2024-04-25 06:00'da normal ve VIP1 kullanıcılar için taker ücreti döndü; VIP2-9 ve SLP için sıfır ücret 2026-01-29 00:00'a kadar sürdü https://www.binance.com/en/support/announcement/3d8514bbc817423eba52fb23483bcbed — bitiş olarak kötümser 2026-01-29 seçildi |
| ETHFDUSD | 2023-12-08 00:00 | 2026-01-29 00:00 | Altı FDUSD çifti sıfır maker+taker https://www.binance.com/en/support/announcement/d0976bedd0b942efaa9f4f1624abd95d ; 2024-04-25 06:00'da normal ve VIP1 kullanıcılar için taker ücreti döndü; VIP2-9 ve SLP için sıfır ücret 2026-01-29 00:00'a kadar sürdü https://www.binance.com/en/support/announcement/3d8514bbc817423eba52fb23483bcbed — bitiş olarak kötümser 2026-01-29 seçildi |
| LINKFDUSD | 2023-12-08 00:00 | 2026-01-29 00:00 | Altı FDUSD çifti sıfır maker+taker https://www.binance.com/en/support/announcement/d0976bedd0b942efaa9f4f1624abd95d ; 2024-04-25 06:00'da normal ve VIP1 kullanıcılar için taker ücreti döndü; VIP2-9 ve SLP için sıfır ücret 2026-01-29 00:00'a kadar sürdü https://www.binance.com/en/support/announcement/3d8514bbc817423eba52fb23483bcbed — bitiş olarak kötümser 2026-01-29 seçildi |
| SOLFDUSD | 2023-12-08 00:00 | 2026-01-29 00:00 | Altı FDUSD çifti sıfır maker+taker https://www.binance.com/en/support/announcement/d0976bedd0b942efaa9f4f1624abd95d ; 2024-04-25 06:00'da normal ve VIP1 kullanıcılar için taker ücreti döndü; VIP2-9 ve SLP için sıfır ücret 2026-01-29 00:00'a kadar sürdü https://www.binance.com/en/support/announcement/3d8514bbc817423eba52fb23483bcbed — bitiş olarak kötümser 2026-01-29 seçildi |
| XRPFDUSD | 2023-12-08 00:00 | 2026-01-29 00:00 | Altı FDUSD çifti sıfır maker+taker https://www.binance.com/en/support/announcement/d0976bedd0b942efaa9f4f1624abd95d ; 2024-04-25 06:00'da normal ve VIP1 kullanıcılar için taker ücreti döndü; VIP2-9 ve SLP için sıfır ücret 2026-01-29 00:00'a kadar sürdü https://www.binance.com/en/support/announcement/3d8514bbc817423eba52fb23483bcbed — bitiş olarak kötümser 2026-01-29 seçildi |

### delist_announcements.csv (4 satır)

| symbol | announced_utc | delist_utc | kind | source |
| --- | --- | --- | --- | --- |
| LUNAUSDT | 2022-05-13 00:40 | 2022-05-13 00:40 | delist | Decrypt: kaldırma tweet ile kaldırma anında duyuruldu https://decrypt.co/100290/binance-halts-trading-terra-delists-luna-ust (duyuru zamanı = kaldırma zamanı varsayıldı) |
| FTTUSDT | 2022-11-14 | 2022-11-15 04:30 | delist | FTT/BTC, FTT/BNB, FTT/ETH, FTT/USDT kaldırıldı (FTT/BUSD kaldı): Decrypt 2022-11-14 https://decrypt.co/114361/binance-remove-trading-pairs-ftx-token-except-busd ; saat: https://fxnewsgroup.com/forex-news/cryptocurrency/binance-to-remove-several-ftt-pairs-from-list-of-trading-instruments/ (duyuru saati bilinmiyor, yalnız tarih) ; not: arşivde FTTUSDT serisi 2023-09-22'de yeniden başlıyor (trend.data.clean belgesi), delist kuralı ilk kapanışa uygulanır |
| OCEANUSDT | 2024-06-14 10:30 | 2024-07-01 03:00 | delist | FET birleşmesi (MERGE_INTO_EXISTING) https://www.binance.com/en/support/announcement/e485541c370240adba3929fded74f269 |
| AGIXUSDT | 2024-06-14 10:30 | 2024-07-01 03:00 | delist | FET birleşmesi (MERGE_INTO_EXISTING) https://www.binance.com/en/support/announcement/e485541c370240adba3929fded74f269 |

### Veriden bulunan adaylar (`meta/symbol_map_candidates.csv`)

112 aday (yöntem: pair_round_ratio 102, split_check 8, pair_name_hint 1, pair_round_ratio+pair_name_hint 1).

| old_symbol | new_symbol | type | ratio | old_last_trade_utc | new_first_trade_utc | method | detail |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POLYUSDT | POLYXUSDT | REDENOM | 1.12474 | 2022-10-10 | 2022-10-17 | pair_name_hint | gap_days=7;price_old=0.2696;price_new=0.2397;log10_ratio=0.0511;within_split_tol=False |
| 1INCHDOWNUSDT | BICOUSDT | REDENOM | 0.001 | 2021-12-02 | 2021-12-09 | pair_round_ratio | gap_days=7;price_old=0.006148;price_new=5.631;log10_ratio=-2.9619;within_split_tol=False |
| AAVEDOWNUSDT | ENSUSDT | REDENOM | 0.0001 | 2021-11-11 | 2021-11-10 | pair_round_ratio | gap_days=-1;price_old=0.004673;price_new=43.66;log10_ratio=-3.9705;within_split_tol=False |
| AAVEDOWNUSDT | POWRUSDT | REDENOM | 0.01 | 2021-11-11 | 2021-11-17 | pair_round_ratio | gap_days=6;price_old=0.004673;price_new=0.5233;log10_ratio=-2.0492;within_split_tol=False |
| AEURUSDT | FLNCBUSDT | REDENOM | 0.1 | 2026-07-31 | 2026-07-29 | pair_round_ratio | gap_days=-2;price_old=1.1443;price_new=12.62;log10_ratio=-1.0425;within_split_tol=False |
| AEURUSDT | GSBUSDT | REDENOM | 0.001 | 2026-07-31 | 2026-07-29 | pair_round_ratio | gap_days=-2;price_old=1.1443;price_new=1033.34;log10_ratio=-2.9557;within_split_tol=False |
| AIONUSDT | LQTYUSDT | REDENOM | 0.01 | 2023-02-27 | 2023-02-28 | pair_round_ratio | gap_days=1;price_old=0.00943;price_new=1;log10_ratio=-2.0255;within_split_tol=False |
| AIONUSDT | VIBUSDT | REDENOM | 0.1 | 2023-02-27 | 2023-02-24 | pair_round_ratio | gap_days=-3;price_old=0.00943;price_new=0.1031;log10_ratio=-1.0387;within_split_tol=False |
| ALCXUSDT | CBRSBUSDT | REDENOM | 0.01 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=1.91;price_new=192.01;log10_ratio=-2.0023;within_split_tol=True |
| ALCXUSDT | GLWBUSDT | REDENOM | 0.01 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=1.91;price_new=194.8;log10_ratio=-2.0086;within_split_tol=True |
| ALCXUSDT | NBISBUSDT | REDENOM | 0.01 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=1.91;price_new=213.02;log10_ratio=-2.0474;within_split_tol=False |
| ALCXUSDT | QCOMBUSDT | REDENOM | 0.01 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=1.91;price_new=186.48;log10_ratio=-1.9896;within_split_tol=True |
| ALCXUSDT | SOXLBUSDT | REDENOM | 0.01 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=1.91;price_new=175.1;log10_ratio=-1.9623;within_split_tol=False |
| ANYUSDT | MULTIUSDT | RENAME | 1.0 | 2022-03-30 | 2022-04-06 | pair_round_ratio | gap_days=7;price_old=12.3;price_new=13.15;log10_ratio=-0.0290;within_split_tol=False |
| ARDRUSDT | CBRSBUSDT | REDENOM | 0.0001 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=0.02096;price_new=192.01;log10_ratio=-3.9619;within_split_tol=False |
| ARDRUSDT | GLWBUSDT | REDENOM | 0.0001 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=0.02096;price_new=194.8;log10_ratio=-3.9682;within_split_tol=False |
| ARDRUSDT | IBMBUSDT | REDENOM | 0.0001 | 2026-07-10 | 2026-07-15 | pair_round_ratio | gap_days=5;price_old=0.02096;price_new=217.07;log10_ratio=-4.0152;within_split_tol=True |
| ARDRUSDT | MRVLBUSDT | REDENOM | 0.0001 | 2026-07-10 | 2026-07-15 | pair_round_ratio | gap_days=5;price_old=0.02096;price_new=222.44;log10_ratio=-4.0258;within_split_tol=False |
| ARDRUSDT | NBISBUSDT | REDENOM | 0.0001 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=0.02096;price_new=213.02;log10_ratio=-4.0070;within_split_tol=True |
| ASTUSDT | PARTIUSDT | RENAME | 1.0 | 2025-03-28 | 2025-03-25 | pair_round_ratio | gap_days=-3;price_old=0.0261;price_new=0.025;log10_ratio=0.0187;within_split_tol=True |
| BALUSDT | HYPERUSDT | REDENOM | 10.0 | 2025-04-16 | 2025-04-22 | pair_round_ratio | gap_days=6;price_old=0.967;price_new=0.09;log10_ratio=1.0312;within_split_tol=False |
| BALUSDT | KERNELUSDT | REDENOM | 10.0 | 2025-04-16 | 2025-04-14 | pair_round_ratio | gap_days=-2;price_old=0.967;price_new=0.1;log10_ratio=0.9854;within_split_tol=True |
| BCHDOWNUSDT | GLMRUSDT | RENAME | 1.0 | 2022-01-04 | 2022-01-11 | pair_round_ratio | gap_days=7;price_old=0.2247;price_new=0.25;log10_ratio=-0.0463;within_split_tol=False |
| BCHUPUSDT | ACHUSDT | RENAME | 1.0 | 2022-01-04 | 2022-01-10 | pair_round_ratio | gap_days=6;price_old=0.0724;price_new=0.06464;log10_ratio=0.0492;within_split_tol=False |
| BKRWUSDT | SANDUSDT | REDENOM | 0.1 | 2020-08-07 | 2020-08-14 | pair_round_ratio | gap_days=7;price_old=0.0008453;price_new=0.008333;log10_ratio=-0.9938;within_split_tol=True |
| BNBDOWNUSDT | PDAUSDT | REDENOM | 0.01 | 2024-02-28 | 2024-03-01 | pair_round_ratio | gap_days=2;price_old=0.002151;price_new=0.2347;log10_ratio=-2.0379;within_split_tol=False |
| BTCDOWNUSDT | AXLUSDT | REDENOM | 0.001 | 2024-02-28 | 2024-03-01 | pair_round_ratio | gap_days=2;price_old=0.001185;price_new=1.2071;log10_ratio=-3.0080;within_split_tol=True |
| BTCDOWNUSDT | WIFUSDT | REDENOM | 0.001 | 2024-02-28 | 2024-03-05 | pair_round_ratio | gap_days=6;price_old=0.001185;price_new=1.1892;log10_ratio=-3.0015;within_split_tol=True |
| CHESSUSDT | ESPUSDT | REDENOM | 0.1 | 2026-02-13 | 2026-02-12 | pair_round_ratio | gap_days=-1;price_old=0.00281;price_new=0.0278;log10_ratio=-0.9953;within_split_tol=True |
| COMBOUSDT | GUNUSDT | RENAME | 1.0 | 2025-03-28 | 2025-03-31 | pair_round_ratio | gap_days=3;price_old=0.0276;price_new=0.03;log10_ratio=-0.0362;within_split_tol=False |
| COMBOUSDT | PARTIUSDT | RENAME | 1.0 | 2025-03-28 | 2025-03-25 | pair_round_ratio | gap_days=-3;price_old=0.0276;price_new=0.025;log10_ratio=0.0430;within_split_tol=False |
| CREAMUSDT | INITUSDT | REDENOM | 10.0 | 2025-04-16 | 2025-04-24 | pair_round_ratio | gap_days=8;price_old=2.1;price_new=0.2;log10_ratio=1.0212;within_split_tol=False |
| CREAMUSDT | WCTUSDT | REDENOM | 10.0 | 2025-04-16 | 2025-04-15 | pair_round_ratio | gap_days=-1;price_old=2.1;price_new=0.2;log10_ratio=1.0212;within_split_tol=False |
| DAIUSDT | IRISUSDT | REDENOM | 10.0 | 2020-08-12 | 2020-08-11 | pair_round_ratio | gap_days=-1;price_old=1.0189;price_new=0.11269;log10_ratio=0.9562;within_split_tol=False |
| DAIUSDT | SRMUSDT | REDENOM | 10.0 | 2020-08-12 | 2020-08-11 | pair_round_ratio | gap_days=-1;price_old=1.0189;price_new=0.11;log10_ratio=0.9667;within_split_tol=False |
| DARUSDT | CGPTUSDT | RENAME | 1.0 | 2025-01-06 | 2025-01-10 | pair_round_ratio | gap_days=4;price_old=0.21707;price_new=0.2129;log10_ratio=0.0084;within_split_tol=True |
| DOCKUSDT | BANANAUSDT | REDENOM | 0.0001 | 2024-07-22 | 2024-07-20 | pair_round_ratio | gap_days=-2;price_old=0.0039;price_new=40;log10_ratio=-4.0110;within_split_tol=True |
| DOCKUSDT | GUSDT | REDENOM | 0.1 | 2024-07-22 | 2024-07-19 | pair_round_ratio | gap_days=-3;price_old=0.0039;price_new=0.04237;log10_ratio=-1.0360;within_split_tol=False |
| DOTUPUSDT | HOOKUSDT | RENAME | 1.0 | 2022-11-29 | 2022-12-01 | pair_round_ratio | gap_days=2;price_old=0.096;price_new=0.1;log10_ratio=-0.0177;within_split_tol=True |
| DUSDT | REUSDT | REDENOM | 0.1 | 2026-06-19 | 2026-06-18 | pair_round_ratio | gap_days=-1;price_old=0.00461;price_new=0.05;log10_ratio=-1.0353;within_split_tol=False |
| EOSBULLUSDT | DATAUSDT | REDENOM | 100.0 | 2020-03-31 | 2020-04-07 | pair_round_ratio | gap_days=7;price_old=3.85;price_new=0.04088;log10_ratio=1.9739;within_split_tol=False |
| EOSBULLUSDT | XZCUSDT | RENAME | 1.0 | 2020-03-31 | 2020-04-07 | pair_round_ratio | gap_days=7;price_old=3.85;price_new=3.554;log10_ratio=0.0347;within_split_tol=False |
| EOSDOWNUSDT | CVXUSDT | REDENOM | 1e-05 | 2021-12-23 | 2021-12-23 | pair_round_ratio | gap_days=0;price_old=0.0003665;price_new=38.51;log10_ratio=-5.0215;within_split_tol=False |
| EOSUPUSDT | JOEUSDT | REDENOM | 0.1 | 2021-12-23 | 2021-12-28 | pair_round_ratio | gap_days=5;price_old=0.2113;price_new=2.21;log10_ratio=-1.0195;within_split_tol=True |
| EOSUPUSDT | OOKIUSDT | REDENOM | 10.0 | 2021-12-23 | 2021-12-24 | pair_round_ratio | gap_days=1;price_old=0.2113;price_new=0.02156;log10_ratio=0.9913;within_split_tol=True |
| EOSUPUSDT | SPELLUSDT | REDENOM | 10.0 | 2021-12-23 | 2021-12-24 | pair_round_ratio | gap_days=1;price_old=0.2113;price_new=0.02357;log10_ratio=0.9525;within_split_tol=False |
| ERNUSDT | EPICUSDT | RENAME | 1.0 | 2025-03-10 | 2025-03-13 | pair_round_ratio | gap_days=3;price_old=2.183;price_new=2.183;log10_ratio=0.0000;within_split_tol=True |
| ETHDOWNUSDT | PORTALUSDT | RENAME | 1.0 | 2024-02-28 | 2024-02-29 | pair_round_ratio | gap_days=1;price_old=0.0457;price_new=0.05;log10_ratio=-0.0391;within_split_tol=False |
| ETHUPUSDT | AXLUSDT | REDENOM | 10.0 | 2024-02-28 | 2024-03-01 | pair_round_ratio | gap_days=2;price_old=11.651;price_new=1.2071;log10_ratio=0.9846;within_split_tol=True |
| ETHUPUSDT | WIFUSDT | REDENOM | 10.0 | 2024-02-28 | 2024-03-05 | pair_round_ratio | gap_days=6;price_old=11.651;price_new=1.1892;log10_ratio=0.9911;within_split_tol=True |
| FRONTUSDT | SLFUSDT | RENAME | 1.0 | 2024-08-27 | 2024-08-30 | pair_round_ratio | gap_days=3;price_old=0.88;price_new=0.88;log10_ratio=0.0000;within_split_tol=True |
| FXSUSDT | FRAXUSDT | RENAME | 1.0 | 2026-01-13 | 2026-01-15 | pair_round_ratio | gap_days=2;price_old=0.812;price_new=0.812;log10_ratio=0.0000;within_split_tol=True |
| GFTUSDT | MOVEUSDT | REDENOM | 0.1 | 2024-12-03 | 2024-12-09 | pair_round_ratio | gap_days=6;price_old=0.00196;price_new=0.02;log10_ratio=-1.0088;within_split_tol=True |
| HARDUSDT | HYPERUSDT | REDENOM | 0.1 | 2025-04-16 | 2025-04-22 | pair_round_ratio | gap_days=6;price_old=0.0095;price_new=0.09;log10_ratio=-0.9765;within_split_tol=False |
| HARDUSDT | KERNELUSDT | REDENOM | 0.1 | 2025-04-16 | 2025-04-14 | pair_round_ratio | gap_days=-2;price_old=0.0095;price_new=0.1;log10_ratio=-1.0223;within_split_tol=False |
| ICXUSDT | STXBUSDT | REDENOM | 1e-05 | 2026-09-03 | 2026-09-02 | pair_round_ratio | gap_days=-1;price_old=0.00841;price_new=816.64;log10_ratio=-4.9872;within_split_tol=True |
| KLAYUSDT | KAIAUSDT | RENAME | 1.0 | 2024-10-30 | 2024-10-31 | pair_round_ratio | gap_days=1;price_old=0.1255;price_new=0.1255;log10_ratio=0.0000;within_split_tol=True |
| LITUSDT | HEIUSDT | RENAME | 1.0 | 2025-02-10 | 2025-02-13 | pair_round_ratio | gap_days=3;price_old=0.743;price_new=0.743;log10_ratio=0.0000;within_split_tol=True |
| LTCDOWNUSDT | ACAUSDT | RENAME | 1.0 | 2022-01-27 | 2022-01-25 | pair_round_ratio | gap_days=-2;price_old=2.2279;price_new=2;log10_ratio=0.0469;within_split_tol=False |
| LTCDOWNUSDT | XNOUSDT | RENAME | 1.0 | 2022-01-27 | 2022-01-28 | pair_round_ratio | gap_days=1;price_old=2.2279;price_new=2.224;log10_ratio=0.0008;within_split_tol=True |
| LTOUSDT | LAUSDT | REDENOM | 0.01 | 2025-07-04 | 2025-07-09 | pair_round_ratio | gap_days=5;price_old=0.0038;price_new=0.4;log10_ratio=-2.0223;within_split_tol=False |
| MBOXUSDT | EWYBUSDT | REDENOM | 1e-05 | 2026-06-19 | 2026-06-23 | pair_round_ratio | gap_days=4;price_old=0.0021;price_new=196.16;log10_ratio=-4.9704;within_split_tol=False |
| NANOUSDT | ACAUSDT | RENAME | 1.0 | 2022-01-24 | 2022-01-25 | pair_round_ratio | gap_days=1;price_old=2.224;price_new=2;log10_ratio=0.0461;within_split_tol=False |
| NANOUSDT | XNOUSDT | RENAME | 1.0 | 2022-01-24 | 2022-01-28 | pair_round_ratio | gap_days=4;price_old=2.224;price_new=2.224;log10_ratio=0.0000;within_split_tol=True |
| NFPUSDT | CBRSBUSDT | REDENOM | 1e-05 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=0.00181;price_new=192.01;log10_ratio=-5.0256;within_split_tol=False |
| NFPUSDT | COINBUSDT | REDENOM | 1e-05 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=0.00181;price_new=168.87;log10_ratio=-4.9699;within_split_tol=False |
| NFPUSDT | GLWBUSDT | REDENOM | 1e-05 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=0.00181;price_new=194.8;log10_ratio=-5.0319;within_split_tol=False |
| NFPUSDT | QCOMBUSDT | REDENOM | 1e-05 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=0.00181;price_new=186.48;log10_ratio=-5.0130;within_split_tol=True |
| NFPUSDT | SOXLBUSDT | REDENOM | 1e-05 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=0.00181;price_new=175.1;log10_ratio=-4.9856;within_split_tol=True |
| OAXUSDT | 1000CATUSDT | RENAME | 1.0 | 2024-12-10 | 2024-12-17 | pair_round_ratio | gap_days=7;price_old=0.0358;price_new=0.03918;log10_ratio=-0.0392;within_split_tol=False |
| OAXUSDT | PENGUUSDT | REDENOM | 10.0 | 2024-12-10 | 2024-12-17 | pair_round_ratio | gap_days=7;price_old=0.0358;price_new=0.003375;log10_ratio=1.0256;within_split_tol=False |
| ORNUSDT | LUMIAUSDT | RENAME | 1.0 | 2024-10-15 | 2024-10-18 | pair_round_ratio | gap_days=3;price_old=1.053;price_new=1.053;log10_ratio=0.0000;within_split_tol=True |
| PAXUSDT | VIDTUSDT | RENAME | 1.0 | 2021-09-06 | 2021-09-09 | pair_round_ratio | gap_days=3;price_old=0.9996;price_new=1.0711;log10_ratio=-0.0300;within_split_tol=False |
| PDAUSDT | STOUSDT | REDENOM | 0.1 | 2025-05-02 | 2025-05-02 | pair_round_ratio | gap_days=0;price_old=0.00977;price_new=0.0956;log10_ratio=-0.9906;within_split_tol=True |
| PIVXUSDT | DJTBUSDT | REDENOM | 0.001 | 2026-08-17 | 2026-08-26 | pair_round_ratio | gap_days=9;price_old=0.0097;price_new=9.4;log10_ratio=-2.9864;within_split_tol=True |
| PLAUSDT | PDAUSDT | RENAME | 1.0 | 2024-02-26 | 2024-03-01 | pair_round_ratio | gap_days=4;price_old=0.2347;price_new=0.2347;log10_ratio=0.0000;within_split_tol=True |
| POLYUSDT | NEBLUSDT | REDENOM | 0.1 | 2022-10-10 | 2022-10-14 | pair_round_ratio | gap_days=4;price_old=0.2696;price_new=2.89;log10_ratio=-1.0302;within_split_tol=False |
| PONDUSDT | RKLBBUSDT | REDENOM | 1e-05 | 2026-07-10 | 2026-07-15 | pair_round_ratio | gap_days=5;price_old=0.00081;price_new=78.81;log10_ratio=-4.9881;within_split_tol=True |
| PONDUSDT | SPYBUSDT | REDENOM | 1e-06 | 2026-07-10 | 2026-07-07 | pair_round_ratio | gap_days=-3;price_old=0.00081;price_new=751.28;log10_ratio=-5.9673;within_split_tol=False |
| RENUSDT | 1000CATUSDT | RENAME | 1.0 | 2024-12-10 | 2024-12-17 | pair_round_ratio | gap_days=7;price_old=0.04274;price_new=0.03918;log10_ratio=0.0378;within_split_tol=False |
| STORJUSDT | HIMSBUSDT | REDENOM | 0.001 | 2026-09-03 | 2026-09-09 | pair_round_ratio | gap_days=6;price_old=0.0298;price_new=28.17;log10_ratio=-2.9756;within_split_tol=False |
| STORMUSDT | STMXUSDT | RENAME | 1.0 | 2020-06-08 | 2020-06-11 | pair_round_ratio | gap_days=3;price_old=0.003397;price_new=0.003332;log10_ratio=0.0084;within_split_tol=True |
| STPTUSDT | AUSDT | REDENOM | 0.1 | 2025-05-19 | 2025-05-28 | pair_round_ratio | gap_days=9;price_old=0.07042;price_new=0.7799;log10_ratio=-1.0443;within_split_tol=False |
| STPTUSDT | AWEUSDT | RENAME | 1.0 | 2025-05-19 | 2025-05-21 | pair_round_ratio | gap_days=2;price_old=0.07042;price_new=0.07042;log10_ratio=0.0000;within_split_tol=True |
| SUSHIDOWNUSDT | CVXUSDT | RENAME | 1.0 | 2021-12-14 | 2021-12-23 | pair_round_ratio | gap_days=9;price_old=37.37;price_new=38.51;log10_ratio=-0.0131;within_split_tol=True |
| TONUSDT | COINBUSDT | REDENOM | 0.01 | 2026-06-30 | 2026-07-07 | pair_round_ratio | gap_days=7;price_old=1.6;price_new=168.87;log10_ratio=-2.0234;within_split_tol=False |
| TONUSDT | GRAMUSDT | RENAME | 1.0 | 2026-06-30 | 2026-07-02 | pair_round_ratio | gap_days=2;price_old=1.6;price_new=1.6;log10_ratio=0.0000;within_split_tol=True |
| TONUSDT | SOXLBUSDT | REDENOM | 0.01 | 2026-06-30 | 2026-07-07 | pair_round_ratio | gap_days=7;price_old=1.6;price_new=175.1;log10_ratio=-2.0392;within_split_tol=False |
| UFTUSDT | HYPERUSDT | REDENOM | 0.1 | 2025-04-16 | 2025-04-22 | pair_round_ratio | gap_days=6;price_old=0.0089;price_new=0.09;log10_ratio=-1.0049;within_split_tol=True |
| UNIDOWNUSDT | JOEUSDT | RENAME | 1.0 | 2021-12-23 | 2021-12-28 | pair_round_ratio | gap_days=5;price_old=2.172;price_new=2.21;log10_ratio=-0.0075;within_split_tol=True |
| UNIDOWNUSDT | OOKIUSDT | REDENOM | 100.0 | 2021-12-23 | 2021-12-24 | pair_round_ratio | gap_days=1;price_old=2.172;price_new=0.02156;log10_ratio=2.0032;within_split_tol=True |
| UNIDOWNUSDT | SPELLUSDT | REDENOM | 100.0 | 2021-12-23 | 2021-12-24 | pair_round_ratio | gap_days=1;price_old=2.172;price_new=0.02357;log10_ratio=1.9645;within_split_tol=False |
| UNIUPUSDT | USTUSDT | RENAME | 1.0 | 2021-12-23 | 2021-12-24 | pair_round_ratio | gap_days=1;price_old=1.055;price_new=1;log10_ratio=0.0233;within_split_tol=False |
| USDPUSDT | HYPEUSDT | REDENOM | 0.01 | 2026-09-24 | 2026-09-24 | pair_round_ratio | gap_days=0;price_old=0.9997;price_new=92;log10_ratio=-1.9639;within_split_tol=False |
| USDSBUSDT | XTZUSDT | RENAME | 1.0 | 2019-09-27 | 2019-09-24 | pair_round_ratio | gap_days=-3;price_old=0.9997;price_new=1.015;log10_ratio=-0.0066;within_split_tol=True |
| WANUSDT | MEGAUSDT | RENAME | 1.0 | 2026-04-23 | 2026-04-30 | pair_round_ratio | gap_days=7;price_old=0.0543;price_new=0.053;log10_ratio=0.0105;within_split_tol=True |
| WAVESUSDT | ZROUSDT | RENAME | 1.0 | 2024-06-17 | 2024-06-20 | pair_round_ratio | gap_days=3;price_old=1.076;price_new=1;log10_ratio=0.0318;within_split_tol=False |
| WTCUSDT | AEURUSDT | REDENOM | 0.01 | 2023-12-07 | 2023-12-04 | pair_round_ratio | gap_days=-3;price_old=0.0103;price_new=1.0875;log10_ratio=-2.0236;within_split_tol=False |
| XLMDOWNUSDT | CVXUSDT | REDENOM | 0.1 | 2021-12-14 | 2021-12-23 | pair_round_ratio | gap_days=9;price_old=4.304;price_new=38.51;log10_ratio=-0.9517;within_split_tol=False |
| XLMUPUSDT | HIGHUSDT | REDENOM | 0.001 | 2021-12-14 | 2021-12-17 | pair_round_ratio | gap_days=3;price_old=0.0243;price_new=24.4;log10_ratio=-3.0018;within_split_tol=True |
| XLMUPUSDT | SPELLUSDT | RENAME | 1.0 | 2021-12-14 | 2021-12-24 | pair_round_ratio | gap_days=10;price_old=0.0243;price_new=0.02357;log10_ratio=0.0132;within_split_tol=True |
| XMRUSDT | AXLUSDT | REDENOM | 100.0 | 2024-02-20 | 2024-03-01 | pair_round_ratio | gap_days=10;price_old=118.7;price_new=1.2071;log10_ratio=1.9927;within_split_tol=True |
| YFIUPUSDT | FLUXUSDT | REDENOM | 0.1 | 2021-12-02 | 2021-12-10 | pair_round_ratio | gap_days=8;price_old=0.1169;price_new=1.22;log10_ratio=-1.0185;within_split_tol=True |
| DARUSDT | DUSDT | RENAME | 1.0 | 2025-01-06 | 2025-01-09 | pair_round_ratio+pair_name_hint | gap_days=3;price_old=0.21707;price_new=0.21707;log10_ratio=0.0000;within_split_tol=True |
| BNXBUSD | BNXBUSD | REDENOM | 100.0 | 2023-02-16 | 2023-02-22 | split_check | prev_close=175.8;next_open=1.758;log10_ratio=2;k=2;suggested_ratio=100;gap_days=5 |
| BTCSTBUSD | BTCSTBUSD | REDENOM | 10.0 | 2021-03-15 | 2021-03-19 | split_check | prev_close=373.612;next_open=37.361;log10_ratio=1.000002325;k=1;suggested_ratio=10;gap_days=3 |
| ETHDOWNUSDT | ETHDOWNUSDT | REDENOM | 1e-05 | 2021-07-08 | 2021-07-09 | split_check | prev_close=5.9e-05;next_open=6;log10_ratio=-5.007299239;k=-5;suggested_ratio=1e-05;gap_days=0 |
| FTMUSDC | FTMUSDC | REDENOM | 0.01 | 2020-01-07 | 2024-03-27 | split_check | prev_close=0.01107;next_open=1.0648;log10_ratio=-1.983120422;k=-2;suggested_ratio=0.01;gap_days=1540 |
| PHBTUSD | PHBTUSD | REDENOM | 0.01 | 2021-11-01 | 2021-11-05 | split_check | prev_close=0.013818;next_open=1.4;log10_ratio=-2.005682847;k=-2;suggested_ratio=0.01;gap_days=3 |
| SUSHIDOWNUSDT | SUSHIDOWNUSDT | REDENOM | 1e-05 | 2021-09-23 | 2021-09-24 | split_check | prev_close=0.0005288;next_open=54.865;log10_ratio=-5.016003937;k=-5;suggested_ratio=1e-05;gap_days=0 |
| TRXDOWNUSDT | TRXDOWNUSDT | REDENOM | 1e-05 | 2021-09-13 | 2021-09-14 | split_check | prev_close=0.00012;next_open=12.154;log10_ratio=-5.005537986;k=-5;suggested_ratio=1e-05;gap_days=0 |
| XLMUSDC | XLMUSDC | REDENOM | 0.1 | 2020-01-07 | 2024-12-04 | split_check | prev_close=0.0497;next_open=0.5066;log10_ratio=-1.008308797;k=-1;suggested_ratio=0.1;gap_days=1792 |

### Birleştirilmiş varlıklar (`meta/asset_segments.csv`)

756 varlık; birden fazla parçalı: 22.

| asset_id | source_symbol | start | end | ratio |
| --- | --- | --- | --- | --- |
| AAVEUSDT | LENDUSDT | 2020-05-15 00:00:00 | 2020-10-12 00:00:00 | 0.01 |
| AAVEUSDT | AAVEUSDT | 2020-10-15 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| AUSDT | EOSUSDT | 2018-05-28 00:00:00 | 2025-05-26 00:00:00 | 1.0 |
| AUSDT | AUSDT | 2025-05-28 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| BCHUSDT | BCHABCUSDT | 2018-11-16 00:00:00 | 2019-11-27 00:00:00 | 1.0 |
| BCHUSDT | BCHUSDT | 2019-11-28 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| BEAMXUSDT | MCUSDT | 2021-12-02 00:00:00 | 2023-11-07 00:00:00 | 100.0 |
| BEAMXUSDT | BEAMXUSDT | 2023-11-14 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| BTTCUSDT | BTTUSDT | 2019-01-31 00:00:00 | 2022-01-17 00:00:00 | 1000.0 |
| BTTCUSDT | BTTCUSDT | 2022-01-25 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| COMBOUSDT | COCOSUSDT | 2019-08-21 00:00:00 | 2021-01-19 00:00:00 | 0.001 |
| COMBOUSDT | COCOSUSDT | 2021-01-23 00:00:00 | 2023-05-29 00:00:00 | 1.0 |
| COMBOUSDT | COMBOUSDT | 2023-06-02 00:00:00 | 2025-03-28 00:00:00 | 1.0 |
| EGLDUSDT | ERDUSDT | 2019-07-04 00:00:00 | 2020-08-31 00:00:00 | 0.001 |
| EGLDUSDT | EGLDUSDT | 2020-09-03 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| FIROUSDT | XZCUSDT | 2020-04-07 00:00:00 | 2021-01-25 00:00:00 | 1.0 |
| FIROUSDT | FIROUSDT | 2021-01-29 00:00:00 | 2025-04-16 00:00:00 | 1.0 |
| FORMUSDT | BNXUSDT | 2021-11-04 00:00:00 | 2023-02-16 00:00:00 | 100.0 |
| FORMUSDT | BNXUSDT | 2023-02-22 00:00:00 | 2025-03-18 00:00:00 | 1.0 |
| FORMUSDT | FORMUSDT | 2025-03-19 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| GUSDT | GALUSDT | 2022-05-05 00:00:00 | 2024-07-15 00:00:00 | 60.0 |
| GUSDT | GUSDT | 2024-07-19 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| HIFIUSDT | MFTUSDT | 2019-08-27 00:00:00 | 2023-01-03 00:00:00 | 0.01 |
| HIFIUSDT | HIFIUSDT | 2023-01-12 00:00:00 | 2025-09-17 00:00:00 | 1.0 |
| OOKIUSDT | BZRXUSDT | 2020-08-31 00:00:00 | 2021-12-20 00:00:00 | 10.0 |
| OOKIUSDT | OOKIUSDT | 2021-12-24 00:00:00 | 2024-11-06 00:00:00 | 1.0 |
| POLUSDT | MATICUSDT | 2019-04-26 00:00:00 | 2024-09-10 00:00:00 | 1.0 |
| POLUSDT | POLUSDT | 2024-09-13 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| PUNDIXUSDT | NPXSUSDT | 2019-08-13 00:00:00 | 2021-04-05 00:00:00 | 0.001 |
| PUNDIXUSDT | PUNDIXUSDT | 2021-04-09 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| QUICKUSDT | QUICKUSDT | 2021-08-13 00:00:00 | 2023-07-17 00:00:00 | 1000.0 |
| QUICKUSDT | QUICKUSDT | 2023-07-21 00:00:00 | 2026-10-28 00:00:00 | 1.0 |
| RENDERUSDT | RNDRUSDT | 2021-11-27 00:00:00 | 2024-07-22 00:00:00 | 1.0 |
| RENDERUSDT | RENDERUSDT | 2024-07-26 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| SKYUSDT | MKRUSDT | 2020-07-23 00:00:00 | 2025-09-15 00:00:00 | 24000.0 |
| SKYUSDT | SKYUSDT | 2025-09-17 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| STRAXUSDT | STRATUSDT | 2020-02-19 00:00:00 | 2020-11-12 00:00:00 | 10.0 |
| STRAXUSDT | STRAXUSDT | 2020-11-18 00:00:00 | 2024-03-20 00:00:00 | 10.0 |
| STRAXUSDT | STRAXUSDT | 2024-03-28 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| SUNUSDT | SUNUSDT | 2020-09-21 00:00:00 | 2021-06-14 00:00:00 | 1000.0 |
| SUNUSDT | SUNUSDT | 2021-06-18 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| SUSDT | FTMUSDT | 2019-06-11 00:00:00 | 2025-01-13 00:00:00 | 1.0 |
| SUSDT | SUSDT | 2025-01-16 00:00:00 | 2026-11-01 00:00:00 | 1.0 |
| VANRYUSDT | TVKUSDT | 2021-08-06 00:00:00 | 2023-11-27 00:00:00 | 1.0 |
| VANRYUSDT | VANRYUSDT | 2023-12-01 00:00:00 | 2026-08-17 00:00:00 | 1.0 |
| VICUSDT | TOMOUSDT | 2019-08-24 00:00:00 | 2023-11-20 00:00:00 | 1.0 |
| VICUSDT | VICUSDT | 2023-11-24 00:00:00 | 2026-08-17 00:00:00 | 1.0 |

<!-- AUTO:END -->
