# Deney sonucu: az komisyon + yüksek yön isabeti (09.11.2026)

Ön kayıt: [deney_2026-11-09_onkayit.md](deney_2026-11-09_onkayit.md) (commit `c4f50d3`, deneyden önce). Kod:
`deney_2026-11-09.py` (commit `a8deaea`). Tek çalıştırma, 1 dk 46 sn.
- Karar anı: 404 (tasarım 228, 06.11 12:50 → 07.11 23:55; bekletme 176, 08.11 00:00 → 12:35).
- Ön kayıttan sapma yok. Kod iki kez değişti: hızlandırıldı, rastgele kıyasa "açık coin hariç" eklendi. İkisi de ilk
  çalıştırma hiç sonuç yazmadan durdurulduktan sonra yapıldı.

## Sonuç: GEÇMEDİ

Tasarımda seçilen yapılandırma: **son 4 saatte piyasaya göre en çok yükselen coine short** (r240x, rev, |z| ≥ 1,5, yalnız
short), kâr al / zarar kes ±%1,2, en çok 60 dk.

| | İşlem | Günde | Net | İsabet (brüt > 0) |
|---|---:|---:|---:|---:|
| Tasarım | 45 | 31 | **+213,0 $** | %71 |
| Bekletme | 17 | 26 | **−0,6 $** | %59 |
| Bekletme, taker giriş | | | −10,7 $ | |

- Rastgele girişte (aynı an, yön ve çıkışlar, rastgele coin, 1.000 tekrar) bekletme ortancası −1,8 $, %95'lik dilim
  +38,6 $ → **p = 0,48**.
- Şartlar: tasarım net > 0 ✓ · bekletme net > 0 ✗ · bekletme isabeti > %50 ✓ · p < 0,05 ✗.

## Izgara geneli: gerçek sinyal rastgele sinyalden iyi değil

| | Tasarımda net > 0 | Bekletmede net > 0 | Bekletme net ortancası | Bekletme isabet ortancası | Bekletmede en iyi |
|---|---:|---:|---:|---:|---:|
| Gerçek sinyal | 205 / 810 | 144 / 808 | −58,1 $ | %50,0 | +87,4 $ |
| Rastgele sinyal (karıştırılmış) | 220 / 810 | 136 / 810 | −46,7 $ | %49,3 | +80,0 $ |

**Tasarımdaki kazanç sinyalden değil, düşen piyasada short açmaktan geldi.** Tasarımın en iyi 5 yapılandırmasının ikisi
rastgele sinyalle de +158,8 $ ve +193,4 $ kazandı. Yalnız-short yapılandırmalarının tasarım ortancası gerçek sinyalle
+12,4 $, rastgele sinyalle +10,1 $; bekletmede gerçek −15,7 $, rastgele −45,2 $.

## Komisyonun etkisi (bilgi; seçimde kullanılmadı)

Izgaranın ortancası, iki dönem toplam (2,4 gün):

| Kâr al / zarar kes | En çok tutma | İşlem | Net | Ücret |
|---|---:|---:|---:|---:|
| ±%0,5 | 60 dk | 112 | −241 $ | 97 $ |
| ±%0,5 | 240 dk | 77 | −130 $ | 64 $ |
| ±%0,8 | 120 dk | 70 | −149 $ | 63 $ |
| ±%1,2 | 60 dk | 78 | −140 $ | 76 $ |
| ±%1,2 | 240 dk | 44 | −67 $ | 39 $ |

Daha geniş hedef ve daha uzun tutma, işlem sayısını ve ücreti düşürüyor; zarar da onunla birlikte küçülüyor. Ama hiçbir
satırda artıya geçmiyor. Bu, sinyalde bir avantaj olmadığını gösterir: kayıp, büyük ölçüde ödenen ücret kadar.

## Ne anlama geliyor

- Denenen beş özellik (coinin piyasaya göre son 30 / 60 / 240 dk hareketi, ikisinin birleşimi, defter dengesi), iki yön,
  üç eşik, üç mod, üç hedef ve üç süre arasında, bu 3 günde yönü rastgeleden iyi tahmin eden kural bulunmadı.
- Komisyonu azaltmanın tek etkili yolu daha az ve daha geniş işlem. Bu zararı küçültüyor, ama kâr yaratmıyor.
- 3 gün tek bir piyasa dönemi ve bekletme yalnız 12,5 saat. Bu sonuç "hiçbir kural çalışmaz" demek değil, ama "bu veriden
  çalışan bir kural çıkmadı" demek. Bu ızgaradan demoya alınacak aday yok.
