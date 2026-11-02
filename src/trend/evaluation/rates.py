"""ABD 3 aylık hazine bonosu (FRED DTB3): indirme, 7/24 günlük takvim, günlük basit faiz, nakit getirisi.

SPEC "Ön kayıt → Risksiz faiz ve nakit getirisi":
- Sharpe her zaman hazine bonosu üzerindeki fazla getiriyle hesaplanır (yıllıklandırma √365).
- Nakit getirisi: temel %0 (`zero`); duyarlılık max(0, bono − 1,5 puan) (`tbill_minus_1_5`) ve tam bono (`tbill`).

Varsayımlar (kodda ve raporda belirtilir):
- DTB3 iş günü serisidir (ikincil piyasa, iskonto esası, yıllık %). İskonto esası olduğu gibi kullanılır;
  tahvil eşdeğeri getiriye çevrilmez (fark %5 faizde ≈ 0,13 puan).
- Kripto takvimi 7/24: her takvim günü için **son bilinen** değer ileri taşınır (geriye doldurma yok).
  Ayrıca değer `TBILL_LAG_DAYS` gün gecikmeli kullanılır: d günü gözlemi en erken d+1'de bilinir (H.15 yayını).
- Yıllık % → günlük basit oran: y / 100 / 365 (ACT/365; √365 yıllıklandırmasıyla tutarlı).

meta/tbill_3m.csv kolonları: `date, tbill_3m_pct, downloaded_at_utc` (FRED'in boş/"." değerleri boş bırakılır;
`downloaded_at_utc` her satırda aynıdır = indirme zaman damgası).
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from trend.config import load_settings, path as cfg_path
from trend.evaluation.common import periods_per_year, settings

FRED_DTB3_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"
TBILL_FILENAME = "tbill_3m.csv"
DOWNLOAD_START = "2010-01-01"  # veri başlangıcından (2017-08) yeterince önce
CASH_YIELD_MODES = ("zero", "tbill_minus_1_5", "tbill")

_EV = load_settings()["evaluation"]
# "hazine bonosu − 1,5 puan" duyarlılığındaki indirim (puan)
CASH_YIELD_SPREAD_PP = float(_EV["cash_yield_spread_pp"])
# d günü gözleminin kullanılabildiği ilk gün d + gecikme
TBILL_LAG_DAYS = int(_EV["tbill_lag_days"])
# son gözlemden bu kadar gün sonra seri bayat sayılır (NaN)
TBILL_MAX_STALE_DAYS = int(_EV["tbill_max_stale_days"])


def tbill_path(cfg: dict[str, Any] | None = None) -> Path:
    return cfg_path(settings(cfg), "meta") / TBILL_FILENAME


def parse_fred_csv(text: str) -> pd.DataFrame:
    """FRED fredgraph.csv metni → `date, tbill_3m_pct`. Başlık `observation_date` veya `DATE` olabilir."""
    raw = pd.read_csv(io.StringIO(text), na_values=["."], keep_default_na=True)
    if raw.shape[1] < 2:
        raise ValueError("beklenmeyen FRED CSV biçimi")
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(raw.iloc[:, 0]),
            "tbill_3m_pct": pd.to_numeric(raw.iloc[:, 1], errors="coerce").astype(float),
        }
    )
    return out.sort_values("date").drop_duplicates("date").reset_index(drop=True)


def download_tbill(
    dest: Path | str | None = None,
    start: str = DOWNLOAD_START,
    timeout: float = 30.0,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """DTB3'ü FRED'den indirir ve indirme zaman damgasıyla meta/tbill_3m.csv'ye yazar."""
    resp = requests.get(f"{FRED_DTB3_URL}&cosd={start}", timeout=timeout)
    resp.raise_for_status()
    df = parse_fred_csv(resp.text)
    if df["tbill_3m_pct"].notna().sum() == 0:
        raise ValueError("FRED yanıtında DTB3 değeri yok")
    df["downloaded_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dest = Path(dest) if dest is not None else tbill_path(cfg)
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dest, index=False, date_format="%Y-%m-%d", lineterminator="\n")
    return df


