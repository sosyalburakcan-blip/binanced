# Ön kayıt v2 — trend takibi dışındaki aday stratejiler

> **Durum: DONDURULDU (2026-11-03, tag `prereg-v2`), gerçek veride hiçbir aday çalıştırılmadan.** Kullanıcı 2026-11-03'te
> trend takibi dışında yeni strateji denenmesini istedi ve tam yetki verdi. Parametreler `research_v2.yaml`'da.
> Bu belgeden sonra yapılan her değişiklik `experiments.md`'ye yazılır ve N'ye eklenir.

## 1. Neden ve dürüstlük notu

v1 (PREREGISTRATION.md, G12) alt-coin trend sistemini reddetti; karar BTC-200. v2 aynı veriyle yeni bir hipotez
ailesi dener. **Bu veride gerçek örneklem dışı dönem kalmadı:** 2024-01 – 2026-11 doğrulama dönemi G12'de
harcandı ve piyasanın genel seyri (BTC yükseldi, alt-coinler düştü) biliniyor. Bu yüzden:

- 2024-01 – 2026-11 bu ön kayıtta **kirlenmiş bekletme dönemi**dir: adayların kendi sonuçları görülmedi ama dönemin
  karakteri biliniyor. Burada geçmek gerekli ama yeterli değildir.
- Adaylar ve parametreler literatürdeki standart tanımlardan, dönem sonuçlarına bakılmadan seçildi; ızgara
  temel + tek eksenli komşulardır ve hepsi raporlanır.
- Tek gerçek test ileriye dönük gölge moddur (en az 12 ay).
- N, v1'in tüm denemelerini ve v2'nin tüm adaylarını içerir (§6).

## 2. Dönemler

| Dönem | Aralık | Kullanım |
| --- | --- | --- |
| Isınma | 2017-08 – 2019-06 | Gösterge geçmişi |
| Tasarım | 2019-07 – 2023-12 | PBO, sıfır hipotezleri, kontroller |
| Kirlenmiş bekletme | 2024-01 – 2026-11-01 | Sharpe > 0 şartı (1× ve 2× maliyet) |
| Tam | 2019-07 – 2026-11-01 | Birincil test, DSR, komşular, uydu payı |

Veri G12 anlık görüntüsüdür (`lock/LOCK.json`, kilit tarihi 2026-11-01); değişmez.

## 3. Aday aileler (trend takibi değil)

| Kod | Aile | Kural (temel ayar) | Komşular |
| --- | --- | --- | --- |
| XS_REV | Kesitsel kısa vadeli geri dönüş | Evrende (20 coin) son 7 günün en çok düşen 5 coini; 1/σ ağırlık, portföy oynaklığı %35'e ölçekli; 7 günde bir | geriye bakış 3, 14; coin sayısı 3, 10; sıklık 3, 14 gün |
| XS_LOWVOL | Düşük oynaklık anomalisi | Evrende 60 günlük oynaklığı en düşük 5 coin; aynı boyutlandırma; ay sonu | pencere 30, 120; coin sayısı 3, 10 |
| VM_BTC | Oynaklığa göre yönetilen BTC (Moreira–Muir) | BTC ağırlığı min(1, %50 / σ̂₃₀); bant %20 | hedef %35, %65; pencere 14, 60 |
| MR_BTC | BTC kısa vadeli geri dönüş | z = (C − SMA₂₀)/σ₂₀ < −2 → %100 BTC; z ≥ 0 veya 20 gün sonra çık | pencere 10, 40; giriş z 1,5, 2,5 |
| RV_ETHBTC | ETH/BTC oran geri dönüşü | log(ETH/BTC)'nin 90 günlük z'si < −1 → %100 ETH, > 1 → %100 BTC, arada 50/50 | pencere 45, 180; z bandı 0,5, 1,5 |

Toplam 5 temel + 22 komşu = 27 aday. Ayrıntılı tanımlar ve nedensellik `src/trend/alt/` modül notlarında.

## 4. Yürütme (tüm adaylar)

- v1 motoru değişmeden: t kapanışında karar, t+1 VWAP 00–02 UTC dolum, v1 komisyon/kayma/delist/boşluk kuralları,
  nakitte %0 getiri, Sharpe hazine bonosu üzerinden √365.
- Ortak karar verici `trend.alt.base.AltStrategy`: yeniden dengeleme takvimi, bant, MINTRADE, delist → 0, evren
  dışı → 0 (kesitsel), brüt ≤ 1.
