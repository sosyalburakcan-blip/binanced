# Kayan pencere: 15 / 20 / 30 / 45 / 60 dk (09.11.2026)

Kod: `kayan_pencere_2026-11-09.py`. Kaynak C3 kuralı, iki değişiklikle:
- Karar saat başında değil, her 5 dk'da veriliyor.
- Piyasanın son W dakikalık hareketi ölçülüyor.

**Kural:**
1. z = son W dk piyasa getirisi / bu getirinin son 24 saatteki standart sapması.
2. |z| > eşik ve piyasa çalkantılıysa (son 60 dk dakikalık oynaklık > son 24 saatin ortancası), BTC ve ETH hariç betası en
   yüksek 4 altcoinde gir. Her biri 1.500 $, piyasa emri.
3. Yön iki türlü denendi: TERSİNE (fade) ya da YÖNÜNDE (takip).
4. H dk sonra kapat. Aynı anda tek olay. Taker %0,05 + 1 bps kayma, iki uçta.

**Izgara:** W {15, 20, 30, 45, 60} × eşik {1; 1,5; 2} × H {15, 30, 60} × yön {tersine, yönünde}. Her ayar 5 farklı başlangıç
dakikasıyla çalıştırıldı ve ortancası alındı.

**Uyarı:** 08.11 C3 sınavında kullanıldığı için "sınav" sütunu artık temiz değil, yalnız kontrol amaçlı. Gerçek sınav,
değiştirilmeden çalıştırılacak demo ileri testi olacak.

## Sonuç (her satır: eşik × tutma = 9 ayar)

| Pencere | TERSİNE: tasarımda artı | sınavda artı | YÖNÜNDE: tasarımda artı | sınavda artı |
|---|---:|---:|---:|---:|
| 15 dk | 1/9 | 3/9 | 7/9 | 2/9 |
| 20 dk | 0/9 | 3/9 | 8/9 | **0/9** |
| 30 dk | 0/9 | 5/9 | 6/9 | 0/9 |
| **45 dk** | **6/9** | **7/9** | 1/9 | 0/9 |
| **60 dk** | **5/9** | **6/9** | 1/9 | 0/9 |

**Kısa pencereler (15–30 dk) kararsız.** Tasarımda hareketin yönünde gitmek kazandırdı (sert hareket kısa vadede devam
etti), sınavda aynı ayarlar 0/9 çöktü. Gün değişince davranış da değişiyor.

**Uzun pencereler (45–60 dk) iki dönemde de aynı yönü gösteriyor.** Tersine oynamak kazandırıyor, yönünde oynamak
kaybettiriyor.

**Tutma süresi belirleyici.** Tersine oynarken 60 dk tutmak sınavda 15/15 artı, 15 dk tutmak 2/15. Geri dönüş yaklaşık bir
saat sürüyor; 15 dk'da komisyon ödenip çıkılıyor ama geri dönüş henüz gelmemiş oluyor.

**Çok pencereli ortalama z** (15 + 20 + 30 + 60) tek başına 45 / 60 dk pencereden iyi değil, çünkü kararsız kısa pencereleri
de içeriyor.

## Öne çıkan ayarlar (tersine, 60 dk tut)

| W | Eşik | Tasarım: olay, net (artı faz) | Sınav: olay, net (artı faz) |
|---|---:|---|---|
| 60 | 1,0 | 8, +246,7 $ (5/5) | 10, +328,5 $ (5/5) |
| 60 | 1,5 | 5, +118,3 $ (4/5) | 7, +388,7 $ (5/5) |
| 45 | 1,0 | 7, +109,7 $ (5/5) | 10, +369,4 $ (5/5) |
| 45 | 1,5 | 6, +41,9 $ (3/5) | 8, +402,9 $ (5/5) |

Hepsi aynı ~6 oynak döneme dayanıyor. Ayarlar arasındaki farklar gürültü sayılmalı, "en iyisi" seçilmemeli.
