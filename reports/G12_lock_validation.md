# G12 — Kilit ve doğrulama

Kilit tarihi **2026-11-01**. Doğrulama dönemi 2024-01-01 – 2026-11-01, tam dönem 2019-07-01 – 2026-11-01. Ön kayıt `prereg-v1`. Nakit getirisi temel varsayım %0; Sharpe ABD 3 aylık hazine bonosu üzerinden, √365.

> Doğrulama dönemi tasarımı etkileyen olayları (10 Ekim 2025, 2026 ayı piyasası) içerdiği için gerçek bir test değildir; akıl sağlığı kontrolüdür. Tek gerçek test ileriye dönük 12 aylık gölge moddur.

## Kilit kaydı

| Alan | Değer |
| --- | --- |
| Kilit tarihi (son tam günlük mum) | 2026-11-01 |
| Anlık görüntü (UTC) | 2026-11-03 14:58:54 |
| Özetlenen dosya | 2061 dosya, 1.54 GB (merged, quality_flags, meta, universe, ledger) |
| `lock/data_manifest.csv` SHA-256 | `b3135253bb73be25ef257b033c8b023066e735fd00dbab70827a9317d6e77193` |
| `settings.yaml` SHA-256 | `7233684884b76ea7e668474f164899885175e9f741c065504cd2df9f79771059` |
| `PREREGISTRATION.md` SHA-256 | `a216875e5ba28c46853fd19cdf99a82f27f568917e65347305bba3850a1432d7` |
| `pyproject.toml` SHA-256 | `4409fb6c3448b87f25bdc47e3c01e7363b203a04a3a2f9fd4fb9de014ddbb1bb` |
| `uv.lock` SHA-256 | `b484f2a61abeb04c6793465c007f7082871a051ad57bd08b0affee13e812eac0` |
| Toplu çalıştırma | 2026-11-03 15:01:19 → 2026-11-03 15:02:17 UTC, 66 çalıştırma |
| Çalıştırmanın commit'i | `8ca4a5516aa674f9eadfd2c811d18440b9fb5755` |

Toplu çalıştırma bir kez yapıldı ve `lock/G12_run.json`'a yazıldı (kayıt çalıştırmadan önce açılır). Anlık görüntü `python -m trend.research.g12 verify` ile yeniden doğrulanır.

## Geliştirme döneminin yeniden üretimi (geleceği görme kontrolü)

Tam dönem çalıştırmalarının 2019-07-01 – 2023-12-31 kısmı G10 çalıştırmalarıyla karşılaştırıldı. Gerçek ve T8 panellerindeki 50 çalıştırmanın **50**'i birebir aynı (günlük getiri farkı ≤ 1e-12); en büyük fark 6.66e-16. Sonradan gelen veri geçmiş kararları değiştirmiyor.

Kontrol panelleri (karıştırma, GARCH) ve B_btcvol tüm dönem üzerinden kurulduğu için farklıdır (16 çalıştırma; tasarım gereği).

## Geç/kal kararı

Kriter dönemleri çalıştırmadan önce experiments.md satır 17'ye yazıldı.

| # | Kriter | Dönem | Değer | Durum |
| --- | --- | --- | --- | --- |
| 1 | BTC-200'ü Sharpe'ta eşleştirilmiş bootstrap ile %95 güvenle yener | tam | ΔSharpe -0.48, p = 0.8681 | **HAYIR** |
| 2 | DSR ≥ 0,95 | tam | 0.262 | **HAYIR** |
| 3 | PBO < 0,5 | geliştirme | 0.763 (tam dönem 0.570, bilgi) | **HAYIR** |
| 4 | Net Sharpe > 0, 1× ve 2× maliyet | doğrulama | -137.71 / -137.71 | **HAYIR** |
| 5 | İki sıfır hipotezi Sharpe'ta %95 | geliştirme | p = 0.8501, 0.0010 (tam dönem 0.6623, 0.0010, bilgi) | **HAYIR** |
| 6 | Bootstrap medyan MDD < evren EW'nin yarısı | tam | -31.4% / -94.0% | **evet** |
| 7 | Tüm komşularda Sharpe > 0 ve ≥ temelin %50'si | tam | en düşük 0.18 (oran 0.98) | **evet** |
| 8 | Tüm negatif kontroller beklendiği gibi | geliştirme | 8/11 (tam dönem 8/11, bilgi) | **HAYIR** |
| 9 | %20 delist cezasıyla net Sharpe > 0 | tam | 0.18 | **evet** |

**Karar (ön kayıt kuralı):**

- Birincil hipotez **reddedildi**. Varsayılan karar **BTC-200** (veya hiç işlem yapmamak); ana pozisyon BTC-200'dür.
- Uydu payı kuralı (tam dönem): 0,5 × SR_T0 = 0.090, ρ × SR_BTC200 = 0.346 (SR_T0 0.18, SR_BTC200 0.66, ρ = 0.53) → alt-coin sistemine **%0** pay.
- Kriter 2–9: 3/8 geçti → alt-coin sistemi Aşama 2'ye **geçemez**.
- Bu karardan sonra parametre veya kod değişikliği yapılmaz (SPEC "Sıralama").

