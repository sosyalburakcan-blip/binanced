"""Minimum kayıt uzunluğu (MinTRL), Bailey ve López de Prado (2012) "The Sharpe Ratio Efficient Frontier".

MinTRL = 1 + [1 − γ3·SR + (γ4 − 1)/4 · SR²] · (z_{1−α} / (SR − SR*))²   (gözlem sayısı; SR gözlem frekansında)

SPEC sağlaması (≈ 2,7 yıl SR = 1; ≈ 10,8 yıl SR = 0,5) şu kuralla tutar: **günlük gözlem** (SR_g = SR_yıllık/√365),
normal getiri (γ3 = 0, γ4 = 3), SR* = 0, tek yönlü %95 (z = 1,645), gün sayısı/365. Sonuç ≈ (z/SR_yıllık)² yıl:
SR = 1 → 2,71 yıl; SR = 0,5 → 10,83 yıl. (Yıllık gözlemle aynı formül 5,1 ve 13,2 yıl verir; SPEC bunu kullanmaz.)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from trend.evaluation.dsr import sharpe_moments


def min_track_record_length(
    sr: float, sr_benchmark: float = 0.0, skew: float = 0.0, kurt: float = 3.0, alpha: float = 0.05
) -> float:
    """MinTRL, gözlem sayısı cinsinden; SR ≤ SR* ise sonsuz."""
    if sr <= sr_benchmark:
        return float("inf")
    z = stats.norm.ppf(1.0 - alpha)
    term = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    return float(1.0 + term * (z / (sr - sr_benchmark)) ** 2)


def min_track_record_years(
    sr_annual: float,
    sr_benchmark_annual: float = 0.0,
    skew: float = 0.0,
    kurt: float = 3.0,
    alpha: float = 0.05,
    ppy: int = 365,
) -> float:
    """MinTRL, yıl cinsinden; günlük gözlem (γ3, γ4 günlük getirilerin momentleri)."""
    k = np.sqrt(ppy)
    return min_track_record_length(sr_annual / k, sr_benchmark_annual / k, skew, kurt, alpha) / ppy


def min_track_record_from_returns(
    returns: pd.Series,
    rf: pd.Series | float | None = None,
    sr_benchmark_annual: float = 0.0,
    alpha: float = 0.05,
    ppy: int = 365,
) -> dict[str, float]:
    """Gözlenen getirilerden MinTRL (yıl) ve mevcut kayıt uzunluğu (yıl)."""
    m = sharpe_moments(returns, rf)
    years = min_track_record_length(m["sr"], sr_benchmark_annual / np.sqrt(ppy), m["skew"], m["kurt"], alpha) / ppy
    return {"min_trl_years": years, "track_years": m["n"] / ppy, "sharpe_annual": m["sr"] * np.sqrt(ppy),
            "skew": m["skew"], "kurt": m["kurt"]}
