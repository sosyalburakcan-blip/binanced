# Araştırma v4 — gün içi momentum (spot ve kaldıraçlı vadeli)

Tasarım 2019-07-01 – 2023-12-31, kirlenmiş bekletme 2024-01-01 – 2026-11-01. Ön kayıt `PREREGISTRATION_v4.md` (tag `prereg-v4`). 648 yapılandırma × 5 piyasa/kaldıraç; komisyon, kayma ve vergi dahil, nakit %0.

Toplu çalıştırma: 2026-11-03 19:46:06 → 2026-11-03 20:11:31 UTC, 5596 çalıştırma, commit `50d4a50` (`lock/V4_run.json`).

## Sonuç

En iyi yapılandırma (tasarımda seçildi): `L6_z2_k6_tp4_sl4_h72` → **reddedildi**.

| # | Kriter | Değer | Durum |
| --- | --- | --- | --- |
| 1 | Bekletmede net Sharpe > 0 (1× ve 2× maliyet) | -0.57 / -1.03 | **HAYIR** |
| 2 | Tam dönemde BTC-200'ü yener (p < 0,05) | ΔSharpe -0.38, p = 0.7738 | **HAYIR** |
| 3 | DSR ≥ 0,95 | 0.000 (N = 3324) | **HAYIR** |
| 4 | PBO < 0,5 (648 yapılandırma, tasarım) | 0.000 | **evet** |
| 5 | Rastgele giriş sıfırı p < 0,05 (tasarım) | p = 0.010 | **evet** |
| 6 | Gerçek ızgaranın en iyisi rastgele ızgaraların en iyisini geçer (tasarım) | 0.80 vs -0.49, -0.43 | **evet** |
| 7 | Pozitif kontrol: 1 saat sızıntı Sharpe ≥ temel + 1 | 1.43 (temel 0.80) | **HAYIR** |
| 8 | Komşular (tasarım) Sharpe > 0 | en düşük -0.90 | **HAYIR** |

## Izgaranın tamamı (spot, 1×)

| Dönem | medyan Sharpe | %90 | en iyi | Sharpe > 0 olan pay |
| --- | --- | --- | --- | --- |
| design | -3.40 | -0.87 | 0.80 | %2 |
| holdout | -3.06 | -1.09 | -0.13 | %0 |
| full | -3.20 | -1.01 | 0.28 | %1 |

Tasarım ve bekletme Sharpe'larının sıra korelasyonu (Spearman): 0.92 (tasarımda iyi olan bekletmede de iyi mi?).

## En iyi liste (tasarım dönemi net Sharpe'ına göre)

| sıra | yapılandırma | tasarım_sharpe | bekletme_sharpe | tam_sharpe | tasarım_yıllık | bekletme_yıllık | tam_1000 | tam_mdd | işlem | kazanma | ort_işlem |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | L6_z2_k6_tp4_sl4_h72 | 0.80 | -0.57 | 0.28 | 13.5% | -5.0% | 1,531 | -34.4% | 749 | 56.1% | 0.2% |
| 2 | L6_z2_k3_tp4_sl4_h72 | 0.57 | -0.83 | 0.02 | 14.0% | -18.7% | 1,005 | -63.1% | 1968 | 53.0% | 0.0% |
| 3 | L6_z2_k6_tp4_sl4_h24 | 0.52 | -0.61 | 0.10 | 8.3% | -4.2% | 1,268 | -34.0% | 764 | 51.3% | 0.1% |
| 4 | L6_z1.5_k6_tp4_sl4_h72 | 0.49 | -0.78 | -0.03 | 10.3% | -14.5% | 998 | -55.7% | 1494 | 53.4% | 0.0% |
| 5 | L12_z2_k6_tp4_sl4_h72 | 0.43 | -0.25 | 0.16 | 8.6% | -2.4% | 1,353 | -36.6% | 1151 | 54.1% | 0.1% |
| 6 | L3_z1.5_k6_tp4_sl4_h72 | 0.38 | -0.29 | 0.12 | 4.4% | 2.0% | 1,283 | -8.3% | 216 | 56.5% | 0.4% |
| 7 | L12_z1.5_k6_tp4_sl4_h72 | 0.28 | -0.68 | -0.10 | 6.1% | -16.3% | 786 | -64.3% | 2093 | 52.7% | 0.0% |
| 8 | L6_z2_k6_tp2_sl4_h72 | 0.25 | -0.43 | -0.02 | 4.0% | -0.9% | 1,164 | -27.1% | 840 | 70.4% | 0.1% |
| 9 | L6_z2_k3_tp4_sl4_h24 | 0.23 | -1.30 | -0.36 | 4.7% | -24.0% | 564 | -73.3% | 2049 | 49.8% | -0.1% |
| 10 | L12_z2_k6_tp4_sl4_h24 | 0.21 | -0.31 | 0.02 | 4.1% | -2.3% | 1,123 | -39.4% | 1170 | 51.3% | 0.1% |
| 11 | L6_z1.5_k6_tp4_sl4_h24 | 0.16 | -1.09 | -0.33 | 3.2% | -17.5% | 670 | -67.9% | 1547 | — | — |
| 12 | L6_z2_k3_tp2_sl4_h72 | 0.11 | -0.37 | -0.08 | 2.1% | -4.7% | 958 | -48.7% | 2489 | — | — |
| 13 | L12_z1.5_k6_tp4_sl4_h24 | 0.05 | -1.19 | -0.44 | 0.2% | -24.5% | 454 | -74.4% | 2189 | — | — |
| 14 | L6_z2_k6_tp4_sl2_h72 | 0.01 | -1.05 | -0.39 | 1.4% | -7.3% | 857 | -34.7% | 807 | — | — |
| 15 | L6_z2_k6_tp2_sl4_h24 | -0.00 | -0.37 | -0.15 | 1.4% | 0.0% | 1,064 | -25.4% | 842 | — | — |
| 16 | L3_z1.5_k6_tp4_sl4_h24 | -0.03 | -0.49 | -0.21 | 1.4% | 0.9% | 1,093 | -11.4% | 216 | — | — |
| 17 | L6_z1_k6_tp4_sl4_h72 | -0.08 | -0.99 | -0.43 | -5.3% | -26.8% | 324 | -81.7% | 2853 | — | — |
| 18 | L6_z1.5_k6_tp2_sl4_h72 | -0.15 | -1.42 | -0.68 | -1.6% | -19.4% | 505 | -65.8% | 1743 | — | — |
| 19 | L12_z2_k3_tp4_sl4_h72 | -0.19 | -0.40 | -0.27 | -5.6% | -8.7% | 594 | -73.8% | 1975 | — | — |
| 20 | L6_z2_k3_tp2_sl4_h24 | -0.20 | -0.70 | -0.40 | -3.0% | -9.9% | 648 | -56.4% | 2516 | — | — |

