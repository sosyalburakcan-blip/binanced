# Ön kayıt (PREREGISTRATION.md)

> **Durum: DONDURULDU (2026-11-03).** Bu belge SPEC.md v3'ün "Ön kayıt" ve "Değerlendirme" bölümlerinden
> birebir derlendi ve geliştirme döneminin hiçbir strateji sonucu görülmeden kullanıcı tarafından onaylandı.
> Bundan sonra bu dosyada, `settings.yaml`'da veya `meta/symbol_map.csv`'de yapılan her değişiklik
> `experiments.md`'ye bir deneme olarak yazılır ve N'ye eklenir.

## Dondurma kaydı (G9'da doldurulur)

| Alan | Değer |
| --- | --- |
| Dondurma tarihi (UTC) | _doldurulacak_ |
| Kod commit'i | _doldurulacak_ |
| İmzalı git tag'i | _doldurulacak_ (`git tag -s prereg-v1`; bu makinede GPG anahtarı yok, kullanıcı oluşturur) |
| `settings.yaml` SHA-256 | _doldurulacak_ |
| `meta/symbol_map.csv` SHA-256 (kullanıcı onaylı) | _doldurulacak_ |
| Bu dosyanın SHA-256'sı | Dondurmadan sonra hesaplanır ve üçüncü bir yere (ör. kendinize e-posta) zaman damgasıyla gönderilir |

## 1. Birincil hipotez (tek)

> Kilitli alt-coin trend sistemi (temel ayar T0), geliştirme + doğrulama döneminin tamamında (2019-07 – kilit
> tarihi), maliyetler sonrası risksiz faiz üzerindeki Sharpe oranında **BTC 200 günlük ortalama temel kıyasını**
> eşleştirilmiş durağan blok bootstrap ile tek yönlü %95 güvenle yener.

- **BTC-200:** BTC günlük kapanışı 200 günlük basit ortalamanın üstündeyse %100 BTC, altındaysa %100 nakit.
  Aynı dolum, aynı maliyet, nakitte aynı getiri varsayımı. Histerezis yok.
- **Reddedilirse:** varsayılan karar BTC-200'dür (veya hiç işlem yapmamak). Alt-coin sistemi en fazla aşağıdaki
  uydu payı kuralıyla küçük ve tavanlı bir ek dilim olabilir.
- **Sharpe:** ABD 3 aylık hazine bonosu (FRED DTB3) üzerindeki getiriyle, yıllıklandırma √365.
- **Nakit getirisi:** temel varsayım %0. Birincil hipotez bu varsayımla geçilmelidir. Duyarlılık:
  max(0, hazine bonosu − 1,5 puan) ve tam hazine bonosu. Her strateji için zaman ağırlıklı nakit payı ve nakit
  kaybı raporlanır.

## 2. Dönemler

| Dönem | Aralık | Kullanım |
| --- | --- | --- |
| Isınma | 2017-08 – 2019-06 | Sadece gösterge geçmişi; sonuç raporlanmaz |
| Geliştirme | 2019-07 – 2023-12 | Hata ayıklama, sağlamlık, PBO, sıfır hipotezleri |
| Doğrulama | 2024-01 – kilit tarihi | Kilitten sonra bir kez çalıştırılır; gerçek bir test değildir |
| İleriye dönük test | Kod dondurulduktan sonra en az 12 ay | Tek gerçek test; sistem ve BTC-200 gölge modda yan yana |

Tüm sonuçlar iki rejim için ayrıca raporlanır: 2019-07 – 2021-11 ve 2022-01 sonrası.

## 3. Temel ayar ve varyantlar

Parametrelerin tamamı `settings.yaml`'dadır (SHA-256 yukarıda). Özet:

