# v9-demo kaybeden işlemler incelemesi (07.11.2026)

Kaynak: `v9live/live.db` trades (06.11 08:00 – 07.11 04:46 UTC, 69 kapanan işlem: 46 kaybeden NET < 0, 23 kazanan).
Piyasa verisi: Binance gerçek fapi + spot, herkese açık (1 dk mum, aggTrades, openInterestHist 5 dk, fundingRate,
globalLongShortAccountRatio 5 dk). Kod: `collect.py` (veri, bot.py içe aktarılmaz), `analyze.py` (karşılaştırma). Ham ölçüm:
`trades_measured.json`. p0 = dolum anındaki son gerçek işlem fiyatı.

## Sonuç (kısa)
1. **"Tepeden aldık" desteklenmedi:** 2 sa zirvesine uzaklık kaybedenlerde −%0,71, kazananlarda −%0,61 (p 0,39); kaybedenlerin
   yalnız %9'u zirvenin %0,2 yakınında (kazananlarda %17).
2. **Girişte tek belirgin fark ivme farkı (ACC_1 = son saat − önceki saat):** kaybeden +%0,75, kazanan +%0,06 (p 0,008). İki dönemde
   de aynı yön (18:09 UTC öncesi +%0,36 / −%0,15; sonrası +%0,80 / +%0,34). ACC_1 botun puan bileşeni: puan yüksek ACC_1'i ödüllendiriyor.
   ~25 giriş ölçüsü karşılaştırıldı → tesadüf ihtimali var (Bonferroni eşiği 0,002'yi geçmiyor).
3. **İşlem sırasında:** ilk 30 dk alıcı payı kaybeden %46 / kazanan %53 (p < 0,001; bu fiyat düşüşünün kendisi, erken uyarı değil);
   BTC işlem süresince −%0,12 / +%0,09 (p 0,002), BTC ≥ %0,3 düştü: kaybedenlerin %39'u, kazananların %17'si;
   en yüksek noktaya varış 6,5 dk / 25 dk, en yüksek +%0,25 / +%0,91; kaybedenlerin %37'si girişin %0,2 üstüne hiç çıkmadı.
4. **Fark görülmeyenler:** önceki 5/15/60 dk getiri, 4 sa aralıkta konum, hacim artışı, alıcı payı (önce), açık pozisyon, fonlama,
   long/short oranı, BTC korelasyonu, defter dengesi, demo giriş farkı. Açık pozisyon olayları seyrek: long kapatma %11, yeni short %7.
5. **Zararın kaynağı (özdeşlik, kalan 0):** kaybedenler NET −391,67 $ = gerçek fiyat hareketi −357,25 $ + komisyon −32,93 $ +
   demo dolum farkı −0,84 $ + fonlama −0,65 $. Demo giriş farkı ortanca 4,2 bps; düşük hacimli coinlerde büyük (RLC 54, TA 31, AIO 28,
   VVV 17 bps; ENA 39).

## Sınırlar
46 / 23 işlem az; kurallar dönem içinde birkaç kez değişti (kâr al +%3 → +5 $ → ±oynaklık; karar saatlik → dakikalık → 5 dk);
"kümeli giriş" farkı (kaybeden 2, kazanan 6) dönem etkisi (12:50'deki 6'lı giriş), bulgu sayılmadı. Tasfiye (liquidation) geçmişi
Binance REST'te yok → ölçülmedi. İşlem içi ölçüler sonuçla birlikte oluşur (neden değil, nasıl düştüğünü anlatır).
Bayrak eşikleri `analyze.py` FLAGS'te açık.

# 2. tur: kazanan + kaybeden, emir defteri dahil (07.11.2026 ~05:20 UTC)
Ek veri (`collect2.py` → `trades_measured2.json`): botun gerçek piyasa defter arşivi `v9live/book/*.db` (/fapi/v1/depth 1000, dakikada bir;
okuma botun `depth` özetiyle 12/12 birebir), botun `scores` tablosundan piyasa geneli, gerçek 1 dk mumla girişten 60 dk sonra (`ret_60`,
çıkış kuralından bağımsız tek tip sonuç) ve çıkıştan 30/60 dk sonra. 66/69 işlemde defter var (ilk 3 arşivden önce). Demo defteri kayıtlı değil.
Analiz `analyze2.py` (ortak yön: grubun ≥ %70'i tüm işlemlerin ortancasının bir yanında; fark: permütasyon; sağlamlık: iki dönem + ret_60 ile
Spearman; 34 giriş öncesi ölçü → Bonferroni 0,0015).

- **Girişte iki grubu ayıran neredeyse hiçbir şey yok.** Defter (alış-satış farkı ≈ 1,2 bps, ±%0,1/0,25/0,5 dengesi, alış/satış duvarı,
  pozisyon / ±%0,1 alış derinliği ≈ %2), piyasa geneli (son 60 dk artıda coin payı %57 / %58), fonlama, long/short, açık pozisyon: fark yok.
- **BTC önceki 4 sa** (kazanan +%0,46 / kaybeden −%0,01, p 0,001) aynı yarım saatteki işlemler tek kayıt sayılınca kayboldu
  (27 küme: BTC 4 sa artıda kazanma payı %32, eksi %35) → zaman kümelenmesi, bulgu sayılmadı.
- **İvme farkı** kümelenmeden sonra da (ρ −0,41, p 0,034) aynı yön; zaten puandan çıkarıldı (Değişiklik 16).
- **Tek tip sonuçla en güçlü ilişki: girişten önceki 60 dk yükselişi ↔ sonraki 60 dk** ρ −0,43 (p < 0,001; dönem 1 −0,51, dönem 2 −0,30
  p 0,16; 27 küme −0,38 p 0,055). Üçte birlikler: en az yükselen (ortanca −%0,04) → sonraki 60 dk +%0,22, 14/22 yukarı, NET −14,8 $;
  orta (+%0,41) → −%0,30, 4/22, −86,3 $; en çok yükselen (+%1,29) → −%0,42, 7/24, −153,5 $. Aynı yönde: son 4 sa (ρ −0,31), 4 sa aralıkta
  konum (−0,29), son 15 dk hacim artışı (−0,30), açık pozisyon artışı (−0,24). Hepsi "çok yükselmiş" demek → tek hikâye, bağımsız 5 bulgu değil.
  En az yükselen üçte birin çoğu: 13:17 UTC "son 60 dk > 0" şartından önceki girişler ya da karar ile dolum arasında geri çekilenler.
- **Kazananların ortak yönü (işlem sırasında):** BTC de yükseldi (%78), ilk 30 dk alıcı payı arttı (%83), dip sığ (%87), zirve geç (25 dk).
  Kâr aldan sonra fiyat düştü: 60 dk sonra 19'un 17'si aşağıda (ortanca −%0,55) → kâr al erken değil.
- **Kaybedenler iki tür:** hızlı (stop, 21): son 15 dk sıçrama (+%0,25 / −%0,10, p 0,013), BTC 4 sa zayıf (−%0,32 / +%0,13, p 0,001),
  zirve 3. dk; stoptan 60 dk sonra 18'in 12'si biraz yukarıda (ortanca +%0,20, stop mesafesinden küçük). Yavaş (kontrol, 25): son saat alıcı
  payı yüksek (%56 / %51, p 0,005), zirve 17. dk; çıkıştan sonra yatay (9/19 yukarı, −%0,15) → kontrol kuralı sistematik yanlış satmıyor.
- Sınırlar: 69 işlem / 27 bağımsız yarım saat, kurallar değişti, demo defteri ve tasfiye verisi yok; işlem içi ölçüler nedeni değil düşüşün
  nasıl olduğunu anlatır.
