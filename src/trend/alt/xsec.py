"""Araştırma v2 kesitsel adayları (research_v2.yaml `families`): XS_REV ve XS_LOWVOL.

İkisi de aynı iskeleti kullanır: t kararının evren üyeleri (ay(t+1)) arasından bir skora göre en düşük N varlık
seçilir, ham ağırlık 1/σ ile oynaklık hedefli sepet kurulur (`vol_target_weights`, σ* = common.sigma_target,
kovaryans common.cov_window / cov_min_obs, kademe tavanı ve brüt ≤ 1). Yürütme `AltStrategy` ortaktır
(`use_universe`, `apply_cap`, bant = common.drift_band; ara günlerde çıkış ve dolmamış girişlerin yeniden denenmesi).

XS_REV — kesitsel kısa vadeli geri dönüş (params: lookback L, n_hold N, every E gün):
- skor[i] = log(C[i] / C[i−L]); iki kapanıştan biri yoksa NaN (ileri doldurma yok: boşluğu aşan skor yok).
- σ = rolling_vol(C, common.vol_window, common.vol_min_obs) (yıllık, log getiri std'si).
- En düşük skorlu (en çok düşen) N uygun varlık; ham ağırlık 1/σ. Yeniden dengeleme: ilk karar günü + her E gün.

XS_LOWVOL — düşük oynaklık anomalisi (params: window W, n_hold N, every "monthly" | gün):
- skor = σ = rolling_vol(C, W, max(10, W // 2)).
- En düşük skorlu (en az oynak) N uygun varlık; ham ağırlık 1/skor.

Uygunluk (t = i karar günü, j = i − lag skor satırı; bkz. base): evren üyesi (v.univ), skor[j] ve σ[j] sonlu,
σ[j] > 0, force_zero değil.

Varsayımlar:
- Eşit skorda motor varlık sırasında önce gelen seçilir (kararlı sıralama).
- Uygun varlık N'den azsa uygun olanların hepsi tutulur (sepet küçülür, kalan nakitte).
- σ = 0 (pencerede sabit fiyat) uygun sayılmaz: 1/σ tanımsızdır; uygun sayılsa seçim yerini ağırlıksız harcardı.
- Seçim ve ham ağırlık j satırından; evren, tavan ve force_zero karar günü i'nin görünümünden (lag kontrolleri).
- Sepet yeniden dengeleme gününde seçilir ve bir sonrakine kadar tutulur (`hold_targets`); arada yalnızca delist
  ve evrenden çıkış satılır.
- Kademe tavanı `common.tier_caps` ile (varsayılan açık; research_v2.yaml'da kapalı: tek coin ağırlığını oynaklık
  hedefi ve brüt ≤ 1 sınırlar).
"""

from __future__ import annotations

import numpy as np

from trend.alt.base import AltStrategy, rolling_vol, vol_target_weights
from trend.backtest.interface import DayView, EngineData


def lowest_n(score: np.ndarray, eligible: np.ndarray, n: int) -> np.ndarray:
    """Uygun varlıklar arasında skoru en düşük n tanesinin maskesi; eşitlikte düşük sütun indeksi önce."""
    sel = np.zeros(score.shape[0], dtype=bool)
    idx = np.flatnonzero(eligible)
    if idx.size == 0 or n <= 0:
        return sel
    order = idx[np.argsort(score[idx], kind="stable")]
    sel[order[:n]] = True
    return sel


class _CrossSection(AltStrategy):
    """Ortak kesitsel seçim; alt sınıflar `compute` içinde `self.score` ve `self.sigma` (yıllık σ) kurar."""

    use_universe = True
    apply_cap = True
    hold_targets = True           # sepet yeniden dengelemeden yeniden dengelemeye tutulur (base modül notu)

    def __init__(self, params: dict, common: dict, lag: int = 0):
        super().__init__(every=params["every"], band=common["drift_band"], lag=lag)
        self.params, self.common = dict(params), dict(common)
        self.apply_cap = bool(common.get("tier_caps", True))   # research_v2.yaml: false (PREREGISTRATION_v2 §4)
        self.n_hold = int(params["n_hold"])
        if self.n_hold < 1:
            raise ValueError(f"n_hold: {params['n_hold']!r}")

    def select(self, j: int, v: DayView) -> np.ndarray:
        s, sg = self.score[j], self.sigma[j]
        ok = v.univ & np.isfinite(s) & np.isfinite(sg) & (sg > 0) & ~v.force_zero
        return lowest_n(s, ok, self.n_hold)

    def target(self, j: int, v: DayView) -> np.ndarray:
        sel = self.select(j, v)
        raw = np.zeros(sel.shape[0])
        raw[sel] = 1.0 / self.sigma[j][sel]
        c = self.common
        return vol_target_weights(raw, sel, self.R, j, float(c["sigma_target"]), int(c["cov_window"]),
                                  int(c["cov_min_obs"]), v.cap if self.apply_cap else None)


class XsReversal(_CrossSection):
    """XS_REV: son L günün en çok düşen N evren üyesi (bkz. modül notu)."""

    name = "XS_REV"

    def __init__(self, params: dict, common: dict, lag: int = 0):
        super().__init__(params, common, lag)
        self.lookback = int(params["lookback"])
        if self.lookback < 1:
            raise ValueError(f"lookback: {params['lookback']!r}")

    def compute(self, data: EngineData) -> None:
        C, L = self.C, self.lookback
        self.score = np.full_like(C, np.nan)
        if L < C.shape[0]:
            ok = np.isfinite(C[L:]) & np.isfinite(C[:-L])
            with np.errstate(divide="ignore", invalid="ignore"):
                self.score[L:] = np.where(ok, np.log(C[L:] / C[:-L]), np.nan)
        c = self.common
        self.sigma = rolling_vol(C, int(c["vol_window"]), int(c["vol_min_obs"]))


class XsLowVol(_CrossSection):
    """XS_LOWVOL: son W günün en az oynak N evren üyesi (bkz. modül notu)."""

    name = "XS_LOWVOL"

    def __init__(self, params: dict, common: dict, lag: int = 0):
        super().__init__(params, common, lag)
        self.window = int(params["window"])
        if self.window < 10:                         # en az gözlem max(10, W // 2) ≤ W olmalı
            raise ValueError(f"window: {params['window']!r}")

    def compute(self, data: EngineData) -> None:
        self.score = rolling_vol(self.C, self.window, max(10, self.window // 2))
        self.sigma = self.score


FAMILIES = {"XS_REV": XsReversal, "XS_LOWVOL": XsLowVol}