| Kod | Varyant | Rol |
| --- | --- | --- |
| T0 | Tamponlu sinyal (h = 0,5; vadeler 20/50/100), haftalık giriş + günlük çıkış, 20 coinlik evren, rejim filtresi yok, VWAP 00–02 dolum, nakitte %0 getiri, oynaklık hedefi %35, brüt ≤ 1, tavanlar %10/%5/%3 | Birincil |
| T1 | T0 + BTC rejim filtresi (0,97/1,03 × SMA200 histerezisli) | İkincil |
| T3 | T0, dolum t+1 açılışında (iyimser) | Duyarlılık |
| T4 | T0, dolum VWAP 06–07 ve VWAP 14–15 UTC | İşlem saati seçimi |
| T5 | T0, delist cezası %20 ve %50 | Stres |
| T6 | T0, maliyetler ×2; borsadaki varlığın tek seferde %20 ve %50 kaybı | Stres |
| T7 | T0, sadece USDT hacmiyle kurulan evren | Sağlamlık |
| T8 | T0, günlük mum 04/08/12/16/20 UTC kapanışlı; haftalık giriş gününün diğer 6 güne kaydırılması (raporlanır, seçilmez) | Zamanlama şansı |
| T9 | T0 + Bitcoin'e göre güç filtresi (30 gün, üçte birlik dilimler, −%5 histerezis) | İkincil |
| T10 | %80 BTC-200 + %20 T0 ve %50 + %50; aylık yeniden dengelenir | Tanı |

## 4. Parametre ızgarası (tümü raporlanır, en iyisi seçilmez)

| Parametre | Temel | Komşular |
| --- | --- | --- |
| Portföy oynaklık hedefi | %35 | %25, %45 |
| Vadeler (birlikte) | 20/50/100 | ×0,8 ve ×1,2 |
| Evren büyüklüğü | 20 | 30, 50 |
| Kayma bandı | %25 | %15, %35 |
| Tampon h | 0,5 | 0, 1,0 |

## 5. Deneme sayısı (DSR için N)

N = `experiments.md`'deki tüm denemeler + ızgara boyutu + varyantlar; **alt sınır 100**. Ön kayıttan sonra yapılan
her değişiklik `experiments.md`'ye tarih, gerekçe ve sonuçla yazılır ve N'ye eklenir. Doğrulama dönemi bir kez
çalıştırıldıktan sonra değişiklik yapılırsa o dönem artık doğrulama sayılmaz.

## 6. Uydu payı kuralı (birincil hipotez reddedilirse)

Alt-coin sistemi portföye yalnızca `0,5 × SR_T0_net > ρ × SR_BTC200_net` ise **%20** pay ile girer, aksi halde **%0**.
SR'ler tam dönem net Sharpe, ρ iki stratejinin günlük getiri korelasyonu. Takdire dayalı artırım yapılmaz.

## 7. İstatistiksel yöntemler

- Deflated Sharpe (Bailey ve López de Prado), N yukarıdaki gibi.
- PBO (CSCV) parametre ızgarası üzerinde.
- Durağan blok bootstrap: ortalama blok 30 gün, 10.000 yol, sabit tohum (`settings.yaml: evaluation.bootstrap.seed`).
- Sıfır hipotezleri (a) tarih karıştırma ve (b) maruziyet yolu korunarak rastgele coin; her biri 1.000 çalıştırma,
  sabit tohum, p = (1 + sıfır ≥ gözlenen) / 1.001.
