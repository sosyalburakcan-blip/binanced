"""Canlı kuralların backtest karşılıkları: delist tablosu ve −%35 sert sınır (SPEC "Delist kuralı",
"Canlı kuralların backteste yansıtılması").

Delist bilgisi biçimi (motor girdisi): DataFrame `asset, last_day, announced_day`
- `last_day`  = son mumun gün etiketi (SPEC: "Backtestte son mumun tarihi kullanılır"). Duyuru bilinmiyorsa pozisyon
  bu güne kadar tutulur ve bu günün dolum penceresi VWAP'ı × (1 − ceza) ile kapatılır.
- `announced_day` = duyurunun bilindiği ilk karar günü = duyuru zamanının gün tabanı (duyuru t−1 kapanışından önceyse
  t günü satılır ⇔ karar günü = floor(duyuru)). NaT = duyuru yok.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def delist_info_from_panel(
    close: pd.DataFrame,
    stale_days: int,
    announcements: pd.DataFrame | None = None,
    as_of: pd.Timestamp | None = None,
    kinds: tuple[str, ...] = ("delist",),
) -> pd.DataFrame:
    """Panelden delist tablosu: son geçerli kapanışı `as_of − stale_days`'ten eski olan varlıklar delist sayılır.

    `as_of` varsayılanı panelin son günüdür (verinin indirildiği an). `announcements` CONTRACTS §4 biçimindedir
    (`symbol, announced_utc, delist_utc, kind, source`; symbol = asset_id varsayılır); yalnızca `kinds` türleri
    satış tetikler (varsayım: monitoring_tag satış tetiklemez).
    """
    idx = pd.DatetimeIndex(close.index).as_unit("ns")
    as_of = pd.Timestamp(as_of) if as_of is not None else idx.max()
    v = np.isfinite(close.to_numpy(dtype=float))
    has = v.any(axis=0)
    last_pos = len(idx) - 1 - v[::-1].argmax(axis=0)
    rows = []
    for j, a in enumerate(close.columns):
        if not has[j]:
            continue
        last = idx[last_pos[j]]
        if (as_of - last).days > stale_days:
            rows.append((str(a), last))
    out = pd.DataFrame(rows, columns=["asset", "last_day"])
    out["announced_day"] = pd.NaT
    if announcements is not None and len(announcements):
        ann = announcements[announcements["kind"].isin(kinds)].copy()
        ann["announced_day"] = pd.to_datetime(ann["announced_utc"]).dt.floor("D")
        first = ann.groupby(ann["symbol"].astype(str))["announced_day"].min()
        out = out.set_index("asset")
        for sym, d in first.items():
            if sym in out.index:
                out.loc[sym, "announced_day"] = d
            else:  # duyurulmuş ama veri henüz bitmemiş (ör. panel sonu yakın): yalnız duyuru
                out.loc[sym, ["last_day", "announced_day"]] = [pd.NaT, d]
        out = out.reset_index()
    out["last_day"] = pd.to_datetime(out["last_day"])
    out["announced_day"] = pd.to_datetime(out["announced_day"])
    return out


class HardStop:
    """Zirveden `stop_at` (−%35) düşüşte yeni alımlar durur; zirvenin `resume_at`'ine (−%25) dönünce başlar."""

    def __init__(self, stop_at: float, resume_at: float, enabled: bool = True):
        self.stop_at, self.resume_at, self.enabled = stop_at, resume_at, enabled
        self.peak = -np.inf
        self.stopped = False

    def update(self, nav: float) -> bool:
        self.peak = max(self.peak, nav)
        if not self.enabled:
            return False
        dd = nav / self.peak - 1.0 if self.peak > 0 else 0.0
        if not self.stopped and dd <= self.stop_at:
            self.stopped = True
        elif self.stopped and dd >= self.resume_at:
            self.stopped = False
        return self.stopped
