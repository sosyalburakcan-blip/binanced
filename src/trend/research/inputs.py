"""Araştırma girdileri (G10–G12): günlük panel, dolum fiyatları, evren sağlayıcıları, delist tablosu, kalite
işaretleri, hazine bonosu.

Aşama kuralı (PREREGISTRATION §7 "Sıralama"): `stage="development"` iken fiyat verisi geliştirme döneminin sonunda
kesilir; doğrulama dönemi verisi belleğe alınmaz. Delist tablosu yalnızca günlük kapanışların tamamından ve duyuru
tablosundan kurulur (son mumun tarihi SPEC'in backtest kuralıdır; geliştirme dışındaki tarihler motora etkisizdir).

Varsayımlar:
- Panel, herhangi bir evren varyantında (ana, 30, 50, yalnız USDT) en az bir kez yer alan varlıklar + BTC/ETH ile
  sınırlıdır; motor zaten yalnızca evren üyelerini izler.
- Saatlik veriden yalnızca gereken alanlar okunur (VWAP: quote_volume, volume; T8: ayrıca open, close).
- Delist duyurusundaki sembol, duyuru anını kapsayan segmentin asset_id'sine eşlenir (ör. LUNAUSDT 2022-05 duyurusu
  `LUNAUSDT_until_20220513`'e gider, yeni LUNA'ya değil).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from trend.backtest.fills import fill_prices_from_settings, open_fill_prices
from trend.backtest.providers import MonthlyUniverse
from trend.backtest.rules import delist_info_from_panel
from trend.config import load_settings, path as cfg_path
from trend.evaluation import rates
from trend.quality import flags_to_assets, load_flags

UNIVERSE_VARIANTS = {"main": "", "size_30": "size_30", "size_50": "size_50", "usdt_only": "usdt_only"}
DAILY_FIELDS = {"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume",
                "quote_volume": "quote_volume"}
HOURLY_VWAP_FIELDS = ("quote_volume", "volume")
HOURLY_T8_FIELDS = ("open", "close", "quote_volume", "volume")
READ_THREADS = int(load_settings()["data"]["panel_read_threads"])


def stage_end(cfg: dict, stage: str, lock_date=None) -> pd.Timestamp:
    """Verinin kesildiği son gün etiketi: geliştirmede geliştirme sonu, tam dönemde kilit tarihi."""
    if stage == "development":
        return pd.Timestamp(cfg["periods"]["development"][1])
    if stage == "full":
        if lock_date is None:
            raise ValueError("stage='full' için kilit tarihi gerekir")
        return pd.Timestamp(lock_date)
    raise ValueError(f"bilinmeyen aşama: {stage!r}")


def universe_assets(cfg: dict) -> list[str]:
    """Tüm evren varyantlarında en az bir kez görülen varlıklar + BTC/ETH."""
    root = cfg_path(cfg, "universe")
    out = {cfg["universe"]["btc_asset"], cfg["universe"]["eth_asset"]}
    for sub in UNIVERSE_VARIANTS.values():
        d = root / sub if sub else root
        for f in sorted(d.glob("*.csv")):
            if len(f.stem) == 7 and f.stem[4] == "-":
                out |= set(pd.read_csv(f, usecols=["symbol"])["symbol"].astype(str))
    return sorted(out)


def _read_fields(path: Path, fields: dict[str, str], end_time: pd.Timestamp | None) -> pd.DataFrame:
    filters = [("open_time", "<=", end_time)] if end_time is not None else None
    t = pq.read_table(path, columns=["open_time", *fields.values()], filters=filters)
    df = t.to_pandas().set_index("open_time")
    df.index = pd.DatetimeIndex(df.index).as_unit("ns")
    return df.rename(columns={v: k for k, v in fields.items()})


def load_fields(interval: str, assets: list[str], fields: dict[str, str] | tuple[str, ...],
                end_time: pd.Timestamp | None, cfg: dict) -> dict[str, pd.DataFrame]:
    """Birleştirilmiş seriden (CONTRACTS §4) yalnızca istenen alanlar: alan → (zaman × varlık), float64."""
    if not isinstance(fields, dict):
        fields = {f: f for f in fields}
    d = cfg_path(cfg, "merged") / interval
    with ThreadPoolExecutor(max_workers=READ_THREADS) as ex:
        frames = list(ex.map(lambda a: _read_fields(d / f"{a}.parquet", fields, end_time), assets))
    idx = frames[0].index
    for f in frames[1:]:
        idx = idx.union(f.index)
    out = {}
    for k in fields:
        arr = np.full((len(idx), len(assets)), np.nan)
        for j, f in enumerate(frames):
            arr[idx.get_indexer(f.index), j] = f[k].to_numpy(dtype=float)
        out[k] = pd.DataFrame(arr, index=idx, columns=pd.Index(assets, name="symbol"))
    return out


def map_announcements(ann: pd.DataFrame, segments: pd.DataFrame) -> pd.DataFrame:
    """Duyuru sembolünü (çift) duyuru anını kapsayan segmentin asset_id'sine çevirir; segment yoksa sembol kalır."""
    if ann is None or ann.empty:
        return ann
    seg = segments.copy()
    seg["start"] = pd.to_datetime(seg["start"])
    seg["end"] = pd.to_datetime(seg["end"])
    out = ann.copy()
    t = pd.to_datetime(out["announced_utc"], format="mixed")
    ids = []
    for sym, ts in zip(out["symbol"].astype(str), t):
        s = seg[seg["source_symbol"] == sym]
        # Varsayım: duyuru, segmentin bitişinden en geç 1 gün sonra olabilir (duyuru = kaldırma anı durumları)
        hit = s[(s["start"] <= ts) & (ts <= s["end"] + pd.Timedelta(days=1))]
        ids.append(str(hit.iloc[-1]["asset_id"]) if len(hit) else sym)
    out["symbol"] = ids
    return out