- Minimum kayıt uzunluğu; düşüş ufku tablosu (30/60/90/180/365 gün, %95'lik).
- Negatif/pozitif kontroller: SPEC "Negatif ve pozitif kontroller" tablosu. Negatif kontrollerde avantaj
  kaybolmuyorsa diğer tüm sonuçlar geçersiz sayılır.

**Sıralama:** ızgara, sıfır hipotezleri, kontroller, PBO ve DSR önce yalnızca geliştirme döneminde çalışır.
Kilitte, önceden kaydedilmiş tüm toplu çalıştırma doğrulama döneminde bir kez yapılır; ardından tam dönem PBO,
DSR ve birincil hipotez testi raporlanır. Bundan sonra değişiklik yapılmaz.

## 8. Geç/kal kriterleri

Kriter 1 sistemin rolünü belirler; 2–9 alt-coin sisteminin Aşama 2'ye geçmesi için zorunludur.

1. Birincil hipotez: tam dönemde BTC-200'ü Sharpe'ta eşleştirilmiş bootstrap ile %95 güvenle yener. Geçmezse
   alt-coin sistemi en fazla küçük bir ek dilimdir; ana pozisyon BTC-200'dür.
2. Tam dönem DSR ≥ 0,95.
3. Geliştirme döneminde PBO < 0,5.
4. Doğrulama döneminde net Sharpe > 0, hem 1× hem 2× maliyetle.
5. Her iki sıfır hipotezini Sharpe'ta %95 düzeyinde geçer.
6. Bootstrap medyan en büyük düşüşü, evren eşit ağırlıklı al-tutun yarısından küçük (eşleştirilmiş örnekleme).
7. Tüm komşularda net Sharpe > 0 ve temel ayarın en az %50'si.
8. Tüm negatif kontroller beklendiği gibi.
9. %20 delist cezasıyla net Sharpe > 0.

## 9. Beklenti aralığı (hedef değil)

Gerçekçi net Sharpe aralığı 0,3–0,8. Canlı sonuçların bu aralığın dışına çıkması bir uyarı işaretidir, parametre
değiştirme gerekçesi değildir.

## 10. Uygulama varsayımları (kodda da belirtilir)

`CONTRACTS.md` zaman kuralı, evren zamanlaması ve veri biçimleri bu ön kaydın parçasıdır. SPEC'in açık bıraktığı
yerlerde verilen kararlar aşağıdadır; hepsi kodda da yorum olarak yazılıdır. **Kullanıcı 2026-11-03'te
onayladı.**

**Kullanıcı onayıyla kesinleşenler**

- `meta/symbol_map.csv` 43 satırıyla olduğu gibi (hepsi `verified=yes`). NPXS→PUNDIX satırındaki son işlem
  saati tablodaki gibi bırakıldı; kesimden sonra hacmi olan mumlar zaten tutulduğu için sınırı veri belirler.
- `meta/fee_promotions.csv` yalnızca hem maker hem taker komisyonunun sıfır olduğu kampanyaları içerir;
  yalnızca maker komisyonunun sıfır olduğu kampanyalar dahil değildir.

**Dondurmadan önce bilinen veri gerçekleri (strateji sonucu değil)**

- Evren 2019–2020'de medyan 10 coin (en az 3), geliştirme döneminin ilk ayı 2019-07'de 9 coin; 2021'den
  itibaren her ay 20. Parametre değiştirilmedi.
- T7 evreni ana evrenle her ay aynı (USDT hacmi her gün diğer stablecoin çiftlerinden büyük). T7 yine de
  çalıştırılır ve raporlanır; bilgi taşımadığı not edilir.

**Veri ve kalite**

- Yarım gün işareti her işlem diliminin ilk ve son mumunu kapsar (ilk mum, kesik `close_time`'lı mum, kesikten
  sonra gelen ilk mum, çift gerçekten bittiyse son mum). Aktif çiftin en yeni mumu yarım gün sayılmaz.
- Tekrar eden `open_time`: ilk satır tutulur (aylık > günlük dosya önceliği), çelişenler `duplicate_open_time` hatası.
- Kalite işaretleri gün başına bir satırdır; sıfır hacim dizisinin ilk iki günü üçüncü günde bilinir; boşluk,
  seri yeniden başladığı gün bilinir. Temiz gün = bar var, yarım gün değil, `error`/`exclude` işareti yok.
- Sembol haritasında yalnızca `verified=yes` satırlar uygulanır.

**Evren**

- 365 temiz gün kümülatiftir (ardışık olması gerekmez); T günündeki yarım gün işareti yok sayılır.
- Likiditede barı olmayan gün 0 sayılır; USDT çifti kampanyadayken de sayılır; stablecoin kapanışı en fazla 7 gün
  geriye taşınır.
- Kademe: A = BTC/ETH sıralarından bağımsız; diğerleri ham sıraya göre ≤ 20 → B, 21–50 → C.
- Stablecoin yedek kontrolünden BTC ve ETH muaftır.

**Strateji**

- Tampon durum makinesi coinin 200. geçerli barında tamponsuz kuralla başlar ve evren üyeliğinden bağımsız işler.
- EMA yalnızca geçerli kapanışlarla hesaplanır, boşlukta dondurulur; boşluğu aşan getiri σ'ya girmez; std ddof=1.
- Oynaklık penceresinin en az gözlem şartı sağlanmazsa o bileşenin son geçerli değeri taşınır; hiç yoksa coin
  ağırlık almaz.
- Korelasyon: çift bazında eksik veriye dayanıklı, sıfır ortalamalı EWMA; ortak gözlem < 60 ise çift aktif kümenin
  ortalama korelasyonuyla doldurulur; hiç bilinen çift yoksa 1 (kötümser); PSD değilse özdeğerler 0'a kırpılır.
- "Artıran/azaltan" işlem Δ'nın işaretiyle belirlenir. −%35 sert sınırdayken bant alımları dahil tüm artırımlar durur.
- T1: SMA200 oluşmadan rejim KAPALI. T9: kapı durumu coin adaydan düşünce sıfırlanır.

**Motor**

- Komisyon nakit olarak gerçekleşen tutardan alınır; T6 ×2 komisyon, kayma ve delist cezasını birlikte çarpar.
- Delist kapanışı: dolum penceresi VWAP'ı, yoksa günlük VWAP, o da yoksa son kapanış; × (1 − ceza), üstüne komisyon.
- Dolum yapılamayan emir düşer, ertesi günün kararı yeniden üretir. Orantılı küçültme dolum anındaki fiyatlarla.
- 10 USDT altı tam çıkış artığı sıfır değerle silinir; çıkış dışı emirlerde 10 USDT filtresi karar anında uygulanır.
- Kıyaslarda sert sınır yoktur; T10 dilimleri arası aktarım maliyetsiz sayılır.
- T6 borsa kaybı günü **2022-11-08** (FTX çöküşü), sonuç görülmeden seçildi (`backtest.stress.exchange_loss_date`).
  Kayıp o gün borsadaki tüm varlığa (nakit + coin) uygulanır; −%35 sert sınırı tetiklenirse motor normal kuralla
  davranır. Doğrulama döneminde bu tarih yoktur; T6 kaybı geliştirme ve tam dönemde raporlanır.

**Değerlendirme**

- Birincil test p = (1 + #{ΔSR* ≤ 0}) / (B + 1) (yüzdelik yöntemi, tek yönlü).
- Hazine bonosu: günlük oran = y/100/365, 1 gün gecikmeli, yalnızca ileri taşınır, 10 günden bayatsa eksik.
- Düşüş ufku tablosu: her bootstrap yolunun ilk h günü. PBO: CSCV, S = 16.
- "Sistemin hâlâ anlamlı kaldığı yıllık beklenen kayıp oranı" (T6): yılda p olasılıkla L kadar (L = %20, %50)
  kayıp, yıllık log getiriyi beklentide p·(−ln(1 − L)) azaltır. Raporlanan p*, T0'ın maliyetler sonrası yıllık
  ortalama aşırı log getirisini sıfıra (ve ayrıca BTC-200'ün düzeyine) indiren değerdir.
- Bağımsız kontrol betiği (SPEC madde 6) G10'dan önce, motor kodunu görmemiş ayrı bir oturumda yalnızca SPEC'ten
  yazılır ve `independent/` altına konur; G10'da sinyaller ve tek coinlik getiri motorla karşılaştırılır.
