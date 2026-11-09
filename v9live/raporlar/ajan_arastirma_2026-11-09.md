# 4 ajanla kural araştırması (09.11.2026)

Kullanıcı isteği: "bu veride kaybetmek yerine + yazalım, agentler ile analiz et, bir yolunu bul".

## Ortak kurallar
4 ajan paralel çalıştı. Her biri ayrı bir fikir ailesine baktı ve aynı protokole uydu:
- **Tasarım:** 08.11 00:00 UTC öncesi. Kural yalnız burada arandı.
- **Bekletme:** 08.11 00:00 UTC sonrası. En çok 3 aday burada bir kez sınandı; sonuç ne çıkarsa çıksın yazıldı.
- **Maliyet:** gerçek hesap ücretleri, maker %0,02, taker %0,05. Taker dolumlar alış/satış fiyatından, üstüne 1 bps kayma.
  Limit emir yalnız fiyat içinden geçerse dolmuş sayıldı.
- **Kıyas:** aynı an ve aynı kurallarla rastgele coin, ≥ 500 tekrar.

Veri: Release'teki defter arşivi (dakikalık gerçek piyasa defteri) ve `live.db`.

## Sonuçlar

| Aile | Denenen | Sınavda (08.11) | Karar |
|---|---:|---|---|
| Emir defteri (dengesizlik, duvarlar, makas, piyasa yapıcılık) | 48 kural, 37 özellik | 3 adayın üçü de zararda (−69, −345, −221 $) | **Yok.** Defterdeki bilgi saniyeler içinde fiyata yansıyor; dakikalık görüntüyle yakalanamıyor. Makas ortanca 1,4 bps, maker gidiş-dönüş ücreti 4 bps. |
| Botun kendi ölçümleri (alıcı payı, açık pozisyon, spot payı, 48 sa tepe/dip) | 86 kural, ~500 görünüm | −50, +18, −55 $ (rastgele p 0,44 / 0,30 / 0,65) | **Yok.** Tasarımdaki kazanç düşen piyasada açılan short'lardan. |
| Pasif limit emir (aşırı hareketi limitle karşılamak) | 588 kural | −193, −174, −146 $ (rastgeleden kötü) | **Yok.** Tasarım kazancı 06.11'deki 3–5 küçük coinin pompala-boşalt hareketinden. Limit emir tam fiyat aleyhe giderken doluyor. |
| Lider-takipçi ve piyasa rejimi | 564 kural | C1 −16 $, C2 +9 $, **C3 +193 $** | Lider-takipçi yok: altcoinler BTC'yi aynı dakikada izliyor. **C3 tek aday.** |

## C3: volatil dönemde piyasanın sert saatlik hareketine karşı oyna

**Kural.** Her 60 dk'da:
1. Listedeki coinlerin eşit ağırlıklı son 60 dk getirisini hesapla.
2. Bu getiri son 24 saatteki dağılımına göre 1 standart sapmadan büyükse, VE son 60 dk'nın oynaklığı son 24 saatin
   ortancasından yüksekse:
3. BTC ve ETH dışındaki, piyasaya göre betası en yüksek 4 coinde, hareketin **tersine** 1.500 $'lık pozisyon aç.
4. 60 dk sonra kapat. Giriş ve çıkış piyasa emriyle (taker).

**Ajanın sonucu.**

| | Olay | İşlem | Net | Ücret |
|---|---:|---:|---:|---:|
| Tasarım | 6 | 24 | +229 $ | 36 $ |
| Bekletme | 8 | 32 | +193 $ | 48 $ |

Bekletmede isabet %72. Yön çevirme testinde p = 0,023; 3 aday sınandığı için düzeltilmiş hâli ≈ 0,07. Rastgele coin
p = 0,22, yani kazanç coin seçiminden değil, saatlik piyasa yönünden geliyor.

**Bağımsız doğrulama** (`ajan_c3_dogrulama.py`; ajanın kodu kullanılmadan sıfırdan yazıldı):
- Kararın saat içindeki dakikası 60 farklı değerle kaydırıldı. Bekletme 60 / 60'ında artı (ortanca +123 $, %10'luk
  dilim +42 $). Tasarım 49 / 60'ında artı.
- Komşu ayarların hepsi (z 0,75 / 1 / 1,5 × tutma 30 / 60 / 120 dk, yalnız tasarım) artı.
- Aynı kural piyasa YÖNÜNDE oynanınca iki dönemde de zarar ediyor (tasarım −241 $, bekletme −213 $). Etki yön olarak
  tutarlı: sert saatlik hareketler bu 3 günde geri döndü.
- Ajanın kodunda ileriye bakış ya da ücret hatası görülmedi.

**Zayıf yanları.**
- 3 günde yalnız **6 ayrı oynak dönem** var; bunların 3'ü bekletmede. İstatistiksel olarak çok az.
- En kötü tek olay −259 $ (06.11). Her olayda tek yönde 6.000 $ açılıyor.
- Yatay ve dalgalı piyasada kazanır, uzun süren tek yönlü çöküş ya da yükselişte kaybeder.
- Fonlama ücreti hesaba katılmadı. Demo defteri sığ, piyasa emirlerinde kayma daha büyük olabilir.

## Öneri
C3 gerçek para için değil. **Değiştirilmeden, demoda ileri test** için tek aday.

İleri test şartları:
- Kurallar yukarıdaki gibi dondurulur.
- En az 40 olay çalıştırılır.
- 20 olaydan sonra net < 0 ise durdurulur.
- Yalnız güvenlik için her pozisyona −%3 acil stop eklenebilir; bu sinyalin parçası değildir.

Ajan betikleri oturumun geçici klasöründe kaldı; tablolar ve kararlar bu dosyada.
