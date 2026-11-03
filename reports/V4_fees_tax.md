# V4 — Binance maliyetleri ve Türkiye vergisi (backtest parametreleri)

2026-11-03. Kapsam: saatlik sinyal, TP/SL çıkışlı, saatlerden birkaç güne kadar tutulan bir momentum stratejisi; Binance
SPOT ve USDⓈ-M PERP (1×, 2×, 3×, 5×). Binance'in canlı değerleri bugün halka açık uç noktalardan çekildi
(`fapi/v1/exchangeInfo`, `fapi/v1/fundingInfo`, `fapi/v1/fundingRate`, `bapi/.../future/common/brackets`;
erişim 2026-11-03). Vergi kısmı hukuki görüş değildir; kaynaklar arasındaki çelişkiler aşağıda tek tek yazılı.

## Kısa sonuç

| Kalem | Değer | Güven |
| --- | --- | --- |
| Spot VIP 0 maker / taker | %0,100 / %0,100 (BNB ile %0,075 / %0,075) | yüksek |
| Futures VIP 0 maker / taker | %0,020 / %0,050 (BNB ile %0,018 / %0,045) | yüksek |
| Funding | BTC/ETH/büyük altlar 8 saatte bir (00/08/16 UTC); işlem gören USDT perp'lerin çoğu (417/522) 4 saatte bir | yüksek |
| En küçük kademede MMR | BTC, ETH %0,40 · SOL, XRP, BNB, ADA, LINK %0,50 · DOGE %0,65 · orta büyüklükteki altlar %1,0 | yüksek (bugünkü değer) |
| Likidasyon temizleme ücreti | BTC, ETH, XRP, BNB %1,25 · SOL, DOGE %1,5 · birçok alt %2–2,5 (notional üzerinden) | yüksek |
| TR işlem vergisi / stopaj | **Yürürlükte yok.** Teklif (%0,03 işlem vergisi + %10 stopaj) 27.03.2026'da geri çekildi | orta-yüksek |
| TR kazanç vergisi | Kriptoya özel hüküm yok; genel GVK'ya göre yıllık beyan (%15–40) riski var, nitelendirme tartışmalı | **belirsiz** |
| Binance global erişimi | Kullanıcıya yasak yok; yük platformlarda. Binance TR'de kaldıraç/türev yasak | orta |

---

## 1. Binance spot ücretleri (Regular / VIP 0)

