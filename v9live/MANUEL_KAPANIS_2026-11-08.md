# 08.11.2026 — Bot durduruldu, açık işlemler elle kapatıldı

Kullanıcı isteği: "botu ve tüm her şeyi durdur". Saatler UTC (TR = UTC+3).

- 16:38 UTC: `v9-demo` servisi durduruldu ve açılışta başlamaması için kapatıldı (`systemctl disable`).
- 16:38 UTC: bekleyen WLDUSDT SHORT giriş emri (v9d-en-1794155720-614, 4613 adet @ 0,3251) iptal edildi, hiç dolmadı.
- 16:42:39 UTC: açık iki SHORT piyasa emriyle (reduceOnly) kapatıldı:

| Coin | Adet | Giriş | Çıkış | Borsa K/Z | Çıkış komisyonu |
|---|---|---|---|---|---|
| ETHUSDT | 0,669 | 2.239,73 | 2.236,99 | +1,83 $ | 0,60 $ |
| HYPEUSDT | 19,38 | 77,314 | 77,453 | −2,69 $ | 0,75 $ |

- Giriş komisyonları (maker) yaklaşık 0,30 $ + 0,30 $. Net toplam ≈ +1,83 − 2,69 − 1,35 − 0,60 ≈ **−2,8 $**.
- Kâr al emirleri pozisyon kapanınca borsada kendiliğinden düştü (EXPIRED), stop emri kalmadı.
- Sonrası: açık pozisyon 0, açık emir 0, USDT bakiye 4.242,60 $.
- Bu kapanışlar bot kapalıyken yapıldığı için `live.db`'de yok; `state.json` durma anındaki hâli gösteriyor.
