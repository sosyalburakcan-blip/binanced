# Araştırma v3 — kısa vadeli trend (günlük, 2–3 günlük, haftalık)

Tam dönem 2019-07-01 – 2026-11-01; tasarım 2019-07-01 – 2023-12-31; kirlenmiş bekletme 2024-01-01 – 2026-11-01. Ön kayıt `PREREGISTRATION_v3.md` (tag `prereg-v3`). Maliyetler, dolum ve evren v1 ile aynı; nakit %0; sert sınır yok.

> Bu veride gerçek örneklem dışı dönem yok (2024 sonrası G12'de görüldü). Geçen bir aile bile ancak gölge mod adayıdır.

Toplu çalıştırma: 2026-11-03 16:52:50 → 2026-11-03 16:53:10 UTC, 57 çalıştırma, commit `535ab72` (`lock/V3_run.json`).

## Sonuç

| Aile | Yıllık getiri | Sharpe | En büyük düşüş | 1.000 $ → | Kriter | Karar |
| --- | --- | --- | --- | --- | --- | --- |
| B_btc200 | 24.5% | 0.66 | -66.2% | 5,005 | kıyas | — |
| B_btchold | 31.5% | 0.71 | -76.6% | 7,493 | kıyas | — |
| B_btceth5050 | 35.9% | 0.76 | -76.2% | 9,542 | kıyas | — |
| B_univew | -7.0% | 0.31 | -92.9% | 589 | kıyas | — |
| T0 | 4.5% | 0.18 | -35.7% | 1,379 | kıyas | — |
| TS_D | -26.7% | -0.60 | -91.5% | 102 | 3/7 | reddedildi |
| TS_W | 9.3% | 0.35 | -67.8% | 1,920 | 2/7 | reddedildi |
| XS_MOM | 12.8% | 0.43 | -57.6% | 2,422 | 3/7 | reddedildi |

DSR için N = max(100, deneme 8 + önceki araştırmalar 62 + bu araştırma 13) = 100. Birincil test Bonferroni ile p < 0.0167.

## Metrikler: full

| metrik | B_btc200 | B_btchold | B_btceth5050 | B_univew | T0 | TS_D | TS_W | XS_MOM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 24.5% | 31.5% | 35.9% | -7.0% | 4.5% | -26.7% | 9.3% | 12.8% |
| annual_vol | 43.5% | 60.5% | 67.4% | 83.0% | 15.3% | 41.7% | 38.8% | 39.9% |
| sharpe | 0.657 | 0.715 | 0.759 | 0.307 | 0.180 | -0.598 | 0.350 | 0.431 |
| sortino | 0.980 | 1.042 | 1.087 | 0.421 | 0.247 | -0.828 | 0.528 | 0.634 |
| max_drawdown | -66.2% | -76.6% | -76.2% | -92.9% | -35.7% | -91.5% | -67.8% | -57.6% |
| avg_gross_exposure | 58.5% | 99.9% | 99.9% | 99.9% | 11.3% | 50.3% | 50.3% | 49.0% |
| turnover_annual | 829.4% | 13.6% | 78.0% | 563.3% | 389.5% | 19471.7% | 2716.0% | 3567.9% |
| cost_annual | 1.2% | 0.0% | 0.1% | 1.2% | 0.8% | 29.2% | 4.1% | 7.0% |
| n_cycles | 31.000 | 1.000 | 2.000 | 314.000 | 552.000 | 717.000 | 100.000 | 1323.000 |
| growth_1000 | 500.5% | 749.3% | 954.2% | 58.9% | 137.9% | 10.2% | 192.0% | 242.2% |

## Metrikler: design

| metrik | B_btc200 | B_btchold | B_btceth5050 | B_univew | T0 | TS_D | TS_W | XS_MOM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 26.6% | 36.3% | 52.2% | 3.5% | 7.4% | -32.2% | 19.6% | 22.3% |
| annual_vol | 47.7% | 67.8% | 74.4% | 88.9% | 19.5% | 47.4% | 43.7% | 41.1% |
| sharpe | 0.693 | 0.777 | 0.924 | 0.479 | 0.368 | -0.610 | 0.585 | 0.650 |
| sortino | 1.025 | 1.122 | 1.307 | 0.652 | 0.506 | -0.828 | 0.887 | 0.966 |
| max_drawdown | -66.2% | -76.6% | -76.2% | -90.9% | -35.7% | -88.9% | -67.8% | -57.6% |
| avg_gross_exposure | 56.8% | 99.9% | 99.9% | 99.9% | 18.4% | 50.2% | 50.5% | 44.4% |
| turnover_annual | 730.5% | 22.2% | 92.5% | 589.9% | 634.8% | 19950.1% | 2589.5% | 3095.0% |
| cost_annual | 1.1% | 0.0% | 0.1% | 1.3% | 1.3% | 29.9% | 3.9% | 6.3% |
| n_cycles | 17.000 | 1.000 | 2.000 | 193.000 | 552.000 | 451.000 | 59.000 | 787.000 |
| growth_1000 | 289.0% | 404.4% | 663.8% | 116.6% | 137.9% | 17.4% | 224.3% | 248.2% |

## Metrikler: holdout

| metrik | B_btc200 | B_btchold | B_btceth5050 | B_univew | T0 | TS_D | TS_W | XS_MOM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 21.3% | 24.3% | 13.6% | -21.4% | 0.0% | -17.2% | -5.3% | -0.9% |
| annual_vol | 35.9% | 46.8% | 54.4% | 72.6% | 0.0% | 30.5% | 29.3% | 38.0% |
| sharpe | 0.598 | 0.606 | 0.427 | -0.025 | -137.714 | -0.610 | -0.187 | 0.054 |
| sortino | 0.917 | 0.912 | 0.635 | -0.035 | -18.924 | -0.917 | -0.277 | 0.079 |
| max_drawdown | -30.9% | -53.0% | -60.2% | -78.5% | 0.0% | -57.3% | -45.8% | -47.1% |
| avg_gross_exposure | 61.3% | 100.0% | 100.0% | 99.9% | 0.0% | 50.5% | 50.1% | 56.4% |
| turnover_annual | 986.3% | 0.0% | 55.0% | 521.2% | 0.0% | 18712.0% | 2916.9% | 4318.8% |
| cost_annual | 1.5% | 0.0% | 0.1% | 1.1% | 0.0% | 28.1% | 4.4% | 8.1% |
| n_cycles | 14.000 | 0.000 | 0.000 | 121.000 | 0.000 | 266.000 | 41.000 | 536.000 |
| growth_1000 | 173.2% | 185.3% | 143.7% | 50.5% | 100.0% | 58.5% | 85.6% | 97.6% |

## Metrikler: regime_2019-07_2021-11

| metrik | B_btc200 | B_btchold | B_btceth5050 | B_univew | T0 | TS_D | TS_W | XS_MOM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 33.8% | 101.3% | 165.7% | 68.9% | 30.8% | -41.1% | 51.5% | 43.8% |
| annual_vol | 58.4% | 76.9% | 84.5% | 97.6% | 22.9% | 54.1% | 48.7% | 42.3% |
| sharpe | 0.782 | 1.301 | 1.592 | 1.045 | 1.267 | -0.695 | 1.084 | 1.057 |
| sortino | 1.141 | 1.902 | 2.271 | 1.433 | 1.800 | -0.910 | 1.725 | 1.570 |
| max_drawdown | -61.7% | -61.6% | -62.1% | -70.0% | -17.3% | -81.0% | -36.2% | -38.9% |
| avg_gross_exposure | 70.0% | 99.8% | 99.8% | 99.8% | 20.8% | 52.2% | 51.5% | 40.4% |
| turnover_annual | 947.1% | 41.3% | 133.1% | 630.8% | 586.6% | 20391.5% | 2429.5% | 2560.4% |
| cost_annual | 1.4% | 0.1% | 0.2% | 1.5% | 1.3% | 30.6% | 3.6% | 5.3% |
| n_cycles | 12.000 | 1.000 | 2.000 | 100.000 | 256.000 | 248.000 | 30.000 | 400.000 |

## Metrikler: regime_2022-01_end

| metrik | B_btc200 | B_btchold | B_btceth5050 | B_univew | T0 | TS_D | TS_W | XS_MOM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 27.6% | 11.5% | 2.3% | -28.7% | -6.8% | -17.7% | -4.5% | 1.5% |
| annual_vol | 33.3% | 50.3% | 56.9% | 74.5% | 9.2% | 33.9% | 32.5% | 38.7% |
| sharpe | 0.778 | 0.389 | 0.254 | -0.130 | -1.146 | -0.524 | -0.100 | 0.129 |
| sortino | 1.232 | 0.570 | 0.368 | -0.179 | -1.431 | -0.791 | -0.145 | 0.190 |
| max_drawdown | -30.9% | -66.9% | -68.2% | -87.3% | -30.1% | -65.2% | -50.8% | -47.1% |
| avg_gross_exposure | 52.5% | 100.0% | 100.0% | 99.9% | 6.4% | 49.5% | 49.7% | 53.5% |
| turnover_annual | 681.7% | 0.0% | 50.2% | 526.6% | 284.5% | 18982.2% | 2865.8% | 4086.4% |
| cost_annual | 1.0% | 0.0% | 0.1% | 1.1% | 0.5% | 28.5% | 4.3% | 7.9% |
| n_cycles | 17.000 | 0.000 | 0.000 | 209.000 | 283.000 | 460.000 | 69.000 | 909.000 |

## Yıl yıl getiri

|  | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B_btc200 | -27.5% | 177.8% | -23.5% | 0.0% | 87.8% | 79.9% | -14.5% | 12.5% |
| B_btchold | -31.2% | 302.0% | 59.8% | -64.2% | 155.6% | 121.3% | -6.3% | -10.6% |
| B_btceth5050 | -43.7% | 398.4% | 205.2% | -65.1% | 122.1% | 81.7% | -4.9% | -16.8% |
| B_univew | -55.1% | 117.7% | 209.4% | -81.2% | 105.3% | 16.8% | -53.9% | -6.1% |
| T0 | -14.2% | 46.2% | 54.3% | -23.6% | -6.7% | 0.0% | 0.0% | 0.0% |
| TS_D | -28.5% | -22.6% | -52.9% | -49.3% | 31.4% | -0.9% | -25.4% | -20.9% |
| TS_W | -27.6% | 175.1% | 20.4% | -47.3% | 77.7% | 8.8% | -8.9% | -13.6% |
| XS_MOM | -31.4% | 95.0% | 68.2% | -43.9% | 96.4% | 9.6% | -13.4% | 2.8% |

## TS_D

| # | Kriter | Değer | Durum |
| --- | --- | --- | --- |
| 1 | BTC-200'ü yener (p < 0.0167) | ΔSharpe -1.25, p = 1.0000 | **HAYIR** |
| 2 | DSR ≥ 0,95 | 0.000 | **HAYIR** |
| 3 | Tasarım ve bekletmede Sharpe > 0 (1× ve 2× maliyet) | -0.61 / -0.61; 2×: -1.24 / -1.52 | **HAYIR** |
| 4 | PBO < 0,5 | 0.230 | **evet** |
| 5 | Sıfır hipotezleri p < 0,05 | dairesel_kaydirma 0.929 | **HAYIR** |
| 6 | Kontroller beklendiği gibi | 3/3 | **evet** |
| 7 | Komşularda Sharpe > 0 ve ≥ temelin %50'si | en düşük 0.08 | **evet** |

Karar: **reddedildi**. Uydu kuralı: 0,5 × -0.60 = -0.299 vs ρ × SR_BTC200 = 0.352 (ρ = 0.54).

Komşular (tam dönem Sharpe): TS_D -0.60, TS_D_lookback2 0.08, TS_D_lookback3 0.28.

| Kontrol | Beklenen | Sonuç | Beklendiği gibi |
| --- | --- | --- | --- |
| Sinyal 365 gün gecikmeli | Sharpe ≤ temelin %50'i | -0.30 (temel -0.61) | uygulanamaz |
| Pozitif kontrol: 1 gün sızıntı | Sharpe ≥ temel + 1 | 9.26 (temel -0.61) | **evet** |
| Ortalamadan arındırılmış karıştırma (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.71 (-1.68…0.24), yıllık -31.7% | **evet** |
| GARCH serileri (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.73 (-1.31…-0.25), yıllık -38.0% | **evet** |

Sıfır hipotezleri (tasarım, basit hesap Sharpe -0.79): dairesel_kaydirma: p = 0.929, sıfır ort. -0.31, %95 0.26.

## TS_W

| # | Kriter | Değer | Durum |
| --- | --- | --- | --- |
| 1 | BTC-200'ü yener (p < 0.0167) | ΔSharpe -0.31, p = 0.8316 | **HAYIR** |
| 2 | DSR ≥ 0,95 | 0.095 | **HAYIR** |
| 3 | Tasarım ve bekletmede Sharpe > 0 (1× ve 2× maliyet) | 0.58 / -0.19; 2×: 0.50 / -0.34 | **HAYIR** |
| 4 | PBO < 0,5 | 0.612 | **HAYIR** |
| 5 | Sıfır hipotezleri p < 0,05 | dairesel_kaydirma 0.313 | **HAYIR** |
| 6 | Kontroller beklendiği gibi | 4/4 | **evet** |
| 7 | Komşularda Sharpe > 0 ve ≥ temelin %50'si | en düşük 0.57 | **evet** |

Karar: **reddedildi**. Uydu kuralı: 0,5 × 0.35 = 0.175 vs ρ × SR_BTC200 = 0.392 (ρ = 0.60).

Komşular (tam dönem Sharpe): TS_W 0.35, TS_W_lookback14 0.57, TS_W_lookback28 0.77.

| Kontrol | Beklenen | Sonuç | Beklendiği gibi |
| --- | --- | --- | --- |
| Sinyal 365 gün gecikmeli | Sharpe ≤ temelin %50'i | 0.27 (temel 0.58) | **evet** |
| Pozitif kontrol: 7 gün sızıntı | Sharpe ≥ temel + 1 | 4.24 (temel 0.58) | **evet** |
| Ortalamadan arındırılmış karıştırma (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.23 (-0.89…0.21), yıllık -16.2% | **evet** |
| GARCH serileri (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.18 (-0.60…0.22), yıllık -16.4% | **evet** |

Sıfır hipotezleri (tasarım, basit hesap Sharpe 0.58): dairesel_kaydirma: p = 0.313, sıfır ort. 0.41, %95 0.91.

## XS_MOM

| # | Kriter | Değer | Durum |
| --- | --- | --- | --- |
| 1 | BTC-200'ü yener (p < 0.0167) | ΔSharpe -0.23, p = 0.7227 | **HAYIR** |
| 2 | DSR ≥ 0,95 | 0.138 | **HAYIR** |
| 3 | Tasarım ve bekletmede Sharpe > 0 (1× ve 2× maliyet) | 0.65 / 0.05; 2×: 0.50 / -0.16 | **HAYIR** |
| 4 | PBO < 0,5 | 0.232 | **evet** |
| 5 | Sıfır hipotezleri p < 0,05 | tarih_karistirma 0.278, rastgele_coin 0.002 | **HAYIR** |
| 6 | Kontroller beklendiği gibi | 4/4 | **evet** |
| 7 | Komşularda Sharpe > 0 ve ≥ temelin %50'si | en düşük 0.31 | **evet** |

Karar: **reddedildi**. Uydu kuralı: 0,5 × 0.43 = 0.215 vs ρ × SR_BTC200 = 0.347 (ρ = 0.53).

Komşular (tam dönem Sharpe): XS_MOM 0.43, XS_MOM_lookback3 0.39, XS_MOM_lookback14 0.39, XS_MOM_n_hold3 0.60, XS_MOM_n_hold10 0.35, XS_MOM_every3 0.50, XS_MOM_every14 0.31.

| Kontrol | Beklenen | Sonuç | Beklendiği gibi |
| --- | --- | --- | --- |
| Sinyal 365 gün gecikmeli | Sharpe ≤ temelin %50'i | 0.23 (temel 0.65) | **evet** |
| Pozitif kontrol: 7 gün sızıntı | Sharpe ≥ temel + 1 | 5.04 (temel 0.65) | **evet** |
| Ortalamadan arındırılmış karıştırma (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.31 (-1.05…0.02), yıllık -15.0% | **evet** |
| GARCH serileri (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.37 (-1.33…0.51), yıllık -15.1% | **evet** |

Sıfır hipotezleri (tasarım, basit hesap Sharpe 0.64): tarih_karistirma: p = 0.278, sıfır ort. 0.51, %95 0.86; rastgele_coin: p = 0.002, sıfır ort. 0.11, %95 0.38.