- **Maker %0,100, taker %0,100.** Ücret BNB ile ödenirse **%25 indirim** uygulanır, iki taraf da **%0,075** olur.
  İndirim **hem maker hem taker** için ve her işlem bacağı (alış ve satış) için geçerlidir.
  Kaynak: [binance.com/en/fee/trading](https://www.binance.com/en/fee/trading) ("BNB 25% off", 0,100% → 0,07500%).
  Sayfada tarih yok, erişim 2026-11-03. Üçüncü taraf 2026 tabloları da aynı değerleri veriyor.
- Koşul: hesapta "BNB ile öde" açık olmalı ve spot cüzdanda ücreti karşılayacak kadar BNB bulunmalı. BNB fiyat riski
  ve BNB'yi yenileme ihtiyacı backtestte modellenmez; bu yüzden BNB'li ücret yalnızca duyarlılık senaryosunda kullanılmalı.
- USDC çiftleri ve kampanyalı sıfır ücretli çiftler farklı ücret tablosuna tabidir; USDT çiftleri için yukarıdaki değerler geçerli.

## 2. Binance USDⓈ-M futures ücretleri (VIP 0)

- **Maker %0,0200, taker %0,0500.** BNB ile ödenirse **%10 indirim**: maker %0,0180, taker %0,0450. BNB, USDⓈ-M futures
  cüzdanında bulunmalı. Bakiye yetmezse ücret USDT olarak ve indirimsiz kesilir.
  Kaynak: [Binance Futures Fee Structure FAQ](https://www.binance.com/en/support/faq/360033544231) (yayın 2019-09-09,
  güncelleme **2026-05-01**). Bu sayfa oranları "varsayımsal örnek" olarak veriyor ve canlı tabloya yönlendiriyor. Canlı
  tablo ([binance.com/en/fee/futureFee](https://www.binance.com/en/fee/futureFee)) JS ile yüklendiği için okunamadı.
  2026'da VIP 0 oranlarını değiştiren bir duyuru bulunamadı.
- Ücret = **notional × oran**, yani teminat üzerinden değil, pozisyon büyüklüğü üzerinden alınır. 5× kaldıraçta taker
  giriş+çıkış = 2 × %0,05 × 5 = **özsermayenin %0,5'i**.
- Diğer kalemler ([What Fees are Generated in Binance Futures Trading?](https://www.binance.com/en/support/faq/detail/98488a516eb84e3eb34605683dffd554),
  güncelleme 2026-01-05): (i) komisyon, (ii) funding (Binance komisyon almaz, taraflar arası transferdir),
  (iii) likidasyonda "insurance clearance fee". Ayrıca bir işlem başı ücret, faiz veya saklama ücreti yok.
  Spread ve kayma ayrı modellenmelidir.

## 3. Funding

Kaynak: [Introduction to Binance Futures Funding Rates](https://www.binance.com/en/support/faq/360033525031) (güncelleme
**2026-03-06**). Ayrıca [Funding Rate Settlement Frequency duyurusu](https://www.binance.com/en/support/announcement/3243c81a35bd4f0c86a37315c3dc96cc)
(2025-04-25, yürürlük 2025-05-02) ve [formül güncellemesi](https://www.binance.com/en-AE/support/announcement/detail/c00588a7e8504b3eb28d02a2da00530b) (2025-09-18).

- **Tutar = pozisyon notional'ı (mark price × miktar) × funding oranı.** Oran pozitifse **long öder, short alır**;
  negatifse tersi geçerli. Yalnızca funding anında açık pozisyon varsa ödenir. Zamanlama ±15 sn toleranslı; birkaç saniye
  önce açılan pozisyon da ödeyebilir.
- **Formül:** F = [P + clamp(I − P, −%0,05, +%0,05)] / (8/N). Burada P ortalama premium index, I faiz bileşeni
  (8 saatte **%0,01**), N funding aralığı (saat). 8/N bölücüsü 2025-09-18'den beri var. Premium −%0,04 ile +%0,06
  arasında kaldığı sürece F = %0,01 / 8 saat olur.
- **Aralık:** varsayılan 8 saat, **00:00, 08:00 ve 16:00 UTC**. Bugünkü `fundingInfo` verisine göre işlem gören 522 USDT
  perp'ün 104'ü 8 saatlik, 417'si 4 saatlik, 1'i 1 saatlik aralıkta. BTC, ETH, SOL, XRP, DOGE, BNB, ADA, LINK, AVAX, TRX,
  LTC ve SUI 8 saatlik.
- **Aralık değişiklikleri gerçekten oldu.** 2025-05-02'den beri bir settlement tavana veya tabana değerse kontrat bir
  sonraki saatten itibaren **1 saatlik** aralığa geçiyor (BTCUSDT dahil; istisnalar FLM, VOXEL, ALPACA). FAQ'a göre 1 saatlik
  aralık, mutlak değeri ≤%0,025 olan 16 ardışık settlement'tan sonra 4 saatliğe dönüyor. Bu otomatik geçişler tek tek
  duyurulmuyor. Örnek: SOLUSDT, 2022-11'de (FTX) 99 kez 2 saatlik aralıkla ödendi (`data.binance.vision` dosyasında
  `funding_interval_hours=2`). **Backtestte sabit 8 saat varsayılmamalı.** Dosyalardaki `calc_time` ve
  `funding_interval_hours` alanları olduğu gibi kullanılmalı (`calc_time` ms kayması içerebilir, örneğin …008; saate yuvarlanmalı).
- **Tavan ve taban:** BTC, ETH, SOL gibi listelenmiş semboller için ±0,75 × (maksimum kaldıraçtaki MMR). Bugünkü değerler
  BTC/ETH **±%0,30**, SOL/XRP/BNB/ADA/LINK/AVAX/LTC ±%0,375, DOGE/TRX ±%0,4875, SUI ±%0,75. Diğer kontratlarda ±%2.
- **Uzun dönem ortalama** (`fapi/v1/fundingRate`, 2026-11-03'e kadar; pozitif değer long'un ödediği anlamına gelir):

| Sembol | Dönem | Ortalama / olay | Yıllık (long öder) | Tam %0,01 olan olay payı | Negatif olay payı |
| --- | --- | --- | --- | --- | --- |
| BTCUSDT | 2019-09 – 2026-11 | 1,05 bp / 8 saat | %11,5 | %35 | %14 |
| ETHUSDT | 2019-11 – 2026-11 | 1,25 bp / 8 saat | %13,6 | %34 | %14 |
| SOLUSDT | 2020-09 – 2026-11 | 0,03 bp / olay | ~%0,3 | %34 | %29 |

  Yıllara göre büyük oynama var. BTC'de yıl içi toplam: 2021'de %30,6, 2022'de %4,2, 2024'te %12,0, 2025'te %5,1,
  2026 (10 ay) %2,7. ETH 2026'da %1,8. SOL 2022'de −%38 (short'lar ödedi). 2026-02..04 arasında BTC/ETH funding
  ortalaması negatif. "Long yılda ~%11 öder" varsayımı yalnızca 2020–2021 ve 2024 için geçerli; son iki yıl çok daha düşük.

## 4. Likidasyon ve teminat

Kaynaklar: [Liquidation Protocols FAQ](https://www.binance.com/en/support/faq/360033525271) (güncelleme 2026-01-04);
kademeler `bapi/futures/v1/friendly/future/common/brackets` (halka açık, erişim 2026-11-03); likidasyon ücreti
`fapi/v1/exchangeInfo` içindeki `liquidationFee` alanı (erişim 2026-11-03).

- **Tetik:** teminat + gerçekleşmiş K/Z + **mark price'a göre** gerçekleşmemiş K/Z < bakım teminatı (MM).
  MM = notional × MMR − cum (kademe sabiti).
- **En küçük kademe (bugünkü değerler):**

| Sembol | MMR | Kademe üst sınırı (notional) | Bu kademede maks. kaldıraç | Likidasyon ücreti |
| --- | --- | --- | --- | --- |
| BTCUSDT | %0,40 | 300.000 USDT | 150× | %1,25 |
| ETHUSDT | %0,40 | 300.000 | 150× | %1,25 |
| SOLUSDT | %0,50 | 50.000 | 100× | %1,50 |
| XRPUSDT | %0,50 | 40.000 | 100× | %1,25 |
| DOGEUSDT | %0,65 | 80.000 | 75× | %1,50 |
| BNB, ADA, LINK | %0,50 | 10.000 | 75× | %1,25 |
| AVAX | %0,50 | 25.000 | 75× | %1,50 |
| TRX, DOT / 1000PEPE / UNI | %0,65 / %0,65 / %0,60 | 10.000–20.000 | 75× | %1,25–1,5 |
| SUI, NEAR, AAVE, TON, HBAR, XLM | %1,00 | 10.000–50.000 | 75× | %1,5–2 |

  İşlem gören 522 USDT perp'te birinci kademe MMR'ın medyanı %1,5; küçük coinlerde %2,5–5'e çıkıyor. Kademeler zaman
  içinde değişiyor (BTC/ETH kademesinin son güncellemesi 2025-08-19, SOL'ünki 2025-06-23), yani tarihsel kademeler
  bugünkünden farklı olabilir.
  2. kademe örnekleri: BTC/ETH 300k–800k için %0,5; SOL 50k–400k için %0,65.
- **Likidasyon ücreti (insurance clearance fee):** notional × oran. Bugün dağılım şöyle: %1,25 (12 sembol), %1,5 (301),
  %2 (180), %2,5 (29). Ücret, pozisyona ayrılan kalan varlıklardan kesilir; iflas eden pozisyondan alınmaz. Likidasyon
  anında kalan teminat ≈ MM (%0,4–1) < ücret (%1,25+) olduğundan **pratikte isolated pozisyonun tüm teminatı kaybedilir**.
  Model: likidasyon = o pozisyonun isolated teminatı sıfırlanır.
- **Isolated ve cross:** isolated modda kayıp pozisyona ayrılan teminatla sınırlıdır ve her pozisyonun kendi likidasyon fiyatı
  vardır. Cross modda tüm futures bakiyesi ortak teminattır; likidasyon hesap seviyesinde olur ve tüm açık emirler iptal
  edilir. Backtest için **isolated** öneriliyor.
- **Yaklaşık likidasyon mesafesi** (isolated, one-way, ücret ve funding'in teminattan düşülmesi hariç):
  long LP ≈ EP·(1−1/L)/(1−MMR), short LP ≈ EP·(1+1/L)/(1+MMR).

| Kaldıraç | Long, MMR %0,4 | Long, MMR %1 | Short, MMR %0,4 | Short, MMR %1 |
| --- | --- | --- | --- | --- |
| 1× | likidasyon yok (fiyat ≈ 0) | yok | +%99,2 | +%98,0 |
| 2× | −%49,8 | −%49,5 | +%49,4 | +%48,5 |
| 3× | −%33,1 | −%32,7 | +%32,8 | +%32,0 |
| 5× | −%19,7 | −%19,2 | +%19,5 | +%18,8 |

  Likidasyon kontrolü için `data.binance.vision`'daki **markPriceKlines** kullanılmalı. Last-price fitilleri mark price'tan
  sert olabilir.

## 5. Türkiye vergileri (gerçek kişi, 2026)

### Şu an yürürlükte olan

- **Kriptoya özel vergi hükmü yok.** [7518 sayılı Kanun](https://www.alomaliye.com/2024/07/02/7518-sayili-spkda-degisiklik-kripto-varliklar/)
  (RG 02.07.2024, 32590) 6362 sayılı SPKn'ye kripto varlık hizmet sağlayıcısı (KVHS) lisans rejimini ekledi. Vergi getirmedi.
- **İşlem vergisi ve stopaj tasarısı yasalaşmadı.** 02.03.2026'da TBMM'ye sunulan torba teklif (Esas 2/3560;
  [TBMM haberi](https://www.tbmm.gov.tr/Haber/Detay?Id=38d60366-e785-48a8-b5f6-019cae7aa2c1)) şunları öngörüyordu:
  6802 sayılı Gider Vergileri Kanunu'na "kripto varlık işlem vergisi" (KVHS'lerin yaptığı veya aracılık ettiği satış ve transferlerde **onbinde 3 = %0,03**;
  Cumhurbaşkanına 0'a indirme veya 5 katına çıkarma yetkisi) ve 193 sayılı GVK'ya SPKn'ye tabi platformlarda kazançlar üzerinden
  **%10 tevkifat** (3 aylık, FIFO). Teklif Plan ve Bütçe Komisyonu'ndan geçti, ancak bu maddeler (1, 3, 4, 5) Genel
  Kurul'da **26–27.03.2026'da geri çekildi** ([Bloomberg HT, 2026-03-27](https://www.bloomberght.com/kripto-varliklara-vergi-teklifi-geri-cekildi-3773037)).
  Teklifin kalanı [7577 sayılı Kanun](https://www.alomaliye.com/2026/04/17/7577-sayili-bazi-kanunlarda-degisiklik-yapilmasina-dair-kanun/)
  olarak yayımlandı (RG 17.04.2026, 33227) ve metinde "kripto" geçmiyor. Sonraki torba kanun 7587'de (RG 01.07.2026) de
  ikincil bültenlere göre kripto hükmü yok.
  [Gökay Gül SMMM, 2026-07-09](https://gokaygul.com/tr/blog/kripto-varlik-vergilendirme-2026/): "yürürlükte değil".
  Legal 500 ([2026-10-08](https://www.legal500.com/intelligence/turkey/finance-and-banking/turkeys-crypto-asset-framework-in-2026-licensing-compliance-and-the-tax-question))
  rejimi "beklemede" sayıyor. Kasım 2026 itibarıyla **yeniden sunulmuş bir teklif bulunamadı.**
- **Çelişen kaynaklar:** bazı rehber siteleri "%0,03 işlem vergisi uygulanıyor" veya "binde 3" diye yazıyor. Birincisi geri
  çekilmeyle çelişiyor; ikincisi oranı 10 kat yanlış veriyor (doğrusu onbinde 3). Hiçbiri RG atfı vermiyor.
- **Genel GVK hükümleri yine de geçerli.** Kazancın niteliği tartışmalı:
  süreklilik veya organizasyon varsa **ticari kazanç** (GVK 37) sayılır ve yıllık beyana tabidir (GİB özelgesi 38810,
  09.08.2022, Gökay Gül'ün aktarımıyla). Arızi ise **arızi kazanç** (GVK 82; 2022 Ankara VDB özelgesi, Hürriyet aktarımı;
  2026 istisnası 350.000 TL) ya da **değer artışı** (GVK Mük. 80; kripto listede sayılmadığı için dayanağı tartışmalı) olabilir.
  Uygulanacak oran 2026 tarifesi (ücret dışı): %15 (190.000 TL'ye kadar), %20 (400.000), %27 (1.000.000), %35 (5.300.000),
  üstü %40 (GVK Genel Tebliği 332, RG 31.12.2025, 33124 5. mük.;
  [alomaliye](https://www.alomaliye.com/2025/12/31/2026-yili-vergi-dilimleri/),
  [KPMG 2026-01-02](https://kpmgvergi.com/yayinlar/mali-bultenler/vergi/2026-yili-gelir-vergisi-dilimleri-ile-dikkate-alinacak-bazi-had-ve-tutarlar-belirlendi/3351)).
  Saatlik sinyalle yılda çok sayıda işlem "süreklilik" yorumunu güçlendirir. Matrah **TL** bazındadır, dolayısıyla
  USDT/TRY artışı da kazanca girebilir.

### Sorulan üç durum

| Durum | Bugün (2026-11) | Geri çekilen teklif yasalaşsaydı |
| --- | --- | --- |
| (a) Spot kazancı | İşlem vergisi ve stopaj yok. Yıllık beyan riski var (ticari, arızi veya değer artışı; %15–40). Belirsiz | KVHS'de %0,03 işlem vergisi + %10 nihai stopaj. KVHS dışında yıllık beyan |
| (b) Türev / futures kazancı | Kripto türevine özgü hüküm veya özelge bulunamadı. GVK geçici 67 yalnızca yurt içi borsa veya aracı kurum üzerinden yapılan türevleri kapsar. Yurt dışı türev kazancı için de yıllık beyan riski var. Belirsiz | Teklif kriptoya özgüydü; KVHS'ler türev sunamadığı için yalnızca yıllık beyan |
| (c) Yurt dışı (Binance global) / TR lisanslı (Binance TR) | İkisinde de bugün stopaj ve işlem vergisi yok. Binance TR'de futures yok (bkz. 6). TR platformu komisyonları KDV'ye tabi (GİB özelgesi 38992, 26.09.2025, Gökay Gül aktarımı) | İşlem vergisi ve stopaj yalnızca TR lisanslı platformlarda. Binance global'de yıllık beyan |

**Modelleme önerisi:** temel senaryoda işlem başına TR vergisi **0** ve kazanç vergisi **0** (vergi öncesi sonuç) kullanılır.
Vergi sonrası sonuç için iki ayrı duyarlılık: (1) spot, TR platformunda ise taraf başına %0,03 işlem vergisi (temkinli
okuma: USDT de kripto varlık olduğu için USDT→coin alışı da "satış" sayılabilir; teklifin metni "satış ve transfer"
diyor). (2) Yıllık net pozitif TL kazancına %15 / %27 / %40 düz oran, zarar yıl içinde mahsup edilir. Bu, hukuki görüş
değildir; gerçek beyan için mali müşavirle görüşülmeli.

## 6. Erişim ve yasal durum (kısa)

- **Kullanıcı için suç tanımı yok.** 7518'in yükümlülükleri platformlara ait. SPK
  [02.07.2024 duyurusu](https://spk.gov.tr/duyurular/basin-duyurulari/2024/kripto-varlik-hizmet-saglayicilara-iliskin-duyuru_02072024):
  yurt dışı platformlar Türkiye'ye yönelik faaliyeti (Türkçe site, Türkiye'de iş yeri, doğrudan tanıtım) **en geç
  02.10.2024'te sonlandırmak zorunda**. Aksi hâlde SPKn 99/A ve 109/A uygulanır. Binance 2024-07-02'de "Türk
  kullanıcılarına hizmete devam" dedi; Türkçe dil seçeneğini 3 ay içinde kaldıracağını ve doğrudan pazarlamayı
  durdurduğunu açıkladı
  ([Ekonomim, 2024-07-02](https://www.ekonomim.com/finans/kripto-para/binance-turkiye-faaliyetlerini-gecici-durdurma-karari-aldi-haberi-752222)).
- SPK birçok yurt dışı borsaya erişim engeli getirdi (haberlere göre 2024-12 ve 2025-06'da MEXC, Bitmart, CoinEx ve
  benzerleri). **binance.com için engel kararı bulunamadı.** Binance'in yasaklı ülkeler listesi JS ile yüklendiği için
  doğrudan okunamadı; Türkiye'nin listede olduğuna dair bir kaynak da yok. Gelecekte erişim engeli ihtimali bir risk.
- **Binance TR** ("Binance Turkey Kripto Varlık Alım Satım Platformu AŞ", eski adı BN Teknoloji AŞ) SPK'nın
  [geçici faaliyette bulunanlar listesinde](https://spk.gov.tr/kurumlar/kripto-varlik-hizmet-saglayicilar/faaliyette-bulunanlar-listesi)
  4 numarada. SPK'ya göre bu liste yetkilendirme anlamına gelmiyor; sayfadaki en yeni dipnot 23.09.2026 tarihli. SPK
  lisans sürelerini 27.03.2026'da uzattı ([Bloomberg HT](https://www.bloomberght.com/spk-dan-kripto-karari-3772994)).
- **TR platformlarında kaldıraç ve türev yasak:** SPK Tebliğ III-35/B.2 md. 14/1 (RG 13.03.2025, 32840;
  [metin](https://www.alomaliye.com/2025/03/13/kripto-varlik-hizmet-saglayicilarin-calisma-usul-ve-esaslari-ile-sermaye-yeterliligi-iii-35-b-2/)):
  listelenmiş kripto varlıklar kaldıraçlı alınıp satılamaz, türev, kredili alım, açığa satış ve ödünç işlemlerine konu
  edilemez. Yani 2×–5× ve short senaryoları ancak yurt dışı platformda (Binance global USDⓈ-M) mümkün. Binance TR yalnızca spot.

---

```yaml
model_params:
  as_of: "2026-11-03"
  # --- Spot (VIP 0, USDT çiftleri) ---
  spot_taker: 0.0010
  spot_maker: 0.0010
  spot_bnb_discount: 0.25          # iki tarafa da uygulanır -> 0.00075
  # --- USDⓈ-M perpetual (VIP 0) ---
  fut_taker: 0.0005
  fut_maker: 0.0002
  fut_bnb_discount: 0.10           # -> taker 0.00045, maker 0.00018
  fee_base: notional               # futures ücreti notional × oran (teminat değil)
  # --- Funding ---
  funding_source: data.binance.vision fundingRate (calc_time, funding_interval_hours, last_funding_rate)
  funding_interval_h: 8            # BTC/ETH/SOL/XRP/DOGE/BNB/ADA/LINK; dosyadaki funding_interval_hours esas alınır (4h/2h/1h oluyor)
  funding_times_utc_8h: ["00:00", "08:00", "16:00"]
  funding_interest_per_8h: 0.0001
  funding_clamp: 0.0005
  funding_sign: "pozitif oran: long öder, short alır; tutar = mark notional × oran; yalnızca funding anında açık pozisyona"
  funding_cap_btc_eth: 0.0030      # bugünkü değer; SOL/XRP 0.00375, diğerlerinin çoğu 0.02
  funding_longrun_btc_per_8h: 0.000105   # 2019-09..2026-11 ortalama (yıllık ~%11,5); 2025: 0.000047, 2026 YTD: 0.000029
  funding_longrun_eth_per_8h: 0.000125
  # --- Teminat / likidasyon (en küçük kademe, bugünkü) ---
  margin_mode: isolated
  mmr_btc: 0.004                   # notional <= 300k USDT
  mmr_eth: 0.004                   # notional <= 300k USDT
  mmr_alt: 0.010                   # temkinli tek değer: orta büyüklükteki altlar; büyük altlar için aşağıdaki tablo
  mmr_by_symbol: {SOLUSDT: 0.005, XRPUSDT: 0.005, BNBUSDT: 0.005, ADAUSDT: 0.005, LINKUSDT: 0.005, AVAXUSDT: 0.005, LTCUSDT: 0.005, DOGEUSDT: 0.0065, TRXUSDT: 0.0065, DOTUSDT: 0.0065, "1000PEPEUSDT": 0.0065, UNIUSDT: 0.006, SUIUSDT: 0.010, NEARUSDT: 0.010}
  liquidation_fee: 0.0125          # BTC/ETH/XRP/BNB/ADA/LINK; SOL/DOGE/AVAX/SUI 0.015; birçok alt 0.02-0.025
  liquidation_loss_model: full_isolated_margin   # likidasyonda pozisyon teminatının tamamı kaybedilir
  liquidation_price_source: markPriceKlines
  # --- Türkiye vergileri (temel: yürürlükteki duruma göre) ---
  tr_tax_per_side_spot: 0.0
  tr_tax_per_side_futures: 0.0
  tr_gain_tax_rate: 0.0            # temel senaryo vergi öncesi; vergi sonrası için sensitivity
  sensitivity:
    fees_with_bnb: {spot_taker: 0.00075, spot_maker: 0.00075, fut_taker: 0.00045, fut_maker: 0.00018}
    tp_exit_as_maker: true         # TP limit emri maker, giriş ve SL taker
    fees_x2_stress: {spot_taker: 0.0020, fut_taker: 0.0010}
    funding_flat_long_pays_per_8h: 0.0001   # gerçek dosya yerine sabit %0,01/8 saat stres testi
    mmr_alt_high: 0.015            # birinci kademe medyanı (522 USDT perp); küçük coinler 0.025-0.05
    liquidation_fee_alt: 0.02
    tr_tx_tax_per_side_tr_platform: 0.0003  # geri çekilen teklif (onbinde 3); yalnızca TR lisanslı spot; yasalaşmadı
    tr_tx_tax_per_side_tr_platform_max: 0.0015  # teklifteki 5 kat yetki
    tr_withholding_gain_tr_platform: 0.10   # geri çekilen teklif; yalnızca TR lisanslı platform
    tr_gain_tax_rate_annual: [0.15, 0.27, 0.40]  # yıllık net pozitif TL kazancına düz oran (2026 GVK 103 dilimleri)
    slippage_per_side_assumption: {btc_eth: 0.0002, large_alt: 0.0005}  # kaynak yok, varsayım
```
