"""Sharpe standart hatası, Probabilistic Sharpe Ratio (PSR) ve Deflated Sharpe Ratio (DSR).

Kaynaklar:
- Lo (2002) "The Statistics of Sharpe Ratios"; Mertens (2002); Opdyke (2007): çarpıklık/basıklık düzeltmeli
  SE(ŜR) = √[(1 − γ3·SR + (γ4 − 1)/4 · SR²) / (n − 1)]   (SR gözlem frekansında, γ4 Pearson basıklığı, normal = 3)
- Bailey ve López de Prado (2012) "The Sharpe Ratio Efficient Frontier": PSR(SR*) = Φ[(ŜR − SR*)·√(n−1) /
  √(1 − γ3·ŜR + (γ4 − 1)/4 · ŜR²)]
- Bailey ve López de Prado (2014) "The Deflated Sharpe Ratio": DSR = PSR(SR0),
  SR0 = √V[SR_n] · [(1 − γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e))], γ = Euler–Mascheroni.

Tüm iç hesaplar günlük (gözlem) frekansındadır; yıllık girdiler √365 (Sharpe) ve 365 (varyans) ile çevrilir.
N, settings `evaluation.dsr_n_min` (100) altına inemez (SPEC "Ön kayıt → Deneme sayısı").
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from trend.evaluation.common import excess_returns, periods_per_year, settings

EULER_GAMMA = 0.5772156649015329


def sharpe_moments(returns: pd.Series, rf: pd.Series | float | None = None) -> dict[str, float]:
    """Gözlem frekansında Sharpe (ddof=1), çarpıklık γ3 ve Pearson basıklığı γ4 (bias=False), n."""
    ex = excess_returns(returns.dropna(), rf).to_numpy()
    return {
        "sr": float(ex.mean() / ex.std(ddof=1)),
        "skew": float(stats.skew(ex, bias=False)),
        "kurt": float(stats.kurtosis(ex, fisher=False, bias=False)),
        "n": int(ex.size),
    }


def _var_term(sr: float, skew: float, kurt: float) -> float:
    return 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2


def sharpe_se(sr: float, n: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    """Gözlem frekansında Sharpe standart hatası (Lo 2002 / Mertens 2002)."""
    return float(np.sqrt(_var_term(sr, skew, kurt) / (n - 1)))


def annual_sharpe_se(
    sr_annual: float, years: float, skew: float = 0.0, kurt: float = 3.0, ppy: int = 365
) -> float:
    """Yıllık Sharpe'ın SE'si, günlük gözlemlerden: SE_günlük(SR/√ppy, n = years·ppy) · √ppy.

    SPEC sağlaması: 2,8 yıl, SR = 0, normal getiri → 0,598 ≈ 0,6.
    """
    n = int(round(years * ppy))
    return sharpe_se(sr_annual / np.sqrt(ppy), n, skew, kurt) * np.sqrt(ppy)


def probabilistic_sharpe_ratio(
    sr: float, sr_benchmark: float, n: int, skew: float = 0.0, kurt: float = 3.0
) -> float:
    """PSR(SR*) = P(gerçek SR > SR*) (Bailey ve López de Prado 2012); SR'ler gözlem frekansında."""
    return float(stats.norm.cdf((sr - sr_benchmark) * np.sqrt(n - 1) / np.sqrt(_var_term(sr, skew, kurt))))


def expected_max_sharpe(n_trials: int, var_trials: float) -> float:
    """N bağımsız denemede beklenen en yüksek Sharpe (SR0), sıfır gerçek beceri altında; birimi √var_trials'ınki."""
    if n_trials < 2:
        return 0.0
    z1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(var_trials) * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2))


def effective_n_trials(n_trials: int, cfg: dict[str, Any] | None = None) -> int:
    """N = max(N, dsr_n_min)."""
    return int(max(int(n_trials), int(settings(cfg)["evaluation"]["dsr_n_min"])))


def n_trials_for_dsr(n_experiments: int, grid_size: int, n_variants: int, cfg: dict[str, Any] | None = None) -> int:
    """SPEC: N = experiments.md denemeleri + ızgara boyutu + varyantlar, alt sınır dsr_n_min."""
    return effective_n_trials(n_experiments + grid_size + n_variants, cfg)


def deflated_sharpe_ratio(
    returns: pd.Series,
    n_trials: int,
    var_trial_sharpe_annual: float | None = None,
    trial_sharpes_annual: np.ndarray | None = None,
    rf: pd.Series | float | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """DSR (Bailey ve López de Prado 2014). Deneme Sharpe varyansı yıllık birimde verilir (doğrudan ya da
    deneme Sharpe'larından, ddof=1). N, dsr_n_min altına inemez. Geç/kal kriteri 2: DSR ≥ 0,95."""
    ppy = periods_per_year(cfg)
    if var_trial_sharpe_annual is None:
        if trial_sharpes_annual is None:
            raise ValueError("var_trial_sharpe_annual veya trial_sharpes_annual gerekir")
        var_trial_sharpe_annual = float(np.var(np.asarray(trial_sharpes_annual, dtype=float), ddof=1))
    n_eff = effective_n_trials(n_trials, cfg)
    m = sharpe_moments(returns, rf)
    sr0 = expected_max_sharpe(n_eff, var_trial_sharpe_annual / ppy)
    dsr = probabilistic_sharpe_ratio(m["sr"], sr0, m["n"], m["skew"], m["kurt"])
    return {
        "dsr": dsr,
        "psr0": probabilistic_sharpe_ratio(m["sr"], 0.0, m["n"], m["skew"], m["kurt"]),
        "sharpe_annual": m["sr"] * np.sqrt(ppy),
        "sr0_annual": sr0 * np.sqrt(ppy),
        "sharpe_se_annual": sharpe_se(m["sr"], m["n"], m["skew"], m["kurt"]) * np.sqrt(ppy),
        "n_trials_used": n_eff,
        "n_trials_given": int(n_trials),
        "var_trial_sharpe_annual": float(var_trial_sharpe_annual),
        "skew": m["skew"],
        "kurt": m["kurt"],
        "n_obs": m["n"],
    }
