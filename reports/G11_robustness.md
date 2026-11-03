# G11 — Geliştirme dönemi sağlamlık ve istatistik

Aşama: geliştirme (2019-07-01 – 2023-12-31); veri sonu 2023-12-31; doğrulama dönemi yüklenmedi. Kod `8d2f770`, ön kayıt `prereg-v1`. Nakit getirisi temel varsayım %0; Sharpe ABD 3 aylık hazine bonosu üzerinden, √365.

> Tüm sonuçlar raporlanır, hiçbiri seçilmez. Kriterler 1, 2 ve 4 tam dönem / doğrulama dönemi içindir; aşağıdaki karşılıkları ön bilgidir.

## Parametre ızgarası (temel + 10 komşu)

| metrik | T0 | G_vol25 | G_vol45 | G_span0.8 | G_span1.2 | G_univ30 | G_univ50 | G_drift15 | G_drift35 | G_h0 | G_h1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sharpe | 0.368 | 0.719 | 0.512 | 0.478 | 0.406 | 0.409 | 0.601 | 0.364 | 0.366 | 0.467 | 0.409 |
| annual_return | 7.4% | 12.6% | 11.4% | 9.7% | 8.2% | 8.3% | 12.9% | 7.3% | 7.4% | 9.2% | 8.5% |
| annual_vol | 19.5% | 15.6% | 22.4% | 19.5% | 19.6% | 19.7% | 20.6% | 19.4% | 19.7% | 18.5% | 20.4% |
| max_drawdown | -35.7% | -28.2% | -35.9% | -35.2% | -35.3% | -35.5% | -35.6% | -35.4% | -36.0% | -35.0% | -35.9% |
| turnover_annual | 634.8% | 543.1% | 566.8% | 756.5% | 553.9% | 614.5% | 722.2% | 646.1% | 624.7% | 850.8% | 505.3% |
| sharpe_vs_base | 1.000 | 1.952 | 1.390 | 1.297 | 1.103 | 1.112 | 1.632 | 0.988 | 0.995 | 1.267 | 1.112 |

Rejimlere göre Sharpe:

|  | regime_2019-07_2021-11 | regime_2022-01_end |
| --- | --- | --- |
| T0 | 1.27 | -1.36 |
| G_vol25 | 1.15 | 0.08 |
| G_vol45 | 1.28 | -1.62 |
| G_span0.8 | 1.27 | -0.93 |
| G_span1.2 | 1.24 | -1.25 |
| G_univ30 | 1.30 | -1.32 |
| G_univ50 | 1.57 | -1.13 |
| G_drift15 | 1.26 | -1.34 |
| G_drift35 | 1.26 | -1.36 |
| G_h0 | 1.27 | -1.03 |
| G_h1 | 1.32 | -1.24 |

**PBO (CSCV, S = 16, 12870 kombinasyon, 11 nokta):** 0.763. Örneklem dışı kayıp olasılığı 0.24; bozulma eğimi -0.92.

## Deflated Sharpe (geliştirme dönemi, ön bilgi)

N = max(100, deneme 5 + ızgara 11 + varyant 24) = 100; deneme Sharpe varyansı 0.058; beklenen en büyük Sharpe 0.61. T0 Sharpe 0.37 (SH 0.47); **DSR 0.305**, PSR(0) 0.781.

## Bootstrap (durağan blok, ortalama 30 gün, 10.000 yol)

