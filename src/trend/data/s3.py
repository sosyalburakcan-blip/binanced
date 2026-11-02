"""G1 — sembol keşfi ve dosya envanteri (data.binance.vision S3 listelemesi).

Uç nokta Binance tarafından belgelenmemiştir (SPEC "Sembol keşfi"); yanıtlar XML'dir ve sayfalıdır
(`IsTruncated`, `NextMarker`). S3 her anahtarın `Size` değerini verdiği için toplam indirme boyutu tahmin değil,
kesin değerdir.

Çıktılar:
- `meta/symbols_raw.csv` (CONTRACTS §2): gereken her sembol × aralık bir satır.
- `{paths.raw}/_inventory.csv`: indirilecek her zip'in yolu, URL'si, boyutu (indirici bunu okur).
- `meta/exchange_info_{YYYYMMDD}.json`: günün `GET /api/v3/exchangeInfo` ham yanıtı.

CLI: `python -m uv run python -m trend.data.s3 [--symbols BTCUSDT,ETHUSDT] [--no-exchange-info]`
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from trend.config import load_settings, path
from trend.data import _http

NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
MONTHLY_ROOT = "data/spot/monthly/klines/"
DAILY_ROOT = "data/spot/daily/klines/"
ARCHIVE_PREFIX = "data/spot/"  # CONTRACTS §2: yerel aynada bu önek atılır
INVENTORY_NAME = Path(load_settings()["paths"]["inventory"]).name  # {paths.raw}/_inventory.csv
INVENTORY_COLS = ["rel_path", "url", "size_bytes", "last_modified", "symbol", "interval", "kind", "period",
                  "has_checksum"]
SYMBOLS_RAW_COLS = ["symbol", "quote", "base", "interval", "first_month", "last_month", "n_monthly_files"]


# --------------------------------------------------------------------------------------------- S3 listeleme
@dataclass
class Listing:
    prefixes: list[str]
    contents: list[dict]  # {key, size, last_modified}


def list_bucket(prefix: str, *, cfg: dict | None = None, marker: str | None = None,
                delimiter: str = "/") -> Listing:
    """Bir S3 önekini sayfalama ile tam listeler. `marker` verilirse ondan (sözlük sırasıyla) sonraki anahtarlar."""
    cfg = cfg or load_settings()
    d = cfg["data"]
    prefixes: list[str] = []
    contents: list[dict] = []
    while True:
        params = {"delimiter": delimiter, "prefix": prefix}
        if marker:
            params["marker"] = marker
        r = _http.get(d["s3_list_url"], params=params, max_retries=d["max_retries"],
                      backoff_base_s=d["backoff_base_s"])
        r.raise_for_status()
        root = ET.fromstring(r.content)
        page_pfx = [e.findtext(f"{NS}Prefix") for e in root.iter(f"{NS}CommonPrefixes")]
        page_cnt = [{"key": e.findtext(f"{NS}Key"), "size": int(e.findtext(f"{NS}Size")),
                     "last_modified": e.findtext(f"{NS}LastModified")} for e in root.iter(f"{NS}Contents")]
        prefixes += page_pfx
        contents += page_cnt
        if root.findtext(f"{NS}IsTruncated") != "true":
            break
        # NextMarker yalnızca delimiter verildiğinde döner; yoksa son anahtar/önek işaretçi olur (S3 v1 kuralı).
        nxt = root.findtext(f"{NS}NextMarker") or max([*page_pfx, *(c["key"] for c in page_cnt)], default=None)
        if not nxt or nxt == marker:
            break
        marker = nxt
    return Listing(prefixes, contents)


def list_symbols(root: str = MONTHLY_ROOT, cfg: dict | None = None) -> list[str]:
    """Arşivdeki tüm sembol dizinleri (ör. `data/spot/monthly/klines/BTCUSDT/` → `BTCUSDT`)."""
    return sorted(p[len(root):].rstrip("/") for p in list_bucket(root, cfg=cfg).prefixes)


# ------------------------------------------------------------------------------------------ sembol ayrıştırma
def parse_quote(symbol: str, other_quotes: list[str]) -> str | None:
    """Sembolün gereken quote varlığını döndürür; gereksizse None.

    Varsayım (sonek kuralı; borsa bilgisi olmadan tek mümkün kural):
    - Sembol `USDT` ile bitiyorsa quote = USDT (ör. `BUSDUSDT` → base BUSD, `USDCUSDT` → base USDC).
    - Değilse diğer quote'lar uzundan kısaya denenir (FDUSD, BUSD, TUSD, USDC; hiçbiri diğerinin soneki değil).
    - `USDTTRY`, `BTCUSDS` gibi semboller hiçbir gereken sonekle bitmediği için dışarıda kalır.
    Bu kural güncel exchangeInfo'daki baseAsset/quoteAsset ile `validate_against_exchange_info` ile kontrol edilir.
    """
    if symbol.endswith("USDT") and len(symbol) > 4:
        return "USDT"
    for q in sorted(other_quotes, key=len, reverse=True):
        if symbol.endswith(q) and len(symbol) > len(q):
            return q
    return None


def true_quotes(exinfo: dict | None) -> dict[str, str]:
    """exchangeInfo'dan sembol → gerçek quoteAsset (TRADING ve BREAK durumundaki tüm çiftler)."""
    return {x["symbol"]: x["quoteAsset"] for x in (exinfo or {}).get("symbols", [])}


