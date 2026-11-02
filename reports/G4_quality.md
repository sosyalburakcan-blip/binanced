# G4 — Veri kalitesi raporu

_Üretildi: `python -m trend.quality report` · işaret tablosu sha256 `effb68a8851bd67abba16378df5c087fe35729c3e5c62e53108daf03242391c6`_

Kurallar SPEC "Veri kalitesi ve meta tablolar" ve CONTRACTS §5'e göredir; satır tasarımı ve varsayımlar `src/trend/quality.py` başındaki açıklamadadır. T günündeki karar yalnızca `known_from ≤ T − 1` işaretleri kullanır.

## Kontrol başına sayılar (1d)

| check | severity | rows | symbols |
| --- | --- | --- | --- |
| extreme_return | flag | 1728 | 767 |
| extreme_wick | flag | 952 | 732 |
| half_day | flag | 2850 | 1755 |
| missing_days | flag | 66 | 64 |
| ohlc_inconsistent | error | 7 | 3 |
| split_candidate | flag | 15 | 15 |
| timestamp | error | 1 | 1 |
| zero_volume | exclude | 43 | 7 |

Temizleyicinin tekrar kaydı (`_duplicates.csv`, ilk satır tutuldu): exact 4; 4 sembol. Yalnız `conflict` olanlar `duplicate_open_time` hatası olarak işaretlendi.

## En çok işaretlenen semboller

Kullanılamaz gün (error/exclude/yarım gün) sayısına göre ilk 20:

| symbol | unusable_days |
| --- | --- |
| BGBPUSDC | 22 |
| MORPHOFDUSD | 9 |
| SOPHFDUSD | 6 |
| BTTUSDT | 6 |
| BTCTUSD | 6 |
| TFUELTUSD | 5 |
| INITFDUSD | 5 |
| MIRAFDUSD | 5 |
| SAHARAFDUSD | 5 |
| ETHTUSD | 5 |
| ADATUSD | 4 |
| PAXGBUSD | 4 |
| KEYUSDT | 4 |
| FTMUSDC | 4 |
| AEURUSDT | 4 |
| LTCTUSD | 4 |
| PHBTUSD | 4 |
| XRPTUSD | 4 |
| SUSHIDOWNUSDT | 4 |
| TUSDBUSD | 4 |
_(+1735 satır daha)_

`extreme_return` satır sayısına göre ilk 10:

| symbol | rows |
| --- | --- |
| XRPDOWNUSDT | 19 |
| SUSHIDOWNUSDT | 16 |
| DOTDOWNUSDT | 16 |
| FILDOWNUSDT | 13 |
| XRPUPUSDT | 12 |
| LUNABUSD | 12 |
| EOSUPUSDT | 11 |
| LUNAUSDT | 11 |
| SXPDOWNUSDT | 11 |
| XTZDOWNUSDT | 11 |
_(+757 satır daha)_

`extreme_wick` satır sayısına göre ilk 10:

| symbol | rows |
| --- | --- |
| SUSHIDOWNUSDT | 6 |
| SXPDOWNUSDT | 5 |
| LUNABUSD | 5 |
| ANCUSDT | 4 |
| LUNAUSDT | 4 |
| ANCBUSD | 3 |
| USDCBUSD | 3 |
| ALPINEUSDT | 3 |
| TUSDBUSD | 3 |
| BANANAS31USDC | 3 |
_(+722 satır daha)_

`missing_days` satır sayısına göre ilk 10:

| symbol | rows |
| --- | --- |
| ETHTUSD | 2 |
| BTCTUSD | 2 |
| ADATUSD | 1 |
| ADAUSDC | 1 |
| ATOMUSDC | 1 |
| BCCUSDT | 1 |
| AEURUSDT | 1 |
| ALGOUSDC | 1 |
| BCHUPUSDT | 1 |
| BCHUSDC | 1 |
_(+54 satır daha)_

## 10 Ekim 2025 bilinen iğneleri

| symbol | spec_low | data_low | close | flagged |
| --- | --- | --- | --- | --- |
| WBETHUSDT | 430.0 | 430.65 | 4000.0 | True |
| BNSOLUSDT | 34.9 | 34.9 | 197.4 | True |
| USDEUSDT | 0.65 | 0.65 | 0.9978 | False |

Not: kural low < 0,3 × close'dur; USDe'nin ~0,65'lik iğnesi (~%35 düşüş) bu eşiğin altında kalmaz, dolayısıyla işaretlenmemesi beklenir (USDe zaten stablecoin olarak evren dışıdır). wBETH/BNSOL dışlama listesinde.

## Veriden ne öğrendik

- Temiz 1d çift sayısı: **1755**; kotasyona göre: BUSD 378, FDUSD 197, TUSD 67, USDC 338, USDT 775.
- En erken gün: **2017-08-17** (BTCUSDT); en geç gün (data_end): **2026-11-01**.
- Veri sonundan 7+ gün önce biten (delist/rename) çift: **949**.

Yıllara göre sembol sayıları (active = yıl içinde en az bir mum):

| year | usdt_active | usdt_listed | usdt_ended | all_active |
| --- | --- | --- | --- | --- |
| 2017 | 6 | 6 | 0 | 6 |
| 2018 | 24 | 18 | 2 | 38 |
| 2019 | 90 | 68 | 3 | 175 |
| 2020 | 245 | 158 | 18 | 436 |
| 2021 | 354 | 127 | 20 | 672 |
| 2022 | 375 | 41 | 38 | 754 |
| 2023 | 395 | 58 | 24 | 835 |
| 2024 | 434 | 63 | 46 | 727 |
| 2025 | 490 | 102 | 51 | 963 |
| 2026 | 573 | 134 | 52 | 1016 |

