---
name: fullreview-2026-11-07
description: "07.11 tam inceleme (fullreview/RAPOR.md): 86 işlem −315 $, kod doğru, ilk 5 zarar −171 $ (06.11 stopsuz dönem, JCT −95), ±VOL60 döneminde 38'de 6 kazanma"
metadata:
  node_type: memory
  type: project
  originSessionId: c1b0c029-3cd7-4db2-91b9-820664ed201b
  modified: 2026-11-07T10:07:35.957Z
---

07.11.2026 ~10:00–10:40 UTC kullanıcı isteği: "botu en baştan analiz et, kurallar, doğruluk, oynaklık, neden kaybediyor, çıkış türüne göre zarar".
Sıfırdan kod + taze Binance verisi: `/root/binanced/fullreview/` (fetch.py, fetch_ref.py, analyze.py, tables.py, RAPOR.md, trades.csv, KURALLAR_OZET.md).

Bulgular (86 işlem, 06.11 11:00 → 07.11 12:52 TR):
- Kod doğru: borsadan yeniden net −315,28 $ (bot −314,98; fark = ETH, ONDO fonlaması 0,15'er $ bot kaydına girmemiş), giriş şartı 86/86, VOL60 38/38.
- Parçalar: gerçek fiyat −155 $, demo farkı −100 $ (alış −66, piyasa satışı −38, kâr al −31 = zamanlama, stop +32), komisyon −58 $. Kötü tarafla: piyasa ≈ −187, demo ≈ −69.
- Çıkış: zarar stopu 22 → −184 $, 60 dk kontrolü 32 → −175 $, acil stop JCT −95 $, kâr al 21 → +138 $.
- İlk 5 zarar −171 $ (06.11 15:50–16:22 TR, stopsuz dönem B).
- ±VOL60 (E–F) 38 işlem −115 $: 6 kazanan (başa baş %35); 60 dk kontrolünde 25 satışın 25'i "+%0,14 kârda değil" şartından.
- VOL60 girişten sonraki saatten büyük: 60 dk'da +1'e değme 5/38, −1'e 11/38 (önceki 25 sa tabanı %39 / %35).
Önceki inceleme: [[allreview-2026-11-07]]. Bot: [[binanced-paper-service]].

13:20 TR ek (RAPOR.md §9–§11, gate_now.py, why_signal.py): şu anki kurallarla 0 işlem; 12:20–13:15 TR 12 kararda tüm şartı geçen 0
(en çok eleyen LC ≥ 2 %12; akış şartları kalan ≈2'yi 0'a indiriyor; bağımsız hesap 360/360 aynı). Sinyal ölçümü (17 saat, 192 karar):
"son 4 sa artıda" geçenler 60 dk'da −0,10 ± 0,09, 120 dk'da −0,20 ± 0,14 puan GERİDE; puan ρ ≈ 0; çıkışlar tut-60'a göre −13 $ (stoplar).
Kayıp girişten; akış şartları için ~24 saat kayıt gerek (60 dk sonucu olan 0).

13:45 TR ek (RAPOR.md §12–§13, burst.py, tide.py, tide_all.py): 06.11 15:00 TR 7/7 kâr al = piyasa dalgası (30 coinin 26'sı hedefe değdi;
15:20–15:30 BTC vadeli alım dalgası 2,4× hacim, %71 alıcı, spot küçük, OI +%0,36; haber yok, NFP 16:30 TR; 16:05'te geri verildi).
Tüm veride: 30 dk'da coin hareketinin %64'ü piyasa; 86 işlemde piyasa kısmı −97 $, seçim −99 $; işlemlerin 53/86'sında piyasa düştü;
±%0,4 dalga 49 kez (≈ saatte 1), yükselişlerin 16/25'i 60 dk'da geri döndü; hiçbir ölçü dalgayı önceden göstermedi (RET_4 −0,35 sınırda).

14:00 TR ek (RAPOR §14, candidates.py): DÜZELTME "düşünce al" izi yok (anlık tetik 16/31 yukarı). En çok düşen 3 coin listeye göre +0,13/+0,28
(60/120 dk) ama mutlak +0,05/+0,15 < masraf 0,17; düşen3 al − yükselen3 sat +0,35 ± 0,23 / +0,55 ± 0,29 (tek masrafı geçen yapı, 17 saat).
Engel etiketi etkisiz. Kullanıcıya çıkar/ekle listesi + A (uzun-kısa demo) / B (sadece liste) / C (işlemi durdur, ölç) soruldu.

14:30 TR öz denetim (RAPOR §15): masraf eşiği %0,17 değil ≈ %0,12–0,14 (komisyon 0,053 + demo 0,063–0,091); al-sat 120 dk üst üste
binmeyen ≈ 7 sepetle +0,58 ± 0,59 (60 dk +0,38 ± 0,32, ≈ 15 sepet) — önce ± 0,29 / "14/15" diye fazla kesin sunuldu; ≈ 40 ölçüden en
iyisi seçildi (seçim yanlılığı). Ders: çakışan pencerede bağımsız birim say, çoklu denemeyi söyle, masrafı veriden hesapla.

07.11 15:47 TR: bu araştırmadan çıkan al-sat sepeti demoda ~1,5 saat denendi, kullanıcı beğenmedi, iptal + tüm izi silindi; yeniden önerme ([[binanced-paper-service]]).