def resolve_quote(symbol: str, other_quotes: list[str], tq: dict[str, str] | None = None) -> str | None:
    """Sembol exchangeInfo'da varsa gerçek quoteAsset kullanılır (gereken quote değilse None), yoksa sonek kuralı.
    G1 bulgusu: sonek kuralı tek başına `BNBUSD` (BNB/USD) → BUSD ve `USDTUSD` (USDT/USD) → TUSD hatası yapıyor;
    Binance 2025+ USD quote'lu çiftler açtı. exchangeInfo BREAK durumundaki eski çiftleri de içerdiğinden
    gereken 1760 sembolün 1757'si kapsanır; kalan 3'ü (NBTUSDT, USDSTUSD, USDSUSDC) sonek kuralıyla doğrudur."""
    if tq and symbol in tq:
        q = tq[symbol]
        return q if (q == "USDT" or q in other_quotes) and symbol.endswith(q) else None
    return parse_quote(symbol, other_quotes)


def needed_pairs(symbols: list[str], cfg: dict, tq: dict[str, str] | None = None) -> list[tuple[str, str, str]]:
    """(sembol, quote, aralık) listesi. USDT çiftleri 1d+1h, diğer quote'lar 1d, stable/USDT çiftleri 1d.
    Stable/USDT çiftleri zaten USDT çifti olduğundan 1h da iner (zararsız; SPEC "tüm USDT çiftleri 1d ve 1h")."""
    d = cfg["data"]
    out = []
    for s in symbols:
        q = resolve_quote(s, d["other_quotes"], tq)
        if q is None:
            continue
        ivs = list(d["intervals_usdt"]) if q == "USDT" else list(d["intervals_other_quotes"])
        if s in d["stable_usdt_pairs"]:
            ivs = list(dict.fromkeys(ivs + list(d["intervals_other_quotes"])))
        out += [(s, q, iv) for iv in ivs]
    return out


