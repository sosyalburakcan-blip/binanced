"""dsr.py ve mintrl.py: SPEC sağlamaları (SE ≈ 0,6; MinTRL 2,7 / 10,8 yıl) ve Monte Carlo kontrolleri."""

import numpy as np
import pandas as pd
import pytest

from trend.evaluation import dsr as D
from trend.evaluation import mintrl as T


def test_spec_sharpe_se_about_0_6_for_2_8_years():
    se = D.annual_sharpe_se(0.0, 2.8)
    assert se == pytest.approx(0.598, abs=0.002)
    assert round(se, 1) == 0.6
    assert D.annual_sharpe_se(0.5, 2.8) == pytest.approx(0.598, abs=0.003)  # günlükte SR² terimi ihmal edilebilir


def test_spec_min_trl_years():
    assert T.min_track_record_years(1.0) == pytest.approx(2.71, abs=0.01)
    assert T.min_track_record_years(0.5) == pytest.approx(10.83, abs=0.02)
    assert T.min_track_record_years(0.3, 0.5) == float("inf")
    # negatif çarpıklık ve kalın kuyruk gereken süreyi uzatır
    assert T.min_track_record_years(1.0, skew=-1.0, kurt=10.0) > T.min_track_record_years(1.0)


def test_min_trl_consistent_with_psr():
    """MinTRL gözlem sayısında PSR(0) = 1 − α olmalı (tanım gereği)."""
    sr = 0.04
    n = T.min_track_record_length(sr, 0.0, 0.0, 3.0, 0.05)
    assert D.probabilistic_sharpe_ratio(sr, 0.0, n, 0.0, 3.0) == pytest.approx(0.95, abs=1e-9)


def test_sharpe_se_monte_carlo():
    rng = np.random.default_rng(0)
    n, sr = 1000, 0.05
    x = rng.normal(sr * 0.01, 0.01, (4000, n))
    est = x.mean(1) / x.std(1, ddof=1)
    assert est.std() == pytest.approx(D.sharpe_se(sr, n), rel=0.05)


def test_psr_basics():
    assert D.probabilistic_sharpe_ratio(0.05, 0.05, 500) == pytest.approx(0.5)
    assert D.probabilistic_sharpe_ratio(0.1, 0.0, 1000) > 0.99


def test_expected_max_sharpe_monte_carlo():
    rng = np.random.default_rng(1)
    N, sd = 100, 0.3
    mc = rng.normal(0, sd, (20000, N)).max(axis=1).mean()
    assert D.expected_max_sharpe(N, sd**2) == pytest.approx(mc, rel=0.03)
    assert D.expected_max_sharpe(1000, 0.09) > D.expected_max_sharpe(100, 0.09)


def test_deflated_sharpe_noise_vs_signal_and_n_floor():
    rng = np.random.default_rng(2)
    idx = pd.date_range("2019-07-01", periods=1600, freq="D")
    noise = pd.Series(rng.normal(0.0, 0.02, 1600), index=idx)
    res = D.deflated_sharpe_ratio(noise, n_trials=10, var_trial_sharpe_annual=0.25, rf=0.0)
    assert res["n_trials_used"] == 100 and res["n_trials_given"] == 10  # alt sınır
    assert res["dsr"] < 0.5
    strong = pd.Series(rng.normal(0.004, 0.02, 1600), index=idx)  # yıllık SR ≈ 3,8
    res2 = D.deflated_sharpe_ratio(strong, n_trials=200, trial_sharpes_annual=rng.normal(0, 0.5, 200), rf=0.0)
    assert res2["dsr"] > 0.95 and res2["n_trials_used"] == 200
    assert res2["sr0_annual"] == pytest.approx(
        D.expected_max_sharpe(200, res2["var_trial_sharpe_annual"] / 365) * np.sqrt(365))
    assert D.n_trials_for_dsr(5, 11, 14) == 100 and D.n_trials_for_dsr(50, 243, 14) == 307


def test_min_trl_from_returns():
    rng = np.random.default_rng(3)
    r = pd.Series(rng.normal(0.001, 0.02, 2000), index=pd.date_range("2019-01-01", periods=2000, freq="D"))
    out = T.min_track_record_from_returns(r)
    assert out["track_years"] == pytest.approx(2000 / 365)
    assert out["min_trl_years"] == pytest.approx(
        T.min_track_record_years(out["sharpe_annual"], 0, out["skew"], out["kurt"]), rel=1e-9)
