# Değişiklik 31: C3 "sert saatlik hareketi geri al" — VPS'teki Claude için uygulama talimatı

Bu dosya VPS'te (`/root/binanced`) çalışan Claude Code'a verilmek için yazıldı. Kullanıcı bu talimatın uygulanmasını istiyor.
Kuralın gerekçesi ve testleri: `v9live/raporlar/ajan_arastirma_2026-11-09.md`, `v9live/raporlar/kayan_pencere_2026-11-09.md`.

## 0. Önce bil

- **Hesap:** yalnızca DEMO (`demo-fapi.binance.com`). Sinyal ve fiyat gerçek piyasadan (`fapi.binance.com`, herkese açık).
- **Servis:** `v9-demo` 08.11 16:38 UTC'den beri durdurulmuş ve `disable` edilmiş. Açık pozisyon ve açık emir yok.
  Başlatmadan önce yine de borsadan doğrula.
- **Bu bir İLERİ TEST.** Kural 3 günlük veride bulundu. Kanıt zayıf: yaklaşık 6 oynak döneme dayanıyor. Bu yüzden kural
  **dondurulur**. Test boyunca eşik, pencere, süre ve coin sayısı DEĞİŞTİRİLMEZ, kurala filtre EKLENMEZ.
  - Kullanıcı değişiklik isterse, bunun testi sıfırlayacağını söyle.
  - Kullanıcı yine de isterse, ayrı bir "Değişiklik 32" olarak yaz ve olay sayacını sıfırla.
- Repodaki alışkanlıklar sürer:
  - Her değişiklikten önce `*.bak_YYYYMMDD_HHMM` yedeği alınır.
  - `KURALLAR.md`'ye "Değişiklik 31" bölümü yazılır.
  - Bağımsız denetim aracı yazılır; `bot.py` içe aktarılmaz.
  - Önce `--dry` çalıştırılır.
  - Servis, kullanıcı onay verince başlatılır.

## 1. Tam ayarlar

