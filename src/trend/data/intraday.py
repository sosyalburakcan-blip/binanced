"""Gün içi veri — Binance spot ve USDT-M sürekli vadeli 15 dk mumları + fonlama oranları (data.binance.vision).

Kapsam: sabit 57 varlık (`ASSETS`, asset_id = spot USDT çifti). G12 kilidindeki donmuş anlık görüntüye
(data/merged, data/raw, data/clean, meta/, universe/, data/ledger.csv, lock/, golden/) dokunulmaz; her şey
`data/intraday/` altına yazılır. settings.yaml de kilit özetinde olduğu için bu modülün sabitleri (varlık listesi,
bitiş, dizinler) burada tanımlıdır; indirme ayarları (eşzamanlılık, yeniden deneme) settings.yaml'dan okunur.

Dizinler (`data/intraday/`):
- `raw/` arşiv aynası; rel_path = arşiv anahtarının `data/` önekinden sonrası (ör. `spot/monthly/klines/...`,
  `futures/um/monthly/fundingRate/...`). `ledger.csv` kendi defteri (şema `download.LEDGER_COLS`).
- `_inventory.csv` S3 listeleme envanteri, `futures_symbols.csv` vadeli sembol planı, `merge_log.txt` uyarılar.
- `spot_15m/{ASSET}.parquet`, `futures_15m/{ASSET}.parquet`: open_time, open, high, low, close, volume,
  quote_volume, source_symbol (open_time tz-naive UTC, sıralı ve benzersiz; fiyatlar spot biriminde).
- `funding/{ASSET}.parquet`: funding_time, funding_rate (dönem başına), source_symbol.
- `inventory.csv` varlık başına kapsama özeti; `sanity.json` doğrulama sayıları (`--check`).

Kurallar:
- Listeleme `s3.list_bucket`; indirme, CHECKSUM ve defter `download` (fetch_one, Ledger, plan, run) ile — kaldığı
  yerden devam: defterde `ok`, yerelde aynı boyutta duran dosyalar yeniden indirilmez. Dosya seçimi `s3.list_pair`
  ile aynı: tüm aylık zip'ler + aylık dizide boş kalan aylar ve son aylık aydan sonraki günler için günlük zip'ler.
- Okuma `clean.build_frame` ile (ms/µs dönüşümü, başlık satırı, aylık > günlük önceliği, tekrarlar).
- Spot birleştirme `meta.iter_merged` ile 1d/1h serileriyle aynı kurallarla (meta/symbol_map.csv, verified=yes).
  `trend.quality.INTERVAL_STEP` yalnız 1d/1h içerdiğinden 15m adımı çalışma anında sözlüğe eklenir (dosya
  değişmez). Kaynak semboller `meta/asset_segments.csv`'den okunur; birleşik serinin (kaynak sembol, oran) dizisi
  bu tabloyla karşılaştırılır, uyuşmazlık hata sayılır.
- Vadeli sembol: her spot kaynak sembolü `{BASE}USDT` için `{önek}{BASE}USDT` adayları (önek "", 1000, 1000000,
  1M) arşiv listesinde aranır. Çarpan = önek çarpanı × spot segment oranı (1000SHIBUSDT → 1000; eski BTTUSDT
  vadelisi spot BTT→BTTC oranıyla → 1000). Fiyat / çarpan, taban hacim × çarpan, quote hacim değişmez
  (`meta._adjust`). Sembol zinciri (MATICUSDT→POLUSDT, FTMUSDT→SUSDT, EOSUSDT→AUSDT, RNDRUSDT→RENDERUSDT,
  BTTUSDT→1000BTTCUSDT) arşivdeki ilk aya göre sıralanır ve yine `iter_merged` ile birleştirilir: eski sembolün
  yeni sembolün ilk mumundan itibaren olan mumları düşer. Vadelisi olmayan varlık atlanır ve envantere yazılır.
- Varsayım (G-intraday bulgusu): vadeli arşivi delist edilmiş kontratlar için hacimsiz düz mumlar ve sabit fonlama
  satırları yayımlamayı sürdürür (ör. FTMUSDT 15m 2026-10 tamamı 0,7702 ve hacim 0; MATICUSDT fundingRate 2026-10
  0,0001). Bu yüzden her vadeli sembolde ilk işlem gören (hacim > 0) mumdan önceki ve son işlem gören mumdan sonraki
  mumlar atılır; fonlama satırları sembolün [ilk işlem mumu açılışı, son işlem mumu kapanışı] aralığında tutulur.
  Aradaki hacimsiz koşular atılmaz, envanter notunda raporlanır.
- Fonlama zamanı `calc_time` ms sapmalıdır (ör. 08:00:00.005) → en yakın dakikaya yuvarlanır (sapma `sanity`'de).
- Bitiş `END` = 2026-11-01 23:45 (dahil; donmuş 1d/1h ile aynı son gün), sonraki mumlar ve dosyalar alınmaz.
  Fonlama arşivinde günlük dosya yoktur: 2026-11 aylık dosyası yayımlanana kadar fonlama 2026-10-31'de biter.

CLI:
    python -m uv run python -m trend.data.intraday --all
    python -m uv run python -m trend.data.intraday --assets BTCUSDT,ETHUSDT --no-download
    python -m uv run python -m trend.data.intraday --check
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from trend import meta
from trend.config import ROOT, load_settings
from trend.data import _http, clean, download, s3
from trend.quality import INTERVAL_FREQ, INTERVAL_STEP

ASSETS = tuple("""
BTCUSDT ETHUSDT XRPUSDT ADAUSDT DOGEUSDT SOLUSDT TRXUSDT LINKUSDT LTCUSDT POLUSDT SUSDT AVAXUSDT AUSDT NEARUSDT
SUIUSDT ZECUSDT VETUSDT XLMUSDT ETCUSDT RUNEUSDT ATOMUSDT SHIBUSDT PEPEUSDT BCHUSDT NEOUSDT CHZUSDT FETUSDT UNIUSDT
ONTUSDT CFXUSDT WAVESUSDT INJUSDT PEOPLEUSDT BTTCUSDT HOTUSDT THETAUSDT OMGUSDT ZILUSDT FILUSDT TRBUSDT RENDERUSDT
HBARUSDT TAOUSDT ENAUSDT QTUMUSDT TFUELUSDT ALGOUSDT ONEUSDT DOTUSDT LINAUSDT COMPUSDT DYDXUSDT APTUSDT CRVUSDT
ICPUSDT WLDUSDT DEXEUSDT
""".split())
INTERVAL = "15m"
STEP = pd.Timedelta(minutes=15)
END = pd.Timestamp("2026-11-01 23:45")   # son mum (dahil)
END_EXCL = END + STEP                    # 2026-11-02 00:00
INTRADAY_DIR = ROOT / "data" / "intraday"
# Vadeli kontrat öneki → kontratın taban birim sayısı (1000SHIBUSDT fiyatı 1000 SHIB'in fiyatıdır).
FUTURES_PREFIXES = {"": 1.0, "1000": 1e3, "1000000": 1e6, "1M": 1e6}
# Arşiv kökleri (`data/` önekinden sonra). Fonlama oranının günlük dosyası yoktur.
ROOTS = {
    "spot": ("spot/monthly/klines/{s}/15m/", "spot/daily/klines/{s}/15m/"),
    "futures": ("futures/um/monthly/klines/{s}/15m/", "futures/um/daily/klines/{s}/15m/"),
    "funding": ("futures/um/monthly/fundingRate/{s}/", None),
}
# clean.parse_rel `{monthly|daily}/klines/SYM/INT/dosya.zip` bekler: bu önek atılıp ham dizine eklenir.
KIND_BASE = {"spot": "spot/", "futures": "futures/um/", "funding": "futures/um/"}
INVENTORY_COLS = ["rel_path", "url", "size_bytes", "last_modified", "symbol", "kind", "freq", "period",
                  "has_checksum"]
OUT_COLS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume", "source_symbol"]
FUNDING_COLS = ["funding_time", "funding_rate", "source_symbol"]
FUNDING_RAW_COLS = ["calc_time", "funding_interval_hours", "last_funding_rate"]
FUTURES_PLAN_COLS = ["asset_id", "futures_symbol", "spot_source", "multiplier", "order", "first_period",
                     "has_klines", "has_funding"]
INVENTORY_OUT_COLS = ["asset_id", "spot_symbols", "spot_first", "spot_last", "spot_n_bars", "spot_missing_bars",
                      "futures_symbols", "futures_multiplier", "futures_first", "futures_last", "futures_n_bars",
                      "futures_missing_bars", "funding_first", "funding_last", "funding_n_rows", "notes"]
LONG_GAP = pd.Timedelta(days=1)  # notta ayrıca listelenecek boşluk / hacimsiz koşu eşiği

# 15m adımını birleştirme planına tanıt (trend.meta aynı sözlük nesnesini kullanır; dosya değişmez).
INTERVAL_STEP.setdefault(INTERVAL, STEP)
INTERVAL_FREQ.setdefault(INTERVAL, "15min")


@dataclass(frozen=True)
class Paths:
    """`data/intraday` altındaki tüm yollar (testlerde geçici dizin verilir)."""

    root: Path = INTRADAY_DIR

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def ledger(self) -> Path:
        return self.root / "ledger.csv"

    @property
    def inventory(self) -> Path:
        return self.root / "_inventory.csv"

    @property
    def futures_plan(self) -> Path:
        return self.root / "futures_symbols.csv"

    @property
    def summary(self) -> Path:
        return self.root / "inventory.csv"

    @property
    def merge_log(self) -> Path:
        return self.root / "merge_log.txt"

    @property
    def sanity(self) -> Path:
        return self.root / "sanity.json"

    def out(self, kind: str) -> Path:
        return self.root / {"spot": "spot_15m", "futures": "futures_15m", "funding": "funding"}[kind]


def archive_root(cfg: dict) -> str:
    """`data.archive_base` (…/data/spot) → …/data."""
    return cfg["data"]["archive_base"].rstrip("/").removesuffix("/spot")


# ------------------------------------------------------------------------------------------- sembol planı
def spot_sources(segments: pd.DataFrame, assets: list[str]) -> dict[str, list[tuple[str, float]]]:
    """asset_segments → varlık başına zaman sıralı [(kaynak spot sembolü, oran)]."""
    seg = segments[segments["asset_id"].isin(assets)].copy()
    seg["start"] = pd.to_datetime(seg["start"])
    out = {a: [(s, float(r)) for s, r in zip(g["source_symbol"], g["ratio"])]
           for a, g in seg.sort_values(["asset_id", "start"], kind="mergesort").groupby("asset_id", sort=True)}
    missing = sorted(set(assets) - set(out))
    if missing:
        raise ValueError(f"asset_segments'te olmayan varlık: {missing}")
    return out


def futures_plan(sources: dict[str, list[tuple[str, float]]], kline_syms: set[str],
                 funding_syms: set[str]) -> pd.DataFrame:
    """Varlık başına vadeli semboller ve çarpanları (sıra `order_futures` ile ilk aya göre verilir)."""
    rows = []
    for a, srcs in sources.items():
        for src, ratio in srcs:
            base = src.removesuffix("USDT")
            for pfx, mult in FUTURES_PREFIXES.items():
                fs = f"{pfx}{base}USDT"
                if fs in kline_syms or fs in funding_syms:
                    rows.append({"asset_id": a, "futures_symbol": fs, "spot_source": src, "multiplier": mult * ratio,
                                 "order": 0, "first_period": "", "has_klines": fs in kline_syms,
                                 "has_funding": fs in funding_syms})
    df = pd.DataFrame(rows, columns=FUTURES_PLAN_COLS)
    dup = df["futures_symbol"][df["futures_symbol"].duplicated()]
    if len(dup):
        raise ValueError(f"vadeli sembol birden fazla varlığa eşlendi: {sorted(set(dup))}")
    return df


def order_futures(plan: pd.DataFrame, inv: pd.DataFrame) -> pd.DataFrame:
    """Zincir sırası: sembolün arşivdeki ilk kline dönemine göre (yoksa fonlama)."""
    first = inv.groupby(["symbol", "kind"])["period"].min()
    out = plan.copy()

    def fp(s):
        for k in ("futures", "funding"):
            if (s, k) in first.index:
                return first[(s, k)]
        return "9999"

    out["first_period"] = [fp(s) for s in out["futures_symbol"]]
    out = out.sort_values(["asset_id", "first_period", "futures_symbol"], kind="mergesort", ignore_index=True)
    out["order"] = out.groupby("asset_id").cumcount()
    return out


def chain_map(chains: list[list[str]]) -> pd.DataFrame:
    """Ardışık sembolleri RENAME satırlarına çevirir (oran 1; çarpan yükleyicide uygulanır, zaman boş = veri belirler)."""
    rows = [{"old_symbol": a, "new_symbol": b, "type": "RENAME", "ratio": 1.0, "old_last_trade_utc": "",
             "new_first_trade_utc": "", "source": "intraday futures chain", "verified": "yes"}
            for ch in chains for a, b in zip(ch[:-1], ch[1:])]
    return pd.DataFrame(rows, columns=meta.SYMBOL_MAP_COLUMNS)


# ---------------------------------------------------------------------------------------------- listeleme
def _period_ok(freq: str, period: str, end: pd.Timestamp = END) -> bool:
    """Aylık dosya: ay başı ≤ END; günlük dosya: gün ≤ END günü."""
    if freq == "monthly":
        return pd.Timestamp(period + "-01") <= end
    return pd.Timestamp(period) <= end.normalize()


def _file_rows(contents: list[dict], symbol: str, kind: str, freq: str, base_url: str,
               end: pd.Timestamp = END) -> list[dict]:
    keys = {c["key"] for c in contents}
    out = []
    for c in contents:
        k = c["key"]
        if not k.endswith(".zip"):
            continue
        period = s3._period_of(k, freq)
        if not _period_ok(freq, period, end):
            continue
        rel = k.removeprefix("data/")
        out.append({"rel_path": rel, "url": f"{base_url}/{rel}", "size_bytes": int(c["size"]),
                    "last_modified": c["last_modified"], "symbol": symbol, "kind": kind, "freq": freq,
                    "period": period, "has_checksum": f"{k}.CHECKSUM" in keys})
    return out


def list_files(kind: str, symbol: str, cfg: dict, end: pd.Timestamp = END) -> list[dict]:
    """Bir sembol × veri türü için gereken zip'ler (`s3.list_pair` kuralı; günlük önek tümden listelenmez)."""
    base = archive_root(cfg)
    mroot, droot = ROOTS[kind]
    mon = s3.list_bucket("data/" + mroot.format(s=symbol), cfg=cfg).contents
    rows = _file_rows(mon, symbol, kind, "monthly", base, end)
    if droot is None:
        return rows
    dpfx = "data/" + droot.format(s=symbol)
    stem = f"{dpfx}{symbol}-{INTERVAL}-"
    months = sorted(s3._period_of(c["key"], "monthly") for c in mon if c["key"].endswith(".zip"))
    if not months:
        return rows + _file_rows(s3.list_bucket(dpfx, cfg=cfg).contents, symbol, kind, "daily", base, end)
    have = set(months)
    for m in s3._months_between(months[0], months[-1]):
        if m not in have and pd.Timestamp(m + "-01") <= end:
            rows += _file_rows(s3.list_bucket(f"{stem}{m}-", cfg=cfg).contents, symbol, kind, "daily", base, end)
    if pd.Timestamp(months[-1] + "-01") + pd.offsets.MonthBegin(1) <= end:
        tail = s3.list_bucket(dpfx, cfg=cfg, marker=f"{stem}{months[-1]}-99").contents
        rows += _file_rows(tail, symbol, kind, "daily", base, end)
    return rows


