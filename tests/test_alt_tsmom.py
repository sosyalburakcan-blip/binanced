"""Araştırma v3 kısa vadeli trend adayları (trend.alt.tsmom): elle hesap, nedensellik, karar takvimi, kontroller."""

import numpy as np
import pandas as pd
import pytest

from trend.alt.tsmom import FAMILIES, TsMomBTC, XsMomentum
from trend.alt.xsec import XsReversal
from trend.backtest.engine import run_backtest
from trend.backtest.interface import EngineData
from trend.backtest.lookahead import compare_until, corrupt_after
from trend.backtest.synthetic import make_market

COMMON = {"vol_window": 60, "vol_min_obs": 30, "sigma_target": 0.35, "cov_window": 60, "cov_min_obs": 30,
          "drift_band": 0.25, "tier_caps": False}
START = "2019-09-01"


@pytest.fixture(scope="module")
def market():
    return make_market(n_assets=10, n_days=700, start="2019-01-01", seed=5, min_days=200)


def _run(mk, strat, **kw):
    kw.setdefault("panel_1d", mk.panel_1d)
    kw.setdefault("panel_1h", mk.panel_1h)
    kw.setdefault("universe", mk.universe)
    kw.setdefault("delist", mk.delist)
    return run_backtest(strategy=strat, start=START, hard_stop=False, **kw)


def _prep(strat, close):
    days = pd.DatetimeIndex(close.index)
    strat.prepare(EngineData(days=days, assets=list(close.columns), close=close, cfg={}, btc_idx=0))
    return strat


def test_ts_signal_hand_computed():
    c = pd.DataFrame({"BTCUSDT": [100.0, 101.0, 99.0, np.nan, 103.0, 102.0, 104.0]},
                     index=pd.date_range("2020-01-01", periods=7))
    s = _prep(TsMomBTC({"lookback": 2, "every": 1}), c)
    exp = [np.nan, np.nan, np.log(99 / 100), np.nan, np.log(103 / 99), np.nan, np.log(104 / 103)]
    np.testing.assert_allclose(s.sig, exp, equal_nan=True)
    tg = [s.target(j, None)[0] for j in range(7)]
    assert tg == [0, 0, 0, 0, 1.0, 0, 1.0]
    s1 = _prep(TsMomBTC({"lookback": 1, "every": 1}), c)
    assert [s1.target(j, None)[0] for j in range(7)] == [0, 1.0, 0, 0, 0, 0, 1.0]


def test_xs_mom_is_reverse_of_xs_rev():
    rng = np.random.default_rng(0)
    c = pd.DataFrame(np.exp(np.cumsum(rng.standard_normal((120, 4)) * 0.03, axis=0)) * 10,
                     columns=["BTCUSDT", "ETHUSDT", "C002USDT", "C003USDT"], index=pd.date_range("2020-01-01", periods=120))
    p = {"lookback": 7, "n_hold": 2, "every": 7}
    m, r = _prep(XsMomentum(p, COMMON), c), _prep(XsReversal(p, COMMON), c)
    np.testing.assert_allclose(m.score, -r.score, equal_nan=True)
    assert m.hold_targets and m.use_universe and not m.apply_cap


@pytest.mark.parametrize("fam,params", [("TS_D", {"lookback": 1, "every": 1}), ("TS_W", {"lookback": 7, "every": 7}),
                                        ("XS_MOM", {"lookback": 7, "n_hold": 5, "every": 7})])
def test_lookahead_corruption_leaves_decisions_unchanged(market, fam, params):
    mk = market
    base = _run(mk, FAMILIES[fam](params, COMMON), assets=mk.assets)
    rng = np.random.default_rng(3)
    inp = dict(panel_1d=mk.panel_1d, panel_1h=mk.panel_1h, universe=mk.universe, delist=mk.delist)
    for t in ("2019-11-15", "2020-03-02", "2020-08-20"):
        bad = corrupt_after(t, rng, assets=mk.assets, **inp)
        r = _run(mk, FAMILIES[fam](params, COMMON), assets=mk.assets, **{k: bad[k] for k in inp if k in bad})
        assert compare_until(base, r, t) == [], (fam, t)
        assert compare_until(base, r, "2100-01-01") != []
    assert len(base.fills) > 5
    assert base.daily["gross_exposure"].max() <= 1.0 + 1e-9


def test_weekly_rule_trades_only_on_decision_days(market):
    r = _run(market, TsMomBTC({"lookback": 7, "every": 7}))
    days = pd.to_datetime(r.fills["decision_date"]).dt.normalize().unique()
    assert len(days) > 5 and all(((d - pd.Timestamp(START)).days % 7) == 0 for d in days)
    d = _run(market, TsMomBTC({"lookback": 1, "every": 1}))
    assert len(d.fills) > 3 * len(r.fills)                    # günlük kural çok daha sık işlem yapar
    assert set(np.round(d.decisions.loc[d.decisions["delta"] != 0, "w_tgt"], 9)) <= {0.0, 1.0}


@pytest.mark.parametrize("fam,params,leak", [("TS_D", {"lookback": 1, "every": 1}, 1),
                                             ("TS_W", {"lookback": 7, "every": 7}, 7)])
def test_positive_control_one_period_leak_raises_sharpe(market, fam, params, leak):
    def sh(res):
        x = res.daily["ret"].iloc[30:]
        return x.mean() / x.std() * np.sqrt(365)
    a = _run(market, FAMILIES[fam](params, COMMON))
    b = _run(market, FAMILIES[fam](params, COMMON, lag=-leak))
    assert sh(b) > sh(a) + 1.0
