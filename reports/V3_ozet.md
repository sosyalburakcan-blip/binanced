# Araştırma v3 özeti — kısa vadeli trend (günlük, 2–3 günlük, haftalık)

2026-11-03. Ön kayıt `PREREGISTRATION_v3.md` (tag `prereg-v3`, commit `535ab72`) gerçek veride hiçbir aday
çalıştırılmadan donduruldu. Toplu çalıştırma bir kez yapıldı (`lock/V3_run.json`, 57 çalıştırma). Ayrıntılı tablolar
[V3_short_trend.md](V3_short_trend.md) dosyasında.

## Sonuç

**Hiçbir aile ön kayıtlı kriterleri geçmedi.** Karar değişmiyor: BTC-200.

Tam dönem (2019-07 – 2026-11-01), maliyetler dahil, nakit %0:

| Strateji | Yıllık getiri | Sharpe | En büyük düşüş | Yıllık maliyet | 1.000 $ → |
| --- | --- | --- | --- | --- | --- |
| TS_D: BTC, dünkü getiri pozitifse tut (her gün karar) | −%26,7 | −0,60 | −%92 | %29,2 | ~100 $ |
| 2 günlük getiri (komşu) | −%3,1 | 0,08 | −%66 | %18,6 | — |
| 3 günlük getiri (komşu) | %6,2 | 0,28 | −%64 | %15,7 | — |
| TS_W: BTC, son 7 günün getirisi pozitifse tut (haftada bir karar) | %9,3 | 0,35 | −%68 | %4,1 | ~1.900 $ |
| XS_MOM: son 7 günde en çok yükselen 5 coin (haftalık) | %12,8 | 0,43 | −%58 | %7,0 | ~2.400 $ |
| *Kıyas: BTC-200* | %24,5 | 0,66 | −%66 | %1,2 | ~5.000 $ |
| *Kıyas: BTC al-tut* | %31,5 | 0,71 | −%77 | %0,0 | ~7.500 $ |

## Ne oldu

- **Günlük trend maliyete gidiyor.** Sinyal neredeyse her gün değişiyor: 7,3 yılda 717 döngü (yılda ~100) ve yılda
  portföyün yaklaşık 195 katı ciro. Maliyet yılda %29'u götürüyor; maliyetsiz hâli bile ancak sıfır civarında. 2 ve 3 günlük ufukta maliyet
  azalıyor (%16–19) ama getiri yine BTC-200'ün çok altında.
- **Haftalık trend (TS_W) ve haftalık momentum (XS_MOM) para kazandırıyor ama az.** İkisi de 2020–2021 ve 2023'te
  iyi, 2024 sonrasında zayıf. Kirlenmiş bekletme döneminde TS_W'nin Sharpe'ı −0,19; XS_MOM'unki 0,05 (2×
  maliyetle −0,16).
- **Coin seçimi rastgeleden iyi, zamanlama değil.** XS_MOM'da rastgele coin testi p = 0,002, ama tarih karıştırma
  p = 0,28.
- **Kontrollerin hepsi beklendiği gibi.** Bir karar dönemi sızıntı Sharpe'ı 4–9'a çıkarıyor; karıştırılmış ve GARCH
  serilerinde para kaybediliyor; 365 gün gecikme avantajı yarıdan fazla düşürüyor. Sonuç bir kod hatasından değil,
  kuralların bu verideki zayıflığından geliyor.

## Dikkat: en iyi komşu

TS_W'nin 28 günlük komşusu (son 28 günün BTC getirisi pozitifse tut, haftada bir karar) yıllık %30,4, Sharpe 0,77,
düşüş −%63 verdi; kâğıt üzerinde BTC-200'den iyi. Ama:

- Ön kayıtlı temel ayar değil; 13 aday arasından sonuç görüldükten sonra seçilirse aşırı uyum olur.
- Ailenin PBO'su 0,61: ızgarada en iyi görünen ayarın başka dönemde de en iyi kalma ihtimali düşük.
- Bu kural, BTC-200 gibi bir BTC trend kuralı. Ufuk kısaldıkça sonuç kötüleşiyor (28 gün 0,77 → 14 gün 0,57 →
  7 gün 0,35 → 1 gün −0,60). Yani işe yarayan kısa vadeli trend değil, daha uzun vadeli BTC trendi.

Ancak ileriye dönük gölge testte BTC-200'ün yanında izlenebilir; bu veriyle kanıtlanamaz.

## Üç araştırmanın toplamı

v1 (orta vadeli alt-coin trendi), v2 (trend dışı beş aile) ve v3 (kısa vadeli trend) toplam 80'den fazla deneme
yaptı. Hiçbiri, maliyetlerden sonra ve şans payı hesaba katıldığında, BTC-200'ü güvenilir biçimde geçmedi. Kısa
ufukta maliyetler, alt-coinlerde ise 2022 sonrası çöküş belirleyici oldu.
