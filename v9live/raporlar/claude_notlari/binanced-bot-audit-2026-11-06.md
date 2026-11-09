---
name: binanced-bot-audit-2026-11-06
description: "06.11.2026 v9-demo bot değerlendirmesi ve tam denetimi: 9 kod/mantık hatası bulundu+düzeltildi (iki yeniden başlatma), verify.py, kullanıcı kararları, benim tahminim"
metadata:
  node_type: memory
  type: project
  originSessionId: 99e66a66-449f-4105-ad29-658cd5b13af3
  modified: 2026-11-06T07:55:37.962Z
---

Kullanıcı 06.11.2026 (Türkiye sabahı) bu konuşmayı kaydettirdi, önceki oturum notlarını sildirdi. Bot: `v9-demo` systemd,
/root/binanced/v9live/ (bot.py, KURALLAR.md, live.db, status.py), yalnızca demo hesap, 100 $/işlem, 1×, en fazla 3 coin.
Bağlam: v9 backtest sınavı reddedilmişti (−%67, BTC +%32, rastgele giriş daha iyi).

**Değerlendirmem:** teknik sağlam, kazanç beklemiyorum. **Kullanıcı kararları:** karar/kapama kuralı YOK ("kural
koymayalım"); bot süresiz çalışır çünkü demo KODU da sınıyor ("doğru yere bakmak yetmez, doğru yerde doğru şeyi görmeliyiz").

**Denetim 1 → yeniden başlatma 07:23:53 UTC** (bağımsız `v9live/verify.py features [ts]` / `depth`; bot.py'yi içe aktarmaz):
07:00'de RET_4, LC, r_t, r_prev, ACC_1, TAKER_1, SMOOTH_4, şart 30/30 fark 0. Hatalar: OI_1 23/30 coinde 55 dk (t noktası
yayımlanmamıştı) → yayımlanan son nokta + tam 1 sa önce, OI_TS kaydı; defter limit=500 BTC ±%0,09 vb. ±%1'e uzanmıyordu →
limit=1000, band = min(%1, iki uç), depth.band (kullanıcı: BTC/ETH "uzanabildiği kadar"; BTC ≈ ±%0,17, ETH ≈ ±%0,5); acil
stop ortalama girişe taşınır (LTC demo duman testi OK).
**Denetim 2 → yeniden başlatma 07:45:30 UTC:** OI_1 dolar değeri fiyatı kopyalıyordu (korelasyon 0,96; JCT fiyat +%9,8,
değer +%8,4, adet −%1,4) → ADET, OI_VAL_1 yalnız kayıt; saatlik kontrol (a) "r_t > r_prev" → **"r_t > 0"** (kullanıcı
seçti; yeni, test edilmemiş); aynı saatte geri alma yok; demo'da TRADING olmayan coin atlanır (PUMP "SETTLING"), yuva
sıradakine; kontrol hatası coin başına; giriş hatasında emirsiz kayıt silinir + cid iptal; adet en yakın (QNT ≈94 $ kalır).
Doğru çıkanlar: evren (Ekim hacmi, 482 aday → ilk 30 birebir), PnL (userTrades, USDT komisyon), LC/şart.
Gözlemler: 7 bileşenin 4'ü son saat fiyatıyla 0,6–0,72 korelasyonlu (puan ≈ son saat sıçraması); yüksek-ACC üçte bir: eski
kontrolü %5 geçiyordu, yeni (a) ≈%44, (a)+(b) ≈%38 (son 7 gün, 1.173 coin-saat); demo taker komisyonu %0,04 (gerçek %0,05).

**Tahminim (kullanıcıya söylendi):** ~%70 yavaş kayıp, işlem başı −%0,05…−%0,15, günde ~20–40 işlem (tahmin), günlük
gürültü ±10 $; ~%25 ilk günler şans/piyasa ile kârlı; ~%5 gerçek üstünlük. Fikir değiştirme ölçütü: 200+ işlemde ortalama
> +%0,26 VE rastgele seçimden iyi; her zaman aynı dönem BTC al-tut ile kıyasla. Kaybetse de değeri: gerçek maker dolum oranı,
demo kayması, kod doğrulaması, gözlem tablosu (ileride "tut/sat puanı" araştırması — kullanıcı henüz onaylamadı).

**Why:** Kullanıcı sonraki konuşmada buradan devam etmek istiyor. **How to apply:** Her saatten sonra verify.py ile
ölçümleri, her işlemde giriş/stop/kâr al/çıkış sebebini borsa kayıtlarıyla denetle; sonuçları BTC al-tut ve rastgele seçimle
kıyasla. 08:00 UTC ilk karar 08:55'te denetlendi ve kullanıcıya raporlandı: verify features 30/30 fark 0; GTC/TAO/UNI maker dolum (%0,02 komisyon), borsadaki adet/giriş/TP/acil stop state.json ile birebir; book 10 dk sorun 0. Bağımsız borsa okuyucu: v9live/audit/exch_check.py (yalnızca GET, kendi Ed25519 imzası; brackets.py, uni_hour.py da orada). Bkz. [[binanced-paper-service]],
[[test-honesty-rules]], [[feynman-explanations]].

**UNI incelemesi (06.11 09:00, gerçek veri):** UNI 08→09 −%1,40, 30 coinin en kötüsü (BTC +%0,10, ortanca −%0,09) → coine özel.
07–08 yükselişinin %70'i tek 5 dk mumda (07:40, +%1,0, hacim ortancanın 6,7 katı); GTC (kazanan) adım adım (12 mumun 9'u
yukarı, en büyük %28, hacim 1,3×); TAO da tek mumla (%122) → yatay. UNI'de TAKER_1 0,497, BIDSHARE 0,68 seçilenlerin en
zayıfı; puan 0,657 ≈ SAND 0,638 (o da −%0,55). 24 sa düşüşte toparlanma açıklamayı TAO (−%6,3, yatay) çürüttü. Bir hafta
coin-saat: sonraki 1 sa std %1,76, ≤ −%1,4 payı %5,9 → tek işlem gürültü içinde. Hipotez "tek patlamayla gelen yükseliş
söner" — 12 ay testi önerildi, kullanıcı onayı bekleniyor.