def discover_futures(cfg: dict) -> tuple[set[str], set[str]]:
    """Arşivdeki USDT-M vadeli semboller: (kline: aylık ∪ günlük, fonlama)."""
    kl = set(s3.list_symbols("data/futures/um/monthly/klines/", cfg)) | \
        set(s3.list_symbols("data/futures/um/daily/klines/", cfg))
    fr = set(s3.list_symbols("data/futures/um/monthly/fundingRate/", cfg))
    return kl, fr


def build_inventory(pairs: list[tuple[str, str]], cfg: dict, progress: bool = True) -> pd.DataFrame:
    """(sembol, tür) çiftlerini paralel listeler (eşzamanlı istek ≤ data.concurrency)."""
    rows: list[dict] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=cfg["data"]["concurrency"]) as ex:
        futs = {ex.submit(list_files, k, s, cfg): (s, k) for s, k in pairs}
        for i, f in enumerate(as_completed(futs), 1):
            rows += f.result()
            if progress and i % 50 == 0:
                print(f"[intraday] listelendi {i}/{len(pairs)} çift, {len(rows)} dosya, {time.time() - t0:.0f}s",
                      flush=True)
    inv = pd.DataFrame(rows, columns=INVENTORY_COLS)
    return inv.sort_values("rel_path", ignore_index=True)


