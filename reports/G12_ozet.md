# G12 özeti — kilit ve tek seferlik doğrulama

2026-11-03. Kilit tarihi 2026-11-01 (anlık görüntüdeki son tam günlük mum). Doğrulama dönemi 2024-01-01 – 2026-11-01,
tam dönem 2019-07-01 – 2026-11-01. Ayrıntılı tablolar [G12_lock_validation.md](G12_lock_validation.md) dosyasında.

## Karar

Birincil hipotez **reddedildi**: alt-coin sistemi (T0) tam dönemde BTC-200'ü yenmiyor. Ön kaydın kuralına göre:

- Ana pozisyon **BTC-200**.
- Uydu payı kuralı alt-coin sistemine **%0** veriyor (0,5 × 0,18 = 0,09 < ρ × SR_BTC200 = 0,53 × 0,66 = 0,35).
- Aşama 2 için zorunlu kriterlerden (2–9) 3/8'i geçiyor; alt-coin sistemi Aşama 2'ye geçemez.

| Tam dönem | T0 | BTC-200 |
| --- | --- | --- |
| Sharpe | 0,18 | 0,66 |
| Yıllık getiri | %4,5 | %24,5 |
| En büyük düşüş | −%35,7 | −%66,2 |

T0 − BTC-200 eşleştirilmiş bootstrap: ΔSharpe −0,48, %95 GA −1,37…0,37, tek yönlü p = 0,868. DSR 0,26.

| Kriter | Dönem | Sonuç |
| --- | --- | --- |
| 1 Birincil hipotez | tam | HAYIR (p = 0,868) |
| 2 DSR ≥ 0,95 | tam | HAYIR (0,26) |
| 3 PBO < 0,5 | geliştirme | HAYIR (0,76) |
| 4 Doğrulamada Sharpe > 0, 1× ve 2× maliyet | doğrulama | HAYIR (T0 hiç işlem yapmadı) |
| 5 İki sıfır hipotezi | geliştirme | HAYIR (tarih karıştırma p = 0,85) |
| 6 Medyan MDD < evren EW'nin yarısı | tam | evet (−%31 / −%94) |
| 7 Tüm komşularda Sharpe > 0 ve ≥ temelin yarısı | tam | evet (en düşük 0,18) |
| 8 Negatif kontroller | geliştirme | HAYIR (8/11) |
| 9 %20 delist cezasıyla Sharpe > 0 | tam | evet (0,18) |

Kriterlerin hangi dönemde değerlendirileceği çalıştırmadan önce experiments.md satır 17'ye yazıldı.

## Doğrulama döneminde ne oldu

T0 2023-08-17'de −%35 sert sınıra takıldı ve kilit tarihine kadar (1.173 gün) yeni alım yapamadı. Doğrulama
döneminin tamamında nakitte bekledi, getirisi %0. Raporda görünen −137 Sharpe, sıfır getirinin hazine bonosundan
çıkarılmasından gelir; büyüklüğü anlamsız, işareti negatiftir.

Bu sonuç yalnızca kuraldan kaynaklanmıyor. Ön kayıt dışı tanı olarak sert sınır kapatıldığında da T0 doğrulama
döneminde kaybediyor: Sharpe −0,26, dönem toplamı −%8,1. Sınıra takılmadan işlem yapmaya devam eden komşu ve
varyantlar da (G_vol25, T1, T8'in 04–16 saat kapanışları) doğrulamada negatif Sharpe veriyor.

Aynı dönemde BTC-200 yıllık %21,3 getiri, 0,60 Sharpe ve −%30,9 en büyük düşüş verdi. Evrenin eşit ağırlıklı al-tutu
ise yıllık −%21,4 getirdi. 2024 sonrasında alt-coinlerin genelinde trend takibi para kazandırmadı.

## Bütünlük

- **Veri:** 2.061 dosya (1,54 GB) SHA-256 ile özetlendi (`lock/data_manifest.csv`, özet `b3135253…`). Çalıştırmadan
  önce yeniden doğrulandı.
- **Kod:** çalıştırma temiz commit'ten yapıldı (`8ca4a55`, tag `g12-lock`). `settings.yaml` ve ön kayıt özetleri
  dondurulan değerlerle aynı.
- **Tek seferlik:** kayıt çalıştırmadan önce `lock/G12_run.json`'a açıldı; ikinci bir `run` reddedilir.
- **Geleceği görme:** tam dönem çalıştırmalarının geliştirme kısmı G10 çalıştırmalarıyla 50/50 birebir aynı (en büyük
  fark 6,7e-16). Sonradan gelen veri geçmiş kararları değiştirmiyor.
- **Altın kayıt:** T0 ve BTC-200'ün tam dönem karar, dolum ve günlük kayıtları `golden/` altında. Yeniden üretim 6/6
  dosyada bayt bayt aynı. `tests/test_golden_master.py` her test koşusunda bunu denetliyor.

## BTC-200 için kilit bilgileri

Düşüş ufku tablosu (tam dönem bootstrap'i, %95'lik değerler). Canlı durdurma kuralı bu tabloyu kullanır:

| Ufuk | 30 gün | 60 gün | 90 gün | 180 gün | 365 gün |
| --- | --- | --- | --- | --- | --- |
| BTC-200, %95 düşüş | −%22,8 | −%28,5 | −%34,7 | −%47,1 | −%57,7 |

BTC-200 yıl yıl: 2024 +%79,9, 2025 −%14,5, 2026 (1 Kasım'a kadar) +%12,5.

## Sırada ne var

- G12 tamamlandı. Bundan sonra parametre veya kod değişikliği yapılmaz; yapılırsa doğrulama dönemi artık doğrulama
  sayılmaz.
- G13 (gölge mod) ve G14 (canlı), SPEC'e göre Binance durumu netleşene ve yazılı hukuki/vergi görüşü alınana kadar
  kapsam dışı. Gölge mod başlarsa varsayılan karar gereği BTC-200 çalışır; T0 ileriye dönük kanıt için sıfır ağırlıkla
  yanında izlenebilir.
- Kullanıcının yapacakları: `prereg-v1` ve `g12-lock` tag'lerini GPG ile imzalamak; ön kayıt ve veri özetlerini
  zaman damgası için kendine e-postayla göndermek.