| Ayar | Değer | Not |
|---|---|---|
| Coin listesi | DEĞİŞMEZ: `universe_24h` (24 sa USDT hacmine göre ilk 30, VOL60 ≤ %2, demo'da TRADING) | Her dakika yenilenir |
| Karar zamanı | DEĞİŞMEZ: her 5 dk (`DECIDE_STEP_MS`), dakika kapanışından 12 sn sonra (`MIN_DELAY_S`) | |
| Pencere | `C3_W_MIN = 60` dk | |
| Ölçek penceresi | `C3_SIG_MIN = 1440` dk (24 sa), en az `C3_SIG_MINN = 240` değer | |
| Eşik | `C3_Z = 1.0` → \|z\| > 1,0 | |
| Çalkantı | `C3_VOL_MIN = 60` dk (en az 40 değer); ortanca penceresi 1440 dk (en az 240 değer) | |
| Beta penceresi | `C3_BETA_MIN = 240` dk, en az `C3_BETA_MINN = 120` değer, `[-1, 4]` aralığına kırpılır | |
| Coin sayısı | `C3_N = 4` | |
| Hariç | `C3_EXCLUDE = ("BTCUSDT", "ETHUSDT")` | Piyasa ortalamasına girerler, işleme girmezler |
| Yön | z > 0 → **SHORT**, z < 0 → **LONG** (hareketin tersi) | |
| Büyüklük | DEĞİŞMEZ: `NOTIONAL = 1500` $ / coin, `LEV = 10`, izole | |
| Giriş | **MARKET** (taker) | Eski GTX / kovalama yolu kullanılmaz |
| Çıkış | Karar anından ≥ 60 dk sonraki ilk karar turunda **MARKET reduceOnly** (`C3_HOLD_MIN = 60`) | |
| Acil stop | `C3_ESTOP = 0.03`. Long: giriş × 0,97 (aşağı tick); short: giriş × 1,03 (yukarı tick). STOP_MARKET, `closePosition`, `workingType=MARK_PRICE` | Dolumdan hemen sonra konur |
| Kâr al | **YOK** | |
| Aynı anda | Tek olay, yani en çok 4 pozisyon | `SLOTS = 4` aynı kalır |
| Yeni olay | Önceki olayın 4 pozisyonu da kapandıktan sonraki karar turundan itibaren | Kapanış turunda yeni olay açılmaz |
| KAPATILANLAR | 60 dk kontrolü (`kayan_kontrol`), ek süre (Değ. 29), ters sıçrama çıkışı (Değ. 30 `spike_check`), kâr al +5 $, zarar stopu −5 $, eski giriş şartları ve puanla giriş, "short kapatma + spotsuz" engeli, fiyat adımı engeli | Bayrakla kapat, kodu silme (bkz. §6) |
| AÇIK KALANLAR | Liste, defter arşivi (`sample_depth`, `book/`), `depth`, `uni24`, fonlama düzeltmesi (`funding_fix`), Telegram, `trades` kaydı | |

## 2. Kural, formülle

`t` = karar anı (dakika sınırı, ms). `U` = o anki liste (`self.universe`). Mumlar `self.m1[sym]` (gerçek piyasa 1 dk;
`load_m1`). `c_i(m)`, i coininin m anında BİTEN mumunun kapanışıdır, yani `self.m1[sym][m - M][2]`.

```
# 1) Piyasanın dakikalık getirisi (eşit ağırlıklı, log)
mk1(m) = ortalama_i∈U [ ln(c_i(m) / c_i(m − 1 dk)) ]      # yalnız iki kapanışı da olan coinler; hiç yoksa 0
         m = t − 1500 dk … t

# 2) Son 60 dk piyasa hareketi ve ölçeği
P60(m) = Σ_{k = m−59 … m} mk1(k)                          # m anında biten 60 dakika
σ      = std_örneklem( P60(m) : m = t − 1440 dk … t − 1 dk )   # ddof = 1, en az 240 değer; şu anki P60 DAHİL DEĞİL
z      = P60(t) / σ

# 3) Çalkantı filtresi
vol60(m) = std_örneklem( mk1(k) : k = m−59 … m )          # en az 40 değer
volmed   = ortanca( vol60(m) : m = t − 1439 dk … t )       # şu anki DAHİL, en az 240 değer
çalkantı = vol60(t) > volmed

# 4) Beta (her aday coin için, son 240 dk)
r_i(k) = ln(c_i(k) / c_i(k − 1 dk)),  k = t − 239 … t
beta_i = cov_pop(r_i, mk1) / var_pop(mk1)                  # yalnız r_i'nin olduğu dakikalar, en az 120; [−1, 4] aralığına kırp

# 5) Karar
eğer açık C3 pozisyonu varsa       → yeni olay yok
eğer σ, z, vol60, volmed ölçülemiyorsa → olay yok
eğer |z| > 1,0 ve çalkantı:
    yön    = SHORT eğer z > 0, LONG eğer z < 0
    adaylar = U − {BTC, ETH} içinde beta'sı ölçülen, demo'da TRADING, şu an pozisyonu olmayan coinler
    sırala  = beta büyükten küçüğe
    sırayla 4 coine MARKET giriş; biri hata verirse sıradakine geç (aynı turda, en çok 4 başarılı giriş)
```

Testteki tanımla aynıdır. Testte piyasa ortalaması o dakikadaki listeyle alındı; burada geçmiş dakikalar da ŞU ANKİ listeyle
hesaplanıyor. Bu fark küçüktür ve kabul edilmiştir. Bot yeniden başlarsa durum `m1` mumlarından yeniden kurulur, ısınma
gerekmez.

## 3. Emirler

- **Giriş** (yeni yöntem, ör. `c3_enter(sym, t, side, feats)`):
  1. `margin_type(sym, "ISOLATED")` ve `leverage(sym, LEV)` geri okuması, mevcut `enter()`'deki gibi.
  2. Adet = `floor(NOTIONAL / fiyat, step)`. Fiyat long'da demo en iyi satış, short'ta demo en iyi alış.
  3. MARKET emir (BUY long / SELL short). Adet `MARKET_LOT_SIZE` (`f.mmax`) üstündeyse, `exit_market`'teki gibi parçalara böl.
  4. Dolum ortalaması ve adet `userTrades` ya da emir yanıtından (`avgPrice` / `cumQuote`) okunur. `avgPrice` 0 ise
     Değ. 10'daki `absorb` dersini uygula: yanlış değerle toplama.
  5. `Pos`'a yaz: `status="open"`, `fill_ms`, `entry`, `filled_qty`, `side`, `decision_ms = t`, yeni alan `c3_exit_ms = t + 60 dk`.
  6. Acil stopu koy: `STOP_MARKET closePosition MARK_PRICE`, tetik §1'deki gibi. `-2021` (hemen tetiklenir) gelirse
     `exit_market(p, "c3_acil_stop")`.
- **Çıkış:** `decide(t)` başında, `t ≥ p.c3_exit_ms` olan her C3 pozisyonu için `exit_market(p, "c3_sure")`.
  `exit_market` acil stopu (`es_cid`) iptal eder.
- **Acil stop tetiklenirse:** pozisyon adedi 0 olur. `finalize` sebebi `c3_acil_stop` yazmalı (algo emir FINISHED).
- **Çıkış sebepleri:** `c3_sure`, `c3_acil_stop`. `REASON_TR`'ye ekle: "60 dk doldu (C3)", "acil stop %3 (C3)".

## 4. Bilinen tuzaklar (bot.py'ye özgü)

1. **`monitor()` kâr al olmayan açık pozisyonu "giriş sürüyor" sanar.** İlk döngü `p.status == "open" and not p.tp_cid`
   koşulunu girişte sayıyor ve `cur_cid` ile emir sorguluyor. C3'te kâr al yok. C3 pozisyonları (ör. `p.c3_exit_ms > 0`)
   ilk döngüden çıkarılmalı, ikinci döngüye (adet 0 → `finalize`) alınmalı. İkinci döngüdeki `reset_estop` C3'te
   çağrılmamalı: −5 $ stop formülü (`estop_px`) C3'e uymaz.
2. **`spike_check()`** her dakika açık pozisyonu ters sıçramada kapatır. C3 pozisyonlarında çalışmamalı.
3. **`decide()`'nin eski yolu** (60 dk kontrolü, ek süre, puan, giriş) C3 açıkken hiçbir emir göndermemeli. İstersen
   `features()` ve `scores` kaydı araştırma için sürebilir; ama karar yolu C3'e gitmeli.
4. **`state.json` / `Pos(**p)`:** yeni alanlar (`c3_exit_ms`, gerekirse `strategy`) varsayılan değerle eklenmeli. Eski koda
   geri dönülürse bu alanlar `Pos(**p)`'yi bozar (Değ. 29'daki not); önce silinmeli.
