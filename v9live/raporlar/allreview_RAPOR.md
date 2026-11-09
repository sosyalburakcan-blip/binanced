# Botun tüm işlemleri: neden kaybediyor? (07.11.2026, ~08:30 UTC)

**Veri:** `v9live/live.db` (`trades` 81 kapanan işlem, 06.11 08:00 → 07.11 08:15 UTC; `scores` 274 karar anı × 30 coin;
`events`), gerçek Binance vadeli 1 dk mumları (89 coin, `fetch.py`, herkese açık GET), demo `userTrades` + gerçek `aggTrades`
(`exact.py`). Bot kodu içe aktarılmadı. Kod: `analyze.py` (işlemler), `decisions.py` (kararlar), `fills.py`, `exact.py`.
Saatler UTC.

## Sonuç

81 işlem, 25 kazanan, **net −294,21 $**.

| Nereye gitti | $ |
|---|---|
| Gerçek fiyat hareketi (gerçek giriş → gerçek çıkış fiyatı) | **−143,8** |
| · bunun aynı sürede 30 coin ortalaması (piyasa; 1 dk mumlarla, yaklaşık) | −116,7 |
| · coine özel (seçim) | −27,1 |
| Demo fiyatı ↔ aynı saniyedeki gerçek fiyat (giriş −65,2 + çıkış −30,7) | **−95,8** |
| Ücret | −53,8 |
| Fonlama | −0,8 |

İşlem başına (1.500 $): piyasa −1,44 · demo farkı −1,18 · ücret −0,66 · seçim −0,33 → −3,63 $.
Not: ilk tur 1 dk mumlarla yapıldı (fiyat −172, giriş/çıkış farkı −67); botun kayıt saatleri borsa saatinden saniyelerce farklı
olduğu için demo farkı borsa dolum saatleriyle (userTrades) yeniden ölçüldü; tablo bu ikinci ölçümle.

## Bulgular

1. **Puan hangi coinin yükseleceğini bilmiyor.** Her karar anında 30 coin arasında puan ↔ sonraki 60 dk sıra ilişkisi ρ +0,02
   (24 saat bazında t −0,48). Altı bileşenin hepsi ≈ 0 (|ρ| ≤ 0,05). Seçilen coin aynı andaki liste ortalamasından 60 dk'da
   −0,16 % (t −0,89, anlamlı değil). Yani seçim ≈ rastgele.
2. **Bot piyasa yükseldikten hemen sonra giriyor; piyasa sonra geri dönüyor.** Giriş yapılan anlarda 30 coinin önceki 60 dk'sı
   +0,056 % (tüm anlar −0,064 %), sonraki 60 dk'sı −0,125 % (tüm anlar −0,055 %). Bu dönemde piyasa saatten saate geri döndü:
   önceki 60 dk ↔ sonraki 60 dk ρ −0,48 (24 saat). Piyasanın en çok yükseldiği %20'lik saatlerden sonra −0,41 %, en çok düştüğü
   %20'den sonra +0,42 %. Seçilen coinin kendi önceki 60 dk'sı +0,79 % (liste +0,07 %). Yalnız alış (long) + 4 yuva = piyasa
   yönüne tek bahis: fiyat kaybının üçte ikisi (−117 / −172 $) piyasadan.
   (Coin düzeyinde, piyasadan arındırılınca önceki 60 ↔ sonraki 60 ρ −0,005: geri dönüş coinde değil, piyasada.)
3. **Çıkış yapısı kaybı kesinleştiriyor.** ±oynaklık döneminde (06.11 19:00 → , 33 işlem): 60 dk kontrolü 21 (%64, ort −4,31 $,
   **hiçbiri kârlı değil** — kural yalnızca +%0,14'ün altındakini satar), kâr al 5 (%15, ort +10,99), zarar stopu 6 (%18, ort −10,65).
   Kâr yalnız kâr aldan gelebiliyor; o da %15. Tahmin gücü yokken bu yapı kendi başına para kaybettirmez ama her işlemde ücret
   (+ piyasa emriyle çıkışta makas) öder: beklenen ≈ −1 $/işlem; gerçekleşen −2,86 $/işlem.
4. **Eski kurallarda kâr/zarar dengesizliği (düzeltildi).** 11:48–14:13 (+5 $ kâr al, −%6 ≈ −90 $ acil stop): 23 işlemde 14 kazanan
   ama −133 $; JCT tek başına −94,57 $ (19 kazancı sildi). 14:13'te −5 $, 19:00'da ±oynaklık ile düzeltildi.
5. **Alış emri düşüşte doluyor.** Dolumdan 1 dk sonra işlemlerin %78'inde gerçek fiyat girişin altında (ort −0,08 %). Geri çekilme
   döneminde dolmayan 25 alışın coini sonraki 60 dk −0,06 %, dolan 81 işlemin coini −0,41 %: dolan emir çoğunlukla düşen coinde.
6. **Demo fiyat farkı −95,8 $.** Her demo dolumu, aynı andan önceki son GERÇEK işlem fiyatıyla (aggTrades) karşılaştırıldı; yalnız
   gerçek fiyatı ölçülen saniyelerdeki dolumların bps'i alınıp tarafın tutarıyla çarpıldı (`exact.py`, `exact_cov.py`). Demo alışı
   gerçekten ortanca +4,4 bps pahalı (81 işlemin %78'inde pahalı) → −65,2 $; çıkış ortanca −1,7 bps → −30,7 $ (kâr al −27,9,
   60 dk kontrolü −27,0; zarar stopu +22,0 — stop gerçek fiyata yakın işaret fiyatıyla tetikleniyor, demo defteri geride kalıyor).
   Kötü taraf: maker alış gerçekte en iyi alıştan dolar, son işlem fiyatından ucuz olurdu → fark muhtemelen biraz daha büyük.
   Gerçek hesapta bu kalem olmaz; yerine gerçek ücret (taker %0,05 > demo %0,04) gelir.
7. **Kayıt notu (kârı etkilemez):** `trades.exit` borsadaki son satıştan ortanca 1,8 sn (en çok 7 sn) sonra yazılan an;
   `trades.fill` İLK alış dolumunun anı (son dolum ortanca 29 sn sonra, en çok ~4 dk). Saniye düzeyi ölçümde borsa saatlerini kullan.

## Kod hatası var mı?

Hesaplar doğru (önceki bağımsız denetimler: özellikler 30/30 fark 0, kâr/zarar borsayla birebir). Kaybı açıklayan bir hesap/
bağlantı hatası bulunmadı. Kayıp **fikirden** ve **demo borsadan** geliyor: "yükselmiş coini al, 1 saat tut" — bu dönemde
piyasanın 1 saatlik hareketleri geri döndü, puan doğru coini seçemedi (seçim ≈ rastgele), çıkış kuralı küçük kayıpları
kesinleştirdi; üstüne demo fiyat farkı ve ücret.

## Sınırlar

Tek gün, 81 işlem, ~24 bağımsız saat; kurallar bu sürede 7 kez değişti. ρ −0,48 bu günün piyasası; başka günde farklı olabilir.
"Seçim gücü yok" = bu veride hiçbir iz yok; kesin sıfır diye kanıt değil.