@dataclass
class ResearchInputs:
    cfg: dict
    stage: str
    start: pd.Timestamp            # rapor dönemi başı (geliştirme başı)
    end: pd.Timestamp              # verinin ve rapor döneminin sonu
    assets: list[str]
    panel_1d: dict[str, pd.DataFrame]
    universes: dict[str, MonthlyUniverse]
    delist: pd.DataFrame
    flags: pd.DataFrame
    tbill_pct: pd.Series           # takvim günü, yıllık %, nedensel (1 gün gecikmeli)
    rf: pd.Series                  # Sharpe için günlük risksiz oran
    fill_px: dict[str, pd.DataFrame] = field(default_factory=dict)  # dolum modu → dolum günü indeksli fiyat
    hourly: dict[str, pd.DataFrame] | None = None  # yalnızca testler: T8 için bellekteki saatlik panel

    @property
    def tbill_rate(self) -> pd.Series:
        """Motorun nakit getirisi girdisi: yıllık oran (ondalık)."""
        return (self.tbill_pct / 100.0).dropna()


def hourly_end_time(end: pd.Timestamp, offset_hours: int = 0) -> pd.Timestamp:
    """end günü kararlarının dolumu end+1'dedir ama motor end'de durur; T8 için end gününün bloğu yeterlidir."""
    return end + pd.Timedelta(days=1) + pd.Timedelta(hours=offset_hours) - pd.Timedelta(hours=1)


def load_inputs(stage: str = "development", lock_date=None, cfg: dict | None = None,
                fill_modes: tuple[str, ...] = ("vwap_00_02", "open_t1", "vwap_06_07", "vwap_14_15"),
                verbose: bool = True) -> ResearchInputs:
    cfg = cfg or load_settings()
    end = stage_end(cfg, stage, lock_date)
    start = pd.Timestamp(cfg["periods"]["development"][0])
    assets = universe_assets(cfg)
    log = print if verbose else (lambda *a, **k: None)
    log(f"[girdiler] {stage}: {len(assets)} varlık, veri sonu {end.date()}")
    end_day = end + pd.Timedelta(hours=23)
    panel = load_fields("1d", assets, DAILY_FIELDS, end_day, cfg)

    # Delist: son mum tarihi tüm kapanışlardan (yalnızca 1d close; fiyat değeri motora girmez)
    full_close = load_fields("1d", assets, {"close": "close"}, None, cfg)["close"]
    segments = pd.read_csv(cfg_path(cfg, "meta") / "asset_segments.csv")
    ann = pd.read_csv(cfg_path(cfg, "meta") / "delist_announcements.csv")
    ann = map_announcements(ann, segments)
    delist = delist_info_from_panel(full_close, int(cfg["backtest"]["delist_stale_days"]), ann)
    del full_close

    flags = flags_to_assets(load_flags(cfg), segments)
    flags = flags[flags["symbol"].isin(assets)].reset_index(drop=True)

    root = cfg_path(cfg, "universe")
    universes = {k: MonthlyUniverse.from_dir(root / v if v else root) for k, v in UNIVERSE_VARIANTS.items()}

    days = pd.date_range(cfg["periods"]["data_start"], end, freq="D")
    tb = rates.daily_tbill_pct(days)
    rf = rates.rf_daily(days)
    inp = ResearchInputs(cfg=cfg, stage=stage, start=start, end=end, assets=assets, panel_1d=panel,
                         universes=universes, delist=delist, flags=flags, tbill_pct=tb, rf=rf)

    need_1h = [m for m in fill_modes if m != "open_t1"]
    if need_1h:
        h = load_fields("1h", assets, HOURLY_VWAP_FIELDS, hourly_end_time(end), cfg)
        for m in need_1h:
            c = {**cfg, "backtest": {**cfg["backtest"], "fill": m}}
            inp.fill_px[m] = fill_prices_from_settings(c, panel, h)
        del h
    if "open_t1" in fill_modes:
        inp.fill_px["open_t1"] = open_fill_prices(panel)
    log(f"[girdiler] dolum fiyatları: {', '.join(inp.fill_px)}; delist satırı {len(inp.delist)}; "
        f"işaret {len(inp.flags)}")
    return inp
