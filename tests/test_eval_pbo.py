"""pbo.py: saf gürültüde PBO ≈ 0,5; baskın gerçek sinyalde PBO ≈ 0."""

from math import comb

import numpy as np
import pandas as pd
import pytest

from trend.evaluation.pbo import pbo_cscv


def test_pure_noise_pbo_about_half():
    vals = []
    for seed in range(6):
        m = np.random.default_rng(seed).normal(0, 0.01, (1600, 20))
        vals.append(pbo_cscv(m)["pbo"])
    assert np.mean(vals) == pytest.approx(0.5, abs=0.12)


def test_dominant_signal_pbo_near_zero():
    rng = np.random.default_rng(1)
    m = rng.normal(0, 0.01, (1600, 20))
    m[:, 3] += 0.003  # baskın gerçek beceri
    res = pbo_cscv(pd.DataFrame(m))
    assert res["pbo"] < 0.02
    assert res["selected_counts"].argmax() == 3
    assert res["prob_oos_loss"] < 0.02


def test_output_shapes_and_validation():
    m = np.random.default_rng(2).normal(0, 0.01, (1610, 8))
    res = pbo_cscv(m, n_splits=16)
    assert res["n_combinations"] == comb(16, 8) == len(res["logits"])
    assert res["rows_dropped"] == 10
    assert np.isfinite(res["degradation_slope"])
    assert pbo_cscv(m, n_splits=8)["n_combinations"] == comb(8, 4)
    with pytest.raises(ValueError):
        pbo_cscv(m, n_splits=15)
    with pytest.raises(ValueError):
        pbo_cscv(m[:, :1])


def test_overfit_selection_degrades_out_of_sample():
    """Gürültüde IS'te en iyi denemenin OOS performansı IS'tekinden belirgin düşüktür."""
    m = np.random.default_rng(3).normal(0, 0.01, (1600, 50))
    res = pbo_cscv(m)
    assert res["is_perf"].mean() > 0.5 and abs(res["oos_perf"].mean()) < 0.5 * res["is_perf"].mean()
    assert res["degradation_slope"] < 0.5
