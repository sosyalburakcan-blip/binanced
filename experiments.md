# Deneme defteri (experiments.md)

SPEC: Her çalıştırma ve ön kayıttan sonra yapılan her değişiklik buraya tarih, gerekçe ve sonuçla yazılır;
her satır deflated Sharpe için N'ye eklenir. Ön kayıttan önceki altyapı çalıştırmaları da (veri, kalite, evren)
kayıt için yazılır ama strateji sonucu içermez.

| # | Tarih (UTC) | Görev | Ne çalıştırıldı / değişti | Gerekçe | Sonuç | N'ye eklenir mi |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-11-02 | G1 | S3 sembol keşfi (`trend.data.s3`), exchangeInfo anlık görüntüsü | Altyapı | 1.755 sembol, 80.636 zip, 0,998 GB; delist edilmiş semboller arşivde (reports/G1_symbols.md) | Hayır |
| 2 | 2026-11-02 | G2 | Tam indirme (`trend.data.download --all`, eşzamanlılık 8) | Altyapı | 80.636/80.636 ok, checksum hatası 0, ~2,4 saat | Hayır |
| 3 | 2026-11-02 | G3 | Temizleme (`trend.data.clean`) | Altyapı | 1d ve 1h coin başına parquet, hatalı 0 | Hayır |
| 4 | 2026-11-02 | G0 | `settings.yaml`: eşzamanlılık 6 → 8; agentlerin modül sabitleri settings'e taşındı; `size_by_capital` sınırı SPEC'e göre düzeltildi (15.000 dahil 20) | Her parametre tek yerde; SPEC'e uyum | Testler yeşil | Hayır (ön kayıttan önce, strateji sonucu görülmeden) |
