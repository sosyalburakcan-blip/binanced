# v9 demo botu: tam inceleme (07.11.2026, 86 kapanan işlem, 06.11 11:00 TR → 07.11 12:52 TR)

Kod ve veri sıfırdan (`fullreview/`); önceki incelemeler (allreview/, lossreview/) kullanılmadı. bot.py içe aktarılmadı.
Saatler Türkiye saati (UTC+3), aksi yazılmadıkça.

## Veri ve yöntem
- **Demo hesap (imzalı, salt okunur GET):** userTrades 6.362 dolum, allOrders, allAlgoOrders (stop emirleri), income (fonlama, komisyon).
- **Gerçek piyasa (herkese açık):** 40 coinin 1 dk mumları (05.11 05:00 UTC → şimdi); her demo dolum anı için o ana kadarki son
  gerçek işlem (aggTrades, 330 istek, 6.027 dolum anının hepsi bulundu; gerçek işleme uzaklık ortanca 0,8 sn, %99'u ≤ 9,7 sn).
- İşlemler borsa dolumlarından yeniden kuruldu: pozisyon 0'dan açılıp 0'a dönene kadar = 1 işlem. 88 bulundu; 86'sı botun kaydıyla
  eşleşti, 2'si 06.11 sabahı LTC deneme emirleri (`v9d-test`, `v9d-smk`).
- Kurallar `KURALLAR.md`'den; kısa özet `KURALLAR_OZET.md`. Kod: `fetch.py`, `fetch_ref.py`, `analyze.py`, `tables.py`; işlem başına
  her şey `trades.csv`; tablolar `tables.out`.

## 1. Doğruluk (bot yaptığını doğru mu yaptı?)
| Denetim | Sonuç |
|---|---|
| Net kâr, borsadan yeniden | −315,28 $ (bot kaydı −314,98 $). Fark 0,30 $: ETH (07.11 03:00) ve ONDO (07.11 11:00) işlemlerinde 00:00 / 08:00 UTC fonlaması (0,15'er $) bot kaydına girmemiş. Başka fark yok |
| Giriş şartı (karar anında, gerçek mumlardan) | 86/86 geçiyor; ivme puanı LC 86/86 aynı; RET_4 farkı 2e−16 |
| VOL60 (oynaklık) | 38/38 bağımsız hesapla aynı (fark 0; her birinde 1.440 getiri) |
| Büyüklük min(1.500 $, 12 $ / VOL60) | 38/38 hedef aynı. Dolan/hedef ortanca 1,00; 3 yarım dolum (en az %11) |
| Kâr al / stop mesafesi ÷ VOL60 | ortanca 1,01 / 0,99. Fiyat adımı kaba ucuz coinlerde yuvarlama kâr alı 1,18×'e kadar uzaklaştırıyor, stopu 0,82×'e kadar yaklaştırıyor (STRK, WLFI, ERA, ARB) — kural böyle yazılmış, ikisi de aleyhte |
| Çıkış sebebi ↔ borsadaki emir | kâr al 21 = kâr al limiti; zarar stopu 18 = stop emri + 4 = 06.11 17:13 yeniden başlatmada zaten −5 $'ı geçmiş pozisyonların piyasa satışı; 60 dk / saatlik kontrol 38 = botun piyasa satışı; acil stop 1; elle 4 (ETHFI iOS uygulaması; 06.11'deki ONDO, TAO, ZEC borsada botun piyasa satışı `v9d-mx` olarak görünüyor, bot kaydı "kullanıcı kapattı") |

Sonuç: **kod hatası yok** (fonlama kaydı hariç, 0,30 $).

## 2. Para nereye gitti (86 işlem, −315,28 $)
| Parça | $ | Ne demek |
|---|---|---|
| Gerçek fiyat hareketi | −155,5 | aynı anlarda gerçek piyasa fiyatıyla alıp satsaydı |
| Demo fiyat farkı | −100,3 | demo dolum fiyatı − o anki gerçek fiyat |
| Komisyon | −58,4 | |
| Fonlama | −1,1 | |

Demo farkının ayrıntısı (bize karşı +, baz puan = %0,01):
| Dolum | $ | ağırlıklı bps | Yorum |
|---|---|---|---|
| Alışlar (bekleyen emir, 5.678 dolum) | −65,7 | −6,0 | demo, gerçek fiyattan pahalı aldı (%83'ünde) — gerçek maliyet |
| Botun piyasa satışları (63) | −38,2 | −7,5 | demo defteri sığ — gerçek maliyet |
| Kâr al limitleri (596) | −31,4 | −10,1 | demo fiyatı gerçeğin GERİSİNDE kalmış; limit emri gerçekte de aynı fiyattan dolar → kayıp değil, zamanlama |
| Stoplar (19) | +32,3 | +13,0 | işaret fiyatıyla tetik, demo lehimize |
| Acil stop + iOS | +2,7 | | |

Kötü tarafı seçerek (kâr al farkı piyasaya yazılırsa): **piyasa / seçim ≈ −187 $, demo ≈ −69 $, komisyon −58 $, fonlama −1 $.**

## 3. Çıkış türüne göre
| Çıkış | Adet | Kazanan | Net $ | Ort. $ | En kötü $ | Ortanca süre |
|---|---|---|---|---|---|---|
| zarar stopu | 22 | 0 | −183,56 | −8,34 | −24,35 | 28 dk |
| 60 dk kontrolü (5 dk'da bir) | 32 | 0 | −175,10 | −5,47 | −20,54 | 64 dk |
| acil stop −%6 (JCT) | 1 | 0 | −94,57 | | | 41 dk |
| saatlik kontrol (06.11 sabah) | 6 | 1 | −7,19 | −1,20 | | 60 dk |
| elle | 4 | 3 | +6,83 | | | |
| kâr al | 21 | 21 | +138,31 | +6,59 | | 25 dk |
| **toplam** | **86** | **25** | **−315,28** | −3,67 | | |

Şu anki kural ailesi (±1 VOL60, 06.11 22:00 TR'den beri, 38 işlem, −115,44 $):
| Çıkış | Adet | Net $ |
|---|---|---|
| 60 dk kontrolü | 25 | −107,49 |
| zarar stopu | 7 | −68,07 |
| kâr al | 5 | +54,96 |
| elle (ETHFI) | 1 | +5,15 |

60 dk kontrolüyle satılan 25 işlemin **25'i de "kârda değil" (+%0,14 altında) şartından** satıldı; yalnız "düşüş" şartından satılan yok.

## 4. Kural dönemine göre
| Dönem (TR) | Kural | Adet | Kazanan | Net $ |
|---|---|---|---|---|
| A 06.11 11:00–13:34 | küçük pozisyon, saat başı | 7 | 3 | −2,77 |
| B 06.11 13:34–17:13 | 1.500 $, kâr al +5 $, stop YOK (−%6 acil) | 24 | 14 | −135,65 (JCT −94,57 dahil) |
| C 06.11 17:13–21:09 | +5 $ / −5 $ | 13 | 1 | −52,13 |
| D 06.11 21:09–22:00 | +5 $ / −12 $ | 4 | 1 | −9,30 |
| E 06.11 22:00–07.11 07:30 | ±1 VOL60, geri çekilmede al | 21 | 4 | −64,72 |
| F 07.11 07:30–12:15 | ±1 VOL60, hemen al | 17 | 2 | −50,72 |
| G 07.11 12:15'ten beri | + hacim/defter şartı | 0 | – | – |

Kazanç / kayıp dengesi:
- A–D (sabit $ hedef): ort. kazanç +4,49 $, ort. kayıp −9,83 $ → başa baş için %69 kazanma gerekir; gerçek %40.
- E–F (±1 VOL60): ort. kazanç +10,02 $, ort. kayıp −5,49 $ → başa baş için %35 gerekir; gerçek **%16** (38'de 6).

## 5. En çok zarar eden işlemler
| Coin | Karar (TR) | Çıkış | Net $ | Gerçek fiyat $ | Demo farkı $ | Dönem |
|---|---|---|---|---|---|---|
| JCT | 06.11 15:55 | acil stop −%6 | −94,57 | −90,65 | −3,22 | B (VOL60 %6,5, oynaklık sınırı yoktu) |
| ZEC | 06.11 16:22 | stop (17:13 yeniden başlatmada piyasa satışı) | −24,35 | −16,70 | −6,76 | B |
| QNT | 06.11 15:50 | 60 dk kontrolü | −20,54 | −15,07 | −4,59 | B |
| WLD | 06.11 15:50 | 60 dk kontrolü | −18,07 | −14,72 | −2,45 | B |
| 1000PEPE | 06.11 15:50 | 60 dk kontrolü | −13,61 | −12,00 | −0,71 | B |
| QNT | 07.11 01:15 | zarar stopu | −12,87 | −11,74 | −0,26 | E |
| HYPE | 06.11 16:24 | stop (yeniden başlatma) | −12,83 | −7,28 | −4,51 | B |
| VVV | 07.11 05:15 | zarar stopu | −12,82 | −9,57 | −2,42 | E |
| AIO | 07.11 06:50 | zarar stopu | −12,28 | −11,69 | +0,36 | E |
| STRK | 06.11 17:00 | stop (yeniden başlatma) | −12,19 | −6,31 | −4,83 | B |

İlk 5 = −171,14 $ (toplam zararın yarısından fazlası); beşi de 06.11 15:50–16:22 arası, stop ve oynaklık sınırı yokken açıldı.
Tüm zarar edenler −460,62 $, tüm kazananlar +145,34 $.

## 6. Oynaklık (VOL60) ne kadar doğru? (E–F, 38 işlem)
- Hesap doğru (§1). VOL60 ortanca %0,75 (aralık %0,22–%1,95).
- Girişten sonraki 60 dk (gerçek 1 dk mumlar): en yüksek ortanca +0,41 salınım, en düşük ortanca −0,68 salınım; 60 dk getirisinin
  büyüklüğü ortanca 0,34 salınım, std'si 0,69 salınım.
- 60 dk içinde +1 salınıma değen **5/38 (%13)**, −1'e değen **11/38 (%29)**. Aynı coinin önceki 25 saatinde (VOL60'ı ölçen veri)
  rastgele bir dakikadan başlayan 60 dk'da: +1'e %39, −1'e %35.
- Yorum: 25 saatlik ölçü girişten sonraki saatten büyük (girişler "yerinde saymış" anlarda) → sınırlar uzak kalıyor, çoğu işlem
  60 dk kontrolüne kalıyor; değen işlemlerde de aşağı yön daha sık.

## 7. Seçim ve çıkış zamanlaması (gerçek fiyat)
- Girişten 60 dk sonra (çıkış kuralından bağımsız): 85 işlemin 32'si yukarıda; coin ort. −%0,34, aynı anda BTC −%0,02
  (coin − BTC −%0,32). E–F'de coin −%0,07, BTC +%0,04, yükselen 15/37.
- Çıkıştan 60 dk sonra: kâr aldan sonra fiyat ort. −%1,06 (21'in 4'ü yukarıda → kâr al zamanı iyi); zarar stopundan sonra +%0,54
  (21'in 13'ü yukarıda → stoplar dibe yakın sattı); 60 dk kontrolünden sonra +%0,07 (28'in 10'u yukarıda → nötr).
- Dolum bekleme (karar → ilk dolum) ortanca: E (geri çekilmede al) 5,5 dk, F (hemen al) 1,2 dk. Alışların hepsi bekleyen emir
  (maker), satışların %24'ü.

## Sonuç
1. Kod doğru çalışıyor; kayıp hata yüzünden değil.
2. Zararın yarısı 06.11 öğleden sonraki stopsuz / oynaklık sınırsız 5 işlemden (−171 $; JCT tek başına −95 $). O kurallar artık yok.
3. Şu anki düzende (±1 salınım) kayıp küçük ama sürekli: 38'de 6 kazanma (başa baş %35). Sebep: aldığı coin sonraki saatte
   piyasadan iyi gitmiyor (seçim ≈ yazı tura) ve fiyat sınırlara değmeden 60 dk dolunca "kârda değilse sat" ile küçük zararla çıkıyor.
4. Masraflar: komisyon 58 $ + demo fiyat farkı ≈ 69 $ (gerçek hesapta demo farkı olmaz, komisyon olur).

---

# Ek (07.11 13:20 TR): şu anki kurallar, coinler nereden takılıyor, bot neden kazanmıyor

## 9. Önceki bölümler hangi kurallara göre?
86 işlemin hiçbiri şu anki kurallarla (Değ. 18, 07.11 12:15 TR) açılmadı (0 işlem). "Yerinde saymış" şartıyla (08:19 TR'den beri)
13 işlem: 1 kazanan, −44,65 $ (10'u 60 dk kontrolü). Çıkış kuralları (±1 VOL60) 38 işlemde aynı. Yani §2–§7 çoğunlukla ESKİ giriş
kurallarının sonucudur. Aşağıdaki §10–§11 şu anki şartları ölçer.

## 10. Şu anki şartlarda coinler nereden takılıyor (`gate_now.py`, 12 karar anı 12:20–13:15 TR, 360 coin-karar)
Bağımsız yeniden hesap (gerçek 1 dk mumlar + tam defter arşivi, bot.py'siz): 7 şartın 7'si 360/360 botla aynı, fark 0.
| Şart | Tek başına geçen | Sırayla kalan (karar başına) |
|---|---|---|
| son 4 sa artıda | %32 | 9,7 |
| yükseliş hızlanıyor (LC ≥ 2) | %12 | 2,3 |
| son 60 dk yerinde (±%0,2) | %31 | 1,9 |
| 15 dk alıcı baskın (> 0,5) | %37 | 0,5 |
| 15 dk hacim normalden yüksek | %57 | 0,2 |
| defter ±%0,2 alış fazla | %46 | 0 |
| defter ±%0,5 alış artıyor | %51 | 0 |
Tek şarttan kalanlar (6'sını geçmiş): LC 2 (XMR 12:40, AAVE 13:10), alıcı 2 (DOGE 12:30, BTC 12:35), hacim 1 (XMR 13:15),
defter ±%0,2 2 (ETH 13:10, 13:15). Fiyat şartlarını geçip akışta kalanların çoğunda alıcı payı 0,26–0,48 (satıcı baskın).

## 11. Bot neden kazanmıyor: sinyal ölçümü (`why_signal.py`)
Botun kendi kaydı (scores: 192 karar anı × 30 coin, 06.11 21:10 → 07.11 13:15 TR, 17 saat) + sonrasında gerçek fiyat.
"Fazla getiri" = coin − aynı andaki 30 coinin ortalaması. Belirsizlik saat bazında (≈ 15 bağımsız saat; kaba, tek gün).
| Şart (geçen − geçmeyen, fazla getiri) | 15 dk | 60 dk | 120 dk |
|---|---|---|---|
| son 4 sa artıda | −0,03 ± 0,03 | **−0,10 ± 0,09** | **−0,20 ± 0,14** |
| LC ≥ 2 | +0,01 ± 0,02 | −0,00 ± 0,07 | −0,08 ± 0,12 |
| son 60 dk yerinde | −0,02 ± 0,02 | −0,01 ± 0,05 | +0,00 ± 0,07 |
| şu anki fiyat şartı (3'ü birden) | −0,00 ± 0,06 | −0,02 ± 0,10 | −0,07 ± 0,18 |
(yüzde puan, %95 aralık)
- Puan ↔ sonraki fazla getiri: ρ +0,01 (15 dk), +0,01 (60 dk), −0,02 (120 dk) → seçim rastgele kadar. Bileşenlerin hiçbiri
  anlamlı pozitif değil. 24 sa değişimi (CHG24) ρ −0,13 ± 0,10 (60 dk), −0,17 ± 0,08 (120 dk): çok yükselen sonra GERİDE kaldı.
- Şartı geçenlerin mutlak getirisi 60 dk sonra −%0,09 ± 0,11 (liste −%0,07). Masrafı karşılamak için ≈ +%0,17 gerekirdi
  (komisyon %0,07 + demo farkı ≈ %0,1).
- Çıkış kuralları (±1 VOL60, 38 işlem, gerçek fiyat, masraf hariç): gerçek çıkışlar −49,13 $; aynı girişlerle tam 60 dk tutup satmak
  −36,24 $. Fark −12,89 $; çoğu zarar stopundan (−62,51 vs −40,16: stoplar sonradan toparlanan dipte sattı). Kâr al +8 $ katkı.
- Hacim/defter akışı: yalnız 12 karar anı (2 saat), 60 dk sonucu belli olan 0 → yorum yapılamaz; 15 dk ρ −0,06…+0,02.

Sonuç: kayıp çıkıştan çok GİRİŞTEN. Botun ana fikri "yükselene bin" bu 17 saatte işlemedi (yükselenler sonra geride kaldı);
LC ve "yerinde" şartı bunu ≈ 0'a çekiyor ama artıya çevirmiyor. Kenar ≈ 0 iken her işlem masraf kadar (≈ 2–3 $) kaybettirir.
Sınır: tek gün, tek piyasa havası; kanıt değil, ama botun ihtiyacının tersi yönde.

## 12. 06.11 15:00 TR "hep birlikte yükseliş" (`tide.py`, `burst.py`)
- Bot 15:00 kararında 7 coin aldı, 7'si 7–29 dk'da +5 $ kâr al. Aynı anda listedeki 30 coinin 26'sı 30 dk içinde +%0,37'ye değdi
  (liste ort. +%0,51) → seçim değil, piyasa. Sonraki saatlerde aynı ayarlarla 12 işlemde 1 kâr al; o ayarların toplamı −135,65 $.
- Yol (14:30'a göre, liste / BTC): 15:00 +0,21 / +0,04 → 15:05 +0,33 / +0,06 (önce altcoinler; 4 dk'da 11 coin +%0,2, BTC 25. dk)
  → 15:20–15:30 ikinci dalga +0,72 / +0,28 → 16:05 −0,12 / −0,26 (geri verdi).
- 15:20–15:25 BTC vadeli hacim 62 M$ (normalin 2,4×), alıcı payı %71; spot yalnız 3,5 M$ (1,2×). BTC açık pozisyon +%0,36 (yeni long,
  short kapatma değil). Fonlama (+%0,0055), hesap long/short oranı (3,15–3,17), vadeli−spot farkı (−3…−5 bps) değişmedi.
  15:30'dan sonra satıcılar (%34 alıcı), 15:35 spot satışı (2,9× hacim, %26 alıcı).
- Haber: bu yarım saat için bulunamadı; ABD istihdam raporu takvimde 16:30 TR'de (yükselişten 1 saat sonra).
- Botun 15:00 kaydı: şartı geçen 12/30 (piyasa 4 saattir yükseliyordu: ortanca son 4 sa +%1,02, son 60 dk +%0,31); etiketler karışık
  (yeni alıcı 11, short kapatma 10, yükseliş yok 9); defter dengesi 15:00–15:20 düşüyordu (+0,058 → +0,012). Yükselişi önceden gösteren
  bir iz yok.

## 13. Tüm veride "birlikte hareket" (`tide_all.py`, 05.11 11:00 → 07.11 12:55 TR, 40 coin, gerçek 1 dk)
- Birlikte hareket: 5 dk getirilerde iki coin arası korelasyon ortancası 0,58; BTC ile 0,67. 30 dk'da bir coinin hareketinin ortanca
  %64'ü piyasa ortalamasıyla açıklanıyor (çeyrekler %44–%75). Altcoin ortalaması dalgalarda BTC'nin ≈ 2 katı hareket ediyor.
- 86 işlem (1 dk kapanışlarla, masraf hariç, yaklaşık): piyasa kısmı −96,72 $, coine özel (seçim) kısmı −99,26 $. İşlem süresince piyasa
  53 işlemde düştü (ort. −6,78 $), 33'ünde yükseldi (ort. +1,34 $). Kaybedenlerin 45/61'inde, kazananların 17/25'inde piyasa aynı yöndeydi.
- 30 dk'da ≥ ±%0,4 piyasa dalgası: 49 olay (25 yukarı, 24 aşağı; ≈ saatte 1). Yükselişlerin 16/25'i sonraki 60 dk'da geri döndü (ortanca
  −%0,28), düşüşlerin 14/23'ü toparlandı (+%0,34). BTC vadeli hacmi yükselişlerin yalnız 6/23'ünde normalin 1,5 katını geçti.
- Önceden gösteren var mı: önceki 15 dk BTC alıcı payı ↔ sonraki 30 dk piyasa ρ −0,12 (98 pencere, rastgele bandı ±0,20); aynı pencere
  içinde +0,25 (eşzamanlı). Botun 30 coin ortalamaları (30 pencere, bant ±0,36): şartı geçen sayısı +0,04, TAKER_1 +0,09, IMB1_1 +0,02,
  BIDSHARE_1 +0,12, r_t +0,08, RET_4 −0,35 (sınırda), OI_1 +0,31 (sınırda).

## 14. Öneri adaylarının büyüklüğü (`candidates.py`)
- DÜZELTME (§13): "düşüş dalgalarının 14/23'ü toparlandı" sonradan seçilmiş pencerelerdendi. Anında bilinebilir tetikle (piyasa son 30 dk
  −%0,4'ü ilk geçtiği an, 31 tetik): sonraki 60 dk ort. −%0,25, ortanca +%0,03, yukarı 16/31 → "düşünce al" izi YOK.
  Yükseliş tetiği (+%0,4, 32): sonraki 60 dk ortanca −%0,25, yukarı 11/32 (tüm anlarda yukarı %49).
- Son 4 sa en çok düşen 3 coin: listeye göre +%0,13 ± 0,14 (60 dk), +%0,28 ± 0,15 (120 dk); MUTLAK +%0,05 ± 0,21 / +%0,15 ± 0,25.
  En çok yükselen 3: −%0,22 ± 0,14 (60 dk), −%0,28 ± 0,18 (120 dk).
- Düşen 3 al − yükselen 3 sat farkı: +%0,35 ± 0,23 (60 dk, 16 saatin 12'si artı), +%0,55 ± 0,29 (120 dk, 15 saatin 14'ü artı).
  Masraf iki bacak: demo ≈ %0,34, gerçek komisyon ≈ %0,14.
- "short kapatma + spotsuz" engeli: engellenen − diğer yükselenler +%0,03 ± 0,08 (16 saat, 539 coin-karar) → etkisiz.
- Sınır: hepsi 06.11 21:10 → 07.11 13:15 TR (17 saat) ya da ≈ 50 saat; tek piyasa havası.

## 15. Öz denetim ve DÜZELTMELER (07.11 14:30 TR, kullanıcı: "doğru cevap verdin mi, doğru veri, varsayım?")
1. **Masraf eşiği yanlış yüksekti.** Cevaplarda "%0,17 (komisyon %0,07 + demo %0,1)" kullanıldı. Veri (86 işlem, 110.064 $ giriş):
   komisyon %0,053, demo farkı %0,063 (kâr al zamanlaması hariç) – %0,091 (tümü) → **≈ %0,12–0,14**. Sonuç: en çok düşen 3 coinin 120 dk
   mutlak getirisi (+%0,15 ± 0,25) masrafla ≈ başa baş (açıkça altında değil); iki bacaklı sepet masrafı ≈ %0,25–0,28 (%0,34 değil).
2. **Al-sat ölçümünün belirsizliği küçük gösterildi.** 120 dk pencereler saatlik ızgarada üst üste biniyordu. Üst üste binmeyen
   sepetlerle: 60 dk +%0,38 ± 0,32 (≈ 15 sepet, %72'si artı), **120 dk +%0,58 ± 0,59 (≈ 7 sepet, %78'i artı)** → 120 dk sonucu sıfırdan
   ancak kıl payı ayrılıyor. "15 saatin 14'ü artı" çakışan pencerelerdendi.
3. **Çoklu deneme / seçim yanlılığı söylenmedi.** Aynı 17 saatte ≈ 40 ölçü denendi, en iyi görünen seçildi → canlıda etki büyük
   ihtimalle ölçülenden küçük.
4. "Rastgele 7 coin ≈ 3'te 1 ihtimalle 7/7" coinleri BAĞIMSIZ varsaydı (söylenmedi); birlikte hareket ettikleri için ihtimal daha
   yüksek → "seçim değil piyasa" sonucu değişmez.
5. "Kâr aldan sonra fiyat −%1,06 → kâr al zamanı iyi": 21 işlemin çoğu 06.11 öğleden sonra; piyasa düşüşünden ayrılmadı → aşırı yorum.
6. "Haber bulunamadı" yalnızca iki kısa web aramasına dayanıyor. "Haftalık momentum" akademik bilgisi bu oturumda doğrulanmadı.
7. Ölçüm ↔ bot farkı: ölçüm karar anı kapanış fiyatıyla; bot bekleyen emirle dakikalar sonra giriyor (ilk sepette BNB SAT 13 dk sonra
   695,49 yerine 694,80'de doldu, −%0,10 aleyhte).
Doğru olanlar: işlemler borsadan (86/86), gerçek fiyatlar taze (6.027/6.027), şart / VOL60 / büyüklük bağımsız hesapla aynı; varsayımlar
(1 dk kapanışla yaklaşık ayrıştırma, kâr al demo farkı = zamanlama) yazılıydı.
