# G10 — Bağımsız kontrol betiği karşılaştırması (zorunlu test 6)

Bağımsız betik (`independent/check.py`) motor kodunu görmemiş ayrı bir ajan oturumunda yalnızca SPEC'ten yazıldı; yorum kararları `independent/README.md`'de. Tek coinlik portföy: sinyal > 0 iken %100, haftalık giriş (pazar kararı, pazartesi dolum), günlük çıkış, VWAP 00–02, komisyon %0,10 + kademe kayması, 2017-08 – 2023-12.

|  | BTCUSDT | ETHUSDT | SOLUSDT | LINKUSDT | KAIAUSDT | LUNAUSDT_until_20220513 | FTTUSDT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| days | 2328 | 2328 | 1238 | 1811 | 921 | 631 | 1473 |
| ema20_max_rel | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| ema50_max_rel | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| ema100_max_rel | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| state_days | 2128 | 2128 | 1038 | 1611 | 721 | 431 | 1273 |
| state_agree | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| state_first_diff |  |  |  |  |  |  |  |
| sigma_max_abs | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 1.232707 |
| held_agree | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| held_first_diff |  |  |  |  |  |  |  |
| entries_ind | 36 | 30 | 22 | 26 | 14 | 5 | 16 |
| exits_ind | 35 | 29 | 21 | 25 | 13 | 5 | 16 |
| entries_eng | 36 | 30 | 22 | 26 | 14 | 5 | 16 |
| exits_eng | 35 | 29 | 21 | 25 | 13 | 5 | 16 |
| ret_max_abs_diff_adet | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| ret_diff_day_adet | 2018-04-24 | 2018-04-20 | 2021-05-20 | 2020-09-17 | 2022-10-24 | 2021-07-05 | 2021-01-05 |
| nav_ind_adet | 8.500870 | 13.281779 | 18.229983 | 3.919094 | 1.156298 | 3.316881 | 6.668716 |
| ret_max_abs_diff_allcash | 0.001388 | 0.003797 | 0.002063 | 0.003737 | 0.000933 | 0.003476 | 0.001212 |
| ret_diff_day_allcash | 2019-04-02 | 2020-04-16 | 2021-06-21 | 2020-03-12 | 2022-07-29 | 2021-07-09 | 2022-01-31 |
| nav_ind_allcash | 8.530276 | 13.599179 | 18.259379 | 3.978418 | 1.155370 | 3.309467 | 6.663387 |
| ret_days_diff_gt_1e-6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| nav_eng | 8.500870 | 13.281779 | 18.229983 | 3.919094 | 1.156298 | 3.316881 | 6.668716 |
| nav_ratio_adet | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| start | 2017-08-17 | 2017-08-17 | 2020-08-11 | 2019-01-16 | 2021-06-24 | 2020-08-21 | 2019-12-20 |

## Bulgular (2026-11-03, portföy sonucu görülmeden)

İlk karşılaştırma iki uygulama hatası buldu; ikisi de düzeltildi, regresyon testi eklendi ve experiments.md satır
11'e yazıldı:

1. **Yarım gün temiz bar sayılıyordu.** Motorun 200 temiz bar şartı (`strategy.system.clean_bar_count`) yalnızca
   `error`/`exclude` işaretlerini düşüyordu; PREREGISTRATION §10'a göre yarım gün de temiz gün değildir. Sonuç:
   BTC, ETH ve KAIA ilk uygun günlerinde bir gün erken uygun sayılıyor ve bir fazla giriş yapıyordu. Ana portföyde
   etkisi pratikte yoktur (evren zaten 365 temiz gün ister) ama tanım artık ön kayıtla aynıdır.
2. **Delist duyurusu kalıcı yasak gibi uygulanıyordu.** FTTUSDT 2022-11-14 duyurusundan sonra seri 2023-09-22'de
   yeniden başlıyor; motor coini kalıcı olarak hedef 0'da tutuyordu. Onaylı meta tablodaki not ("delist kuralı ilk
   kapanışa uygulanır") gereği duyuru artık seri `delist_stale_days`'ten uzun bir boşluktan dönene kadar geçerlidir.

Kalan tek fark beklenen ve belgelenmiş bir yorum farkıdır: FTT'nin 310 günlük boşluğundan sonra σ penceresi dolana
kadar bağımsız betik σ'yı tanımsız bırakır, motor son geçerli değeri taşır (PREREGISTRATION §10 "son geçerli değer
taşınır"). Bu, tek coinlik portföyü etkilemez (σ kullanılmaz).

Karşılaştırma portföyünde kademe geçişleri (1/3 ↔ 2/3 ↔ 1) işlem doğurmayacak şekilde sabitlenmiştir (bağımsız
README karar 3); bu yapılmadan önce motorun pazartesi günleri ağırlığı %100'e tamamlaması günlük getirilerde en fazla
%0,37 fark yaratıyordu. Birincil getiri karşılaştırması bağımsız betiğin SPEC adet kuralıyla (Adet = Δw·NAV/kapanış)
hesapladığı seriyle (`ret_net_adet`) yapılır; "tüm nakitle alım" serisiyle fark yalnızca bu kuraldan gelir.

**Sonuç:** EMA'lar, tamponlu durum, tutma bayrakları, giriş/çıkış sayıları ve günlük net getiriler 7 coinin
tamamında makine hassasiyetinde eşleşiyor (`ret_days_diff_gt_1e-6` = 0).

