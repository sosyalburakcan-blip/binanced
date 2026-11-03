"""Araştırma v3 kısa vadeli trend adayları (PREREGISTRATION_v3; yürütme trend.alt.base): TS_D, TS_W, XS_MOM.

TS_D / TS_W (`TsMomBTC`) — BTC zaman serisi momentumu (params: lookback k, every E):
- sinyal[i] = log(C[i] / C[i−k]); iki kapanıştan biri yoksa NaN (ileri doldurma yok).
- Hedef: sinyal > 0 → %100 BTC, aksi halde (NaN dahil) %0. Tam giriş / tam çıkış; açık pozisyon yeniden
  boyutlanmaz.
- E = 1 (TS_D): her gün karar. E > 1 (TS_W): karar ilk karar gününde ve sonra her E günde bir; arada hedef tutulur
  ve çıkış da yalnızca karar gününde yapılır (`hold_targets`, `exit_daily` kapalı).

XS_MOM (`XsMomentum`) — kesitsel kısa vadeli momentum: XS_REV'in (trend.alt.xsec) tersi. Evren üyeleri arasında son
L günde en çok YÜKSELEN N coin (skor = −log(C[i] / C[i−L])); seçim, 1/σ ağırlık, oynaklık hedefi, sepetin E gün
tutulması ve kademe tavanı kuralı XS_REV ile aynı.
"""

from __future__ import annotations

import numpy as np

from trend.alt.base import AltStrategy
from trend.alt.single import BTC, NO_RESIZE
from trend.alt.xsec import XsReversal
from trend.backtest.interface import DayView, EngineData


class TsMomBTC(AltStrategy):
    """TS_D / TS_W: son k günün BTC getirisi pozitifse %100 BTC (bkz. modül notu)."""

    name = "TS_BTC"
    use_universe = False
    apply_cap = False

    def __init__(self, params: dict, common: dict | None = None, lag: int = 0):
        self.lookback = int(params["lookback"])
        if self.lookback < 1:
            raise ValueError(f"lookback: {params['lookback']!r}")
        every = params["every"]
        super().__init__(every=every, band=NO_RESIZE, lag=lag, assets=(BTC,))
        periodic = every != 1
        self.hold_targets, self.exit_daily = periodic, not periodic

    def compute(self, data: EngineData) -> None:
        self.k = self.col[BTC]
        c, L = self.C[:, self.k], self.lookback
        self.sig = np.full(c.shape[0], np.nan)
        if L < c.shape[0]:
            ok = np.isfinite(c[L:]) & np.isfinite(c[:-L])
            with np.errstate(divide="ignore", invalid="ignore"):
                self.sig[L:] = np.where(ok, np.log(c[L:] / c[:-L]), np.nan)

    def target(self, j: int, v: DayView) -> np.ndarray:
        out = np.zeros(len(self.data.assets))
        s = self.sig[j]
        out[self.k] = 1.0 if (np.isfinite(s) and s > 0) else 0.0
        return out


class XsMomentum(XsReversal):
    """XS_MOM: son L günün en çok yükselen N evren üyesi (bkz. modül notu)."""

    name = "XS_MOM"

    def compute(self, data: EngineData) -> None:
        super().compute(data)
        self.score = -self.score


FAMILIES = {"TS_D": TsMomBTC, "TS_W": TsMomBTC, "XS_MOM": XsMomentum}
