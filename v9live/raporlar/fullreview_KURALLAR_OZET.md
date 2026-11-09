# Bot nasıl çalışıyor (07.11.2026 12:15 TR'den beri geçerli kurallar, sade dil)

Benzetme: bot, her 5 dakikada bir 30 tezgâhlık pazarı dolaşan bir alıcı. Her tezgâha aynı soruları sorar, hepsine
"evet" diyen tezgâhlardan en iyisinden bir tane alır, aldığını belli bir fiyatta satmak üzere iki emir bırakır.

1. **Pazar (coin listesi), her dakika:** gerçek Binance vadeli piyasasında son 24 saatte en çok işlem gören (hacmi en büyük)
   30 coin. Normal 1 saatlik oynaması (VOL60) %2'den büyük olan atlanır.
2. **VOL60 ("normal 1 saatlik salınım"):** son ≈25 saatin 1 dk mumlarında her dakikadan başlayan 60 dk'lık fiyat değişimleri
   alınır, bunların tipik büyüklüğü (standart sapması). Örnek: VOL60 %0,8 → bu coin bir saatte tipik olarak ±%0,8 oynar.
3. **Sorular (5 dk'da bir, hepsi "evet" olmalı):**
   - son 4 saatte yükselmiş mi (RET_4 > 0),
   - yükseliş hızlanıyor mu: son 2 saat önceki 2 saatten iyi ve artıda (LC ≥ 2),
   - son 60 dk yerinde saymış mı: −%0,2 … +%0,2 arası (çok yükselmişi almaz),
   - son 15 dk alıcılar baskın mı, hacim normalden yüksek mi, defterde fiyata yakın alış satıştan fazla mı, alış birikiyor mu
     (12:15 TR'den beri),
   - "short kapatma + spotsuz" değil mi, demo borsada işlem açık mı.
4. **Seçim:** "evet" diyenlerden puanı en yüksek 1 coin (puan = 6 ölçünün sıra ortalaması). Aynı anda en çok 4 pozisyon.
5. **Büyüklük:** 1 salınım (VOL60) ters giderse 12 $ kaybedecek kadar: pozisyon = 12 $ ÷ VOL60, en çok 1.500 $, 10× kaldıraç.
   Örnek: VOL60 %0,8 → 1.500 $ (12/0,008 = 1.500); VOL60 %1,5 → 800 $.
6. **Alış:** demo borsada en iyi alış fiyatına bekleyen emir; fiyat kaçarsa 30 sn'de bir yukarı taşınır; 15 dk'da dolmazsa vazgeçer.
7. **Çıkış (hangisi önce gelirse):**
   - **kâr al:** giriş + 1 salınım (borsada bekleyen satış emri),
   - **zarar stopu:** giriş − 1 salınım (borsada, işaret fiyatıyla tetiklenir),
   - **60 dk kontrolü:** girişten 60 dk sonra 5 dk'da bir: son 60 dk −%0,2'den kötüyse YA DA fiyat girişin +%0,14 üstünde
     değilse piyasa emriyle satar,
   - **acil stop:** −%6 (VOL60 ≤ %2 olduğu için artık devreye girmez).

Kurallar 06.11 sabahından beri 18 kez değişti; işlemler 7 dönemde açıldı (A–G, `analyze.py REG`).
