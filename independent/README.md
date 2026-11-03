# Bağımsız kontrol betiği

Spesifikasyon v3, "Zorunlu testler" madde 6: *"sinyaller ve tek coinlik getiri, motoru görmemiş ayrı bir Claude oturumunda sadece bu belgeden yazılmış basit bir pandas betiğiyle tekrar hesaplanır."*

Bu klasördeki kod, motoru hiç görmemiş ayrı bir oturumda yazıldı. Kullanılan kaynaklar yalnızca şunlar:

- `Trend Takip Sistemi Spesifikasyon v3 (tek kaynak).md`
- `data/merged/1d/*.parquet` ve `data/merged/1h/*.parquet`

`src/`, `tests/`, `reports/`, `backtests/`, `meta/`, `CONTRACTS.md`, `PREREGISTRATION.md`, `settings.yaml`, `experiments.md` ve git geçmişi açılmadı. `trend` paketi import edilmedi. Spesifikasyonun belirsiz bıraktığı yerlerde karar metinden verildi ve aşağıda listelendi.

## Çalıştırma

Proje kökünden:

```
python -m uv run python independent/check.py
```

Çalışma süresi yaklaşık 3–4 saniye. Betik her varlık için `independent/out/{VARLIK}.csv` dosyasını yazar ve konsola tek satırlık bir özet basar. Varlıklar: BTCUSDT, ETHUSDT, SOLUSDT, LINKUSDT, KAIAUSDT, LUNAUSDT_until_20220513, FTTUSDT.

Veri, parquet filtresi (`open_time <= 2023-12-31 23:59:59.999999`) ile okunur. 2024 ve sonrasına ait satırlar belleğe hiç yüklenmez, çıktıya da yazılmaz.

## Çıktı kolonları ve zaman hizası

Her satır bir takvim günüdür (UTC). Satırlar coinin ilk mumundan min(son mum, 2023-12-31) tarihine kadar uzanır. `date = t`, açılışı t günü 00:00 UTC olan günlük mumdur. Bu mumun kapanışı t+1 günü 00:00 UTC'dir.

| Kolon | t satırındaki anlamı |
| --- | --- |
| `close` | t mumunun kapanışı. Boşluk günlerinde son gerçek kapanış taşınır. |
| `ema20/50/100` | t kapanışı dahil EMA. Boşlukta donar. |
| `signal_raw` | Tamponsuz skor: ortalama_n 1[C(t) > EMA_n(t)]. İlk uygun günden önce NaN. |
| `s20/s50/s100` | Vade bazında tamponlu durum s_{i,n}(t), h = 0,5. |
| `state` | Tamponlu skor S(t) = ortalama_n s_{i,n}(t) ∈ {0, 1/3, 2/3, 1}. t kapanışındaki karar. |
| `target` | **t kapanışında verilen karar**: t+1 sabahı dolduktan sonra coin tutulacak mı (1/0). |
| `trade` | **t günü 00:00–02:00 UTC'de gerçekleşen dolum** (t−1 kapanışındaki kararın sonucu). +1 alış, −1 satış, −2 zorunlu delist satışı. |
| `fill_px` | t gününün ham dolum fiyatı (VWAP, kayma hariç). İşlem olmayan günlerde de gösterilir. |
| `exec_px` | t günü işlem varsa kayma ve delist cezası dahil gerçekleşen fiyat. |
| `slippage` | t günü dolumunda kullanılan kayma oranı. Bu oran, t−1 kararının ait olduğu aylık kademeden gelir. |
| `held` | **t kapanışında elde coin var mı.** t sabahındaki dolumdan sonraki pozisyondur, yani t−1 kararının sonucudur. Dolum mümkün olan her günde `held(t) = target(t−1)` sağlanır. |
| `ret_net` | Portföyün t−1 kapanışından t kapanışına net getirisi. t sabahındaki dolum ve maliyetleri dahildir. |
| `nav` | t kapanışında portföy değeri. İlk satır 1,0'dır ve bileşik hesaplanır. |
| `sigma_d` | Günlük σ_d = son 30 takvim gününün log getiri standart sapması (tampon için). |
| `rv30`, `rv90`, `sigma` | Yıllık (√365) rv30 ve rv90. σ = max(rv30, rv90, 0,30). |
| `ret_net_adet`, `nav_adet` | Alternatif portföy: alım adedi spesifikasyonun "Adet = Δw × NAV(t−1)/kapanış(t−1)" kuralıyla hesaplanır (karar 18). |
| `gap`, `half_day`, `clean_bars`, `eligible`, `sunday`, `delisted` | Yardımcı işaretler: boşluk günü, yarım gün, temiz bar sayacı, ≥ 200 temiz bar, pazar günü, seri delist mi. |

