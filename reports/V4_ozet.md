# Araştırma v4 özeti — gün içi momentum (spot ve kaldıraçlı vadeli)

2026-11-03. Ön kayıt `PREREGISTRATION_v4.md` (tag `prereg-v4`, commit `50d4a50`) gerçek veride hiçbir yapılandırma
çalıştırılmadan donduruldu. Toplu çalıştırma bir kez yapıldı (`lock/V4_run.json`, 5.596 çalıştırma, 25 dakika).
Ayrıntılı tablolar [V4_intraday_momentum.md](V4_intraday_momentum.md), ücret ve vergi kaynakları
[V4_fees_tax.md](V4_fees_tax.md) dosyalarında.

## Sonuç

**Reddedildi.** Tasarım döneminde seçilen en iyi kural, 2024 sonrası bekletme döneminde para kaybettirdi ve
BTC-200'ü geçmedi. Karar değişmiyor: BTC-200.

## Ne denendi

- **Coinler:** her ay en az 2 yıldır listelenen, en likit ilk 10 coin (geriye dönük seçim yok).
- **Sinyal:** her saat momentum ölçümü (z-skoru). En güçlü 3 coin arasından, momentumu belirli bir süre üst üste
  yüksek kalan coine giriş.
- **Çıkış:** kâr al, zarar kes ya da süre dolunca. 15 dakikalık barlarla; aynı barda ikisi birden vurulursa zarar
  kes sayıldı.
- **Izgara:** 648 ayar: 3/6/12/24 saatlik momentum, 3 giriş eşiği, 1/3/6 saat takip, %1/%2/%4 kâr al, %1/%2/%4 zarar
  kes, en fazla 24/72 saat tutma.
- **Piyasalar:** spot ve vadeli 1×, 2×, 3×, 5× kaldıraç.
- **Maliyetler:** Binance komisyonu, kayma, gerçek fonlama ödemeleri ve tasfiye. Türkiye'de yürürlükte işlem vergisi
  olmadığı için temel vergi 0; vergi senaryoları ayrıca hesaplandı.

## En iyi kural ve sonucu

En iyi kural: 6 saatlik momentum, giriş eşiği z ≥ 2, 6 saat takip, %4 kâr al, %4 zarar kes, en fazla 72 saat.

| | 2019-07 – 2023-12 (tasarım) | 2024-01 – 2026-11 (bekletme) |
| --- | --- | --- |
| Spot, yıllık getiri | +%13,5 | **−%5,0** |
| Spot, Sharpe | 0,80 | **−0,57** |

Tam dönemde (7,3 yıl) spotta 1.000 $ → yaklaşık 1.530 $, en büyük düşüş −%34. Aynı dönemde BTC-200: yaklaşık
5.000 $.

## Kaldıraç ve spot farkı (aynı kural)

| | Spot | Vadeli 1× | 2× | 3× | 5× |
| --- | --- | --- | --- | --- | --- |
| Tam dönem, 1.000 $ → | 1.531 | 2.253 | 4.331 | 7.103 | 11.819 |
| **Son 3 yıl (bekletme), 1.000 $ →** | **864** | **997** | **929** | **811** | **504** |
| En büyük düşüş | −%34 | −%28 | −%51 | −%67 | −%87 |

- **Vadeli işlem spottan ucuz.** Komisyon %0,05'e karşı %0,10. Aynı kural vadeli 1×'te belirgin biçimde daha iyi
  çıkıyor (tasarım Sharpe 0,80 → 1,18).
- **Kaldıraç getiriyi değil, hem kazancı hem kaybı büyütüyor.** 5×'te geçmiş 11 kat gösteriyor; ama bu kazancın
  tamamı 2019–2023'ten geliyor. Son 3 yılda aynı kural parayı yarıya indirdi; yol boyunca düşüş −%87.
- **Kötü dönemde kaldıraç hesabı siliyor.** İkinci sıradaki kural 5× vadelide son 3 yılda 1.000 $'ı 27 $'a
  indirdi.

## Gün içi momentum tamamen boş mu?

Tamamen değil. Tasarım döneminde momentum sinyali rastgele girişlerden iyiydi: aynı kâr al/zarar kes ve aynı işlem
sıklığıyla p = 0,01. Rastgele sinyalli ızgaraların en iyisi −0,49 Sharpe verirken bizim en iyimiz 0,80. Ama:

- **Etki küçük ve 2024 sonrası kayboldu.** Spotta 648 ayarın hiçbiri bekletme döneminde pozitif Sharpe vermedi.
  Vadeli 1×'te 16'sı pozitif (en iyisi 0,34), ama bunlar bekletmeye bakılarak seçilemez.
- **Maliyet belirleyici.** Spotta ızgaranın medyan Sharpe'ı −3,4: sık işlem yapan ayarlar komisyon ve kaymayla
  eriyor.
- **PBO'nun 0 çıkması beceri işareti değil.** Sıralamayı işlem sıklığı belirliyor: az işlem yapan ayarlar her
  dönemde daha az kaybediyor. Tasarım ile bekletme sıralamasının korelasyonu 0,92 bundan.
- **Şans payı hesaba katılınca:** 3.324 denemeden sonra DSR 0,000. BTC-200'e karşı p = 0,77.

## Maliyet ve vergi duyarlılığı (en iyi kural, spot, tam dönemde 1.000 $ →)

| Temel | BNB ile komisyon | %0,03 işlem vergisi | 2× maliyet | Yıllık %15 vergi | %27 | %40 |
| --- | --- | --- | --- | --- | --- | --- |
| 1.531 | 1.735 | 1.318 | 929 | 1.377 | 1.263 | 1.147 |

## Sırada: canlı kâğıt takip

Ön kayda göre gölge mod adayı yok. Kullanıcının isteğiyle tasarımda en iyi 3 kural (spot ve vadeli 1×/2×/3×) ve
BTC-200 canlı veride kâğıt üzerinde izlenecek. Asıl amaç gerçek kayma, komisyon ve fonlamayı emir defterinden
ölçmek. Kârlılık beklentisi düşük.
