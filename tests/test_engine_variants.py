"""T0–T10 varyantlarının motorda çalıştığının duman testi (sentetik veri; sonuç değil yalnızca mekanik doğruluk)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trend.backtest.engine import resolve_settings, run_backtest
from trend.backtest.rules import delist_info_from_panel
from trend.backtest.synthetic import make_market
from trend.backtest.variants import T10_CORE_WEIGHTS, shifted_inputs, variant_runs
from trend.strategy.benchmarks import btc_200, core_satellite


@pytest.fixture(scope="module")
def mk():
    return make_market(n_assets=10, n_days=800, seed=41)


def test_all_variant_runs_execute(mk):
    navs = {}
    for v in variant_runs():
        cfg = resolve_settings(overrides=v.overrides)
        kw = dict(universe=mk.universe, delist=mk.delist, start="2019-11-01", overrides=v.overrides)
        p1d, p1h, fp = mk.panel_1d, mk.panel_1h, None
        if "close_hour" in v.params:
            p1d, fp = shifted_inputs(cfg, mk.panel_1h, v.params["close_hour"])
            kw["delist"] = delist_info_from_panel(p1d["close"], int(cfg["backtest"]["delist_stale_days"]))
        if "exchange_loss_frac" in v.params:
            kw["exchange_loss"] = [("2020-06-01", v.params["exchange_loss_frac"])]
        res = run_backtest(p1d, panel_1h=p1h, fill_px=fp, **kw)
        assert res.daily["cash"].min() >= 0 and np.isfinite(res.nav).all()
        navs[v.code] = res.nav
    t0 = navs["T0"]
    assert not navs["T6_cost2"].equals(t0) and navs["T6_cost2"].iloc[-1] < t0.iloc[-1]
    loss = navs["T6_loss20"]
    d = pd.Timestamp("2020-06-01")
    assert loss.loc[d] < loss.shift(1).loc[d] * 0.85
    assert not navs["T3"].equals(t0) and not navs["T4_0607"].equals(t0)


def test_t10_core_satellite_from_two_engine_runs(mk):
    t0 = run_backtest(mk.panel_1d, panel_1h=mk.panel_1h, universe=mk.universe, delist=mk.delist, start="2019-11-01")
    b = run_backtest(mk.panel_1d, panel_1h=mk.panel_1h, universe=mk.universe, delist=mk.delist, start="2019-11-01",
                     strategy=btc_200(mk.panel_1d["close"]), hard_stop=False)
    for wc in T10_CORE_WEIGHTS:
        mix = core_satellite(b.nav, t0.nav, wc)
        assert len(mix) == len(t0.nav) and mix.iloc[0] == pytest.approx(1.0)
        r = mix.pct_change().dropna()
        rc, rs = b.nav.pct_change().dropna(), t0.nav.pct_change().dropna()
        assert r.min() >= min(rc.min(), rs.min()) - 1e-12 and r.max() <= max(rc.max(), rs.max()) + 1e-12
