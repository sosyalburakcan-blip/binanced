"""Değerlendirme modülleri için ortak yardımcılar: ayar okuma, risksiz faizle hizalama, temel Sharpe.

Kural: Sharpe her zaman ABD 3 aylık hazine bonosu üzerindeki fazla getiriyle ve √365 ile yıllıklandırılır
(SPEC "Ön kayıt → Risksiz faiz ve nakit getirisi"). Risksiz faiz serisi `rates.rf_daily` ile üretilir.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from trend.config import load_settings


def settings(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return cfg if cfg is not None else load_settings()


def periods_per_year(cfg: dict[str, Any] | None = None) -> int:
    """Yıllıklandırma gün sayısı (7/24 piyasa: 365)."""
    return int(settings(cfg)["strategy"]["annualization_days"])


def excess_returns(returns: pd.Series, rf: pd.Series | float | None) -> pd.Series:
    """r − rf. `rf` günlük basit oran (Series, aynı takvim) veya sabit; None → 0.

    Getiri tarihlerinden biri için rf eksikse hata verir (sessizce sıfır varsayılmaz).
    """
    if rf is None:
        return returns
    if np.isscalar(rf):
        return returns - float(rf)
    rf_al = rf.reindex(returns.index)
    if rf_al.isna().any():
        missing = rf_al.index[rf_al.isna()]
        raise ValueError(f"risksiz faiz {len(missing)} gün için eksik (ilk: {missing[0]})")
    return returns - rf_al


def sharpe(x: np.ndarray | pd.Series, ppy: int) -> float:
    """Yıllık Sharpe = ort(x) / std(x, ddof=1) · √ppy; x fazla getiri. Sharpe (1966, 1994)."""
    a = np.asarray(x, dtype=float)
    a = a[~np.isnan(a)]
    if a.size < 2:
        return float("nan")
    sd = a.std(ddof=1)
    return float(a.mean() / sd * np.sqrt(ppy)) if sd > 0 else float("nan")


def to_series(x: pd.Series | np.ndarray, name: str | None = None) -> pd.Series:
    if isinstance(x, pd.Series):
        return x.astype(float)
    return pd.Series(np.asarray(x, dtype=float), name=name)
