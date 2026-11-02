# Modüller arası sözleşmeler

Bu dosya modüllerin birbirine verdiği veri biçimlerini ve zaman kuralını sabitler. SPEC.md tek kaynaktır; burası
yalnızca SPEC'in açık bıraktığı uygulama ayrıntılarını tek bir yerde karara bağlar. Buradaki her karar bir
**varsayımdır** ve ilgili kodda da yorum olarak belirtilir.

## 1. Zaman kuralı

- Tüm zamanlar UTC'dir. Parquet ve pandas nesnelerinde **tz-naive `datetime64[ns]` = UTC** kullanılır.
- **Gün etiketi t** = `open_time` değeri t 00:00 UTC olan günlük mum. Bu mumun kapanışı C(t), t+1 00:00 UTC'de bilinir.
- **t günündeki karar** (SPEC: "t kapanışıyla") yalnızca gün etiketi ≤ t olan satırları kullanır.
- **Dolum:** t günündeki kararın emirleri, `open_time` ∈ [t+1 00:00, t+1 02:00) olan iki 1 saatlik mumun
  VWAP'ı ile dolar: VWAP = Σ quote_volume / Σ volume. Pencerede hacim sıfırsa bir sonraki saat eklenir.
  Backtest döngüsündeki "t−1 kapanışında oluşturulan emirleri t günü 00:00–02:00'da gerçekleştir" ile aynı şeydir.
- **Evren zamanlaması:** ay M'nin evreni, M'den önceki ayın son günlük mumu (gün etiketi T = M−1 ayının son günü)
  kapanışıyla kurulur ve T günündeki karardan itibaren geçerlidir. Yani **t günündeki karar, (t + 1 gün)'ün ayının
  evrenini kullanır.**
- **Haftalık giriş:** pozisyonu artıran işlemler yalnızca gün etiketi pazar olan karar gününde yapılır
  (`weekday() == 6`); dolum pazartesi 00:00–02:00.

## 2. Ham veri ve defter (G1–G2, `trend.data`)

- Ham zip'ler arşiv yolunu aynalar: `data/raw/{monthly|daily}/klines/{SYM}/{INT}/{SYM}-{INT}-{...}.zip`
  (arşivdeki `data/spot/` öneki atılır).
- `data/ledger.csv` kolonları: `rel_path, url, sha256_expected, sha256_actual, size_bytes, downloaded_at_utc, status`
  (`status` ∈ ok | checksum_mismatch | missing_remote | error). Aylık yeniden kontrol aynı defteri günceller.
- `meta/symbols_raw.csv` kolonları: `symbol, quote, base, interval, first_month, last_month, n_monthly_files`
  (S3 listelemesinden; her sembol × aralık bir satır). `base` = sembolden `quote` soneki atılmış hali.
- `meta/exchange_info_{YYYYMMDD}.json`: o günkü `GET /api/v3/exchangeInfo` yanıtının ham kopyası.

## 3. Temiz veri (G3)

`data/clean/{interval}/{SYMBOL}.parquet` — **çift (pair) sembolü başına bir dosya**, şema:

| kolon | tip | not |
| --- | --- | --- |
| open_time | datetime64[ns] | UTC, tz-naive, sıralı, benzersiz |
| open, high, low, close | float64 | |
| volume | float64 | taban varlık |
| close_time | datetime64[ns] | |
| quote_volume | float64 | |
| number_of_trades | int64 | |
| taker_buy_base, taker_buy_quote | float64 | |
| half_day | bool | çiftin ilk ve son mumu (SPEC: yarım gün işareti) |

`ignore` kolonu atılır. µs/ms dönüşümü burada yapılır (değer > 1e14 ise /1000).

## 4. Birleştirilmiş seriler (G5, `trend.meta`)

`meta/symbol_map.csv` uygulandıktan sonra **varlık kimliği (asset_id)** başına bir seri:
`data/merged/{interval}/{ASSET_ID}.parquet`, şema temiz veriyle aynıdır, ek kolon: `source_symbol` (o satırın geldiği çift).

- asset_id = varlığın **güncel** USDT çift sembolü (ör. RNDR geçmişi `RENDERUSDT` altında birleşir).
- ASSET_CHANGE ile bölünen eski seri: `{SYMBOL}_until_{YYYYMMDD}` (ör. `LUNAUSDT_until_20220513`).
- Haritada olmayan çiftler için asset_id = çift sembolü.
- Birleştirme kuralı (SPEC): eski fiyat / oran, eski taban hacim × oran, quote hacim değişmez.
- `meta/asset_segments.csv`: `asset_id, source_symbol, start, end, ratio` — her varlığın hangi çiftlerden oluştuğu.

`meta/symbol_map.csv` kolonları (SPEC): `old_symbol, new_symbol, type, ratio, old_last_trade_utc,
new_first_trade_utc, source, verified` (`type` ∈ RENAME | REDENOM | ASSET_CHANGE | MERGE_INTO_EXISTING | DELIST;
`verified` ∈ yes | candidate). Semboller USDT çift adıyla yazılır (ör. `RNDRUSDT`).

Diğer meta tablolar: `meta/fee_promotions.csv` (`symbol, start, end, source`),
`meta/delist_announcements.csv` (`symbol, announced_utc, delist_utc, kind, source`; `kind` ∈ delist | monitoring_tag).

## 5. Kalite işaretleri (G4, `trend.quality`)

`data/quality_flags.parquet`: `symbol, check, period_start, period_end, known_from, severity, detail`.
`symbol` = çift sembolü. `known_from` = işaretin üretilebildiği en erken gün etiketi (genellikle `period_end`).
T günündeki karar yalnızca `known_from ≤ T − 1` olan işaretleri kullanır. `severity` ∈ error | exclude | flag.

## 6. Evren (G6, `trend.universe`)

`universe/{YYYY-MM}.csv`: `symbol, rank, median_liquidity, tier, cap, slippage` — `symbol` = asset_id.
`universe/usdt_only/{YYYY-MM}.csv`: T7 varyantı, aynı şema.

## 7. Panel (bellek içi biçim)

`trend.data.panel.load_panel(interval, symbols=None, source="merged"|"clean")` →
`dict[str, pd.DataFrame]`, anahtarlar `open, high, low, close, volume, quote_volume, trades`; her DataFrame
index = gün/saat etiketi (tz-naive UTC `DatetimeIndex`), kolonlar = asset_id. Eksik değer NaN'dır, taşınmaz
(boşluk kuralı motorda uygulanır).

## 8. Geleceği görme koruması

- Strateji ve evren kodu, t günündeki karar için yalnızca index ≤ t olan veriyi görmelidir.
- Motor stratejiye veriyi **t'de kesilmiş görünüm** olarak verir; kesilmemiş paneli strateji koduna geçirmez.
- Zorunlu test 1: t sonrasındaki fiyat ve meta veri rastgele bozulduğunda t'ye kadarki tüm kararlar aynı kalmalı.
