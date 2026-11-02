"""regression.py: OLS katsayıları, Newey–West SE, yükselen/düşen beta ve Wald testi."""

import numpy as np
import pandas as pd
import pytest

from trend.evaluation import regression as R


def _idx(n):
    return pd.date_range("2019-07-01", periods=n, freq="D")


def test_newey_west_lag_rule():
    assert R.newey_west_lags(1650) == 7
    assert R.newey_west_lags(100) == 4


def test_factor_regression_recovers_coefficients():
    rng = np.random.default_rng(0)
    n = 4000
    btc = pd.Series(rng.normal(0.001, 0.035, n), index=_idx(n))
    ew = pd.Series(0.6 * btc + rng.normal(0, 0.03, n), index=_idx(n))
    y = 0.0002 + 0.3 * btc + 0.5 * ew + pd.Series(rng.normal(0, 0.01, n), index=_idx(n))
    res = R.factor_regression(y, btc, ew)
    assert res.params["btc"] == pytest.approx(0.3, abs=0.02)
    assert res.params["ew_universe"] == pytest.approx(0.5, abs=0.02)
    assert res.extra["alpha_annual"] == pytest.approx(0.0002 * 365, abs=0.06)
    assert res.r2 == pytest.approx(0.869, abs=0.03) and res.nobs == n
    assert set(res.summary().columns) == {"coef", "se_hac", "t", "p"}


def test_hac_se_close_to_classical_for_iid_errors():
    rng = np.random.default_rng(1)
    n = 3000
    x = rng.normal(0, 1, n)
    y = 1.0 + 2.0 * x + rng.normal(0, 1, n)
    res = R.ols_hac(pd.Series(y), pd.DataFrame({"x": x}))
    X = np.column_stack([np.ones(n), x])
    e = y - X @ res.params.to_numpy()
    classical = np.sqrt(np.diag(np.linalg.inv(X.T @ X) * (e @ e) / (n - 2)))
    assert res.se.to_numpy() == pytest.approx(classical, rel=0.15)


def test_hac_larger_than_white_under_autocorrelation():
    rng = np.random.default_rng(2)
    n = 3000
    x = np.zeros(n)
    u = np.zeros(n)
    for t in range(1, n):  # AR(1) regresör ve hata → HAC > White
        x[t] = 0.8 * x[t - 1] + rng.normal()
        u[t] = 0.8 * u[t - 1] + rng.normal()
    y = pd.Series(0.5 * x + u)
    white = R.ols_hac(y, pd.DataFrame({"x": x}), lags=0).se["x"]
    hac = R.ols_hac(y, pd.DataFrame({"x": x}), lags=20).se["x"]
    assert hac > 1.5 * white


def test_up_down_beta():
    rng = np.random.default_rng(3)
    n = 4000
    m = pd.Series(rng.normal(0, 0.035, n), index=_idx(n))
    y = 0.8 * m.clip(lower=0) + 0.2 * m.clip(upper=0) + pd.Series(rng.normal(0, 0.01, n), index=_idx(n))
    res = R.up_down_beta(y, m)
    assert res.params["beta_up"] == pytest.approx(0.8, abs=0.03)
    assert res.params["beta_down"] == pytest.approx(0.2, abs=0.03)
    assert res.extra["wald_p"] < 1e-6
    y2 = 0.5 * m + pd.Series(rng.normal(0, 0.01, n), index=_idx(n))
    assert R.up_down_beta(y2, m).extra["wald_p"] > 0.01
