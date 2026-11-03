# Deneme defteri (experiments.md)

SPEC: Her çalıştırma ve ön kayıttan sonra yapılan her değişiklik buraya tarih, gerekçe ve sonuçla yazılır;
her satır deflated Sharpe için N'ye eklenir. Ön kayıttan önceki altyapı çalıştırmaları da (veri, kalite, evren)
kayıt için yazılır ama strateji sonucu içermez.

| # | Tarih (UTC) | Görev | Ne çalıştırıldı / değişti | Gerekçe | Sonuç | N'ye eklenir mi |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-11-02 | G1 | S3 sembol keşfi (`trend.data.s3`), exchangeInfo anlık görüntüsü | Altyapı | 1.755 sembol, 80.636 zip, 0,998 GB; delist edilmiş semboller arşivde (reports/G1_symbols.md) | Hayır |
| 2 | 2026-11-02 | G2 | Tam indirme (`trend.data.download --all`, eşzamanlılık 8) | Altyapı | 80.636/80.636 ok, checksum hatası 0, ~2,4 saat | Hayır |
| 3 | 2026-11-02 | G3 | Temizleme (`trend.data.clean`) | Altyapı | 1d ve 1h coin başına parquet, hatalı 0 | Hayır |
| 5 | 2026-11-02 | G4 | Kalite işaretleri (`trend.quality flags`), REST çapraz kontrol (10 coin, 210 gün), rapor | Altyapı | 5.662 işaret; REST ile uyuşmayan alan 0 (reports/G4_quality.md) | Hayır |
| 6 | 2026-11-02 | G5 | Sembol haritası 33 → 43 satır (34 evren adayından 10 gerçek takas + BTCST/DREP doğrulandı); birleştirilmiş seriler 1d/1h; tablo son işleminden sonraki sıfır hacimli mumlar atılıyor (KLAY) | Evrene giren coinlerin geçmişi bölünmesin | 746 varlık; **kullanıcı onayı bekliyor** (reports/G5_meta.md) | Hayır |
| 7 | 2026-11-02 | G6 | Evren (`trend.universe build`), T7 ve 10/30/50 büyüklükleri | Altyapı | 2019–2020 medyan 10 coin (SPEC beklentisi 15–30); 2019-07'de 9 coin; T7 ana evrenle %100 aynı (USDT hacmi her gün baskın) | Hayır |
| 4 | 2026-11-02 | G0 | `settings.yaml`: eşzamanlılık 6 → 8; agentlerin modül sabitleri settings'e taşındı; `size_by_capital` sınırı SPEC'e göre düzeltildi (15.000 dahil 20) | Her parametre tek yerde; SPEC'e uyum | Testler yeşil | Hayır (ön kayıttan önce, strateji sonucu görülmeden) |
| 8 | 2026-11-03 | G9 | Kullanıcı sembol tablosunu (43 satır), komisyon kampanyası kapsamını ve ön kayıt varsayımlarını onayladı; T6 kayıp günü 2022-11-08 olarak sabitlendi; ön kayıt donduruldu: kod commit'i `3a13027`, tag `prereg-v1` → `f5b9027` | SPEC G9: sonuçlardan önce | `PREREGISTRATION.md` SHA-256 `a216875e5ba28c46853fd19cdf99a82f27f568917e65347305bba3850a1432d7` | Hayır (strateji sonucu görülmeden) |
| 9 | 2026-11-03 | — | G5 ve G4 rapor yazıcıları LF satır sonuyla yazıyor | Biçim; sonuçları etkilemez | — | Hayır |
