"""Kıyas 7: strateji getirisi ~ BTC getirisi + evren eşit ağırlıklı getiri; yükselen/düşen piyasa betaları.

"Strateji sadece kaldıracı azaltılmış piyasa riski mi?" sorusu için.
- OLS; standart hatalar HAC / Newey–West (1987), Bartlett çekirdeği w_l = 1 − l/(L+1), küçük örneklem düzeltmesi
  yok. Gecikme L varsayılanı Newey–West (1994) kuralı: ⌊4·(T/100)^(2/9)⌋. p-değerleri t(T − k) dağılımından.
- Yükselen/düşen piyasa betaları (Henriksson–Merton 1981 tipi ayrık beta):
  r_s = α + β⁺·max(r_m, 0) + β⁻·min(r_m, 0) + ε; H0: β⁺ = β⁻ için HAC Wald testi (χ²₁).
`rf` verilirse tüm serilerden düşülür (fazla getiri regresyonu); α yıllık = α_günlük · 365.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from trend.evaluation.common import excess_returns


def newey_west_lags(n: int) -> int:
    return int(np.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))


@dataclass
class RegressionResult:
    params: pd.Series
    se: pd.Series
    tvalues: pd.Series
    pvalues: pd.Series
    r2: float
    nobs: int
    lags: int
    cov: pd.DataFrame
    extra: dict = field(default_factory=dict)

    def summary(self) -> pd.DataFrame:
        return pd.DataFrame({"coef": self.params, "se_hac": self.se, "t": self.tvalues, "p": self.pvalues})


def ols_hac(y: pd.Series, X: pd.DataFrame, lags: int | None = None, add_const: bool = True) -> RegressionResult:
    """OLS + Newey–West HAC kovaryansı: (X'X)⁻¹ [Σ_l w_l Γ_l] (X'X)⁻¹, Γ_l = Σ_t x_t e_t e_{t−l} x_{t−l}'."""
    df = pd.concat([y.rename("_y"), X], axis=1, join="inner").dropna()
    yv = df["_y"].to_numpy()
    Xd = df.drop(columns="_y")
    if add_const:
        Xd.insert(0, "const", 1.0)
    names = list(Xd.columns)
    Xv = Xd.to_numpy(dtype=float)
    n, k = Xv.shape
    L = newey_west_lags(n) if lags is None else int(lags)
    beta, *_ = np.linalg.lstsq(Xv, yv, rcond=None)
    e = yv - Xv @ beta
    xe = Xv * e[:, None]
    S = xe.T @ xe
    for lag in range(1, L + 1):
        G = xe[lag:].T @ xe[:-lag]
        S += (1.0 - lag / (L + 1.0)) * (G + G.T)
    inv = np.linalg.inv(Xv.T @ Xv)
    cov = inv @ S @ inv
    se = np.sqrt(np.diag(cov))
    t = beta / se
    p = 2.0 * stats.t.sf(np.abs(t), df=n - k)
    sst = ((yv - yv.mean()) ** 2).sum()
    r2 = 1.0 - (e**2).sum() / sst if sst > 0 else float("nan")
    s = lambda v: pd.Series(v, index=names)  # noqa: E731
    return RegressionResult(s(beta), s(se), s(t), s(p), float(r2), int(n), L,
                            pd.DataFrame(cov, index=names, columns=names))


def factor_regression(
    strategy: pd.Series,
    btc: pd.Series,
    ew_universe: pd.Series,
    rf: pd.Series | float | None = None,
    lags: int | None = None,
    ppy: int = 365,
) -> RegressionResult:
    """r_s = α + β_BTC·r_BTC + β_EW·r_EW + ε (HAC)."""
    X = pd.concat([excess_returns(btc, rf).rename("btc"), excess_returns(ew_universe, rf).rename("ew_universe")],
                  axis=1)
    res = ols_hac(excess_returns(strategy, rf), X, lags)
    res.extra["alpha_annual"] = float(res.params["const"] * ppy)
    return res


def up_down_beta(
    strategy: pd.Series,
    market: pd.Series,
    rf: pd.Series | float | None = None,
    lags: int | None = None,
    ppy: int = 365,
) -> RegressionResult:
    """r_s = α + β⁺·max(r_m, 0) + β⁻·min(r_m, 0) + ε; ayrıca H0: β⁺ = β⁻ Wald testi (HAC)."""
    m = excess_returns(market, rf)
    X = pd.DataFrame({"beta_up": m.clip(lower=0.0), "beta_down": m.clip(upper=0.0)})
    res = ols_hac(excess_returns(strategy, rf), X, lags)
    R = np.array([0.0, 1.0, -1.0])
    diff = float(R @ res.params.to_numpy())
    var = float(R @ res.cov.to_numpy() @ R)
    wald = diff**2 / var
    res.extra.update(alpha_annual=float(res.params["const"] * ppy), beta_diff=diff, wald_stat=wald,
                     wald_p=float(stats.chi2.sf(wald, df=1)))
    return res
