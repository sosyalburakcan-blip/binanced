# G10–G11 özeti — geliştirme dönemi (2019-07 – 2023-12)

2026-11-03. Ön kayıt `prereg-v1` ile donduruldu. Doğrulama dönemi (2024-01 sonrası) hiç yüklenmedi. Ayrıntılı tablolar
[G10_development.md](G10_development.md), [G11_robustness.md](G11_robustness.md) ve
[G10_independent_check.md](G10_independent_check.md) dosyalarında.

## Sonuç

Ön kayıtlı alt-coin sistemi (T0), geliştirme döneminde birincil kıyas BTC-200'ü yenmiyor:

| | T0 | BTC-200 |
| --- | --- | --- |
| Sharpe | 0,37 | 0,69 |
| Yıllık getiri | %7,4 | %26,6 |
| En büyük düşüş | −%35,7 | −%66,2 |

T0 − BTC-200 eşleştirilmiş bootstrap testinin tek yönlü p değeri 0,73. Rejimlere göre tablo şöyle:

| Dönem | T0 Sharpe | BTC-200 Sharpe |
| --- | --- | --- |
| 2019-07 – 2021-11 | 1,27 | 0,78 |
| 2022-01 – 2023-12 | −1,36 | 1,11 |

Geliştirme döneminde ölçülebilen ve Aşama 2 için zorunlu kriterlerden ikisi kalıyor:

- **Kriter 3, PBO < 0,5:** PBO 0,76.
- **Kriter 5, iki sıfır hipotezini de geçme:** tarih karıştırmada p = 0,85, yani aynı döngüler rastgele tarihlere
  konduğunda ortalama Sharpe (0,54) gözlenenden yüksek. Rastgele coin hipotezinde p = 0,001 ile geçiyor.

**Kriter 8 (negatif kontroller), ön kayıtlı eşiklerle:** 8/11 beklendiği gibi. Kalan üç kontrol:

- **Getiri karıştırma:** coinlerin dönem kaymasını koruyor (aşağıya bakın).
- **Orijinal − ters sinyal:** fark anlamlı değil (p = 0,13).
- **Yıl çıkarma:** 2020 ya da 2021 çıkarılınca Sharpe negatife dönüyor.

Kriter 2 (DSR) için geliştirme dönemi karşılığı 0,31.

Kriter 6, 7 ve 9 geçiyor.

Bu yüzden, ön kayıttaki karar kuralına göre, varsayılan karar BTC-200. Tam dönem birincil hipotez testi ve uydu payı
hesabı G12'de (kilit + tek seferlik doğrulama) kesinleşir. Ancak kriter 3 ve 5 geliştirme döneminin kriterleri olduğu
için doğrulama sonucu ne olursa olsun alt-coin sistemi Aşama 2'ye geçemez.

## Hata olmadığına dair kanıt

- **Bağımsız kontrol betiği:** motoru görmemiş ayrı bir oturumda yalnızca SPEC'ten yazıldı. 7 coinde EMA, tamponlu
  durum, tutma bayrağı ve günlük net getiri birebir aynı. İlk karşılaştırmanın bulduğu iki hata portföy sonucu
  görülmeden düzeltildi (experiments.md satır 11).
- **Geleceği görme kontrolleri:**
  - 365 gün gecikme Sharpe'ı 0,06'ya düşürüyor.
  - Sinyali başka coinin getirisine uygulamak 0,11'e düşürüyor.
  - Oynaklığı eşleştirilmiş GARCH serileri −0,52 veriyor.
  - Kaymadan arındırılmış karıştırma −0,35 veriyor.
  - Pozitif kontrol (1 gün sızıntı) Sharpe'ı 2,25'e çıkarıyor, yani sızıntı yakalanıyor.

  Zayıf sonuç bir kod hatasından değil, sinyalin bu dönemdeki gücünden geliyor.

## Sonuçlardan sonra düzeltilenler (experiments.md satır 13)

- Kıyas 6 (aynı sinyal, eşit ağırlık) yanlışlıkla −%35 sert sınırla çalışıyordu. Ön kayıt kıyaslarda sert sınır
  öngörmüyor. Düzeltildi; bu kıyasın Sharpe'ı 0,78.
- GARCH kontrolü sıfır ortalamalı log getiriyle kurulmuştu. Bu, coin başına σ²/2 kadar pozitif kayma ekliyordu
  (ilk sonuç Sharpe 1,66, geçersiz). Basit getirinin beklentisi sıfır olacak şekilde düzeltildi.
- T0 ve stratejinin kendisi değişmedi.

## Karar gerektiren bulgu: sert sınırda kilitlenme

−%35 sert sınır yeni alımları durdurur ve portföy zirvenin −%25'ine döndüğünde kalkar. Pozisyonlar sinyalle
kapandıktan sonra nakit %0 getirdiği için portföy toparlanamaz ve durdurma kalıcı olur.

T0 bu sınıra 2023-08-17'de takılıyor ve dönem sonuna kadar alım yapamıyor. Bu yüzden 2023 sonundaki alt-coin
yükselişini kaçırıyor. Komşuların ve varyantların çoğu da takılıyor. T8'deki büyük saat farkları (Sharpe 0,30–0,95)
da büyük ölçüde bundan kaynaklanıyor: düşüşü −%35'in hemen altında kalan kapanış saatleri kilitlenmiyor.

Ön kayıt dışı bir tanı olarak, sert sınır kapalı T0'ın sonucu (yalnızca tanı, seçim için değil):

| | Geliştirme | 2019-07 – 2021-11 | 2022-01 – 2023-12 |
| --- | --- | --- | --- |
| Sharpe | 0,77 | 1,27 | 0,05 |

Bu tanı yine BTC-200'ü anlamlı biçimde yenmiyor ve 2022 sonrasında zayıf kalıyor.

Kuralı değiştirmek ön kayıttan sonra yapılan bir değişikliktir: N'ye eklenir ve sonuç görülerek yapıldığı için aşırı
uyum riskini artırır. Değiştirmeden G12'ye geçmek ön kaydın bütünlüğünü korur.