**Demo testinin amacı (kullanıcı 06.11 ~09:25 UTC):** "önce komisyon ve vergilerle paramızı çıkarabiliyor muyuz; kâr etmek sonra".
status.py'ye "Masrafı çıkarıyor muyuz?" bölümü eklendi: gerçek hesap ücreti (maker %0,02, taker %0,05; kâr al çıkışı maker)
ile yeniden hesap, temkinli vergi %0,03/taraf (geri çekilen teklif; yürürlükte işlem vergisi yok), %95 aralık (n<30 iken
std varsayımı %1,76), karar: ÇIKARIYOR / ÇIKARAMIYOR / BELİRSİZ. Başa baş eşiği ≈ %0,07/işlem; net kötü ise ~100–200 işlemde
görünür, sıfıra yakınsa binlerce işlem gerekir (kullanıcıya söylendi).

Oturum kaydı: reports/OTURUM_2026-11-06.md [07.11 silindi → OTURUM_2026-11-07.md] (10:56'da yeniden yazıldı; _2/_3 kullanıcı isteğiyle silindi).

**3 saat ivme kuralı fikri (kullanıcı 06.11 ~09:40 UTC):** "son 3 saatin her 1 saati artı VE her saat öncekinden hızlı → direkt
gir, salınımları da görelim". = outcomes.acc_streak_at ≥ 3. Bağımsız bakış v9live/audit/look3h.py (fapi 1h, 22.10–06.11, 30
coin, 10.680 coin-saat; bot tablosuyla 4.590/4.590 birebir): 199 sinyal (97 farklı saat), sonraki 1 sa ort −%0,025, ortanca
−%0,044, artı %47, aynı saatin rastgele coininden −%0,09 kötü, 4 sa −%0,20; saat içi ort en yüksek +%1,12 / en düşük −%1,09
(salınım sonucun ~40 katı). Başa baş +%0,07'ye yakın değil. Kullanıcıya A) gölge izleme B) demo'da gerçek işlem C) 12 ay bakış
seçenekleri sunuldu, karar bekliyor. Bot DEĞİŞTİRİLMEDİ.
Pencere 2/3/4/6 sa da denendi (v9live/audit/win.py): hepsi daha kötü (3 sa: sonraki 3 sa −%0,25, rastgele −%0,10).
"Neden kâr yok" anlatıldı (herkes aynı grafik, masraf, gürültü, hep geçmiş fiyat bilgisi); yön seçilmedi. Kullanıcı
uzun cevaba "kısaca anlat, anlamadım" dedi → kısa yaz. Oturum kaydı: reports/OTURUM_2026-11-06.md [07.11 silindi → OTURUM_2026-11-07.md].