- Boşluk: **66** boşluk, **64** sembolde, toplam **26152** eksik gün. En uzun 15:

| symbol | period_start | period_end | n_missing |
| --- | --- | --- | --- |
| USDSUSDT | 2020-06-25 | 2026-04-08 | 2114 |
| ETCUSDC | 2019-11-16 | 2025-07-21 | 2075 |
| XLMUSDC | 2020-01-08 | 2024-12-03 | 1792 |
| DOGEUSDC | 2019-10-01 | 2024-03-06 | 1619 |
| ALGOUSDC | 2020-01-08 | 2024-04-25 | 1570 |
| ONTUSDC | 2020-01-08 | 2024-04-23 | 1568 |
| FTMUSDC | 2020-01-08 | 2024-03-26 | 1540 |
| ZECUSDC | 2022-09-30 | 2025-11-04 | 1132 |
| NEOUSDC | 2021-12-11 | 2024-04-18 | 860 |
| LINKTUSD | 2021-09-19 | 2023-10-04 | 746 |
| TRXUSDC | 2022-09-30 | 2024-09-03 | 705 |
| BCHTUSD | 2021-09-19 | 2023-06-29 | 649 |
| BLZBUSD | 2020-11-18 | 2022-06-16 | 576 |
| EOSUSDC | 2022-09-30 | 2024-04-25 | 574 |
| ATOMUSDC | 2022-09-30 | 2024-04-16 | 565 |
_(+51 satır daha)_

- Sembol değişmeden bölünme adayı: **15** (tamamı `meta/symbol_map_candidates.csv` üzerinden incelenir):

| symbol | period_start | period_end | detail |
| --- | --- | --- | --- |
| BNXBUSD | 2023-02-16 | 2023-02-22 | prev_close=175.8;next_open=1.758;log10_ratio=2;k=2;suggested_ratio=100;gap_days=5 |
| BNXUSDT | 2023-02-16 | 2023-02-22 | prev_close=175.5;next_open=1.755;log10_ratio=2;k=2;suggested_ratio=100;gap_days=5 |
| BTCSTBUSD | 2021-03-15 | 2021-03-19 | prev_close=373.612;next_open=37.361;log10_ratio=1.000002325;k=1;suggested_ratio=10;gap_days=3 |
| BTCSTUSDT | 2021-03-15 | 2021-03-19 | prev_close=374.996;next_open=37.499;log10_ratio=1.000006949;k=1;suggested_ratio=10;gap_days=3 |
| COCOSUSDT | 2021-01-19 | 2021-01-23 | prev_close=0.000695;next_open=0.695;log10_ratio=-3;k=-3;suggested_ratio=0.001;gap_days=3 |
| DREPUSDT | 2021-03-29 | 2021-04-02 | prev_close=0.026288;next_open=2.629;log10_ratio=-2.00003304;k=-2;suggested_ratio=0.01;gap_days=3 |
| ETHDOWNUSDT | 2021-07-08 | 2021-07-09 | prev_close=5.9e-05;next_open=6;log10_ratio=-5.007299239;k=-5;suggested_ratio=1e-05;gap_days=0 |
| FTMUSDC | 2020-01-07 | 2024-03-27 | prev_close=0.01107;next_open=1.0648;log10_ratio=-1.983120422;k=-2;suggested_ratio=0.01;gap_days=1540 |
| PHBTUSD | 2021-11-01 | 2021-11-05 | prev_close=0.013818;next_open=1.4;log10_ratio=-2.005682847;k=-2;suggested_ratio=0.01;gap_days=3 |
| QUICKUSDT | 2023-07-17 | 2023-07-21 | prev_close=74.2;next_open=0.0742;log10_ratio=3;k=3;suggested_ratio=1000;gap_days=3 |
| STRAXUSDT | 2024-03-20 | 2024-03-28 | prev_close=1.423;next_open=0.1423;log10_ratio=1;k=1;suggested_ratio=10;gap_days=7 |
| SUNUSDT | 2021-06-14 | 2021-06-18 | prev_close=27.572;next_open=0.02757;log10_ratio=3.000031504;k=3;suggested_ratio=1000;gap_days=3 |
| SUSHIDOWNUSDT | 2021-09-23 | 2021-09-24 | prev_close=0.0005288;next_open=54.865;log10_ratio=-5.016003937;k=-5;suggested_ratio=1e-05;gap_days=0 |
| TRXDOWNUSDT | 2021-09-13 | 2021-09-14 | prev_close=0.00012;next_open=12.154;log10_ratio=-5.005537986;k=-5;suggested_ratio=1e-05;gap_days=0 |
| XLMUSDC | 2020-01-07 | 2024-12-04 | prev_close=0.0497;next_open=0.5066;log10_ratio=-1.008308797;k=-1;suggested_ratio=0.1;gap_days=1792 |

- Kullanılamaz (error/exclude/yarım gün) sembol-gün sayısı: **2899**; tüm işaretlerin kapsadığı sembol-gün: **31137**.

## Tarih kesme değişmezi (gerçek veri örneği)

25 sembol × 3 kesim tarihi: **75/75** eşit (GEÇTİ).

## REST çapraz kontrolü (bağımsız kaynak)

19 coin, 210 gün karşılaştırıldı; uyuşmayan alan: **0** (`reports/G4_rest_crosscheck.csv`).

