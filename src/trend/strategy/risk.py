"""Oynaklık ve korelasyon tahmini (SPEC "Strateji" §2).

σ_i = max(rv30, rv90, FLOOR), yıllık (√365). R = EWMA korelasyonu (yarılanma 45 gün), sabit-korelasyon hedefine
%50 küçültme; Σ = D·R·D.

Varsayımlar:
- rv pencereleri takvim günüdür; getiriler `signal.log_returns` (boşluğu aşan getiri NaN). Std ddof=1.
- Min. gözlem şartını (30'da 20, 90'da 60) sağlamayan pencere değeri **geçersizdir**; geçersizse o bileşenin son
  geçerli değeri taşınır (nedensel ffill). Hiç geçerli değeri olmayan bileşen max()'a girmez; iki bileşen de hiç
  geçerli olmadıysa σ = NaN ve coin ağırlık alamaz (aktif kümeye girmez).
- EWMA korelasyonu sıfır ortalamalıdır (RiskMetrics) ve **ikili-tam** (pairwise-complete) güncellenir: bir gün
  yalnızca iki getirisi de olan çiftler için katkı yapar; tüm durumlar her gün aynı oranda söner (takvim zamanı),
  bu oran korelasyonda sadeleşir.
- Ortak gözlem sayısı `CORR_MIN_OBS`'tan az olan çiftin korelasyonu bilinmiyor sayılır ve küçültme hedefiyle
  (aktif kümedeki bilinen köşegen dışı ortalama) doldurulur; hiç bilinen çift yoksa hedef `CORR_FALLBACK` (=1,
  kötümser: tam korelasyon) alınır.
- Sabit-korelasyon hedefi ρ̄ = aktif kümenin (k hesabına giren coinler) köşegen dışı ortalamasıdır.
- Küçültülmüş matris pozitif yarı-tanımlı değilse özdeğerler 0'a kırpılıp köşegen 1'e yeniden ölçeklenir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trend.config import load_settings
from trend.strategy.signal import log_returns, rolling_std

# EWMA korelasyonunun geçerli sayılması için en az ortak gözlem; hiç geçerli çift yoksa sabit korelasyon (kötümser).
CORR_MIN_OBS = int(load_settings()["strategy"]["corr_min_obs"])
CORR_FALLBACK = float(load_settings()["strategy"]["corr_fallback"])


def annualized_vol(
    close: pd.DataFrame,
    windows: list[int] | tuple[int, ...],
    min_obs: dict,
    floor: float,
    ann_days: int,
) -> np.ndarray:
    """σ_i(t) = max(rv_w1, rv_w2, floor) yıllık; bkz. modül varsayımları. Dönüş: gün × varlık ndarray."""
    r = log_returns(close)
    comps = []
    for w in windows:
        m = int(min_obs[w] if w in min_obs else min_obs[str(w)])
        comps.append(rolling_std(r, int(w), m, ffill=True).to_numpy() * np.sqrt(ann_days))
    stack = np.stack(comps, axis=0)
    any_valid = np.isfinite(stack).any(axis=0)
    with np.errstate(invalid="ignore"):
        mx = np.nanmax(np.where(np.isfinite(stack), stack, -np.inf), axis=0)
    sigma = np.where(any_valid, np.maximum(mx, floor), np.nan)
    return sigma


class EwmaCorrelation:
    """İkili-tam, sıfır ortalamalı EWMA korelasyonu; günlük özyinelemeli güncelleme (motor döngüsünde)."""

    def __init__(self, n_assets: int, halflife: float):
        self.lam = 0.5 ** (1.0 / float(halflife))
        self.P = np.zeros((n_assets, n_assets))  # Σ λ^k r_i r_j (ikisi de var)
        self.Q = np.zeros((n_assets, n_assets))  # Σ λ^k r_i² (j de var)
        self.N = np.zeros((n_assets, n_assets), dtype=np.int64)  # ortak gözlem sayısı (sönümsüz)

    def update(self, r: np.ndarray) -> None:
        m = np.isfinite(r)
        r0 = np.where(m, r, 0.0)
        mf = m.astype(float)
        a = 1.0 - self.lam
        self.P *= self.lam
        self.P += a * np.outer(r0, r0)
        self.Q *= self.lam
        self.Q += a * np.outer(r0 * r0, mf)
        self.N += np.outer(m, m)

    def corr(self, idx: np.ndarray, min_obs: int = CORR_MIN_OBS) -> np.ndarray:
        """`idx` alt kümesi için korelasyon; bilinmeyen çiftler NaN, köşegen 1."""
        P = self.P[np.ix_(idx, idx)]
        Q = self.Q[np.ix_(idx, idx)]
        N = self.N[np.ix_(idx, idx)]
        den = np.sqrt(Q * Q.T)
        with np.errstate(invalid="ignore", divide="ignore"):
            R = np.where((N >= min_obs) & (den > 0), P / den, np.nan)
        R = np.clip(R, -1.0, 1.0)
        np.fill_diagonal(R, 1.0)
        return R


def shrink_to_constant(R: np.ndarray, alpha: float, fallback: float = CORR_FALLBACK) -> np.ndarray:
    """(1−α)·R + α·T, T = köşegen 1, köşegen dışı ρ̄ (bilinen çiftlerin ortalaması). Bilinmeyen çift = ρ̄."""
    n = R.shape[0]
    if n <= 1:
        return np.ones((n, n))
    off = ~np.eye(n, dtype=bool)
    known = off & np.isfinite(R)
    rho = float(R[known].mean()) if known.any() else float(fallback)
    Rf = np.where(np.isfinite(R), R, rho)
    T = np.full((n, n), rho)
    np.fill_diagonal(T, 1.0)
    out = (1.0 - alpha) * Rf + alpha * T
    np.fill_diagonal(out, 1.0)
    return nearest_psd_corr(out)


def nearest_psd_corr(R: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Negatif özdeğer varsa 0'a kırpar ve birim köşegene yeniden ölçekler (yoksa matris aynen döner)."""
    if R.shape[0] <= 1:
        return R
    w = np.linalg.eigvalsh(R)
    if w[0] >= -eps:
        return R
    w, V = np.linalg.eigh(R)
    w = np.clip(w, 0.0, None)
    A = (V * w) @ V.T
    d = np.sqrt(np.clip(np.diag(A), 1e-300, None))
    A = A / np.outer(d, d)
    np.fill_diagonal(A, 1.0)
    return A


def covariance(sigma: np.ndarray, R: np.ndarray) -> np.ndarray:
    """Σ = D·R·D."""
    return R * np.outer(sigma, sigma)