Örnek akış:

1. Pazar satırında `state > 0`, `held = 0` ise `target = 1` olur.
2. Pazartesi satırında `trade = +1` olur. Alış o günün `fill_px` değeriyle yapılır ve `held = 1` olur.
3. Pazartesinin `ret_net` değeri, VWAP'tan pazartesi kapanışına kadarki getiriyi ve maliyetleri içerir.

## Yorumlama kararları

1. **Karar ve dolum zamanı.** Spesifikasyon: *"t−1 kapanışında oluşturulan emirleri t gününün 00:00–02:00 UTC VWAP'ından gerçekleştir"*, *"dolum: VWAP 00:00–02:00 (t günü sonrası)"*. Karar: `open_time = t` olan mumun kapanışıyla karar verilir. Dolum, t+1 günü 00:00–02:00 UTC'de olur.

2. **Haftalık giriş günü.** Spesifikasyon: *"Pozisyonu artıran her işlem (yeni giriş, kademe artışı, bant alımı) sadece pazar günü kapanışındaki kararla yapılır (dolum pazartesi 00:00–02:00 UTC)."* Karar: Yeni giriş yalnızca `open_time` günü pazar olan mumun kararıyla verilir. Çıktıda bütün girişlerin dolumu pazartesiye düşüyor. Çıkış her gün mümkündür.

3. **Tutma ve çıkış tanımı.** Spesifikasyon: *"w\*\_i = S\_i · w\_full,i"*, *"Çıkış her zaman tamdır: w\*\_i = 0 ve w\_i > 0 ise pozisyonun tamamı satılır"*. Karar: Coin S > 0 iken tutulmak istenir. Çıkış ancak üç vadenin tamponlu durumu da 0 olduğunda (S = 0) yapılır. Görev tanımı gereği tutulurken ağırlık %100'dür. Bu yüzden 1/3 ↔ 2/3 ↔ 1 kademe değişiklikleri ve kayma bandı işlemi doğurmaz. Ağırlık hiçbir zaman 0,75'in altına düşmediği için bant kuralı tetiklenmez.

4. **EMA.** Spesifikasyon: *"`close.ewm(span=n, adjust=False).mean()`"*. Karar: EMA coinin ilk gerçek mumundan başlar. Yarım gün olan ilk mum da dahildir, ilk EMA değeri ilk kapanıştır. EMA yalnızca gerçek mumlar üzerinde güncellenir ve boşluk günlerinde son değerinde donar. Bu karar sadece FTT'yi etkiler: boşluktan sonraki ilk EMA, donmuş değer ile yeni kapanıştan tek adımla hesaplanır.

5. **Tamponlu durum makinesi.** Spesifikasyon: *"1 : C > EMA(1 + hσ\_d); 0 : C < EMA(1 − hσ\_d); aksi halde s(t−1)"*, *"Tampon çarpandır, toplanan değildir"*. Karar: Eşitsizlikler katıdır. σ_d, t gününün getirisini de içerir.

