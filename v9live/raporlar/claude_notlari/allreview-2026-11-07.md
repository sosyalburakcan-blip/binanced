---
name: allreview-2026-11-07
description: "07.11 ~08:30 UTC 'botun tüm işlemleri, mantık hatası nerde': 81 işlem −294 $ = piyasa −117, demo farkı −96, ücret −54, seçim −27; kod hatası yok"
metadata:
  node_type: memory
  type: project
  originSessionId: a4a631c9-9bb9-4de6-bd70-8be009b14bbd
  modified: 2026-11-07T08:42:14.647Z
---

Kullanıcı 07.11.2026 ~08:15 UTC: "botun yaptığı tüm işlemleri incele, mantık nerde hata var, neden bu kadar kaybediyor".
İnceleme /root/binanced/allreview/ (RAPOR.md; fetch.py gerçek fapi 1 dk, analyze.py, decisions.py, exact.py + exact_cov.py
demo userTrades ↔ gerçek aggTrades). Bot DEĞİŞTİRİLMEDİ.

Sonuç (06.11 08:00 → 07.11 08:15, 81 işlem, 25 kazanan, −294,21 $): gerçek fiyat −143,8 (bunun piyasa payı −116,7, coine özel
−27,1), demo fiyat farkı −95,8 (demo alış gerçekten ortanca +4,4 bps pahalı, %78'inde), ücret −53,8, fonlama −0,8.
Puan ↔ sonraki 60 dk ρ +0,02 (seçim ≈ rastgele); girişler piyasa yükseldikten sonra (önceki 60 dk +0,056 vs −0,064),
piyasa saatlik geri döndü (ρ −0,48, 24 saat); ±VOL60 döneminde çıkışların %64'ü 60 dk kontrolü, hiçbiri kârlı değil.
Kayıt notu: trades.fill = İLK dolum anı, trades.exit = son satıştan ~1,8 sn sonra → saniye ölçümünde borsa saatini kullan.

**Why:** Sonraki "neden kaybediyor" sorularında aynı ölçümü baştan yapmamak, yeni kurallarla kıyaslamak için.
**How to apply:** Yeni dönem değerlendirmesinde aynı ayrıştırmayı (piyasa / seçim / demo / ücret) kullan. Bkz.
[[binanced-paper-service]], [[binanced-bot-audit-2026-11-06]], [[test-honesty-rules]].

07.11 ~09:40 UTC (oturum a2fb03fa, kullanıcı: "oynaklık nasıl hesaplanıyor, stop oynaklığın altında mı, hedef +6 $"): ±VOL60 dönemi
37 işlem −111 $ = kâr al 5 (+55) + stop 6 (−64, hareket ≈ −0,95× VOL60) + 60 dk kontrolü 25 (−107, hareket −0,38× VOL60) + ETHFI elle +5.
Stop tam 1× VOL60'ta, doğru çalışıyor; kâr hedefi sabit değil (pozisyon × VOL60 ≤ 12 $). Önerildi, CEVAP BEKLİYOR: "1 salınım = 6 $"
(pozisyon = min(1.500, 6/VOL60)) ya da kâr al sabit +6 $; oynaklığı kısa pencereden ölçmek (kanıt yok). Bot değiştirilmedi.
Kayıt reports/OTURUM_2026-11-07.md §3-20.