- Kesitsel adaylarda sepet yeniden dengeleme gününde seçilir ve bir sonrakine kadar tutulur; arada yalnızca delist
  ve evrenden çıkış satılır.
- Kesitsel adaylarda v1 kademe tavanları (%10/%5/%3) **uygulanmaz**: N = 5'te brüt maruziyeti %25–37'ye kilitliyor
  ve ailenin kendi kuralını test etmeyi engelliyordu. Tek coin ağırlığını oynaklık hedefi (%35) ve brüt ≤ 1 sınırlar;
  evren zaten en likit 20 coin. (Her iki karar da aile sınıfları sentetik veride denenirken, gerçek veri sonucu
  görülmeden alındı.)
- **Sert sınır yok.** v1'de −%35 sınırı nakit %0 iken kalıcı kilitlenmeye yol açtı; v2 adayları sınırsız çalışır,
  risk kuralı canlıda düşüş ufku tablosundan kurulur. (Bu seçim v1 sonucundan öğrenildi ve burada açıkça yazılı.)

## 5. Kıyaslar

BTC-200 (birincil), BTC al-tut, %50 BTC + %50 ETH (aylık dengelenen), evren eşit ağırlıklı al-tut, v1 T0.

## 6. Geç/kal kriterleri (her aile için temel ayarla)

1. **Birincil:** tam dönemde BTC-200'ü net Sharpe'ta eşleştirilmiş durağan blok bootstrap ile yener; tek yönlü
   p < 0,05 / 5 = 0,01 (Bonferroni, 5 aile).
2. **DSR ≥ 0,95** (tam dönem); N = max(100, experiments.md'de N'ye eklenen satırlar + v1 ızgara/varyant 35 +
   v2 aday 27); deneme Sharpe varyansı v2 adaylarının tam dönem Sharpe'larından.
3. **Tasarım ve bekletme dönemlerinin ikisinde de** net Sharpe > 0, hem 1× hem 2× maliyetle.
4. **PBO < 0,5** aile ızgarasında, tasarım döneminde (CSCV, S = 16).
5. **Sıfır hipotezleri** (tasarım, 1.000'er, sabit tohum, p = (1 + #{sıfır ≥ gözlenen}) / 1.001 < 0,05; v1'in
   basitleştirilmiş getiri hesabı): kesitsel ailelerde tarih karıştırma ve rastgele coin (v1 ile aynı). Tek varlıklı
   ailelerde (VM, MR, RV) döngü yapısı anlamsız olabildiği için (VM hep yatırımda) **dairesel kaydırma**: günlük
   ağırlık yolu rastgele bir gün sayısı (30 … T−30) kadar dairesel kaydırılır; maruziyet dağılımı ve kalıcılığı
   korunur, zamanlama bozulur.
6. **Kontroller** (tasarım): 365 gün gecikmeli sinyal → Sharpe ≤ temelin %50'si (temel > 0 ise); 1 gün sızıntı →
   Sharpe ≥ temel + 1; ortalamadan arındırılmış karıştırma ve GARCH (5'er tohum) → ortalama yıllık getiri < 0 ve
   Sharpe ≤ 0. (v1 tanısı: SPEC'in karıştırma kontrolü coin kaymasını koruduğu için uzun pozisyonlu sistemlerde
   sıfır değildir; v2'de arındırılmış sürüm kullanılır.)
7. **Komşular** (tam dönem): hepsinde Sharpe > 0 ve ≥ temelin %50'si.

**Karar:** 1–7'nin hepsini geçen aile gölge mod adayıdır. Hiçbiri geçmezse BTC-200 kararı sürer. 1'i geçmeyip
2–7'yi geçen ve v1 uydu kuralını (0,5 × SR_aile > ρ × SR_BTC200) sağlayan aile, BTC-200'ün yanında en fazla %20'lik
uydu dilimi adayıdır. Takdire dayalı artırım, aileler arası "en iyiyi seçme" veya sonradan parametre değişikliği yok.

## 7. Uygulama ve bağımsız kontrol

Aile sınıfları sentetik veriyle test edilerek yazıldı (nedensellik: t sonrası veri bozulunca t'ye kadarki kararlar
aynı). Gerçek veride toplu çalıştırma ön kayıt dondurulduktan sonra bir kez yapılır. Geçen bir aile olursa sinyali
ve tek varlıklı getirisi motoru görmemiş ayrı bir ajan oturumunda bu belgeden yeniden hesaplanır.