## Doğrulama dönemi

| metrik | T0 | B_btc200 | B_btceth200 | B_btchold | B_btcvol | B_btc5050 | B_univew | B_trendew |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 0.0% | 21.3% | 16.2% | 24.3% | 7.9% | 14.6% | -21.4% | -17.7% |
| annual_vol | 0.0% | 35.9% | 36.5% | 46.8% | 11.9% | 23.5% | 72.6% | 36.3% |
| vol_minus_target | -35.0% | 0.9% | 1.5% | 11.8% | -23.1% | -11.5% | 37.6% | 1.3% |
| avg_gross_exposure | 0.0% | 61.3% | 54.8% | 100.0% | 25.6% | 50.5% | 99.9% | 39.8% |
| avg_cash_share | 100.0% | 38.7% | 45.2% | 0.0% | 74.4% | 49.5% | 0.1% | 60.2% |
| sharpe | -137.714 | 0.598 | 0.476 | 0.606 | 0.338 | 0.515 | -0.025 | -0.472 |
| sortino | -18.924 | 0.917 | 0.719 | 0.912 | 0.504 | 0.773 | -0.035 | -0.624 |
| calmar |  | 0.691 | 0.519 | 0.458 | 0.487 | 0.484 | -0.273 | -0.298 |
| max_drawdown | 0.0% | -30.9% | -31.2% | -53.0% | -16.2% | -30.2% | -78.5% | -59.6% |
| mdd_peak |  | 2025-01-21 | 2024-12-16 | 2025-10-06 | 2025-10-06 | 2025-10-06 | 2024-12-08 | 2024-03-13 |
| mdd_trough |  | 2025-03-29 | 2025-03-29 | 2026-06-30 | 2026-06-30 | 2026-06-30 | 2026-06-30 | 2026-08-30 |
| mdd_duration_days | 0 | 649 | 238 | 391 | 391 | 391 | 693 | 963 |
| longest_underwater_days | 0 | 649 | 391 | 391 | 391 | 391 | 693 | 963 |
| time_under_water_frac | 0.0% | 96.5% | 96.5% | 94.7% | 94.6% | 94.6% | 97.9% | 98.8% |
| skewness |  | 0.606 | 0.577 | 0.324 | 0.334 | 0.323 | -0.106 | -0.715 |
| turnover_annual | 0.0% | 986.3% | 861.9% | 0.0% | 25.1% | 32.8% | 521.2% | 1368.0% |
| cost_annual | 0.0% | 1.5% | 1.3% | 0.0% | 0.0% | 0.0% | 1.1% | 2.6% |
| n_cycles | 0 | 14 | 24 | 0 | 0 | 0 | 121 | 425 |
| win_rate |  | 28.6% | 29.2% |  |  |  | 25.6% | 16.2% |
| avg_win |  | 5058.842 | 4553.975 |  |  |  | 173.124 | 346.051 |
| avg_loss |  | -913.096 | -1287.215 |  |  |  | -143.128 | -109.108 |
| top10pct_profit_share |  | 126.9% | 258.1% |  |  |  |  |  |
| n_profitable_coins | 0 | 1 | 1 | 0 | 0 | 0 | 16 | 17 |
| n_coins_traded | 0 | 1 | 2 | 0 | 0 | 0 | 64 | 65 |
| worst_1d_at_max_exposure |  | -8.5% | -9.8% | -14.0% | -14.0% | -14.0% | -20.5% | -24.1% |
| worst_3d_at_max_exposure |  | -12.5% | -13.8% | -20.1% | -20.1% | -20.1% | -24.6% | -30.6% |

T0'ın doğrulama dönemindeki durumu (sert sınır, maruziyet):

|  | days | stop_days | avg_gross_exposure | days_invested | cycles_opened | return |
| --- | --- | --- | --- | --- | --- | --- |
| T0 | 1036.000 | 1036.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| T6_cost2 | 1036.000 | 1036.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| D_T0_nostop | 1036.000 | 0.000 | 0.250 | 992.000 | 424.000 | -0.081 |

T0 doğrulama döneminin tamamına yakınında −%35 sert sınırda kilitli: yeni alım yapamıyor, pozisyonlar sinyalle kapandıktan sonra nakitte (%0 getiri) bekliyor ve portföy zirvenin −%25'ine dönemediği için sınır kalkmıyor (G10 tanısı). Bu nedenle doğrulama Sharpe'ı hazine bonosunun altında kalan sıfır getiriden gelir; büyüklüğü anlamsız, işareti negatiftir.

Izgara (doğrulama):

| metrik | T0 | G_vol25 | G_vol45 | G_span0.8 | G_span1.2 | G_univ30 | G_univ50 | G_drift15 | G_drift35 | G_h0 | G_h1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sharpe | -137.714 | -0.254 | -137.714 | -5.806 | -137.714 | -137.714 | -9.281 | -137.714 | -137.714 | -4.345 | -137.714 |
| annual_return | 0.0% | -0.7% | 0.0% | -0.1% | 0.0% | 0.0% | 0.2% | 0.0% | 0.0% | 0.2% | 0.0% |
| max_drawdown | 0.0% | -24.2% | 0.0% | -1.2% | 0.0% | 0.0% | -0.7% | 0.0% | 0.0% | -1.1% | 0.0% |
| avg_gross_exposure | 0.0% | 19.2% | 0.0% | 0.4% | 0.0% | 0.0% | 0.3% | 0.0% | 0.0% | 0.5% | 0.0% |