def read_inventory(p: Path) -> pd.DataFrame:
    if not p.exists():
        return pd.DataFrame(columns=INVENTORY_COLS)
    return pd.read_csv(p, dtype={"period": str, "symbol": str, "kind": str, "freq": str}, keep_default_na=False)


def load_or_build_inventory(pairs: list[tuple[str, str]], paths: Paths, cfg: dict, refresh: bool) -> pd.DataFrame:
    """Envanter bugün (UTC) yazılmış ve tüm çiftleri içeriyorsa okunur; değilse eksik/tüm çiftler listelenir ve
    diğer çiftlerin satırları korunarak dosyaya yazılır."""
    old = read_inventory(paths.inventory)
    p = paths.inventory
    fresh = p.exists() and dt.datetime.fromtimestamp(p.stat().st_mtime, dt.UTC).date() == dt.datetime.now(dt.UTC).date()
    have = set(zip(old["symbol"], old["kind"])) if len(old) else set()
    todo = pairs if (refresh or not fresh) else [x for x in pairs if x not in have]
    if not todo:
        return old[[(s, k) in set(pairs) for s, k in zip(old["symbol"], old["kind"])]].reset_index(drop=True)
    new = build_inventory(todo, cfg)
    keep = old[[(s, k) not in set(todo) for s, k in zip(old["symbol"], old["kind"])]] if len(old) else old
    full = pd.concat([d for d in (keep, new) if len(d)], ignore_index=True) if len(keep) else new
    full = full[INVENTORY_COLS].sort_values("rel_path", ignore_index=True)
    s3.write_atomic_csv(full, p)
    return full[[(s, k) in set(pairs) for s, k in zip(full["symbol"], full["kind"])]].reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ indirme