`tam_1000`: tam dönemde 1.000 $'ın vardığı değer; `kazanma` ve `ort_işlem` (marjine göre net işlem getirisi) yalnızca en iyi 10 için.

## Kaldıraç ve spot farkı (en iyi 10 yapılandırmanın ortalaması, tam dönem)

|  | spot | fut1x | fut2x | fut3x | fut5x |
| --- | --- | --- | --- | --- | --- |
| top_sharpe_mean | 0.020 | 0.374 | 0.463 | 0.491 | 0.508 |
| top_annual_mean | 1.0% | 7.9% | 12.5% | 13.2% | 4.6% |
| top_mdd_mean | -43.6% | -33.6% | -55.6% | -69.9% | -86.2% |
| grid_sharpe_median | -3.204 | -1.980 | -1.822 | -1.687 | -1.480 |
| grid_frac_pos | 0.9% | 3.7% | 5.2% | 6.3% | 6.6% |
| liquidations | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## Maliyet ve vergi duyarlılığı (en iyi 10, tam dönemde 1.000 $ →)

Türkiye'de kripto için yürürlükte işlem vergisi veya stopaj yok (2026'da önerildi, Mart'ta Meclis'te çıkarıldı); kazancın gelir vergisindeki niteliği belirsiz. Yıllık kazanç vergisi senaryoları USD üzerinden, zarar devri olmadan hesaplandı (reports/V4_fees_tax.md).

|  | temel | BNB indirimi | işlem vergisi %0,03 | 2× maliyet | yıllık kazanç vergisi %15 | yıllık kazanç vergisi %27 | yıllık kazanç vergisi %40 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L6_z2_k6_tp4_sl4_h72 | 1,531 | 1,735 | 1,318 | 929 | 1,377 | 1,263 | 1,147 |
| L6_z2_k3_tp4_sl4_h72 | 1,005 | 1,395 | 678 | 271 | 926 | 864 | 798 |
| L6_z2_k6_tp4_sl4_h24 | 1,268 | 1,440 | 1,088 | 761 | 1,181 | 1,115 | 1,047 |
| L6_z1.5_k6_tp4_sl4_h72 | 998 | 1,280 | 740 | 369 | 916 | 854 | 789 |
| L12_z2_k6_tp4_sl4_h72 | 1,353 | 1,639 | 1,075 | 628 | 1,245 | 1,162 | 1,076 |
| L3_z1.5_k6_tp4_sl4_h72 | 1,283 | 1,330 | 1,229 | 1,111 | 1,231 | 1,191 | 1,148 |
| L12_z1.5_k6_tp4_sl4_h72 | 786 | 1,114 | 518 | 195 | 738 | 700 | 659 |
| L6_z2_k6_tp2_sl4_h72 | 1,164 | 1,339 | 984 | 665 | 1,083 | 1,022 | 958 |
| L6_z2_k3_tp4_sl4_h24 | 564 | 794 | 375 | 144 | 528 | 500 | 471 |
| L12_z2_k6_tp4_sl4_h24 | 1,123 | 1,365 | 889 | 515 | 1,053 | 999 | 943 |

## Kontroller ve sıfırlar (en iyi yapılandırma, tasarım)

- 1 saat gecikme Sharpe 0.76; 1 saat sızıntı 1.43; 2× maliyet 0.34 (bekletmede -1.03).
- Rastgele giriş (aynı kâr al/zarar kes/süre, aynı giriş sıklığı, 100 tekrar): ortalama Sharpe -0.99, %95 -0.39; gözlenen 0.80, p = 0.010.
- Rastgele sinyalli ızgaralar: en iyi tasarım -0.49 → bekletmede -1.17 (medyan -3.74); en iyi tasarım -0.43 → bekletmede -2.15 (medyan -3.69).
- Komşular: L3_z2_k6_tp4_sl4_h72 -0.90, L12_z2_k6_tp4_sl4_h72 0.43, L6_z1.5_k6_tp4_sl4_h72 0.49, L6_z2_k3_tp4_sl4_h72 0.57, L6_z2_k6_tp2_sl4_h72 0.25, L6_z2_k6_tp4_sl2_h72 0.01, L6_z2_k6_tp4_sl4_h24 0.52.

