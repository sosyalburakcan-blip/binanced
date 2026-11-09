---
name: binanced-paper-service
description: "binanced kâğıt takip + demo emirleri VPS'te systemd servisi (trend-paper), tek 3× hesap, kural L6_z2_k3 (3 saat takip)"
metadata:
  node_type: memory
  type: project
  originSessionId: 345f7e76-11cb-4152-bcd4-dc7b27294eec
  modified: 2026-11-08T04:48:02.018Z
---

**08.11 16:38 UTC: BOT DURDURULDU** (kullanıcı: "botu ve tüm her şeyi durdur"). `v9-demo` stop + disable (açılışta başlamaz). Bekleyen WLD girişi iptal, ETH/HYPE short elle kapatıldı (net ≈ −2,8 $, live.db'de yok, kayıt v9live/MANUEL_KAPANIS_2026-11-08.md). Demo hesapta pozisyon 0, emir 0, bakiye 4.242,60 $. Aşağıdaki 'çalışıyor' ifadeleri artık geçersiz. Bkz. [[github-export-2026-11-08]].

2026-11-05'ten beri /root/binanced kâğıt takip (gerçek emir yok) bu VPS'te `trend-paper` systemd servisi olarak çalışıyor
(deploy/trend-paper.service, journalctl -u trend-paper, DB data/live/live.db yeni başladı). Kullanıcı eski bilgisayardaki
kopyayı kapattı (eski live.db geçmişi orada kaldı).
Kullanıcı kararı: tek hesap, maker, spot ve BTC-200 yok. Kural 05.11 10:40'tan beri L6_z2_k3_tp4_sl4_h72 (3 saat takip,
~270 işlem/yıl; bekletmede spot −%18,7/yıl, kullanıcıya söylendi); öncesi L6_z2_k6_tp4_sl4_h72 (hesapları live.db'de kalır).
İlk `.env` anahtarı gerçek hesabın salt okunur anahtarıydı (IP kısıtlı, VPS <VPS_IP>).
05.11 07:38: kullanıcı `.env`'yi yeni gerçek anahtarla değiştirtti (spot işlem AÇIK, vadeli/çekim kapalı, IP kısıtlı; secret
sohbette yazıldı → yenilemesi önerildi; eski salt okunur anahtar .env.bak_20261105_0738). Gerçek hesapta bakiye ~0 (kırıntı).
Testnet: src/trend/live/testnet.py (canlı botun aynısı; veri/sinyal/fiyat/tetik GERÇEK piyasadan, emirler testnete;
SignedRest yalnızca demo-fapi/testnet.binancefuture adreslerine izin verir). Anahtar `.env.testnet`
(BINANCE_TESTNET_API_KEY + _SECRET ya da _PRIVATE_KEY_PATH=/root/.binance/demo_ed25519_private.pem); boşken testnet kapalı.
demo-fapi = testnet.binancefuture (aynı defter); ayrı ve sığ piyasa (~7 bps kayık).

05.11 08:52: ilk demo anahtarı -1022 verdi (self-generated açık anahtara bağlı değildi).
05.11 09:09: kullanıcı Binance'in ürettiği (System generated) Ed25519 demo anahtarı verdi → `.env.testnet` yeni key +
/root/.binance/demo_ed25519_sysgen_private.pem (eski: .env.testnet.bak_20261105_0910). İmzalı çağrılar OK; servis yeniden
başlatıldı: exec_ready (10 sembol İZOLE 3×, tek yönlü), kullanıcı akışı bağlı, hesap L6_z2_k6_tp4_sl4_h72/testnet3x
(sanal 1.000 USDT; demo cüzdan ~4.770 USDT). Testnet emirleri artık kâğıtla yan yana gidiyor.

05.11 09:30 kullanıcı kuralları (testnet.py): bütçe borsadan = min(USDT cüzdan, kullanılabilir + botun marjini) × balance_frac 0,20
(MAX_BALANCE_FRAC; TOPLAM marjin, 3 yuvaya bölünür — kullanıcı 05.11 'toplam %20 doğru' diye onayladı);
kaldıraç MAX_LEVERAGE=3 (fazlası ValueError), positionRisk geri okuma + her mutabakatta denetim → bozuksa blocked + 3× geri.
Uçtan uca demo denemesi BNBUSDT (evren dışı): GTX giriş 1,33 BNB maker, TP borsada, zorla SL → maker çıkış, temiz kapandı.
05.11 09:50 acil stop eklendi (kullanıcı isteği): borsada STOP_MARKET closePosition −%6 MARK_PRICE, YALNIZCA Algo Order API
(/fapi/v1/algoOrder; eski uç −4120; pozisyonsuz −4509). Tetiklenen emrin c = clientAlgoId; borsa pozisyon sıfırlanınca
azaltmalı TP'yi ve closePosition stopu kendisi düşürür. Demo'da canlı doğrulandı (tetik + bot çıkışında iptal).
Aynı gün düzeltilen yarış: mutabakat eski anlık görüntüyle canlı emri GONE sayıp çift giriş emri açıyordu → ack_ms < t_fetch şartı.