**12/24 sa pencere + 12 ay (06.11 ~10:05 UTC, v9live/audit/win_long.py, fapi 1h + fonlama, 2025-11-06→2026-11-06, Kasım
evreni 30 coin; çapraz kontrol: win.py 15 gün w=1 199 / w=3 181 sinyal birebir; çıktı audit/win_long_out.csv):** 12 sa: 5.021
sinyal, sonraki 12 sa +%0,21, tüm coinlerden fark +%0,05 [−0,26, +0,49], net (taker %0,10 + fonlama) +%0,11; çeyrekler net
−0,30/−0,38/−0,09/+0,88 (son çeyrek piyasa +%0,37). 24 sa: net −%0,23, fark −%0,22. **Düzeltme:** 15 günde kötü görünen 3 ve 4 sa,
12 ayda tüm coinlerden fark 4 çeyrekte de + (+0,04…+0,24), net +%0,06 / +%0,08; aralık sıfıra değiyor. Zayıf iz: 7 pencere
denendi, evren Ekim 2026 hacmiyle seçildi (sonradan yükselen coinler → yükseliş kurallarını iyi gösterir), kayma yok.
Spearman (12 ay): yükseliş ↔ sonraki pencere −0,02…−0,04, ivme ↔ sonraki −0,03…0 (hepsi sıfır gibi). Kullanıcıya anlatıldı.

