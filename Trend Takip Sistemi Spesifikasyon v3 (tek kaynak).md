# Trend Takip Sistemi: Spesifikasyon v3 (tek kaynak)

Nov 2, 2026 · @Burakcan Kuyrukcu

## Özet

Bu belge projenin **tek geçerli spesifikasyonudur**. [v2 belgesinin](https://claude.ai/artifact/E6HTofxv6gSNW3AGGW53dF) yerini alır. v2, dört bağımsız incelemeden (hesap denetimi, tutarlılık denetimi, kaynak doğrulama, kırmızı takım) geçirildi ve bulgular burada tek, çelişkisiz bir metin olarak birleştirildi. Her parametre bir kez tanımlanır; Claude Code bu belgeyi `SPEC.md` olarak kullanır.

**v2'ye göre en önemli değişiklikler**

1. **Birincil soru değişti.** Sistem artık "kâr ediyor mu" diye değil, "maliyetler sonrası basit bir BTC 200 günlük ortalama kuralını yeniyor mu" diye test edilir. Yenemiyorsa varsayılan karar basit kuraldır.
2. **Pozisyon büyüklüğü algoritması düzeltildi.** v2 formülü sinyal seviyesini yok ediyor, az coinde oynaklık hedefini tutturamıyor ve toplam maruziyeti %100'ün üstüne çıkarabiliyordu.
3. **Yeniden dengeleme kuralı düzeltildi.** v2'deki bant kuralı pozisyonları hiçbir zaman tamamen kapatmıyordu; simülasyonda portföyün ortalama %6–10'u hedefi sıfır olan coinlerde kalıyordu.
4. **Maliyet birinci derece bir sorun.** Simülasyon, EMA sinyallerinin yılda %4–14 maliyet üretebildiğini gösterdi. Giriş/çıkış tamponu artık temel ayarın parçası.
5. **Test dönemi dürüstçe adlandırıldı.** 2024–2026 tasarımı etkilediği için gerçek bir test değil, "doğrulama" dönemi. Tek gerçek test, kod dondurulduktan sonraki ileriye dönük 12 ay.
6. **Evren sıkılaştırıldı.** Borsa tokenleri (BNB, FTT) çıkarıldı, minimum yaş 365 güne çıktı, likiditeye göre tavanlar eklendi.
7. **Olgu hataları düzeltildi:** vergi önerisi "on binde 3" (%0,03), Sharpe standart hatası 0,59 (0,73 değil), kaldıraçlı token tarihleri, Binance güvenlik ihlalinin güncel durumu.

**Kârlılık turu (2 Kasım 2026) ile eklenen değişiklikler**

Dört ajan sistemi bu kez net getiriyi artırmak için inceledi: sinyal, ek getiri kaynakları, portföy kurgusu, maliyet ve vergi. Mekanik olan ve sadece sentetik kanıta dayanan değişiklikler, gerçek veri henüz görülmediği için temel ayara alındı. Strateji tercihi içerenler ön kayıtlı varyant oldu.

1. **Haftalık giriş, günlük çıkış** temel ayara alındı. Simülasyonlarda yıllık maliyeti yaklaşık 1 puan düşürdü ve düşüşleri azalttı.
2. **Evren 50'den 20 coine indirildi.** Altcoinler birbirine o kadar bağlı ki 10 coinden sonra eklenen her coin çeşitlendirmeye neredeyse hiç katkı yapmıyor ama maliyeti artırıyor. Küçük sermayede emir filtreleri de bunu gerektiriyor.
3. **Nakit getirisi dürüstleştirildi.** Borsada bekleyen USDT getiri sağlamadığı için backtestte temel varsayım %0. Önceki varsayım (hazine bonosu faizi) sonuçları yılda yaklaşık 1,7–2,5 puan iyi gösteriyordu.
4. **Türk yatırımcı için çıta eklendi.** 2026'da stopaj sonrası TL mevduatı dolar cinsinden kabaca +%13 getirdi (kur riskiyle). Sonuçlar bu çıtayla da raporlanır.
5. **Borsadaki bakiye kuralı değişti.** "Başlangıcın %120'si üstü çekilir" yerine "toplam strateji varlığının %60–70'i borsada" kuralı. Simülasyonda borsa batma riski varken hem büyümede hem iflas riskinde daha iyi sonuç verdi.
6. **Yeni ve kaldırılan varyantlar.** Bitcoin'e göre güç filtresi (T9) ve çekirdek–uydu karışımı (T10) eklendi. Uydu payı için önceden belirlenmiş bir kural kondu. Fonlama arbitrajı, staking, short tarafı, kripto dışı dilimler, düşüş kontrolü katmanları ve daha yüksek oynaklık hedefi gerekçeli olarak reddedildi (Açık sorular bölümünde).

**Nasıl okunur:** Bölümler uygulama sırasındadır. "Ön kayıt" bölümü, herhangi bir sonuç görülmeden önce dondurulması gereken kararları içerir. Görev listesi en sondadır.

## Kapsam, ilkeler ve aşamalar

Sistem: Binance spot, sadece long, günlük mumla karar veren, kural tabanlı bir trend takip sistemi ve bunun araştırma, test ve işletme altyapısı.

**Aşama 1 — Araştırma (G0–G12):** veri, kalite denetimi, evren, strateji, backtest, değerlendirme, kilit. Sadece kamuya açık veri kullanılır, API anahtarı gerekmez.

**Aşama 2 — Gölge mod ve canlı (G13–G14):** sadece Aşama 1 geç/kal kriterlerini geçerse başlar. Canlıya geçiş ayrıca iki koşula bağlıdır: Binance'in güvenlik ihlali sonrası durumunun netleşmesi ve bir avukat ile mali müşavirden yazılı görüş alınması.

**Kapsam dışı (v1):** short, kaldıraç, vadeli işlem, orderbook/on-chain/makro veri, parametre optimizasyonu, makine öğrenmesi, gün içi stop.

**Temel ilkeler**

1. **Geleceği görme yok.** t günündeki karar yalnızca t günü 00:00 UTC kapanışına kadar bilinen veriyi kullanır. Bu kural fiyatlar kadar meta veri için de geçerlidir (evren listeleri, kalite işaretleri, sembol tabloları).
2. **Önce kayıt, sonra sonuç.** Hipotez, parametreler, varyantlar ve geç/kal kriterleri sonuçlar görülmeden yazılır ve dondurulur. Sonradan yapılan her değişiklik bir deneme olarak sayılır.
3. **Tek kural, tüm coinler.** Coin bazında ayar yapılmaz.
4. **Hayatta kalanlar yanılgısı yok.** Delist edilen ve batan coinler veride kalır; gerçekten yaşanmış çöküşler silinmez.
5. **Her şey tekrar üretilebilir.** Aynı girdi ve aynı kod aynı sonucu verir; ortam sabitlenir, veri özetlenir (hash).
6. **Basit olan varsayılan.** Karmaşıklık ancak basit kıyası istatistiksel olarak yenerse kabul edilir.

**Güncel durum: Binance güvenlik ihlali (2 Kasım 2026 itibarıyla)**

- 29 Ekim 2026'da Binance'ten yaklaşık [6,3 milyar dolarlık varlık çalındı](https://kuwaittimes.com/article/52684/business/crypto-exchange-binance-confirms-63-billion-hack-freezes-half/); yaklaşık 3 milyar doları donduruldu. İlk bulgulara göre bir DevOps mühendisinin dizüstü bilgisayarı üzerinden bir servis konteynerine erişilmiş.
- Binance önce yatırma ve çekmeleri durdurdu; 30 Ekim'de yatırmalar normale döndü. Çekimler [1 Kasım 2026'dan itibaren aşamalı açılıyor](https://www.coindesk.com/markets/2026/11/01/binance-opens-crypto-withdrawals-in-phases-starting-with-bitcoin-following-usd6-3-billion-hack) (ilk aşama BTC, ETH, USDT, USDC, BNB, XRP). Binance etkilenen tutarın büyük kısmını kendi fonlarıyla karşıladığını açıkladı.
- 30 Ekim'de [Binance TR kripto çekimlerini durdurdu](https://paratic.com/binance-trde-kripto-para-cekimleri-durduruldu-kullanici-varliklari-guvende-mi/); alım satım ve TL işlemleri sürüyor. 2 Kasım itibarıyla yeniden açılış haberi bulunamadı.
- **Etkisi:** Aşama 1 etkilenmez. Aşama 2 bu durum netleşene kadar başlamaz.

## Ön kayıt

Bu bölümdeki her karar, geliştirme döneminin hiçbir sonucu görülmeden `PREREGISTRATION.md` dosyasına yazılır, git'e işlenir, işaretlenir (imzalı tag) ve özeti (hash) zaman damgasıyla üçüncü bir yere (örneğin kendinize e-posta) gönderilir. Bu G9'da yapılır ve G10'dan önce tamamlanmalıdır.

**Birincil hipotez (tek)**

> Kilitli alt-coin trend sistemi (temel ayar), geliştirme + doğrulama döneminin tamamında (2019-07 – kilit tarihi), maliyetler sonrası risksiz faiz üzerindeki Sharpe oranında **BTC 200 günlük ortalama temel kıyasını** eşleştirilmiş blok bootstrap ile %95 güvenle yener.

- **Temel kıyas (BTC-200):** BTC günlük kapanışı 200 günlük basit ortalamanın üstündeyse %100 BTC, altındaysa %100 nakit. Aynı dolum, aynı maliyet ve nakitte aynı faiz varsayımı. 7/24 piyasada histerezis yok.
- **Hipotez reddedilirse:** varsayılan karar BTC-200 kuralını (veya hiç işlem yapmamayı) seçmektir. Alt-coin sistemi canlıya ancak küçük ve tavanlı bir ek dilim olarak, ileriye dönük kanıt birikene kadar çıkabilir.
- **Risksiz faiz ve nakit getirisi:** Sharpe her zaman ABD 3 aylık hazine bonosu faizinin üzerindeki getiriyle hesaplanır (yıllıklandırma √365), çünkü dolar bazlı yatırımcının alternatifi budur. Ama nakit kısma **temel varsayımda %0 getiri** işletilir, çünkü borsada bekleyen USDT getiri sağlamaz. Birincil hipotez bu temel varsayımla geçilmelidir. Duyarlılık: max(0, hazine bonosu − 1,5 puan) ve tam hazine bonosu (iyimser üst sınır). Her strateji için zaman ağırlıklı nakit payı ve nakit kaybı (nakit payı × hazine bonosu) raporlanır.

**Dönemler**

| Dönem | Aralık | Kullanım |
| --- | --- | --- |
| Isınma | 2017-08 – 2019-06 | Sadece gösterge geçmişi; sonuç raporlanmaz |
| Geliştirme | 2019-07 – 2023-12 | Hata ayıklama, sağlamlık, PBO, sıfır hipotezleri |
| Doğrulama | 2024-01 – kilit tarihi | Kilitten sonra bir kez çalıştırılır. Tasarımı etkileyen olayları (10 Ekim 2025, 2026 ayı piyasası) içerdiği için **gerçek bir test değildir** |
| İleriye dönük test | Kod dondurulduktan sonra en az 12 ay | Tek gerçek test. Sistem ve BTC-200 gölge modda yan yana çalışır |

Ayrıca tüm sonuçlar iki rejim için ayrı raporlanır: 2019-07 – 2021-11 ve 2022-01 sonrası. Alt-coin trend performansının büyük kısmı 2020–2021'den geliyorsa bu görünür olmalı.

**Temel ayar ve önceden kaydedilen varyantlar**

| Kod | Varyant | Rol |
| --- | --- | --- |
| T0 | Temel ayar: tamponlu sinyal (h = 0,5), haftalık giriş + günlük çıkış, 20 coinlik evren, rejim filtresi yok, VWAP 00–02 dolum, nakitte %0 getiri | Birincil |
| T1 | T0 + BTC rejim filtresi (0,97/1,03 × SMA200 histerezisli) | İkincil |
| T3 | T0, dolum t+1 açılışında (iyimser) | Duyarlılık |
| T4 | T0, dolum VWAP 06–07 ve VWAP 14–15 UTC | İşlem saati seçimi |
| T5 | T0, delist cezası %20 ve %50 | Stres |
| T6 | T0, maliyetler ×2; ayrıca borsadaki varlığın tek seferde %20 ve %50 kaybı | Stres |
| T7 | T0, sadece USDT hacmiyle kurulan evren | Sağlamlık |
| T8 | T0, günlük mum 04:00/08:00/12:00/16:00/20:00 UTC'de kapanıyormuş gibi; ayrıca haftalık giriş gününün diğer 6 güne kaydırılması (raporlanır, seçilmez) | Zamanlama şansı |
| T9 | T0 + Bitcoin'e göre güç filtresi (strateji bölümü) | İkincil |
| T10 | Çekirdek–uydu karışımları: %80 BTC-200 + %20 T0 ve %50 + %50; aylık yeniden dengelenir | Tanı (uydu payı kuralı için) |

Tamponsuz sinyal (eski T2) artık parametre ızgarasının bir komşusu (h = 0) olarak çalışır.

**Deneme sayısı (deflated Sharpe için N)**

N = `experiments.md`'deki tüm denemeler + parametre ızgarasının boyutu + varyantlar. Bu konuşmada trend takibinin araştırmalarla seçilmesi, BTC rejim filtresi, LST/USDe dışlaması gibi geçmişe bakılarak yapılmış seçimler kayıtta görünmediği için N için **alt sınır 100** alınır.

**Değişiklik kuralı:** Ön kayıttan sonra yapılan her değişiklik `experiments.md`'ye tarih, gerekçe ve sonuçla yazılır ve N'ye eklenir. Doğrulama dönemi bir kez çalıştırıldıktan sonra değişiklik yapılırsa, o dönem artık doğrulama sayılmaz.

**Uydu payı kuralı (birincil hipotez reddedilirse uygulanır)**

Alt-coin sistemi portföye ancak şu koşul sağlanırsa **%20** pay ile girer, aksi halde payı **%0**'dır:

```latex
0{,}5 \times SR_{T0}^{net} > \rho \times SR_{BTC200}^{net}
```

SR'ler tam dönem net Sharpe oranları, ρ iki stratejinin ölçülen günlük getiri korelasyonudur. 0,5 çarpanı, backtest Sharpe'larının canlıda tipik olarak büyük ölçüde düşmesine karşı bir indirimdir. Takdire dayalı artırım yapılmaz. BTC-200 çekirdeği %100 yatırım düzeyinde tutulur.

**Beklenti aralığı (hedef değil, referans)**

Portföy oynaklık hedefi %35 olsa da S kademeleri ve tavanlar nedeniyle gerçekleşen oynaklığın yaklaşık %20–30, ortalama toplam maruziyetin yaklaşık %30–50 olması beklenir. Beklenen yıllık fazla getiri kabaca net Sharpe × gerçekleşen oynaklıktır:

| Net Sharpe | Beklenen yıllık fazla getiri | Tek bir yılın tipik aralığı |
| --- | --- | --- |
| 0,3 | yaklaşık %6–9 | yaklaşık −%20 ile +%35 |
| 0,6 | yaklaşık %12–18 | yaklaşık −%15 ile +%45 |
| 1,0 | yaklaşık %20–30 | yaklaşık −%5 ile +%55 |

Yayımlanan maliyet öncesi sonuçların ve canlıda tipik Sharpe düşüşünün ışığında gerçekçi net Sharpe aralığı 0,3–0,8 kabul edilir. Canlı sonuçlar bu aralığın dışına çıkarsa bu bir uyarı işaretidir, parametre değiştirme gerekçesi değildir.

## Veri katmanı

Ana kaynak Binance'in ücretsiz arşivi [data.binance.vision](https://github.com/binance/binance-public-data). REST API sadece günlük güncelleme ve çapraz kontrol için kullanılır.

**İndirilecek veriler (hepsi 2017-08'den itibaren)**

| Veri | Aralık | Kullanım |
| --- | --- | --- |
| Tüm USDT spot çiftleri | 1d ve 1h | Fiyat, sinyal, oynaklık, dolum (VWAP), likidite |
| Tüm BUSD, FDUSD, USDC, TUSD spot çiftleri | 1d | Sadece likidite ölçüsü |
| Stablecoin/USDT çiftleri (USDCUSDT, BUSDUSDT, FDUSDUSDT, TUSDUSDT) | 1d | USDT dışı hacmi USDT'ye çevirme; USDT/USD vekili |

**URL kalıpları**

```
Aylık:   https://data.binance.vision/data/spot/monthly/klines/{SYM}/{INT}/{SYM}-{INT}-{YYYY}-{MM}.zip
Günlük:  https://data.binance.vision/data/spot/daily/klines/{SYM}/{INT}/{SYM}-{INT}-{YYYY}-{MM}-{DD}.zip
Checksum: aynı dosya adı + ".CHECKSUM" (SHA-256)
```

- Aylık dosyalar ayın ilk pazartesi günü, günlük dosyalar ertesi gün yayımlanır. Bu yüzden: tamamlanmış ve aylık dosyası yayımlanmış aylar için aylık dosya, diğer tüm günler için günlük dosyalar.
- Her zip CHECKSUM ile doğrulanır; tutmazsa yeniden indirilir, yine tutmazsa raporlanır. İndirme tarihi ve checksum'lar bir defterde tutulur. Arşiv dosyaları sonradan düzeltilebildiği için (ör. 2022-08-08 düzeltmesi) ayda bir checksum'lar tekrar kontrol edilir.
- Eş zamanlı en fazla 4–8 indirme; hata durumunda artan bekleme ile yeniden deneme. Tekrar çalıştırıldığında sadece eksik dosyalar iner.
- **Tahmini boyut ve süre (ölçülmedi):** 1 saatlik veri dahil 125–235 bin istek, 4 paralel indirmeyle 1,5–6,5 saat; sıkıştırılmış 0,7–1,2 GB, açılmış CSV 2–4 GB. G1 gerçek değerleri ölçer.

**Kolonlar (başlıksız CSV, 12 kolon)**

`open_time, open, high, low, close, volume, close_time, quote_volume, number_of_trades, taker_buy_base, taker_buy_quote, ignore`

**Zaman damgası:** Spot arşivinde 1 Ocak 2025'ten itibaren zaman damgaları **mikrosaniye**, öncesi milisaniye. Kural: değer > 10^14 ise 1000'e böl. REST API varsayılan olarak milisaniye döndürür. Günlük mumlar UTC 00:00'da açılır; REST'in isteğe bağlı `timeZone` parametresi **asla gönderilmez**. Her iki durum için birim testi zorunlu.

**Sembol keşfi**

- Arşivin web sayfası dosya listesi vermez. Liste S3 üzerinden alınır: `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/spot/monthly/klines/`. Bu uç nokta Binance tarafından belgelenmemiştir ama açık kaynak araçlarda kullanılır. Yanıtlar sayfalıdır: `IsTruncated` ve `NextMarker` takip edilir.
- G1 ilk iş olarak delist edilmiş sembollerin arşivde olduğunu doğrular: FTTUSDT, MATICUSDT, RNDRUSDT, eski LUNAUSDT, BUSD çiftleri. **Bu henüz doğrudan test edilmedi ve projenin en kritik varsayımıdır.**
- `GET /api/v3/exchangeInfo` sadece bugünkü sembolleri verir; delist tespiti için yardımcıdır, sembol keşfi için yeterli değildir.

**REST API**

- `GET /api/v3/klines`: istek başına en fazla 1.000 mum (ağırlık 2). BTC'nin tam günlük geçmişi 4 istek.
- Sadece piyasa verisi için [`https://data-api.binance.vision`](https://developers.binance.com/docs/binance-spot-api-docs/faqs/market_data_only) kullanılır.
- Limit: IP başına dakikada 6.000 ağırlık; güncel değer `exchangeInfo.rateLimits`'ten okunur. `X-MBX-USED-WEIGHT-1M` başlığı izlenir, %80'de beklenir. 429'da `Retry-After`'a uyulur; tekrarlanan ihlal IP yasağına (418) yol açar.
- Delist edilen bir çift exchangeInfo'dan [kaldırılınca API'den veri alınamaz](https://dev.binance.vision/t/trade-history-of-delisted-pairs/8973); G1 bunu klines için test eder.

## Veri kalitesi ve meta tablolar

Kalite işaretleri **tarihe bağlıdır**: her işaret `quality_flags.parquet` içinde (sembol, kontrol, dönem, `known_from`) olarak tutulur. T tarihindeki karar sadece `known_from ≤ T−1` olan işaretleri kullanır. 2023'te bulunan bir sorun bir coini 2020 evreninden çıkarmaz. Gerçekten yaşanmış fiyat hareketleri asla silinmez; elle düzeltme sadece ikinci bir kaynak değerin yanlış olduğunu gösteriyorsa yapılır.

**Kontroller**

| Kontrol | Kural | Sonuç |
| --- | --- | --- |
| Tekrarlanan kayıt | Aynı open\_time iki kez | Hata, düzelt |
| OHLC tutarlılığı | high ≥ max(open, close), low ≤ min(open, close), fiyat > 0 | Hata |
| Zaman damgası | ms/µs dönüşümü, UTC 00:00 hizası | Hata |
| Eksik gün | İlk ve son mum arasında atlanan tarih | Boşluk kuralı uygulanır (backtest bölümü) |
| Sembol değişmeden bölünme | Boşluk öncesi/sonrası fiyat oranı için abs(log10(oran) − yuvarlak) < 0,02 | Eşleştirme tablosu adayı |
| Sıfır hacim | volume = 0 veya number\_of\_trades = 0, art arda 3+ gün | O dönem dışlanır |
| Aşırı kapanış sıçraması | Tek günlük mutlak log getiri > %50 | İşaret, ikinci kaynakla kontrol |
| Aşırı iğne | low < 0,3 × close veya high > 3 × close | İşaret; iğne fiyatı hiçbir hesapta kullanılmaz |
| Yarım gün | Bir çiftin ilk ve son mumu (açılış ve delist genelde gün ortasında) | İşaret; tam gün sayılmaz |

Son kontrol için bilinen örnekler: 10 Ekim 2025'te Binance'te [wBETH yaklaşık 430 dolara, BNSOL 34,90 dolara, USDe 0,65 dolara](https://www.coindesk.com/markets/2025/10/12/binance-to-compensate-users-affected-by-crash-in-wbeth-bnsol-and-ethena-s-usde) indi. Yeni çiftlerin açılış saati değişkendir (ör. EGLD 03:00, LUNA 06:00, POL 10:00 UTC); gerçek değer veriden okunur.

**Sembol eşleştirme tablosu (`meta/symbol_map.csv`)**

Kolonlar: eski sembol, yeni sembol, tür, oran, eski çift son işlem zamanı, yeni çift ilk işlem zamanı, kaynak. **Oran = 1 eski token karşılığı yeni token sayısı.** Birleştirmede eski fiyat orana bölünür, eski taban hacim oranla çarpılır, quote hacim değişmez.

| Tür | Anlam | Pozisyon kuralı |
| --- | --- | --- |
| RENAME | Aynı varlık, yeni sembol, 1:1 | Seriler birleştirilir, boşlukta pozisyon tutulur |
| REDENOM | Aynı varlık, oran ≠ 1 (sembol değişebilir veya değişmeyebilir) | Oranla birleştirilir, pozisyon tutulur |
| ASSET\_CHANGE | Aynı sembol başka bir varlığa verildi | Seri bölünür; eski varlık delist kuralıyla kapanır |
| MERGE\_INTO\_EXISTING | Varlık zaten var olan başka bir coine katıldı | Delist kuralıyla kapanır (kötümser, önceden belirlenmiş) |
| DELIST | Sadece kaldırma | Delist kuralı |

**Kaynaklarla doğrulanmış satırlar (binance.com; Binance.US tarihleri farklıdır)**

| Eski → Yeni | Tür | Oran | Eski son işlem (UTC) | Yeni ilk işlem (UTC) |
| --- | --- | --- | --- | --- |
| ERD → EGLD | REDENOM | 0,001 | — | 2020-09-03 03:00 |
| BTT → BTTC | REDENOM | 1000 | Ocak 2022 (tarih G1'de arşivden) | Ocak 2022 |
| LUNAUSDT (eski) | DELIST (USDT serisi) | — | 2022-05-13 00:40 | — |
| LUNAUSDT (yeni) | ASSET\_CHANGE | Yeni varlık | — | 2022-05-31 06:00 |
| BNXUSDT bölünmesi | REDENOM (aynı sembol) | 100 | 2023-02-16 | 2023-02-22 (arşiv boşluğu; nedeni forumda belirtilmiyor) |
| OCEAN → FET | MERGE\_INTO\_EXISTING | 0,433226 | 2024-07-01 03:00 | — |
| AGIX → FET | MERGE\_INTO\_EXISTING | 0,433350 | 2024-07-01 03:00 | — |
| GAL → G | REDENOM | 60 | — | 2024-07-19 |
| RNDR → RENDER | RENAME | 1 | 2024-07-22 03:00 | 2024-07-26 08:00 |
| MATIC → POL | RENAME | 1 | 2024-09-10 03:00 | 2024-09-13 10:00 |
| FTM → S | RENAME | 1 | 2025-01-13 03:00 | 2025-01-16 08:00 |
| BNX → FORM | RENAME | 1 | 2025-03-18 03:00 | 2025-03-19 08:00 |
| EOS → A | RENAME | 1 | 2025-05-26 03:00 | 2025-05-28 08:00 |
| MKR → SKY | REDENOM | 24000 | 2025-09-15 03:00 | 2025-09-17 08:00 |

Doğrulanmamış adaylar (G5'te Binance "Token Swap" duyurularından kontrol edilir): MC→BEAMX, TOMO→VIC, ALPHA→STELLA, NPXS→PUNDIX, LEND→AAVE, BCHABC→BCH, STRAT→STRAX, BQX→VGX, BCHA→XEC. Boşluk ve oran kontrolünün bulduğu diğer adaylar da eklenir. **Tablo kullanıcı tarafından onaylanmadan backtest başlamaz.**

**Diğer meta tablolar**

- `meta/fee_promotions.csv`: sıfır komisyonlu çiftler ve tarih aralıkları. Bilinen: BTC ve bazı büyük çiftlerde yaklaşık Temmuz 2022 – [22 Mart 2023](https://www.fxstreet.com/cryptocurrencies/news/binance-ends-zero-fee-trading-for-btc-pairs-202303230217) sıfır komisyon kampanyası; sonrasında BTC/TUSD. Kaiko'ya göre bu çiftler zirvede Binance hacminin [%85'ini](https://www.kaiko.com/resources/the-impact-of-binances-zero-fee-volume) oluşturdu. Tam liste G5'te duyurulardan çıkarılır.
- `meta/delist_announcements.csv` (isteğe bağlı): Binance'in delist ve Monitoring Tag duyuruları, duyuru tarihiyle. Varsa backtest ve canlı aynı kuralı kullanır (duyurudan sonraki gün sat). Monitoring/Seed Tag sistemi 2023-07-26'da başladı; öncesi için kayıt yok.

## Coin evreni

Evren her ay, **önceki ayın son günlük kapanışıyla** kurulur ve o kapanıştaki karardan itibaren bir ay geçerlidir. Sadece o ana kadar bilinen veri kullanılır.

**Algoritma (ay M için, karar anı T = M'den önceki ayın son kapanışı)**

1. T'de işlem gören tüm USDT çiftlerini al (sembol eşleştirme tablosu uygulanmış seriler).
2. Dışlananları çıkar (aşağıdaki liste).
3. T'de en az **365 temiz günü** olmayanları çıkar. Bu kural yeni listelenen coinlerin "pompala ve süzül" dönemini ve 12 aylık kilit açılışlarını büyük ölçüde dışarıda bırakır. Binance'te 2024 listelemelerinin [medyan getirisi yaklaşık −%50](https://cryptoslate.com/tokens-display-up-to-negative-70-median-returns-after-cex-listing-animoca-research/) oldu.
4. Her gün için likidite ölçüsü: **L\_d = max(USDT çiftinin quote hacmi, kampanyasız diğer stablecoin çiftlerinin en büyüğünün quote hacmi)**. USDT dışı hacim, o stablecoin'in o günkü USDT kapanışıyla çevrilir. Sıfır komisyon kampanyasındaki çiftler kampanya süresince dışarıda tutulur. Toplama yapılmaz.
5. L\_d'nin son 30 günlük medyanını hesapla. 5 milyon USDT'nin altındakileri çıkar.
6. Kalanları medyan likiditeye göre sırala, ilk **20**'yi al (BTC 20'nin içinde sayılır). Alt-coin sistemine ayrılan sermaye 3.000 USDT'nin altındaysa 10, 15.000 USDT'nin üzerindeyse 30 coin kullanılır; 50 coin ancak yaklaşık 20.000 USDT'nin üzerinde anlamlıdır. Bu seçim sermayeye göre önceden yapılır, sonuçlara göre değil.
7. `universe/{YYYY-MM}.csv` olarak kaydet: sembol, sıra, medyan likidite, likidite kademesi.

**Dışlananlar (isim listesiyle, önce)**

- Stablecoin ve fiat: USDC, BUSD, TUSD, USDP/PAX, FDUSD, DAI, USDS, USD1, USDe, UST/USTC, EURI, AEUR, fiat sembolleri. 90 günlük getiri standart sapması < %1 kontrolü sadece yedek.
- Altın: PAXG.
- Sarılmış ve likit staking tokenleri: WBTC, WBETH, BETH, BNSOL.
- Kaldıraçlı tokenler, açık liste ile (BTCUP, BTCDOWN, ETHUP, ETHDOWN, BNBUP, BNBDOWN vb.; isim ekine göre değil, JUP gibi coinler elenmesin). Binance kendi kaldıraçlı tokenlerinde [işlemi 2024-02-28'de durdurdu, 1–3 Nisan 2024'te kaldırdı](https://cointelegraph.com/news/binance-leveraged-token-services-shutdown).
- **Borsa tokenleri: BNB, FTT ve benzerleri.** Binance'te BNB tutmak borsa riskini ikiye katlar (FTX'te FTT tutanların durumu); ayrıca ters oynaklık ağırlıklandırması düşük oynaklıklı borsa tokenlerine büyük ağırlık verir. Backtestte de dışlanır.

**Likidite kademeleri ve ağırlık tavanları**

| Kademe | Tanım | Coin başına ağırlık tavanı | Kayma (her yönde) |
| --- | --- | --- | --- |
| A | BTC ve ETH | %10 | %0,05 |
| B | Evren sırası 3–20 | %5 | 30 günlük medyan likidite ≥ 100M: %0,05; 20–100M: %0,10; < 20M: %0,20 |
| C | Evren sırası 21–50 (sadece 30 ve 50 coinlik komşularda) | %3 | Aynı mutlak likidite kademeleri |

Kayma kademeleri sıraya değil mutlak likiditeye bağlıdır (B ve C için), böylece evren büyüklüğü değiştiğinde maliyet varsayımı değişmez. Kademe ve tavan, evren kurulurken belirlenir ve ay boyunca sabittir.

**Evrenden çıkan coinler:** Ay başında evrenden çıkan bir coinde pozisyon varsa yeni alım yapılmaz; hedef ağırlık min(hesaplanan hedef, mevcut ağırlık) olur, yani pozisyon sadece küçülebilir ve kendi çıkış kuralıyla kapanır.

**Beklenen durum:** 2019–2020'de bu kriterleri geçen coin sayısı muhtemelen 15–30'dur; evren o yıllarda 20'nin altında kalabilir. G6 her ayın evren büyüklüğünü raporlar. Sadece USDT hacmiyle kurulan evren (T7) sağlamlık testi olarak ayrıca çalıştırılır.

## Strateji

Karar her gün 00:00 UTC kapanışıyla, sadece o ana kadarki veriyle verilir. İşlemler aynı gün 00:00–02:00 UTC arasında gerçekleşir (backtest bölümü). Bir coin için sinyal üretilebilmesi için en az 200 temiz bar gerekir; evren kuralı (365 gün) bunu zaten sağlar.

**1. Trend sinyali (tamponlu, üç vade)**

Her coin i ve vade n ∈ {20, 50, 100} için EMA: `close.ewm(span=n, adjust=False).mean()`. Günlük oynaklık σ\_d = 30 günlük log getiri standart sapması. Her vade için durum değişkeni s\_{i,n} ∈ {0, 1}:

```latex
s_{i,n}(t) = \begin{cases} 1 & C_i(t) > EMA_{i,n}(t)\,(1 + h\,\sigma_{d,i}(t)) \\ 0 & C_i(t) < EMA_{i,n}(t)\,(1 - h\,\sigma_{d,i}(t)) \\ s_{i,n}(t-1) & \text{aksi halde} \end{cases} \qquad S_i(t) = \tfrac{1}{3}\sum_n s_{i,n}(t)
```

- Temel ayarda h = 0,5. Tampon çarpandır, toplanan değildir (oynaklık bir getiridir, fiyata eklenemez). Simülasyonda h = 0,5 kesişme sayısını yaklaşık %43, yıllık maliyeti yaklaşık %8'den %4,6'ya indirdi.
- Başlangıç durumu: coinin ilk uygun gününde tamponsuz kural (C > EMA ise 1).
- S ∈ {0, 1/3, 2/3, 1} pozisyonun kademesidir: trend güçlendikçe pozisyon büyür.

**2. Oynaklık ve korelasyon tahmini**

- σ\_i = max(rv30\_i, rv90\_i, 0,30), yıllık (√365). Uzun ve kısa pencerenin büyüğü alınır; sıçramadan hemen önce yapay olarak düşen oynaklığa (FTT tipi) karşı korunma sağlar. Oynaklık için 30 günün en az 20'si, 90 günün en az 60'ı dolu olmalı.
- Korelasyon matrisi R: günlük log getirilerden EWMA korelasyonu, yarılanma 45 gün, sabit-korelasyon hedefine (köşegen dışı ortalama) %50 küçültme. Kovaryans Σ = D·R·D, D = diag(σ). Böylece tek bir oynaklık tahmini kullanılır.

**3. Pozisyon büyüklüğü**

- Aktif küme A = {i : S\_i > 0}. Ham ağırlık v\_i = 1/σ\_i.
- k\* = en büyük k, öyle ki: tam ağırlıklar w\_full,i = min(k·v\_i, CAP\_i) için portföy oynaklığı √(wᵀΣw) ≤ %35 **ve** Σ w\_full ≤ 1. k ikiye bölme (bisection) ile bulunur.
- Hedef ağırlık w\*\_i = S\_i · w\_full,i. Böylece S kademesi korunur ve hedef oynaklık aşılmaz.
- CAP\_i = likidite kademesine göre %10 / %5 / %3.
- Az coin trenddeyken tüm ağırlıklar tavana dayanır ve portföy oynaklığı %35'in altında kalır; bu kabul edilir (kaldıraç yok).
- Evrenden çıkmış ama pozisyon tutulan coin: w\*\_i = min(w\*\_i, w\_i).

**4. Yeniden dengeleme**

- **Çıkış her zaman tamdır:** w\*\_i = 0 ve w\_i > 0 ise pozisyonun tamamı satılır (minimum işlem eşiğinin altında olsa bile).
- **Giriş ve kademe değişikliği hedefe kadar yapılır:** w\_i = 0 iken giriş veya S\_i son işlemdeki değerden farklıysa, hedefe kadar alınır veya satılır.
- **Kayma (drift) bandı:** diğer durumlarda, mutlak fark max(0,25·w\*\_i, 0,005)'i aşarsa sadece bandın kenarına kadar işlem yapılır.
- **Minimum işlem:** çıkış dışındaki işlemler, büyüklüğü MINTRADE\_i = max(1,1 × minNotional\_i / NAV, 0,0025)'in altındaysa yapılmaz.

**Haftalık giriş, günlük çıkış (T0'ın parçası)**

- Sinyaller, hedefler ve emirler her gün hesaplanır.
- Pozisyonu **azaltan** her işlem (çıkış, kademe düşüşü, bant satışı) her gün yapılır. Böylece riskten çıkış gecikmez.
- Pozisyonu **artıran** her işlem (yeni giriş, kademe artışı, bant alımı) sadece pazar günü kapanışındaki kararla yapılır (dolum pazartesi 00:00–02:00 UTC). Diğer günlerde artırım yapılmaz.
- Gerekçe: simülasyonlarda bu kural yıllık maliyeti yaklaşık 1 puan azalttı ve en büyük düşüşü birkaç puan küçülttü. Kripto momentumu 1–4 haftalık ufuklarda sinyalini koruduğu için girişi birkaç gün geciktirmenin bedeli sınırlı kalmalı. Giriş gününün diğer günlere kaydırılması T8'de raporlanır, seçilmez.

**Bitcoin'e göre güç filtresi (sadece T9 varyantında)**

Amacı, mutlak olarak yükselişte olsa bile Bitcoin'in gerisinde kalan alt-coinleri tutmamak. Bu coinler BTC-200 kıyasına karşı getiri katmadan oynaklık ve maliyet ekler.

- rel\_i(t) = ln(C\_i(t)/C\_i(t−30)) − ln(BTC(t)/BTC(t−30)), BTC dışındaki evren coinleri için.
- q\_i(t) = rel\_i(t)'nin evren içindeki yüzdelik sırası.
- Kapı g\_i (durum makinesi): q\_i ≥ 2/3 ve rel\_i > 0 ise 1; q\_i < 1/3 veya rel\_i < −0,05 ise 0; arasında önceki değer korunur. Başlangıç: ilk koşul sağlanıyorsa 1, yoksa 0. 30 temiz bardan azsa 0. BTC için g ≡ 1.
- Etkin sinyal S\_i × g\_i, k hesaplanmadan önce uygulanır. Kapının kapanması tam çıkış demektir.
- Parametreler (30 gün, üçte birlik dilimler, %5 histerezis) literatürden alınmıştır ve ayarlanmaz. Kripto kesitsel momentumunun yaklaşık 4 haftadan uzun pencerelerde zayıfladığı bulgusu nedeniyle 90 değil 30 gün seçildi.

**5. Rejim filtresi (sadece T1 varyantında)**

Durum makinesi: BTC kapanışı 0,97 × SMA200'ün altına inerse KAPALI, 1,03 × SMA200'ün üstüne çıkarsa AÇIK; arasında önceki durum korunur. Başlangıç: C > SMA200 ise AÇIK. KAPALI iken BTC dışı tüm coinlerde S\_i = 0 (k hesaplanmadan önce). Simülasyonda histerezis rejim değişimini yılda yaklaşık 13'ten 5'e indirdi.

**Sözde kod (temel ayar)**

```
PARAM: SPANS=(20,50,100) H=0.5 FLOOR=0.30 TGT=0.35 GMAX=1.0
       REL=0.25 MINB=0.005 CAP={A:0.10, B:0.05, C:0.03}

her gün t, kapanış verisiyle (≤ t):
  E = evren(t) ∩ {≥200 temiz bar}     ; H = tutulan ∖ E
  her i ∈ E ∪ H için:
     s_i,n = tamponlu_durum(C, EMA_n, σ_d, H, önceki s_i,n)
     S_i = ortalama_n(s_i,n)
  [T1] rejim KAPALI ise: S_i = 0, i ≠ BTC
  σ_i = max(rv30, rv90, FLOOR) ; Σ = D·R_küçültmeü·D
  A = {i: S_i>0} ; v_i = 1/σ_i
  k* = bisection: max k, vol(min(k·v, CAP)) ≤ TGT ve Σ min(k·v, CAP) ≤ GMAX
  w_full = min(k*·v, CAP) ; w*_i = S_i·w_full_i ; i∈H: w*_i = min(w*_i, w_i)
  her i için (w = kaymış mevcut ağırlık):
     w*_i = 0 < w_i                 → tamamını sat
     w_i = 0 < w*_i veya S_i değişti → hedefe işlem
     |w_i − w*_i| > max(REL·w*_i, MINB) → bant kenarına işlem
     çıkış dışı |Δ| < MINTRADE_i      → işlem yapma
  [haftalık] t pazar kapanışı değilse: pozisyonu artıran tüm işlemleri atla
             (giriş, kademe artışı, bant alımı); azaltan işlemler her gün yapılır
  emirler: önce satışlar; nakit yetmezse alımlar orantılı küçültülür
  adet = Δw·NAV(t)/C(t), dolum: VWAP 00:00–02:00 (t günü sonrası)
```

Simülasyonda bu kural hedefi sıfır olan coinlerde hiç artık bırakmadı, hedeften sapmayı portföyün %5–9'unda tuttu ve en küçük işlemleri portföyün yaklaşık %0,27'si düzeyinde tuttu.

## Backtest motoru

Olay sıralı günlük döngü; vektörel kısayol kullanılmaz. Başlangıç sermayesi 10.000 USDT (duyarlılık: 2.000 USDT).

**Günlük döngü (t günü)**

1. t−1 kapanışında oluşturulan emirleri t gününün 00:00–02:00 UTC VWAP'ından gerçekleştir (aşağıda).
2. Delist ve boşluk kurallarını uygula.
3. t kapanışında portföyü değerle: nakit (temel varsayımda %0 getiri) + Σ adet × kapanış.
4. Ayın son günüyse bir sonraki ayın evrenini kur.
5. Strateji bölümündeki algoritmayla sinyal, ağırlık ve emirleri sadece t kapanışına kadarki veriyle hesapla.

**Dolum fiyatı**

- Temel: VWAP = Σ quote\_volume / Σ volume, 00:00–02:00 UTC arasındaki iki 1 saatlik mumdan. Tipik fiyat × hacim kullanılmaz.
- Alım fiyatı = VWAP × (1 + kayma), satım = VWAP × (1 − kayma); komisyon %0,10 ayrıca. Bu pencerede hacim sıfırsa bir sonraki saat kullanılır.
- Adet = Δw × NAV(t−1 kapanış) / kapanış(t−1).
- Varyantlar: t+1 açılışı (T3, iyimser), VWAP 06–07 ve 14–15 (T4). İşlem saati gölge moddan sonra değiştirilmek istenirse sadece önceden kaydedilmiş T4 seçeneklerinden biri seçilebilir.

**Maliyetler**

| Kalem | Değer |
| --- | --- |
| Komisyon | %0,10 her yönde (BNB indirimi backtestte sayılmaz) |
| Kayma | Likidite kademesine göre (evren bölümü): %0,05 / %0,10 / %0,20 her yönde |
| Delist cezası | %5 temel; %20 ve %50 zorunlu stres (T5) |
| Nakit getirisi | %0 (temel); duyarlılık: hazine bonosu − 1,5 puan ve tam hazine bonosu |
| Stres | Tüm maliyetler ×2 (T6) |

**Delist kuralı**

- Delist tanımı: son mum 7 günden eski **ve** sembol exchangeInfo'da yok veya durumu TRADING değil. Backtestte son mumun tarihi kullanılır.
- Duyuru tablosu varsa ve duyuru t−1 kapanışından önceyse: t günü normal maliyetle satılır (canlıyla aynı).
- Duyuru bilinmiyorsa: pozisyon son işlem gününe kadar tutulur ve o günün VWAP'ı × (1 − ceza) ile kapatılır. Önceki günün kapanışından satış yapılmaz (artık işlem görülemeyecek bir fiyat).

**Boşluk kuralı**

- Bir serideki boşluk önceden bilinemez. Boşluk süresince son fiyat taşınır, sinyal ve ağırlık dondurulur, işlem yapılmaz.
- Seri devam ederse normal karar döngüsüne dönülür. Hiç devam etmezse delist kuralı son fiyattan uygulanır.
- RENAME ve REDENOM satırlarında iki seri birleştirildiği için boşluk boyunca pozisyon tutulur (bu değişiklikler önceden duyurulduğu için geriye bakış kabul edilebilir).

**Emir filtreleri:** Binance'in NOTIONAL ve LOT\_SIZE filtreleri backtestte de uygulanır. Tarihsel filtre değerleri olmadığı için sabit minimum emir = 10 USDT varsayılır. 10.000 USDT sermayede bu, minimum işlem eşiğini (%0,25) bağlayıcı yapmaz; 2.000 USDT duyarlılığında bağlayıcı olabilir.

**Muhasebe**

- Nakit asla negatif olamaz; önce satışlar, sonra alımlar.
- Her dolum kaydedilir: tarih, coin, yön, adet, VWAP, kayma, komisyon, işlem sonrası ağırlık.
- **Döngü (işlem) tanımı:** ağırlığı 0'dan pozitife taşıyan ilk dolumdan, tekrar 0'a indiren doluma kadar. Aradaki S kademesi değişiklikleri döngünün içindedir. Döngü kârı = tüm dolumlar ve maliyetler; dönem sonunda açık döngüler piyasa değerinden "açık" olarak işaretlenir. Kazanan döngü = kâr > 0. Süre = son dolum − ilk dolum.
- Sonuçlar hem bileşik hem sabit tutarlı olarak raporlanır; USDT/USD vekili (USDCUSDT'nin tersi) ile dolara çevrilmiş hali de gösterilir.

**Canlı kuralların backteste yansıtılması**

- **−%35 sert sınır:** portföy zirvesinden −%35 düşüşte yeni alımların durması kuralı backtestte de uygulanır, böylece düşüş ufku tabloları canlı davranışla tutarlı olur. Backtestte yeniden başlatma kuralı: portföy zirvenin −%25'ine geri döndüğünde.
- **Küsürat:** minimum emir büyüklüğünün altında kalan artıklar satılamayabilir; backtestte değeri sıfırlanır (kötümser).
- **Karşı taraf stresi (T6):** borsadaki varlığın tek seferde %20 ve %50 kaybı senaryoları ve sistemin hala anlamlı kaldığı yıllık beklenen kayıp oranı raporlanır.

**Zorunlu testler**

1. **Geleceği görme testi:** t sonrasındaki tüm fiyat **ve meta veri** (evren dosyaları, kalite işaretleri, sembol tablosu) rastgele bozulduğunda t'ye kadarki tüm kararlar aynı kalmalı.
2. **Pozitif kontrol:** sinyale bilerek 1 günlük sızıntı eklenir; test bunu yakalamalı.
3. **Elle hesap:** 2 coin, 10 günlük bir örnekte portföy değeri elle hesaplananla birebir eşleşmeli.
4. **Al-tut eşdeğerliği:** maliyet sıfır ve tek coinde her zaman tam pozisyon iken sonuç al-tut ile aynı olmalı.
5. **Altın kayıt (golden master):** kilitten sonra tüm karar geçmişi kaydedilir; her kod veya kütüphane değişikliğinden sonra aynı kararlar birebir yeniden üretilmeli.
6. **Bağımsız kontrol betiği:** sinyaller ve tek coinlik getiri, motoru görmemiş **ayrı bir Claude oturumunda** sadece bu belgeden yazılmış basit bir pandas betiğiyle tekrar hesaplanır. Aynı oturumun yazdığı iki kod aynı hatayı paylaşabilir.

## Değerlendirme

Asıl soru "ne kadar kazandırdı" değil, "bu sonuç basit kıyası ve tesadüfü yeniyor mu". İstatistiksel güç düşüktür ve bu açıkça kabul edilir.

**Güç hakkında gerçekçi beklenti**

- Yaklaşık 2,8 yıllık bir dönemde Sharpe'ın standart hatası yaklaşık **0,6**. Gerçek Sharpe'ı sıfırdan ayırt etmek için gereken minimum kayıt uzunluğu, Sharpe 1'de yaklaşık 2,7 yıl, Sharpe 0,5'te yaklaşık 10,8 yıl.
- Hiç becerisi olmayan bir sistem bile "doğrulama döneminde pozitif getiri" kriterini yaklaşık %38–50 ihtimalle geçer; sadece long olduğu için boğa piyasasında daha da yüksek. Bu yüzden doğrulama dönemi tek başına kanıt değil, bir akıl sağlığı kontrolüdür.
- Simülasyonda tüm geç/kal kriterlerini birlikte geçme olasılığı: gerçek Sharpe 0'da yaklaşık %3, 0,5'te %22, 0,8'de %41. Yani iyi bir sistem de kriterleri kaybedebilir; ama kötü bir sistemin geçmesi zordur. Tasarım bilinçli olarak bu yöndedir.

**Raporlanacak metrikler (her çalıştırma, her iki rejim dönemi ayrı ayrı)**

Yıllık getiri; gerçekleşen oynaklık ve %35 hedefle farkı; ortalama toplam maruziyet ve nakit payı; risksiz faiz üzerindeki Sharpe; Sortino; Calmar; en büyük düşüş ve süresi; sudan uzak kalınan süre; çarpıklık; kayan 12 aylık Sharpe; yıl yıl getiri; ortalama ve zaman içindeki toplam maruziyet; yıllık ciro ve toplam maliyet; döngü sayısı, kazanma oranı, ortalama kazanç/zarar; tutma süresinin medyanı ile %10 ve %90 dilimleri (kazanan ve kaybeden ayrı); kârın en iyi %10 döngüden gelen payı; kârlı coin sayısı; **maksimum maruziyette en kötü 1 ve 3 günlük kayıp tablosu** (ör. Mart 2020, Kasım 2022 FTT, 10 Ekim 2025).

**Kıyaslar (hepsi aynı dolum, maliyet ve faiz varsayımıyla)**

1. **BTC-200 (birincil kıyas).**
2. BTC/ETH eşit ağırlıklı, her biri kendi 200 günlük ortalamasıyla.
3. BTC al-tut ve stratejinin oynaklığına ölçeklenmiş BTC al-tut.
4. %50 BTC + %50 nakit.
5. Evrenin eşit ağırlıklı al-tutu (aylık dengelenen).
6. Oynaklık ayarı olmadan eşit ağırlıklı aynı trend sinyali.
7. Regresyon: strateji getirisi \~ BTC getirisi + evren eşit ağırlıklı getiri (ve yükselen/düşen piyasa betaları). Strateji sadece kaldıracı azaltılmış piyasa riski mi?

**Yatırımcı çıtaları (raporlanır):** ABD 3 aylık hazine bonosu ve stopaj sonrası TL mevduatı (hem TL hem USD cinsinden). 2026'da ağırlıklı ortalama TL mevduat faizi yıllık yaklaşık %43, stopaj sonrası yaklaşık %35,5 idi; doların yıl başından bu yana yaklaşık %16 yükselişi düşüldüğünde bu, dolar cinsinden kabaca +%13 eder. Bu çıta kur riskini taşır, ücretsiz bir kıyas değildir; ama Türkiye'de yaşayan bir yatırımcı için borsada boş bekleyen USDT'nin fırsat maliyetini gösterir.

**Sıfır hipotezleri (rastgele kıyas)**

- **(a) Tarih karıştırma:** her coinin döngüleri (süre ve ağırlık yolu) korunur; başlangıç tarihleri, o coinin evrende olduğu pencereler içinde rastgele ve çakışmayacak şekilde taşınır. Toplam ağırlık 1'i aşarsa orantılı küçültülür.
- **(b) Maruziyet yolu korunur:** her günün toplam maruziyeti ve pozisyon sayısı korunur; strateji bir döngü açtığında o ağırlık yolu, o anda tutulmayan rastgele uygun bir coine verilir. Bu, piyasa zamanlamasını coin seçiminden ayırır.
- Her biri 1.000 çalıştırma, sabit tohum. p = (1 + sıfır çalıştırmalarında gözlenen≥) / 1.001; kıyas Sharpe üzerinden, en büyük düşüş yüzdeliği de raporlanır.

**Negatif ve pozitif kontroller**

| Kontrol | Beklenen |
| --- | --- |
| Günlük log getiriler tarihe göre tüm coinlerde birlikte karıştırılıp fiyatlar yeniden kurulur | Avantaj kaybolur (maliyet kadar zarar) |
| Oynaklığı eşleştirilmiş sentetik GARCH serileri | Maliyet kadar zarar |
| Bir coinin sinyali başka bir coinin getirisine uygulanır | Avantaj büyük ölçüde kaybolur |
| Sinyal 365 gün gecikmeli | Avantaj kaybolur |
| Orijinal − ters sinyal farkı | Anlamlı ölçüde sıfırın üzerinde (ters sinyalin zarar etmesi gerekmez) |
| Kararlar 1 ve 3 gün gecikmeli | Biraz bozulur, çökmez |
| Mum zamanlaması değişir (T8) | Benzer sonuç; büyük farklar kırılgan bir avantajı gösterir |
| Bir yıl çıkarılır (o yılın günlük getirileri silinip kalan zincirlenir) | Sonuç tek bir yıla bağlı olmamalı |
| En iyi 5 döngü çıkarılır | Sıfıra yakın veya pozitif |

Negatif kontrollerde avantaj kaybolmuyorsa kodda hata veya geleceği görme var demektir; diğer tüm sonuçlar geçersiz sayılır.

**İstatistik**

- **Deflated Sharpe oranı (DSR)**, N ön kayıt bölümündeki gibi (alt sınır 100). [Bailey ve López de Prado](https://papers.ssrn.com/abstract=2460551)
- **Backtest aşırı uyum olasılığı (PBO, CSCV yöntemi)**, parametre ızgarası üzerinde. [Bailey vd.](https://papers.ssrn.com/abstract=2326253)
- **Durağan blok bootstrap** (ortalama blok 30 gün, 10.000 yol): Sharpe ve kıyasa göre Sharpe farkı için güven aralığı; en büyük düşüş dağılımı; eşleştirilmiş yeniden örnekleme ile BTC-200 farkı.
- **Minimum kayıt uzunluğu** hesabı.
- **Düşüş ufku tablosu:** kilitte, aynı bootstrap'ten h = 30/60/90/180/365 günlük ufuklar için %95'lik düşüş değerleri tablolanır. Canlı durdurma kuralı bu tabloyu kullanır.

**Parametre ızgarası (komşular, tümü raporlanır, en iyisi seçilmez)**

| Parametre | Temel | Komşular |
| --- | --- | --- |
| Portföy oynaklık hedefi | %35 | %25, %45 |
| Vadeler (birlikte) | 20/50/100 | ×0,8 ve ×1,2 |
| Evren büyüklüğü | 20 | 30, 50 |
| Kayma bandı | %25 | %15, %35 |
| Tampon h | 0,5 | 0, 1,0 |

**Sıralama:** ızgara, sıfır hipotezleri, kontroller, PBO ve DSR önce sadece geliştirme döneminde çalışır. Kilitte, önceden kaydedilmiş tüm toplu çalıştırma doğrulama döneminde bir kez yapılır; ardından tam dönem PBO, DSR ve birincil hipotez testi raporlanır. Bundan sonra değişiklik yapılmaz.

**Geç/kal kriterleri (2–9 alt-coin sisteminin Aşama 2'ye geçmesi için zorunlu; 1 sistemin rolünü belirler)**

1. Birincil hipotez: tam dönemde BTC-200'ü Sharpe'ta eşleştirilmiş bootstrap ile %95 güvenle yener. **Geçmezse alt-coin sistemi en fazla küçük bir ek dilim olabilir; ana pozisyon BTC-200'dür.**
2. Tam dönem DSR ≥ 0,95.
3. Geliştirme döneminde PBO < 0,5.
4. Doğrulama döneminde net Sharpe > 0, hem 1× hem 2× maliyetle.
5. Her iki sıfır hipotezini Sharpe'ta %95 düzeyinde geçer.
6. Bootstrap medyan en büyük düşüşü, evren eşit ağırlıklı al-tutun yarısından küçük (eşleştirilmiş örnekleme).
7. Tüm komşularda net Sharpe > 0 ve temel ayarın en az %50'si.
8. Tüm negatif kontroller beklendiği gibi.
9. %20 delist cezasıyla net Sharpe > 0.

## Gölge mod ve canlı (Aşama 2)

Gölge mod sistemin backtestle aynı kararları ürettiğini ve gerçek maliyetleri doğrular; kârlılığı kanıtlamaz. Alt-coin sistemi ve BTC-200 gölge modda yan yana çalışır; bu aynı zamanda 12 aylık ileriye dönük testin başlangıcıdır.

**Günlük işleyiş (00:05 UTC)**

1. Yeni kapanan günlük mumu REST klines'tan al (`close_time < şimdi` kontrolüyle). Günlük arşiv dosyası ertesi gün yayımlandığında karşılaştır; fark ayrıca raporlanır.
2. O günün tüm girdilerini (fiyatlar, evren, meta tablolar) bir anlık görüntü olarak kaydet ve özetle.
3. Kalite kontrolü, sinyal, hedef ağırlık, emir listesi.
4. **Tutarlılık kontrolü:** backtest motoru aynı anlık görüntü üzerinde çalıştırılır; kararlar birebir aynı olmalı. Fark = hata, uyarı.
5. Gölge modda sanal dolum; orderbook ölçümleri (aşağıda). Canlıda gerçek emir.

**Kayma ölçümü:** gerçek borsanın herkese açık `/api/v3/depth` verisinden. Ayrı alanlar: karar anındaki orta fiyat, hedef emir büyüklüğünde orderbook'u yürüme maliyeti, 00:00–02:00 VWAP. Görüntüler 00:05, 01:00, 06:00 ve 14:00 UTC'de alınır (T4 varyantlarıyla uyumlu). Maliyet = işaretli (dolum − karar anı orta fiyat) / orta fiyat + komisyon. Binance Spot Demo Mode verisi ["gerçekçi" ama "gerçek" değil](https://developers.binance.com/docs/binance-spot-api-docs/demo-mode/general-info); sadece emir akışı ve filtre testleri için kullanılır (demo API anahtarı gerekir). Testnet kullanılmaz.

**Periyodik işler**

| Sıklık | İş |
| --- | --- |
| Her gün | Durum raporu (sadece istisnalar bildirim olarak); harici "ölü adam" sinyali: günlük iş 01:00 UTC'ye kadar kendini bildirmezse uyarı |
| Her gün | exchangeInfo durumu ve Binance delist duyuruları kontrolü |
| Her gün (canlı) | Bakiye mutabakatı: gerçek ve sanal portföy farkı > %0,5 ise uyarı |
| Her hafta | Özet rapor |
| Her ay | Arşiv checksum'larını tekrar kontrol; sembol eşleştirme ve kampanya tablolarını güncelle; borsa bakiyesi payı kontrolü (canlı) |
| Üç ayda bir | Tam backtesti yeni veriyle çalıştır, canlı sonuçları dağılımla karşılaştır (parametre değişmez); API anahtarını yenile |

**Emir güvenliği (canlı)**

- **Çifte emir önleme:** `newClientOrderId` sadece açık emirler arasında benzersizdir; dolmuş bir emrin kimliği tekrar kullanılabilir. Gün + sembol + yön için belirleyici bir kimlik kullanılır; emir niyeti gönderilmeden önce SQLite'a yazılır; yeniden başlatmada açık emirler ve işlemler sorgulanıp mutabakat yapılır. 5XX yanıtı "başarısız" değil "bilinmiyor" sayılır.
- **Filtreler:** her emir NOTIONAL, LOT\_SIZE ve MARKET\_LOT\_SIZE'a göre yuvarlanır; geçmeyen emir kaydedilir ve atlanır.
- **Saat:** chrony ile senkron; emirlerden önce `/api/v3/time` ile karşılaştırma; recvWindow 5.000 ms.
- **Bakım:** borsa bakımdaysa 23:00 UTC'ye kadar saatte bir tekrar denenir, sonra o gün atlanır ve kaydedilir.
- **Denetim kaydı:** SQLite'ta sadece ekleme yapılan kayıt: niyet, istek, yanıt, dolum. Şifreli olarak sunucu dışına yedeklenir.

**Canlı maliyet uygulamaları (backtest varsayımını değiştirmez)**

- **BNB ile komisyon ödeme:** komisyonu %0,10'dan %0,075'e indirir; mevcut işlem sıklığında yılda portföyün yaklaşık %0,2–0,5'i tasarruf. Bunun için sadece komisyona yetecek kadar, portföyün yaklaşık %0,1–0,2'si kadar BNB tutulur ve ayda bir tamamlanır. Bu bakiye NAV'a ve mutabakata dahil edilmez. Borsa tokenlerinin evrenden dışlanması kuralı değişmez; bu tutar o riski anlamlı biçimde artırmaz.
- **Fiyat sınırlı, hemen dolan emirler (IOC limit):** piyasa emri yerine, orderbook'u fazla yürümeyi engelleyen bir fiyat sınırıyla verilir. Maliyeti yoktur.
- **Maker (bekleyen limit) emirler** bu sermaye büyüklüğünde yılda en fazla yaklaşık 0–0,2 puan kazandırır ve trend devam ederken emrin dolmaması riskini taşır; sadece gölge modda deney olarak denenebilir.
- **TL dönüşümü:** USDT/TRY dönüşümleri limit emirle ve toplu yapılır; P2P kullanılmaz (fiyat farkları ve banka hesabı dondurulma riski). Binance TR çekimleri durduğu için bu yol şu an kesik.
- **Küsürat:** 20 USDT altındaki bakiyeleri BNB'ye çevirmenin %2 ücreti vardır; çıkışlarda bakiyenin tamamı lot adımına yuvarlanarak satılır, artıklar USDT'ye çevrilir.

**API anahtarı:** ayrı bir alt hesap; Binance'in önerdiği Ed25519 anahtar; VPS'in sabit IP'sine bağlı; sadece spot işlem yetkisi, para çekme ve transfer kapalı. Anahtar ayrı bir servis kullanıcısında, dosya izni 600, systemd `LoadCredential` ile yüklenir; git'e ve düz `.env`'ye konmaz. Üç ayda bir yenilenir.

**Acil durdurma (üç mod, gölge modda test edilir):** (a) yeni alım yok, mevcut pozisyonlar kendi kurallarıyla yönetilir; (b) her şeyi USDT'ye çevir; (c) API anahtarını Binance arayüzünden elle iptal et. (a) ve (b) bir bayrak dosyası ve Telegram komutuyla tetiklenir.

**Olay protokolü (önceden belirlenmiş):** borsa güvenlik ihlali veya çekim dondurma, USDT'nin 1 dolardan %2'den fazla sapması, ya da tutulan bir coin için delist duyurusu durumunda ilgili pozisyonlar bir sonraki saatlik VWAP'tan satılır ve yeni sermaye eklenmez. USDT sapması %1'i aşarsa uyarı verilir.

**Müdahale protokolü:** sisteme elle müdahale (bir işlemi atlamak, kuralı değiştirmek) ancak gerekçesi yazılıp 72 saat beklendikten sonra yapılabilir ve bir deneme olarak sayılır. Canlı sadece işaretlenmiş (tag) sürümlerden çalışır; her kod değişikliği altın kayıt testinden geçmeden devreye girmez.

**Karşı taraf riski:** borsada sadece işlem sermayesi tutulur. Toplam strateji varlığının %60–70'i borsada tutulur, kalanı borsa dışında. Pay üç ayda bir, ya da ±10 puandan fazla saparsa daha erken yeniden dengelenir; sermaye artışları da aynı oranı izler. Simülasyonda bu kural, eski "%120 üstü çekilir" kuralına göre borsa batma riski varken hem beklenen büyümede hem de servetin yarısını kaybetme olasılığında daha iyi sonuç verdi. Binance TR'nin çekimleri durdurması, oradan fon aktarma yolunun da kesilebileceğini gösterdi; alternatif bir fonlama yolu önceden belirlenir.

**Takvim ve kriterler**

- Gölge mod 6–8 hafta (veya 4 hafta gölge + 4 hafta minimum büyüklükte canlı).
- **Canlıya geçiş (hepsi):** 0 karar farkı; işlerin %100'ü tamamlandı; ölçülen medyan maliyet varsayımın altında ve %90'lık dilim en fazla 2 katı; tüm emirler filtrelerden geçti; acil durdurma ve çökme sonrası kurtarma en az bir kez test edildi; Binance'in durumu netleşti; yazılı hukuki ve vergi görüşü alındı.
- **Sermaye:** ilk 2 ay çalışabilir minimum büyüklük (20 coinlik evrende kademe adımlarının minimum emrin en az 3 katı olması için alt-coin sistemine ayrılan sermaye yaklaşık 2.600–4.500 USDT olmalı; %80/%20 çekirdek–uydu bölünümünde önemli olan uydunun kendi sermayesidir); durdurma kuralları tetiklenmezse her çeyrekte en fazla 2 kat.
- **Durdurma kuralları:** canlı düşüşü, canlı süresine en yakın ufkun %95'lik düşüş değerini aşarsa; canlı ve gölge aylık getirisi 2 yüzde puandan fazla ayrışırsa; ölçülen maliyet 14 gün boyunca varsayımın 2 katını aşarsa; açıklanamayan mutabakat farkı olursa; borsa çekimleri dondurursa. Ayrıca backtestten bağımsız sert bir sınır: portföy zirvesinden −%35 düşüşte yeni alımlar durur (acil durdurma modu a) ve yazılı bir gözden geçirme yapılır; yeniden başlatma bu gözden geçirmeye bağlıdır.

## VPS ve altyapı

Aşama 1 kendi bilgisayarınızda yapılabilir; Aşama 2 için 7/24 çalışan bir VPS gerekir. Kod baştan taşınabilir yazılır.

- **Konum:** Binance, ABD IP'lerinden gelen isteklere "restricted location" (HTTP 451) döndürür; bazı Avrupa bulut IP'lerinde de aynı hata görüldü. Sunucu kiralandıktan sonra sadece `/ping` değil, **imzalı ve salt okunur bir çağrı** test edilir. Sabit IP'li sıradan bir VPS tercih edilir. Hesabın ülkesi Türkiye kalır; VPN veya proxy ile kısıtlama aşılmaz. Binance 1 Temmuz 2026'dan itibaren AB sakinlerine yeni spot hizmetini askıya aldı; bu kural hesabın ikametine bağlıdır, sunucu IP'sine değil, ama G0'da test edilmelidir.
- **Boyut:** 2 vCPU, 4 GB RAM, 40–60 GB disk (1 saatlik veri açılmış halde birkaç GB tutar). Bootstrap ve sıfır hipotezi çalıştırmaları için geçici olarak daha büyük bir makine kullanılabilir. VPS fiyatları 2026'da arttı; bütçe güncel fiyata göre yapılır.
- **Ortam:** Ubuntu LTS, Python 3.11+, `uv` ile kilitli bağımlılıklar (`uv.lock`), git. Tüm zamanlar UTC; kodda makineye özel yol yok, tüm yollar `settings.yaml`'dan.
- **Zamanlama:** systemd timer (`OnCalendar=*-*-* 00:05:00 UTC`, `Persistent=true`); timer dosyaları depoda tutulur.
- **Güvenlik:** SSH sadece anahtarla, şifreli giriş kapalı; ufw açık; otomatik güvenlik güncellemeleri; sistem ayrı bir servis kullanıcısıyla çalışır. Binance ihlalinin bir mühendisin dizüstü bilgisayarından başladığı unutulmamalı: anahtarlar kişisel bilgisayarda tutulmaz.
- **Yedekleme:** `meta/`, `reports/`, `experiments.md`, `PREREGISTRATION.md` ve SQLite denetim kaydı günlük, şifreli (restic veya age) olarak sunucu dışına. Ham veri yeniden indirilebilir.
- **Taşıma:** veri kopyalanmaz, VPS'te yeniden indirilir ve aynı checksum ve sonuçların alındığı doğrulanır. Bu aynı zamanda tekrarlanabilirlik testidir.

## Türkiye: hukuki ve vergisel durum

Bu bölüm bilgi amaçlıdır, hukuki veya vergi tavsiyesi değildir. Canlıya geçmeden önce bir avukat ve bir mali müşavirden yazılı görüş alınması Aşama 2'nin ön koşuludur.

| Konu | Durum | Kaynak |
| --- | --- | --- |
| 7518 sayılı Kanun kripto hizmet sağlayıcılarını SPK denetimine aldı (Resmî Gazete, 2 Temmuz 2024). Yabancı platformların Türkiye'yi hedefleyen faaliyetleri 2 Ekim 2024'e kadar sona ermeliydi. Cezai yaptırımlar hizmet sağlayıcılara yönelik | Yürürlükte | [SPK](https://spk.gov.tr/duyurular/basin-duyurulari/2024/kripto-varlik-hizmet-saglayicilara-iliskin-duyuru_02072024) |
| Binance TR, SPK'nın 28 Ekim 2026 tarihli geçici "faaliyette olanlar" listesindeki 40 platformdan biri; SPK listede olmanın izin anlamına gelmediğini belirtiyor | Lisans bekleniyor | [TechInside](https://www.techinside.com/spk-kripto-listesi-2026/) |
| Bireyin binance.com kullanması: kullanıcıya yönelik açık bir yaptırım bulunamadı. SPK Aralık 2024'te 50'den fazla kripto borsası dahil 108 siteye, Temmuz 2025'te başka platformlara erişim engeli getirdi; benzer bir engel mümkün | Belirsiz | [Sözcü](https://www.sozcu.com.tr/spk-50-den-fazla-kripto-para-borsasina-erisim-engeli-getirdi-p115798), [Av. Bilal Alyar](https://bilalalyar.av.tr/binance-yasal-mi/) |
| **On binde 3 (%0,03)** kripto işlem vergisi ve kazançlara %10 stopaj önerisi 27 Mart 2026'da torba yasadan çıkarıldı; ayrı bir yasayla geri gelebilir | Önerildi, geri çekildi | [Bloomberg HT](https://www.bloomberght.com/kripto-varliklara-vergi-teklifi-geri-cekildi-3773037) |
| Kriptoya özel vergi yasası yok; genel gelir vergisi hükümleri geçerli. Sürekli alım satım ticari kazanç sayılabiliyor; ara sıra elde edilen kazancın durumu tartışmalı | Belirsiz | [Gökay Gül SMMM](https://gokaygul.com/tr/blog/kripto-varlik-vergilendirme-2026/) |
| Türkiye OECD kripto raporlama çerçevesine (CARF) taahhüt verdi; ilk bilgi değişimini 2028'e kadar yapacak grupta. Yabancı borsa faaliyetleri vergi idaresince görünür hale gelecek | Taahhüt edildi | [Taina](https://www.taina.tech/resources-news-and-awards/48-jurisdictions-commit-to-implement-the-crypto-asset-reporting-framework-carf-by-2027) |
| MASAK düzenlemesiyle Binance TR'de 4 Temmuz 2025'ten itibaren ilk kripto çekimi için 72 saate, sonrakiler için 48 saate kadar bekleme ve stablecoin limitleri | Yürürlükte | [DonanımHaber](https://www.donanimhaber.com/binance-tr-borsasinda-onemli-gelisme--193467) |

**Sisteme yansımaları**

- İlk günden itibaren TL cinsinden eksiksiz bir işlem defteri tutulur (her dolum için o anki USDT/TRY kuru). TL'nin değer kaybı nedeniyle USDT'de yatay bir yıl TL'de vergiye tabi kazanç üretebilir; vergi senaryoları endekslemeli ve endekslemesiz olarak raporlanır.
- Sık yeniden dengeleme, vergi defterini karmaşıklaştırır; kayma bandı ve tampon bunu da azaltır.
- binance.com'un Türkiye'den erişilemez hale gelmesi veya hesapların kapatılması ihtimali için bir plan yapılır (pozisyonları kapatma sırası, fon çıkış yolu).
- Sonuçlar USD ve TL cinsinden ayrıca raporlanır; TL yatırımcı için alternatif getiri (USD faiz, TL mevduat) kıyas olarak gösterilir.

## Claude Code görev listesi

Başlangıç talimatı: "SPEC.md'yi baştan sona oku. G0'dan başla. Her görevin sonunda testleri çalıştır, kabul kriterini raporla ve onayımı bekle. Parametreleri sonuçlara bakarak değiştirme; değişiklik önerin varsa gerekçesini yaz ve bekle. Her çalıştırmayı experiments.md'ye kaydet. Yaptığın her varsayımı kodda ve özette açıkça belirt."

| # | Görev | Girdi → çıktı | Kabul testi |
| --- | --- | --- | --- |
| G0 | Kurulum: depo, `uv.lock`, `settings.yaml` (bu belgedeki tüm parametreler, her biri tek yerde), pytest, `experiments.md` ve `PREREGISTRATION.md` şablonları. Binance erişim testi (imzasız `/ping` + data.binance.vision'dan tek dosya; VPS'te ayrıca imzalı salt okunur çağrı) | → depo, ayarlar | pytest yeşil; her parametre tek yerde tanımlı |
| G1 | Sembol keşfi (S3 listesi, sayfalama). Delist edilmiş sembollerin arşivde olduğunun doğrulanması (FTTUSDT, MATICUSDT, RNDRUSDT, eski LUNAUSDT, BUSD çiftleri). REST'in delist edilmiş sembol için dönüşü. Gerçek dosya sayısı ve boyut tahmini | → `meta/symbols_raw` | Bilinen delist örnekleri bulunur; sonuç raporlanır ve **onay beklenir** |
| G2 | İndirme: 1d (USDT, diğer stablecoin çiftleri, stablecoin/USDT) ve 1h (USDT), 2017-08'den itibaren. Checksum defteri, yeniden deneme, aylık/günlük dosya kuralı | → `data/raw/` | Checksum'lar tutar; tekrar çalıştırmada sadece eksikler iner |
| G3 | Temizleme: ms/µs dönüşümü, tipler, yarım gün işaretleri, coin başına Parquet | → `data/clean/` | Zaman damgası birim testleri; yeniden kurulumda aynı hash |
| G4 | Kalite denetimi: tarihe bağlı işaretler, rapor. Tekrarlanabilirlik ve bağımsız kaynakla çapraz kontrol (rastgele 10 coin × 20 gün REST ile). "Veriden ne öğrendik" sorularının yazılı cevabı | → `quality_flags.parquet`, rapor | Veri T'den sonra kesildiğinde T'ye kadarki işaretler değişmez |
| G5 | Meta tablolar: tipli `symbol_map`, `fee_promotions`, `delist_announcements` (isteğe bağlı). Boşluk ve oran kontrolünün adayları + doğrulanmamış adayların duyurulardan kontrolü | → `meta/*.csv` | Her satırın kaynağı var; **kullanıcı onaylamadan backtest başlamaz** |
| G6 | Evren: max likidite kuralı, stablecoin dönüşümü, 365 gün, dışlamalar, kademeler, zamanlama. Sadece USDT evreni (T7) | → `universe/` | T sonrası veri silindiğinde liste değişmez; meta veri sızıntı testi; aylık evren büyüklüğü raporu |
| G7 | Sinyal ve pozisyon büyüklüğü: tamponlu S, σ ve Σ, bisection, kademe tavanları, yeniden dengeleme kuralları; T1 rejim filtresi bayrak olarak | → `signals`, `targets` | Elle hesaplanmış küçük örneklerle birebir; hedefi 0 olan coinde artık kalmaz |
| G8 | Backtest motoru: VWAP dolum, maliyetler, delist/boşluk kuralları, emir filtreleri, döngü defteri | → `backtests/` | Altı zorunlu testin ilk dördü yeşil |
| G9 | **Ön kayıt:** `PREREGISTRATION.md` doldurulur (hipotez, temel ayar, varyantlar, ızgara, geç/kal, N), işaretlenir ve zaman damgası alınır. Bağımsız kontrol betiği ayrı bir oturumda yazılır | → işaretli commit | Geliştirme sonuçlarından önce tamamlanır |
| G10 | Geliştirme dönemi değerlendirmesi: metrikler, kıyaslar, sıfır hipotezleri, kontroller, bağımsız betiğin karşılaştırması | → rapor | Tohumdan bağımsız; negatif kontroller beklendiği gibi |
| G11 | Geliştirme dönemi sağlamlık ve istatistik: ızgara, PBO, DSR, bootstrap, minimum kayıt uzunluğu, varyantlar T1–T10, uydu payı kuralının hesabı | → rapor | Tüm sonuçlar raporlanır, hiçbiri gizlenmez |
| G12 | Kilit ve doğrulama: veri anlık görüntüsü dondurulur ve özetlenir; toplu çalıştırma doğrulama döneminde bir kez; tam dönem istatistikleri; düşüş ufku tablosu; altın kayıt | → geç/kal kararı | Bir kez çalıştığı kayıtlı |
| G13 | Gölge mod (koşullu): REST günlük veri, anlık görüntüler, orderbook ölçümleri, Demo Mode ile emir akışı, BTC-200 paralel, ölü adam sinyali, SQLite kaydı, yedekleme, acil durdurma testi | → 6–8 haftalık kayıt | Canlıya geçiş kriterleri |
| G14 | Canlı (Aşama 2; Binance durumu netleşince ve yazılı hukuki/vergi görüşü alınınca): çifte emir önleme, mutabakat, üç modlu acil durdurma, delist izleme, olay protokolü, TL defteri, anahtar yönetimi, durdurma kuralları | → canlı sistem | Durdurma kuralları izleniyor; 12 aylık ileriye dönük test sürüyor |

## Açık sorular ve doğrulanmamış noktalar

| Konu | Durum | Nerede çözülür |
| --- | --- | --- |
| Delist edilmiş coinlerin arşivde durup durmadığı | **En kritik açık nokta**; hiçbir inceleme doğrudan test edemedi | G1 |
| S3 listeleme uç noktasının çalışıp çalışmadığı | Belgelenmemiş; açık kaynak araçlarda kullanılıyor | G1 |
| Toplam sembol sayısı, dosya sayısı, süre ve boyut | Tahmin | G1–G2 |
| 2019–2020 evren büyüklüğü | Tahmin: 15–30 coin | G6 |
| BTT→BTTC kesin tarihi; doğrulanmamış diğer token dönüşümleri | Ay biliniyor, gün değil | G5 |
| Sıfır komisyon kampanyası çiftlerinin tam listesi ve tarihleri | Ana kampanya biliniyor; tam liste duyurulardan çıkarılacak | G5 |
| Türkiye'de ikamet eden bir hesabın AB IP'li bir VPS'ten API kullanımı | Doğrulanmadı | G0 (VPS'te imzalı çağrı) |
| IP kısıtlaması olmayan API anahtarlarının silinip silinmediği | Sadece üçüncü taraf kaynağı; zaten IP kısıtlaması kullanılıyor | — |
| Binance TR çekimlerinin yeniden açılışı, Binance ihlalinin nihai sonucu | 2 Kasım 2026 itibarıyla belirsiz | Aşama 2 öncesi |
| Bireyin binance.com kullanımının hukuki durumu, kazançların vergilendirmesi | Belirsiz | Avukat ve mali müşavir görüşü |
| Gerçek veride maliyet ve ciro | Simülasyonda yılda %4–14; gerçek trendli veride daha düşük bekleniyor | G10–G11 |

**Kârlılık turunda değerlendirilip reddedilen veya ertelenen fikirler**

| Fikir | Karar | Gerekçe |
| --- | --- | --- |
| Funding arbitrajı (spot al + vadeli sat) | Red | 2026'da yıllık getirisi yaklaşık %2–3, hazine bonosunun altında. Asıl sorun zamanlaması: getiri trend sistemi zaten yatırımdayken yüksek, nakitteyken sıfıra yakın. Çapraz teminat için 100.000 USDT gerekiyor |
| Binance Simple Earn ile boş USDT'ye getiri | Ertelendi | Yılda +%1–2,5 katkı sağlayabilir ama borç verme ve borsa riski ekler; Binance ihlal sonrası rezerv kanıtı yayımlarsa ve ancak ön kayıtlı bir operasyonel deney olarak |
| Tokenize hazine bonoları, USDe | Red | Bireysel yatırımcıya kapalı veya yüksek risk (USDe 10 Ekim 2025'te 0,65'e indi) |
| Tutulan ETH/SOL'u stake etmek | Red | Katkısı yılda yaklaşık %0,03; kilitler tam ve aynı gün çıkışı geciktirir; likit staking tokenleri evren dışı |
| Düşüş trendinde short (vadeli işlem) | Ertelendi | Kanıt zayıf, 2026'da negatif funding ve sıkışma riski. Sadece araştırma: ileride geçmiş funding verisiyle BTC'de ön kayıtlı bir deney |
| Kripto dışı dilimler (PAXG, bStocks) | Red | BTC–altın korelasyonu Eylül 2026'da 0,86; ek ihraçı riski; geçmiş veri yok. Çeşitlendirme sistem dışı sermayeyle yapılır |
| Düşüş kontrolü katmanları (CPPI, kademeli küçültme) | Red | Simülasyonda büyümeyi yılda 2,8–8 puan düşürdü, Sharpe'ı artırmadı; sadece sabit düşük maruziyetle eşdeğer |
| Daha yüksek oynaklık hedefi (%45–60) | Red | Sadece güçlü trendli senaryoda büyüme sağladı, düşüşü her adımda yaklaşık 8 puan artırdı. %35 hedef gerçekte yaklaşık %25 oynaklık üretiyor, bu da yarım Kelly civarında |
| "50 coin arasından en güçlü 10" | Red (T9 ile örtüşüyor) | Aynı kesitsel seçim fikri; ciro 1,5 kat; 2 kat maliyette kazanç büyük ölçüde kayboluyor |
| Alt-coin sezonu filtresi (ETH/BTC trendi) | Red | 2014'ten beri yaklaşık 4 alt-coin sezonu, geliştirme döneminde 1–2 tane; T9 aynı işi aşağıdan yukarı yapıyor |
| Sürekli sinyal, trend kalitesi, hacim teyidi, sıçrama filtresi | Red | Kanıt zayıf veya ters yönde (kriptoda yüksek günlük getiri sonraki haftayı olumlu yorduyor); her biri yeni serbest parametre |
| USDC çiftleri, VIP seviyeleri, işlem saati değişikliği | Red | Bu sermaye büyüklüğünde yılda 0–0,1 puan |

**Dürüst değerlendirme (kırmızı takım incelemesinden):** alt-coin sisteminin önümüzdeki yıllarda maliyetler sonrası BTC-200 kuralını Sharpe'ta yenme olasılığı yaklaşık %30–40 olarak tahmin edildi; bunu iki yıl içinde istatistiksel güvenle gösterme olasılığı %10'un altında. Trend takibinin kriptodaki asıl faydası büyük düşüşlerden kaçınmaktır ve bunu BTC tek başına da sağlar. Alt-coin çeşitliliği en çok 2017–2021'in düşük korelasyonlu döneminde işe yaradı. Bu yüzden plan, basit kıyası ana yol, alt-coin sistemini kanıtlanana kadar küçük bir ek olarak görür. Bu bir tahmindir, kesin bir ölçüm değildir.

## Kaynaklar

**Veri ve API**

- [Binance Public Data (resmî depo)](https://github.com/binance/binance-public-data)
- [Binance spot API: sadece piyasa verisi uç noktası](https://developers.binance.com/docs/binance-spot-api-docs/faqs/market_data_only)
- [Binance Spot Demo Mode](https://developers.binance.com/docs/binance-spot-api-docs/demo-mode/general-info)
- [Delist edilen çiftlerin API'de erişilebilirliği (Binance geliştirici forumu)](https://dev.binance.vision/t/trade-history-of-delisted-pairs/8973)
- [BNXUSDT 1d arşiv boşluğu (Binance geliştirici forumu)](https://dev.binance.vision/t/missing-data-in-binances-bnxusdt-1d-klines/15877)
- Binance token dönüşüm duyuruları: [RNDR→RENDER](https://www.binance.com/en/support/announcement/d1f2ae8d99b24439a7a900caa9bb6b3b), [MATIC→POL](https://www.binance.com/en/support/articles/6a6de383727f4659a3050f7982e1620f), [FTM→S](https://www.binance.com/en/support/announcement/aec6fcbc84b749eeab6690e6bcac2f3d), [EOS→A](https://www.binance.com/en/support/announcement/1e89a9ca957c4b0ca7502e60b993e201), [BNX→FORM](https://www.binance.com/en/support/announcement/2f963977c7274e0583f16f2e26987b61), [ERD→EGLD](https://www.binance.com/en/support/articles/24feffc4fccf446f9c97fe527cf379be), [LUNC/BUSD](https://www.binance.com/en/support/announcement/c52fa3c686be4b2b9d5df50de15847ec)
- [OCEAN ve AGIX → FET (BeInCrypto)](https://beincrypto.com/binance-to-delist-ai-cryptos-ocean-agix/)
- [Eski LUNA/USDT'nin kaldırılması (Decrypt)](https://decrypt.co/100290/binance-halts-trading-terra-delists-luna-ust)
- [Sıfır komisyon kampanyasının sonu (FXStreet)](https://www.fxstreet.com/cryptocurrencies/news/binance-ends-zero-fee-trading-for-btc-pairs-202303230217), [Sıfır komisyon hacmi (Kaiko)](https://www.kaiko.com/resources/the-impact-of-binances-zero-fee-volume)
- [10 Ekim 2025 iğneleri (CoinDesk)](https://www.coindesk.com/markets/2025/10/12/binance-to-compensate-users-affected-by-crash-in-wbeth-bnsol-and-ethena-s-usde)
- [Kaldıraçlı tokenlerin kapatılması (Cointelegraph)](https://cointelegraph.com/news/binance-leveraged-token-services-shutdown)

**Yöntem ve araştırma**

- [The Deflated Sharpe Ratio (Bailey ve López de Prado)](https://papers.ssrn.com/abstract=2460551)
- [The Probability of Backtest Overfitting (Bailey vd.)](https://papers.ssrn.com/abstract=2326253)
- [A Trend Factor for the Cross Section of Cryptocurrency Returns (JFQA, 2025)](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178)
- [Timing Bitcoin with SMAs (CXO Advisory)](https://www.cxoadvisory.com/currency-trading/timing-bitcoin-with-smas/)
- [Position Sizing in Trend Following (Concretum Group)](https://concretumgroup.com/position-sizing-in-trend-following-comparing-volatility-targeting-volatility-parity-and-pyramiding/)
- [Binance listelemelerinin getirisi (CryptoSlate / Animoca)](https://cryptoslate.com/tokens-display-up-to-negative-70-median-returns-after-cex-listing-animoca-research/)

**Güncel durum ve hukuk**

- [Binance güvenlik ihlali (Kuwait Times)](https://kuwaittimes.com/article/52684/business/crypto-exchange-binance-confirms-63-billion-hack-freezes-half/), [aşamalı çekim açılışı (CoinDesk)](https://www.coindesk.com/markets/2026/11/01/binance-opens-crypto-withdrawals-in-phases-starting-with-bitcoin-following-usd6-3-billion-hack)
- [Binance TR çekim durdurma (Paratic)](https://paratic.com/binance-trde-kripto-para-cekimleri-durduruldu-kullanici-varliklari-guvende-mi/)
- [SPK duyurusu, 7518 sayılı Kanun](https://spk.gov.tr/duyurular/basin-duyurulari/2024/kripto-varlik-hizmet-saglayicilara-iliskin-duyuru_02072024)
- [SPK geçici liste (TechInside)](https://www.techinside.com/spk-kripto-listesi-2026/)
- [Vergi teklifinin geri çekilmesi (Bloomberg HT)](https://www.bloomberght.com/kripto-varliklara-vergi-teklifi-geri-cekildi-3773037)
- [Kripto vergilendirme 2026 (Gökay Gül SMMM)](https://gokaygul.com/tr/blog/kripto-varlik-vergilendirme-2026/)
- [CARF taahhütleri (Taina)](https://www.taina.tech/resources-news-and-awards/48-jurisdictions-commit-to-implement-the-crypto-asset-reporting-framework-carf-by-2027)

**İnceleme dosyaları:** dört inceleme raporu ve hesap denetimi simülasyonları, bu çalışma ortamında `spec_review/` altında tutuldu (math\_audit, consistency, factcheck, redteam).