05.11 10:15 aylık liste otomatiği: src/trend/live/universe_live.py (REST 1d son 1000 gün → trend.universe kendi
fonksiyonları; 12 ay resmi listeyle birebir, 2026-11 bayt bayt aynı). Çıktı data/live/universe/ (G12 kilidi universe/,
meta/'ya yazılmaz). paper.py: listeden çıkan ama açık pozisyonlu coin izlenir, sıralamaya girmez (held_only).
deploy/trend-universe.{service,timer} yazıldı ama KURULMADI: systemd kurulumu izin sınıflandırıcısınca reddedildi →
kullanıcı kendisi kuracak (cp + daemon-reload + enable --now trend-universe.timer).

05.11 17:07 kullanıcı isteğiyle `systemctl stop trend-paper` (v5 ivme backtest'ine CPU için; demo hesapta
pozisyon/emir/algo emir yoktu, doğrulandı). Servis enabled kaldı; yeniden başlatma kullanıcıya sorulacak.
Aynı gün v5 ivme testi bitti (reports/V5_ivme.md, experiments 26–28): reddedildi ama bekletmede şu anki kuraldan
belirgin iyi (en iyi S6_a2_e0.7_tp4_sl4_h72); canlıya alma/bot yeniden başlatma kararı kullanıcıda.
Aynı gün v6 (26 özellikli tahmin modeli, reports/V6_tahmin.md) da reddedildi; kuru provada bekletme sızdı (açıklandı).

**Why:** Kullanıcı canlının birebir taklidini ve sonra demo API ile otomatik emir istiyor.
**How to apply:** Gerçek hesaba kullanıcının açık kararı olmadan asla emir gönderme; testnet kâğıtla yan yana çalışır. Bkz. [[vps-germany]].

06.11 06:22: YENİ `v9-demo` systemd servisi kuruldu ve çalışıyor (enabled; /etc/systemd/system/v9-demo.service, kod
/root/binanced/v9live/bot.py, kurallar KURALLAR.md, özet status.py, kayıt live.db/state.json). Aynı demo hesabı kullanıyor.
Çakışmasın diye eski `trend-paper` DISABLE edildi (zaten durmuştu; geri: systemctl enable trend-paper). Emir türleri
LTCUSDT'de duman testiyle doğrulandı (GTX, market, TP reduceOnly, Algo STOP_MARKET closePosition ve reduceOnly+quantity, −2021).
06.11 06:38: kullanıcı isteğiyle v9-demo'da 2× masraf KORUMA EMRİ KAPATILDI (PROTECTION_ON=False; "1 sa içinde salınım olabilir,
araştırılmalı"). Kalan: %3 TP, −%6 acil stop, saatlik kontrol (07:45'ten beri: son saat > 0 VE ≥ +%0,14 kâr; biri yoksa sat; ayrıntı [[binanced-bot-audit-2026-11-06]]). Kullanıcı istiyor:
saatlik tut/sat kararı ileride "ivme/yükseliş devamlılığı" araştırmasından çıkacak bir PUANLA verilsin (henüz yapılmadı).
06.11 06:49: v9-demo'ya GÖZLEM eklendi (kullanıcı: "kaç saate yükselir ne olur baksın hep"; kararı ETKİLEMEZ): live.db
`outcomes` tablosu, her saat her coin için s=t−24 sa: o an yükseliş/hızlanma kaç saattir (up/acc_streak_at, lc_at) → sonraki
1–24 sa getiri, kaç saat daha yükseldi, +%3/−%6'ya değme saati. İlk çalıştırmada son ~150 saat geriye dönük dolar. status.py
"Gözlem" tabloları. Defter görüntüleri de live.db `depth` tablosunda (restart kaybı yok).
06.11 08:46:47 UTC (kullanıcı: "tam defter kayıt ve 3 saate silinmesin") v9-demo yeniden başlatıldı: TAM emir defteri arşivi
v9live/book/YYYY-MM-DD.db (tablo book: ts, sym, last_update_id, E, T, n_bids, n_asks, raw = Binance yanıtı bayt bayt lzma;
ts = depth özetiyle aynı), dakikada bir 30 coin, ek istek yok, ≈6–9 KB/görüntü ≈ 350 MB/gün (29 GB boş → ~75 gün).
depth özeti artık SİLİNMEZ (eskiden 3 sa). Bot hiçbir şey silmez; disk < 3 GB → yalnızca tam defter yazımı durur + telefon
uyarısı, yer açılınca sürer. Bağımsız denetim: verify.py book [DAKİKA]. status.py "Defter kaydı" bölümü. Yedekler *.bak_20261106_0845.
Açık kalan (kullanıcıya söylendi, karar bekliyor): kapanan işlemde Binance emir numaraları trades'e yazılmıyor; hatalar telefona gitmiyor.
06.11 09:05 kullanıcı: "pozisyon girişi 150 dolar, kaldıraç 10x" → bot.py NOTIONAL=150, LEV=10 (teminat 15 $; kullanıcıya
iki okuma soruldu, pozisyon=150 $ seçildi). **06.11 10:34 kullanıcı: "işlem teminatı 150 dolar" → NOTIONAL=1500 (teminat 150 $, 10×).** Kaldıraç yanıtı geri okunur, dolumdan sonra positionRisk kaldıraç+tasfiye
kaydı (state lev/liq_px, trades.lev; boş=1×). 30 coinin hepsi demo'da ≥10×; tasfiye ≈ −%8,2…−%9,6, acil stop −%6 önce.
Önceki 1× pozisyonlar 1× kalır. Yedekler *.bak_20261106_0905. Yeniden başlatma 09:06:36 UTC (NEAR/ONDO girişleri bitince; açık GTC/NEAR/ONDO 1× 100 $ kaldı). İlk 10× giriş henüz yok: yeni kod yolu (kaldıraç geri okuma, positionRisk tasfiye) ilk girişte borsadan denetlenmeli.

**06.11 11:40:21 UTC yeniden başlatma (kullanıcı: "b ekle ve test et etkileyip etkilemediğini"):** giriş ENGELİ eklendi:
son saat r_t > 0 VE OI_1 < 0 VE SPOT_REL_1 < 1 (spot/vadeli $ hacim oranı ÷ önceki 168 sa ortancası) → "short_kapatma+spotsuz",
girilmez, yuva sıradakine (SPOT_FILTER_ON). Puan değişmedi. Spot = api.binance.com 1h (1000PEPE→PEPE; Q/JCT/AGT spotsuz →
engel yok). live.db `labels` tablosu (etiket, block, blocked, chosen); status.py "Etiket etkisi" (engelli vs diğer, atlanan vs
girilen; sonraki 1/4/24 sa, 95% aralık, grup başı ≥30 olmadan karar yok). Bağımsız denetim audit/label_check.py [db] [ts]
(11:00 deneme 30/30). Deneme modu artık dry_run.db + dry_state.json'a yazar. Yedekler *.bak_20261106_1140.
Test = demo'da ileriye dönük kayıt (backtest DEĞİL; kullanıcı backtest önermememi istedi).
**06.11 11:48:29 yeniden başlatma (kullanıcı: "150 dolar teminatlı büyük işlemde 5 dolar kâr yeterli olur"):** hedef ≥ 1.000 $
pozisyonda kâr al = net +5 $ (maker giriş+çıkış ücreti düşülmüş; 1.500 $'da ≈ +%0,37), TP_NET_USD/BIG_NOTIONAL, tp_price();
küçük eski pozisyonlar +%3. Başlangıçta borsadaki TP kurala uymuyorsa taşınır (SAND 0,04519 → 0,04404, exch_check ile doğrulandı).
Saatlik kontrol ve −%6 acil stop (−90 $) aynı → kazanç +5 $, kayıplar daha büyük (kullanıcıya söylendi).
**06.11 11:50:11 yeniden başlatma (kullanıcı: "kâr alınmadıysa hâlâ pozisyon açıksa 3'ten fazla yani 8'e kadar işlem açılabilir"):**
SLOTS = 8 (önce 3). 8 × 150 $ teminat = 1.200 $; hepsi acil stopa değerse ≈ −720 $ (kullanıcıya söylendi). Yedek *.bak_20261106_1152.
(Başlangıç mesajı metni "kâr al büyükte net +5 $" olarak düzeltildi; sonraki yeniden başlatmada görünür.)
**06.11 11:51 kullanıcı: "100 dolarlık ve 15 dolarlık işlemleri kapat"** → bot durduruldu, botun kendi exit_market yoluyla
ONDO (1×, 100 $) +0,92 $ ve TAO (10×, 150 $) +0,90 $ kapatıldı (reason kullanici_kapatti, trades'te), 11:51:31 yeniden başladı.
Borsada yalnızca SAND (1.500 $) + TP 0,04404 + acil stop kaldı (exch_check doğruladı). Not: servis saat başından SONRA
başlarsa o saatin kararını atlar (next_hour = bir sonraki saat) → yeniden başlatmaları :00'dan önce yap.
**06.11 12:14:47 yeniden başlatma (kullanıcı: "telegram yazılarını düzenle… giriş çıkış yeşil, kaybedenler kırmızı yuvarlak"):**
Telegram'a artık yalnızca 🟢 GİRDİ (dolunca: saat, adet×fiyat=$, kaldıraç/teminat, kâr al, acil stop) ve 🟢/🔴 ÇIKTI
(çıkış türü, giriş→çıkış saati+süre, fiyat %, fiyat kârı, komisyon giriş+çıkış ayrı, fonlama ≠0 ise, NET + teminata göre %).
"GİRİŞ EMRİ" ve eski POZİSYON/ÇIKIŞ satırları yalnız journal'a. Saatler TÜRKİYE saati (MSG_TZ, varsayım; kullanıcıya söylendi), ondalık virgül.
Yedek bot.py.bak_20261106_1215. Deneme: scratchpad msgtest.py gerçek WLD/SAND/PEPE verisiyle, DB'deki ücret/net ile birebir.
**06.11 12:49:27 yeniden başlatma — KAYAN PENCERE (kullanıcı: "her saat başı yenilenmesin, her dk 1 saatlik pencere olsun"):**
karar her dakika (dakika kapanışı +3 sn, decide(t)); tüm pencereler 1 dk mumlardan t'den geriye (son 60 dk, N×60 dk; m1 önbelleği
KL_KEEP=2900, her dk ağırlık 1). Kullanıcı seçimleri (AskUserQuestion): giriş+çıkış ikisi de kayan; kontrol girişten 60 dk sonra
başlar sonra HER DAKİKA (CHECK_AFTER_MS, sebep `kayan_kontrol`, `checks` tablosu); satılan coine bir sonraki dakikadan itibaren
yeniden girilebilir. İstisnalar: OI_1 5 dk adımlı (Binance 5 dk yayımlar); SPOT_REL_1 tabanı + outcomes saatte bir (hour_jobs).
scores/labels her dakika (≈25 MB/gün); status.py etiket testinde yalnız saat başı / coin-saat başına bir satır (çoğaltma yok).
verify.py ve audit/label_check.py dakikalık; dry 12:46 + saat başı 12:00 bağımsız denetimde 30/30 fark 0. Yedekler *.bak_20261106_1245.
İlk dakika 12:50'de 6 giriş (13:00 beklenmedi).
**06.11 13:17:03 yeniden başlatma (kullanıcı seçimi A):** giriş şartına son 60 dk r_t > 0 eklendi (ENTRY_RT_POSITIVE; önce FIL/LINK/HYPE/SOL
son 60 dk eksideyken giriyordu; puanın alt sınırı yok, 8 yuva şartı geçen hemen herkesi alıyordu). verify.py GATE_RT_FROM_MS.
**13:24:45:** MIN_DELAY_S 3 → 12 (kapanan 1 dk mum REST'te +3 sn'de 30 coinin 11–13'ünde kesin değil, +8 sn'de hepsi doğru; kararlar
etkilenmemişti). **13:27:42:** absorb() avgPrice=0 hatası (ZEC giriş 726,8 sanıldı, acil stop 683'e taşındı) düzeltildi + state elle
düzeltildi. YENİDEN BAŞLATMA KURALI: status pending VEYA (open ve tp_cid boş) pozisyon varken yeniden başlatma — giriş sürüyor demek.
Kullanıcı: "her dk 1 saat için geçerli olmalı" = mevcut kayan pencere (son 60 adet 1 dk mum), değiştirilmedi.
**06.11 14:13–14:14 UTC yeniden başlatma (Değişiklik 11):** coin listesi HER DAKİKA = tüm USDT perp'lerden Binance 24 sa değişimi > 0
olanların 24 sa hacme göre ilk 30'u (uni24 tablosu; sabit coin yok; yeni coin ≈30 dk defter birikene kadar puanlanmaz); SLOTS 4;
borsada −5 $ zarar stopu (zs, MARK_PRICE, max(giriş−5/adet, −%6)); açıklara da uygulandı (ZEC/HYPE/FIL/STRK satıldı, −58 $);
bakiye Telegram'da; düzeltmeler: takılı çıkış, MARKET maxQty bölme, dolum toleransı. verify.py universe komutu. Gün: 29 işlem −148,78 $,
USDT 4.620 $.
**06.11 14:39:21 UTC (Değişiklik 12, kullanıcı seçimi C):** kararlar YENİDEN SAAT BAŞI (HOURLY_DECIDE; saatlik kontrol fill_ms < t,
sebep saatlik_kontrol); liste her dakika yenilenir ama yalnız defter görüntüsü için. Sebep: kayan "son 60 dk > 0" saatte ~4 kez işaret
değiştiriyor, %27'si 1 dk'lık sapma. Kâr al +5 / −5 $ stop borsada sürekli. 14:39'da açık pozisyon yoktu.
**06.11 18:09:53 UTC yeniden başlatma (Değişiklik 13; kullanıcı: "bu sistemi yapmak istiyorum … stop loss −12 dolar" + seçim "oynaklık sınırı ekle"):**
karar 5 DK'DA BİR (DECIDE_STEP_MS; :00/:05 +12 sn), pencere uçları = son 5 adet 1 dk kapanış ortalaması (SMOOTH_N; RET_4/LC/r_t/r_prev/ACC_1/SMOOTH_4 payı),
bant ±%0,2 (BAND: giriş r_t > +%0,2, kontrol (a) r_t ≥ −%0,2; (b) +%0,14 anlık demo aynen), kontrol girişten 60 dk sonra 5 dk'da bir;
STOP_USD 5 → 12 (≈ −%0,8, başa baş ≈ %72 kazanma, kullanıcıya söylendi); liste: 24 sa > 0, hacim sırası, VOL60 ≤ %2 (son 1.500 dk 1 dk
kapanış, 60 dk getirilerin std'si, 5 dk sınırında; uni24.vol60, uni_excl tablosu). labels/etiket HAM r_t (r_t_raw) ile kaldı.
Gürültü ölçümü (kâr testi değil): 5 dk ham 1,77 değişim/sa %55 geri dönüş → ort.+bant 0,92 / %18. verify.py V9_DB ortam değişkeni.
Deneme 18:08: features 30/30 fark 0, universe VOL60 fark 7e−18. Yedekler *.bak_20261106_1805. KURALLAR.md üst bölümler güncellendi.
**06.11 19:00:26 UTC yeniden başlatma (Değişiklik 14; kullanıcı: "sebepleri tersine çevir, uyumsuz mantığı düzelt"; 4 seçimin hepsi önerilen):**
pozisyon = min(1.500 $, 12 $ / VOL60) (RISK_USD); kâr al = giriş×(1+VOL60), zarar stopu = giriş×(1−VOL60) (BRACKET_K=1, eşit; başa baş ≈%53);
giriş = sinyal anı demo alışın %0,2 altına SABİT post-only (PULLBACK, kovalama yok; trend bozulursa karar anında iptal `pullback_cancel`; 15 dk);
karar başına en çok 1 yeni giriş (MAX_NEW_PER_TICK). Pos.vol/pb_px/ref_px; vol=0 olan eski pozisyonlar (FIL, QNT, HYPE, AVAX) eski kural
(+5 $ / −12 $) ile biter — yeniden başlatmada emirleri değişmedi (exch_check). Denetim: audit/bracket_check.py [başlangıç_ms=1793991626858].
Gerekçe gözlemi: 4 giriş 2 sa zirvesinin %0,07 yakınında, hepsi 1 dk sonra girişin altında (zirveden alma + maker dolum düşüşte + korelasyon).
Kullanıcıya söylendi: yapısal dezavantajları kaldırır, tahmin gücü kazandırmaz.
**07.11 04:30:44 UTC yeniden başlatma (Değişiklik 15; kullanıcı: "en fazla hacme sahip coin evrenine geri dönüyoruz, hacim az coinde emir dolana kadar zarar"):**
seçimler "Bugünün en büyük 30'u" (UNI_REQUIRE_UP=False: '24 sa artıda' şartı listeden VE giriş şartından kalktı; VOL60 ≤ %2 sürer) +
"Hemen al (eski hâli)" (ENTRY_CHASE=True: en iyi alışa GTX, 30 sn'de takip, 15 dk; pb_px=0). Büyüklük/±VOL60/5 dk/1 giriş/4 yuva aynı.
Kullanıcıya söylendi: geç dolum listeden değil geri çekilme alışından (ortanca ~1 → ~5 dk, büyük coinlerde de); "+6 $ gördü" AIO'nun kâr alı +12 $'daydı
(dolum sorunu değil). verify.py GATE24_TO_MS, audit/bracket_check.py pb_px=0 desteği, KURALLAR.md Değişiklik 15. Yedekler *.bak_20261107_0735.
Not: decide() "dakika …" satırını yalnız giriş/çıkış varken ya da :00/:15/:30/:45'te yazar → karar olup olmadığını live.db scores'tan bak.
**07.11 04:56:51 UTC yeniden başlatma (Değişiklik 16; kullanıcı: "ivme farkını puandan çıkar"):** SCORE_EXCLUDE=("ACC_1",), puan = LC+SMOOTH_4+
TAKER_1+IMB1_1+BIDSHARE_1+OI_1 (ACC_1 ölçülür/kaydedilir). Gerekçe lossreview/RAPOR.md (69 işlem: kaybeden ACC_1 +%0,75 / kazanan +%0,06, p 0,008;
"tepeden alma" desteklenmedi; zararın kaynağı gerçek fiyat −357 $, demo farkı −0,84 $). verify.py features artık puanı da bağımsız hesaplar
(NOACC_FROM_MS). Yeni listedeki coinler ilk ~30 dk defter görüntüsü < 30 olduğu için puanlanmaz (IMB1_1/BIDSHARE_1 boş; geçici).
**07.11 05:19:47 UTC yeniden başlatma (Değişiklik 17; kullanıcı: "çok yükselmiş coinleri alma"; seçim "Yerinde saymışı al"):** ENTRY_CALM=True →
giriş şartı RET_4 > 0, LC ≥ 2, −%0,2 ≤ son 60 dk (r_t) ≤ +%0,2 (önce > +%0,2). Gerekçe lossreview/RAPOR.md 2. tur (önceki 60 dk ↔ sonraki 60 dk
ρ −0,43; kümelenmiş p 0,055, kanıt değil). verify.py CALM_FROM_MS. Not: kazanan/kaybeden girişte defter/piyasa/fonlama farkı YOK; BTC 4 sa farkı
zaman kümelenmesiydi.
Not (07.11): kullanıcı bazen pozisyonu Binance iOS uygulamasından ELLE kapatır (ETHFI 07:45 TR, +5,15 $). Bot bunu trades'e reason
"bilinmiyor", ücret 0 diye yazar. "bilinmiyor" görünce demo userTrades → /fapi/v1/order clientOrderId'ye bak (ios_/android_/web_ = elle).
**07.11 09:15:44 UTC yeniden başlatma (Değişiklik 18; kullanıcı: "hacim ve emir defteri alıcı yoğunluğu gösterirse gir … gölge değil direkt dene" + seçim "Henüz kıpırdamamış"):**
BOOKFLOW_ON: yerinde saymış şartına EK TAKER_15 > 0,5, VOLR_15 > 1 (15 dk hacim / 4 sa ort. 15 dk), NB_IMB02 > 0 (±%0,2 defter dengesi, son 5 görüntü),
BUILD_05 > 0 (±%0,5 denge son 5 dk − 15–20 dk önce); puan aynı. live.db `depth2` tablosu; restart'ta son 30 dk arşivden (`band_sums`). Denetim
`verify.py flow [ts]` (V9_FLOW_FROM_MS); ilk canlı karar 09:20: 30/30 fark ≤ 1,1e−16, şart 0 = 0, features 0 fark. Tam defter arşivi 06.11 08:46'dan
beri, eksik dakika 0. Temel şartı geçen 4–5 coinden akış şartıyla 0–3 kalıyor. Yedekler *.bak_20261107_1205. Gerekçe [[allreview-2026-11-07]].

**07.11.2026 12:52 UTC (15:52 TR) Değişiklik 20:** 11:11–12:47 UTC denenen al-sat sepeti (Değ. 19) kullanıcı isteğiyle iptal edildi
("sepet mantığı berbat bir şey") ve tüm izi silindi (kod, live.db/dry_run.db işlemleri + side/basket sütunları, yedekler, KURALLAR bölümü,
ön kayıt, pair_check.py). Bot Değ. 18: `bot.py`/`status.py` = `*.bak_20261107_1357` birebir. live.db toplamı demo bakiyesinden +1,16 $
farklı (silinen 6 işlem). Al-sat / sepet / short fikrini yeniden önerme. Bkz. [[rule-cancel-delete-all]].

**07.11 ~16:30 TR tam doğrulama** (kullanıcı: "çalışma mantığına bak, her birini doğrula"): yeni `audit/decide_check.py`, `audit/closed_check.py`;
`pnl_check.py` zamana göre eşleştiriyor. Hepsi tuttu; tek hata fonlama kaydı: çıkış fonlamadan ≈ 25 sn sonra → borsa kaydı henüz yok → 0 yazılıyor
(ETH 00:00, ONDO 08:00 UTC, 0,15'er $). **Değ. 21 (~16:26 TR, kullanıcı "evet düzelt") düzeltildi:** funding_recheck() kapanıştan ≥ 3 dk sonra
fonlamayı yeniden okur, gerekirse pnl'yi günceller + telefona 🔧 not; 2 eski kayıt düzeltildi. Yedekler *.bak_20261107_1621. Demo en iyi alış geçmişe dönük doğrulanamaz.

**07.11 14:01:07 UTC (17:01 TR) Değişiklik 22** (kullanıcı: "hacim şartını kaldır"): `VOLR_GATE_ON = False` — VOLR_15 > 1 giriş şartı yok (ölçülüp kaydediliyor);
diğer akış şartları (TAKER_15 > 0,5, NB_IMB02 > 0, BUILD_05 > 0) ve temel şart aynı. verify.py/decide_check.py `VOLR_TO_MS = 1794060067000`. Yedekler *.bak_20261107_1656.

**07.11 19:11:31 TR (16:11:31 UTC) Değişiklik 23** (kullanıcı: "her girdiği işleme direkt +5 dolar kârını hesaplayıp emir koyulsun ve stoploss kaldırılsın";
seçimler: 60 dk kontrolü KALSIN, açık TA da geçsin): `TP_NET_ALL, STOP_ON = True, False` — kâr al = net +5 $ (komisyon sonrası, fonlama hariç:
tp = (5/adet + giriş×1,0002)/0,9998, yukarı tick), zarar stopu emri HİÇ yok (±VOL60 ve −%6 taban kapalı; açık stop yeniden başlatmada iptal,
olay `estop_removed`), zarardakini yalnız 60 dk kontrolü kapatır, ilk 60 dk'da ~−%9'da tasfiye riski (sebep `tasfiye`). Büyüklük min(1.500, 12/VOL60)
aynen. closed_check.py `DEG23_MS`. Yedekler *.bak_20261107_1903. TA (Değ. 23 öncesi) 19:05:03 TR kullanıcı iPhone uygulamasından elle kapattı
(emir `ios_…`, net +3,74 $, bot `bilinmiyor` yazdı) — `ios_`/`android_`/`web_` önekli satış = kullanıcının elle kapatması.

**07.11 17:56:12 UTC = 20:56 TR DEĞİŞİKLİK 24 (şu anki kural; Değ. 23'ün "stop yok"u geçersiz):** kullanıcı "botu o haline (06.11 15:00 TR)
geri getir, yükselişi başlar başlamaz gör, zarar stopsuzluktan" + seçimler: giriş şartı yalnız RET_4 > 0 ve LC ≥ 2 (`ENTRY_RT_POSITIVE = False`);
Değ. 17 sakin ±%0,2 ve Değ. 18/22 hacim+defter akışı İPTAL, kodu+metni SİLİNDİ (işlem kayıtları kaldı; depth2 tablosu, feats'teki eski değerler,
*.bak yedekleri, raporlar duruyor — silinsin mi sorulacak); YÜKSELİŞ SİNYALİ `RALLY_*`: listedeki 30 coinin ≥ 20'si son 5 dk artıda (ham 1 dk
kapanış) VE önceki 11 karar (60 dk) sönük → 4 sa/LC aranmadan puanı en yüksekler BOŞ YUVA KADAR (engel etiketi yine geçerli), telefona 🚀;
her karar events kind `rally`; 1.500 $ SABİT (`SIZE_BY_VOL = False`, Pos.vol = 0), kâr al net +5 $, zarar stopu −5 $ (`STOP_ON = True`,
`STOP_USD = 5`, max(giriş − 5/adet, ×0,94), MARK, `zs`); 5 dk karar, 4 yuva, karar başına 1, 60 dk kontrolü aynen. Denetim: `verify.py rally [ts]`,
`verify.py features` (D24_FROM_MS=1794074172000; Değ. 17–23 şartı denetlenmez), `audit/decide_check.py` (sinyal dahil). closed_check.py
Değ. 24 için HENÜZ güncellenmedi (−5 $ stop, 1.500 sabit). Yedekler *.bak_20261107_2045. Stop seçiminden önce ölçüm (92 işlem, 1.500 $ sayılarak):
−5 → sonra +5 dönen 14, −8'e de inen 46 → −8 ile fark ≈ +2 $; sinyal tanımları son 31 saatte 2–10 kez, sonuç çıkarılamadı (kullanıcıya söylendi).
**07.11 ~21:10 TR DEĞİŞİKLİK 25** (kullanıcı seçimi "Bu coinleri alma"): Değ. 24 ilk işlemi CYBER, fiyat adımı 0,001 = %0,31 → −5 $ stop tek adım,
2 sn'de −10,27 $. `TICK_MAX_REL = 0.001`: scores.feats `TICK_REL` = demo tick / son 1 dk kapanış; büyük ya da ölçülemeyen → seçimde atlanır
"(fiyat adımı %x)". verify.py features TICK_REL'i denetler; decide_check D25_FROM_MS. Yedekler *.bak_20261107_2105. Ders: canlı bot çalışırken aynı
IP'den ağır deneme (dry/harness) çalıştırma → 18:09:53 UTC 429 oldu.
**08.11 05:43:10 TR DEĞİŞİKLİK 26** (kullanıcı: "önerinş uygula"; 07.11 gecesi 32 işlem 10 kazanç −66,66 $ incelemesinden): giriş şartı = PİYASA
son 30 dk artıda (`MKT_30` > 0 = listedeki coinlerin ham R30 ortalaması, `MKT_WIN_MS`) + LC ≥ 2. "Son 4 sa > 0" (RET_4) ve YÜKSELİŞ SİNYALİ
(RALLY_*) İPTAL + kodu/metni SİLİNDİ (sinyal gece hiç başlamadı: 5 dk sayaç yanıp söndü, "60 dk sönük" oluşmadı). Kanıt tek gece: piyasa
son 30 dk artıdayken girilen 15 işlem −9 $, eksideyken 17 işlem −58 $ (kullanıcıya "kanıt değil" denildi). Not: LC de 2 saate bakıyor
(yükselişin başında yine geç kalabilir). verify.py features (D26_FROM_MS=1794105790000; öncesi şart denetlenmez, `rally` komutu silindi),
decide_check (MKT_30'u yeniden toplar). Duranlar (sorulacak): events kind `rally`, feats'teki RET_4/R5/RALLY*/GATED, *.bak yedekleri.
Yedekler *.bak_20261108_0535. Değ. 26 test: yapay R30 eksi/NaN → giriş yok.
**08.11 07:16:36 TR (04:16:36 UTC) DEĞİŞİKLİK 27** (kullanıcı: "direkt bota ekle ve görelim demoda", seçim "Dördü de şart"): piyasa şartı = MKT_30 ≥ +%0,10
VE MKT_UP (R30 > 0 coin) ≥ 20 VE MKT_5 (ortalama yol son 5 dk) > 0 VE MKT_PEAK (son 30 dk tepesine uzaklık) ≥ −%0,10, + LC ≥ 2. Eşikler
Claude'un seçimi, veriye dayanmıyor (söylendi). MKT_TOP/MKT_PN yalnız kayıt. verify.py (D27_FROM_MS) yolu REST'ten kurar; decide_check
ayrıca events enter_error'u (METUSDT "Leverage 10 is not valid", 01:35 TR'den beri 7 kez) atlanmış sayar. Yedekler *.bak_20261108_0707. Test: son dakika sıçraması (+%0,3 tek dk) şartları GEÇER (açık, kullanıcıya söylendi).
Kullanıcıya önerim "3 gün değiştirme" idi; kullanıcı demoda denemeyi seçti. Gece (21:00–06:47 TR) 41 işlem −98,66 $ = piyasa −83 + seçim
+40 + demo farkı −22 + ücret −33; işlem boyunca piyasa artıda 15 işlem +7,78 $, eksi 26 işlem −106 $.
**08.11 07:36:30 TR (04:36:30 UTC) DEĞİŞİKLİK 28** (kullanıcı: "sıçrama şartını da ekle"): Değ. 27'nin 4 şartı + SIÇRAMA DEĞİL: MKT_JUMP = idx(t) − idx(t−2 dk)
≤ 0,5 × MKT_30 (`MKT_JUMP_MS, MKT_JUMP_SHARE`); eşik Claude'un seçimi. Sıçrama anında ayırt edilemez → kural bekler, sonraki kararda
sıçrama tuttu + yükseliş sürüyorsa girer. verify.py D28_FROM_MS, decide_check D28_FROM_MS. Yedekler *.bak_20261108_0725. Test t27/test28.py.
**08.11 07:47:09 TR (04:47:09 UTC) DEĞİŞİKLİK 29** (kullanıcı: 60 dk kontrolünde eksi ama yükseliyorsa satma, 3 kez daha bak): kâr < +%0,14
ama son 60 dk ≥ −%0,2 VE coin son 5 dk (R_5M) artıda → satma, 3 ek kontrol (65/70/75. dk): +%0,14 → sat (ek_kontrol_kâr), düşerse hemen
sat (ek_kontrol_düştü), 75'te hâlâ eksi → sat (ek_kontrol_süre). Kullanıcı seçimleri: son 5 dk artıda, +%0,14'te sat, hemen sat, en fazla
75 dk. bot.py `check_decide()` + `Pos.grace` (eski koda dönüşte state.json'dan silinmeli) + events `ek_kontrol`; denetim YENİ
audit/grace_check.py; testler t27/test29_unit.py (32 durum) ve test29_dry.py. Yedekler *.bak_20261108_0744.

**08.11 10:01:33 TR (07:01:33 UTC) DEĞİŞİKLİK 30** (kullanıcı KENDİSİ istedi: "bot hem long hem de short açma kararını verecek kabiliyete
getir … 60 dk'lık pencere içindeki sıçramaları da izleyelim"; seçimler "Girişte coin sıçraması" + "Açıkken ters sıçramada çık", "4 yer ortak"):
SHORT = long piyasa şartlarının aynası (son 30 dk ≤ −%0,10, ≥ 20 coin ekside, son 5 dk ekside, 30 dk dibinden ≤ %0,10 yukarıda, düşüş
sıçrama değil) + LC_DN ≥ 2; her kararda en çok bir yön (scores.side), short puanı scores.score_s (LC_DN, −SMOOTH_4, −TAKER_1, −IMB1_1,
−BIDSHARE_1, OI_1). Girişte coinin son 60 dk hareketinin yarısından fazlası tek 2 dk sıçramasından geldiyse girilmez (COIN_J_UP/DN);
açıkken her dakika son 2 dk işlemin tersine ≥ %0,20 → hemen kapat (ters_sıçrama, spike_checks tablosu). Short emirleri: SELL GTX en iyi
satış, kâr al BUY reduceOnly net +5 $, stop BUY STOP_MARKET closePosition −5 $. trades/checks.side. Denetim: verify.py features,
decide_check (yuva sayımı da düzeltildi), grace_check, pnl_check, YENİ audit/spike_check.py. Testler t30/test30_unit.py + test30_decide.py
hata 0; dry 06:57 UTC SHORT BCH, verify fark 0. Eşikler Claude'un seçimi. Yedekler *.bak_20261108_0648. Değ. 19 sepet iptali kararı
geçerli: SEPETİ yeniden önerme; short artık kullanıcı isteğiyle botta.