5. **`reconcile()` başlangıçta** C3 pozisyonlarını tanımalı. Süresi geçmişse ilk turda kapatmalı.
6. **`run()` açılış mesajı** C3 kuralını yazmalı. Eski uzun metin C3 açıkken gösterilmemeli.
7. `STOP_ON`, `TP_NET_ALL`, `place_tp`, `place_estop` eski yolları C3 pozisyonu için çağrılmamalı. C3'ün kendi stop
   yöntemi olmalı.

## 5. Kayıt

- **Yeni tablo** `c3_decisions(ts, n_coins, p60, sigma, z, vol60, volmed, side, fired, skip_reason, picks)`.
  - Her 5 dk'lık kararda bir satır yazılır, olay olmasa da.
  - `picks` = JSON `[{"sym", "beta", "entered", "error"}]`.
  - `skip_reason`: `acik_olay`, `olculemedi`, `esik_alti`, `sakin`, `aday_yok`.
- **`trades`:** mevcut sütunlar. `reason` = `c3_sure` / `c3_acil_stop`. `feats` = `{"C3": 1, "Z", "P60", "SIGMA", "VOL60",
  "VOLMED", "BETA", "EVENT_TS"}`. `score` = beta.
- **journal:** her kararda tek satır, ör. `C3 piyasa son 60 dk +0,82% (30 coin), σ 0,61% → z +1,34, çalkantı 0,071% > 0,055%
  ✓ → SHORT: ARB(β 1,9) INJ(1,8) …` ya da `→ olay yok (eşik altı)`.
- **Telegram:** olay açılınca tek mesaj (yön, 4 coin, z), her pozisyon kapanınca mevcut ÇIKTI mesajı, olay bitince olayın
  toplam neti ve olay sayacı (`olay 7/40`).

## 6. Kod düzeni

- `bot.py`'ye bir bayrak ekle: `C3_ON = True`. False iken bot tam olarak Değ. 30 gibi davranmalı.
- Eski kodu SİLME. Kullanıcının daha önceki kuralı "iptal edilen kuralın kodu ve metni silinsin" idi. Ama bu bir iptal
  değil, ileri test. Kullanıcıya sor: "eski karar kodu bayrakla kapalı dursun mu, silinsin mi?" Varsayılan: dursun.
- C3 hesabını **saf fonksiyon** olarak yaz, ör. `c3_signal(closes: dict[str, dict[int, float]], universe, t) -> dict`.
  Böylece borsasız test edilebilir.

## 7. Testler (gerçek emir yok)