6. **Durum makinesinin başlangıcı ve uygunluk.** Spesifikasyon: *"Bir coin için sinyal üretilebilmesi için en az 200 temiz bar gerekir"*, *"Başlangıç durumu: coinin ilk uygun gününde tamponsuz kural (C > EMA ise 1)."* Karar: Görev evreni yok saymayı istediği için ilk uygun gün, 200. temiz barın günüdür (o gün dahil). O gün s_n = 1[C > EMA_n] alınır, sonraki günlerde tamponlu kural uygulanır. Uyarı: Motor evren üyeliğini (365 temiz gün, likidite, ilk 20) kullanıyorsa durum makinesi daha geç başlar. Tamponlu durumlar ilk bant dışı kesişmeye kadar farklı olabilir.

7. **Temiz bar.** Spesifikasyonun kalite tablosu: *"Yarım gün … İşaret; tam gün sayılmaz"*, *"Sıfır hacim … art arda 3+ gün | O dönem dışlanır"*. Karar: Temiz bar, gerçek bir günlük mumdur. Yarım gün olmamalı ve art arda 3 veya daha fazla günlük sıfır hacim (volume = 0 veya number_of_trades = 0) döneminin parçası olmamalıdır. Bu yedi varlıkta ≤ 2023 döneminde sıfır hacimli gün yok. Aşırı sıçrama ve iğne işaretleri ("İşaret, ikinci kaynakla kontrol") barı temizlikten çıkarmaz. Yarım gün mumlarının kapanışı EMA ve getiri hesabında kullanılır, sadece temiz bar sayacına girmez.

8. **Oynaklık.** Spesifikasyon: *"σ\_d = 30 günlük log getiri standart sapması"*, *"σ\_i = max(rv30\_i, rv90\_i, 0,30), yıllık (√365)"*, *"Oynaklık için 30 günün en az 20'si, 90 günün en az 60'ı dolu olmalı."* Karar:
   - Log getiri takvim günleri üzerinde ln(C_t/C_{t−1}) olarak hesaplanır. Boşluğa komşu getiriler "dolu değil" (NaN) sayılır, boşluk boyunca biriken sıçrama getirisi oynaklığa girmez.
   - rv30 = son 30 takvim gününün std'si, en az 20 değer gerekir. rv90 = son 90 günün std'si, en az 60 değer gerekir.
   - pandas varsayılanı ddof = 1 kullanılır.
   - σ_d = günlük rv30.
   - Yıllık σ, rv30 veya rv90 hesaplanamıyorsa NaN olur.
   - Boşluk günlerinde σ donar.

9. **σ_d hesaplanamayan gerçek gün.** Bu durum yalnızca FTT'de, boşluktan sonraki 2023-09-22 – 2023-10-11 arasında oluyor. Spesifikasyon tamponun σ_d olmadan nasıl çalışacağını söylemiyor. Karar: Bu günlerde durum ve hedef, boşluk kuralındaki gibi donar.

10. **Dolum fiyatı.** Spesifikasyon: *"VWAP = Σ quote\_volume / Σ volume, 00:00–02:00 UTC arasındaki iki 1 saatlik mumdan"*, *"Bu pencerede hacim sıfırsa bir sonraki saat kullanılır."* Karar:
    - Pencere, `open_time` değeri [00:00, 02:00) aralığında olan 1 saatlik mumlardır.
    - Pencerede hacim sıfırsa veya mum yoksa pencere birer saat uzatılır, gün sonuna kadar denenir.
    - 2018-02-09'daki kaymış saatlik mumlar (xx:28) bu kuralla doğal olarak ele alınır.
    - Gerçekleşen işlemlerin hiçbiri uzatılmış pencereye düşmedi.

11. **Maliyetler.** Spesifikasyon: *"Alım fiyatı = VWAP × (1 + kayma), satım = VWAP × (1 − kayma); komisyon %0,10 ayrıca."* Karar: Komisyon, gerçekleşen fiyat üzerinden işlem tutarının %0,10'udur. Alışta q = nakit / (VWAP·(1+kayma)·1,001). Satışta gelir = q·VWAP·(1−kayma)·0,999.