Varyantlar (doğrulama):

| metrik | T0 | T1 | T3 | T4_0607 | T4_1415 | T5_20 | T5_50 | T6_cost2 | T6_loss20 | T6_loss50 | T7 | T8_h04 | T8_h08 | T8_h12 | T8_h16 | T8_h20 | T8_wd0 | T8_wd1 | T8_wd2 | T8_wd3 | T8_wd4 | T8_wd5 | T9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sharpe | -137.714 | -0.463 | -137.714 | -7.043 | -8.419 | -137.714 | -137.714 | -137.714 | -137.714 | -137.714 | -137.714 | -0.230 | -0.184 | -0.305 | -0.584 | -8.001 | -137.714 | -137.714 | -137.714 | -137.714 | -137.714 | -137.714 | -137.714 |
| annual_return | 0.0% | -5.8% | 0.0% | 0.1% | -0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | -2.3% | -1.5% | -3.9% | -8.0% | -0.1% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| max_drawdown | 0.0% | -34.6% | 0.0% | -1.0% | -0.9% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | -31.3% | -31.4% | -32.7% | -35.1% | -0.7% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| avg_gross_exposure | 0.0% | 18.9% | 0.0% | 0.5% | 0.3% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 24.6% | 25.2% | 24.9% | 22.7% | 0.3% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| cost_annual | 0.0% | 1.2% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 1.7% | 1.8% | 1.8% | 1.6% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |

T0 − BTC-200, doğrulama (bilgi): ΔSharpe -138.31, p = 1.0000 (BTC-200 Sharpe 0.60).

## Tam dönem

| metrik | T0 | B_btc200 | B_btceth200 | B_btchold | B_btcvol | B_btc5050 | B_univew | B_trendew |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 4.5% | 24.5% | 33.6% | 31.5% | 10.8% | 19.9% | -7.0% | 10.1% |
| annual_vol | 15.3% | 43.5% | 47.9% | 60.5% | 15.3% | 30.2% | 83.0% | 45.4% |
| vol_minus_target | -19.7% | 8.5% | 12.9% | 25.5% | -19.7% | -4.8% | 48.0% | 10.4% |
| avg_gross_exposure | 11.3% | 58.5% | 57.2% | 99.9% | 25.5% | 50.3% | 99.9% | 42.3% |
| avg_cash_share | 88.7% | 41.5% | 42.8% | 0.1% | 74.5% | 49.7% | 0.1% | 57.7% |
| sharpe | 0.180 | 0.657 | 0.789 | 0.715 | 0.567 | 0.660 | 0.307 | 0.382 |
| sortino | 0.247 | 0.980 | 1.132 | 1.042 | 0.825 | 0.962 | 0.421 | 0.526 |
| calmar | 0.125 | 0.370 | 0.575 | 0.412 | 0.391 | 0.408 | -0.075 | 0.143 |
| max_drawdown | -35.7% | -66.2% | -58.5% | -76.6% | -27.7% | -48.8% | -92.9% | -70.9% |
| mdd_peak | 2021-05-09 | 2021-04-13 | 2019-07-09 | 2021-11-08 | 2021-11-08 | 2021-11-08 | 2021-05-09 | 2021-05-09 |
| mdd_trough | 2023-08-25 | 2023-03-10 | 2020-05-11 | 2022-11-21 | 2022-11-21 | 2022-11-21 | 2026-06-30 | 2026-08-30 |
| mdd_duration_days | 2002 | 1055 | 499 | 846 | 827 | 840 | 2002 | 2002 |
| longest_underwater_days | 2002 | 1055 | 1006 | 846 | 827 | 840 | 2002 | 2002 |
| time_under_water_frac | 97.9% | 97.8% | 96.9% | 96.5% | 95.8% | 96.2% | 98.4% | 97.8% |
| skewness | -0.698 | 0.274 | -0.507 | -0.457 | -0.358 | -0.407 | -0.663 | -0.852 |
| turnover_annual | 389.5% | 829.4% | 748.0% | 13.6% | 34.5% | 47.3% | 563.3% | 1321.4% |
| cost_annual | 0.8% | 1.2% | 1.1% | 0.0% | 0.1% | 0.1% | 1.2% | 2.7% |
| n_cycles | 552 | 31 | 55 | 1 | 1 | 1 | 314 | 1033 |
| win_rate | 23.6% | 22.6% | 27.3% | 100.0% | 100.0% | 100.0% | 36.3% | 20.3% |
| avg_win | 125.370 | 9052.574 | 7482.914 | 64933.644 | 11300.501 | 27891.603 | 431.093 | 469.614 |
| avg_loss | -29.645 | -971.551 | -952.105 |  |  |  | -266.282 | -107.263 |
| top10pct_profit_share | 373.1% | 131.9% | 115.8% | 100.0% | 100.0% | 100.0% |  | 874.2% |
| n_profitable_coins | 29 | 1 | 2 | 1 | 1 | 1 | 44 | 39 |
| n_coins_traded | 84 | 1 | 2 | 1 | 1 | 1 | 130 | 124 |
| worst_1d_at_max_exposure | -46.0% | -14.4% | -44.6% | -39.5% | -39.5% | -39.5% | -42.9% | -46.8% |
| worst_3d_at_max_exposure | -49.4% | -21.0% | -46.8% | -39.5% | -39.5% | -39.5% | -44.8% | -50.5% |

