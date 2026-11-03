# Ön kayıt v3 — kısa vadeli trend (günlük, 2–3 günlük, haftalık)

> **Durum: DONDURULDU (2026-11-03, tag `prereg-v3`), gerçek veride hiçbir aday çalıştırılmadan.** Kullanıcı
> 2026-11-03'te günlük, 2–3 günlük ve haftalık trendin denenmesini istedi. Parametreler `research_v3.yaml`'da.
> Bu belgeden sonra yapılan her değişiklik `experiments.md`'ye yazılır ve N'ye eklenir.

## 1. Neden ve dürüstlük notu

v1 orta vadeli trendi (20/50/100 günlük ortalamalar) alt-coinlerde denedi ve reddetti. v2 trend dışı beş aileyi
denedi ve hepsini reddetti. v3 daha kısa ufukları ve v1'den çıkan dersle **BTC'yi** dener:

- Aynı veri; 2024-01 – 2026-11 **kirlenmiş bekletme** dönemidir (v2 §1 ile aynı gerekçe).
- Bu üçüncü araştırma. N, v1 ve v2'nin tüm denemelerini içerir (§5). Burada geçen bir kural bile yalnızca gölge mod
  adayıdır.
- Kısa ufuklu kurallar sık işlem yapar; v1 maliyetleri (komisyon, kayma) aynen uygulanır.

## 2. Dönemler

v2 ile aynı: tasarım 2019-07 – 2023-12; kirlenmiş bekletme 2024-01 – 2026-11-01; tam dönem 2019-07 – 2026-11-01.
Veri G12 anlık görüntüsü (`lock/LOCK.json`).

## 3. Aday aileler

| Kod | Aile | Kural (temel ayar) | Komşular |
| --- | --- | --- | --- |
| TS_D | BTC günlük trend | Son 1 günün BTC getirisi > 0 → %100 BTC, değilse nakit; her gün karar | 2 ve 3 günlük getiri |
| TS_W | BTC haftalık trend | Son 7 günün BTC getirisi > 0 → %100 BTC; haftada bir karar (giriş ve çıkış) | 14 ve 28 günlük getiri |
| XS_MOM | Kesitsel haftalık momentum | Evrende (20 coin) son 7 günde en çok yükselen 5 coin; 1/σ ağırlık, portföy oynaklığı %35; 7 günde bir | geriye bakış 3, 14; coin sayısı 3, 10; sıklık 3, 14 gün |

Toplam 3 temel + 10 komşu = 13 aday. Tanımlar `src/trend/alt/tsmom.py` modül notunda. XS_MOM, v2'deki XS_REV ile
aynı yürütmeyi kullanır; tek fark seçim yönüdür (en çok düşen yerine en çok yükselen).

## 4. Yürütme

v2 §4 ile aynı: t kapanışında karar, t+1 VWAP 00–02 UTC dolum, v1 maliyetleri, nakit %0, **sert sınır yok**,
kesitsel ailede kademe tavanı yok ve sepet yeniden dengelemeler arasında tutulur. TS ailelerinde tam giriş / tam
çıkış; TS_W'de çıkış da yalnızca haftalık karar gününde.

## 5. Geç/kal kriterleri (her aile için temel ayarla)

v2 §6 ile aynı yedi kriter; farklar:

1. **Birincil:** tam dönemde BTC-200'ü net Sharpe'ta eşleştirilmiş bootstrap ile yener; tek yönlü
   p < 0,05 / 3 ≈ 0,0167 (Bonferroni, 3 aile).
2. **DSR ≥ 0,95**; N = max(100, experiments.md'de N'ye eklenen satırlar + önceki araştırmalar 62 + v3 adayları 13).
3. Tasarım ve bekletmede net Sharpe > 0, 1× ve 2× maliyetle.
4. Aile ızgarasında PBO < 0,5 (tasarım).
5. **Sıfır hipotezleri** (tasarım, 1.000'er): TS_D ve TS_W'de dairesel kaydırma; XS_MOM'da tarih karıştırma ve
   rastgele coin.
6. **Kontroller** (tasarım): 365 gün gecikme → Sharpe ≤ temelin %50'si; **bir karar dönemi sızıntı** (TS_D 1 gün,
   TS_W ve XS_MOM 7 gün) → Sharpe ≥ temel + 1 (trend kuralında geleceği görmek sonucu iyileştirmeli; v2'deki eşik
   hatası karşıt kurallardaydı); ortalamadan arındırılmış karıştırma ve GARCH (5'er tohum) → yıllık getiri < 0 ve
   Sharpe ≤ 0.
7. Komşularda (tam dönem) Sharpe > 0 ve ≥ temelin %50'si.

**Karar:** v2 ile aynı. 1–7'nin hepsini geçen aile gölge mod adayıdır; hiçbiri geçmezse BTC-200 sürer. 1'i geçmeyip
2–7'yi geçen ve uydu kuralını sağlayan aile en fazla %20'lik uydu dilimi adayıdır. Geçen bir aile olursa sinyali,
motoru görmemiş ayrı bir ajan oturumunda yeniden hesaplanır.
