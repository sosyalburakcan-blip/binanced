# v9 demo botu: kurallar (kullanıcı kararları, 06.11.2026)

**Yalnızca Binance DEMO hesabı (demo-fapi.binance.com). Gerçek para yok.** İmzalı istemci başka adrese istek atmayı
reddeder. Sinyal ve fiyat verisi **gerçek** piyasadan (fapi.binance.com, herkese açık) gelir. Emirler demo defterinde
dolar: demo defteri ayrı ve sığdır, fiyatı gerçekten birkaç baz puan sapabilir.

## Coin listesi (07.11 04:30:44 UTC'den beri; geçmiş: Değişiklik 11, 13, 15)
Her dakika, gerçek piyasadaki TÜM USDT sürekli vadeli coinlerden (dayanak COIN, TRADING, sabit coin değil, demo'da TRADING):
1. ~~Binance 24 sa değişimi > 0 olanlar~~ — **07.11'den beri bu şart YOK** (listede de girişte de; düşen coin de girer),
2. 24 sa USDT hacmine göre sıralanır,
3. sırayla yürünür; **VOL60 ≤ %2** olan coin alınır, büyükse (ya da ölçülemezse) atlanır, yerine sıradaki girer; **30** coin
   dolunca durulur. VOL60 = "normal 1 saatlik oynama": son 1.500 adet 1 dk mum kapanışıyla, 60 dk arayla tüm getirilerin
   (üst üste binen pencereler) std'si; :00, :05, … sınırında hesaplanır.
Liste `uni24` (vol60 sütunu), alınmayanlar `uni_excl` (vrank = hacim sırası). Karar o anki listeyle verilir; açık pozisyonun coini
listeden çıksa da izlenir. 18:05 denemesinde alınmayan 8 coin: AKE %13,4, JCT %6,1, CYBER %4,8, BIRB %4,5, IDOL %3,4, ON %3,4,
ICNT %3,1, ONE %3,0. (06.11 14:13'e kadar: geçen ayın hacmine göre sabit 30 coin.)

## Karar zamanı — 5 DK'DA BİR (06.11 18:09:53 UTC'den beri; geçmiş: 12:45–14:39 her dakika, 14:39–18:09 saat başı)
Bot :00, :05, :10, … dakika kapanışından 12 sn sonra ölçer, puanlar, açık pozisyonları kontrol eder ve boş yuva varsa girer.
Aşağıda "son saat" = **son 60 dakika**, "son N saat" = **son N × 60 dakika**, o andan geriye; fiyatlar gerçek piyasa 1 dk
mumlarından. **Uçların ortalaması (18:09'dan beri):** her pencerenin uç fiyatı tek bir kapanış değil, o anda biten **son 5 adet
1 dk mum kapanışının ortalaması** (LC, son saat, önceki saat, ACC_1 ve SMOOTH_4'ün payı; SMOOTH_4'ün yol uzunluğu ve R30 ham).
Ham son 60 dk (`r_t_raw`) ayrıca kaydedilir ve etiketlerde kullanılır. İstisnalar: `OI_1` Binance 5 dk'da bir yayımladığı için
5 dk adımlarla kayar; `SPOT_REL_1`'in tabanı (168 saatlik ortanca) saatte bir yenilenir; `outcomes` gözlemi saatte bir kalır.
**1. Ölçüm.** Her coin için, gerçek piyasa verisiyle:

| Ad | Ne ölçer |
|---|---|
| R30 | coinin ham son 30 dk getirisi: karar anında biten 1 dk mumun kapanışı / 30 dk önce biten kapanış − 1 (Değ. 26) |
| MKT_30, MKT_N | PİYASA son 30 dk: o kararın listesindeki coinlerin R30'larının eşit ağırlıklı ortalaması ve ölçülen coin sayısı (her coin satırına aynı değer yazılır; Değ. 26) |
| MKT_UP | PİYASA genişliği: R30 > 0 olan coin sayısı (Değ. 27) |
| MKT_5, MKT_PEAK, MKT_PN | PİYASA yolu: idx(m) = listedeki coinlerin c(m) / c(t − 30 dk) − 1 ortalaması, m = t − 30 … t (1 dk kapanışlar, yolu tam olan MKT_PN coin). MKT_5 = idx(t) − idx(t − 5 dk) (son 5 dk); MKT_PEAK = idx(t) − en yüksek idx (son 30 dk tepesine uzaklık, ≤ 0) (Değ. 27) |
| R_5M | coinin ham son 5 dk getirisi (t'de biten 1 dk kapanış / 5 dk önce biten − 1); 60 dk kontrolünün ek süresi (Değ. 29) |
| MKT_JUMP | PİYASA son 2 dk: idx(t) − idx(t − 2 dk) (sıçrama ölçüsü; Değ. 28) |
| MKT_DN, MKT_TROUGH | Değ. 30 (short aynası): R30 < 0 olan coin sayısı; MKT_TROUGH = idx(t) − en düşük idx (son 30 dk dibine uzaklık, ≥ 0) |
| LC_DN | Değ. 30: LC'nin aynası — 2, 3, 4, 5, 6, 8, 12 saatlik pencerelerde sırayla "son N saat < önceki N saat ve < 0" (hızlanarak düşüş) sağlanan en büyük N |
| COIN_J_UP, COIN_J_DN | Değ. 30: coinin son 60 dk'sı içinde (ham 1 dk kapanışlar c(t−60) … c(t)) üst üste binen 2 dk hareketlerinin c(k)/c(k−2)−1 en büyüğü / en küçüğü (tek sıçrama ölçüsü) |
| MKT_TOP | yalnız kayıt: |R30|'u en büyük coinin ortalamaya katkısı = R30 / MKT_N (tek coin sıçraması ortalamayı ne kadar oynatıyor; Değ. 27) |
| LC | ivme puanı: 2, 3, 4, 5, 6, 8, 12 saatlik pencerelerde sırayla "son N saat > önceki N saat ve > 0" sağlanan en büyük N |
| ACC_1 | ivme farkı: son saatin yükselişi − önceki saatin yükselişi |
| SMOOTH_4 | son 4 saatin düzgünlüğü: net yükseliş / dakikalık adımların toplamı |
| TAKER_1 | son saatte alıcı-başlatan hacmin payı |
| IMB1_1 | son saatte ±%1 içindeki alış − satış emri dengesi (dakikada bir alınan defter görüntüleriyle; görüntü 1000 basamak. Binance daha fazlasını vermez: BTC'de ≈ ±%0,17, ETH'de ≈ ±%0,5, ZEC'te ≈ ±%0,97'ye uzanır → band = min(%1, iki ucun yakını), iki taraf eşit genişlikte; band `depth` tablosuna yazılır. Kullanıcı kararı 06.11: "uzanabildiği kadar ölç") |
| BIDSHARE_1 | son saatte alış tarafının ağır olduğu görüntülerin payı |
| OI_1 | açık pozisyon **adedinin** 1 saatlik değişimi (sumOpenInterest; dolar değeri fiyatı da içerdiği için kullanılmaz, yalnızca `OI_VAL_1` olarak kaydedilir): Binance'in yayımladığı son 5 dk değeri (≤ saat başı) ile tam 1 saat öncesi; kullanılan nokta `OI_TS` |

**2. Giriş şartı (Değişiklik 27, 08.11 04:16:36 UTC = 07:16 TR'den beri):** PİYASA şartlarının **dördü birden**: son 30 dk ortalaması
**≥ +%0,10** (MKT_30), **en az 20 coin** son 30 dk artıda (MKT_UP), **son 5 dk artıda** (MKT_5 > 0), son 30 dk'nın **tepesinden en çok
%0,10 aşağıda** (MKT_PEAK ≥ −%0,10) ve **sıçrama değil** (Değ. 28: son 2 dk MKT_JUMP ≤ 0,5 × MKT_30, yani 30 dk yükselişin
yarısından fazlası son 2 dakikada gelmemiş); biri ölçülemezse giriş yok. Eşikler Claude'un seçimi, veriye dayanmıyor. Ve coinde LC ≥ 2 (en az
2 saattir hızlanarak yükseliyor). Değ. 26 (05:43–07:10 TR): yalnız MKT_30 > 0. Son 60 dk için ayrı şart YOK (`ENTRY_RT_POSITIVE = False`). Karar
başına en fazla 1 yeni giriş. İptal edilip kodu ve metni silinenler: coinin "son 4 sa > 0" şartı (RET_4) ve yükseliş sinyali
(Değ. 26); Değ. 17 "yerinde saymış" ve Değ. 18/22 hacim + defter akışı şartları (Değ. 24). Önceki hâller: 06.11 13:17–18:09 son 60 dk
> 0; 18:09–07.11 05:19 > +%0,2; 06.11 14:13–07.11 04:30 Binance 24 sa değişimi > 0.

**2b. YÖN — Değişiklik 30 (08.11 07:01:33 UTC = 10:01 TR'den beri): yukarıdaki şart → LONG; aynası → SHORT.** SHORT şartı: son 30 dk ortalaması
**≤ −%0,10**, **en az 20 coin** son 30 dk ekside (MKT_DN), **son 5 dk ekside** (MKT_5 < 0), son 30 dk'nın **dibinden en çok %0,10
yukarıda** (MKT_TROUGH ≤ %0,10), **düşüş sıçrama değil** (MKT_JUMP ≥ 0,5 × MKT_30: düşüşün yarısından fazlası son 2 dk'da gelmemiş);
ve coinde **LC_DN ≥ 2**. İki yönün piyasa şartı aynı anda sağlanamaz (≥ +%0,10 / ≤ −%0,10) → her kararda en çok bir yön; scores.side
(LONG / SHORT / boş). Eşikler ve short tanımı Claude'un seçimi (long'un aynası), veriye dayanmıyor. **4 yuva iki yöne ortak.**

**3. Puan (07.11 04:56:51 UTC'den beri ACC_1 YOK — Değişiklik 16):** Şartı sağlayan coinlerde LC, SMOOTH_4, TAKER_1, IMB1_1, BIDSHARE_1 ve OI_1'in
(önce ACC_1 de vardı; hâlâ ölçülüp kaydedilir) 30 coin içindeki
yüzdelik sıralarının ortalaması alınır. Hepsinde yüksek değer iyi sayılır (kullanıcı sezgisi). Puanı en yüksek
olanlar boş yuvalara alınır. **Short puanı (Değ. 30, `scores.score_s`):** LC_DN, −SMOOTH_4, −TAKER_1, −IMB1_1, −BIDSHARE_1 ve OI_1'in
sıra yüzdeleri ortalaması (düşüşte satıcı baskısı yüksek iyi; OI artışı iki yönde de yeni pozisyon sayılır). `scores.score` long puanı.

**4. Kontrol (açık pozisyonlar) — 18:09'dan beri: girişten 60 dk sonraki ilk 5 dk sınırında başlar, sonra 5 DK'DA BİR.**
Örnek: 18:23'te doldu → 19:25, 19:30, 19:35… İkisi birden sağlanmalı:
- **(a) yükseliş sürüyor:** son 60 dk getirisi (uçlar 5 dk ort.) **≥ −%0,2** (bant: −%0,2 ile +%0,2 arası "sürüyor" sayılır;
  14:39–18:09 saat başında > 0; 07:45'e kadar "son saat > önceki saat"),
- **(b) kârdayız:** anlık demo fiyatı ≥ giriş × (1 + 2c), yani ≥ +%0,14 (değişmedi).
- **SHORT'ta aynası (Değ. 30):** (a) son 60 dk **≤ +%0,2**, (b) demo en iyi **satış** ≤ giriş × (1 − 2c) (−%0,14); ek süre (Değ. 29)
  son 5 dk **< 0** iken. `checks.bid` short'ta demo en iyi satış, `checks.side` yön.

Biri bile yoksa pozisyon hemen piyasa emriyle satılır. Kontroller yeni girişlerden önce yapılır. Bir coinin kontrolünde
hata olursa o coin o dakika kontrol edilmeden kalır (borsadaki kâr al / acil stop durur), diğerleri sürer.
Satış sebebi `kayan_kontrol` (Telegram: "60 dk kontrolü"; saat başı dönemlerinde `saatlik_kontrol`). Her kontrol `checks`
tablosunda (r_t sütunu 18:09'dan beri uçlar 5 dk ortalamalı).

**5. Seçimde atlananlar:** o turda satılan coin (bir sonraki 5 dk turundan itibaren yeniden girilebilir; 12:45 kullanıcı
seçimi "hemen girebilir" mantığı), demo borsada işleme kapalı coin (ör. PUMP
"SETTLING"), girişi hata veren coin, **"short kapatma + spotsuz" yükselen coin** (06.11 ~11:40'tan beri, aşağıda), **fiyat adımı kaba
coin** (Değişiklik 25: demo fiyat adımı / son 1 dk kapanış `TICK_REL` > %0,1 ya da ölçülemeyen), **60 dk sıçramalı coin**
(Değ. 30: long'da r_t_raw > 0 ve COIN_J_UP > 0,5 × r_t_raw; short'ta r_t_raw < 0 ve COIN_J_DN < 0,5 × r_t_raw, yani son 60 dk
hareketinin yarısından fazlası tek 2 dk'lık sıçramadan; son 60 dk işlemin tersindeyse kural uygulanmaz; ölçülemeyen coine girilmez).
"Short kapatma + spotsuz" engeli yalnız LONG'da. Yuva sıradaki coine verilir.

**6. Etiket ve giriş engeli (06.11 ~11:40 UTC, kullanıcı: "b ekle ve test et etkileyip etkilemediğini").** Her saat her
coine, son kapanan saatin verisiyle "yükseliş kimden geliyor" etiketi konur:
- fiyat son saat artmadıysa → `yukselis_yok`
- açık pozisyon adedi (OI_1) azaldıysa → `short_kapatma` (fiyat çıkarken pozisyon azalıyor: short açanlar geri alıyor),
  arttıysa → `yeni_alici`, ölçülemediyse → `oi_yok`
- spot katılımı: `SPOT_SHARE_1` = spot $ hacmi / vadeli $ hacmi (son saat); `SPOT_REL_1` = bu oran / aynı oranın önceki
  168 saatlik ortancası. < 1 → `spotsuz` (spot her zamankinden geride), ≥ 1 → `spotlu`, spot piyasası yoksa ya da ölçülemezse
  → `spot_olcum_yok`. Spot verisi api.binance.com herkese açık 1 sa mum (1000PEPE → PEPEUSDT); Q, JCT, AGT'nin spotu yok.
- **Engel:** `short_kapatma+spotsuz` olan coine girilmez (`SPOT_FILTER_ON = True`). Ölçülemeyen değerde engel yok.
- Kayıt (gözlem): `DD_48` (son 48 saatin en yükseğine uzaklık), `BOUNCE_48` (en düşüğünden sıçrama), `SPOT_TAKER_1`, BTC'nin
  son saati. Puan DEĞİŞMEDİ: etiket yalnızca seçimde "girme" der.
- **Test:** `labels` tablosu her dakika 30 coin (12:45 öncesi her saat); `status.py` "yükselen tüm coinler" gruplarında
  yalnızca saat başı satırlarını, seçim gruplarında coin başına saatte bir satırı kullanır (ardışık dakikalar neredeyse aynı
  ölçüm; çoğaltılırsa "30 kayıt" şartı sahte dolar); `blocked` = kural yüzünden atlanan (yuva boştu, girilecekti), `chosen` = girilen.
  `status.py` "Etiket etkisi": engelli ve diğer yükselişlerin, ayrıca atlananlarla girilenlerin sonraki 1 sa / 4 sa /
  24 sa getirisi ve +%3 / −%6'ya değme payı, 95% aralıkla. Her grupta en az 30 kayıt olmadan karar yazılmaz.
  Kodun doğruluğu: `audit/label_check.py [db] [ts]` etiketleri Binance'ten sıfırdan hesaplar (bot.py içe aktarılmaz);
  ilk deneme 11:00 saati 30/30 aynı.

## İşlem — Değişiklik 24'ten beri (07.11 ~21:00 TR; Değ. 26–28'de değişmedi; Değ. 29: 60 dk kontrolüne ek süre)
- **Büyüklük:** her işlem **1.500 $ sabit** (`SIZE_BY_VOL = False`; 12 $ / VOL60 kullanılmaz), 10×, izole, teminat 150 $. VOL60 yalnız kayıt.
- **Kâr al:** giriş bitince net **+5 $** (komisyon sonrası): tp = (5 / adet + giriş × 1,0002) / 0,9998, yukarı tick (Değ. 23 ile aynı).
- **Zarar stopu:** borsada STOP_MARKET closePosition MARK_PRICE, tetik = max(giriş − **5 $** / dolan adet → yukarı tick, giriş × 0,94);
  ilk dolumda konur, dolan adet arttıkça taşınır (Değ. 11 yolu, `zs`). 1.500 $'da fiyatta ≈ −%0,33; gerçekleşen ≈ −6 $ (ücret + kayma).
  Seviye hemen tetiklenirse (−2021) piyasa emriyle satılır.
- **Giriş:** hemen al (Değ. 15, aynen). **60 dk kontrolü** (girişten 60 dk sonra, 5 dk'da bir): son 60 dk ≥ −%0,2 ve kâr ≥ +%0,14
  ise tut, değilse sat — **Değ. 29 (08.11 04:47:09 UTC = 07:47 TR'den beri):** kâr +%0,14'ün altında AMA son 60 dk ≥ −%0,2 ve coinin
  son 5 dk'sı (R_5M, gerçek fiyat) artıda ise satılmaz, **3 ek kontrol** (≈ 65, 70, 75. dk): kâr ≥ +%0,14 → sat (`ek_kontrol_kâr`);
  son 60 dk < −%0,2 ya da son 5 dk ≤ 0 → hemen sat (`ek_kontrol_düştü`); 3. ek kontrolde hâlâ +%0,14 altında → sat
  (`ek_kontrol_süre`). Kâr al +5 $ ve stop −5 $ borsada her durumda yerinde. En fazla 4 pozisyon.
- **SHORT (Değ. 30):** giriş demo en iyi **satışa** post-only SELL (GTX), satış fiyatı düşerse ≥ 30 sn arayla aşağı taşınır, 15 dk;
  kâr al net +5 $: tp = (giriş × 0,9998 − 5 / adet) / 1,0002 → **aşağı** tick, BUY LIMIT reduceOnly; zarar stopu BUY STOP_MARKET
  closePosition MARK_PRICE, tetik = min(giriş + 5 $ / dolan adet → aşağı tick, giriş × 1,06 → yukarı tick); kapanış BUY MARKET
  reduceOnly; kâr = (giriş $ − çıkış $) − komisyon + fonlama (`trades.cost` = giriş $, `value` = çıkış $, `side` = SHORT).
- **Açıkken ters sıçrama (Değ. 30, long ve short):** her dakika (kapanıştan 12 sn sonra, karardan önce) coinin son 2 dk ham hareketi
  c(t)/c(t−2)−1 (gerçek piyasa); pencere tamamen dolumdan sonra (t − 2 dk ≥ dolum). İşlemin tersine **≥ %0,20** → hemen piyasa
  emriyle kapat (`ters_sıçrama`; Telegram "ters sıçrama (2 dk ≥ %0,20)"); o coine aynı turda girilmez. Her ölçüm `spike_checks`
  (ts, sym, side, fill_ms, c_now, c_2, move, sold). Eşik Claude'un seçimi (stop %0,33'ün altında), veriye dayanmıyor.

## İşlem — 06.11 ~19:00 UTC – 07.11 Değ. 24 (Değişiklik 14; o dönemde açılan pozisyonlar bitti)
- **Büyüklük (oynaklığa göre):** pozisyon = min(1.500 $, 12 $ / VOL60), aşağı adım; kaldıraç 10×, izole. VOL60 = coinin normal 1 saatlik
  oynaması (liste bölümündeki tanım, karar anında). Ör. VOL60 %0,94 → 1.277 $; %0,32 → 1.500 $; %1,46 → 821 $.
- **Giriş — 07.11 04:30:44 UTC'den beri HEMEN AL (Değişiklik 15):** demo en iyi alış fiyatına post-only (GTX) alış; alış yükselirse 30 sn'de
  bir yeni en iyi alışa taşınır (kovalama), 15 dk'da dolmazsa vazgeçilir, kısmi dolum pozisyon olur (22:00 TR öncesi gibi). Büyüklük ve kâr al/stop
  aşağıdaki gibi aynen. `pb_px = 0`, geri çekilme iptali çalışmaz.
- ~~**Giriş (geri çekilmede)**~~ (06.11 19:00 – 07.11 04:30): sinyal anındaki demo en iyi alışın **%0,2 altına** (aşağı tick) post-only (GTX) alış, **sabit fiyat,
  yukarı taşınmaz**. 15 dk'da dolmazsa vazgeçilir; dolmakta olan emir bir karar anında trend bozulursa (RET_4 ≤ 0, LC < 2 ya da son 60 dk
  < −%0,2) iptal edilir (olay `pullback_cancel`); kısmi dolum pozisyon olur. Borsa emri düşürürse aynı fiyattan (fiyat daha düştüyse
  o anki alıştan) yeniden konur.
- **[07.11 19:03 TR'den beri Değ. 23 geçerli: kâr al NET +5 $, zarar stopu YOK — aşağıya bakın]** ~~Kâr al ve zarar stopu eşit mesafede = 1 × VOL60:~~ kâr al = giriş × (1 + VOL60) (yukarı tick, azaltmalı limit, maker), zarar stopu =
  giriş × (1 − VOL60) (yukarı tick, STOP_MARKET closePosition, MARK_PRICE). Stopta fiyat kaybı en çok **12 $** (komisyon ve kayma ayrı),
  kâr alda ≈ +12 $ (sakin coinde daha az, ör. BNB ±4,8 $). Mesafe yüzde olduğu için kısmi dolumda kayıp dolan payla küçülür.
  Başa baş ≈ %53 kazanma (komisyonlar). −%6 acil stop tabanı yine geçerli (VOL60 ≤ %2 olduğu için devreye girmez).
- **Karar anı başına en fazla 1 yeni giriş** (puanı en yüksek coin; 4 yuva en erken 20 dk'da dolar).
- 60 dk kontrolü (a) son 60 dk ≥ −%0,2 ve (b) kâr ≥ +%0,14 değişmedi.
- Denetim: `audit/bracket_check.py [başlangıç_ms]` (bot.py'yi içe aktarmaz): VOL60'ı sıfırdan, geri çekilme fiyatını, hedef adedi,
  borsadaki adet/giriş/kâr al/zarar stopunu ve karar anı başına ≤ 1 girişi denetler.

## İşlem — eski kurallar (19:00'dan önce açılan pozisyonlar: FIL, QNT, HYPE, AVAX kendi kuralıyla biter)
- **Büyüklük (06.11 10:35'ten beri, kullanıcı: "işlem teminatı 150 dolar"):** Teminat **150 USDT**, kaldıraç **10×**, yani pozisyon başına **1.500 USDT** (adet en yakın adıma yuvarlanır), izole, aynı anda en fazla **8 coin** (06.11 ~11:50'ye kadar 3), coin başına bir. Kaldıraç her girişte borsaya yazılır ve yanıt geri okunur; uymazsa giriş yapılmaz. Dolumdan sonra borsadaki kaldıraç ve tasfiye fiyatı okunup kaydedilir; tasfiye acil stopun üstündeyse uyarı verilir. 10×'te tasfiye ≈ −%8,2…−%9,6 (coin'e göre; demo leverageBracket, 30 coinin hepsi 10×'e izin veriyor), acil stop −%6 ondan önce gelir. Kâr/zarar yüzdesi pozisyona göre yazılır; teminata göre yüzde = 10 katı. Öncesi: 09:05–10:35 150 USDT pozisyon / 15 USDT teminat (10×); ondan önce 100 USDT, 1×. Açık pozisyonlar kendi büyüklüğünde kalır.
- **Giriş:** Demo en iyi alış fiyatına post-only (GTX, maker) limit alış. 30 saniyede bir yeni en iyi alışa taşınır;
  15 dakikada dolmazsa vazgeçilir. Kısmi dolum pozisyon olur.
- **Masraf:** c = maker %0,02 + taker %0,05 = %0,07 (Binance API'den okunmuştu, `v9/data/costs.json`).
- **Kâr al:** Giriş bitince (tam dolum ya da 15 dk) borsaya azaltmalı limit satış konur. **Büyük işlemde** (hedef ≥ 1.000 $, yani 150 $ teminat / 1.500 $ pozisyon; 06.11 ~11:48 kullanıcı: "5 dolar kâr yeterli olur") fiyat, giriş ve çıkış maker ücreti düşüldükten sonra **net +5 $** kalacak şekilde hesaplanır: tp = (5 / adet + giriş × 1,0002) / 0,9998, yukarı tick'e (1.500 $'da ≈ +%0,37). Küçük (eski 100 $ / 150 $) pozisyonlarda ortalama giriş × **1,03**. Bot başlarken açık pozisyonun borsadaki kâr al fiyatı kurala uymuyorsa iptal edilip yenisi konur (SAND 11:48: 0,04519 → 0,04404).
- **Koruma (2× masraf): KAPALI** (kullanıcı 06.11 06:37: "1 saat içinde fiyatta salınım olabilir, araştırılmalı").
  Kod duruyor, `PROTECTION_ON = False`. Saatlik kontroldeki "kârdayız" eşiği (+%0,14) aynen geçerli.
- **Zarar stopu (büyük işlem):** borsada STOP_MARKET closePosition, işaret fiyatıyla; tetik = max(giriş − **12 $** / adet, giriş × 0,94)
  (18:09'dan beri; 14:13–18:09 −5 $). 1.500 $'da fiyatta ≈ −%0,8; gerçekleşen ≈ −13…−14 $ (ücret + kayma). Sebep `zarar_stop`.
- **Acil stop:** İlk dolumda borsaya giriş × **0,94** STOP_MARKET closePosition (işaret fiyatıyla) konur; giriş bitince
  **ortalama** giriş × 0,94'e taşınır (eski iptal → yeni; yeni reddedilirse eski geri konur). Bot kapalıyken de korur.
- Pozisyon kapanınca kalan emirler iptal edilir. Sonuç borsanın işlem kayıtlarından (userTrades, komisyon dahil)
  yazılır.

## Kayıt
- `v9live/live.db` (SQLite):
  - `scores`: her dakika (12:45 öncesi her saat) 30 coinin tüm ölçümleri, şart, puan, seçildi mi (≈ 25 MB/gün)
  - `checks` (06.11 12:45): her pozisyon kontrolü (dakika, son 60 dk getirisi, demo fiyatı, iki şart, satıldı mı)
  - `labels` (06.11 ~11:40): her dakika (12:45 öncesi her saat) 30 coinin etiketi, engel, kural yüzünden atlandı mı, girildi mi, spot/OI ölçümleri
  - `trades`: kapanan her işlem (zamanlar, fiyatlar, adet, maliyet, komisyon, fonlama, net kâr, çıkış sebebi, girişteki
    ölçümler, saatlik kontroller); rakamlar borsanın işlem kayıtlarından
  - `depth`: dakikada bir her coinin defter özeti (band içi alış $, satış $, band). **06.11'den beri silinmez**
    (eskiden 3 saatten eskisi siliniyordu)
  - `outcomes`: gözlem (kararı etkilemez): 24 saat önceki her coin-saatten sonra ne oldu
  - `events`: hatalar ve olağandışı olaylar
- `v9live/book/YYYY-MM-DD.db` (06.11, kullanıcı: "tam defter kayıt ve 3 saate silinmesin"): dakikada bir her coinin
  **tam emir defteri** (1000 alış + 1000 satış basamağı), Binance yanıtı bayt bayt, lzma ile sıkıştırılmış. Tablo `book`:
  `ts` (depth özetiyle aynı an → eşleşir), `sym`, `last_update_id`, `E`, `T`, `n_bids`, `n_asks`, `raw`.
  Açmak: `json.loads(lzma.decompress(raw))`. Ek Binance isteği yok (aynı yanıt). Görüntü başına ≈ 6–9 KB → günde
  ≈ 350 MB. **Bot hiçbir şeyi silmez.** Diskte 3 GB'tan az boş yer kalırsa yalnızca tam defter yazımı durur, telefona
  uyarı gider; özet ve işlemler sürer; yer açılınca kendiliğinden yeniden başlar.
  Bağımsız denetim: `python v9live/verify.py book [DAKİKA]`.
- `v9live/state.json`: açık pozisyonların anlık defteri (emir numaraları, dolan adet, stop); yeniden başlatmada buradan
  devam edilir, pozisyon kapanınca çıkar
- `journalctl -u v9-demo`: metin günlüğü
- Telefona bildirim (`.env.bildirim`): başladı/durdu, giriş emri, pozisyon, çıkış, disk uyarısı (hatalar gitmez)
- `python v9live/status.py`: açık pozisyonlar, kapanan işlemler, defter kaydı, gözlem tabloları

## Düzeltmeler (06.11.2026 07:24 UTC, bağımsız denetim `v9live/verify.py` ile bulundu)
1. **OI_1** 30 coinin 23'ünde 60 değil 55 dk ölçülüyordu (07:00 değeri saat başından 10 sn sonra henüz yayımlanmamıştı).
2. **Emir defteri** 500 basamakla alınıyordu; BTC (±%0,09), ETH, ZEC, HYPE, BNB'de ±%1'e uzanmıyordu.
3. **Acil stop** ilk dolan parçanın fiyatına göre kalıyordu, ortalama girişe taşınmıyordu.
Doğru çıkanlar (07:00, 30 coin, fark 0): RET_4, LC, son saat, önceki saat, ACC_1, TAKER_1, SMOOTH_4, giriş şartı.

## Düzeltmeler 2 (06.11.2026 07:45 UTC, kullanıcı isteğiyle tam denetim)
4. **OI_1** dolar değeriydi → fiyatla korelasyon 0,96 (JCT: fiyat +%9,8, değer +%8,4, adet −%1,4). Artık adet.
5. **Saatlik kontrol (a)** "son saat > önceki saat" → "son saat > 0" (kullanıcı kararı; yeni kural, test edilmemiş).
6. **Aynı saatte geri alma** yasak (eskiden satılan coin puanı yüksekse hemen geri alınabiliyordu: iki kez masraf).
7. **Demo'da kapalı coin** (PUMP SETTLING) seçilmez; eskiden giriş hata verip yuva boş kalıyordu.
8. **Hata dayanıklılığı:** bir coinde demo fiyat hatası tüm saati iptal ediyordu → coin başına. Emir gönderiminde hata
   olursa emirsiz pozisyon kaydı yuvayı süresiz tutuyordu → kayıt silinir, olası emir cid ile iptal edilir.
9. **Yuvarlama** aşağı → en yakın (AAVE 90 $ → 104 $).
Doğru çıkanlar: evren (Ekim hacmi, bağımsız hesapla birebir), kâr/zarar formülü (borsa kayıtları, USDT komisyon), LC/şart.
Not: demo piyasa emri komisyonu %0,04 (gerçek %0,05) → demo sonuçları işlem başı ≈ %0,01 iyimser.

## Değişiklik 3 (06.11.2026 09:05 UTC, kullanıcı isteği)
10. **Büyüklük ve kaldıraç:** yeni girişler 100 $ / 1× → **150 $ / 10×** (teminat 15 $). Açık 1× pozisyonlar (GTC, NEAR,
    ONDO) olduğu gibi kalır. Her pozisyon kendi kaldıracını `state.json` (`lev`, `liq_px`) ve `trades.lev` sütununa yazar
    (boş = 1×). Kaldıraç ayarı borsa yanıtıyla, pozisyon kaldıracı ve tasfiye fiyatı positionRisk ile doğrulanır.

## Değişiklik 4 (06.11.2026 ~10:35 UTC, kullanıcı isteği: "işlem teminatı 150 dolar olarak ayarla")
11. **Büyüklük:** yeni girişler pozisyon 150 $ (teminat 15 $) → **pozisyon 1.500 $, teminat 150 $**, kaldıraç 10× aynı.
    Kontrol (demo-fapi, değişiklikten önce): 30 coinin hepsinde 10× basamağı ≥ 1.575 $ alıyor; demo cüzdan 4.767 $, 3 yuva × 150 $
    = 450 $ teminat. Açık pozisyonlar (ONDO 1× ~101 $, 1000PEPE ve TAO 10× ~150 $) olduğu gibi kalır.
    Sonuç: +%3 kâr al ≈ +45 $, −%6 acil stop ≈ −90 $ (teminatın %60'ı), tasfiye ≈ −%8…−%10 (teminatın tamamı).


## Değişiklik 5 (06.11.2026 ~11:40 UTC, kullanıcı isteği: "b ekle ve test et")
"Short kapatma + spotsuz" giriş engeli ve etiket kaydı (yukarıda madde 6). Deneme modu artık `dry_run.db` ve
`dry_state.json`'a yazar, canlı `live.db` / `state.json`'a dokunmaz. Yedekler `*.bak_20261106_1140`.

## Değişiklik 6 (06.11.2026 ~11:48 UTC, kullanıcı: "150 dolar teminatlı büyük işlemde 5 dolar kâr yeterli olur")
Büyük işlemde kâr al net +5 $ (yukarıda "Kâr al"). Saatlik kontrol (+%0,14 eşiği) ve acil stop (−%6 = −90 $) DEĞİŞMEDİ.
Yeniden başlatma 11:48:29; SANDUSDT kâr al 0,04519 → 0,04404 (borsadan doğrulandı, tek TP emri). Yedekler `*.bak_20261106_1148`.

## Değişiklik 7 (06.11.2026 ~11:50 UTC, kullanıcı: "kâr alınmadıysa ve hâlâ pozisyon açıksa 3'ten fazla, yani 8'e kadar işlem açılabilir")
Aynı anda en fazla **8 pozisyon** (önce 3), coin başına bir. Büyüklük aynı (150 $ teminat, 10×, 1.500 $). Bir saatte boş yuva
kadar yeni giriş olabilir. 8 büyük pozisyon = 1.200 $ teminat, 12.000 $ pozisyon; hepsi acil stopa değerse ≈ −720 $.
Yedekler `*.bak_20261106_1152`.

## Değişiklik 8 (06.11.2026 13:17:03 UTC, kullanıcı seçimi "A")
Giriş şartına **son 60 dk getirisi > 0** eklendi (`ENTRY_RT_POSITIVE = True`). Sebep (kayıtlardan): puanın alt sınırı yok, şartı geçen
7–12 coin 8 yuvaya neredeyse hep giriyordu; FIL, LINK, HYPE, SOL son 60 dk EKSİDEYKEN girmişti — botun 60 dk sonra kendi
kontrolüyle satacağı coinler. Deneme 13:16: eski kural 9 coin, yeni kural 2 coin (dry_run.db). Puan, yuva (8), kâr al, kontrol,
acil stop DEĞİŞMEDİ; açık pozisyonlar olduğu gibi. `verify.py` şart denetimi `GATE_RT_FROM_MS`'ten sonra yeni kuralla.
Yedekler `*.bak_20261106_1314`.

## Değişiklik 9 (06.11.2026 13:24:45 UTC, hata düzeltmesi — veri zamanlaması)
Dakikalık karar dakika kapanışından **12 sn** sonra (önce 3 sn). Ölçüm (13:22 ve 13:23, gerçek fapi, 30 coin): kapanan 1 dk mum REST'te
+3 sn'de 11–13 coinde kapanışı, 16–19 coinde en az bir alanı kesin değerden farklı; +5 sn 1–3 coin; +8 sn 0. `verify.py` 12:50–13:19
dakikalarında r_t/RET_4/TAKER_1/SMOOTH_4 farkı (≤ %0,05) ve 13:19'da bir coinde LC farkı buldu. Bağımsız yeniden hesap (scratchpad
impact.py): 12:50–13:24 arası 34 dakikanın HİÇBİRİNDE şartı geçen küme değişmedi, 12 girişin puanı/sırası aynı → kararlar etkilenmedi.
Düzeltmeden sonra 13:28, 13:29, 13:30: 30/30 fark 0 (yeni şart dahil). Saatlik modda bekleme 10 sn'ydi (sorun yoktu).

## Değişiklik 10 (06.11.2026 13:27:42 UTC, hata düzeltmesi — giriş değeri)
ZEC 13:22 girişi: yeniden fiyatlama için emir iptal edilirken 0,512 adet doldu; iptal yanıtındaki avgPrice 0 → 676,96 $ değer 0
sayıldı, bot ortalama girişi 726,83 sandı (borsa 1.322,22), 13:25'te acil stopu 683,21'e taşıdı ve kâr al emri borsa fiyat
bandına takıldı (−4024, emir girmedi). Düzeltme: `absorb()` avgPrice 0 ise cumQuote, yoksa emri yeniden okur, yine yoksa HATA verir
(yanlış değerle toplamaz; olay `avgprice_zero`). state.json ZEC elle düzeltildi (userTrades: 0,741 @ 1.322,19 + 0,396 @ 1.322,27 =
1.503,36 $; yedek state.json.bak_20261106_1326*). Yeniden başlatmada bot acil stopu 1.242,88'e aldı, kâr al 1.327,15 koydu;
exch_check: 7 pozisyon bot = borsa, her birinde 1 kâr al + 1 acil stop. Not: 13:24:45 yeniden başlatma ZEC girişi bitmeden
yapıldı ("open" + kâr al yok = giriş sürüyor); bundan sonra yeniden başlatmadan önce tp_cid boş pozisyon da beklenecek.
Yedekler `*.bak_20261106_1324`.

## Değişiklik 11 (06.11.2026 14:13:21 / 14:14:38 UTC, kullanıcı: "coin evreni son 24 saate pozitif değer alana göre yeniden değerlendirilmeli, demodaki bakiyenin hepsini göster ve bota yansıt, işlem sayısı anlık 4, −5 $ zarar açıklayınca hemen emir koy ve satış bekle")
Kullanıcı seçimleri (AskUserQuestion): "listeyi yeniden kur", "sadece göster", "borsaya baştan stop emri", "açık pozisyonlara da".
- **Coin listesi her dakika:** TÜM USDT sürekli vadeli coinler (gerçek piyasa, underlyingType COIN, TRADING) içinden Binance 24 sa
  değişimi > 0 olanların 24 sa USDT hacmine göre ilk 30'u (`/fapi/v1/ticker/24hr`, karar anında t + 12 sn). Demo'da TRADING olmayan /
  demo filtresi olmayan ve sabit coinler (USDC vb.) alınmaz. Liste `uni24` tablosunda. Giriş şartına CHG24 > 0 da eklendi.
  Önceki sabit liste (Ekim hacmi) kullanılmıyor. Listeye yeni giren coin, son 60 dk'da 30 defter görüntüsü birikene kadar (≈30 dk)
  puanlanmaz (IMB1_1/BIDSHARE_1 boş). Spot ortancası yeni coin için o saat ilk görüldüğünde bir kez alınır.
  14:06 listesinde AKE +%100, CYBER +%46, ONE +%29 gibi çok oynak küçük coinler var; 24 sa hacim 9–480 M$ (kullanıcıya söylendi).
- **En fazla 4 pozisyon** (önce 8).
- **Zarar stopu:** büyük işlemde borsada STOP_MARKET closePosition MARK_PRICE, tetik = max(giriş − 5 $ / adet → tick yukarı,
  giriş × 0,94). cid `zs`, sebep `zarar_stop`. Giriş sürerken dolan adet arttıkça stop taşınır. Seviye "hemen tetiklenir" (−2021)
  ise zarar zaten −5 $'ı geçmiştir → piyasa emriyle satılır. Gerçekleşen kayıp ≈ −6…−7 $ (ücret + kayma), geçmişse daha çok.
  Yeniden başlatmada açık pozisyonlara uygulandı: ZEC −24,35, HYPE −12,83, FIL −9,11, STRK −12,19 $ satıldı (zaten −5'i geçmişlerdi);
  RLC (0,4516) ve TAO (222,44) stopları kondu (pnl_check ✓).
- **Bakiye:** Telegram GİRDİ/ÇIKTI ve başlangıç mesajında tüm demo bakiyeleri (USDT, USDC, BTC); status.py "Demo bakiye". Bot yalnız USDT kullanır.
- **Denetim düzeltmeleri:** (1) piyasa satışı başarısızsa exit_cid temizlenir, kâr al geri konur, sonraki tur yeniden dener; giriş sürerken
  çıkışta önce giriş emri durdurulur. (2) Piyasa emri adet sınırı (MARKET_LOT_SIZE maxQty; STRK demo 30.000 < 37.128 → −4005) →
  satış parçalara bölünür. (3) Giriş "doldu mu" toleransı 1e-12 → adım/2 (STRK 37128,7 vs 37128,700000000004 dolmadı sayılıyordu).
- Doğrulama: verify.py features 14:15/14:16 30/30 fark 0; verify.py universe 14:15/14:16 uyuşmayan 0 (ticker ile 1 dk mum 24 sa farkı
  ≤ %0,4); audit/pnl_check.py 29 kapanan işlem fark 0. Yedekler `*.bak_20261106_1403`.

## Değişiklik 12 (06.11.2026 14:39:21 UTC, kullanıcı seçimi "C": kararlar yeniden saat başı)
Soru: "1 dk mum daha dalgalı, anlık sıçramayla nasıl başa çıkacağız?" Ölçüm (gerçek fapi 1 dk, 09:32–17:32 TR, listedeki 30 coin):
1 dk mum std %0,25; 60 dk pencere saat başı %1,27, her dakika %1,35 (aynı oynaklık); ama "son 60 dk artıda mı" cevabı saatte ortanca
3,9 kez (en çok 9,4) değişiyor ve değişimlerin %27'si 1 dk sonra geri dönüyor → her dakika sormak anlık sapmalara yakalatıyordu.
Seçenekler A (3 dk onay), B (5 dk ortalama), C (saat başı) sunuldu; kullanıcı C'yi seçti.
- `HOURLY_DECIDE = True`: giriş kararı ve saatlik kontrol YALNIZCA saat başında (t = :00, +12 sn). Saat başında 1 dk mumlardan hesap =
  Binance 1 sa mumu (16:00 TR'de 30/30 birebir). Saatlik kontrol eski kural: saat başından önce dolmuş her açık pozisyon (sebep
  `saatlik_kontrol`). Boşalan yuva bir sonraki saat başında dolar; o saat satılan coine o saat girilmez.
- Liste (24 sa artıda, hacme göre ilk 30) her dakika yenilenir (`uni24`) ama yalnızca defter görüntüleri hangi coinlerde alınacak diye;
  karar saat başındaki listeyle. `scores` / `labels` artık yalnız saat başı.
- Değişmeyenler: kâr al net +5 $ ve −5 $ zarar stopu borsada (sürekli), en fazla 4 pozisyon, 24 sa şartı, 60 dk / 4 sa / LC şartları.
- Not (14:28 ZEC): zarar stopu MARK fiyatına göre tetiklenir; demo işlem fiyatı mark'tan ~7–13 bps farklı → ZEC'te tetik 1.316,07,
  satış 1.317,78, net −3,94 $ (beklenen ≈ −6 $'dan iyi). Ters yönde de olabilir.
Yedekler `*.bak_20261106_1438`.

## Değişiklik 13 (06.11.2026 18:09:53 UTC, kullanıcı: "bu sistemi yapmak istiyorum … stop loss −12 dolar olsun" + seçim "oynaklık sınırı ekle")
Soru: "her 5 dk'da bir kurallar uygulanırsa ne olur, gürültü için ne yapılmalı". Ölçüm (gerçek fapi 1 dk, 05.11 18:59–06.11 17:52 UTC,
listedeki 30 coin; kâr testi DEĞİL, yalnız sinyal oynaklığı): "son 60 dk > 0" cevabı saatte kaç kez değişiyor / değişimlerin kaçı
15 dk içinde geri dönüyor: saat başı 0,46 / –; her dakika 4,02 / %77; 5 dk ham 1,77 / %55; 5 dk + uçlar 5 dk ort. 1,44 / %45;
5 dk + ±%0,2 bant 1,00 / %28; 5 dk + 2 kez onay 0,96 / %23 (5 dk gecikme); **5 dk + ortalama + bant 0,92 / %18** (seçilen).
İvme (son 60 dk − önceki 60 dk): ham 2,25 / %56 → ortalama + bant 1,20 / %22.
- **Karar 5 dk'da bir** (`DECIDE_STEP_MS`), **uçlar 5 dk ortalaması** (`SMOOTH_N`), **bant ±%0,2** (`BAND`): giriş r_t > +%0,2, kontrol (a)
  r_t ≥ −%0,2. Kontrol girişten 60 dk sonra başlar, sonra 5 dk'da bir; (b) +%0,14 anlık demo fiyatıyla aynen.
- **Zarar stopu −12 $** (`STOP_USD`; önce −5 $). Kâr al net +5 $ aynı → kayıplar stoptan gelirse başa baş için ≈ %72 kazanma gerekir
  (kullanıcıya söylendi). 14:13–18:05 arası: 13 işlem, 1 kâr al, 11 zarar stopu (hepsi −5 $ stopla, 1–35 dk içinde), net −52,13 $.
- **Liste oynaklık sınırı VOL60 ≤ %2** (`VOL_MAX`; yukarıda "Coin listesi"). Sebep: −12 $ stop = −%0,8; rastgele girişte 60 dk içinde
  −%0,8'e inme oranı oynak coinlerde %65–91, diğerlerinde %3–57 (aynı veri). −%0,33'e (eski −5 $) inme ortanca %73'tü.
- **Etiket deneyi değişmedi:** `labels.r_t` ve etiket HAM son 60 dk ile (`r_t_raw`), `audit/label_check.py` geçerli.
- Denetim: deneme 18:08 (`dry_run.db`): `V9_DB=…/dry_run.db verify.py features` 30/30 fark 0 (ortalamalı uçlar, r_t_raw, bantlı şart);
  `verify.py universe` VOL60 bot − bağımsız 6,9e−18, alınmayan 8 coin hepsi > %2; tek uyuşmazlık BTC 24 sa işareti (ticker +%0,001,
  1 dk mum −%0,008: sıfıra çok yakın, bilinen ticker/mum farkı). `verify.py` artık `V9_DB` ortam değişkeniyle başka veritabanını denetler.
- Yeniden başlatma 18:09:53 (açık / bekleyen pozisyon yoktu). Yedekler `*.bak_20261106_1805`.

## Değişiklik 14 (06.11.2026 ~19:00 UTC, kullanıcı: "sebepleri tersine çevirmek istiyoruz … uyumsuz mantığı mantığa uygun hale getirelim")
Gözlem (gerçek fapi 1 dk, 21:15–21:40 TR): FIL, QNT, HYPE, AVAX girişte 2 saatlik zirvelerinin %0,07 yakınındaydı; dördü de dolumdan 1 dk
sonra girişin altına indi; 25 dk içinde dördü birden açıldı. Sebepler: (1) şartlar + puan tanım gereği zirvedeki coini seçiyor, (2) bekleyen
alış emri satıcı gelince dolar (yükselişte dolmaz, kovalanır), (3) coinler birlikte hareket ediyor → 4 işlem ≈ tek bahis, (4) sinyal
saatlik, kâr al +%0,37 / stop −%0,8 ise normal 1 saatlik oynamanın (≈ %0,9) içinde → sonuç dakikalık gürültü; +5 / −13 $ ile başa baş
%72 kazanma ister. Kullanıcı seçimleri (AskUserQuestion, hepsi önerilen): "Oynaklığa göre, en çok −12 $", "Geri çekilmede al",
"5 dk'da en fazla 1 giriş", "Eski kurallarıyla bitsin". Kod: `RISK_USD`, `BRACKET_K`, `PULLBACK`, `MAX_NEW_PER_TICK`; `Pos.vol/pb_px/ref_px`
(vol = 0 → eski kural). Not: bunlar yapısal dezavantajları kaldırır, sinyale tahmin gücü KAZANDIRMAZ; sonuç demo kaydıyla görülecek.
Deneme (bot.py deneme modunda, gerçek demo tick/adım): FIL %0,94 → 1.544 adet 1.276,6 $, kâr al +12,04 $, stop −11,89 $; BNB %0,32 →
1.500 $ ±4,8 $; ZEC %1,46 → 821 $ ±12 $; yarım dolumda kayıp yarıya; eski 4 pozisyonun kurala göre stop/kâr al değeri borsadakiyle aynı.
Yedekler `*.bak_20261106_1900`.

## Değişiklik 15 (07.11.2026 04:30:44 UTC = 07:30 TR; kullanıcı: "coin evrenini değiştiriyorum, en fazla hacme sahip olan coin evrenine geri
dönüyoruz … hacim az coinde emir dolana kadar zarar ediyoruz")
Ölçüm (live.db trades, decision → fill): alış dolum süresi ortancası 22:00 TR öncesi ≈ 0,7–1,6 dk, sonrası ≈ 4–6 dk; yavaşlama eski sabit listedeki
büyük coinlerde de (4,2 dk) küçüklerde de (5,8 dk) aynı → sebep liste değil, geri çekilme alışı. 3 yarım dolum (WLFI 408/1.500 $, AERO 107/945 $,
FIL 471/1.480 $). Kullanıcının örneği ("+6 $ gördü, şimdi −3 $"): AIO en çok +7,99 $ (07:14 TR), kâr al +12,00 $'daydı, hiç değmedi → dolum
sorunu değil, hedef uzaklığı; AIO 07:23 TR −12,28 $ zarar stopuyla kapandı. Kullanıcıya söylendi.
Kullanıcı seçimleri (AskUserQuestion): liste "Bugünün en büyük 30'u" ('24 sa artıda' şartı kalktı: `UNI_REQUIRE_UP = False`, liste + giriş şartı),
alış "Hemen al (eski hâli)" (`ENTRY_CHASE = True`). Değişmeyen: VOL60 ≤ %2 liste sınırı, büyüklük min(1.500, 12/VOL60), ±VOL60 kâr al/stop,
5 dk karar, karar başına 1 giriş, 4 yuva, 60 dk kontrolü.
Deneme: `bot.py --dry` 04:28 → `V9_DB=dry_run.db V9_GATE24_TO_MS=0 verify.py universe` uyuşmayan 0 (VOL60 farkı 6,9e−18), `features` 30/30 fark 0;
sahte borsayla `enter()`+`monitor()` (scratchpad enter_test.py): ilk emir = en iyi alış, pb_px 0, alış yükselince iptal + yeni en iyi alış.
`verify.py` (GATE24_TO_MS), `audit/bracket_check.py` (pb_px = 0 → hemen alış), `status.py` metni güncellendi. Yeniden başlatma 04:30:44 (açık: ETHFI, TA,
ikisi de dolu + kâr al/stop borsada; bekleyen giriş yoktu). Yedekler `*.bak_20261107_0735`.

## Değişiklik 16 (07.11.2026 04:56:51 UTC = 07:56 TR; kullanıcı: "ivme farkını puandan çıkar")
Gerekçe: `lossreview/RAPOR.md` (69 kapanan işlem, gerçek fapi verisi): kaybedenlerde girişteki ACC_1 ortancası +%0,75, kazananlarda +%0,06
(permütasyon p 0,008; iki dönemde de aynı yön; ~25 ölçüden biri → kanıt değil, kullanıcıya söylendi). Kod: `SCORE_EXCLUDE = ("ACC_1",)`,
`SCORE_COMPONENTS` (puan = 6 bileşenin sıra yüzdesi ortalaması). ACC_1 ölçülür, `scores`/`trades` feats'e yazılır, logda görünür; şartlar
(RET_4 > 0, LC ≥ 2, son 60 dk > +%0,2) değişmedi. `verify.py features` artık puanı da bağımsız yeniden hesaplar (botun kaydettiği
bileşenlerden, kendi sıra hesabı; `NOACC_FROM_MS` öncesi 7, sonrası 6 bileşen): eski kural 04:55 kararında fark 1,1e−16 (18 coin).
Yeniden başlatma öncesi NEAR girişi (04:55, eski puan) dolması beklendi (11 sn'de doldu). İlk "hemen al" dolumları: QNT 2,8 dk, UNI 1,1 dk,
NEAR 0,5 dk (karar → dolum). Yedekler `*.bak_20261107_0755`.

## Değişiklik 17 (07.11.2026 05:19:47 UTC = 08:19 TR; kullanıcı: "çok yükselmiş coinleri alma, giriş şartını değiştir")
İptal edildi (Değişiklik 24): "yerinde saymış" giriş şartı (son 60 dk −%0,2…+%0,2). Kodu ve metni silindi; o dönemin işlemleri `trades`'te duruyor.

## Değişiklik 18 (07.11.2026 09:15:44 UTC; kullanıcı: "hacim ve emir defteri alıcı yoğunluğu gösterirse gir … bota ekle, gölge değil direkt denemeye başla")
İptal edildi (Değişiklik 24): hacim + emir defteri akışı giriş şartı. Kodu (ölçüm, `depth2` yazımı, `band_sums`, `verify.py flow`) ve metni silindi; o dönemin işlemleri ve `depth2` tablosu duruyor. Tam defter arşivi (`v9live/book`) sürüyor.

## Değişiklik 20 (07.11.2026 12:52:05 UTC = 15:52 TR; kullanıcı: "sepet mantığını iptal et ve bu mantığı tamamen kaldır … bir önceki döneme dönelim", ardından iki kez "onları da sil")
- 11:11–12:47 UTC arasında denenen kural (Değişiklik 19) iptal edildi ve kodu, kayıtları, yedekleri, ön kaydı silindi. Bot Değişiklik 18'e döndü:
  `bot.py` ve `status.py` = `*.bak_20261107_1357` ile birebir aynı (bot.py SHA-256 0f7256ee…4227).
- live.db `trades` tablosundan o dönemin 6 işlemi silindi (toplam +1,16 $); demo bakiyesi bu tutarı içerdiği için bot kaydının toplamı borsa
  bakiyesinden bu kadar farklı. O dönemdeki tek Değişiklik 18 işlemi (XMR, 12:05 UTC kapandı, −2,11 $) duruyor.

## Denetim 07.11.2026 ~16:30 TR (kullanıcı: "botun çalışma mantığına bak … her birini doğrula") — kural değişikliği YOK
- Yeni bağımsız araçlar (bot.py içe aktarılmaz): `audit/decide_check.py` (5 dk düzeni, şart, puan, seçim; bekleyen/dolmayan emir yuvası dahil),
  `audit/closed_check.py` (kapanmış işlem ve dolmayan girişte: VOL60, adet, post-only takip, 15 dk, kâr al, zarar stopu ve taşınması, 60 dk kontrol
  zamanları ve kararları, çıkış türü, net kâr; borsa allOrders/allAlgoOrders/userTrades/income). `audit/pnl_check.py` artık işlemleri zamana göre
  eşleştiriyor; botun kaydında olmayan borsa turlarını (06.11 kurulum denemeleri LTC, silinen Değ. 19 işlemleri) ayrı listeliyor.
- Sonuç: liste, ölçümler, akış, defter, etiket, şart/puan/seçim (26 karar), emir adımları (18 işlem + 1 dolmayan) uyuşmayan 0.
  **Tek hata (Değişiklik 21'de düzeltildi):** çıkış fonlama anından ≈ 25 sn sonra olursa (kontrol :00'da satarsa) borsa fonlama kaydını henüz yayımlamadığı
  için `trades.funding` 0 yazılıyor: ETH 07.11 00:00 UTC −0,15 $, ONDO 08:00 UTC −0,15 $. Fonlamadan 10–23 dk sonra çıkan 3 işlemde doğru.

## Değişiklik 21 (07.11.2026 ~13:26 UTC = ~16:26 TR; kullanıcı: "evet düzelt") — yalnız KAYIT düzeltmesi, kural/karar DEĞİŞMEDİ
- **Hata:** Binance fonlama kaydını (FUNDING_FEE) fonlama anından birkaç sn sonra yayımlıyor; çıkış fonlama anından ≈ 25 sn sonra olursa
  (60 dk kontrolü :00'da satarsa) `finalize` sorgusu kaydı göremiyor, `trades.funding` 0 yazılıyordu.
- **Düzeltme:** `funding_recheck()` + `Bot.funding_fix()` (dakikalık döngüde, deneme modunda çalışmaz): kapanan her işlemin fonlaması kapanıştan
  ≥ 3 dk sonra, [dolum, çıkış] aralığında borsadan BİR KEZ yeniden okunur; farklıysa `funding`, `pnl`, `pnl_pct` güncellenir, olay `funding_fix`,
  journal "FONLAMA DÜZELTMESİ", telefona "🔧 FONLAMA DÜZELTMESİ" (eski → yeni NET). Yeniden başlatmada son 3 saatte kapananlar yeniden bakılır
  (aynıysa dokunulmaz). Hata olursa olay `funding_recheck_error`, işlem sürer.
- **Geçmiş:** aynı fonksiyonla tek seferlik (06.11 23:50 UTC → şimdi, 30 işlem): ETH (dolum 06.11 22:59 UTC) fonlama 0 → −0,1500, net −0,719 → −0,869 $;
  ONDO (07.11 06:55 UTC) 0 → −0,1502, net −1,881 → −2,031 $; diğer 28 işlem aynı. (06.11 06:00–23:50 arası `pnl_check.py`'ye göre farksız.)
- **Test:** live.db kopyasında aynı 2 düzeltme, başka satır değişmedi, ikinci çağrı boş; `bot.py --dry` hata yok.
Yedekler `*.bak_20261107_1621`.

## Değişiklik 22 (07.11.2026 14:01:07 UTC = 17:01 TR; kullanıcı: "hacim şartını kaldır")
İptal edildi (Değişiklik 24, Değ. 18 ile birlikte): hacim şartının kaldırılması. Metni silindi.

## Değişiklik 23 (07.11.2026 16:11:31 UTC = 19:11 TR; kullanıcı: "botun her girdiği işleme direkt +5 dolar karını hesaplayıp direkt emir koyulsun ve stoploss kaldırılsın")
- **Kullanıcı seçimleri:** 60 dk kontrolü **kalsın**; açık TA da yeni kurala geçsin (TA bu sırada 19:05:03 TR'de iPhone uygulamasından elle
  piyasa satışıyla kapatıldı, emir `ios_…`, net +3,74 $; bot sebebi `bilinmiyor` yazdı — geçiş gerekmedi).
- **Kâr al:** her işlemde, giriş bitince azaltmalı limit (maker) satış; fiyat = komisyonlar (giriş maker + çıkış maker, %0,02 + %0,02)
  düşüldükten sonra **net +5 $**: tp = (5 / adet + giriş × 1,0002) / 0,9998, yukarı tick (`TP_NET_ALL = True`). Fonlama hariç (önceden bilinmez).
  1.500 $'da ≈ +%0,37; küçük pozisyonda daha uzak (661 $'da ≈ +%0,80). Bot başlarken açık pozisyonun kâr alı bu kurala taşınır.
- **Zarar stopu YOK** (`STOP_ON = False`): ne ±VOL60 stopu ne −%6 taban konur; açık pozisyonun borsadaki stopu yeniden başlatmada iptal edilir
  (olay `estop_removed`). Zarardaki işlemi yalnız **60 dk kontrolü** kapatır (aynen: dolum + 60 dk'dan sonraki ilk 5 dk sınırından itibaren
  5 dk'da bir; son 60 dk ≥ −%0,2 VE demo alış ≥ giriş × 1,0014, değilse piyasa satışı). İlk 60 dk'da fiyat ≈ −%8,2…−%9,6'ya inerse borsa
  pozisyonu **tasfiye** eder (10× izole): kayıp ≈ teminatın tamamı (1.500 $'da ≈ 150 $ = 30 kez +5 $). Bot bunu sebep `tasfiye` diye yazar.
- **Değişmeyen:** liste, karar, giriş şartları, puan, büyüklük min(1.500 $, 12 $ / VOL60) (artık stop mesafesine bağlı değil ama aynen
  bırakıldı), giriş (GTX, takip, 15 dk), en fazla 4 pozisyon, karar başına 1 giriş, 60 dk kontrolü.
- **Telegram:** 🟢 GİRDİ mesajında "Kâr al <fiyat> (+%x, net +5,00 $) · zarar stopu yok (60 dk kontrolü)".
- **Deneme:** `bot.py --dry` hata yok; sahte borsa birim testi 12/12 (TA kâr al 0,09805 = net +5,0006 $, bir tick aşağısı 4,93 $; ETH 1.498 $
  +%0,374; stop emri hiç konmuyor; eski stop bir kez iptal, red olsa da kayıt temizleniyor; giriş mesajı; tasfiye sebebi; başlangıçta
  kâr al taşıma + stop iptali sırası). Kapalı kalan kod: `estop_px`, ±VOL60 kâr al dalı, −%6 taban (bayrakla kapalı). Yeniden başlatma 16:11:31 UTC (açık pozisyon yok); `audit/closed_check.py` `DEG23_MS = 1794067891000`. Yedekler `*.bak_20261107_1903`.


## Değişiklik 24 (07.11.2026 17:56:12 UTC = 20:56 TR; kullanıcı: "botu o haline geri getirmemiz gerekiyor ve piyasa yükselişini tam anlamıyla başlar başlamaz görmemiz gerekiyor ve bizim o zaman toplam zarar yazmamızın nedeni tamamen stoploss koymayışımızdan kaynaklı oldu")
- **Kullanıcı seçimleri (AskUserQuestion):** "Sadece giriş şartı" (06.11 15:00 TR'deki hâl; 5 dk karar, liste, 4 yuva, kâr al, 60 dk kontrolü
  aynen; pozisyon 1.500 $ sabit), zarar stopu **−5 $** (önce botun 2 günlük 92 işlemi incelendi, aşağıda), bir de yükseliş sinyali
  (Değ. 26'da iptal edildi, kodu ve metni silindi), iptal edilen şartların **"kod ve metni silinsin, işlem kayıtları kalsın"**.
- **Kural:** giriş şartı son 4 sa > 0 ve LC ≥ 2 (4 sa şartı Değ. 26'da piyasa son 30 dk ile değişti); 1.500 $ sabit, kâr al net +5 $,
  zarar stopu −5 $ (§İşlem).
- **Silinen kod:** `ENTRY_CALM`, `BOOKFLOW_ON`, `VOLR_GATE_ON`, `NB_BAND`/`BUILD_BAND`/`FLOW_MIN_SNAPS`/`FLOW_KEYS`, `band_sums`, `load_depth2`,
  `depth2` yazımı ve tablo oluşturma, TAKER_15/VOLR_15/NB_IMB02/BUILD_05 ölçümü (bot.py); `verify.py flow`, `CALM_FROM_MS`, `VOLR_TO_MS`;
  `audit/decide_check.py` akış/bant şartları. Değ. 17/18/22 metinleri kısa nota indirildi. Duranlar (sorulacak): `depth2` tablosu, `scores.feats`
  ve `trades.feats` içindeki eski değerler, `*.bak_*` yedekleri, raporlardaki anlatımlar.
- **Stop incelemesi (botun kaydı + gerçek fapi 1 dk mumları, her işlem 1.500 $ sayıldı; kâr al = son fiyat, stop = MARK; aynı dakikada ikisi →
  stop önce):** 92 işlemden 29'u −5 $'a inmeden +5 $; 14'ü −5 $'a inip sonra −8 $'a inmeden +5 $; 46'sı −5 $'tan sonra −8 $'a da indi; 3 belirsiz.
  −8 $'ın −5 $'a farkı ≈ 14 × 10 − 46 × 3 = +2 $ (pratikte yok). 06.11 15:00–17:13 TR'deki 23 işlem (gerçek −133 $) −5 $ stopla ≈ −49…−60 $.
- **Deneme:** `bot.py --dry` 17:50 UTC hatasız (şartı geçen 4: LTC, LINK, UNI, TA).
- Yedekler `*.bak_20261107_2045` (bot.py, status.py, verify.py, KURALLAR.md, audit/decide_check.py).

## Değişiklik 25 (07.11.2026 18:13:19 UTC = 21:13 TR; kullanıcı seçimi "Bu coinleri alma")
- **Sebep:** Değ. 24'ün ilk işlemi CYBER (karar 21:00, puan 0,70): fiyat 0,320, demo fiyat adımı 0,001 = fiyatın %0,31'i → −5 $ stop (%0,33) tek adım.
  21:02:17 doldu (maker 0,320), bot dolumu 4 sn sonra gördü, stop 0,319 (MARK) 21:02:21,7'de kondu, 0,4 sn sonra tetiklendi, satış 0,318 →
  net **−10,27 $** (borsa userTrades + algo emir FINISHED ile doğrulandı). Kâr al da aynı yuvarlamayla 0,322 (+%0,63) olmuştu.
  O anki listede stop adım sayısı: CYBER 1,1; TRUMP 3,9; ENA 5,3; ARB 5,6; ADA 6,1; diğer 25 coin > 11.
- **Kural:** her kararda `TICK_REL` = demo fiyat adımı / karar anında biten 1 dk mumun kapanışı (gerçek piyasa) `scores.feats`'e yazılır;
  `TICK_REL > TICK_MAX_REL` (%0,1) ya da ölçülemeyen coine girilmez, journal'da atlanan "(fiyat adımı %x)", yuva sıradakine geçer.
  Liste, puan, şart, büyüklük, kâr al, stop değişmedi.
- **Denetim:** `verify.py features` TICK_REL'i demo exchangeInfo + REST kapanışla sıfırdan hesaplar; `audit/decide_check.py` D25_FROM_MS'ten sonra
  kaba adımlı coini seçimden çıkarır.
- **Deneme:** `bot.py --dry` 18:08 UTC hatasız (TICK_REL 30/30 ölçüldü; en büyük CYBER %0,307, TRUMP %0,084). Atlama kolu yapay sınırla (%0,02)
  denendi: CYBER "(fiyat adımı %0.31)" atlandı, yuvalar FIL, LINK, HYPE'a geçti. Not: denemeler canlı botla aynı IP'den çalıştığı için
  18:09:53 UTC'de Binance 429 (8 sn bekleme) oldu; bot kendiliğinden devam etti. Yedekler `*.bak_20261107_2105`.

## Değişiklik 26 (08.11.2026 02:43:10 UTC = 05:43 TR; kullanıcı: "önerinş uygula")
- **Sebep (botun 07.11 21:13 – 08.11 04:26 TR kaydı, 32 işlem, 10 kazanç, −66,66 $; gerçek fapi 1 dk mumları):** kayıp saatlerde
  (21:15–00:15, 02:45–04:30) listedeki 30 coinin ortalaması −%1,29 / −%0,77, kazanılan 01:30–02:45'te +%0,38. 00:15–01:30'da piyasa
  +%0,53 yükselirken giriş olmadı: düşüşten sonra "son 4 sa > 0" olan coin karar başına 2–5, iki şartı birden geçen 0; yükseliş sinyali
  sayacı 7 kez ≥ 20 oldu ama sayaç 5 dk'lık olduğu için sürekli yanıp söndü (gece 96 kararın 26'sında ≥ 20) → "60 dk sönük" hiç
  oluşmadı, sinyal hiç başlamadı. Karar anında piyasa son 30 dk artıdayken girilen 15 işlem 7 kazanç −9,11 $; eksideyken girilen 17 işlem
  3 kazanç −57,55 $. Tek gece; kanıt değil, kullanıcıya söylendi (bu şartla da o gece kalan işlemler zararda; kâra geçirdiği gösterilemez).
- **Kural:** giriş şartı **PİYASA son 30 dk artıda** (MKT_30 > 0) ve LC ≥ 2 (§2). MKT_30 = o anki listedeki (self.universe) coinlerin
  R30'larının eşit ağırlıklı ortalaması; R30 = karar anında biten 1 dk mumun kapanışı / 30 dk önce biten kapanış − 1 (ham, gerçek piyasa).
  Ölçülemeyen coin ortalamaya girmez; hiçbiri ölçülemezse giriş yok. Liste, puan, karar başına 1 giriş, fiyat adımı sınırı, 1.500 $,
  kâr al net +5 $, zarar stopu −5 $, 60 dk kontrolü DEĞİŞMEDİ. Açık ARB ve UNI pozisyonları kendi kâr al / stoplarıyla sürüyor.
- **Kayıt:** `scores.feats` ve `trades.feats` R30, MKT_30, MKT_N; journal her kararda "piyasa son 30 dk ±x% (n coin) ✓/✗"; GİRİŞ EMRİ
  satırında piyasa ve coin son 30 dk.
- **Silinen kod (kullanıcı kuralı: iptal = tüm iz):** bot.py `RET_4` ölçümü ve şartı, `RALLY_*`, `R5`, `rally_count`, sinyal kolu (boş yuva
  kadar giriş), `rally` olay yazımı, 🚀 Telegram mesajları, açılış metnindeki sinyal; `verify.py rally`, `RET_4` yeniden hesabı,
  `GAP_FROM_MS`/`D24_FROM_MS`/`GATE_RT_FROM_MS`/`RALLY_*` ve eski dönem şart denetimi; `audit/decide_check.py` sinyal ve 4 sa şartı.
  KURALLAR §2b silindi, §2 ve Değ. 24/25 metinlerindeki sinyal anlatımı kısa nota indi. Geri çekilme alışı iptali (kullanılmayan yol,
  `ENTRY_CHASE = True`) 4 sa yerine piyasa son 30 dk'ya bakar.
- **Duranlar (sorulacak):** `events` tablosunda kind `rally` satırları (07.11 20:56 TR'den beri her karar), `scores.feats`/`trades.feats`
  içindeki RET_4, R5, RALLY, RALLY_UP, RALLY_N, GATED değerleri, `*.bak_20261107_2045`, `*.bak_20261107_2105`, `*.bak_20261108_0535`
  yedekleri, `reports/` ve hafızadaki anlatımlar.
- **Deneme:** `bot.py --dry` 02:40 UTC hatasız (piyasa +%0,010, 30 coin ✓; şartı geçen 3; ARB açık olduğu için UNI seçildi = canlı botun
  aynı dakikadaki seçimi). `V9_DB=dry_run.db verify.py features 1794105600000`: R30, MKT_30, LC, puan dahil 30/30 fark 0, uyuşmayan 0.
  Yapay R30 testi (gerçek veri, dry Bot): hepsi eksi → piyasa −%0,276 ✗, şartlı 0, giriş yok; hepsi ölçülemez → MKT_N 0 ✗, giriş yok;
  hepsi artı → şartlı 2 (= LC ≥ 2 olanlar), ikisi de açık olduğu için seçilen yok (doğru).
- **Denetim:** `verify.py features [ts]` R30'u REST'ten ve MKT_30'u o kararın coinlerinden sıfırdan hesaplar, D26_FROM_MS'ten sonra şartı
  da denetler; `audit/decide_check.py` (varsayılan pencere D26_FROM_MS'ten) MKT_30'u coin kayıtlarından yeniden toplar, şart + seçim.
- Yeniden başlatma 02:43:10 UTC (02:40 sınırından 190 sn sonra, bekleyen giriş yok). Yedekler `*.bak_20261108_0535` (bot.py, verify.py,
  audit/decide_check.py, KURALLAR.md).

## Değişiklik 27 (08.11.2026 04:16:36 UTC = 07:16 TR; kullanıcı: "direkt bota ekle ve görelim demoda", seçim "Dördü de şart")
- **Sebep:** kullanıcı: "ne kadar arttığı önemli değil mi … ne kadar hızla arttı … belki o anlık bir peek attı". Değ. 26 yalnız işarete
  bakıyordu: 06:50 TR'de piyasa +%0,004 "artıda" sayıldı (PEPE alındı), +%0,66 ile aynı. Değ. 26 kararlarında (gerçek fapi 1 dk yol):
  06:05–06:25 yükselişi geniş (27–29/30 coin), tek coin katkısı en çok %0,08 (sıçrama değil); 06:20 ve 06:25'te son 5 dk eksi, piyasa
  tepeden −%0,22 / −%0,31 iken MKT_30 hâlâ artı → ADA, ARB alındı. 11 karar; kanıt değil, kullanıcıya söylendi. Eşikler (+%0,10, 20 coin,
  %0,10) Claude'un seçimi, veriye dayanmıyor (kullanıcıya soruda yazıldı).
- **Kural (§2):** MKT_30 ≥ +%0,10 VE MKT_UP ≥ 20 VE MKT_5 > 0 VE MKT_PEAK ≥ −%0,10 (biri ölçülemezse giriş yok) VE LC ≥ 2. Sabitler
  `MKT_MIN, MKT_UP_MIN, MKT_FAST_MS, MKT_PEAK_MAX = 0.001, 20, 5 dk, 0.001`. Liste, puan, karar başına 1 giriş, fiyat adımı sınırı,
  1.500 $, kâr al net +5 $, zarar stopu −5 $, 60 dk kontrolü DEĞİŞMEDİ. Açık pozisyonlar kendi kâr al / stoplarıyla sürer.
- **Kod:** `features()` R30'un yanında t−30 … t her dakikanın c/c(t−30)−1 yolunu (`_P30`, kayda girmez) üretir; `decide()` yolların
  ortalamasından MKT_5 / MKT_PEAK'i, R30'lardan MKT_UP / MKT_TOP'u hesaplar, `_P30`'u siler, hepsini her coin satırına yazar.
- **Kayıt:** `scores.feats` ve `trades.feats` MKT_30, MKT_N, MKT_UP, MKT_5, MKT_PEAK, MKT_TOP, MKT_PN; journal "piyasa son 30 dk ±x%
  (n coin), artıda k, son 5 dk ±y%, tepeden −z% ✓/✗"; GİRİŞ EMRİ satırında da.
- **Denetim:** `verify.py features [ts]` yolu REST 1 dk mumlarından sıfırdan kurar, MKT_UP/MKT_5/MKT_PEAK/MKT_TOP'u karşılaştırır,
  D27_FROM_MS'ten sonra dört şartı denetler. `audit/decide_check.py` MKT_30 ve MKT_UP'ı coin R30'larından yeniden toplar, MKT_5/MKT_PEAK'i
  botun kaydından alır (coinler arasında aynı mı), şart + seçim; ayrıca borsanın reddettiği giriş (events `enter_error`, karar anından
  60 sn içinde) artık atlanmış sayılır (06:10 TR METUSDT "Leverage 10 is not valid" yanlış uyuşmazlığı kapandı).
- **Deneme:** `bot.py --dry` 04:14 UTC hatasız (piyasa −%0,062, artıda 9, son 5 dk −%0,099, tepeden −%0,135 ✗, şartlı 0).
  `V9_DB=dry_run.db V9_D27_FROM_MS=1 verify.py features 1794111240000`: R30, MKT_30, MKT_UP, MKT_5, MKT_PEAK, MKT_TOP, LC, puan dahil
  30/30 fark 0, uyuşmayan 0. Yapay yol testi (scratchpad t27/test27.py; gerçek coin ölçümleri, yol + R30 yapay, botun decide()'ı):
  gerçek ✗; geniş düzenli +%0,30 ✓ (şartlı = LC ≥ 2 olan 25); küçük +%0,05 ✗; dar 15/30 ✗; tepeden düşüyor (+%0,6 → +%0,4) ✗;
  yol ölçülemez ✗; **son dakika sıçraması (+%0,3 tek dakikada) ✓ — bu şartlar henüz geri dönmemiş anlık sıçramayı yakalamaz**
  (kullanıcıya söylendi).
- Yeniden başlatma 04:16:36 UTC (04:15 sınırından 96 sn sonra, bekleyen giriş yok; açık BTC, ADA, 1000PEPE — PEPE 04:15'te Değ. 26
  ile piyasa +%0,00 iken alındı). İlk Değ. 27 kararı 04:20 UTC: piyasa −%0,153, artıda 6, son 5 dk −%0,097, tepeden −%0,170 ✗, giriş
  yok; `verify.py features 1794111600000` 30/30 fark 0, `decide_check` uyuşmayan 0. Yedekler `*.bak_20261108_0707` (bot.py, verify.py,
  audit/decide_check.py, KURALLAR.md).

## Değişiklik 28 (08.11.2026 04:36:30 UTC = 07:36 TR; kullanıcı: "sıçrama şartını da ekle")
- **Sebep:** Değ. 27 yapay testinde son dakikada +%0,3 sıçrama dört şartı da geçti (geri dönmemiş sıçrama yükseliş gibi görünür).
  Koşu yükselişi 30 dk'ya yayılır, sıçrama son 1–2 dakikada gelir. Gerçek kararlarda (Değ. 26 dönemi, gerçek fapi yol): 06:50 ve 07:15
  TR'de (PEPE alındı) 30 dk yükselişin tamamı son 2 dk'daydı (pay %1.532 / %2.951; öncesinde piyasa eksi); 06:05–06:25 yükselişinde
  son 2 dk payı −%26…+%3. Eşik (2 dk, %50) Claude'un seçimi, veriye dayanmıyor.
- **Kural (§2):** Değ. 27'nin dört şartı + MKT_JUMP = idx(t) − idx(t − 2 dk) ≤ 0,5 × MKT_30 (ölçülemezse giriş yok). Sabitler
  `MKT_JUMP_MS, MKT_JUMP_SHARE = 2 dk, 0.5`. Sıçrama anında AYIRT EDİLEMEZ; kural bekler: sonraki karar(lar)da sıçrama tutmuş ve yükseliş
  sürüyorsa (son 5 dk artıda, tepeye yakın, son 2 dk payı küçük) girilir; geri verdiyse "tepeden" şartı engeller; yerinde saydıysa
  "son 5 dk artıda" şartı engeller. Bedel: gerçek koşuda ≥ 5 dk geç ve daha pahalı giriş. Diğer her şey DEĞİŞMEDİ.
- **Kayıt:** `scores.feats` / `trades.feats` MKT_JUMP; journal ve GİRİŞ EMRİ satırında "son 2 dk".
- **Denetim:** `verify.py features` MKT_JUMP'ı REST yolundan sıfırdan hesaplar, D28_FROM_MS'ten sonra şartı denetler; `decide_check`
  botun kaydındaki MKT_JUMP ile (coinler arasında aynı mı) şartı yeniden kurar.
- **Yapay test** (scratchpad t27/test28.py, gerçek coin ölçümleri + yapay yol, botun decide()'ı): geniş düzenli +%0,30 ✓ (son 2 dk %7);
  son dakika sıçraması +%0,3 ✗; düzenli +%0,3 üstüne son dk +%0,3 ✗ (pay %53); sıçrama 7 dk önce + sonra yükselmeye devam ✓;
  sıçrama 7 dk önce + yerinde saydı ✗ (son 5 dk 0); küçük, dar, tepeden düşüyor, ölçülemez ✗ (Değ. 27 ile aynı).
- **Deneme:** `bot.py --dry` 04:33 UTC hatasız (piyasa −%0,193, artıda 2, son 5 dk −%0,149, tepeden −%0,287, son 2 dk −%0,042 ✗);
  `V9_DB=dry_run.db V9_D27_FROM_MS=1 V9_D28_FROM_MS=1 verify.py features` 30/30 fark 0 (MKT_JUMP dahil), uyuşmayan 0.
- Yeniden başlatma 04:36:30 UTC (04:35 sınırından 90 sn sonra, bekleyen giriş yok; açık yalnız 1000PEPE — BTC −0,91 $ ve ADA −3,39 $
  04:25'te 60 dk kontrolüyle kapandı). İlk Değ. 28 kararı 04:40 UTC: piyasa −%0,305, artıda 1, son 5 dk −%0,037, tepeden −%0,305,
  son 2 dk −%0,017 ✗, giriş yok; `verify.py features 1794112800000` fark 0, `decide_check` uyuşmayan 0. Yedekler `*.bak_20261108_0725`.

## Değişiklik 29 (08.11.2026 04:47:09 UTC = 07:47 TR; kullanıcı: "1 saatlik kontrol eğer coin ilk alındığından beri eksi değerdeyse
veya bu eksi değer gittikçe azalıyorsa ve coinin verileri artış yönündeyse işlemden çıkış yapılmasın ve 5er dk lık 1 saatlik pencere 3 kere
daha kontrol etsin sonra eğer yükselmiyorsa satsın eğer değer + ise kar yazıp çıksın")
- **Kullanıcı seçimleri (AskUserQuestion):** "yükseliyor" = **son 5 dk artıda** (+ son 60 dk ≥ −%0,2, mevcut ölçü); ek sürede artıya
  geçince **+%0,14'te sat** (≈ net +1 $; mevcut "kârda mıyız" eşiği PROTECT); ek kontrolde düşerse **hemen sat**; 75. dk'da hâlâ eksi
  → **sat** (en fazla 75 dk).
- **Kural:** `check_decide(grace, rise_ok, pnl_ok, up5)` (bot.py, saf fonksiyon): ek süre dışında (a)+(b) → tut; (a) + son 5 dk > 0 →
  tut, ek 1; yoksa sat (`kayan_kontrol`). Ek sürede (k ≥ 1): (b) → sat `ek_kontrol_kâr`; (a) yok ya da son 5 dk ≤ 0 → sat
  `ek_kontrol_düştü`; k ≥ 3 → sat `ek_kontrol_süre`; yoksa tut, k + 1. `GRACE_N = 3`. Satış piyasa emriyle (exit_market, eskisi gibi).
  Kârdaki (≥ +%0,14) ve yükselen pozisyon eskisi gibi tutulur (ek süre yok, +5 $ kâr al beklenir).
- **Kod/kayıt:** `Pos.grace` (state.json; eski koda geri dönülürse bu alan Pos(**p)'yi bozar → önce silinmeli); `features()` R_5M
  (scores.feats'e de yazılır); `p.checks` girdisine r5, grace, sell, why; ek süreyle ilgili her kontrolde events kind `ek_kontrol`
  (sym, t, fill_ms, entry, bid, r_t, r5, rise_ok, pnl_ok, grace_before, grace_after, sell, why); journal kontrol satırında "son 5 dk",
  "ek kontrol k → k'/3", "→ tut / SAT (sebep)"; REASON_TR'ye üç yeni çıkış sebebi (Telegram). checks tablosu sütunları aynı (sell =
  gerçek satış; dry'de 0).
- **Denetim:** `audit/grace_check.py` (yeni, bot.py'yi içe aktarmaz): her `ek_kontrol` olayında kâr eşiğini, son 60 dk bandını ve son 5
  dk'yı (REST 1 dk mumlarından sıfırdan) yeniden kurar, kararı ve sayaç sırasını (5 dk arayla, ardışık) ve trades çıkış sebebini
  denetler. `verify.py features` R_5M'yi REST'ten karşılaştırır. `audit/closed_check.py` hâlâ Değ. 24 öncesine göre (eski açık iş).
- **Testler:** birim (scratchpad t27/test29_unit.py): 4 sayaç × 8 durum = 32 durum, kullanıcı cevaplarından yazılan kural tablosuyla
  fark 0; zaman çizelgeleri: hep eksi + yükseliyor → 60 tut, 65 tut, 70 tut, 75 SAT süre; 70'te +%0,14 → SAT kâr; 65'te son 5 dk eksi
  → SAT düştü; 60'ta son 5 dk eksi → SAT kayan_kontrol; kârda + yükseliyor → eskisi gibi tut. Entegrasyon (t27/test29_dry.py, dry Bot,
  gerçek demo alışı, sahte BTCUSDT pozisyonu, botun decide() döngüsü): A tut/tut/tut/SAT süre (4 olay), B tut/SAT düştü, C tut/tut/SAT
  kâr, D (son 60 dk −%0,3) SAT kayan_kontrol (olay yok); dry'de emir yok. Test sonrası dry_state.json'daki sahte pozisyon silindi.
- Yeniden başlatma 04:47:09 UTC (04:45 sınırından 129 sn sonra, bekleyen giriş yok; açık 1000PEPE 04:47:18'de borsadaki stopla −5,13 $
  kapandı). Yedekler `*.bak_20261108_0744` (bot.py, verify.py, KURALLAR.md).

## Değişiklik 30 (08.11.2026 07:01:33 UTC = 10:01 TR; kullanıcı: "bot aynı zamanda hem long hem de short açma kararını verecek kabiliyete getir çünkü ne yaparsak yapalım long'da da short'ta da ani ters sıçramaları bilemiyoruz ya da 60 dk'lık pencere içinde bulunan sıçramaları da izleyelim")
- **Kullanıcı seçimleri (AskUserQuestion):** sıçrama için "Girişte coin sıçraması" + "Açıkken ters sıçramada çık" (üçüncü seçenek "Sadece
  kaydet" seçilmedi; yine de her ölçüm kayda girer); yuvalar "4 yer ortak". Short tanımı (long şartlarının aynası), short puanı ve
  eşikler (%50 sıçrama payı, %0,20 ters sıçrama) **Claude'un seçimi, veriye dayanmıyor**. Not: kullanıcı daha önce Değ. 19 al-sat
  sepetini iptal ettirmişti; bu kez short'u kullanıcı kendisi istedi.
- **Kural:** §2b (yön), §3 (short puanı), §4 (short kontrolü), §5 (60 dk sıçramalı coin), İşlem (short emirleri, açıkken ters sıçrama).
  Saf fonksiyonlar (bot.py): `market_side`, `coin_spike`, `check_inputs`, `sd`; yöntem `spike_check` (her dakika, karardan önce;
  kapattığı coin `decide(t, pre_sold)` ile o turda yeniden alınmaz). `SHORT_ON = True` (False → yalnız long, eski hâl).
- **Kod/kayıt:** `Pos.side` (state.json; eski kayıt = LONG); `trades.side`, `scores.side` + `scores.score_s`, `checks.side`; yeni tablo
  `spike_checks`; events `spike_exit`, `spike_error`; `ek_kontrol` olayına side, ask, px. finalize: giriş dolumları = giriş yönündeki
  (short'ta SELL) entry_oids, çıkış = ters yön; kâr = yön × (çıkış $ − giriş $) − komisyon + fonlama. Journal/Telegram: GİRİŞ EMRİ /
  POZİSYON / ÇIKIŞ / kontrol satırlarında yön; karar satırında "artıda / ekside", "dipten", "→ LONG / SHORT / yön yok". REASON_TR
  `ters_sıçrama`; `ek_kontrol_düştü` metni "ek kontrolde coin ters döndü".
- **Denetim:** `verify.py features` LC_DN, COIN_J_UP/DN, MKT_DN, MKT_TROUGH'u REST'ten sıfırdan, yönü ve short puanını bağımsız hesaplar
  (`D30_FROM_MS`); `audit/decide_check.py` yön, LC/LC_DN şartı, short puanı, sıçramalı coin atlaması, engel yalnız long; ayrıca yuva
  sayımı düzeltildi: borsadaki kâr al / stop karardan (t + 12 sn) sonra dolduysa coin karar anında açık sayılır (04:10 PEPE yanlış
  alarmı; eski sürümle 1, yeniyle 0 uyuşmaz / 51 karar). `audit/grace_check.py` short aynası; `audit/pnl_check.py` açık short'ta kâr
  al / stop formülü; YENİ `audit/spike_check.py` (her spike_checks satırını REST 1 dk mumlarından yeniden kurar, karar, pencere,
  kapsam, çıkış sebebi). `status.py` yön gösterir. `audit/closed_check.py` hâlâ Değ. 24 öncesine göre (eski açık iş).
- **Testler (gerçek emir yok):** scratchpad t30/test30_unit.py — piyasa yönü 8 örnek + 200.000 rastgele (bağımsız yazılmış ayna formülü),
  coin sıçraması 7 + 100.000, kontrol girdileri 100.000, sahte borsayla tam ömür (SHORT XMR kârda/zararda, LONG XMR, SHORT 1000PEPE:
  giriş SELL GTX en iyi satışta, stop BUY closePosition MARK, kâr al BUY reduceOnly, kâr al net +5,006/+5,018 $, stop brüt −4,98 $,
  kapanış BUY MARKET, trades.pnl beklenenle 1e-9), ters sıçrama 5 pozisyon (long −%0,25 kapat, short +%0,25 kapat, −%0,10 tut, dolumdan
  önce başlayan pencere bakılmaz, short lehine −%0,30 tut) → hata 0. t30/test30_decide.py — decide() sentetik 30 coin, 15 karar
  (düşüş → SHORT, yükseliş → LONG, karışık → yön yok; long + short puanı bağımsız sıra-yüzdesi ile 1e-12; sıçramalı en iyi coin atlandı)
  → hata 0. Gerçek veri deneme (`--dry`, 06:57 UTC): piyasa −%0,50, 28 coin ekside → SHORT, seçilen BCHUSDT; `verify.py features`
  (V9_DB=dry_run.db) 22 ölçüm + yön + iki puan fark 0; decide_check seçim ✓ (DOGE, TIA sıçramalı atlanacaktı).
- Yeniden başlatma 07:01:33 UTC (07:00 sınırından 93 sn sonra; açık / bekleyen pozisyon yok). Yedekler `*.bak_20261108_0648` (bot.py,
  verify.py, KURALLAR.md, status.py, audit/decide_check.py, grace_check.py, pnl_check.py).