### regime_2019-07_2021-11

| metrik | T0 | B_btc200 | B_btceth200 | B_btchold | B_btcvol | B_btc5050 | B_univew | B_trendew |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 30.8% | 33.8% | 87.2% | 101.3% | 25.5% | 51.5% | 68.9% | 84.0% |
| annual_vol | 22.9% | 58.4% | 67.7% | 76.9% | 19.6% | 38.5% | 97.6% | 61.5% |
| vol_minus_target | -12.1% | 23.4% | 32.7% | 41.9% | -15.4% | 3.5% | 62.6% | 26.5% |
| avg_gross_exposure | 20.8% | 70.0% | 73.2% | 99.8% | 26.0% | 50.9% | 99.8% | 50.9% |
| avg_cash_share | 79.2% | 30.0% | 26.8% | 0.2% | 74.0% | 49.1% | 0.2% | 49.1% |
| sharpe | 1.267 | 0.782 | 1.264 | 1.301 | 1.231 | 1.261 | 1.045 | 1.298 |
| sortino | 1.800 | 1.141 | 1.772 | 1.902 | 1.794 | 1.839 | 1.433 | 1.825 |
| calmar | 1.785 | 0.548 | 1.490 | 1.645 | 1.397 | 1.495 | 0.984 | 1.968 |
| max_drawdown | -17.3% | -61.7% | -58.5% | -61.6% | -18.3% | -34.5% | -70.0% | -42.7% |
| mdd_peak | 2020-02-14 | 2021-04-13 | 2019-07-09 | 2019-07-09 | 2019-07-09 | 2019-07-09 | 2019-07-08 | 2021-05-09 |
| mdd_trough | 2020-04-20 | 2021-10-02 | 2020-05-11 | 2020-03-12 | 2020-03-12 | 2020-03-12 | 2020-03-12 | 2021-08-03 |
| mdd_duration_days | 168 | 231 | 499 | 469 | 383 | 388 | 504 | 205 |
| longest_underwater_days | 214 | 496 | 499 | 469 | 383 | 388 | 504 | 212 |
| time_under_water_frac | 93.6% | 95.5% | 94.0% | 93.8% | 92.8% | 93.2% | 95.2% | 93.2% |
| skewness | -0.491 | 0.030 | -0.760 | -0.782 | -0.659 | -0.726 | -1.040 | -0.895 |
| turnover_annual | 586.6% | 947.1% | 885.0% | 41.3% | 49.3% | 70.5% | 630.8% | 1289.8% |
| cost_annual | 1.3% | 1.4% | 1.3% | 0.1% | 0.1% | 0.1% | 1.5% | 2.8% |
| n_cycles | 256 | 12 | 22 | 1 | 1 | 1 | 100 | 257 |
| win_rate | 32.8% | 8.3% | 18.2% | 100.0% | 100.0% | 100.0% | 53.0% | 31.9% |
| avg_win | 169.153 | 19237.038 | 9526.540 | 64933.644 | 11300.501 | 27891.603 | 721.701 | 639.584 |
| avg_loss | -29.894 | -1148.035 | -748.271 |  |  |  | -506.746 | -115.368 |
| top10pct_profit_share | 114.9% | 286.1% | 154.7% | 100.0% | 100.0% | 100.0% | 180.9% | 127.4% |
| n_profitable_coins | 33 | 1 | 1 | 1 | 1 | 1 | 29 | 31 |
| n_coins_traded | 52 | 1 | 2 | 1 | 1 | 1 | 52 | 52 |
| worst_1d_at_max_exposure | -46.0% | -14.4% | -44.6% | -39.5% | -39.5% | -39.5% | -42.9% | -46.8% |
| worst_3d_at_max_exposure | -49.4% | -21.0% | -46.8% | -39.5% | -39.5% | -39.5% | -44.8% | -50.5% |

### regime_2022-01_end