def load_tbill(path: Path | str | None = None) -> pd.Series:
    """meta/tbill_3m.csv → gözlem tarihli Series (yıllık %, boş günler atılır)."""
    p = Path(path) if path is not None else tbill_path()
    df = pd.read_csv(p, parse_dates=["date"])
    s = df.set_index("date")["tbill_3m_pct"].astype(float).dropna()
    s.index = pd.DatetimeIndex(s.index).as_unit("ns")
    s.index.name = "date"
    return s.sort_index()


def tbill_downloaded_at(path: Path | str | None = None) -> str:
    p = Path(path) if path is not None else tbill_path()
    return str(pd.read_csv(p, usecols=["downloaded_at_utc"], nrows=1).iloc[0, 0])


def daily_tbill_pct(
    index: pd.DatetimeIndex | None = None,
    tbill: pd.Series | None = None,
    lag_days: int = TBILL_LAG_DAYS,
    max_stale_days: int | None = TBILL_MAX_STALE_DAYS,
) -> pd.Series:
    """Takvim günü (7/24) hazine bonosu, yıllık %. Değer t = son gözlem (tarih ≤ t − lag_days); ileri taşıma.

    İlk gözlemden önceki ve `max_stale_days`'ten bayat günler NaN kalır (geleceği görme / sessiz bayatlık yok).
    """
    s = (tbill if tbill is not None else load_tbill()).dropna().sort_index()
    avail = pd.DatetimeIndex(s.index) + pd.Timedelta(days=lag_days)  # değerin bilinir olduğu ilk gün
    s = pd.Series(s.to_numpy(), index=avail)
    if index is None:
        index = pd.date_range(avail[0], avail[-1], freq="D")
    index = pd.DatetimeIndex(index)
    union = avail.union(index)
    vals = s.reindex(union).ffill().reindex(index)
    if max_stale_days is not None:
        known = pd.Series(avail, index=avail).reindex(union).ffill().reindex(index)
        stale = (index - pd.DatetimeIndex(known)).days > max_stale_days
        vals = vals.mask(stale)
    vals.name = "tbill_3m_pct"
    return vals


def pct_to_daily(pct: pd.Series | float, ppy: int = 365) -> pd.Series | float:
    """Yıllık % → günlük basit oran: y/100/ppy."""
    return pct / 100.0 / ppy


def rf_daily(
    index: pd.DatetimeIndex,
    tbill: pd.Series | None = None,
    lag_days: int = TBILL_LAG_DAYS,
    cfg: dict[str, Any] | None = None,
) -> pd.Series:
    """Sharpe için günlük risksiz faiz (basit oran), `index` takviminde."""
    out = pct_to_daily(daily_tbill_pct(index, tbill, lag_days), periods_per_year(cfg))
    out.name = "rf_daily"
    return out


def cash_yield_pct(tbill_pct: pd.Series, mode: str, spread_pp: float = CASH_YIELD_SPREAD_PP) -> pd.Series:
    """Nakit getirisi (yıllık %): zero → 0; tbill_minus_1_5 → max(0, bono − 1,5); tbill → bono."""
    if mode == "zero":
        return tbill_pct * 0.0
    if mode == "tbill_minus_1_5":
        return (tbill_pct - spread_pp).clip(lower=0.0)
    if mode == "tbill":
        return tbill_pct.copy()
    raise ValueError(f"bilinmeyen nakit getirisi modu: {mode!r} (geçerli: {CASH_YIELD_MODES})")


def cash_yield_daily(
    index: pd.DatetimeIndex,
    mode: str | None = None,
    tbill: pd.Series | None = None,
    lag_days: int = TBILL_LAG_DAYS,
    cfg: dict[str, Any] | None = None,
) -> pd.Series:
    """Nakit kısma uygulanacak günlük basit oran. `mode` None → settings `backtest.cash_yield`."""
    cfg = settings(cfg)
    mode = mode or cfg["backtest"]["cash_yield"]
    if mode == "zero":
        out = pd.Series(0.0, index=pd.DatetimeIndex(index))
    else:
        out = pct_to_daily(cash_yield_pct(daily_tbill_pct(index, tbill, lag_days), mode), periods_per_year(cfg))
    out.name = "cash_yield_daily"
    return out
