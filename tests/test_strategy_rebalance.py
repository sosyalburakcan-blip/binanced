"""G7: yeniden dengeleme kuralları ve haftalık giriş / günlük çıkış (SPEC §4)."""

from __future__ import annotations

import numpy as np
import pytest

from trend.strategy.rebalance import (
    BAND, ENTRY, EXIT, NONE, SKIP_MINTRADE, SKIP_WEEKLY, TIER, mintrade, rebalance_orders,
)

REL, MINB = 0.25, 0.005


def _rb(w, wt, s_now, s_last, held=None, mt=0.0025, allow=True):
    w, wt = np.asarray(w, float), np.asarray(wt, float)
    held = (w > 0) if held is None else np.asarray(held)
    return rebalance_orders(held, w, wt, np.asarray(s_now), np.asarray(s_last), mt, allow, REL, MINB)


def test_full_exit_always_even_below_mintrade():
    d, r = _rb([0.001, 0.04], [0.0, 0.0], [0, 0], [3, 1])
    assert d.tolist() == [-0.001, -0.04] and (r == EXIT).all()
    # haftalık kural çıkışı engellemez
    d, r = _rb([0.001], [0.0], [0], [3], allow=False)
    assert d.tolist() == [-0.001] and r[0] == EXIT


def test_entry_and_tier_change_trade_to_target():
    d, r = _rb([0.0, 0.03, 0.03], [0.02, 0.05, 0.01], [1, 3, 1], [-1, 2, 2])
    assert d == pytest.approx([0.02, 0.02, -0.02]) and r.tolist() == [ENTRY, TIER, TIER]


def test_drift_band_trades_only_to_band_edge():
    # w* = 0.04 → bant max(0.01, 0.005) = 0.01
    d, r = _rb([0.055, 0.025, 0.049, 0.031], [0.04] * 4, [3] * 4, [3] * 4)
    assert d == pytest.approx([0.05 - 0.055, 0.03 - 0.025, 0.0, 0.0])
    assert r.tolist() == [BAND, BAND, NONE, NONE]
    # küçük hedefte mutlak alt sınır 0.005
    d, r = _rb([0.019, 0.0149], [0.01, 0.01], [1, 1], [1, 1])
    assert r[1] == NONE and r[0] == BAND and d[0] == pytest.approx(0.015 - 0.019)
    # bant kenarına işlem MINTRADE'in altındaysa yapılmaz
    d, r = _rb([0.0151], [0.01], [1], [1])
    assert r[0] == SKIP_MINTRADE and d[0] == 0.0


def test_mintrade_skips_small_non_exit_trades():
    assert mintrade(10000, 10, 1.1, 0.0025) == 0.0025
    assert mintrade(2000, 10, 1.1, 0.0025) == pytest.approx(0.0055)
    d, r = _rb([0.0, 0.03], [0.002, 0.032], [1, 3], [-1, 2], mt=0.0025)
    assert d.tolist() == [0.0, 0.0] and r.tolist() == [SKIP_MINTRADE, SKIP_MINTRADE]
    d, r = _rb([0.0], [0.006], [1], [-1], mt=0.0055)
    assert r[0] == ENTRY


def test_weekly_entry_blocks_only_increasing_trades():
    w = [0.0, 0.03, 0.03, 0.055, 0.025, 0.05]
    wt = [0.02, 0.05, 0.01, 0.04, 0.04, 0.0]
    s_now = [1, 3, 1, 3, 3, 0]
    s_last = [-1, 2, 2, 3, 3, 3]
    d, r = _rb(w, wt, s_now, s_last, allow=False)
    # giriş, kademe artışı, bant alımı atlanır; kademe düşüşü, bant satışı, çıkış yapılır
    assert r.tolist() == [SKIP_WEEKLY, SKIP_WEEKLY, TIER, BAND, SKIP_WEEKLY, EXIT]
    assert d == pytest.approx([0, 0, -0.02, -0.005, 0, -0.05])
    d2, r2 = _rb(w, wt, s_now, s_last, allow=True)
    assert r2.tolist() == [ENTRY, TIER, TIER, BAND, BAND, EXIT]


def test_s_change_vs_last_trade_not_vs_yesterday():
    # S son işlemde 1 idi; bugün 2 → hedefe; S son işlemle aynıysa bant kuralı
    d, r = _rb([0.02], [0.04], [2], [1])
    assert r[0] == TIER and d[0] == pytest.approx(0.02)
    d, r = _rb([0.035], [0.04], [2], [2])
    assert r[0] == NONE


def test_no_residual_after_exit_rule_sequence():
    """Hedef 0 olan coinde çıkış tam: Δ = −w (artık 0)."""
    rng = np.random.default_rng(0)
    w = rng.uniform(0, 0.1, 50)
    wt = np.where(rng.random(50) < 0.5, 0.0, rng.uniform(0, 0.1, 50))
    s_now = np.where(wt > 0, rng.integers(1, 4, 50), 0)
    d, r = _rb(w, wt, s_now, rng.integers(1, 4, 50), allow=bool(rng.integers(0, 2)))
    z = wt == 0
    np.testing.assert_array_equal(w[z] + d[z], 0.0)
