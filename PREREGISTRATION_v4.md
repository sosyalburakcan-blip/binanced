# Ön kayıt v4 — gün içi momentum (spot ve kaldıraçlı vadeli)

> **Durum: DONDURULDU (2026-11-03, tag `prereg-v4`), gerçek fiyat verisinde hiçbir yapılandırma çalıştırılmadan.**
> Kullanıcı 2026-11-03'te gün içinde sürekli momentum ölçümü, belli bir takip süresi, kâr al/zarar kes çıkışları,
> komisyon ve vergi dahil hesap, bilinen coinlerle momentuma göre belirlenen liste ve kaldıraç–spot karşılaştırması
> istedi; ajanlarla ve tam yetkiyle. Parametreler `research_v4.yaml`'da. Bu belgeden sonra yapılan her değişiklik
> `experiments.md`'ye yazılır ve N'ye eklenir.

## 1. Dürüstlük notu

- Bu veride dördüncü araştırma; N önceki 75 denemeyi ve buradaki 648 × 5 = 3.240 çalıştırmanın tamamını içerir (§6).
- 648 yapılandırmalık bir ızgaradan "en iyi listesi" çıkarmak aşırı uyumun ta kendisidir; bu yüzden liste yalnızca
  **tasarım döneminde** sıralanır ve listenin **bekletme dönemindeki** sonucu, rastgele sinyalli ızgaraların "en
  iyileri" ve PBO ile birlikte raporlanır. Kullanıcıya gösterilen her rakamın yanında bu sınavlar durur.
- 2024 sonrası kirlenmiş bekletmedir (piyasanın genel seyri biliniyor; bu yapılandırmaların sonuçları görülmedi).
- Gerçek test ileriye dönük gölge moddur.

## 2. Veri ve dönemler

- 15 dk spot ve USDT-M vadeli barlar, fonlama oranları: data.binance.vision, `data/intraday/` (envanter
  `data/intraday/inventory.csv`, SHA-256 çalıştırma kaydına yazılır). Saatlik sinyaller 15 dk barlardan kurulur.
  G12 anlık görüntüsüne dokunulmaz (`g12 verify`).
- Tasarım 2019-07-01 – 2023-12-31 (sıralama, PBO, sıfırlar, kontroller); kirlenmiş bekletme 2024-01-01 –
  2026-11-01; tam dönem ikisinin birleşimi. Vadeli veri BTC için 2019-09'dan, diğerleri için listelendikleri tarihten.

## 3. Coin listesi ve momentum listesi

- **Bilinen, güvenilir coinler (nokta zamanlı):** her ay m için `universe/{m}.csv` (ana evren; stablecoin,
  kaldıraçlı token, sarılmış token ve borsa tokenları hariç, ay başında bilinen veriyle kurulmuş) üyelerinden, ay
  başında en az 730 gündür listelenmiş olanlar arasında likidite sırasına göre ilk 10. Bugün hayatta kalan coinleri
  geriye dönük seçmez.
- **Momentum listesi:** her saat kapanışında z = log(C_t / C_{t−L}) / (σ_saat · √L) (σ: son 168 saatin saatlik log
  getiri std'si); bilinen coinler arasında z'si en yüksek 3 coin.

## 4. İşlem kuralı (tüm yapılandırmalar)

- Giriş: coin momentum listesindeyse ve z, `confirm_h` saat üst üste `z_entry`'nin üstündeyse ("takip süresi")
  sonraki saatin ilk 15 dk barının açılışında; en fazla 3 eşzamanlı pozisyon, her biri özsermayenin 1/3'ü; öncelik
  z sırasıyla; coin başına bir pozisyon.
- Çıkış (15 dk barlarda): kâr al (limit, kaymasız, yapıcı ücreti), zarar kes (stop-market, kayma + alıcı ücreti;
  boşlukta açılıştan), aynı barda ikisi birden → önce zarar kes (temkinli), süre dolunca açılıştan; vadelide
  tasfiye (izole marjin, marjinin tamamı).
- Maliyetler (`reports/V4_fees_tax.md`, kaynaklı): spot %0,10/%0,10; vadeli yapıcı %0,02, alıcı %0,05 (VIP 0, BNB
  indirimi yok); kayma v1 evren kademelerinden (%0,05/%0,10/%0,20 her yönde); vadelide gerçek fonlama ödemeleri;
  bakım marjı %1. Türkiye'de yürürlükte işlem vergisi/stopaj yok → temel vergi 0.
- Tam simülasyon kuralları `src/trend/intraday/sim.py` modül notunda.

## 5. Izgara ve piyasalar

- 648 yapılandırma: geriye bakış 3/6/12/24 saat × giriş z 1,0/1,5/2,0 × takip 1/3/6 saat × kâr al %1/%2/%4 ×
  zarar kes %1/%2/%4 × en uzun tutma 24/72 saat.
- Her yapılandırma 5 piyasada: spot 1× ve USDT-M vadeli 1×, 2×, 3×, 5×.
- En iyi 10 (tasarım, spot) için: 1 saat gecikme, 1 saat sızıntı (pozitif kontrol), 2× maliyet, BNB indirimi,
  %0,03 işlem vergisi; en iyisi için 100 rastgele giriş tekrarı (aynı kâr al/zarar kes/süre ve giriş sıklığı);
  ayrıca 2 tam rastgele sinyalli ızgara (veri madenciliği sıfırı). Yıllık kazanç vergisi %15/%27/%40 senaryoları
  NAV'dan hesaplanır.

## 6. Geç/kal kriterleri (tasarımda seçilen 1 numaralı yapılandırma, spot 1×)

1. Bekletme döneminde net Sharpe > 0, hem 1× hem 2× maliyetle.
2. Tam dönemde BTC-200'ü net Sharpe'ta eşleştirilmiş bootstrap ile yener (tek yönlü p < 0,05).
3. DSR ≥ 0,95; N = max(100, experiments.md'de N'ye eklenen satırlar + önceki araştırmalar 75 + 3.240).
4. 648 yapılandırma üzerinde tasarım döneminde PBO < 0,5.
5. Rastgele giriş sıfırı (tasarım, 100 tekrar) p < 0,05.
6. Gerçek ızgaranın tasarımdaki en iyi Sharpe'ı, iki rastgele sinyalli ızgaranın en iyilerinin ikisini de geçer.
7. Pozitif kontrol: 1 saat sızıntı Sharpe'ı ≥ temel + 1 (kodun geleceği görmediğinin değil, testin duyarlı
   olduğunun kontrolü; karar kriteri değildir).
8. Tek eksenli komşularının hepsinde tasarım Sharpe'ı > 0.

**Karar:** 1–6 ve 8'in hepsi geçerse gölge mod adayıdır; aksi halde reddedilir ve BTC-200 kararı sürer. Kaldıraç
yalnızca raporlanır: kaldıraç Sharpe'ı artırmaz, getiri ve düşüşü katlar, ücret/fonlama/tasfiye ekler. Kaldıraçlı bir
sonuç seçilmez; spotta geçmeyen bir kural kaldıraçla da aday olmaz.