def download_files(inv: pd.DataFrame, paths: Paths, cfg: dict, dry_run: bool = False) -> dict:
    """`download.plan` + `download.run`: defterde ok olmayan / boyutu değişen dosyaları indirir."""
    ledger = download.Ledger(paths.ledger)
    try:
        todo = download.plan(inv, ledger, paths.raw)
        print(f"[intraday] envanter {len(inv)} dosya ({inv['size_bytes'].sum() / 1e6:.1f} MB); indirilecek "
              f"{len(todo)} ({todo['size_bytes'].sum() / 1e6:.1f} MB); eşzamanlılık {cfg['data']['concurrency']}",
              flush=True)
        if dry_run or todo.empty:
            return {"todo": len(todo), "interrupted": False, "error": 0, "checksum_mismatch": 0}
        st = download.run(list(zip(todo["rel_path"], todo["url"], todo["size_bytes"])), ledger, paths.raw, cfg,
                          label="intraday")
        st["todo"] = len(todo)
        return st
    finally:
        ledger.close()


def ok_files(inv: pd.DataFrame, paths: Paths) -> pd.DataFrame:
    """Envanterdeki dosyalardan defterde ok olanlar (ve durum sütunu)."""
    led = download.read_ledger(paths.ledger)
    st = dict(zip(led["rel_path"], led["status"]))
    out = inv.assign(status=[st.get(r, "not_downloaded") for r in inv["rel_path"]])
    return out


# ------------------------------------------------------------------------------------------------- okuma
def _clean_files(rels: list[str], kind: str) -> pd.DataFrame:
    """Defter yolları → `clean.parse_rel` alanları (tür öneki atılır)."""
    base = KIND_BASE[kind]
    meta_rows = [clean.parse_rel(r.removeprefix(base)) for r in rels]
    return pd.DataFrame(meta_rows, columns=["rel_path", "kind", "symbol", "interval", "period", "month", "start", "end"])


def load_klines(rels: list[str], raw_dir: Path, kind: str, symbol: str, thr: int,
                end: pd.Timestamp = END) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Kline zip'leri → `clean` şeması (≤ end). Dönüş: (tablo, tekrar kaydı)."""
    files = _clean_files(rels, kind)
    df, dups = clean.build_frame(files, raw_dir / KIND_BASE[kind].rstrip("/"), thr, end + STEP, symbol, INTERVAL)
    return df[df["open_time"] <= end].reset_index(drop=True), dups


def trim_inactive(df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """İlk işlem gören (hacim > 0) mumdan önceki ve son işlem gören mumdan sonraki mumları atar.
    Dönüş: (tablo, baştan atılan, sondan atılan)."""
    act = (df["volume"] > 0).to_numpy()
    if not act.any():
        return df.iloc[0:0].copy(), len(df), 0
    i0 = int(np.argmax(act))
    i1 = len(act) - int(np.argmax(act[::-1]))
    return df.iloc[i0:i1].reset_index(drop=True), i0, len(df) - i1


def read_funding_csv(data: bytes, thr: int) -> pd.DataFrame:
    """Fonlama CSV baytları → funding_time (dakikaya yuvarlanmış), funding_rate, offset_s (ham − yuvarlanmış)."""
    data = data.removeprefix(b"\xef\xbb\xbf")
    if not data.strip():
        return pd.DataFrame({"funding_time": pd.Series(dtype="datetime64[ns]"),
                             "funding_rate": pd.Series(dtype="float64"), "offset_s": pd.Series(dtype="float64")})
    header = not data[:1].isdigit()
    raw = pd.read_csv(io.BytesIO(data), header=0 if header else None)
    if not header or "calc_time" not in raw.columns:
        # Varsayım: başlıksız dosyada sütun sırası başlıklılarla aynı (calc_time, funding_interval_hours, rate).
        raw.columns = FUNDING_RAW_COLS[: raw.shape[1]] + [f"c{i}" for i in range(raw.shape[1] - 3)]
    t = pd.Series(clean.ts_to_datetime(raw["calc_time"].astype("int64"), thr))
    ft = t.dt.round("min")
    return pd.DataFrame({"funding_time": ft.astype("datetime64[ns]").to_numpy(),
                         "funding_rate": pd.to_numeric(raw["last_funding_rate"], errors="coerce").astype("float64"),
                         "offset_s": ((t - ft).dt.total_seconds()).to_numpy()})


def read_funding_zip(p: Path, thr: int) -> pd.DataFrame:
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"{p}: zip içinde tek CSV beklenirdi, bulunan {z.namelist()}")
        return read_funding_csv(z.read(names[0]), thr)


