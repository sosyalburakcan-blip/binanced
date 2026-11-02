"""satellite.py: 0,5·SR_T0 > ρ·SR_BTC200 → %20, aksi halde %0."""

import numpy as np
import pandas as pd
import pytest

from trend.evaluation.satellite import satellite_from_returns, satellite_weight


def test_rule_thresholds():
    assert satellite_weight(1.0, 0.8, 0.6) == pytest.approx(0.20)  # 0,50 > 0,48
    assert satellite_weight(0.9, 0.8, 0.6) == 0.0  # 0,45 < 0,48
    assert satellite_weight(1.0, 1.0, 0.5) == 0.0  # eşitlik geçmez (katı >)
    assert satellite_weight(0.2, 0.8, -0.1) == pytest.approx(0.20)  # negatif korelasyon


def test_from_returns():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2019-07-01", periods=2000, freq="D")
    b = pd.Series(rng.normal(0.001, 0.03, 2000), index=idx)
    t0 = pd.Series(0.2 * b + rng.normal(0.001, 0.015, 2000), index=idx)
    out = satellite_from_returns(t0, b, rf=0.0)
    assert out["rho"] == pytest.approx(t0.corr(b))
    assert out["weight"] == (0.20 if 0.5 * out["sr_t0"] > out["rho"] * out["sr_btc200"] else 0.0)
    assert out["n_obs"] == 2000
