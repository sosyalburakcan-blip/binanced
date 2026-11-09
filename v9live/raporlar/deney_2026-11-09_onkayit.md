# Deney ön kaydı: az komisyon + yüksek yön isabeti (09.11.2026)

Kullanıcı isteği: "bu veriler ışığında az komisyon vererek ve yön tahmini ihtimal olarak yüksek tutacak denemeler yap".
Bu dosya, bekletme dönemine hiç bakılmadan, deney çalıştırılmadan önce yazıldı ve commit edildi. Commit zamanı kanıttır.
Sonuçtan sonra hiçbir madde değiştirilmez; değişiklik olursa ayrı bir "ön kayıt dışı" başlıkla yazılır.

## Veri
- Fiyat: Release `v9live_book.tar.zst` (06.11 08:46 → 08.11 16:37 UTC). Her coin, her dakika ilk görüntü: en iyi alış, en iyi
  satış, orta.
- Defter dengesi: `live.db` `depth` (b1 = band içi alış $, a1 = band içi satış $).
- **Tasarım:** 06.11 başlangıç (+ 240 dk ısınma) → 07.11 23:59 UTC karar anları. **Bekletme:** 08.11 00:00 UTC → son
  veri − tutma süresi. Seçim yalnızca tasarımla yapılır.

## Karar ve özellikler
- Karar her 5 dk (dakika % 5 = 0). O dakikada, 30 / 60 / 240 dk öncesinde ve bir sonraki dakikada görüntüsü olan coinler
  liste sayılır. En az 20 coin gerekir.
- Özellikler, karar dakikasının görüntüsünden (girişten önce, ileriye bakış yok):
  - `r30x`, `r60x`, `r240x`: coinin son 30 / 60 / 240 dk getirisi − aynı anda listenin ortalaması (piyasaya göre)
  - `combo`: z(r60x) + z(r240x)
  - `imb`: (b1 − a1) / (b1 + a1)
- Her özellik karar anında coinler arasında z-skoruna çevrilir.
- Yön: `mom` (yüksek z → long) ya da `rev` (yüksek z → short).
- Aday: long tarafında yönde en uç coin, short tarafında en uç coin. Yalnız |z| ≥ eşik olanlar.

## Izgara (5 × 2 × 3 × 3 × 3 × 3 = 810 yapılandırma)
- özellik {r30x, r60x, r240x, combo, imb} × yön {mom, rev}
- eşik |z| {1,5; 2,0; 2,5}
- mod {yalnız long, yalnız short, ikisi}
- kâr al = zarar kes = x {%0,5; %0,8; %1,2}
- en uzun tutma H {60, 120, 240 dk}

Ortak kurallar: en fazla 4 açık pozisyon, coin başına bir, pozisyon 1.500 $. Karar başına taraf başına en çok 1 giriş;
iki taraf da uygunsa |z|'si büyük olan önce girer.

## Dolum ve maliyet (gerçek hesap ücretleri)
- **Giriş:** bir sonraki dakikanın orta fiyatı, maker %0,02.
- **Kâr al:** limit. Long'da alış ≥ hedef, short'ta satış ≤ hedef olduğu ilk dakikada hedef fiyattan dolar, maker %0,02.
- **Zarar kes:** orta fiyat seviyeyi geçtiği ilk dakikada. Fiyat long'da min(alış, seviye), short'ta max(satış, seviye),
  1 bps kayma, taker %0,05. Aynı dakikada ikisi birden olursa zarar kes sayılır.
- **Süre:** H dakikada long'da alıştan, short'ta satıştan çıkılır, taker %0,05.
- **Duyarlılık (seçimde kullanılmaz):** taker giriş, yani long'da satış fiyatından, short'ta alıştan, %0,05.

## Seçim ve geçme şartları
- **Seçim:** tasarımda en az 20 işlemi olan yapılandırmalar arasından tasarım net $'ı en yüksek olan TEK yapılandırma.
- **Geçer**, ancak bekletmede dördü birden sağlanırsa:
  1. tasarım net > 0
  2. bekletme net > 0
  3. bekletme isabeti (brüt getirisi > 0 olan işlem payı) > %50
  4. bekletme net'i rastgele girişlerin %95'inden büyük (p < 0,05). Rastgele giriş: aynı karar anları, aynı yön, aynı
     çıkışlar, coin o anki listeden rastgele, açık coin hariç, 1.000 tekrar.
- **Izgara geneli:** 810 yapılandırmanın kaçının bekletmede net > 0 olduğu, rastgele sinyalli ızgarayla karşılaştırılır.
  Rastgele sinyal: her kararda özellik değerleri coinler arasında karıştırılır (tohum 1).
- Sonuç ne çıkarsa çıksın yazılır. Geçse bile 3 günlük veriyle kanıt sayılmaz. Geçen yapılandırma ancak değiştirilmeden
  demoda ileri testin adayı olur.
