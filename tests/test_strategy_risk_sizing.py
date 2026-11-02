"""G7: oynaklık, korelasyon (SPEC §2) ve bisection ile pozisyon büyüklüğü (SPEC §3)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trend.strategy.risk import EwmaCorrelation, annualized_vol, covariance, nearest_psd_corr, shrink_to_constant
from trend.strategy.sizing import portfolio_vol, solve_k

MIN_OBS = {30: 20, 90: 60}


def _prices(returns: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(100 * np.exp(np.concatenate([[0.0], np.cumsum(returns)])), columns=["a"])


def test_vol_floor_and_max_of_windows():
    rng = np.random.default_rng(0)
    calm = rng.standard_normal(200) * 0.005           # yıllık ≈ %9.5 → taban %30
    sig = annualized_vol(_prices(calm), [30, 90], MIN_OBS, 0.30, 365)[:, 0]
    assert np.allclose(sig[100:], 0.30)
    # son 30 gün çok oynak: rv30 > rv90 → σ = rv30
    r = np.concatenate([rng.standard_normal(170) * 0.02, rng.standard_normal(30) * 0.08])
    p = _prices(r)
    sig = annualized_vol(p, [30, 90], MIN_OBS, 0.30, 365)[:, 0]
    lr = np.log(p["a"]).diff()
    rv30 = lr.rolling(30, min_periods=20).std().iloc[-1] * np.sqrt(365)
    rv90 = lr.rolling(90, min_periods=60).std().iloc[-1] * np.sqrt(365)
    assert rv30 > rv90 and sig[-1] == pytest.approx(rv30, rel=1e-12)
    # tersine: sakinleşme sonrası rv90 büyük kalır (FTT tipi korunma)
    r2 = np.concatenate([rng.standard_normal(170) * 0.08, rng.standard_normal(30) * 0.02])
    p2 = _prices(r2)
    lr2 = np.log(p2["a"]).diff()
    rv90b = lr2.rolling(90, min_periods=60).std().iloc[-1] * np.sqrt(365)
    assert annualized_vol(p2, [30, 90], MIN_OBS, 0.30, 365)[-1, 0] == pytest.approx(rv90b, rel=1e-12)


def test_vol_min_obs_failure_carries_last_valid_value():
    rng = np.random.default_rng(1)
    p = _prices(rng.standard_normal(150) * 0.05)
    p.iloc[120:135] = np.nan  # 15 günlük boşluk → 30 günlük pencerede < 20 gözlem
    lr = np.log(p["a"]).diff()
    rv30 = lr.rolling(30, min_periods=20).std()
    rv90 = lr.rolling(90, min_periods=60).std()
    assert rv30.iloc[140:146].isna().any()
    sig = annualized_vol(p, [30, 90], MIN_OBS, 0.30, 365)[:, 0]
    k = int(np.nonzero(rv30.isna().to_numpy() & (np.arange(len(p)) > 125))[0][0])
    exp = max(rv30.iloc[:k].dropna().iloc[-1], rv90.ffill().iloc[k]) * np.sqrt(365)
    assert sig[k] == pytest.approx(max(exp, 0.30), rel=1e-12)
    # hiç geçerli pencere yoksa σ tanımsız (coin ağırlık alamaz)
    short = annualized_vol(_prices(rng.standard_normal(10) * 0.05), [30, 90], MIN_OBS, 0.30, 365)
    assert np.isnan(short).all()


def test_ewma_correlation_matches_direct_weighted_formula():
    rng = np.random.default_rng(2)
    n = 300
    x = rng.standard_normal(n)
    y = 0.6 * x + 0.8 * rng.standard_normal(n)
    z = rng.standard_normal(n)
    z[50:120] = np.nan  # eksik veri: ikili-tam
    ec = EwmaCorrelation(3, 45)
    for t in range(n):
        ec.update(np.array([x[t], y[t], z[t]]))
    lam = 0.5 ** (1 / 45)
    w = lam ** np.arange(n)[::-1]
    rxy = (w * x * y).sum() / np.sqrt((w * x * x).sum() * (w * y * y).sum())
    m = ~np.isnan(z)
    rxz = (w[m] * x[m] * z[m]).sum() / np.sqrt((w[m] * x[m] ** 2).sum() * (w[m] * z[m] ** 2).sum())
    R = ec.corr(np.array([0, 1, 2]))
    assert R[0, 1] == pytest.approx(rxy, rel=1e-10) and R[0, 2] == pytest.approx(rxz, rel=1e-10)
    assert np.allclose(np.diag(R), 1.0)
    # yetersiz ortak gözlem → bilinmiyor (NaN)
    ec2 = EwmaCorrelation(2, 45)
    for t in range(30):
        ec2.update(np.array([x[t], y[t]]))
    assert np.isnan(ec2.corr(np.array([0, 1]))[0, 1])


def test_shrinkage_to_constant_correlation():
    R = np.array([[1, .8, .4], [.8, 1, .6], [.4, .6, 1.0]])
    S = shrink_to_constant(R, 0.5)
    exp = np.array([[1, .7, .5], [.7, 1, .6], [.5, .6, 1.0]])  # ρ̄ = 0.6
    np.testing.assert_allclose(S, exp, atol=1e-15)
    # bilinmeyen çift ρ̄ ile doldurulur
    R2 = np.array([[1, .8, np.nan], [.8, 1, .4], [np.nan, .4, 1.0]])
    S2 = shrink_to_constant(R2, 0.5)
    assert S2[0, 2] == pytest.approx(0.6) and S2[0, 1] == pytest.approx(0.7)
    # hiç bilinen çift yoksa kötümser 1.0
    S3 = shrink_to_constant(np.array([[1, np.nan], [np.nan, 1.0]]), 0.5)
    assert S3[0, 1] == pytest.approx(1.0)


def test_psd_repair():
    R = np.array([[1, .95, -.9], [.95, 1, .9], [-.9, .9, 1.0]])
    assert np.linalg.eigvalsh(R)[0] < 0
    F = nearest_psd_corr(R)
    assert np.linalg.eigvalsh(F)[0] > -1e-10 and np.allclose(np.diag(F), 1.0)


def _cov(sig, rho):
    n = len(sig)
    R = np.full((n, n), rho)
    np.fill_diagonal(R, 1.0)
    return covariance(np.asarray(sig), R)


def test_bisection_vol_constraint_binds():
    sig = np.array([0.6, 0.9, 1.2, 0.8])
    cov = _cov(sig, 0.7)
    cap = np.full(4, 0.5)
    k, w = solve_k(1 / sig, cap, cov, 0.35, 1.0, 1e-12)
    assert portfolio_vol(w, cov) <= 0.35 and portfolio_vol(w, cov) == pytest.approx(0.35, rel=1e-8)
    assert w.sum() <= 1.0
    w_up = np.minimum((k + 1e-8) * (1 / sig), cap)
    assert portfolio_vol(w_up, cov) > 0.35  # en büyük k
    # ham ağırlıklar ters oynaklık oranında (tavan bağlamıyorsa)
    np.testing.assert_allclose(w * sig, (w * sig)[0])


def test_bisection_gross_constraint_binds():
    sig = np.full(20, 0.30)
    cov = _cov(sig, 0.0)
    k, w = solve_k(1 / sig, np.full(20, 0.10), cov, 0.35, 1.0, 1e-12)
    assert w.sum() <= 1.0 and w.sum() == pytest.approx(1.0, rel=1e-9)
    assert portfolio_vol(w, cov) < 0.35
    np.testing.assert_allclose(w, 0.05, rtol=1e-9)


def test_caps_bind_when_few_assets_trend():
    sig = np.array([0.4, 0.7, 0.5])
    cap = np.array([0.10, 0.05, 0.05])
    cov = _cov(sig, 0.8)
    k, w = solve_k(1 / sig, cap, cov, 0.35, 1.0, 1e-12)
    np.testing.assert_allclose(w, cap)  # tüm ağırlıklar tavanda, oynaklık hedefin altında (kabul edilir)
    assert portfolio_vol(w, cov) < 0.35


def test_s_tier_preserved_and_target_never_exceeded():
    rng = np.random.default_rng(5)
    for _ in range(200):
        n = int(rng.integers(1, 25))
        sig = rng.uniform(0.3, 2.0, n)
        rho = rng.uniform(0.0, 0.9)
        cov = _cov(sig, rho)
        cap = rng.choice([0.10, 0.05, 0.03], n)
        S = rng.choice([1, 2, 3], n) / 3
        k, wf = solve_k(1 / sig, cap, cov, 0.35, 1.0, 1e-9)
        wt = S * wf
        assert (wf <= cap + 1e-15).all() and wf.sum() <= 1.0 + 1e-12
        assert portfolio_vol(wf, cov) <= 0.35 + 1e-12
        assert portfolio_vol(wt, cov) <= 0.35 + 1e-12 and wt.sum() <= 1.0 + 1e-12
        np.testing.assert_allclose(wt / wf, S)  # kademe korunur


def test_empty_active_set():
    k, w = solve_k(np.zeros(0), np.zeros(0), np.zeros((0, 0)), 0.35, 1.0, 1e-9)
    assert k == 0.0 and w.size == 0