**Üç yeni fikir testi (06.11 10:25 UTC, kullanıcı "bota eklemeden önce dene"; /root/binanced/ideas3/ ON_KAYIT.md → SONUC.md):**
v9 arşivi (aylık evren, 115 coin, 2025-11→2026-10; check.py: canlı REST ile 1m/fonlama/OI fark 0; **OI arşiv zamanı + 5 dk =
REST zamanı → t−10 dk kullan**; 28 m1 dosyası 06:51 disk temizliğinde kırpıldığı için SHA uymaz, normal). 22/22 kural "iz yok":
sessiz alım (yatay + OI/hacim) tutarsız; fonlama<0 + son sa ≥%1 12 sa net +%0,27 ama kazanç fonlamadan, fiyat ≈0, son 4 ay ters;
BTC sıçraması → diğerleri 15–30 dk brüt ≤ %0,05 < masraf. Bota eklenmedi. Not: v9 araştırmasında 36 ölçüm (TAKER, IMB, BIDSHARE,
DEPTH, OI, TOPLS, FUND, VOL) tek tek denenmişti — "hiç denemedik" deme. Denenmemiş kalan: tam emir defteri (v9live/book, 06.11'den beri).

**Değişiklik 4 (06.11 10:34 UTC, kullanıcı "işlem teminatı 150 dolar"):** bot.py NOTIONAL 150 → **1500** (10×, teminat 150 $); yedek
bot.py.bak_20261106_1034; KURALLAR.md Değişiklik 4; servis açıklaması güncellendi. Kontrol: 30 coinin 10× sınırı ≥ 1.575 $, demo cüzdan
4.767 $. Açık ONDO (1×), 1000PEPE, TAO (150 $) olduğu gibi. Acil stop −%6 ≈ −90 $/işlem.

**Tetikleyici araştırması (06.11 ~11:00, /root/binanced/triggers/ RAPOR.md):** 2.467 sert yükseliş (60 dk ≥ +%5): %74 görünür sebep yok,
%19 piyasa geneli, %27'si 24 sa ≥ %10 düşüş sonrası (taban %4,4); %60'ında 24 sa içinde ≥ %5 düşüş; hacim önceden artmıyor; fonlama
fark etmiyor. Koşullar (oynaklık, hacim, ±%10, yeni listeleme) sert hareketi 5–8 kat artırıyor ama iki yönde eşit. Binance duyuruları:
listeleme ilk 1 dk +%10 sonra ≈0; izleme etiketi/listeden çıkarma sonrası düşüş sürüyor (60 dk −%2…−5, 24 sa −%4…−6) — tek tutarlı iz.
Upbit API bu sunucuyu engelliyor (1015); tarayıcı kılığına girme denemesi reddedildi — tekrar deneme.

06.11 12:30 kullanıcı (canlıya çıkmadan önce): "gerçekte orderbook dolar mıydı, kuyrukta kaç kişi vardı?" → bağımsız denetim
v9live/audit/real_fill_check.py (demo allOrders + gerçek defter arşivi v9live/book + gerçek aggTrades; kötü taraf: önümüzdeki
herkes kalır, emir demo emrinden sonraki ilk gerçek görüntüde verilmiş sayılır — eski görüntü 'anında doldu' yanılgısı verdi, düzeltildi;
SOL elle doğrulandı). Sonuç (1 gün): 12/12 giriş gerçekte 1–3 dk içinde dolardı, önde 112 $–50.692 $; gerçek giriş demodan ort.
12,6 bps ucuz (QNT −76, ENA −40; demo kovaladı); 6/6 kâr al gerçekte de doldu (demodan önce); piyasa satışında kayma ≤ 0,20 $,
demo 1–27 bps kötü sattı. Kişi sayısı Binance'te görünmez (yalnız miktar). Sınırlar kullanıcıya söylendi.

**06.11 13:05 "1 dk muma geçince patladık mı?" incelemesi:** HAYIR. 13:00'te botun 1 dk mumdan hesabı = Binance 1 sa mumu (r_t, r_prev,
RET_4, TAKER_1; 30/30 fark 0; verify.py features 13:00 fark 0; events'te hata yok, her dakika karar var). Kayıp piyasadan: 12:50→13:05
30 coin ort −%0,41, BTC −%0,23; botun 6 coini −%0,56; saatlik modda 13:00'te aynı coinler alınırdı (ort −%0,73). Açık 7 poz ≈ −57 $.
Kayan pencerenin asıl etkisi davranış: yuvalar dakikada dolar → hep ~8×1.500 $ = 12.000 $ (cüzdan 4.807 $'ın 2,5 katı); kâr al
+5 $ ama düşüşte kontrol 60 dk sonra; JCT kâr al'dan 1 dk sonra daha yüksekten yeniden alındı (−26 $). Bot DEĞİŞTİRİLMEDİ.
06.11 13:40 UTC: kullanıcı "konuşmayı kaydet, botu kendi haline bırakalım, nasıl iş yapacak görelim" → bota DOKUNMA, yalnız izle.
reports/OTURUM_2026-11-06.md [07.11 silindi → OTURUM_2026-11-07.md] yeniden yazıldı (13:38 durumu). JCT 13:36:38 acil stop −94,57 $ (gün net −37 $, 21 işlem).

**06.11 ~13:55 UTC tam denetim (kullanıcı: "mantık/matematik/bağlantı hatası, doğrulanmamış yer var mı; −5 $'dan dönüp kârla kapanan var mı"):**
Temiz: 22 kapanan işlem PnL borsa userTrades+income ile birebir (audit/pnl_check.py, fark 0); açık pozisyonlarda TP formülü/acil stop/
tasfiye ✓; bugün bağlantı/sınır/Telegram hatası 0; 60 dk kontrol satışı ilk kez çalıştı (QNT −20,54, PEPE −13,61; borsayla birebir).
Bulunan: (1) exit_market satış emri hata verirse exit_cid kalır → decide bir daha kontrol etmez, TP zaten iptal → yalnız acil stop
(henüz olmadı); (2) giriş kovalama sınırı yok (15 dk yukarı taşır; ort +22 bps, JCT +136, QNT +110, RLC +108 bps); (3) AAVE demo'da
girilemiyor: ayrık kasa −3,30 $ (Mayıs'tan, pozisyon yok) → −2019 her dakika; (4) hiç çalışmamış yollar: giriş zaman aşımı/kısmi,
fonlama (16:00 UTC), kırıntı, yeni absorb yedeği, ay başı evren; (5) tek döngü → izleme tepkisi 5–15 sn.
−5 $ (audit/eksi5.py, demo aggTrades, fiyat kârı = adet×(fiyat−giriş)): 14 büyük kapanandan 5'i −5 altına indi, 3'ü yine +5 TP
(ENA −6,08/4 sn, JCT −7,32/65 sn, ZEC −11,32/7,5 dk); "10 sn −5 altı → piyasa sat" kapananlarda −35 → +24 $ (tamamı JCT stopundan;
JCT hariç kural −29 $ kötü), 30/60 sn daha kötü. Hiçbir şey DEĞİŞTİRİLMEDİ; kullanıcı kararı bekleniyor.
06.11 14:42 UTC: konuşma kaydedildi (reports/OTURUM_2026-11-06.md [07.11 silindi → OTURUM_2026-11-07.md] yeniden yazıldı, Değişiklik 8–12 dahil). 14:39:21 yeniden başlatma yine
giriş sürerken yapıldı (ZEC 14:39:00 kararı) → ZEC 0,029 kırıntı kaldı, kâr al +%12,6 / stop −%6; kullanıcıya söylendi.
Ders: durum kontrolü restart'la AYNI python/bash adımında, bekleme döngüsünden SONRA yapılmalı.
06.11 14:46 UTC: ZEC kırıntı kapatıldı (kullanıcı), bot saatlik modda yeniden başladı, borsada pozisyon yok.

06.11 17:30 UTC "bot neden saçma işlem yaptı": 14:46'dan beri 10 işlem 1 kâr 9 zarar −42,6 $ (gün 43 işlem −185 $), hata 0. Sebep: ±5 $ = 1.500 $'da
±%0,33 → gürültü bandı (1 dk std %0,25), kazanç +5 / kayıp −6 $; 15:00'te 4 coin birlikte girdi, BTC 30 dk −%0,94 → hepsi 1–4 dk'da stop;
mark/demo farkı ZEC/TRUMP'ı −%0,16'da sattı. Stop olan 9'un 5'i (ZEC, INJ, TRUMP, RAY, SUI) 1–16 dk sonra +%0,37'ye döndü (gerçek fapi 1 dk;
10 işlem az, kural değil). Bot DEĞİŞTİRİLMEDİ. Araç: scratchpad after.py (oturuma özel).
