# G10 — Geliştirme dönemi değerlendirmesi

Aşama: geliştirme (2019-07-01 – 2023-12-31); veri sonu 2023-12-31; doğrulama dönemi yüklenmedi. Kod `8d2f770`, ön kayıt `prereg-v1`. Nakit getirisi temel varsayım %0; Sharpe ABD 3 aylık hazine bonosu üzerinden, √365.

> Birincil hipotez, DSR ve geç/kal kararları **tam dönemde** (kilitten sonra, G12) verilir. Bu rapordaki testler yalnızca geliştirme dönemidir ve ön bilgi niteliğindedir.

## Metrikler: T0 ve kıyaslar

B_btc200 birincil kıyas; B_btceth200 BTC/ETH eşit ağırlık (kendi SMA200'leri); B_btchold BTC al-tut; B_btcvol T0'ın gerçekleşen oynaklığına ölçekli BTC al-tut (dönem sonu bilgisiyle ölçeklendi); B_btc5050 %50 BTC + %50 nakit; B_univew evrenin eşit ağırlıklı al-tutu (aylık); B_trendew aynı trend sinyali, oynaklık ayarsız eşit ağırlık.

### development

| metrik | T0 | B_btc200 | B_btceth200 | B_btchold | B_btcvol | B_btc5050 | B_univew | B_trendew |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 7.4% | 26.6% | 45.9% | 36.3% | 14.4% | 23.3% | 3.5% | 32.4% |
| annual_vol | 19.5% | 47.7% | 53.9% | 67.8% | 19.4% | 33.7% | 88.9% | 50.2% |
| vol_minus_target | -15.5% | 12.7% | 18.9% | 32.8% | -15.6% | -1.3% | 53.9% | 15.2% |
| avg_gross_exposure | 18.4% | 56.8% | 58.8% | 99.9% | 29.0% | 50.3% | 99.9% | 43.9% |
| avg_cash_share | 81.6% | 43.2% | 41.2% | 0.1% | 71.0% | 49.7% | 0.1% | 56.1% |
| sharpe | 0.368 | 0.693 | 0.941 | 0.777 | 0.693 | 0.737 | 0.479 | 0.778 |
| sortino | 0.506 | 1.025 | 1.330 | 1.122 | 1.001 | 1.064 | 0.652 | 1.086 |
| calmar | 0.207 | 0.401 | 0.785 | 0.474 | 0.463 | 0.478 | 0.038 | 0.465 |
| max_drawdown | -35.7% | -66.2% | -58.5% | -76.6% | -31.1% | -48.8% | -90.9% | -69.6% |
| mdd_peak | 2021-05-09 | 2021-04-13 | 2019-07-09 | 2021-11-08 | 2021-11-08 | 2021-11-08 | 2021-05-09 | 2021-05-09 |
| mdd_trough | 2023-08-25 | 2023-03-10 | 2020-05-11 | 2022-11-21 | 2022-11-21 | 2022-11-21 | 2023-09-11 | 2023-10-12 |
| mdd_duration_days | 966 | 992 | 499 | 783 | 783 | 783 | 966 | 966 |
| longest_underwater_days | 966 | 992 | 964 | 783 | 783 | 783 | 966 | 966 |
| time_under_water_frac | 96.5% | 97.6% | 96.8% | 96.7% | 96.2% | 96.4% | 97.4% | 96.4% |
| skewness | -0.575 | 0.171 | -0.714 | -0.608 | -0.509 | -0.556 | -0.852 | -0.886 |
| turnover_annual | 634.8% | 730.5% | 676.4% | 22.2% | 44.1% | 56.5% | 589.9% | 1292.0% |
| cost_annual | 1.3% | 1.1% | 1.0% | 0.0% | 0.1% | 0.1% | 1.3% | 2.7% |
| n_cycles | 552 | 17 | 31 | 1 | 1 | 1 | 193 | 608 |
| win_rate | 23.6% | 17.6% | 25.8% | 100.0% | 100.0% | 100.0% | 43.5% | 24.2% |
| avg_win | 125.370 | 11029.790 | 7641.869 | 30437.819 | 8322.626 | 15734.787 | 496.571 | 504.786 |
| avg_loss | -29.645 | -1013.305 | -704.415 |  |  |  | -367.469 | -105.836 |
| top10pct_profit_share | 373.1% | 151.8% | 105.5% | 100.0% | 100.0% | 100.0% | 1924.9% | 252.0% |
| n_profitable_coins | 29 | 1 | 2 | 1 | 1 | 1 | 39 | 37 |
| n_coins_traded | 84 | 1 | 2 | 1 | 1 | 1 | 97 | 94 |
| worst_1d_at_max_exposure | -46.0% | -14.4% | -44.6% | -39.5% | -39.5% | -39.5% | -42.9% | -46.8% |
| worst_3d_at_max_exposure | -49.4% | -21.0% | -46.8% | -39.5% | -39.5% | -39.5% | -44.8% | -50.5% |

### regime_2019-07_2021-11

| metrik | T0 | B_btc200 | B_btceth200 | B_btchold | B_btcvol | B_btc5050 | B_univew | B_trendew |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 30.8% | 33.8% | 87.2% | 101.3% | 29.2% | 51.5% | 68.9% | 84.0% |
| annual_vol | 22.9% | 58.4% | 67.7% | 76.9% | 22.3% | 38.5% | 97.6% | 61.5% |
| vol_minus_target | -12.1% | 23.4% | 32.7% | 41.9% | -12.7% | 3.5% | 62.6% | 26.5% |
| avg_gross_exposure | 20.8% | 70.0% | 73.2% | 99.8% | 29.6% | 50.9% | 99.8% | 50.9% |
| avg_cash_share | 79.2% | 30.0% | 26.8% | 0.2% | 70.4% | 49.1% | 0.2% | 49.1% |
| sharpe | 1.267 | 0.782 | 1.264 | 1.301 | 1.237 | 1.261 | 1.045 | 1.298 |
| sortino | 1.800 | 1.141 | 1.772 | 1.902 | 1.803 | 1.839 | 1.433 | 1.825 |
| calmar | 1.785 | 0.548 | 1.490 | 1.645 | 1.412 | 1.495 | 0.984 | 1.968 |
| max_drawdown | -17.3% | -61.7% | -58.5% | -61.6% | -20.7% | -34.5% | -70.0% | -42.7% |
| mdd_peak | 2020-02-14 | 2021-04-13 | 2019-07-09 | 2019-07-09 | 2019-07-09 | 2019-07-09 | 2019-07-08 | 2021-05-09 |
| mdd_trough | 2020-04-20 | 2021-10-02 | 2020-05-11 | 2020-03-12 | 2020-03-12 | 2020-03-12 | 2020-03-12 | 2021-08-03 |
| mdd_duration_days | 168 | 231 | 499 | 469 | 385 | 388 | 504 | 205 |
| longest_underwater_days | 214 | 496 | 499 | 469 | 385 | 388 | 504 | 212 |
| time_under_water_frac | 93.6% | 95.5% | 94.0% | 93.8% | 92.9% | 93.2% | 95.2% | 93.2% |
| skewness | -0.491 | 0.030 | -0.760 | -0.782 | -0.669 | -0.726 | -1.040 | -0.895 |
| turnover_annual | 586.6% | 947.1% | 885.0% | 41.3% | 53.9% | 70.5% | 630.8% | 1289.8% |
| cost_annual | 1.3% | 1.4% | 1.3% | 0.1% | 0.1% | 0.1% | 1.5% | 2.8% |
| n_cycles | 256 | 12 | 22 | 1 | 1 | 1 | 100 | 257 |
| win_rate | 32.8% | 8.3% | 18.2% | 100.0% | 100.0% | 100.0% | 53.0% | 31.9% |
| avg_win | 169.153 | 19237.038 | 9526.540 | 30437.819 | 8322.626 | 15734.787 | 677.135 | 639.584 |
| avg_loss | -29.894 | -1148.035 | -748.271 |  |  |  | -502.047 | -115.368 |
| top10pct_profit_share | 114.9% | 286.1% | 154.7% | 100.0% | 100.0% | 100.0% | 198.1% | 127.4% |
| n_profitable_coins | 33 | 1 | 1 | 1 | 1 | 1 | 29 | 31 |
| n_coins_traded | 52 | 1 | 2 | 1 | 1 | 1 | 52 | 52 |
| worst_1d_at_max_exposure | -46.0% | -14.4% | -44.6% | -39.5% | -39.5% | -39.5% | -42.9% | -46.8% |
| worst_3d_at_max_exposure | -49.4% | -21.0% | -46.8% | -39.5% | -39.5% | -39.5% | -44.8% | -50.5% |

### regime_2022-01_end

| metrik | T0 | B_btc200 | B_btceth200 | B_btchold | B_btcvol | B_btc5050 | B_univew | B_trendew |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | -15.6% | 37.0% | 24.4% | -4.3% | 2.1% | 1.9% | -37.9% | -9.1% |
| annual_vol | 14.3% | 29.1% | 28.7% | 55.0% | 15.4% | 26.9% | 77.2% | 32.6% |
| vol_minus_target | -20.7% | -5.9% | -6.3% | 20.0% | -19.6% | -8.1% | 42.2% | -2.4% |
| avg_gross_exposure | 15.5% | 40.1% | 40.1% | 100.0% | 28.5% | 49.7% | 99.9% | 36.0% |
| avg_cash_share | 84.5% | 59.9% | 59.9% | 0.0% | 71.5% | 50.3% | 0.1% | 64.0% |
| sharpe | -1.359 | 1.105 | 0.781 | 0.131 | -0.019 | 0.073 | -0.271 | -0.235 |
| sortino | -1.696 | 1.891 | 1.235 | 0.186 | -0.027 | 0.105 | -0.364 | -0.318 |
| calmar | -0.518 | 1.962 | 1.246 | -0.065 | 0.085 | 0.048 | -0.452 | -0.162 |
| max_drawdown | -30.1% | -18.9% | -19.6% | -66.9% | -24.4% | -39.6% | -83.8% | -55.9% |
| mdd_peak | 2022-01-03 | 2023-02-20 | 2023-04-16 | 2022-01-01 | 2022-03-29 | 2022-03-29 | 2022-01-03 | 2022-01-03 |
| mdd_trough | 2023-08-25 | 2023-03-10 | 2023-06-14 | 2022-11-21 | 2022-11-21 | 2022-11-21 | 2023-09-11 | 2023-10-12 |
| mdd_duration_days | 727 | 23 | 206 | 729 | 611 | 614 | 727 | 727 |
| longest_underwater_days | 727 | 103 | 382 | 729 | 611 | 614 | 727 | 727 |
| time_under_water_frac | 99.7% | 42.6% | 95.8% | 99.9% | 98.8% | 99.2% | 99.7% | 99.7% |
| skewness | -1.242 | 1.628 | 0.870 | -0.093 | 0.012 | -0.019 | -0.454 | -0.611 |
| turnover_annual | 688.4% | 249.4% | 327.0% | 0.0% | 33.3% | 40.9% | 534.4% | 1302.7% |
| cost_annual | 1.3% | 0.4% | 0.5% | 0.0% | 0.0% | 0.1% | 1.2% | 2.6% |
| n_cycles | 283 | 3 | 7 | 0 | 0 | 0 | 88 | 338 |
| win_rate | 16.3% | 66.7% | 57.1% |  |  |  | 35.2% | 19.2% |
| avg_win | 45.419 | 6926.166 | 5757.199 |  |  |  | 187.864 | 334.734 |
| avg_loss | -29.717 | -338.673 | -452.431 |  |  |  | -209.250 | -97.387 |
| top10pct_profit_share |  | 70.0% | 42.9% |  |  |  |  |  |
| n_profitable_coins | 3 | 1 | 2 | 0 | 0 | 0 | 17 | 16 |
| n_coins_traded | 55 | 1 | 2 | 0 | 0 | 0 | 62 | 65 |
| worst_1d_at_max_exposure | -21.7% | -7.3% | -7.2% | -15.4% | -15.4% | -15.4% | -23.7% | -22.2% |
| worst_3d_at_max_exposure | -31.9% | -10.3% | -15.5% | -23.8% | -23.8% | -23.8% | -35.7% | -33.0% |

## T0 yıl yıl getiri ve maliyet

|  | 2019 | 2020 | 2021 | 2022 | 2023 |
| --- | --- | --- | --- | --- | --- |
| return | -14.2% | 46.2% | 54.3% | -23.6% | -6.7% |
| n_days | 184.000 | 366.000 | 365.000 | 365.000 | 365.000 |
| turnover | 247.0% | 743.6% | 493.8% | 731.2% | 645.5% |
| cost | 0.5% | 1.8% | 0.9% | 1.3% | 1.3% |

BTC-200:

|  | 2019 | 2020 | 2021 | 2022 | 2023 |
| --- | --- | --- | --- | --- | --- |
| return | -27.5% | 177.8% | -23.5% | 0.0% | 87.8% |
| n_days | 184.000 | 366.000 | 365.000 | 365.000 | 365.000 |
| turnover | 399.2% | 499.2% | 1895.2% | 0.0% | 498.8% |
| cost | 0.6% | 0.7% | 2.8% | 0.0% | 0.7% |

## T0 tutma süreleri (gün)

|  | n | p10 | median | p90 |
| --- | --- | --- | --- | --- |
| winners | 130.0 | 23.8 | 55.0 | 145.1 |
| losers | 422.0 | 1.0 | 8.0 | 37.0 |
| all | 552.0 | 2.0 | 15.0 | 62.0 |

## Maksimum maruziyette en kötü 1 ve 3 günlük kayıplar (T0)

| window_days | rank | start | end | loss_at_max_exposure | actual_return | avg_exposure |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 2020-03-12 | 2020-03-12 | -0.4604 | -0.0394 | 0.0856 |
| 1 | 2 | 2021-05-19 | 2021-05-19 | -0.3445 | -0.0619 | 0.1797 |
| 1 | 3 | 2021-06-21 | 2021-06-21 | -0.2392 | -0.0236 | 0.0985 |
| 1 | 4 | 2022-11-09 | 2022-11-09 | -0.2165 | -0.0320 | 0.1477 |
| 1 | 5 | 2019-09-24 | 2019-09-24 | -0.1804 | -0.0121 | 0.0670 |
| 3 | 1 | 2020-03-10 | 2020-03-12 | -0.4940 | -0.0449 | 0.0887 |
| 3 | 2 | 2021-05-17 | 2021-05-19 | -0.3551 | -0.0662 | 0.1867 |
| 3 | 3 | 2022-11-07 | 2022-11-09 | -0.3190 | -0.0875 | 0.3474 |
| 3 | 4 | 2022-01-20 | 2022-01-22 | -0.2638 | -0.0296 | 0.1146 |
| 3 | 5 | 2021-06-19 | 2021-06-21 | -0.2492 | -0.0242 | 0.0678 |

Kayan 12 aylık Sharpe (T0): en düşük -2.25, medyan -0.09, en yüksek 3.19.

## Nakit getirisi duyarlılığı ve sabit tutarlı sonuç

| metrik | T0 | T0_cash_m15 | T0_cash_tb | B_btc200 | B_btc200_cash_m15 | B_btc200_cash_tb | T0_fixed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| annual_return | 7.4% | 9.5% | 18.8% | 26.6% | 27.0% | 27.6% | 14.3% |
| annual_return_simple | 9.0% | 11.0% | 19.4% | 34.9% | 35.3% | 35.7% | 14.6% |
| sharpe | 0.368 | 0.465 | 0.838 | 0.693 | 0.701 | 0.710 | 0.805 |
| max_drawdown | -35.7% | -35.4% | -34.3% | -66.2% | -65.8% | -65.4% | -23.5% |
| avg_cash_share | 81.6% | 80.8% | 78.1% | 43.2% | 43.2% | 43.2% | 83.7% |
| cash_drag_annual | 1.5% | 1.5% | 1.4% | 0.8% | 0.8% | 0.8% | 1.5% |

## Dolar cinsinden (USDT/USD vekili: USDCUSDT'nin tersi)

|  | T0 | B_btc200 |
| --- | --- | --- |
| annual_return_usd | 7.5% | 26.7% |
| sharpe_usd | 0.370 | 0.695 |
| usdt_usd_min | 99.4% | 99.4% |
| usdt_usd_max | 104.3% | 104.3% |

## Regresyon (HAC)

T0 aşırı getirisi ~ BTC + evren eşit ağırlıklı:

|  | katsayı | t |
| --- | --- | --- |
| const | 0.000 | 0.089 |
| btc | -0.019 | -1.215 |
| ew_universe | 0.180 | 11.030 |

Yıllık alfa 0.5%, R² 0.59. Yükselen/düşen piyasa betası (BTC): β⁺ 0.13, β⁻ 0.22, eşitlik Wald p = 0.009.

## Yatırımcı çıtaları

- ABD 3 aylık hazine bonosu, geliştirme dönemi ortalaması: yıllık 1.86%.
- Stopaj sonrası TL mevduatı: geçmiş seri indirilmedi (TCMB EVDS gerekir). SPEC'teki 2026 değeri (yaklaşık %35,5 TL, dolar cinsinden kabaca +%13) yalnızca bugünkü fırsat maliyetini gösterir.

## Sıfır hipotezleri (Sharpe, basitleştirilmiş getiri)

Gözlenen (aynı basit hesap, maliyet oranı 0.20% ciro): Sharpe 0.37, en büyük düşüş -37.3%.

| Sıfır | çalıştırma | sıfır ort. Sharpe | sıfır %95 | p (Sharpe) | %95'te geçer | MDD yüzdelik sırası | sıfır medyan MDD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| a_tarih_karistirma | 1000 | 0.54 | 0.79 | 0.8501 | **HAYIR** | 0.01 | -26.9% |
| b_rastgele_coin | 1000 | 0.09 | 0.22 | 0.0010 | **evet** | 0.99 | -44.1% |

## Negatif ve pozitif kontroller

Eşikler sonuçlardan önce experiments.md satır 10'a yazıldı.

| Kontrol | Beklenen | Sonuç | Beklendiği gibi |
| --- | --- | --- | --- |
| Getiriler tarihe göre birlikte karıştırıldı (5 tohum) | Avantaj kaybolur (maliyet kadar zarar) | Sharpe ort. 0.57 (aralık -0.05…1.12), yıllık getiri ort. 14.0%, yıllık maliyet ort. 1.6%; kıyas T3 Sharpe 0.39 | **HAYIR** |
| Oynaklığı eşleştirilmiş GARCH serileri (5 tohum) | Avantaj kaybolur (maliyet kadar zarar) | Sharpe ort. -0.52 (aralık -0.72…-0.23), yıllık getiri ort. -6.0%, yıllık maliyet ort. 2.0%; kıyas T3 Sharpe 0.39 | **evet** |
| Bir coinin sinyali başka coinin getirisine | Avantaj büyük ölçüde kaybolur | 200 eşleme medyan Sharpe 0.11 (gözlenen, basit hesap 0.37) | **evet** |
| Sinyal 365 gün gecikmeli | Avantaj kaybolur | Sharpe 0.06 (T0 0.37) | **evet** |
| Orijinal − ters sinyal | Anlamlı ölçüde sıfırın üzerinde | ΔSharpe 0.60, %95 GA -0.41…1.48, p = 0.1257 (ters sinyal Sharpe -0.23) | **HAYIR** |
| Kararlar 1 gün gecikmeli (sinyal gecikmesi) | Biraz bozulur, çökmez | Sharpe 0.43 (T0 0.37) | **evet** |
| Kararlar 3 gün gecikmeli (sinyal gecikmesi) | Biraz bozulur, çökmez | Sharpe 0.34 (T0 0.37) | **evet** |
| Mum zamanlaması değişir (T8, 5 saat + 6 giriş günü) | Benzer sonuç | Sharpe aralığı 0.30…0.95 (T0 0.37) | **evet** |
| Bir yıl çıkarılır | Sonuç tek bir yıla bağlı olmamalı | Sharpe: 2019: 0.59, 2020: -0.13, 2021: -0.24, 2022: 0.82, 2023: 0.60 | **HAYIR** |
| En iyi 5 döngü çıkarılır | Sıfıra yakın veya pozitif | Sharpe (basit hesap) 0.07, tüm döngülerle 0.37 | **evet** |
| Pozitif kontrol: sinyale 1 gün sızıntı | Sharpe belirgin yükselir (yakalanmalı) | Sharpe 2.25 (T0 0.37) | **evet** |

GARCH kontrolünün ilk kurulumunda simüle edilen log getirinin ortalaması sıfırdı; bu, coin başına σ²/2 kadar pozitif aritmetik kayma (günlük %5 oynaklıkta yılda yaklaşık %50) taşıyordu ve kontrolü geçersiz kılıyordu. Tablodaki satır düzeltilmiş kurulumdur (basit getirinin beklentisi sıfır); ilk sonuç ve düzeltme experiments.md'de.

## Ön kayıt dışı tanılar (seçim için kullanılmaz; experiments.md'ye yazıldı, N'ye eklendi)

**Ortalamadan arındırılmış karıştırma** (her coinin basit getirisi kendi ortalamasından arındırılıp aynı şekilde karıştırıldı, 5 tohum): Sharpe ort. -0.35 (aralık -0.62…0.04), yıllık getiri ort. -4.5%, yıllık maliyet ort. 1.3%. SPEC'in karıştırma kontrolü coinlerin dönem boyunca toplam kaymasını korur; uzun pozisyonlu bir sistem bu kaymadan zamanlama becerisi olmadan da kazanır. Kayma kaldırılınca kalan sonuç zamanlama ve geleceği görme için temiz bir sıfırdır.

**−%35 sert sınır ve nakitte kilitlenme.** Sert sınır yeni alımları durdurur ve portföy zirvenin −%25'ine dönünce kalkar. Pozisyonlar sinyalle kapandıktan sonra nakit %0 getirdiği için portföy toparlanamaz ve durdurma dönem sonuna kadar sürer. Çalıştırmaların durdurma geçmişi:

|  | stop_days | first_stop | stopped_at_end | max_drawdown |
| --- | --- | --- | --- | --- |
| T0 | 137 | 2023-08-17 | True | -0.357 |
| G_vol45 | 418 | 2022-11-09 | True | -0.359 |
| G_span0.8 | 81 | 2023-10-12 | True | -0.352 |
| G_span1.2 | 205 | 2023-06-10 | True | -0.353 |
| G_univ30 | 205 | 2023-06-10 | True | -0.355 |
| G_univ50 | 112 | 2023-09-11 | True | -0.356 |
| G_drift15 | 137 | 2023-08-17 | True | -0.354 |
| G_drift35 | 137 | 2023-08-17 | True | -0.360 |
| G_h0 | 81 | 2023-10-12 | True | -0.350 |
| G_h1 | 137 | 2023-08-17 | True | -0.359 |
| T3 | 138 | 2023-08-16 | True | -0.366 |
| T4_0607 | 112 | 2023-09-11 | True | -0.354 |
| T4_1415 | 114 | 2023-09-09 | True | -0.358 |
| T5_20 | 137 | 2023-08-17 | True | -0.357 |
| T5_50 | 137 | 2023-08-17 | True | -0.357 |
| T6_cost2 | 187 | 2023-06-28 | True | -0.357 |
| T6_loss20 | 419 | 2022-11-08 | True | -0.439 |
| T6_loss50 | 419 | 2022-11-08 | True | -0.650 |
| T7 | 137 | 2023-08-17 | True | -0.357 |
| T8_h20 | 113 | 2023-09-10 | True | -0.352 |
| T8_wd0 | 205 | 2023-06-10 | True | -0.356 |
| T8_wd1 | 201 | 2023-06-14 | True | -0.350 |
| T8_wd2 | 137 | 2023-08-17 | True | -0.358 |
| T8_wd3 | 137 | 2023-08-17 | True | -0.361 |
| T8_wd4 | 205 | 2023-06-10 | True | -0.354 |
| T8_wd5 | 235 | 2023-05-11 | True | -0.352 |
| T9 | 418 | 2022-11-09 | True | -0.369 |
| T0_cash_m15 | 112 | 2023-09-11 | True | -0.354 |
| C_lag1 | 137 | 2023-08-17 | True | -0.360 |
| C_lag3 | 137 | 2023-08-17 | True | -0.371 |
| C_lag365 | 599 | 2022-05-12 | True | -0.355 |
| C_shuffle2 | 841 | 2021-09-12 | True | -0.355 |
| C_garch0 | 415 | 2022-11-12 | True | -0.357 |
| C_garch1 | 252 | 2023-04-24 | True | -0.364 |
| C_garch2 | 135 | 2023-08-19 | True | -0.375 |
| C_garch3 | 393 | 2022-12-04 | True | -0.356 |
| C_garch4 | 402 | 2022-11-25 | True | -0.363 |
| D_shuffledm0 | 871 | 2021-08-13 | True | -0.360 |
| D_shuffledm1 | 961 | 2021-05-15 | True | -0.361 |
| D_shuffledm2 | 23 | 2023-12-09 | True | -0.353 |
| D_shuffledm3 | 59 | 2023-11-03 | True | -0.365 |
| D_shuffledm4 | 454 | 2022-10-04 | True | -0.356 |

T0 ile aynı ayar, sert sınır kapalı (tanı):

| metrik | T0 | D_T0_nostop |
| --- | --- | --- |
| annual_return | 7.4% | 17.2% |
| sharpe | 0.368 | 0.773 |
| max_drawdown | -35.7% | -37.1% |
| avg_gross_exposure | 18.4% | 21.9% |

Döneme göre Sharpe:

|  | development | regime_2019-07_2021-11 | regime_2022-01_end |
| --- | --- | --- | --- |
| T0 | 0.37 | 1.27 | -1.36 |
| D_T0_nostop | 0.77 | 1.27 | 0.05 |


Toplam backtest süresi: 1 dk işçi süresi, 66 çalıştırma.
