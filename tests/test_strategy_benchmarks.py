"""Kıyaslar: BTC-200, BTC/ETH-200, al-tut, %50 BTC, evren eşit ağırlık, eşit ağırlıklı trend; T10 karışımı."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trend.backtest.engine import run_backtest
from trend.backtest.synthetic import make_market
from trend.strategy.benchmarks import (
    btc_200, btc_eth_200, btc_hold, core_satellite, trend_equal_weight, universe_equal_weight,
)


@pytest.fixture(scope="module")
def mk():
    return make_market(n_assets=10, n_days=1000, seed=31, n_delist=2, n_gaps=2)


def _run(mk, strat, **kw):
    return run_backtest(mk.panel_1d, panel_1h=mk.panel_1h, universe=mk.universe, delist=mk.delist, strategy=strat,
                        start="2019-09-01", hard_stop=False, **kw)


def test_btc_200_target_definition(mk):
    c = mk.panel_1d["close"]["BTCUSDT"]
    w = btc_200(mk.panel_1d["close"]).weights["BTCUSDT"]
    sma = c.rolling(200).mean()
    exp = (c > sma).astype(float)
    exp[sma.isna()] = 0.0
    np.testing.assert_array_equal(w.to_numpy(), exp.to_numpy())


def test_btc_200_engine_run_is_all_in_or_cash(mk):
    strat = btc_200(mk.panel_1d["close"])
    res = _run(mk, strat)
    assert set(res.fills["asset"]) == {"BTCUSDT"}
    sig = strat.weights["BTCUSDT"].reindex(res.daily.index)
    held = res.weights["BTCUSDT"]
    on = sig.shift(1).fillna(0) == 1  # karar t → dolum t+1
    both = on & (sig.shift(2).fillna(0) == 1)
    assert (held[both] > 0.98).all() and held[both].mean() > 0.995
    off = (sig.shift(1).fillna(1) == 0) & (sig.shift(2).fillna(1) == 0)
    assert (held[off] == 0).all()
    assert res.daily["cash"].min() >= 0


def test_btc_eth_and_static_mixes(mk):
    r = _run(mk, btc_eth_200(mk.panel_1d["close"]))
    assert set(r.fills["asset"]) <= {"BTCUSDT", "ETHUSDT"} and r.weights.max().max() < 0.8
    h = _run(mk, btc_hold(mk.panel_1d["close"]))
    assert (h.fills["side"] == "buy").all() and h.weights["BTCUSDT"].iloc[1:].min() > 0.98
    half = _run(mk, btc_hold(mk.panel_1d["close"], weight=0.5))
    me = half.daily.index[(half.daily.index + pd.Timedelta(days=1)).day == 1]
    after = [d + pd.Timedelta(days=1) for d in me if d + pd.Timedelta(days=1) in half.weights.index]
    wa = half.weights.loc[after, "BTCUSDT"]  # ay başı dolumundan sonraki kapanış (gün içi fiyat hareketi dahil)
    assert (wa - 0.5).abs().max() < 0.05 and abs(wa.mean() - 0.5) < 0.01


def test_universe_equal_weight_monthly(mk):
    strat = universe_equal_weight(mk.panel_1d["close"], mk.universe)
    res = _run(mk, strat)
    f = res.fills[res.fills.kind != "delist"]
    dd = pd.to_datetime(f["decision_date"])
    assert ((dd + pd.Timedelta(days=1)).dt.day.eq(1) | (dd == res.daily.index[0])).all()  # yalnız ay sonu kararları
    t = pd.Timestamp("2020-03-01")
    n = len(mk.universe(t - pd.Timedelta(days=1)))
    w = res.weights.loc[t]
    assert (w[w > 0] - 1 / n).abs().max() < 0.01


def test_trend_equal_weight_uses_same_rules(mk):
    res = _run(mk, trend_equal_weight())
    pos = res.decisions[(res.decisions.w_tgt > 0) & (res.decisions.reason != "frozen")]
    assert len(pos) > 0 and (pos["s3"] > 0).all()
    buys = res.fills.query("side == 'buy'")
    assert (pd.to_datetime(buys["date"]).dt.day_of_week == 0).all()  # haftalık giriş kuralı aynen
    assert (res.decisions.groupby("date")["w_tgt"].sum() <= 1 + 1e-9).all()


def test_core_satellite_monthly_rebalance_math():
    idx = pd.date_range("2024-01-30", periods=4, freq="D")  # 30, 31 Oca, 1, 2 Şub
    core = pd.Series([1.0, 1.10, 1.21, 1.21], index=idx)
    sat = pd.Series([1.0, 0.90, 0.90, 0.99], index=idx)
    mix = core_satellite(core, sat, 0.8)
    v31 = 0.8 * 1.10 + 0.2 * 0.90  # 31 Oca kapanışı (ay sonu) → yeniden dengele
    v1 = v31 * (0.8 * 1.10 + 0.2 * 1.0)
    v2 = v31 * (0.8 * 1.10 + 0.2 * 1.10)
    np.testing.assert_allclose(mix.to_numpy(), [1.0, v31, v1, v2], rtol=1e-12)