def validate_against_exchange_info(symbols: list[str], exinfo: dict, other_quotes: list[str]) -> pd.DataFrame:
    """Sonek kuralını exchangeInfo'daki (bugün listelenen + BREAK durumundaki) çiftlerle karşılaştırır.
    Dönen tablo uyuşmazlıklardır: sonek kuralı ile borsanın baseAsset/quoteAsset'i farklıysa."""
    info = {s["symbol"]: (s["baseAsset"], s["quoteAsset"]) for s in exinfo.get("symbols", [])}
    needed_q = {"USDT", *other_quotes}
    rows = []
    for s in symbols:
        q = parse_quote(s, other_quotes)
        if s not in info:
            continue
        b_true, q_true = info[s]
        q_true_needed = q_true if q_true in needed_q else None
        if q != q_true_needed or (q is not None and s[: -len(q)] != b_true):
            rows.append({"symbol": s, "rule_quote": q, "true_base": b_true, "true_quote": q_true})
    return pd.DataFrame(rows, columns=["symbol", "rule_quote", "true_base", "true_quote"])


# ------------------------------------------------------------------------------------------------- envanter
def _period_of(key: str, kind: str) -> str:
    stem = key.rsplit("/", 1)[-1][: -len(".zip")]
    parts = stem.split("-")
    return "-".join(parts[-2:]) if kind == "monthly" else "-".join(parts[-3:])


def _rows(contents: list[dict], symbol: str, interval: str, kind: str, archive_base: str) -> list[dict]:
    keys = {c["key"] for c in contents}
    out = []
    for c in contents:
        k = c["key"]
        if not k.endswith(".zip"):
            continue
        rel = k[len(ARCHIVE_PREFIX):]
        out.append({"rel_path": rel, "url": f"{archive_base}/{rel}", "size_bytes": c["size"],
                    "last_modified": c["last_modified"], "symbol": symbol, "interval": interval, "kind": kind,
                    "period": _period_of(k, kind), "has_checksum": f"{k}.CHECKSUM" in keys})
    return out


def _months_between(a: str, b: str) -> list[str]:
    p = pd.period_range(a, b, freq="M")
    return [str(x) for x in p]


def list_pair(symbol: str, interval: str, cfg: dict, latest_month: str | None,
              daily_only: bool = False) -> tuple[list[dict], list[str]]:
    """Bir sembol × aralık için gereken dosyalar: tüm aylık zip'ler + aylık dosyanın kapsamadığı günlük zip'ler.

    Günlük dosyalar için büyük günlük önek listelenmez:
    - son aylık dosyadan sonraki günler: `marker = {SYM}-{INT}-{YYYY}-{MM}-99` (o ayın tüm günlerinden büyük,
      sonraki ayın günlerinden küçük) ile yalnızca kuyruk listelenir;
    - aylık dizideki boş aylar: `prefix = ...{SYM}-{INT}-{YYYY}-{MM}-` ile yalnızca o ay listelenir.
    Varsayım: son aylık ayı global son yayımlanmış aydan (`latest_month`) 1 aydan fazla eski olan çiftler delist
    edilmiştir; bunlarda kuyruk listelemesi atlanır (verileri aylık dosyalarda tamamdır).
    Dönüş: (envanter satırları, aylık dizide boş kalan aylar).
    """
    base = cfg["data"]["archive_base"]
    rows: list[dict] = []
    gaps: list[str] = []
    dpfx = f"{DAILY_ROOT}{symbol}/{interval}/"
    if daily_only:
        return _rows(list_bucket(dpfx, cfg=cfg).contents, symbol, interval, "daily", base), gaps
    mon = list_bucket(f"{MONTHLY_ROOT}{symbol}/{interval}/", cfg=cfg).contents
    rows += _rows(mon, symbol, interval, "monthly", base)
    months = sorted(r["period"] for r in rows)
    if not months:
        return rows, gaps
    have = set(months)
    gaps = [m for m in _months_between(months[0], months[-1]) if m not in have]
    for m in gaps:
        rows += _rows(list_bucket(f"{dpfx}{symbol}-{interval}-{m}-", cfg=cfg).contents, symbol, interval, "daily",
                      base)
    if latest_month is None or pd.Period(months[-1], "M") >= pd.Period(latest_month, "M") - 1:
        tail = list_bucket(dpfx, cfg=cfg, marker=f"{dpfx}{symbol}-{interval}-{months[-1]}-99").contents
        rows += _rows(tail, symbol, interval, "daily", base)
    return rows, gaps