| metrik | T0 | B_btc200 | B_btceth200 | B_btchold | B_btcvol | B_btc5050 | B_univew | B_trendew |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | -6.8% | 27.6% | 19.5% | 11.5% | 5.4% | 9.2% | -28.7% | -14.3% |
| annual_vol | 9.2% | 33.3% | 33.5% | 50.3% | 12.6% | 25.0% | 74.5% | 34.8% |
| vol_minus_target | -25.8% | -1.7% | -1.5% | 15.3% | -22.4% | -10.0% | 39.5% | -0.2% |
| avg_gross_exposure | 6.4% | 52.5% | 48.7% | 100.0% | 25.4% | 50.1% | 99.9% | 38.3% |
| avg_cash_share | 93.6% | 47.5% | 51.3% | 0.0% | 74.6% | 49.9% | 0.1% | 61.7% |
| sharpe | -1.146 | 0.778 | 0.581 | 0.389 | 0.166 | 0.317 | -0.130 | -0.380 |
| sortino | -1.431 | 1.232 | 0.890 | 0.570 | 0.242 | 0.464 | -0.179 | -0.506 |
| calmar | -0.225 | 0.893 | 0.626 | 0.172 | 0.250 | 0.232 | -0.329 | -0.239 |
| max_drawdown | -30.1% | -30.9% | -31.2% | -66.9% | -21.7% | -39.6% | -87.3% | -59.6% |
| mdd_peak | 2022-01-03 | 2025-01-21 | 2024-12-16 | 2022-01-01 | 2022-03-29 | 2022-03-29 | 2022-01-03 | 2024-03-13 |
| mdd_trough | 2023-08-25 | 2025-03-29 | 2025-03-29 | 2022-11-21 | 2022-11-21 | 2022-11-21 | 2026-06-30 | 2026-08-30 |
| mdd_duration_days | 1763 | 649 | 238 | 769 | 611 | 614 | 1763 | 963 |
| longest_underwater_days | 1763 | 649 | 391 | 769 | 611 | 614 | 1763 | 963 |
| time_under_water_frac | 99.9% | 74.2% | 96.3% | 97.1% | 96.3% | 96.5% | 99.9% | 99.7% |
| skewness | -2.082 | 0.892 | 0.662 | 0.097 | 0.170 | 0.143 | -0.266 | -0.684 |
| turnover_annual | 284.5% | 681.7% | 640.8% | 0.0% | 27.4% | 36.2% | 526.6% | 1341.0% |
| cost_annual | 0.5% | 1.0% | 1.0% | 0.0% | 0.0% | 0.1% | 1.1% | 2.6% |
| n_cycles | 283 | 17 | 31 | 0 | 0 | 0 | 209 | 763 |
| win_rate | 16.3% | 35.3% | 35.5% |  |  |  | 29.2% | 16.8% |
| avg_win | 45.419 | 7355.163 | 6739.777 |  |  |  | 178.598 | 360.726 |
| avg_loss | -29.717 | -860.875 | -1161.997 |  |  |  | -168.303 | -104.054 |
| top10pct_profit_share |  | 80.2% | 108.6% |  |  |  |  |  |
| n_profitable_coins | 3 | 1 | 2 | 0 | 0 | 0 | 24 | 25 |
| n_coins_traded | 55 | 1 | 2 | 0 | 0 | 0 | 100 | 98 |
| worst_1d_at_max_exposure | -21.7% | -8.5% | -9.8% | -15.4% | -15.4% | -15.4% | -23.7% | -24.1% |
| worst_3d_at_max_exposure | -31.9% | -12.5% | -15.5% | -23.8% | -23.8% | -23.8% | -35.7% | -33.0% |

### Yıl yıl (T0)

|  | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| return | -14.2% | 46.2% | 54.3% | -23.6% | -6.7% | 0.0% | 0.0% | 0.0% |
| n_days | 184.000 | 366.000 | 365.000 | 365.000 | 365.000 | 366.000 | 365.000 | 305.000 |
| turnover | 247.0% | 743.6% | 493.8% | 731.2% | 645.5% | 0.0% | 0.0% | 0.0% |
| cost | 0.5% | 1.8% | 0.9% | 1.3% | 1.3% | 0.0% | 0.0% | 0.0% |

BTC-200:

|  | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| return | -27.5% | 177.8% | -23.5% | 0.0% | 87.8% | 79.9% | -14.5% | 12.5% |
| n_days | 184.000 | 366.000 | 365.000 | 365.000 | 365.000 | 366.000 | 365.000 | 305.000 |
| turnover | 399.2% | 499.2% | 1895.2% | 0.0% | 498.8% | 998.9% | 1700.7% | 99.9% |
| cost | 0.6% | 0.7% | 2.8% | 0.0% | 0.7% | 1.5% | 2.6% | 0.1% |

### Birincil hipotez ve istatistik

- **T0 − BTC-200 (eşleştirilmiş durağan blok bootstrap, 10.000 yol):** ΔSharpe -0.48, %95 GA -1.37…0.37, tek yönlü p = 0.8681 (T0 0.18, BTC-200 0.66).
  - regime_2019-07_2021-11: ΔSharpe 0.49, p = 0.2329.
  - regime_2022-01_end: ΔSharpe -1.92, p = 0.9999.
