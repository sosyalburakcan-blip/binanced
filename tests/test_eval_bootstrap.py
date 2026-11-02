"""bootstrap.py: durağan blok bootstrap indeksleri, eşleştirilmiş Sharpe testi, düşüş dağılımları, ufuk tablosu."""

import time

import numpy as np
import pandas as pd
import pytest

from trend.evaluation import bootstrap as B
from trend.evaluation.metrics import drawdown

FAST = {"n_paths": 2000, "seed": 7}


def _series(x, start="2020-01-01"):
    return pd.Series(x, index=pd.date_range(start, periods=len(x), freq="D"))


def test_indices_shape_range_and_block_length():
    rng = np.random.default_rng(0)
    idx = B.stationary_indices(500, 3000, 200, 30.0, rng)
    assert idx.shape == (200, 3000) and idx.min() >= 0 and idx.max() < 500
    cont = (np.diff(idx, axis=1) % 500) == 1  # blok devamı
    # yeni blok başı oranı ≈ 1/30 (rastgele başlangıcın tesadüfen ardıl olması ihmal edilebilir)
    assert (1 - cont.mean()) == pytest.approx(1 / 30, rel=0.05)


def test_deterministic_given_seed():
    r = _series(np.random.default_rng(1).normal(0, 0.01, 400))
    a = B.bootstrap_sharpe(r, n_paths=300, seed=11)["dist"]
    b = B.bootstrap_sharpe(r, n_paths=300, seed=11)["dist"]
    c = B.bootstrap_sharpe(r, n_paths=300, seed=12)["dist"]
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_bootstrap_sharpe_se_matches_iid_theory():
    n = 1500
    r = _series(np.random.default_rng(2).normal(0.0005, 0.02, n))
    res = B.bootstrap_sharpe(r, **FAST)
    theory = np.sqrt(1 / (n - 1)) * np.sqrt(365)
    assert res["se"] == pytest.approx(theory, rel=0.2)
    assert res["ci95"][0] < res["sharpe"] < res["ci95"][1]


def test_paired_sharpe_test_detects_better_strategy():
    rng = np.random.default_rng(3)
    n = 1800
    bench = rng.normal(0.0003, 0.03, n)
    strat = 0.5 * bench + rng.normal(0.0015, 0.01, n)  # çok daha yüksek Sharpe, korelasyonlu
    res = B.paired_sharpe_test(_series(strat), _series(bench), rf=0.0, **FAST)
    assert res["passed"] and res["p_value"] < 0.01 and res["lower_one_sided"] > 0
    assert res["ci95_diff"][0] > 0 and res["sharpe_diff"] > 1
    rev = B.paired_sharpe_test(_series(bench), _series(strat), rf=0.0, **FAST)
    assert not rev["passed"] and rev["p_value"] > 0.99


def test_paired_identical_series_never_passes():
    r = _series(np.random.default_rng(4).normal(0.001, 0.02, 600))
    res = B.paired_sharpe_test(r, r.copy(), rf=0.0, n_paths=500, seed=1)
    assert res["sharpe_diff"] == 0 and res["p_value"] == 1.0 and not res["passed"]


def test_paired_alignment_uses_common_dates():
    a = _series(np.random.default_rng(5).normal(0.001, 0.02, 500))
    b = a.iloc[100:] * 0.5
    res = B.paired_sharpe_test(a, b, rf=0.0, n_paths=200, seed=1)
    assert res["n_obs"] == 400


def test_max_drawdown_distribution_observed_matches_metrics():
    r = _series(np.random.default_rng(6).normal(0.0005, 0.03, 700))
    res = B.max_drawdown_distribution(r, **FAST)
    assert res["observed"] == pytest.approx(drawdown(r).min())
    assert res["q05"] <= res["median"] <= res["q95"] <= 0


def test_paired_drawdown_comparison_criterion6():
    other = _series(np.random.default_rng(7).normal(0.0005, 0.02, 1000))
    res = B.paired_drawdown_comparison(other * 0.2, other, ratio=0.5, **FAST)
    assert res["passed"] and res["frac_paths_passing"] > 0.95
    assert abs(res["median_mdd_strategy"]) < 0.5 * abs(res["median_mdd_other"])
    same = B.paired_drawdown_comparison(other, other, ratio=0.5, **FAST)
    assert not same["passed"] and same["frac_paths_passing"] == 0


def test_drawdown_horizon_table_monotone():
    r = _series(np.random.default_rng(8).normal(0.0005, 0.03, 1000))
    t = B.drawdown_horizon_table(r, [30, 60, 90, 180, 365], **FAST)
    assert list(t.index) == [30, 60, 90, 180, 365] and "dd_q95" in t.columns
    assert (np.diff(t["dd_q95"].to_numpy()) <= 0).all()  # uzun ufukta daha derin
    assert (t["dd_q95"] <= t["dd_median"]).all()
    # sabit pozitif getiri → düşüş yok; seri ufuktan kısa olsa da çalışır
    flat = B.drawdown_horizon_table(_series(np.full(100, 0.001)), [30, 365], n_paths=100, seed=1)
    assert (flat.to_numpy() == 0).all()


def test_horizon_quantile_matches_direct_computation():
    r = _series(np.random.default_rng(9).normal(0, 0.02, 400))
    t = B.drawdown_horizon_table(r, [30], n_paths=500, seed=3)
    rng = np.random.default_rng(3)
    idx = B.stationary_indices(400, 400, 500, 30.0, rng)
    mdd30 = B.max_drawdown_paths(r.to_numpy()[idx][:, :30])
    assert t.loc[30, "dd_q95"] == pytest.approx(np.quantile(mdd30, 0.05))


def test_full_size_run_is_fast():
    """Ayarlardaki 10.000 yol, ~7 yıllık eşleştirilmiş seri: makul sürede."""
    n = 7 * 365
    rng = np.random.default_rng(10)
    s, b = _series(rng.normal(0.001, 0.02, n)), _series(rng.normal(0.0005, 0.03, n))
    t0 = time.perf_counter()
    res = B.paired_sharpe_test(s, b, rf=0.0)
    assert res["n_paths"] == 10000
    assert time.perf_counter() - t0 < 60