1. **Birim:** `c3_signal`'ı yapay mumlarla dene:
   - düz piyasa → olay yok;
   - +%1 sert yükseliş + yüksek oynaklık → SHORT, en yüksek betalı 4 coin;
   - aynası → LONG;
   - sakin (vol60 ≤ volmed) → olay yok;
   - eksik veri → ölçülemedi;
   - BTC / ETH asla seçilmez.
2. **Bağımsız denetim aracı** `v9live/audit/c3_check.py` (`bot.py`'yi içe aktarmaz):
   - Bir `c3_decisions.ts` için o anki listeyi `uni24`'ten alır.
   - Gerçek fapi 1 dk mumlarını REST'ten çeker.
   - p60, σ, z, vol60, volmed ve betaları sıfırdan hesaplar, kayıtla karşılaştırır (fark ≤ 1e-9; liste farkı varsa söyle).
   - Yön ve seçilen 4 coin aynı olmalı.
3. **Sahte borsayla tam ömür:**
   - MARKET giriş → acil stop konuldu mu (long 0,97 / short 1,03, doğru tick yönü, closePosition, MARK_PRICE);
   - 60 dk sonra MARKET reduceOnly kapanış → stop iptali → `trades` satırı;
   - acil stop tetiklenince `c3_acil_stop`;
   - `-2021` dalı;
   - giriş hatasında sıradaki coine geçiş;
   - açık olay varken yeni olay yok.
4. **`bot.py --dry`:** o anki z, çalkantı, seçilecek 4 coin. Emir yok. Sonuç `dry_run.db`'deki `c3_decisions`'a yazılır ve
   `c3_check.py` ile fark 0 olmalı.

## 8. Devreye alma (kullanıcı onayıyla)

1. Borsada pozisyon 0 ve açık emir 0 olduğunu doğrula (`audit/exch_check.py` ya da positionRisk / openOrders).
2. Yedekler: `bot.py`, `verify.py`, `status.py`, `KURALLAR.md` → `*.bak_YYYYMMDD_HHMM`.
3. `KURALLAR.md`'ye "Değişiklik 31" bölümünü yaz: §1 tablosu, §2 formülü, gerekçe (rapor dosyaları), "ileri test,
   dondurulmuş", durdurma kuralları. Başa yaz: eski kurallar C3 açıkken geçersiz. README'nin "Son kural" bölümünü güncelle.
4. `status.py`'ye C3 özeti ekle: olay sayısı, olay başına net, toplam net, long/short, sebepler.
5. Kullanıcıya özet ver ve sor: "servisi başlatayım mı?" Onay gelirse `systemctl enable --now v9-demo`, sonra
   `journalctl -u v9-demo -f` ile ilk 2 kararı izle.
6. İlk olaydan sonra:
   - `c3_check.py` o olayın kararını denetler (fark 0);
   - borsadaki adet, giriş ve stop seviyesi botla aynı mı (`exch_check`);
   - sonuç kullanıcıya yazılır.

## 9. Durdurma ve değerlendirme (önceden yazıldı, test boyunca değişmez)

- **Olay** = bir karar turunda açılan C3 pozisyonları grubu.
- **Erken durdurma 1:** 20 olay tamamlandığında toplam net < 0 ise yeni olay açma, kullanıcıya bildir (servis durdurulmaz,
  açık olay biter).
- **Erken durdurma 2:** toplam net (tüm C3 işlemleri, komisyon dahil) < −400 $ olursa aynı şekilde dur.
- **Değerlendirme:** 40 olayda. Şu dört soruya cevap verilir:
  1. Toplam net > 0 mı?
  2. Olayların > %50'si artı mı?
  3. Aynı anlarda rastgele 4 coinle aynı yönde girilseydi (betaya bakmadan) sonuç ne olurdu? Bu, `c3_decisions` ve mumlarla
     sonradan hesaplanır.
  4. Yön çevrilince (olay başına yön rastgele) sonucumuz dağılımın %95'inin üstünde mi?
- Değerlendirmeden önce **hiçbir parametre değişmez.**

## 10. Kullanıcıya söylenmesi gerekenler

- Bu kural 3 günde yaklaşık 6 oynak döneme dayanıyor. Kazanacağı kanıtlanmış değil; ileri test bunu ölçecek.
- Her olayda tek yönde 6.000 $ açılıyor. 3 günlük testte en kötü tek olay −259 $ idi.
- Uzun süren tek yönlü bir çöküşte ya da rallide kaybeder.
- Demo'da piyasa emri komisyonu %0,04 (gerçek %0,05). Demo defteri sığ olduğu için kayma gerçekten farklı olabilir.