12. **Kayma kademesi.** Spesifikasyon: *"A | BTC ve ETH | … | %0,05"*, *"B | … | 30 günlük medyan likidite ≥ 100M: %0,05; 20–100M: %0,10; < 20M: %0,20"*, *"Kademe ve tavan, evren kurulurken belirlenir ve ay boyunca sabittir"*, *"Evren her ay, önceki ayın son günlük kapanışıyla kurulur ve o kapanıştaki karardan itibaren bir ay geçerlidir."* Karar:
    - BTC ve ETH için %0,05 kullanılır.
    - Diğerleri için her ayın son günü, son 30 takvim gününün medyan likiditesine bakılır. Bu oran o ay sonu kararından (dolum ertesi ayın 1'i) bir sonraki ay sonuna kadar geçerlidir.
    - Eşikler: ≥ 100M → %0,05; 20M–100M → %0,10; < 20M → %0,20.
    - **Basitleştirme:** Likidite yalnızca USDT çiftinin `quote_volume` değeridir. Diğer stablecoin çiftleri ve sıfır komisyon kampanyası tablosu `meta/` altında olduğu ve bu oturumda okunamadığı için T7 tarzı (sadece USDT) ölçü kullanıldı.
    - Mum olmayan gün likiditesi 0 sayılır. Bu yüzden FTT boşluktan sonra bir süre %0,20 kademesinde kalır.
    - Kademe hesaplanamazsa %0,20 kullanılır. Bu durum sadece ilk aylarda olabilir, o dönemde işlem yok.

13. **Boşluk kuralı.** Spesifikasyon: *"Boşluk süresince son fiyat taşınır, sinyal ve ağırlık dondurulur, işlem yapılmaz. Seri devam ederse normal karar döngüsüne dönülür."* Karar:
    - Boşluk günü = günlük mumu olmayan gün.
    - Kapanış taşınır, NAV bu fiyatla değerlenir. EMA, σ, durum ve hedef donar, dolum yapılmaz.
    - Emirler "hedefe işlem" mantığıyla yürür: boşluk öncesinde dolamamış bir hedef, seri devam ettiğinde ilk dolum günü gerçekleşir.
    - Seri devam ettiğinde durum makinesi yeniden başlatılmaz, donmuş durumdan devam eder.

14. **FTT.** ≤ 2023 penceresinde FTT serisi 2022-11-15'te yarım günle (04:30 UTC) kesiliyor ve 2023-09-22'de yeniden başlıyor. Arada 310 gün boşluk var. Spesifikasyon: *"Hiç devam etmezse delist kuralı son fiyattan uygulanır"*, *"Backtestte son mumun tarihi kullanılır"*. Karar: Bu pencerede seri devam ettiği için olay delist değil, boşluk olarak işlendi. Sonuç: FTT'deki çıkış kararı 2022-11-05 kapanışında verildi ve 2022-11-06'da doldu. 8 Kasım çöküşünden ve boşluktan önce pozisyon kapalıydı.

15. **Delist kuralı.** Spesifikasyon: *"Duyuru bilinmiyorsa: pozisyon son işlem gününe kadar tutulur ve o günün VWAP'ı × (1 − ceza) ile kapatılır. Önceki günün kapanışından satış yapılmaz"*, *"Delist cezası | %5 temel"*. Karar:
    - Son mumu 2023-12-31'den önce olan seri delist sayılır. Bu yedi varlıkta yalnızca LUNA (son mum 2022-05-13 00:40) bu durumda.
    - Son işlem günü önce normal dolum yapılır. Coin hâlâ tutuluyorsa aynı günün dolum VWAP'ı ile zorla satılır: fiyat = VWAP·(1−kayma)·(1−0,05), üstüne %0,10 komisyon. Ceza, normal maliyetlerin yerine değil, onlara ek olarak uygulanır.
    - VWAP yoksa son kapanış kullanılır.
    - LUNA'da çıkış kararı 2022-04-30'da verildi ve 2022-05-01'de doldu, bu yüzden kural tetiklenmedi. Kod yolu sentetik bir seriyle elle doğrulandı.

16. **Dönem sonu.** 2023-12-31 bir delist değil, kesimdir. O günün kararı `target` kolonunda görünür ama dolmaz, çünkü 2024 verisi okunmaz.

17. **Başlangıç ve nakit.** NAV ilk satırda 1,0'dır. İlk uygun günden önce pozisyon yoktur. Nakit getirisi %0'dır (*"nakit kısma temel varsayımda %0 getiri"*).

18. **Alım adedi (iki sürüm).** Görev tanımına göre tutulurken ağırlık %100'dür. Birincil `ret_net`/`nav` bu tanımı birebir uygular: alışta tüm nakit kullanılır. Spesifikasyonun kuralı ise farklıdır: *"Adet = Δw × NAV(t−1 kapanış) / kapanış(t−1)"*, *"Nakit asla negatif olamaz"*, *"nakit yetmezse alımlar orantılı küçültülür"*. Bu kural `ret_net_adet`/`nav_adet` kolonlarında uygulanır: adet = NAV(t−1)/C(t−1), nakit yetmezse nakitle sınırlanır, küçük bir nakit artığı kalabilir. Satışlar her iki sürümde de tamdır, işlem günleri aynıdır.

19. **Rejim filtresi, güç filtresi, evren, vol hedefi, tavanlar, −%35 sert sınır, minimum emir.** Görev tanımı gereği hiçbiri uygulanmadı (T0, tek coin, coin hep uygun).

## Yapılan akıl sağlığı kontrolleri

- Çıktıda 2023-12-31'den sonra satır yok. Tarihler kesintisiz günlük, NAV her yerde sonlu.
- EMA'lar elle yazılmış özyinelemeyle birebir aynı. σ_d ve σ, numpy ile elle hesaplananla eşleşiyor (1e-15). VWAP, ham 1 saatlik veriden elle hesaplananla aynı.
- İlk BTC döngüsünün giriş ve çıkış günü NAV'ı elle hesaplananla birebir aynı.
- Bütün tamponlu durum geçişleri kurala uyuyor (0 ihlal).
- Bütün girişler pazartesi doluyor. Durumu > 0 olup elde coin olmayan her pazar günü giriş kararı veriliyor, başka hiçbir gün verilmiyor.
- BTC şu dönemlerde tutuldu (bazılarında kısa aralar var): 2019-02 – 2019-08, 2020-04 – 2020-09, 2020-09-28 – 2021-05-13, 2021-07 – 2021-11, 2023-01 – 2023-08. 2022 ayı piyasasında çoğunlukla nakitteydi.

| Varlık | İlk uygun gün | Giriş/çıkış | Uygun günlerde tutma | Son NAV |
| --- | --- | --- | --- | --- |
| BTCUSDT | 2018-03-05 | 36/35 | %57,4 | 8,53 |
| ETHUSDT | 2018-03-05 | 30/29 | %58,8 | 13,60 |
| SOLUSDT | 2021-02-27 | 22/21 | %51,9 | 18,26 |
| LINKUSDT | 2019-08-04 | 26/25 | %58,7 | 3,98 |
| KAIAUSDT | 2022-01-10 | 14/13 | %35,2 | 1,16 |
| LUNAUSDT_until_20220513 | 2021-03-09 | 5/5 | %74,5 | 3,31 |
| FTTUSDT | 2020-07-07 | 16/16 | %41,9 | 6,66 |

Bu sayılar tek coinlik basitleştirilmiş kontrol portföyüne aittir. Stratejinin performansı değildir.
