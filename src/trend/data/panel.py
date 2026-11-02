"""Panel yükleyici (CONTRACTS §7): coin başına parquet'leri geniş tablolara çevirir.

`load_panel(interval, symbols=None, source="merged"|"clean", start=None, end=None)` →
`dict[str, DataFrame]`, anahtarlar `open, high, low, close, volume, quote_volume, trades`; index = open_time
(tz-naive UTC `DatetimeIndex`, sıralı), kolonlar = sembol/asset_id (sıralı). Eksik değer NaN, ileri taşıma yok.
`trades` NaN içerebildiği için float64'tür.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from trend.config import ROOT, load_settings, path

FIELDS = {"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume",
          "quote_volume": "quote_volume", "trades": "number_of_trades"}
MERGED_DIR = load_settings()["paths"]["merged"]  # CONTRACTS §4: data/merged/{interval}/{ASSET_ID}.parquet
READ_THREADS = int(load_settings()["data"]["panel_read_threads"])


def source_dir(cfg: dict, source: str, interval: str) -> Path:
    if source == "clean":
        return path(cfg, "clean") / interval
    if source == "merged":
        return ROOT / MERGED_DIR / interval
    raise ValueError(f"source 'merged' veya 'clean' olmalı: {source!r}")


def available_symbols(interval: str, source: str = "merged", cfg: dict | None = None) -> list[str]:
    d = source_dir(cfg or load_settings(), source, interval)
    return sorted(p.stem for p in d.glob("*.parquet") if not p.name.startswith("_"))


def _read(p: Path, start, end) -> pd.DataFrame:
    filters = []
    if start is not None:
        filters.append(("open_time", ">=", pd.Timestamp(start)))
    if end is not None:
        filters.append(("open_time", "<=", pd.Timestamp(end)))
    t = pq.read_table(p, columns=["open_time", *FIELDS.values()], filters=filters or None)
    return t.to_pandas().set_index("open_time")


def load_panel(interval: str, symbols: list[str] | None = None, source: str = "merged", start=None, end=None,
               cfg: dict | None = None) -> dict[str, pd.DataFrame]:
    """Geniş paneli yükler. `start`/`end` dahil (index etiketi üzerinden). Dosyası olmayan sembol → KeyError
    yerine FileNotFoundError (sessizce atlamak evren hatalarını gizler)."""
    cfg = cfg or load_settings()
    d = source_dir(cfg, source, interval)
    if not d.exists():
        raise FileNotFoundError(f"{d} yok ({source} verisi henüz üretilmemiş)")
    symbols = sorted(symbols) if symbols is not None else available_symbols(interval, source, cfg)
    missing = [s for s in symbols if not (d / f"{s}.parquet").exists()]
    if missing:
        raise FileNotFoundError(f"{d}: dosyası olmayan semboller: {missing[:10]}{' …' if len(missing) > 10 else ''}")
    with ThreadPoolExecutor(max_workers=READ_THREADS) as ex:
        frames = list(ex.map(lambda s: _read(d / f"{s}.parquet", start, end), symbols))
    if not frames:
        idx = pd.DatetimeIndex([], dtype="datetime64[ns]", name="open_time")
        return {k: pd.DataFrame(index=idx, dtype="float64") for k in FIELDS}
    # Tek hizalama: (sembol, alan) çok seviyeli kolonlarla birleştir, sonra alan başına ayır.
    wide = pd.concat(frames, axis=1, keys=symbols, sort=True)
    out = {}
    for key, col in FIELDS.items():
        df = wide.xs(col, axis=1, level=1).astype("float64")
        df.columns = pd.Index(symbols, name="symbol")
        df.index.name = "open_time"
        out[key] = df
    return out
