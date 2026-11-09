# v9 demo botu — tüm bilgiler (06.11–08.11.2026)

**Yalnızca Binance DEMO hesabı** (`demo-fapi.binance.com`). Gerçek para hiç kullanılmadı.
Sinyal ve fiyat verisi gerçek piyasadan (herkese açık `fapi.binance.com`), emirler demo defterine gitti.

**Durum: DURDURULDU.** 08.11.2026 16:38 UTC'de `v9-demo` servisi durduruldu ve kapatıldı (`disable`).
Açık işlemler elle kapatıldı; demo hesapta pozisyon 0, emir 0, bakiye 4.242,60 USDT
(ayrıntı: [MANUEL_KAPANIS_2026-11-08.md](MANUEL_KAPANIS_2026-11-08.md)).

## Canlı (demo) kayıt özeti — `live.db` `trades` tablosu

| | |
|---|---|
| İlk dolum → son çıkış | 06.11 08:00 UTC → 08.11 16:15 UTC |
| İşlem sayısı | 175 (163 LONG, 12 SHORT) |
| Kazanan | 49 (%28) |
| Toplam net K/Z | **−525,55 $** (komisyon −131,26 $, fonlama −2,00 $ dahil) |
| Gün gün | 06.11: 57 işlem −215,72 $ · 07.11: 60 işlem −176,68 $ · 08.11: 58 işlem −133,14 $ |

Not: durdurma sonrası elle kapatılan ETH/HYPE (≈ −2,8 $) `live.db`'de yok. İptal edilip izi silinen
Değişiklik 19 yüzünden `live.db` toplamı demo bakiyesinden +1,16 $ farklıdır.

Çıkış sebebine göre: zarar_stop 59 (−414,29 $), kayan_kontrol 50 (−229,63 $), kâr_al 41 (+243,27 $),
ters_sıçrama 9 (−23,75 $), saatlik_kontrol 6 (−7,19 $), ek_kontrol_düştü 3 (−10,92 $),
kullanici_kapatti 3 (+1,68 $), bilinmiyor 2 (+8,89 $, telefondan elle kapatma), ek_kontrol_kâr 1 (+0,97 $),
acil_stop 1 (−94,57 $).

## Son kural (Değişiklik 30, 08.11 07:01 UTC)
Tam metin ve tüm değişiklik geçmişi (Değişiklik 1–30, saatleri ve kullanıcının sözleriyle): **[KURALLAR.md](KURALLAR.md)**.
Kısaca: liste = 24 sa hacme göre ilk 30 coin; 5 dk'da bir karar; LONG ve SHORT (birbirinin aynası);
en fazla 4 pozisyon; 1.500 $ pozisyon (150 $ teminat × 10); kâr al net +5 $, zarar stopu −5 $ (borsada);
girişten 60 dk sonra kontrol (+ Değ. 29 ek süre); açıkken son 2 dk'da ters yöne ≥ %0,20 sıçrama → kapat.

## Dosyalar

| Yol | Ne |
|---|---|
| `bot.py` | Botun kendisi (tek dosya). `--dry` = emir yok, yalnız ölçüm (`dry_run.db`) |
| `KURALLAR.md` | Kurallar + tüm değişiklik/düzeltme geçmişi |
| `status.py` | Özet rapor (`python v9live/status.py`) |
| `verify.py` | Bağımsız denetim (özellikler, liste, akış, defter) |
| `audit/` | Denetim araçları: decide_check, closed_check, pnl_check, bracket_check, real_fill_check, spike_check, label_check, grace_check, exch_check … |
| `v9-demo.service` | systemd birimi |
| `state.json` | Durma anındaki bot durumu (açık pozisyonlar o an) |
| `universe_2026-11.json` | İlk coin listesi |
| `live.db` | Tüm canlı kayıt (SQLite): trades, events, checks, scores, labels, depth, depth2, uni24, uni_excl, outcomes, spike_checks |
| `dry_run.db`, `dry_state.json`, `dry.out` | Deneme modu kayıtları |
| `veri_csv/` | `trades`, `events`, `checks`, `spike_checks` tablolarının CSV kopyası (kolay okuma) |
| `kayit/journal_v9-demo.log` | `journalctl -u v9-demo` tam günlüğü (06.11 06:21 → 08.11 16:38 UTC) |
| `raporlar/` | İşlem incelemeleri (allreview, fullreview, lossreview), oturum kayıtları (OTURUM_2026-11-07/08) |
| `raporlar/inceleme_2026-11-09.md` | 3 günün tamamının incelemesi (dönemler, sinyal ↔ rastgele, zarar kaynağı; defter arşiviyle) |
| `raporlar/claude_notlari/` | Çalışma sırasında tutulan notlar (kronolojik karar defteri) |
| `../src/trend/live/testnet.py`, `exchange.py`, `stream.py`, `notify.py` | Botun kullandığı imzalı demo istemcisi, borsa filtreleri, Telegram bildirimi |

**Tam emir defteri arşivi** (`book/2026-11-06…08.db`, ~790 MB; her dakika 30 coin, Binance yanıtı bayt bayt lzma)
git'e sığmadığı için bu reponun **Release**'inde: `v9live_book.tar.zst` (açmak: `tar -I zstd -xf v9live_book.tar.zst`).

## Repoda OLMAYANLAR (bilerek)
- API anahtarları, özel anahtar (`.pem`), Telegram token/chat id — `.env.testnet`, `.env.bildirim` hiç eklenmedi;
  paket gerçek anahtar değerlerine karşı bayt bayt tarandı, bulgu yok. VPS IP adresi `<VPS_IP>` ile değiştirildi.
- `*.bak_*` yedek dosyaları (her sürümün metni `KURALLAR.md` geçmişinde var) ve `__pycache__`.

## Çalıştırma (yeniden kurmak isterseniz)
```bash
uv sync                                   # bağımlılıklar (numpy, pandas, requests, cryptography)
# proje kökünde .env.testnet: BINANCE_TESTNET_API_KEY=…  BINANCE_TESTNET_PRIVATE_KEY_PATH=/yol/anahtar.pem
# isteğe bağlı .env.bildirim: TELEGRAM_BOT_TOKEN=…  TELEGRAM_CHAT_ID=…
.venv/bin/python v9live/bot.py --dry      # emir yok, yalnız ölçüm
```
`bot.py` içinde `ROOT = Path("/root/binanced")` sabit; başka klasörde çalıştırmak için bu satırı değiştirin.
İmzalı istemci yalnızca demo adreslerine istek atar (gerçek hesaba emir gidemez).