- **DSR:** N = max(100, deneme 6 + ızgara 11 + varyant 24) = 100; beklenen en büyük Sharpe 0.42; T0 Sharpe 0.18 (SH 0.37); DSR 0.262, PSR(0) 0.687.
- **T0 Sharpe bootstrap:** %95 GA -0.68…0.97.
- **PBO (tam dönem, bilgi):** 0.570 (geliştirme 0.763).
- **Minimum kayıt uzunluğu:** Sharpe 0.18 ile 84.0 yıl; mevcut 7.3 yıl.
- **En büyük düşüş medyanı:** T0 -31.4%, evren eşit ağırlıklı al-tut -94.0% (yolların 92%'ında yarısından küçük).

### Düşüş ufku tablosu (kilit; canlı durdurma kuralı bunu kullanır)

T0 (tam dönem getirileri; 2023-08'den sonraki uzun nakit dönemi tabloyu iyimser yapar):

| horizon_days | dd_q95 | dd_median | dd_mean |
| --- | --- | --- | --- |
| 30 | -0.089 | -0.022 | -0.028 |
| 60 | -0.110 | -0.039 | -0.046 |
| 90 | -0.133 | -0.057 | -0.060 |
| 180 | -0.176 | -0.091 | -0.093 |
| 365 | -0.237 | -0.131 | -0.138 |

BTC-200 (varsayılan karar):

| horizon_days | dd_q95 | dd_median | dd_mean |
| --- | --- | --- | --- |
| 30 | -0.228 | -0.070 | -0.085 |
| 60 | -0.285 | -0.119 | -0.132 |
| 90 | -0.347 | -0.153 | -0.166 |
| 180 | -0.471 | -0.225 | -0.240 |
| 365 | -0.577 | -0.304 | -0.331 |

### Izgara ve varyantlar (tam dönem)

| metrik | T0 | G_vol25 | G_vol45 | G_span0.8 | G_span1.2 | G_univ30 | G_univ50 | G_drift15 | G_drift35 | G_h0 | G_h1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sharpe | 0.180 | 0.352 | 0.306 | 0.264 | 0.211 | 0.213 | 0.373 | 0.176 | 0.180 | 0.257 | 0.217 |
| annual_return | 4.5% | 7.3% | 6.8% | 5.8% | 5.0% | 5.0% | 7.8% | 4.4% | 4.5% | 5.6% | 5.1% |
| annual_vol | 15.3% | 15.4% | 17.5% | 15.2% | 15.4% | 15.4% | 16.2% | 15.2% | 15.4% | 14.5% | 16.0% |
| max_drawdown | -35.7% | -28.2% | -35.9% | -35.2% | -35.3% | -35.5% | -35.6% | -35.4% | -36.0% | -35.0% | -35.9% |
| turnover_annual | 389.5% | 615.2% | 347.8% | 465.1% | 339.9% | 377.1% | 443.7% | 396.4% | 383.3% | 523.0% | 310.0% |
| sharpe_vs_base | 1.000 | 1.955 | 1.702 | 1.467 | 1.170 | 1.186 | 2.071 | 0.977 | 0.998 | 1.427 | 1.206 |

| metrik | T0 | T1 | T3 | T4_0607 | T4_1415 | T5_20 | T5_50 | T6_cost2 | T6_loss20 | T6_loss50 | T7 | T8_h04 | T8_h08 | T8_h12 | T8_h16 | T8_h20 | T8_wd0 | T8_wd1 | T8_wd2 | T8_wd3 | T8_wd4 | T8_wd5 | T9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sharpe | 0.180 | 0.441 | 0.194 | 0.272 | 0.286 | 0.180 | 0.180 | 0.152 | 0.070 | -0.111 | 0.180 | 0.461 | 0.528 | 0.479 | 0.398 | 0.273 | 0.152 | 0.149 | 0.126 | 0.198 | 0.198 | 0.207 | -0.084 |
| annual_return | 4.5% | 9.8% | 4.7% | 6.0% | 6.2% | 4.5% | 4.5% | 4.0% | 2.5% | -3.8% | 4.5% | 10.8% | 12.4% | 11.2% | 9.2% | 6.0% | 4.0% | 4.0% | 3.6% | 4.8% | 4.8% | 4.9% | 0.9% |
| max_drawdown | -35.7% | -34.6% | -36.6% | -35.4% | -35.8% | -35.7% | -35.7% | -35.7% | -43.9% | -65.0% | -35.7% | -34.2% | -31.9% | -32.7% | -35.1% | -35.2% | -35.6% | -35.0% | -35.8% | -36.1% | -35.4% | -35.2% | -36.9% |
| avg_gross_exposure | 11.3% | 18.0% | 11.3% | 11.9% | 11.8% | 11.3% | 11.3% | 10.8% | 8.4% | 8.4% | 11.3% | 23.1% | 23.6% | 23.6% | 23.1% | 12.2% | 10.5% | 10.5% | 11.4% | 11.3% | 10.7% | 10.5% | 7.5% |
| cost_annual | 0.8% | 1.1% | 0.8% | 0.8% | 0.8% | 0.8% | 0.8% | 1.5% | 0.6% | 0.6% | 0.8% | 1.6% | 1.6% | 1.6% | 1.6% | 0.9% | 0.7% | 0.7% | 0.8% | 0.8% | 0.7% | 0.7% | 0.7% |

T10 (BTC-200 çekirdek + T0 uydu, aylık):

|  | T10_core80 | T10_core50 |
| --- | --- | --- |
| sharpe | 0.653 | 0.613 |
| annual_return | 22.2% | 16.9% |
| max_drawdown | -58.2% | -46.1% |

**T6 karşı taraf stresi:** T0 yıllık aşırı log getirisi 1.6%, BTC-200 19.1%. L = %20: getiriyi sıfırlayan p* = 0.071/yıl, BTC-200 düzeyine indiren p* = 0.000/yıl; L = %50: getiriyi sıfırlayan p* = 0.023/yıl, BTC-200 düzeyine indiren p* = 0.000/yıl.

### Regresyon (HAC, tam dönem)

|  | katsayı | t |
| --- | --- | --- |
| const | -0.000 | -0.090 |
| btc | 0.005 | 0.443 |
| ew_universe | 0.115 | 8.966 |

Yıllık alfa -0.4%, R² 0.41; β⁺ 0.10, β⁻ 0.18.

### Nakit getirisi duyarlılığı (tam dönem)

| metrik | T0 | T0_cash_m15 | T0_cash_tb | B_btc200 | B_btc200_cash_m15 | B_btc200_cash_tb | T0_fixed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 4.5% | 6.8% | 11.2% | 24.5% | 25.2% | 25.9% | 8.3% |
| annual_return_simple | 5.5% | 7.9% | 12.8% | 31.4% | 32.0% | 32.4% | 9.0% |
| sharpe | 0.180 | 0.314 | 0.484 | 0.657 | 0.670 | 0.681 | 0.441 |
| max_drawdown | -35.7% | -35.4% | -34.3% | -66.2% | -65.8% | -65.4% | -23.5% |
| avg_cash_share | 88.7% | 85.5% | 76.9% | 41.5% | 41.5% | 41.5% | 84.8% |
| cash_drag_annual | 2.6% | 2.5% | 2.1% | 1.1% | 1.1% | 1.1% | 2.4% |

### Dolar cinsinden (USDCUSDT'nin tersi vekil)

|  | T0 | B_btc200 |
| --- | --- | --- |
| annual_return_usd | 4.5% | 24.6% |
| sharpe_usd | 0.183 | 0.657 |
| usdt_usd_min | 99.4% | 99.4% |
| usdt_usd_max | 104.3% | 104.3% |

### Sıfır hipotezleri ve kontroller (tam dönem, bilgi)

| Sıfır | p (Sharpe) | sıfır ort. Sharpe | sıfır %95 |
| --- | --- | --- | --- |
| a_tarih_karistirma | 0.6623 | 0.25 | 0.50 |
| b_rastgele_coin | 0.0010 | -0.03 | 0.07 |

| Kontrol | Beklenen | Sonuç | Beklendiği gibi |
| --- | --- | --- | --- |
| Getiriler tarihe göre birlikte karıştırıldı (5 tohum) | Avantaj kaybolur (maliyet kadar zarar) | Sharpe ort. 0.44 (aralık 0.14…0.66), yıllık getiri ort. 10.9%, yıllık maliyet ort. 1.7%; kıyas T3 Sharpe 0.19 | **HAYIR** |
| Oynaklığı eşleştirilmiş GARCH serileri (5 tohum) | Avantaj kaybolur (maliyet kadar zarar) | Sharpe ort. -0.65 (aralık -1.21…0.03), yıllık getiri ort. -3.2%, yıllık maliyet ort. 1.6%; kıyas T3 Sharpe 0.19 | **evet** |
| Bir coinin sinyali başka coinin getirisine | Avantaj büyük ölçüde kaybolur | 200 eşleme medyan Sharpe -0.07 (gözlenen, basit hesap 0.18) | **evet** |
| Sinyal 365 gün gecikmeli | Avantaj kaybolur | Sharpe -0.08 (T0 0.18) | **evet** |
| Orijinal − ters sinyal | Anlamlı ölçüde sıfırın üzerinde | ΔSharpe 0.50, %95 GA -0.35…1.28, p = 0.1257 (ters sinyal Sharpe -0.32) | **HAYIR** |
| Kararlar 1 gün gecikmeli (sinyal gecikmesi) | Biraz bozulur, çökmez | Sharpe 0.23 (T0 0.18) | **evet** |
| Kararlar 3 gün gecikmeli (sinyal gecikmesi) | Biraz bozulur, çökmez | Sharpe 0.16 (T0 0.18) | **evet** |
| Mum zamanlaması değişir (T8, 5 saat + 6 giriş günü) | Benzer sonuç | Sharpe aralığı 0.13…0.53 (T0 0.18) | **evet** |
| Bir yıl çıkarılır | Sonuç tek bir yıla bağlı olmamalı | Sharpe: 2019: 0.34, 2020: -0.24, 2021: -0.32, 2022: 0.49, 2023: 0.32, 2024: 0.24, 2025: 0.23, 2026: 0.22 | **HAYIR** |
| En iyi 5 döngü çıkarılır | Sıfıra yakın veya pozitif | Sharpe (basit hesap) -0.07, tüm döngülerle 0.18 | **evet** |
| Pozitif kontrol: sinyale 1 gün sızıntı | Sharpe belirgin yükselir (yakalanmalı) | Sharpe 1.90 (T0 0.18) | **evet** |

Hazine bonosu tam dönem ortalaması: yıllık 2.79%.

## Ön kayıt dışı tanılar (seçim için kullanılmaz)

T0 sert sınır kapalı (`D_T0_nostop`), döneme göre Sharpe:

|  | development | validation | full | regime_2019-07_2021-11 | regime_2022-01_end |
| --- | --- | --- | --- | --- | --- |
| T0 | 0.37 | -137.71 | 0.18 | 1.27 | -1.15 |
| D_T0_nostop | 0.77 | -0.26 | 0.38 | 1.27 | -0.14 |

Sert sınır geçmişi (tam dönem):

|  | stop_days | first_stop | stopped_at_end | max_drawdown |
| --- | --- | --- | --- | --- |
| T0 | 1173 | 2023-08-17 | True | -0.357 |
| G_vol45 | 1454 | 2022-11-09 | True | -0.359 |
| G_span0.8 | 1117 | 2023-10-12 | True | -0.352 |
| G_span1.2 | 1241 | 2023-06-10 | True | -0.353 |
| G_univ30 | 1241 | 2023-06-10 | True | -0.355 |
| G_univ50 | 1148 | 2023-09-11 | True | -0.356 |
| G_drift15 | 1173 | 2023-08-17 | True | -0.354 |
| G_drift35 | 1173 | 2023-08-17 | True | -0.360 |
| G_h0 | 1117 | 2023-10-12 | True | -0.350 |
| G_h1 | 1173 | 2023-08-17 | True | -0.359 |
| T3 | 1174 | 2023-08-16 | True | -0.366 |
| T4_0607 | 1148 | 2023-09-11 | True | -0.354 |
| T4_1415 | 1150 | 2023-09-09 | True | -0.358 |
| T5_20 | 1173 | 2023-08-17 | True | -0.357 |
| T5_50 | 1173 | 2023-08-17 | True | -0.357 |
| T6_cost2 | 1223 | 2023-06-28 | True | -0.357 |
| T6_loss20 | 1455 | 2022-11-08 | True | -0.439 |
| T6_loss50 | 1455 | 2022-11-08 | True | -0.650 |
| T7 | 1173 | 2023-08-17 | True | -0.357 |
| T8_h16 | 118 | 2026-07-07 | True | -0.351 |
| T8_h20 | 1149 | 2023-09-10 | True | -0.352 |
| T8_wd0 | 1241 | 2023-06-10 | True | -0.356 |
| T8_wd1 | 1237 | 2023-06-14 | True | -0.350 |
| T8_wd2 | 1173 | 2023-08-17 | True | -0.358 |
| T8_wd3 | 1173 | 2023-08-17 | True | -0.361 |
| T8_wd4 | 1241 | 2023-06-10 | True | -0.354 |
| T8_wd5 | 1271 | 2023-05-11 | True | -0.352 |
| T9 | 1454 | 2022-11-09 | True | -0.369 |
| T0_cash_m15 | 858 | 2023-09-11 | False | -0.354 |
| C_lag1 | 1173 | 2023-08-17 | True | -0.360 |
| C_lag3 | 1173 | 2023-08-17 | True | -0.371 |
| C_lag365 | 1635 | 2022-05-12 | True | -0.355 |
| C_inverse | 274 | 2026-02-01 | True | -0.390 |
| C_shuffle2 | 706 | 2024-11-26 | True | -0.375 |
| C_shuffle4 | 690 | 2024-12-12 | True | -0.371 |
| C_garch1 | 1709 | 2022-02-27 | True | -0.360 |
| C_garch2 | 1800 | 2021-11-28 | True | -0.371 |
| C_garch3 | 653 | 2025-01-18 | True | -0.359 |
| C_garch4 | 1369 | 2023-02-02 | True | -0.364 |
| D_shuffledm0 | 1896 | 2021-08-24 | True | -0.356 |
| D_shuffledm1 | 963 | 2024-03-14 | True | -0.360 |
| D_shuffledm2 | 1113 | 2023-10-16 | True | -0.362 |
| D_shuffledm3 | 2150 | 2020-12-13 | True | -0.375 |
| D_shuffledm4 | 1511 | 2022-09-13 | True | -0.362 |

## Altın kayıt

T0 ve BTC-200'ün tam dönem karar, dolum ve günlük kayıtları `golden/` altında (commit `8ca4a55`). Her kod veya kütüphane değişikliğinden sonra `python -m trend.research.g12 golden --check` (ve `tests/test_golden_master.py`) aynı kararları yeniden üretmeli (ondalık alanlarda göreli 1e-09).

| Dosya | Satır | CSV SHA-256 |
| --- | --- | --- |
| `T0_decisions.csv.gz` | 52102 | `1ec28c0e8ab9bab0…` |
| `T0_fills.csv.gz` | 2400 | `5706360898b4b0e4…` |
| `T0_daily.csv.gz` | 2681 | `68e98d9018c241d9…` |
| `B_btc200_decisions.csv.gz` | 49999 | `3269c4912cc2a535…` |
| `B_btc200_fills.csv.gz` | 63 | `7eb746b1b0bd304d…` |
| `B_btc200_daily.csv.gz` | 2681 | `b19d5c7aa6e3ab49…` |

Son kontrol (2026-11-03 15:02:48): **geçti**; birebir aynı bayt: 6/6 dosya.