def load_funding(rels: list[str], raw_dir: Path, thr: int, end_excl: pd.Timestamp = END_EXCL) -> pd.DataFrame:
    """Bir sembolün fonlama zip'leri → sıralı, benzersiz funding_time (< end_excl), NaN oranlar atılır."""
    parts = [read_funding_zip(raw_dir / r, thr) for r in sorted(rels)]
    if not parts:
        return read_funding_csv(b"", thr)
    df = pd.concat(parts, ignore_index=True)
    df = df[df["funding_rate"].notna() & (df["funding_time"] < end_excl)]
    df = df.sort_values("funding_time", kind="mergesort")
    return df[~df["funding_time"].duplicated(keep="first")].reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ özetler
def gap_stats(t: pd.Series, step: pd.Timedelta = STEP) -> dict:
    """Izgaraya göre eksik mum sayısı ve uzun boşluklar (≥ LONG_GAP)."""
    if len(t) == 0:
        return {"missing": 0, "long": []}
    t = t.reset_index(drop=True)
    d = t.diff().iloc[1:]
    miss = int(((d // step) - 1).clip(lower=0).sum())
    big = d[d >= LONG_GAP + step]
    long = [f"{t.iloc[i - 1] + step:%Y-%m-%d %H:%M}→{t.iloc[i]:%Y-%m-%d %H:%M}" for i in big.index]
    return {"missing": miss, "long": long}


def zero_volume_runs(df: pd.DataFrame, min_bars: int = int(LONG_GAP / STEP)) -> list[str]:
    """Ardışık hacimsiz mum koşuları (≥ min_bars)."""
    z = (df["volume"] <= 0).to_numpy()
    if not z.any():
        return []
    edges = np.diff(np.concatenate([[0], z.astype(int), [0]]))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    ot = df["open_time"]
    return [f"{ot.iloc[a]:%Y-%m-%d %H:%M}→{ot.iloc[b - 1]:%Y-%m-%d %H:%M} ({b - a} mum)"
            for a, b in zip(starts, ends) if b - a >= min_bars]


def off_grid(df: pd.DataFrame, label: str) -> list[str]:
    """15 dk ızgarasına oturmayan open_time'lar (arşiv kusuru, ör. spot 2018-02-09 09:58:14.789); veri olduğu gibi
    tutulur (temiz 1d/1h verisiyle aynı), yalnız raporlanır."""
    t = df["open_time"]
    off = t != t.dt.floor("15min")
    if not off.any():
        return []
    return [f"{label} ızgara dışı open_time {int(off.sum())} mum ({_fmt(t[off].iloc[0])}→{_fmt(t[off].iloc[-1])})"]


def listing_gaps(inv: pd.DataFrame, symbol: str, kind: str) -> list[str]:
    """Sembolün ilk ve son dönemi arasında ne aylık ne günlük dosyası olan aylar."""
    g = inv[(inv["symbol"] == symbol) & (inv["kind"] == kind)]
    if g.empty:
        return []
    months = set(g["period"].str[:7])
    return [m for m in s3._months_between(min(months), max(months)) if m not in months]


def _fmt(t) -> str:
    return "" if t is None or pd.isna(t) else f"{pd.Timestamp(t):%Y-%m-%d %H:%M}"


def _write_parquet(df: pd.DataFrame, p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, p)


# ------------------------------------------------------------------------------------------- varlık kurulumu
@dataclass
class AssetJob:
    asset_id: str
    spot: list[tuple[str, float]]          # [(spot sembolü, oran)] asset_segments sırasıyla
    futures: list[tuple[str, float]]       # [(vadeli sembol, çarpan)] zincir sırasıyla
    files: dict[tuple[str, str], list[str]]  # (sembol, tür) → defterde ok rel_path'ler
    not_ok: list[str]                      # envanterde olup defterde ok olmayan dosyalar
    listing_gaps: dict[str, list[str]]     # "tür/sembol" → boş aylar
    spot_map: pd.DataFrame                 # symbol_map'in bu varlığın sembollerini içeren satırları
    root: str
    thr: int


def _merge(symbols: list[str], loader, smap: pd.DataFrame, warnings: list[str]):
    """`meta.iter_merged` → (birleşik seri, segmentler) — tek zincir beklenir."""
    res = list(meta.iter_merged(symbols, loader, smap, INTERVAL, False, warnings))
    if len(res) > 1:
        raise ValueError(f"tek zincir beklenirdi, bulunan {[a for a, _, _ in res]}")
    if not res:
        return None, []
    return res[0][1], res[0][2]


def build_asset(job: AssetJob) -> dict:
    """Bir varlığın spot, vadeli ve fonlama parquet'lerini yazar; envanter satırı + uyarıları döndürür."""
    paths = Paths(Path(job.root))
    raw = paths.raw
    a = job.asset_id
    notes: list[str] = []
    warns: list[str] = []
    row = {c: "" for c in INVENTORY_OUT_COLS}
    row["asset_id"] = a

    # --- spot
    def spot_loader(sym: str) -> pd.DataFrame:
        df, dups = load_klines(job.files.get((sym, "spot"), []), raw, "spot", sym, job.thr)
        if len(dups):
            notes.append(f"spot {sym}: {len(dups)} tekrar open_time ({int((dups['kind'] == 'conflict').sum())} çelişkili)")
        return df

    spot_syms = [s for s, _ in job.spot]
    sw: list[str] = []
    sdf, segs = _merge(spot_syms, spot_loader, job.spot_map, sw)
    warns += [f"{a} spot: {w}" for w in sw]
    if sdf is not None:
        got = [(s["source_symbol"], float(s["ratio"])) for s in segs]
        if got != [(s, float(r)) for s, r in job.spot]:
            raise ValueError(f"{a}: 15m segmentleri asset_segments ile uyuşmuyor: {got} ≠ {job.spot}")
        sdf = sdf[OUT_COLS]
        _write_parquet(sdf, paths.out("spot") / f"{a}.parquet")
        gs = gap_stats(sdf["open_time"])
        row.update(spot_first=_fmt(sdf["open_time"].iloc[0]), spot_last=_fmt(sdf["open_time"].iloc[-1]),
                   spot_n_bars=len(sdf), spot_missing_bars=gs["missing"])
        if gs["long"]:
            notes.append(f"spot ≥1g boşluk: {'; '.join(gs['long'])}")
        notes += off_grid(sdf, "spot")
        if len(segs) > 1:
            notes.append("spot segmentler: " + "; ".join(
                f"{s['source_symbol']} {_fmt(s['start'])}→{_fmt(s['end'])}"
                + (f" oran {s['ratio']:g}" if s["ratio"] != 1 else "") for s in segs))
    else:
        notes.append("spot verisi yok")
    row["spot_symbols"] = "|".join(spot_syms)

    # --- vadeli
    fut_syms = [s for s, _ in job.futures]
    mult = dict(job.futures)
    row["futures_symbols"] = "|".join(fut_syms)
    row["futures_multiplier"] = "|".join(f"{mult[s]:g}" for s in fut_syms)
    active: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
    if not fut_syms:
        notes.append("USDT-M sürekli vadeli kontrat yok (arşivde eşleşen sembol bulunamadı)")
    else:
        def fut_loader(sym: str) -> pd.DataFrame:
            df, dups = load_klines(job.files.get((sym, "futures"), []), raw, "futures", sym, job.thr)
            if len(dups):
                notes.append(f"vadeli {sym}: {len(dups)} tekrar open_time "
                             f"({int((dups['kind'] == 'conflict').sum())} çelişkili)")
            df, lead, trail = trim_inactive(df)
            if lead or trail:
                notes.append(f"vadeli {sym}: işlem öncesi {lead} / sonrası {trail} hacimsiz mum atıldı")
            if len(df):
                active[sym] = (df["open_time"].iloc[0], df["open_time"].iloc[-1] + STEP)
                runs = zero_volume_runs(df)
                if runs:
                    notes.append(f"vadeli {sym} ≥1g hacimsiz koşu: {'; '.join(runs)}")
            if mult[sym] != 1.0:
                notes.append(f"vadeli {sym}: fiyat ÷{mult[sym]:g}, hacim ×{mult[sym]:g}")
            return meta._adjust(df, mult[sym], sym)

        fw: list[str] = []
        fdf, fsegs = _merge(fut_syms, fut_loader, chain_map([fut_syms]), fw)
        warns += [f"{a} vadeli: {w}" for w in fw]
        if fdf is not None:
            fdf = fdf[OUT_COLS]
            _write_parquet(fdf, paths.out("futures") / f"{a}.parquet")
            gs = gap_stats(fdf["open_time"])
            row.update(futures_first=_fmt(fdf["open_time"].iloc[0]), futures_last=_fmt(fdf["open_time"].iloc[-1]),
                       futures_n_bars=len(fdf), futures_missing_bars=gs["missing"])
            if gs["long"]:
                notes.append(f"vadeli ≥1g boşluk: {'; '.join(gs['long'])}")
            notes += off_grid(fdf, "vadeli")
            if len(fsegs) > 1:
                notes.append("vadeli segmentler: " + "; ".join(
                    f"{s['source_symbol']} {_fmt(s['start'])}→{_fmt(s['end'])}" for s in fsegs))
        else:
            notes.append("vadeli kline verisi yok")

        # --- fonlama
        offs: list[float] = []

        def fr_loader(sym: str) -> pd.DataFrame:
            df = load_funding(job.files.get((sym, "funding"), []), raw, job.thr)
            if sym in active:
                lo, hi = active[sym]
                keep = (df["funding_time"] >= lo) & (df["funding_time"] <= hi)
                if (~keep).any():
                    notes.append(f"fonlama {sym}: işlem aralığı dışında {int((~keep).sum())} satır atıldı")
                df = df[keep]
            if len(df):
                offs.append(float(df["offset_s"].abs().max()))
            return df.drop(columns="offset_s").rename(columns={"funding_time": "open_time"})

        rw: list[str] = []
        rdf, _ = _merge(fut_syms, fr_loader, chain_map([fut_syms]), rw)
        warns += [f"{a} fonlama: {w}" for w in rw]
        if rdf is not None:
            rdf = rdf.rename(columns={"open_time": "funding_time"})[FUNDING_COLS]
            _write_parquet(rdf, paths.out("funding") / f"{a}.parquet")
            row.update(funding_first=_fmt(rdf["funding_time"].iloc[0]), funding_last=_fmt(rdf["funding_time"].iloc[-1]),
                       funding_n_rows=len(rdf))
            row["_funding_max_offset_s"] = max(offs) if offs else 0.0
        else:
            notes.append("fonlama verisi yok")

    for k, months in job.listing_gaps.items():
        if months:
            notes.append(f"arşivde dosyasız ay {k}: {','.join(months)}")
    if job.not_ok:
        notes.append(f"defterde ok olmayan {len(job.not_ok)} dosya: {', '.join(job.not_ok[:5])}"
                     + (" …" if len(job.not_ok) > 5 else ""))
    row["notes"] = " | ".join(dict.fromkeys(notes))
    return {"row": row, "warnings": warns}


def make_jobs(assets: list[str], sources: dict, fplan: pd.DataFrame, inv: pd.DataFrame, paths: Paths,
              cfg: dict) -> list[AssetJob]:
    smap = meta.load_symbol_map(cfg=cfg)
    st = ok_files(inv, paths)
    ok = st[st["status"] == "ok"]
    files = {k: sorted(g["rel_path"]) for k, g in ok.groupby(["symbol", "kind"])}
    thr = int(cfg["data"]["timestamp_us_threshold"])
    jobs = []
    for a in assets:
        spot = sources[a]
        fp = fplan[fplan["asset_id"] == a].sort_values("order")
        fut = list(zip(fp["futures_symbol"], fp["multiplier"].astype(float)))
        syms = {s for s, _ in spot}
        pairs = [(s, "spot") for s in syms] + [(s, k) for s, _ in fut for k in ("futures", "funding")]
        mine = st[[(s, k) in set(pairs) for s, k in zip(st["symbol"], st["kind"])]]
        not_ok = sorted(mine.loc[mine["status"] != "ok", "rel_path"])
        gaps = {f"{k}/{s}": listing_gaps(inv, s, k) for s, k in pairs}
        sm = smap[smap["old_symbol"].isin(syms) | smap["new_symbol"].isin(syms)].reset_index(drop=True)
        jobs.append(AssetJob(a, spot, fut, {k: v for k, v in files.items() if k in set(pairs)}, not_ok, gaps, sm,
                             str(paths.root), thr))
    return jobs


def build_all(jobs: list[AssetJob], paths: Paths, workers: int | None = None, progress: bool = True) -> pd.DataFrame:
    """İşleri süreç havuzunda çalıştırır; inventory.csv ve merge_log.txt yazar (alt kümede diğer satırlar korunur)."""
    workers = workers or max(1, min(len(jobs), (os.cpu_count() or 2) - 1))
    rows, warns, failed = [], [], {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(build_asset, j): j.asset_id for j in jobs}
        for i, f in enumerate(as_completed(futs), 1):
            a = futs[f]
            try:
                r = f.result()
            except Exception as e:  # noqa: BLE001 — varlık bazında hata raporlanır, diğerleri sürer
                failed[a] = f"{type(e).__name__}: {e}"
                print(f"[intraday] HATA {a}: {failed[a]}", flush=True)
                continue
            rows.append(r["row"])
            warns += r["warnings"]
            if progress and (i % 10 == 0 or i == len(jobs)):
                print(f"[intraday] kuruldu {i}/{len(jobs)} varlık ({time.time() - t0:.0f}s)", flush=True)
    new = pd.DataFrame(rows)
    offs = new.pop("_funding_max_offset_s") if "_funding_max_offset_s" in new else None
    new = new.reindex(columns=INVENTORY_OUT_COLS).astype(str)
    old = pd.read_csv(paths.summary, dtype=str, keep_default_na=False) if paths.summary.exists() else None
    if old is not None and len(old):
        new = pd.concat([old[~old["asset_id"].isin(new["asset_id"])], new], ignore_index=True)
    order = {a: i for i, a in enumerate(ASSETS)}
    new = new.sort_values("asset_id", key=lambda s: s.map(lambda x: order.get(x, 10**6)), ignore_index=True)
    s3.write_atomic_csv(new, paths.summary)
    lines = [f"built_utc={download.now_utc()} assets={len(rows)} failed={len(failed)}"]
    lines += [f"HATA {a}: {e}" for a, e in sorted(failed.items())]
    lines += [f"UYARI {w}" for w in warns]
    if offs is not None:
        lines.append(f"fonlama calc_time en büyük |sapma| (dakikaya yuvarlama): {float(offs.max()):.3f} s")
    paths.merge_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[intraday] BİTTİ {len(rows)} varlık, hatalı {len(failed)}, uyarı {len(warns)}, {time.time() - t0:.0f}s "
          f"→ {paths.summary}", flush=True)
    if failed:
        raise SystemExit(f"kurulamayan varlık: {sorted(failed)}")
    return new


# ------------------------------------------------------------------------------------------------ doğrulama
def sanity(paths: Paths, cfg: dict) -> dict:
    """BTC/ETH: 15m'den türetilen saatlik kapanış (saatin son 15m mumu) = data/merged/1h kapanışı; BTC vadeli−spot
    medyan mutlak baz; BTC günlük fonlama satırı; fonlama zaman sapması."""
    out: dict = {}
    mdir = meta.merged_dir("1h", cfg)
    for a in ("BTCUSDT", "ETHUSDT"):
        s = pd.read_parquet(paths.out("spot") / f"{a}.parquet")
        h = pd.read_parquet(mdir / f"{a}.parquet", columns=["open_time", "close", "volume"])
        s = s.assign(hour=s["open_time"].dt.floor("h"))
        last = s[s["open_time"].dt.minute == 45].set_index("hour")
        vol = s.groupby("hour")["volume"].sum()
        j = h.set_index("open_time").join(last[["close"]].rename(columns={"close": "c15"}), how="inner")
        j = j.join(vol.rename("v15"), how="inner")
        j = j.join(s.groupby("hour").size().rename("n15"), how="inner")
        rel = (j["c15"] / j["close"] - 1).abs()
        vrel = ((j["v15"] - j["volume"]).abs() / j["volume"].where(j["volume"] > 0)).fillna(0.0)
        full = j["n15"] == 4
        out[a] = {"overlap_hours": int(len(j)), "hours_1h": int(len(h)), "close_max_rel_diff": float(rel.max()),
                  "close_n_diff": int((rel > 0).sum()), "full_hours": int(full.sum()),
                  "full_hours_volume_max_rel_diff": float(vrel[full].max()),
                  "full_hours_volume_n_diff_gt_1e-9": int((vrel[full] > 1e-9).sum()),
                  "spot_first": str(s["open_time"].iloc[0]), "spot_last": str(s["open_time"].iloc[-1])}
    s = pd.read_parquet(paths.out("spot") / "BTCUSDT.parquet").set_index("open_time")["close"]
    f = pd.read_parquet(paths.out("futures") / "BTCUSDT.parquet").set_index("open_time")["close"]
    b = (f / s).dropna() - 1
    out["BTC_basis"] = {"overlap_bars": int(len(b)), "median_abs_basis": float(b.abs().median()),
                        "median_abs_basis_bps": float(b.abs().median() * 1e4), "median_basis_bps": float(b.median() * 1e4),
                        "p99_abs_basis_bps": float(b.abs().quantile(0.99) * 1e4)}
    fr = pd.read_parquet(paths.out("funding") / "BTCUSDT.parquet")
    per_day = fr.groupby(fr["funding_time"].dt.normalize()).size()
    out["BTC_funding"] = {"rows": int(len(fr)), "days": int(len(per_day)), "mean_rows_per_day": float(per_day.mean()),
                          "rows_per_day_counts": {str(k): int(v) for k, v in per_day.value_counts().sort_index().items()},
                          "first": str(fr["funding_time"].iloc[0]), "last": str(fr["funding_time"].iloc[-1]),
                          "minutes_not_00": int((fr["funding_time"].dt.minute != 0).sum())}
    paths.sanity.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


# --------------------------------------------------------------------------------------------------- CLI
def plan_symbols(assets: list[str], cfg: dict) -> tuple[dict, pd.DataFrame, list[tuple[str, str]]]:
    """(spot kaynakları, vadeli plan (sırasız), listelenecek (sembol, tür) çiftleri)."""
    segs = pd.read_csv(meta.segments_path(cfg, "1d"))
    sources = spot_sources(segs, assets)
    kl, fr = discover_futures(cfg)
    fplan = futures_plan(sources, kl, fr)
    pairs = sorted({(s, "spot") for v in sources.values() for s, _ in v}
                   | {(s, "futures") for s in fplan.loc[fplan["has_klines"], "futures_symbol"]}
                   | {(s, "funding") for s in fplan.loc[fplan["has_funding"], "futures_symbol"]})
    return sources, fplan, pairs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="15m spot + USDT-M vadeli mumlar ve fonlama oranları (data/intraday)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help=f"{len(ASSETS)} varlığın tamamı")
    g.add_argument("--assets", help="virgülle ayrılmış asset_id alt kümesi, ör. BTCUSDT,ETHUSDT")
    g.add_argument("--check", action="store_true", help="yalnız doğrulama sayıları (sanity.json)")
    ap.add_argument("--no-download", action="store_true", help="indirme yok; yalnız defterdeki ok dosyalardan kur")
    ap.add_argument("--download-only", action="store_true", help="yalnız listele + indir")
    ap.add_argument("--refresh-inventory", action="store_true", help="S3'ü bugün listelenmiş olsa da yeniden listele")
    ap.add_argument("--dry-run", action="store_true", help="yalnız indirme planını yazdır")
    ap.add_argument("--workers", type=int, help="kurulum süreç sayısı (varsayılan: çekirdek − 1)")
    a = ap.parse_args(argv)
    _http.utf8_stdout()
    cfg = load_settings()
    paths = Paths()
    if a.check:
        print(json.dumps(sanity(paths, cfg), indent=1, ensure_ascii=False))
        return 0
    assets = list(ASSETS) if a.all else a.assets.split(",")
    bad = sorted(set(assets) - set(ASSETS))
    if bad:
        ap.error(f"listede olmayan varlık: {bad}")
    paths.root.mkdir(parents=True, exist_ok=True)
    sources, fplan, pairs = plan_symbols(assets, cfg)
    inv = load_or_build_inventory(pairs, paths, cfg, a.refresh_inventory)
    fplan = order_futures(fplan, inv)
    if a.all:
        s3.write_atomic_csv(fplan, paths.futures_plan)
    no_fut = sorted(set(assets) - set(fplan["asset_id"]))
    print(f"[intraday] {len(assets)} varlık; spot sembol {sum(k == 'spot' for _, k in pairs)}, vadeli sembol "
          f"{len(fplan)}; vadelisi olmayan: {no_fut or '-'}", flush=True)
    rc = 0
    if not a.no_download:
        st = download_files(inv, paths, cfg, a.dry_run)
        if st.get("interrupted"):
            return 130
        rc = 1 if st.get("error") or st.get("checksum_mismatch") else 0
    if a.dry_run or a.download_only:
        return rc
    build_all(make_jobs(assets, sources, fplan, inv, paths, cfg), paths, a.workers)
    if a.all:
        print(json.dumps(sanity(paths, cfg), indent=1, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