- T0 Sharpe 0.37, %95 GA -0.71…1.34.
- T0 − BTC-200 (eşleştirilmiş, geliştirme): ΔSharpe -0.33, %95 GA -1.41…0.73, tek yönlü p = 0.7336 (BTC-200 Sharpe 0.69).
- regime_2019-07_2021-11: ΔSharpe 0.49, p = 0.2329.
- regime_2022-01_end: ΔSharpe -2.46, p = 0.9997.
- En büyük düşüş medyanı: T0 -31.3%, evren eşit ağırlıklı al-tut -87.6% (kriter 6: yarısından küçük → **evet**; yolların 90%'ında geçiyor).

Düşüş ufku tablosu (ön bilgi; canlı kural kilitteki tabloyu kullanır):

| horizon_days | dd_q95 | dd_median | dd_mean |
| --- | --- | --- | --- |
| 30 | -0.101 | -0.037 | -0.044 |
| 60 | -0.133 | -0.066 | -0.069 |
| 90 | -0.160 | -0.084 | -0.087 |
| 180 | -0.214 | -0.118 | -0.126 |
| 365 | -0.290 | -0.171 | -0.179 |

**Minimum kayıt uzunluğu:** gözlenen Sharpe 0.37 ile 20.2 yıl gerekir; mevcut kayıt 4.5 yıl.

## Varyantlar T1–T10

| metrik | T0 | T1 | T3 | T4_0607 | T4_1415 | T5_20 | T5_50 | T6_cost2 | T6_loss20 | T6_loss50 | T7 | T8_h04 | T8_h08 | T8_h12 | T8_h16 | T8_h20 | T8_wd0 | T8_wd1 | T8_wd2 | T8_wd3 | T8_wd4 | T8_wd5 | T9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sharpe | 0.368 | 0.990 | 0.387 | 0.480 | 0.502 | 0.368 | 0.368 | 0.333 | 0.216 | -0.054 | 0.368 | 0.864 | 0.951 | 0.948 | 0.945 | 0.484 | 0.334 | 0.328 | 0.299 | 0.393 | 0.394 | 0.406 | 0.058 |
| annual_return | 7.4% | 20.8% | 7.8% | 9.8% | 10.3% | 7.4% | 7.4% | 6.6% | 4.1% | -6.2% | 7.4% | 19.9% | 22.1% | 22.0% | 21.6% | 10.1% | 6.6% | 6.6% | 6.0% | 7.9% | 7.9% | 8.1% | 1.5% |
| max_drawdown | -35.7% | -23.6% | -36.6% | -35.4% | -35.8% | -35.7% | -35.7% | -35.7% | -43.9% | -65.0% | -35.7% | -34.2% | -31.9% | -31.0% | -34.3% | -35.2% | -35.6% | -35.0% | -35.8% | -36.1% | -35.4% | -35.2% | -36.9% |
| avg_gross_exposure | 18.4% | 17.5% | 18.4% | 19.2% | 19.0% | 18.4% | 18.4% | 17.6% | 13.8% | 13.8% | 18.4% | 22.2% | 22.6% | 22.8% | 23.3% | 19.7% | 17.1% | 17.1% | 18.5% | 18.4% | 17.5% | 17.1% | 12.3% |
| cost_annual | 1.3% | 1.1% | 1.3% | 1.3% | 1.3% | 1.3% | 1.3% | 2.5% | 1.0% | 1.0% | 1.3% | 1.5% | 1.5% | 1.5% | 1.5% | 1.4% | 1.2% | 1.2% | 1.3% | 1.3% | 1.2% | 1.2% | 1.1% |

Rejimlere göre Sharpe:

|  | regime_2019-07_2021-11 | regime_2022-01_end |
| --- | --- | --- |
| T0 | 1.27 | -1.36 |
| T1 | 1.26 | 0.58 |
| T3 | 1.34 | -1.43 |
| T4_0607 | 1.36 | -1.14 |
| T4_1415 | 1.42 | -1.19 |
| T5_20 | 1.27 | -1.36 |
| T5_50 | 1.27 | -1.36 |
| T6_cost2 | 1.21 | -1.41 |
| T6_loss20 | 1.27 | -1.30 |
| T6_loss50 | 1.27 | -1.02 |
| T7 | 1.27 | -1.36 |
| T8_h04 | 1.41 | 0.08 |
| T8_h08 | 1.44 | 0.24 |
| T8_h12 | 1.44 | 0.27 |
| T8_h16 | 1.42 | 0.29 |
| T8_h20 | 1.38 | -1.15 |
| T8_wd0 | 1.26 | -1.48 |
| T8_wd1 | 1.26 | -1.40 |
| T8_wd2 | 1.19 | -1.27 |
| T8_wd3 | 1.34 | -1.31 |
| T8_wd4 | 1.35 | -1.49 |
| T8_wd5 | 1.33 | -1.44 |
| T9 | 0.79 | -1.64 |

T10 (BTC-200 çekirdek + T0 uydu, aylık):

|  | T10_core80 | T10_core50 |
| --- | --- | --- |
| sharpe | 0.701 | 0.682 |
| annual_return | 24.8% | 20.0% |
| max_drawdown | -58.2% | -46.1% |

**T6 karşı taraf stresi — sistemin hâlâ anlamlı kaldığı yıllık beklenen kayıp olasılığı:** T0 yıllık aşırı log getirisi 5.3%, BTC-200 21.7%. L = %20: getiriyi sıfırlayan p* = 0.236/yıl, BTC-200 düzeyine indiren p* = 0.000/yıl; L = %50: getiriyi sıfırlayan p* = 0.076/yıl, BTC-200 düzeyine indiren p* = 0.000/yıl.

## Uydu payı kuralı (geliştirme dönemi, ön bilgi)

0,5 × SR_T0 = 0.184; ρ × SR_BTC200 = 0.426 (ρ = 0.61). Kural sonucu: **%0**. Kesin hesap tam dönemde yapılır.

## Geç/kal kriterleri — geliştirme dönemi karşılıkları (ön bilgi)

| # | Kriter | Geliştirme dönemi | Durum |
| --- | --- | --- | --- |
| 1 | BTC-200'ü Sharpe'ta %95 güvenle yener (tam dönemde) | p = 0.7336 | **HAYIR** (ön bilgi) |
| 2 | DSR ≥ 0,95 (tam dönemde) | 0.305 | **HAYIR** (ön bilgi) |
| 3 | Geliştirmede PBO < 0,5 | 0.763 | **HAYIR** |
| 4 | Doğrulamada net Sharpe > 0, 1× ve 2× maliyet | geliştirmede 0.37 / 0.33 | doğrulamada ölçülecek |
| 5 | İki sıfır hipotezi %95 | p = 0.8501, 0.0010 | **HAYIR** |
| 6 | Bootstrap medyan MDD < evren EW'nin yarısı | -31.3% / -87.6% | **evet** |
| 7 | Tüm komşularda Sharpe > 0 ve ≥ temelin %50'si | en düşük 0.36 (oran 0.99) | **evet** |
| 8 | Tüm negatif kontroller beklendiği gibi | 8/11 | **HAYIR** |
| 9 | %20 delist cezasıyla Sharpe > 0 | 0.37 | **evet** |

