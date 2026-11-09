---
name: birb-doymus-2026-11-08
description: "08.11 11:10 TR BIRB \"doymuş coine long\" incelemesi; 4 seçenek önerildi, kullanıcı cevabı bekleniyor"
metadata:
  node_type: memory
  type: project
  originSessionId: 0928f2db-5087-4522-89b2-96be2db0abca
  modified: 2026-11-08T08:14:10.462Z
---

08.11 ~11:10 TR kullanıcı: BIRB şartları sağladı ama koşusunu bitirmiş ("doymuş"), long açtık, hemen düştü.
İşlem: karar 10:55 TR, giriş 0,09073, 11:02:54 zarar_stop 0,08996, **−13,88 $** (−5 $ stop döneminin 25 stopundan en kötüsü;
22'si −7 $'dan iyi). Sebep 1: 10:10–10:35 +%2,4 koşu, 10:35–10:55 tepede yatay, girişte 60 dk tepesinin %0,70 altında, LC 6.
Sebep 2: 11:02'de 1 dk'da −%0,7; stop MARK_PRICE ve demo işaret fiyatı ~1 dk geç kaldı (demo son fiyat 0,0899'dayken tetik 0,09043).
Canlı kayıt (141 long, gerçek fapi 1 dk mum, scratchpad doymus/): son 6 adet 5 dk mumun ≥5'i yeşil → 21 işlemde 3 kazanan (%14,
diğerleri %31), ama 1.500 $ işlemde $ farkı yok (−2,4 vs −2,7 $/işlem); BIRB bu ölçüde 4/6 (durdurmazdı). 60 dk tepesinden
≥ %0,5 aşağıda giriş: 47 işlem ort −%0,44 vs −%0,16 (sonraki 30 dk'da fark şanstan ayırt edilemez, p≈0,1).
Önerilen seçenekler (cevap yok): 1) ≥5/6 yeşil mumsa girme, 2) 60 dk tepesinden > %0,5 aşağıdaysa girme, 3) stop tetiği son fiyat
(CONTRACT_PRICE), 4) hiçbiri. Eşikler Claude'un seçimi.

**How to apply:** kullanıcı seçerse kural + KURALLAR.md + verify yolu ([[binanced-paper-service]]); seçmezse açık iş olarak taşı.
