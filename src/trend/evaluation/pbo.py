"""Backtest aşırı uyum olasılığı (PBO), CSCV yöntemi.

Bailey, Borwein, López de Prado ve Zhu (2017) "The Probability of Backtest Overfitting", J. Computational Finance.
T × N deneme getirisi matrisi S eşit satır bloğuna bölünür (S çift). Her C(S, S/2) kombinasyonda seçilen bloklar
eğitim (IS), kalanlar test (OOS) olur. IS'te en iyi deneme n* seçilir; OOS'taki göreli sırası ω = sıra/(N+1)
(sıra 1..N, en iyi = N, eşitlikte ortalama), logit λ = ln(ω/(1 − ω)). PBO = P(λ ≤ 0) (eşitlik muhafazakâr olarak
aşırı uyum sayılır). Performans bozulması: OOS_SR(n*) = a + b·IS_SR(n*) doğrusal regresyonu ve P(OOS_SR(n*) < 0).

Bölünemeyen T mod S satır en baştan (en eski) atılır. Performans ölçütü: Sharpe (varsayılan) veya ortalama getiri.
Kombinasyon toplamları blok toplamlarından matris çarpımıyla hesaplanır (vektörel).
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

from trend.config import load_settings

# CSCV blok sayısı S (çift); SPEC değer vermiyor, literatür varsayılanı 16.
PBO_N_SPLITS = int(load_settings()["evaluation"]["pbo_splits"])


def pbo_cscv(
    trials: pd.DataFrame | np.ndarray,
    n_splits: int = PBO_N_SPLITS,
    metric: str = "sharpe",
    ppy: int = 365,
) -> dict[str, Any]:
    """CSCV ile PBO. `trials`: (T, N) günlük getiri (kolon = deneme, ör. parametre ızgarası noktaları)."""
    m = np.asarray(trials, dtype=float)
    if m.ndim != 2 or m.shape[1] < 2:
        raise ValueError("trials (T, N≥2) olmalı")
    if n_splits % 2 or n_splits < 2:
        raise ValueError("n_splits çift olmalı")
    if np.isnan(m).any():
        raise ValueError("trials içinde NaN var")
    T, N = m.shape
    rows = T // n_splits
    if rows < 2:
        raise ValueError("blok başına en az 2 satır gerekir")
    m = m[T - rows * n_splits :].reshape(n_splits, rows, N)
    bsum, bsq = m.sum(axis=1), (m**2).sum(axis=1)  # (S, N)

    combos = np.array(list(combinations(range(n_splits), n_splits // 2)))
    ind = np.zeros((len(combos), n_splits))
    ind[np.arange(len(combos))[:, None], combos] = 1.0
    n_half = rows * n_splits // 2

    def perf(s, q):
        mean = s / n_half
        if metric == "mean":
            return mean * ppy
        var = (q - n_half * mean**2) / (n_half - 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            return mean / np.sqrt(var) * np.sqrt(ppy)

    tr_s, tr_q = ind @ bsum, ind @ bsq
    is_perf = perf(tr_s, tr_q)
    oos_perf = perf(bsum.sum(0) - tr_s, bsq.sum(0) - tr_q)

    c = np.arange(len(combos))
    nstar = np.nanargmax(is_perf, axis=1)
    sel_oos = oos_perf[c, nstar]
    less = (oos_perf < sel_oos[:, None]).sum(axis=1)
    eq = (oos_perf == sel_oos[:, None]).sum(axis=1)
    rank = less + (eq + 1) / 2.0
    omega = rank / (N + 1.0)
    logits = np.log(omega / (1.0 - omega))
    sel_is = is_perf[c, nstar]
    slope, intercept = np.polyfit(sel_is, sel_oos, 1)
    return {
        "pbo": float(np.mean(logits <= 0)),
        "logits": logits,
        "is_perf": sel_is,
        "oos_perf": sel_oos,
        "degradation_slope": float(slope),
        "degradation_intercept": float(intercept),
        "prob_oos_loss": float(np.mean(sel_oos < 0)),
        "selected_counts": np.bincount(nstar, minlength=N),
        "n_combinations": int(len(combos)),
        "n_splits": int(n_splits),
        "rows_dropped": int(T - rows * n_splits),
    }
