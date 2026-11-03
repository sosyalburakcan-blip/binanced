# Görev listesi — v4 gün içi momentum + canlı kâğıt takip (2026-11-03)

Kurallar: **gerçek emir yok** (yalnızca kâğıt işlem; gerçek emir kullanıcının API anahtarı ve hukuki şartıyla, onun
adımı). Her adım `experiments.md`'ye. G12 anlık görüntüsüne dokunma (`python -m uv run python -m trend.research.g12
verify` → ok). Ön kayıt dondurulmadan gerçek fiyat verisinde v4 ızgarası çalıştırılmaz. Komutlar proje kökünde,
`PYTHONIOENCODING=utf-8 python -m uv run ...`.

## A. v4 backtest (gün içi momentum, spot + 1×/2×/3×/5× vadeli)

1. [x] **Veri** `data/intraday/` (15 dk spot, 15 dk vadeli, fonlama; 57 bilinen coin): indirici
   `python -m uv run python -m trend.data.intraday --all` (kaldığı yerden devam eder; ajan yazdı:
   `src/trend/data/intraday.py`, `tests/test_data_intraday.py`). Bitince `data/intraday/inventory.csv` dolu olmalı;
   BTC/ETH için 15 dk'dan türetilen saatlik kapanış = `data/merged/1h` kapanışı; `g12 verify` ok.
2. [x] Simülatör `src/trend/intraday/sim.py` (22 test), çalıştırıcı `src/trend/intraday/study.py` (3 test),
   `research_v4.yaml`, `PREREGISTRATION_v4.md`, ücret/vergi araştırması `reports/V4_fees_tax.md`.
3. [x] `experiments.md` satır 23: v4 ön kaydı (Evet +1). Tüm testler (`pytest -q -p no:cacheprovider`). Commit
   (yeni dosyalar: GOREVLER.md, PREREGISTRATION_v4.md, research_v4.yaml, reports/V4_fees_tax.md,
   src/trend/intraday/*, src/trend/data/intraday.py, tests/test_intraday_*.py, tests/test_data_intraday.py,
   tests/fixtures/intraday/*). `git tag -a prereg-v4`. `data/intraday/` git'e girmez (gitignore'a ekle).
4. [ ] Bir kez: `python -m uv run python -m trend.intraday.study run` (arka planda; ~30–60 dk; kayıt
   `lock/V4_run.json`) → `python -m uv run python -m trend.intraday.study report` → `reports/V4_intraday_momentum.md`.
5. [ ] En iyi yapılandırma 1–6 ve 8. kriterleri geçerse: bağımsız kontrol ajanı (motoru görmeden, yalnız
   PREREGISTRATION_v4 + veriden sinyal ve işlem listesini yeniden hesaplar).
6. [ ] `reports/V4_ozet.md` (Türkçe, sade: en iyi liste, bekletme sonucu, kaldıraç–spot farkı, vergi), experiments
   satır 24, commit.

## B. Canlı kâğıt takip (websocket, anahtarsız herkese açık veri)

7. [ ] `src/trend/live/stream.py`: spot `wss://stream.binance.com:9443`, vadeli `wss://fstream.binance.com`;
   akışlar `kline_15m`, `bookTicker`, `depth20@100ms`, vadeli `markPrice@1s` (fonlama). Yeniden bağlanma (24 saatte
   bir kopma), ping/pong, saat senkronu (REST `/api/v3/time`), boşluk tespiti.
8. [ ] `src/trend/live/paper.py`: v4 en iyi 3 yapılandırma + BTC-200 kıyası; saat kapanışında sinyal (sim.py ile
   aynı fonksiyonlar); dolum emir defterinde yürüyerek (bizim emir büyüklüğümüzde VWAP), kâr al limit/zarar kes
   stop; komisyon (spot %0,10; vadeli yapıcı %0,02, alıcı %0,05), fonlama, kaldıraç 1×/2×/3× ve spot paralel kâğıt
   hesaplar; tasfiye işaret fiyatıyla.
9. [ ] Kayıt `data/live/live.db` (SQLite): sinyaller, kâğıt emirler, dolumlar, kayma (baz puan, varsayımla fark),
   defter anlık görüntüleri (işlem anında), hatalar/kopmalar. Günlük rapor `reports/live/YYYY-MM-DD.md`.
10. [ ] Tutarlılık: her gün canlı sinyaller = aynı saatlerin motor sinyalleri (fark → hata kaydı).
11. [ ] Çalıştırma: `python -m uv run python -m trend.live.paper` arka planda; otomatik başlatma kullanıcı onayıyla.
12. [ ] Haftalık: gerçekleşen kayma ve maliyet vs varsayım, kâğıt PnL vs backtest beklentisi; 1–3 ay sonra maliyet
    sonucu, 6–12 ay sonra kârlılık sonucu.