def build_inventory(cfg: dict | None = None, symbols: list[str] | None = None, progress: bool = True,
                    exinfo: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """S3'ü listeleyip (envanter, symbols_raw, özet) döndürür. `symbols` verilirse yalnız onlar (test/alt küme).
    `exinfo` verilmezse meta/ altındaki en yeni exchangeInfo kopyası kullanılır (yoksa indirilip kaydedilir)."""
    cfg = cfg or load_settings()
    tq = true_quotes(exinfo if exinfo is not None else latest_exchange_info(cfg))
    t0 = time.time()
    all_monthly = list_symbols(MONTHLY_ROOT, cfg)
    all_daily = list_symbols(DAILY_ROOT, cfg)
    universe = sorted(set(all_monthly) | set(all_daily))
    if symbols is not None:
        universe = [s for s in universe if s in set(symbols)]
    pairs = needed_pairs(universe, cfg, tq)
    monthly_set = set(all_monthly)

    # Global son yayımlanmış ay: BTCUSDT'nin aralık başına son aylık dosyası (en likit çift; her ay yayımlanır).
    latest: dict[str, str | None] = {}
    for iv in {iv for _, _, iv in pairs}:
        mon = list_bucket(f"{MONTHLY_ROOT}BTCUSDT/{iv}/", cfg=cfg).contents
        ks = sorted(_period_of(c["key"], "monthly") for c in mon if c["key"].endswith(".zip"))
        latest[iv] = ks[-1] if ks else None

    rows: list[dict] = []
    raw_rows: list[dict] = []
    gap_info: dict[str, list[str]] = {}
    done = 0

    def work(p):
        s, q, iv = p
        return p, list_pair(s, iv, cfg, latest[iv], daily_only=s not in monthly_set)

    with ThreadPoolExecutor(max_workers=cfg["data"]["concurrency"]) as ex:
        for (s, q, iv), (rws, gaps) in ex.map(work, pairs):
            done += 1
            rows += rws
            mon = sorted(r["period"] for r in rws if r["kind"] == "monthly")
            if not rws:  # dizin var ama dosya yok (ör. USDSOLDUSDT günlük dizini boş)
                continue
            raw_rows.append({"symbol": s, "quote": q, "base": s[: -len(q)], "interval": iv,
                             "first_month": mon[0] if mon else "", "last_month": mon[-1] if mon else "",
                             "n_monthly_files": len(mon)})
            if gaps:
                gap_info[f"{s}/{iv}"] = gaps
            if progress and done % 200 == 0:
                print(f"[s3] listelendi {done}/{len(pairs)} çift×aralık, {len(rows)} dosya, "
                      f"{time.time() - t0:.0f}s", flush=True)

    inv = pd.DataFrame(rows, columns=INVENTORY_COLS).sort_values("rel_path", ignore_index=True)
    raw = pd.DataFrame(raw_rows, columns=SYMBOLS_RAW_COLS).sort_values(["symbol", "interval"], ignore_index=True)
    summary = {"n_symbols_archive_monthly": len(all_monthly), "n_symbols_archive_daily": len(all_daily),
               "n_daily_only": len(set(all_daily) - monthly_set), "latest_month": latest,
               "n_pairs": len(pairs), "gaps": gap_info, "listing_seconds": round(time.time() - t0, 1),
               "all_symbols": universe}
    return inv, raw, summary


def save_exchange_info(cfg: dict, day: dt.date | None = None) -> tuple[Path, dict]:
    """`GET /api/v3/exchangeInfo` ham yanıtını meta/exchange_info_YYYYMMDD.json'a yazar."""
    day = day or dt.datetime.now(dt.UTC).date()
    r = _http.get(cfg["data"]["rest_base"] + "/api/v3/exchangeInfo", max_retries=cfg["data"]["max_retries"],
                  backoff_base_s=cfg["data"]["backoff_base_s"])
    r.raise_for_status()
    out = path(cfg, "meta") / f"exchange_info_{day:%Y%m%d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return out, json.loads(r.content)


def latest_exchange_info(cfg: dict) -> dict:
    """meta/exchange_info_*.json içinden en yenisi; hiç yoksa bugünkü indirilip kaydedilir."""
    files = sorted(path(cfg, "meta").glob("exchange_info_*.json"))
    if files:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    return save_exchange_info(cfg)[1]


def inventory_path(cfg: dict) -> Path:
    return path(cfg, "raw") / INVENTORY_NAME


def read_inventory(cfg: dict) -> pd.DataFrame:
    p = inventory_path(cfg)
    if not p.exists():
        raise FileNotFoundError(f"{p} yok; önce `python -m trend.data.s3` çalıştırın.")
    return pd.read_csv(p, dtype={"period": str, "symbol": str, "interval": str}, keep_default_na=False)


def write_atomic_csv(df: pd.DataFrame, p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    df.to_csv(tmp, index=False, lineterminator="\n")
    tmp.replace(p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="G1: S3 sembol keşfi ve dosya envanteri")
    ap.add_argument("--symbols", help="virgülle ayrılmış alt küme (varsayılan: gereken tüm semboller)")
    ap.add_argument("--no-exchange-info", action="store_true",
                    help="exchangeInfo'yu yeniden indirme (meta/ altındaki en yenisini kullan)")
    ap.add_argument("--no-symbols-raw", action="store_true",
                    help="meta/symbols_raw.csv'yi yazma (alt küme çalıştırmalarında otomatik)")
    a = ap.parse_args(argv)
    _http.utf8_stdout()
    cfg = load_settings()
    syms = a.symbols.split(",") if a.symbols else None
    if a.no_exchange_info:
        ex = latest_exchange_info(cfg)
    else:
        p, ex = save_exchange_info(cfg)
        print(f"[s3] exchangeInfo: {p} ({len(ex.get('symbols', []))} çift)", flush=True)
    inv, raw, summ = build_inventory(cfg, syms, exinfo=ex)
    summ_out = {k: v for k, v in summ.items() if k != "all_symbols"}
    if syms is None:
        # Alt küme envanteri tam envanterin üzerine yazmasın diye yalnız tam çalıştırmada yazılır.
        write_atomic_csv(inv, inventory_path(cfg))
        inventory_path(cfg).with_name("_inventory_summary.json").write_text(
            json.dumps(summ_out, indent=1), encoding="utf-8")
        if not a.no_symbols_raw:
            write_atomic_csv(raw, path(cfg, "meta") / "symbols_raw.csv")
    else:
        sub = inventory_path(cfg).with_name("_inventory_subset.csv")
        write_atomic_csv(inv, sub)
        print(f"[s3] alt küme envanteri: {sub}")
    bad = validate_against_exchange_info(summ["all_symbols"], ex, cfg["data"]["other_quotes"])
    print(f"[s3] sonek kuralı ile exchangeInfo uyuşmazlığı: {len(bad)} (exchangeInfo değeri kullanıldı)")
    if len(bad):
        print(bad.to_string(index=False))
    m, d = inv[inv.kind == "monthly"], inv[inv.kind == "daily"]
    print(f"[s3] arşivde sembol: aylık {summ['n_symbols_archive_monthly']}, günlük {summ['n_symbols_archive_daily']}"
          f" (sadece günlük {summ['n_daily_only']}); gereken çift×aralık {summ['n_pairs']}; "
          f"son aylık ay {summ['latest_month']}")
    print(f"[s3] aylık zip {len(m)} ({m.size_bytes.sum() / 1e9:.3f} GB), günlük zip {len(d)} "
          f"({d.size_bytes.sum() / 1e6:.2f} MB); aylık dizide boşluklu çift {len(summ['gaps'])}; "
          f"listeleme {summ['listing_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
