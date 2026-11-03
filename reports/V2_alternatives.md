# Araştırma v2 — trend takibi dışındaki stratejiler

Tam dönem 2019-07-01 – 2026-11-01; tasarım 2019-07-01 – 2023-12-31; kirlenmiş bekletme 2024-01-01 – 2026-11-01. Ön kayıt `PREREGISTRATION_v2.md` (tag `prereg-v2`). Maliyetler, dolum ve evren v1 ile aynı; nakit %0; sert sınır yok.

> Bu veride gerçek örneklem dışı dönem yok (2024 sonrası G12'de görüldü). Geçen bir aile bile ancak gölge mod adayıdır.

Toplu çalıştırma: 2026-11-03 16:11:50 → 2026-11-03 16:12:15 UTC, 97 çalıştırma, commit `b03c3b9` (`lock/V2_run.json`).

## Sonuç

| Aile | Yıllık getiri | Sharpe | En büyük düşüş | 1.000 $ → | Kriter | Karar |
| --- | --- | --- | --- | --- | --- | --- |
| B_btc200 | 24.5% | 0.66 | -66.2% | 5,005 | kıyas | — |
| B_btchold | 31.5% | 0.71 | -76.6% | 7,493 | kıyas | — |
| B_btceth5050 | 35.9% | 0.76 | -76.2% | 9,542 | kıyas | — |
| B_univew | -7.0% | 0.31 | -92.9% | 589 | kıyas | — |
| T0 | 4.5% | 0.18 | -35.7% | 1,379 | kıyas | — |
| XS_REV | 6.3% | 0.27 | -56.7% | 1,564 | 1/7 | reddedildi |
| XS_LOWVOL | 29.4% | 0.76 | -44.7% | 6,622 | 2/7 | reddedildi |
| VM_BTC | 24.5% | 0.64 | -71.1% | 5,010 | 2/7 | reddedildi |
| MR_BTC | -9.8% | -0.20 | -77.0% | 469 | 1/7 | reddedildi |
| RV_ETHBTC | 16.6% | 0.53 | -77.7% | 3,090 | 3/7 | reddedildi |

DSR için N = max(100, deneme 7 + v1 35 + v2 27) = 100. Birincil test Bonferroni ile p < 0,01.

## Metrikler: full

| metrik | B_btc200 | B_btchold | B_btceth5050 | B_univew | T0 | XS_REV | XS_LOWVOL | VM_BTC | MR_BTC | RV_ETHBTC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 24.5% | 31.5% | 35.9% | -7.0% | 4.5% | 6.3% | 29.4% | 24.5% | -9.8% | 16.6% |
| annual_vol | 43.5% | 60.5% | 67.4% | 83.0% | 15.3% | 35.4% | 41.8% | 47.9% | 34.1% | 69.2% |
| sharpe | 0.657 | 0.715 | 0.759 | 0.307 | 0.180 | 0.271 | 0.758 | 0.643 | -0.201 | 0.533 |
| sortino | 0.980 | 1.042 | 1.087 | 0.421 | 0.247 | 0.385 | 1.098 | 0.924 | -0.264 | 0.773 |
| max_drawdown | -66.2% | -76.6% | -76.2% | -92.9% | -35.7% | -56.7% | -44.7% | -71.1% | -77.0% | -77.7% |
| avg_gross_exposure | 58.5% | 99.9% | 99.9% | 99.9% | 11.3% | 44.1% | 65.4% | 85.1% | 19.7% | 99.9% |
| turnover_annual | 829.4% | 13.6% | 78.0% | 563.3% | 389.5% | 3599.6% | 449.5% | 154.9% | 1154.7% | 3363.0% |
| cost_annual | 1.2% | 0.0% | 0.1% | 1.2% | 0.8% | 7.3% | 0.9% | 0.2% | 1.7% | 5.0% |
| n_cycles | 31.000 | 1.000 | 2.000 | 314.000 | 552.000 | 1389.000 | 119.000 | 1.000 | 43.000 | 123.000 |
| growth_1000 | 500.5% | 749.3% | 954.2% | 58.9% | 137.9% | 156.4% | 662.2% | 501.0% | 46.9% | 309.0% |

## Metrikler: design

| metrik | B_btc200 | B_btchold | B_btceth5050 | B_univew | T0 | XS_REV | XS_LOWVOL | VM_BTC | MR_BTC | RV_ETHBTC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 26.6% | 36.3% | 52.2% | 3.5% | 7.4% | 1.1% | 33.4% | 22.5% | -17.3% | 34.1% |
| annual_vol | 47.7% | 67.8% | 74.4% | 88.9% | 19.5% | 35.4% | 42.3% | 50.6% | 39.2% | 74.2% |
| sharpe | 0.693 | 0.777 | 0.924 | 0.479 | 0.368 | 0.158 | 0.850 | 0.623 | -0.320 | 0.751 |
| sortino | 1.025 | 1.122 | 1.307 | 0.652 | 0.506 | 0.215 | 1.218 | 0.877 | -0.410 | 1.081 |
| max_drawdown | -66.2% | -76.6% | -76.2% | -90.9% | -35.7% | -56.7% | -44.7% | -71.1% | -77.0% | -77.7% |
| avg_gross_exposure | 56.8% | 99.9% | 99.9% | 99.9% | 18.4% | 41.4% | 57.2% | 79.5% | 20.0% | 99.8% |
| turnover_annual | 730.5% | 22.2% | 92.5% | 589.9% | 634.8% | 3226.1% | 436.3% | 199.4% | 1108.5% | 3582.3% |
| cost_annual | 1.1% | 0.0% | 0.1% | 1.3% | 1.3% | 6.7% | 0.9% | 0.3% | 1.7% | 5.4% |
| n_cycles | 17.000 | 1.000 | 2.000 | 193.000 | 552.000 | 822.000 | 78.000 | 1.000 | 25.000 | 81.000 |
| growth_1000 | 289.0% | 404.4% | 663.8% | 116.6% | 137.9% | 105.3% | 366.4% | 249.2% | 42.4% | 375.9% |

## Metrikler: holdout

| metrik | B_btc200 | B_btchold | B_btceth5050 | B_univew | T0 | XS_REV | XS_LOWVOL | VM_BTC | MR_BTC | RV_ETHBTC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 21.3% | 24.3% | 13.6% | -21.4% | 0.0% | 15.0% | 23.2% | 27.9% | 3.7% | -6.7% |
| annual_vol | 35.9% | 46.8% | 54.4% | 72.6% | 0.0% | 35.4% | 40.9% | 43.3% | 23.9% | 60.6% |
| sharpe | 0.598 | 0.606 | 0.427 | -0.025 | -137.714 | 0.449 | 0.608 | 0.685 | 0.091 | 0.116 |
| sortino | 0.917 | 0.912 | 0.635 | -0.035 | -18.924 | 0.690 | 0.897 | 1.034 | 0.134 | 0.171 |
| max_drawdown | -30.9% | -53.0% | -60.2% | -78.5% | 0.0% | -49.9% | -44.4% | -53.2% | -41.1% | -71.4% |
| avg_gross_exposure | 61.3% | 100.0% | 100.0% | 99.9% | 0.0% | 48.3% | 78.4% | 94.0% | 19.3% | 100.0% |
| turnover_annual | 986.3% | 0.0% | 55.0% | 521.2% | 0.0% | 4192.8% | 470.6% | 84.3% | 1228.1% | 3014.8% |
| cost_annual | 1.5% | 0.0% | 0.1% | 1.1% | 0.0% | 8.2% | 0.9% | 0.1% | 1.8% | 4.5% |
| n_cycles | 14.000 | 0.000 | 0.000 | 121.000 | 0.000 | 567.000 | 41.000 | 0.000 | 18.000 | 42.000 |
| growth_1000 | 173.2% | 185.3% | 143.7% | 50.5% | 100.0% | 148.6% | 180.7% | 201.0% | 110.8% | 82.2% |

## Metrikler: regime_2019-07_2021-11

| metrik | B_btc200 | B_btchold | B_btceth5050 | B_univew | T0 | XS_REV | XS_LOWVOL | VM_BTC | MR_BTC | RV_ETHBTC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 33.8% | 101.3% | 165.7% | 68.9% | 30.8% | 14.6% | 59.9% | 58.0% | -8.2% | 104.9% |
| annual_vol | 58.4% | 76.9% | 84.5% | 97.6% | 22.9% | 36.3% | 45.4% | 52.8% | 44.6% | 82.6% |
| sharpe | 0.782 | 1.301 | 1.592 | 1.045 | 1.267 | 0.544 | 1.252 | 1.130 | 0.045 | 1.290 |
| sortino | 1.141 | 1.902 | 2.271 | 1.433 | 1.800 | 0.746 | 1.780 | 1.591 | 0.059 | 1.877 |
| max_drawdown | -61.7% | -61.6% | -62.1% | -70.0% | -17.3% | -34.6% | -37.8% | -47.2% | -54.9% | -71.3% |
| avg_gross_exposure | 70.0% | 99.8% | 99.8% | 99.8% | 20.8% | 37.8% | 48.6% | 71.7% | 17.7% | 99.7% |
| turnover_annual | 947.1% | 41.3% | 133.1% | 630.8% | 586.6% | 2710.5% | 413.9% | 231.4% | 1033.4% | 2963.3% |
| cost_annual | 1.4% | 0.1% | 0.2% | 1.5% | 1.3% | 5.9% | 0.9% | 0.3% | 1.6% | 4.4% |
| n_cycles | 12.000 | 1.000 | 2.000 | 100.000 | 256.000 | 423.000 | 47.000 | 1.000 | 13.000 | 36.000 |

## Metrikler: regime_2022-01_end

| metrik | B_btc200 | B_btchold | B_btceth5050 | B_univew | T0 | XS_REV | XS_LOWVOL | VM_BTC | MR_BTC | RV_ETHBTC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 27.6% | 11.5% | 2.3% | -28.7% | -6.8% | 2.5% | 19.6% | 14.9% | -8.5% | -8.0% |
| annual_vol | 33.3% | 50.3% | 56.9% | 74.5% | 9.2% | 35.0% | 39.9% | 45.2% | 27.4% | 61.5% |
| sharpe | 0.778 | 0.389 | 0.254 | -0.130 | -1.146 | 0.130 | 0.547 | 0.445 | -0.329 | 0.107 |
| sortino | 1.232 | 0.570 | 0.368 | -0.179 | -1.431 | 0.190 | 0.805 | 0.652 | -0.443 | 0.156 |
| max_drawdown | -30.9% | -66.9% | -68.2% | -87.3% | -30.1% | -53.1% | -44.4% | -61.7% | -61.9% | -71.4% |
| avg_gross_exposure | 52.5% | 100.0% | 100.0% | 99.9% | 6.4% | 47.4% | 74.1% | 91.9% | 20.6% | 100.0% |
| turnover_annual | 681.7% | 0.0% | 50.2% | 526.6% | 284.5% | 4050.9% | 469.1% | 119.3% | 1215.0% | 3560.1% |
| cost_annual | 1.0% | 0.0% | 0.1% | 1.1% | 0.5% | 8.1% | 0.9% | 0.2% | 1.8% | 5.3% |
| n_cycles | 17.000 | 0.000 | 0.000 | 209.000 | 283.000 | 949.000 | 71.000 | 0.000 | 30.000 | 85.000 |

## Yıl yıl getiri

|  | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B_btc200 | -27.5% | 177.8% | -23.5% | 0.0% | 87.8% | 79.9% | -14.5% | 12.5% |
| B_btchold | -31.2% | 302.0% | 59.8% | -64.2% | 155.6% | 121.3% | -6.3% | -10.6% |
| B_btceth5050 | -43.7% | 398.4% | 205.2% | -65.1% | 122.1% | 81.7% | -4.9% | -16.8% |
| B_univew | -55.1% | 117.7% | 209.4% | -81.2% | 105.3% | 16.8% | -53.9% | -6.1% |
| T0 | -14.2% | 46.2% | 54.3% | -23.6% | -6.7% | 0.0% | 0.0% | 0.0% |
| XS_REV | -29.5% | 26.5% | 55.9% | -50.8% | 53.7% | 74.1% | -31.6% | 24.8% |
| XS_LOWVOL | -26.7% | 146.6% | 54.1% | -30.4% | 88.8% | 110.1% | -10.6% | -3.7% |
| VM_BTC | -23.3% | 154.3% | 31.3% | -59.9% | 142.3% | 132.7% | -2.6% | -11.3% |
| MR_BTC | 13.4% | -42.1% | 9.6% | -60.8% | 50.0% | 29.1% | 12.2% | -23.5% |
| RV_ETHBTC | -57.4% | 304.3% | 168.0% | -64.3% | 127.8% | 86.7% | -39.8% | -26.9% |

## XS_REV

| # | Kriter | Değer | Durum |
| --- | --- | --- | --- |
| 1 | BTC-200'ü yener (p < 0.010) | ΔSharpe -0.39, p = 0.8489 | **HAYIR** |
| 2 | DSR ≥ 0,95 | 0.078 | **HAYIR** |
| 3 | Tasarım ve bekletmede Sharpe > 0 (1× ve 2× maliyet) | 0.16 / 0.45; 2×: -0.03 / 0.22 | **HAYIR** |
| 4 | PBO < 0,5 | 0.241 | **evet** |
| 5 | Sıfır hipotezleri p < 0,05 | tarih_karistirma 0.761, rastgele_coin 0.673 | **HAYIR** |
| 6 | Kontroller beklendiği gibi | 2/4 | **HAYIR** |
| 7 | Komşularda Sharpe > 0 ve ≥ temelin %50'si | en düşük -0.15 | **HAYIR** |

Karar: **reddedildi**. Uydu kuralı: 0,5 × 0.27 = 0.135 vs ρ × SR_BTC200 = 0.349 (ρ = 0.53).

Komşular (tam dönem Sharpe): XS_REV 0.27, XS_REV_lookback3 0.17, XS_REV_lookback14 0.12, XS_REV_n_hold3 0.07, XS_REV_n_hold10 0.27, XS_REV_every3 -0.15, XS_REV_every14 0.29.

| Kontrol | Beklenen | Sonuç | Beklendiği gibi |
| --- | --- | --- | --- |
| Sinyal 365 gün gecikmeli | Sharpe ≤ temelin %50'i | 0.39 (temel 0.16) | **HAYIR** |
| Pozitif kontrol: 1 gün sızıntı | Sharpe ≥ temel + 1 | -0.49 (temel 0.16) | **HAYIR** |
| Ortalamadan arındırılmış karıştırma (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.20 (-0.63…0.27), yıllık -11.8% | **evet** |
| GARCH serileri (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.57 (-1.00…-0.20), yıllık -22.7% | **evet** |

Sıfır hipotezleri (tasarım, basit hesap Sharpe 0.15): tarih_karistirma: p = 0.761, sıfır ort. 0.30, %95 0.66; rastgele_coin: p = 0.673, sıfır ort. 0.23, %95 0.50.

## XS_LOWVOL

| # | Kriter | Değer | Durum |
| --- | --- | --- | --- |
| 1 | BTC-200'ü yener (p < 0.010) | ΔSharpe 0.10, p = 0.3731 | **HAYIR** |
| 2 | DSR ≥ 0,95 | 0.462 | **HAYIR** |
| 3 | Tasarım ve bekletmede Sharpe > 0 (1× ve 2× maliyet) | 0.85 / 0.61; 2×: 0.83 / 0.58 | **evet** |
| 4 | PBO < 0,5 | 0.741 | **HAYIR** |
| 5 | Sıfır hipotezleri p < 0,05 | tarih_karistirma 0.492, rastgele_coin 0.011 | **HAYIR** |
| 6 | Kontroller beklendiği gibi | 2/4 | **HAYIR** |
| 7 | Komşularda Sharpe > 0 ve ≥ temelin %50'si | en düşük 0.51 | **evet** |

Karar: **reddedildi**. Uydu kuralı: 0,5 × 0.76 = 0.379 vs ρ × SR_BTC200 = 0.398 (ρ = 0.61).

Komşular (tam dönem Sharpe): XS_LOWVOL 0.76, XS_LOWVOL_window30 0.71, XS_LOWVOL_window120 0.77, XS_LOWVOL_n_hold3 0.86, XS_LOWVOL_n_hold10 0.51.

| Kontrol | Beklenen | Sonuç | Beklendiği gibi |
| --- | --- | --- | --- |
| Sinyal 365 gün gecikmeli | Sharpe ≤ temelin %50'i | 0.67 (temel 0.85) | **HAYIR** |
| Pozitif kontrol: 1 gün sızıntı | Sharpe ≥ temel + 1 | 0.87 (temel 0.85) | **HAYIR** |
| Ortalamadan arındırılmış karıştırma (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.13 (-0.63…0.31), yıllık -12.5% | **evet** |
| GARCH serileri (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.43 (-1.31…0.14), yıllık -15.6% | **evet** |

Sıfır hipotezleri (tasarım, basit hesap Sharpe 0.84): tarih_karistirma: p = 0.492, sıfır ort. 0.84, %95 1.11; rastgele_coin: p = 0.011, sıfır ort. 0.49, %95 0.74.

## VM_BTC

| # | Kriter | Değer | Durum |
| --- | --- | --- | --- |
| 1 | BTC-200'ü yener (p < 0.010) | ΔSharpe -0.01, p = 0.5112 | **HAYIR** |
| 2 | DSR ≥ 0,95 | 0.343 | **HAYIR** |
| 3 | Tasarım ve bekletmede Sharpe > 0 (1× ve 2× maliyet) | 0.62 / 0.68; 2×: 0.62 / 0.68 | **evet** |
| 4 | PBO < 0,5 | 0.503 | **HAYIR** |
| 5 | Sıfır hipotezleri p < 0,05 | dairesel_kaydirma 0.847 | **HAYIR** |
| 6 | Kontroller beklendiği gibi | 1/4 | **HAYIR** |
| 7 | Komşularda Sharpe > 0 ve ≥ temelin %50'si | en düşük 0.59 | **evet** |

Karar: **reddedildi**. Uydu kuralı: 0,5 × 0.64 = 0.321 vs ρ × SR_BTC200 = 0.468 (ρ = 0.71).

Komşular (tam dönem Sharpe): VM_BTC 0.64, VM_BTC_sigma_target0.35 0.62, VM_BTC_sigma_target0.65 0.67, VM_BTC_window14 0.69, VM_BTC_window60 0.59.

| Kontrol | Beklenen | Sonuç | Beklendiği gibi |
| --- | --- | --- | --- |
| Sinyal 365 gün gecikmeli | Sharpe ≤ temelin %50'i | 0.81 (temel 0.62) | **HAYIR** |
| Pozitif kontrol: 1 gün sızıntı | Sharpe ≥ temel + 1 | 0.81 (temel 0.62) | **HAYIR** |
| Ortalamadan arındırılmış karıştırma (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. 0.07 (-0.43…0.49), yıllık -7.1% | **HAYIR** |
| GARCH serileri (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.26 (-1.37…0.35), yıllık -17.9% | **evet** |

Sıfır hipotezleri (tasarım, basit hesap Sharpe 0.61): dairesel_kaydirma: p = 0.847, sıfır ort. 0.73, %95 0.92.

## MR_BTC

| # | Kriter | Değer | Durum |
| --- | --- | --- | --- |
| 1 | BTC-200'ü yener (p < 0.010) | ΔSharpe -0.86, p = 0.9489 | **HAYIR** |
| 2 | DSR ≥ 0,95 | 0.003 | **HAYIR** |
| 3 | Tasarım ve bekletmede Sharpe > 0 (1× ve 2× maliyet) | -0.32 / 0.09; 2×: -0.36 / 0.01 | **HAYIR** |
| 4 | PBO < 0,5 | 0.925 | **HAYIR** |
| 5 | Sıfır hipotezleri p < 0,05 | dairesel_kaydirma 0.965 | **HAYIR** |
| 6 | Kontroller beklendiği gibi | 2/3 | **HAYIR** |
| 7 | Komşularda Sharpe > 0 ve ≥ temelin %50'si | en düşük 0.00 | **evet** |

Karar: **reddedildi**. Uydu kuralı: 0,5 × -0.20 = -0.101 vs ρ × SR_BTC200 = 0.125 (ρ = 0.19).

Komşular (tam dönem Sharpe): MR_BTC -0.20, MR_BTC_window10 0.02, MR_BTC_window40 0.02, MR_BTC_entry_z1.5 0.06, MR_BTC_entry_z2.5 0.00.

| Kontrol | Beklenen | Sonuç | Beklendiği gibi |
| --- | --- | --- | --- |
| Sinyal 365 gün gecikmeli | Sharpe ≤ temelin %50'i | 0.66 (temel -0.32) | uygulanamaz |
| Pozitif kontrol: 1 gün sızıntı | Sharpe ≥ temel + 1 | -1.65 (temel -0.32) | **HAYIR** |
| Ortalamadan arındırılmış karıştırma (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.09 (-0.58…0.62), yıllık -6.0% | **evet** |
| GARCH serileri (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.22 (-0.32…-0.12), yıllık -15.4% | **evet** |

Sıfır hipotezleri (tasarım, basit hesap Sharpe -0.37): dairesel_kaydirma: p = 0.965, sıfır ort. 0.27, %95 0.94.

## RV_ETHBTC

| # | Kriter | Değer | Durum |
| --- | --- | --- | --- |
| 1 | BTC-200'ü yener (p < 0.010) | ΔSharpe -0.12, p = 0.6530 | **HAYIR** |
| 2 | DSR ≥ 0,95 | 0.240 | **HAYIR** |
| 3 | Tasarım ve bekletmede Sharpe > 0 (1× ve 2× maliyet) | 0.75 / 0.12; 2×: 0.68 / 0.04 | **evet** |
| 4 | PBO < 0,5 | 0.441 | **evet** |
| 5 | Sıfır hipotezleri p < 0,05 | dairesel_kaydirma 0.774 | **HAYIR** |
| 6 | Kontroller beklendiği gibi | 2/4 | **HAYIR** |
| 7 | Komşularda Sharpe > 0 ve ≥ temelin %50'si | en düşük 0.51 | **evet** |

Karar: **reddedildi**. Uydu kuralı: 0,5 × 0.53 = 0.266 vs ρ × SR_BTC200 = 0.406 (ρ = 0.62).

Komşular (tam dönem Sharpe): RV_ETHBTC 0.53, RV_ETHBTC_window45 0.51, RV_ETHBTC_window180 0.61, RV_ETHBTC_z_band0.5 0.60, RV_ETHBTC_z_band1.5 0.61.

| Kontrol | Beklenen | Sonuç | Beklendiği gibi |
| --- | --- | --- | --- |
| Sinyal 365 gün gecikmeli | Sharpe ≤ temelin %50'i | 0.94 (temel 0.75) | **HAYIR** |
| Pozitif kontrol: 1 gün sızıntı | Sharpe ≥ temel + 1 | 0.10 (temel 0.75) | **HAYIR** |
| Ortalamadan arındırılmış karıştırma (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.04 (-0.37…0.26), yıllık -24.8% | **evet** |
| GARCH serileri (5 tohum) | yıllık getiri < 0 ve Sharpe ≤ 0 | Sharpe ort. -0.09 (-0.57…0.25), yıllık -27.8% | **evet** |

Sıfır hipotezleri (tasarım, basit hesap Sharpe 0.70): dairesel_kaydirma: p = 0.774, sıfır ort. 0.81, %95 1.02.

