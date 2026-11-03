"""Araştırma v2 tek/çift varlık adayları: VM_BTC, MR_BTC, RV_ETHBTC (PREREGISTRATION_v2; yürütme trend.alt.base).

Ortak: her gün karar (every=1); evren süzgeci ve kademe tavanı yok (yalnızca BTC/ETH); `common` kullanılmaz.
Tüm diziler `compute` içinde nedensel kurulur (satır i yalnızca ≤ i kapanışlarından); `target(j)` yalnızca j satırını
okur ve dolumlara bağlı durum tutmaz, böylece gecikme kontrolleri (j = i − lag) aynı dizileri kaydırır.

VM_BTC (`VolManagedBTC`) — yön sinyali yok, yalnızca oynaklık yönetimi:
- σ = rolling_vol(C_BTC, W, max(5, W // 2)); w_BTC = min(1, S / σ_j); σ NaN veya ≤ 0 → 0.
- Bant B: |w − w*| ≤ B·w* ise yeniden boyutlama yok (giriş/çıkış her zaman).

MR_BTC (`MeanRevBTC`) — BTC kısa vadeli z-skoru geri dönüşü:
- z_i = (C_i − ort(C_{i−W+1..i})) / std(C_{i−W+1..i}, ddof=1); son W takvim gününün kapanışlarından biri bile
  yoksa NaN.
- Durum (yalnızca z'den): dışarıda → içeride z_i < −e; içeride → dışarıda z_i ≥ 0 veya girişten bu yana W gün
  (giriş günü = 0, W'inci gün çıkış; en fazla W gün içeride). İçerideyken NaN z durumu korur ve gün sayılır (süre
  sınırı yine işler); dışarıdayken NaN z → dışarıda.
- w_BTC = durum_j; bant çok büyük → açık pozisyon yeniden boyutlanmaz (yalnızca tam giriş / tam çıkış).

RV_ETHBTC (`RatioRotationETHBTC`) — ETH/BTC oranı geri dönüşü, her zaman yatırımda:
- x = log(C_ETH / C_BTC) (ikisi de geçerliyse, yoksa NaN); z = (x − ort_W(x)) / std_W(x, ddof=1); W takvim günlük
  pencere, en az W // 2 geçerli x.
- z < −b → ETH 1; z > b → BTC 1; diğer (NaN z dahil) → j'de iki kapanış da varsa 50/50, yalnızca biri varsa ona 1,
  hiçbiri yoksa 0. Bant: params["band"].

Varsayımlar (brifin açık bıraktığı yerler):
- Pencere std'si 0 ise (sabit fiyat) z NaN.
- MR'de günde en fazla bir geçiş: çıkış günü yeniden giriş yok; ertesi gün z < −e ise yeniden giriş.
- Pozitif olmayan kapanış geçersiz sayılır (log için; gerçek veride yok).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trend.alt.base import AltStrategy, rolling_vol
from trend.backtest.interface import DayView, EngineData
from trend.config import load_settings

_U = load_settings()["universe"]
BTC, ETH = str(_U["btc_asset"]), str(_U["eth_asset"])
# MR bandı: açık pozisyonda |w − w*| hiçbir zaman bunun w* katını aşmaz (inf·0 = NaN olmasın diye sonlu).
NO_RESIZE = 1e9


def window_z(c: np.ndarray, window: int) -> np.ndarray:
    """Son `window` takvim günü kapanışlarına göre z-skoru (ddof=1); penceredeki tüm kapanışlar geçerli değilse NaN."""
    z = np.full(c.shape[0], np.nan)
    if c.shape[0] < window:
        return z
    win = np.lib.stride_tricks.sliding_window_view(c, window)
    ok = np.isfinite(win).all(axis=1)
    m = win.mean(axis=1)
    sd = win.std(axis=1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        zz = (c[window - 1:] - m) / sd
    z[window - 1:] = np.where(ok & (sd > 0), zz, np.nan)
    return z


def mr_states(z: np.ndarray, entry_z: float, max_hold: int) -> np.ndarray:
    """MR durum makinesi (bkz. modül notu); 1 = içeride."""
    st = np.zeros(z.shape[0], dtype=np.int8)
    inside, age = False, 0
    for i, zi in enumerate(z):
        if inside:
            age += 1
            if zi >= 0 or age >= max_hold:          # NaN ≥ 0 yanlış → durum korunur
                inside = False
        elif zi < -entry_z:                         # NaN < x yanlış → dışarıda kalır
            inside, age = True, 0
        st[i] = inside
    return st


def ratio_z(cb: np.ndarray, ce: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """x = log(ce / cb) ve kayan z-skoru (W takvim günü, ddof=1, en az W // 2 geçerli x)."""
    ok = np.isfinite(cb) & np.isfinite(ce) & (cb > 0) & (ce > 0)
    x = np.full(cb.shape[0], np.nan)
    x[ok] = np.log(ce[ok] / cb[ok])
    r = pd.Series(x).rolling(window, min_periods=window // 2)
    m, sd = r.mean().to_numpy(), r.std(ddof=1).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (x - m) / sd
    return x, np.where(np.isfinite(z) & (sd > 0), z, np.nan)


class VolManagedBTC(AltStrategy):
    """VM_BTC: w_BTC = min(1, σ*/σ̂) (bkz. modül notu)."""

    name = "VM_BTC"
    use_universe = False
    apply_cap = False

    def __init__(self, params: dict, common: dict | None = None, lag: int = 0):
        self.sigma_target, self.window = float(params["sigma_target"]), int(params["window"])
        if self.window < 5:                         # rolling_vol en az 5 gözlem ister
            raise ValueError(f"window: {self.window}")
        super().__init__(every=1, band=float(params["band"]), lag=lag, assets=(BTC,))

    def compute(self, data: EngineData) -> None:
        self.k = self.col[BTC]
        self.sig = rolling_vol(self.C[:, [self.k]], self.window, max(5, self.window // 2))[:, 0]

    def target(self, j: int, v: DayView) -> np.ndarray:
        out = np.zeros(len(self.data.assets))
        s = self.sig[j]
        if np.isfinite(s) and s > 0:
            out[self.k] = min(1.0, self.sigma_target / s)
        return out


class MeanRevBTC(AltStrategy):
    """MR_BTC: z < −e al, z ≥ 0 veya W gün sonra sat; tam giriş / tam çıkış (bkz. modül notu)."""

    name = "MR_BTC"
    use_universe = False
    apply_cap = False

    def __init__(self, params: dict, common: dict | None = None, lag: int = 0):
        self.window, self.entry_z = int(params["window"]), float(params["entry_z"])
        if self.window < 2:
            raise ValueError(f"window: {self.window}")
        self.max_hold = self.window
        super().__init__(every=1, band=NO_RESIZE, lag=lag, assets=(BTC,))

    def compute(self, data: EngineData) -> None:
        self.k = self.col[BTC]
        self.z = window_z(self.C[:, self.k], self.window)
        self.state = mr_states(self.z, self.entry_z, self.max_hold)

    def target(self, j: int, v: DayView) -> np.ndarray:
        out = np.zeros(len(self.data.assets))
        out[self.k] = float(self.state[j])
        return out


class RatioRotationETHBTC(AltStrategy):
    """RV_ETHBTC: ETH/BTC oranı ucuz olanı tut, arada 50/50 (bkz. modül notu)."""

    name = "RV_ETHBTC"
    use_universe = False
    apply_cap = False

    def __init__(self, params: dict, common: dict | None = None, lag: int = 0):
        self.window, self.z_band = int(params["window"]), float(params["z_band"])
        if self.window < 2:
            raise ValueError(f"window: {self.window}")
        super().__init__(every=1, band=float(params["band"]), lag=lag, assets=(BTC, ETH))

    def compute(self, data: EngineData) -> None:
        self.kb, self.ke = self.col[BTC], self.col[ETH]
        self.x, self.z = ratio_z(self.C[:, self.kb], self.C[:, self.ke], self.window)

    def target(self, j: int, v: DayView) -> np.ndarray:
        out = np.zeros(len(self.data.assets))
        z = self.z[j]
        if z < -self.z_band:
            out[self.ke] = 1.0
        elif z > self.z_band:
            out[self.kb] = 1.0
        else:                                       # bant içi veya NaN z
            fb, fe = np.isfinite(self.C[j, self.kb]), np.isfinite(self.C[j, self.ke])
            if fb and fe:
                out[self.kb] = out[self.ke] = 0.5
            elif fb:
                out[self.kb] = 1.0
            elif fe:
                out[self.ke] = 1.0
        return out


FAMILIES = {"VM_BTC": VolManagedBTC, "MR_BTC": MeanRevBTC, "RV_ETHBTC": RatioRotationETHBTC}
