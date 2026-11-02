"""nulls.py: sentetik döngü defteri ve ağırlık yollarıyla sıfır hipotezi üreteçleri."""

import numpy as np
import pandas as pd
import pytest

from trend.evaluation import nulls as N


def _setup(T=120):
    idx = pd.date_range("2020-01-01", periods=T, freq="D")
    cols = ["A", "B", "C", "D", "E"]
    w = pd.DataFrame(0.0, index=idx, columns=["A", "B", "C"])
    rows = []

    def add(asset, s, e, path):
        w.iloc[s:e, w.columns.get_loc(asset)] = path
        rows.append((asset, idx[s], idx[e] if e < T else pd.NaT, e >= T))

    add("A", 5, 15, 0.10)
    add("A", 30, 40, np.linspace(0.05, 0.10, 10))
    add("B", 10, 30, 0.08)
    add("C", 50, 60, 0.05)
    add("C", 100, 120, 0.07)  # açık döngü
    cycles = pd.DataFrame(rows, columns=["asset", "open_date", "close_date", "is_open"])
    cycles["profit"] = 1.0
    mem = pd.DataFrame(True, index=idx, columns=cols)
    return idx, w, cycles, mem


def test_start_of_day_weights_inverts_drift():
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    w0 = pd.DataFrame({"A": [0.3, 0.2, 0.0], "B": [0.2, 0.4, 0.5]}, index=idx)
    r = pd.DataFrame({"A": [0.1, -0.2, 0.05], "B": [-0.05, 0.3, 0.0]}, index=idx)
    rp = (w0 * r).sum(axis=1)
    w_end = (w0 * (1 + r)).div(1 + rp, axis=0)
    pd.testing.assert_frame_equal(N.start_of_day_weights(w_end, r), w0)


def test_portfolio_returns_known():
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    w = pd.DataFrame({"A": [0.5, 0.5, 0.0]}, index=idx)
    r = pd.DataFrame({"A": [0.1, np.nan, 0.2]}, index=idx)
    out = N.portfolio_returns(w, r, cost_rate=0.01)
    assert out.tolist() == pytest.approx([0.05 - 0.005, 0.0, -0.005])


def test_extract_paths_includes_zero_close_day_and_open_cycle():
    idx, w, cycles, _ = _setup()
    paths = N.extract_cycle_paths(cycles, w)
    assert paths[0][1] == 5 and len(paths[0][2]) == 11 and paths[0][2][-1] == 0.0
    assert len(paths[-1][2]) == 20 and paths[-1][2][-1] == 0.07


def test_date_shuffle_preserves_paths_and_respects_membership():
    idx, w, cycles, mem = _setup()
    mem.loc[:, "A"] = False
    mem.iloc[60:110, mem.columns.get_loc("A")] = True  # A yalnız 60–109 evrende
    out, info = N.null_date_shuffle(cycles, w, mem, np.random.default_rng(0))
    assert info["dropped"] == 0
    for c in ["A", "B", "C"]:
        assert out[c].sum() == pytest.approx(w[c].sum())  # yol toplamı korunur (toplam ≤ 1)
        assert (out[c] > 0).sum() == (w[c] > 0).sum()  # çakışma yok → pozitif gün sayısı aynı
    a = out["A"].to_numpy()
    assert (a[:60] == 0).all() and (a[110:] == 0).all()
    assert list(out.columns[:3]) == ["A", "B", "C"] and out[["D", "E"]].abs().sum().sum() == 0
    out2, _ = N.null_date_shuffle(cycles, w, mem, np.random.default_rng(0))
    pd.testing.assert_frame_equal(out, out2)
    out3, _ = N.null_date_shuffle(cycles, w, mem, np.random.default_rng(1))
    assert not out.equals(out3)


def test_date_shuffle_scales_down_when_total_exceeds_one():
    idx = pd.date_range("2020-01-01", periods=12, freq="D")
    w = pd.DataFrame(0.0, index=idx, columns=["A", "B"])
    w.iloc[0:10, 0] = 0.8
    w.iloc[0:10, 1] = 0.8
    cycles = pd.DataFrame({"asset": ["A", "B"], "open_date": [idx[0], idx[0]], "close_date": [idx[10], idx[10]],
                           "is_open": [False, False]})
    mem = pd.DataFrame(True, index=idx, columns=["A", "B"])
    out, _ = N.null_date_shuffle(cycles, w, mem, np.random.default_rng(0), gross_max=1.0)
    assert out.sum(axis=1).max() <= 1.0 + 1e-12


def test_date_shuffle_reports_unplaceable():
    idx, w, cycles, mem = _setup()
    mem.loc[:, "B"] = False
    mem.iloc[0:5, mem.columns.get_loc("B")] = True  # B'nin 21 günlük döngüsü sığmaz
    _, info = N.null_date_shuffle(cycles, w, mem, np.random.default_rng(0), max_tries=3)
    assert info["dropped"] == 1


def test_random_coin_preserves_exposure_and_count():
    idx, w, cycles, mem = _setup()
    mem.loc[idx[:50], "E"] = False  # E 50. günden önce aday değil
    for seed in range(5):
        out, info = N.null_random_coin(cycles, w, mem, np.random.default_rng(seed))
        assert info["dropped"] == 0
        np.testing.assert_allclose(out.sum(axis=1).to_numpy(), w.sum(axis=1).to_numpy())
        assert ((out > 0).sum(axis=1) == (w > 0).sum(axis=1)).all()
        assert (out.loc[idx[:50], "E"] == 0).all()
    many = [N.null_random_coin(cycles, w, mem, np.random.default_rng(s))[0] for s in range(40)]
    used = set().union(*[set(o.columns[(o > 0).any()]) for o in many])
    assert {"D", "E"} <= used  # hiç işlem görmemiş evren coinleri de seçilir


def test_p_value_and_run_null():
    assert N.null_p_value(5.0, np.array([1.0, 2.0, 3.0])) == pytest.approx(1 / 4)
    assert N.null_p_value(0.0, np.array([1.0, 2.0, 3.0])) == pytest.approx(1.0)
    assert N.percentile_rank(-0.3, np.array([-0.5, -0.4, -0.2, -0.1])) == 0.5
    idx, w, cycles, mem = _setup()
    rng0 = np.random.default_rng(0)
    rets = pd.DataFrame(rng0.normal(0, 0.02, (len(idx), 5)), index=idx, columns=list("ABCDE"))

    def stat(wh):
        r = N.portfolio_returns(wh, rets)
        return [r.mean() / r.std(), r.min()]

    gen = lambda rng: N.null_random_coin(cycles, w, mem, rng)[0]  # noqa: E731
    a = N.run_null(gen, stat, n_runs=20, seed=3)
    b = N.run_null(gen, stat, n_runs=20, seed=3)
    assert a.shape == (20, 2) and np.array_equal(a, b)
    obs = stat(w)[0]
    p = N.null_p_value(obs, a[:, 0])
    assert 1 / 21 <= p <= 1.0
