"""Pozisyon büyüklüğü (SPEC "Strateji" §3).

A = {i : S_i > 0}, v_i = 1/σ_i. k* = en büyük k öyle ki w_full = min(k·v, CAP) için √(wᵀΣw) ≤ TGT ve
Σ w_full ≤ GMAX (ikiye bölme). Hedef w* = S · w_full.

Not: √(wᵀΣw) negatif korelasyonlarda k'ya göre monoton olmayabilir; ikiye bölme yine de her zaman uygun (kısıtları
sağlayan) bir k döndürür (alt uç). Kripto korelasyonlarında ve küçültmeden sonra pratikte monotondur.
"""

from __future__ import annotations

import numpy as np


def portfolio_vol(w: np.ndarray, cov: np.ndarray) -> float:
    q = float(w @ cov @ w)
    return float(np.sqrt(q)) if q > 0 else 0.0


def solve_k(
    v: np.ndarray,
    cap: np.ndarray,
    cov: np.ndarray,
    target_vol: float,
    gross_max: float,
    tol: float,
) -> tuple[float, np.ndarray]:
    """En büyük uygun k ve w_full = min(k·v, cap). `tol` = k üzerinde mutlak tolerans (settings.bisection_tol)."""
    n = v.shape[0]
    if n == 0:
        return 0.0, np.zeros(0)

    def feasible(k: float) -> bool:
        w = np.minimum(k * v, cap)
        return w.sum() <= gross_max and portfolio_vol(w, cov) <= target_vol

    k_hi = float(np.max(cap / v))  # bunun üstünde tüm ağırlıklar tavanda
    if feasible(k_hi):
        return k_hi, np.minimum(k_hi * v, cap)
    lo, hi = 0.0, k_hi
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if feasible(mid):
            lo = mid
        else:
            hi = mid
    return lo, np.minimum(lo * v, cap)


def equal_weights(n_universe: int, n_active: int) -> np.ndarray:
    """Kıyas 6 (oynaklık ayarsız eşit ağırlık): w_full = 1/|E|, tavan ve hedef oynaklık yok."""
    if n_active == 0 or n_universe == 0:
        return np.zeros(n_active)
    return np.full(n_active, 1.0 / n_universe)
