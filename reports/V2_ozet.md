# Araştırma v2 özeti — trend takibi dışındaki stratejiler

2026-11-03. Ön kayıt `PREREGISTRATION_v2.md` (tag `prereg-v2`, commit `b03c3b9`) gerçek veride hiçbir aday
çalıştırılmadan donduruldu. Toplu çalıştırma bir kez yapıldı (`lock/V2_run.json`, 97 çalıştırma). Ayrıntılı tablolar
[V2_alternatives.md](V2_alternatives.md) dosyasında.

## Sonuç

**Hiçbir aile ön kayıtlı kriterleri geçmedi.** Karar değişmiyor: BTC-200.

Tam dönem (2019-07 – 2026-11-01), maliyetler dahil, nakit %0:

| Strateji | Yıllık getiri | Sharpe | En büyük düşüş | 1.000 $ → | Kriter |
| --- | --- | --- | --- | --- | --- |
| XS_LOWVOL (en az oynak 5 coin) | %29,4 | 0,76 | −%45 | ~6.600 $ | 2/7 |
| VM_BTC (oynaklığa göre yönetilen BTC) | %24,5 | 0,64 | −%71 | ~5.000 $ | 2/7 |
| RV_ETHBTC (ETH/BTC oranı) | %16,6 | 0,53 | −%78 | ~3.100 $ | 3/7 |
| XS_REV (en çok düşen 5 coin) | %6,3 | 0,27 | −%57 | ~1.600 $ | 1/7 |
| MR_BTC (BTC dip alımı) | −%9,8 | −0,20 | −%77 | ~470 $ | 1/7 |
| *Kıyas: BTC-200* | %24,5 | 0,66 | −%66 | ~5.000 $ | — |
| *Kıyas: %50 BTC + %50 ETH* | %35,9 | 0,76 | −%76 | ~9.500 $ | — |
| *Kıyas: v1 alt-coin trend (T0)* | %4,5 | 0,18 | −%36 | ~1.400 $ | — |

## En iyi görünen aday neden geçmedi: XS_LOWVOL

Ham rakamlar BTC-200'den iyi: daha yüksek getiri, daha küçük düşüş. Ama:

- **Fark tesadüften ayırt edilemiyor:** BTC-200'e karşı p = 0,37; geçme eşiği 0,01.
- **Ayar seçimi dayanıksız:** PBO 0,74. Bir dönemde en iyi görünen komşu ayar, başka bir dönemde iyi çıkmıyor.
- **Zamanlama rastgeleden iyi değil:** tarih karıştırma testinde p = 0,49. Coin seçimi ise rastgeleden iyi
  (p = 0,011), çünkü seçilen coinler hep aynı büyük coinler: BTC, ETH, BNB.
- **Sinyali bir yıl geciktirmek sonucu neredeyse değiştirmiyor:** Sharpe 0,85'ten 0,67'ye iniyor. Yani bu bir sinyal
  değil, fiilen "büyük coinleri tut" stratejisi.
- **Uydu kuralını da kıl payı geçemiyor:** 0,379'a karşı 0,398.

Bu dönemde büyük coinler yükseldi, küçükler düştü; bunu bugün biliyoruz. Aynı şey basit %50 BTC + %50 ETH kıyasında
da görünüyor: en yüksek getiri (%35,9) ondan geldi, ama −%76'lık düşüşle.

## Kontrol sonuçlarının yorumu

- **Sızıntı kontrolü (yarının verisini görme) üç karşıt ailede sonucu iyileştirmedi, kötüleştirdi:** XS_REV
  0,16 → −0,49; MR_BTC −0,32 → −1,65; RV_ETHBTC 0,75 → 0,10. Bu kurallar düşeni alıyor; yarını görünce düşmek üzere
  olanı alıyorlar. Sonuç büyük ölçüde değiştiği için sızıntı yakalanıyor ve kodda gizli bir geleceği görme yok. Ön
  kayda "Sharpe ≥ temel + 1" yazılmıştı; bu eşik yalnızca trend kuralları için doğru. Hata bende, ama hiçbir kararı
  değiştirmiyor: tüm aileler zaten birincil testte kalıyor.
- **365 gün gecikme XS_LOWVOL, VM_BTC ve RV_ETHBTC'yi bozmuyor:** getiri zamanlamadan değil, piyasada durmaktan
  geliyor.
- **Karıştırılmış ve GARCH serilerinde** tüm aileler para kaybediyor; beklenen buydu.

## Ne öğrendik

Bu veride ve Binance spotta yalnızca uzun pozisyonla, denediğimiz trend dışı beş aile, büyük coinleri basitçe
tutmaktan istatistiksel olarak ayırt edilebilir bir şey üretmedi. Getiriyi belirleyen şey hangi coinlerin
tutulduğuydu (BTC ve ETH yükseldi, alt-coinler çöktü); zamanlama kuralları değil.

Not: v1 raporundaki BTC/ETH-200 kıyası (her biri kendi 200 günlük ortalamasıyla) tam dönemde yıllık %33,6, Sharpe
0,79, düşüş −%58 verdi. Bu da bir trend kuralı ve sonuç görüldükten sonra seçilirse aşırı uyum olur. Ancak ileriye
dönük gölge testte BTC-200'ün yanında izlenebilir.
