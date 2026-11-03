"""Araştırma v2 ortak karar verici (trend.alt.base): yürütme kuralları, nedensellik, oynaklık hedefi."""

import numpy as np
import pandas as pd
import pytest

from trend.alt.base import AltStrategy, rolling_vol, vol_target_weights
from trend.backtest.engine import run_backtest
from trend.backtest.lookahead import compare_until, corrupt_after
from trend.backtest.synthetic import make_market
from trend.config import load_settings


class _Hold(AltStrategy):
    """Sabit hedef: yalnızca verilen varlık, ağırlık w."""

    def __init__(self, asset, w=1.0, **kw):
        super().__init__(assets=(asset,), **kw)
        self.asset, self.wv = asset, w

    def compute(self, data):
        pass

    def target(self, j, v):
        out = np.zeros(len(self.data.assets))
        out[self.col[self.asset]] = self.wv
        return out


class _Losers(AltStrategy):
    """Evren üyeleri arasında son 3 günün en çok düşen 2'si, oynaklık hedefli; haftalık."""

    use_universe = True
    apply_cap = True

    def compute(self, data):
        C = self.C
        self.score = np.full_like(C, np.nan)
        self.score[3:] = np.log(C[3:] / C[:-3])
        self.vol = rolling_vol(C, 60, 30)

    def target(self, j, v):
        s = np.where(v.univ & np.isfinite(self.score[j]) & np.isfinite(self.vol[j]), self.score[j], np.inf)
        pick = np.argsort(s)[:2]
        sel = np.zeros(len(s), dtype=bool)
        sel[pick[np.isfinite(s[pick])]] = True
        return vol_target_weights(1.0 / self.vol[j], sel, self.R, j, 0.35, 60, 30, v.cap)


@pytest.fixture(scope="module")
def market():
    return make_market(n_assets=10, n_days=700, start="2019-01-01", seed=5, min_days=200)


def _run(mk, strat, **kw):
    kw.setdefault("panel_1d", mk.panel_1d)
    kw.setdefault("panel_1h", mk.panel_1h)
    kw.setdefault("universe", mk.universe)
    kw.setdefault("delist", mk.delist)
    return run_backtest(strategy=strat, start="2019-09-01", hard_stop=False, **kw)


def test_always_btc_tracks_btc(market):
    r = _run(market, _Hold("BTCUSDT", 1.0, every=30))
    d = r.daily
    assert d["gross_exposure"].iloc[5:].min() > 0.97
    btc = market.panel_1d["close"]["BTCUSDT"].reindex(d.index).pct_change()
    assert np.corrcoef(d["ret"].iloc[5:], btc.iloc[5:])[0, 1] > 0.999


def test_rebalance_schedule_and_band(market):
    r = _run(market, _Hold("BTCUSDT", 0.5, every=7, band=0.0))
    f = r.fills
    days = pd.to_datetime(f["decision_date"]).dt.normalize().unique()
    first = pd.Timestamp("2019-09-01")
    assert all(((d - first).days % 7) == 0 for d in days)
    r2 = _run(market, _Hold("BTCUSDT", 0.5, every=1, band=10.0))   # bant çok geniş → yalnız giriş
    assert len(r2.fills) == 1


def test_lookahead_corruption_leaves_decisions_unchanged(market):
    base = _run(market, _Losers(every=7), assets=market.assets)
    rng = np.random.default_rng(1)
    inp = dict(panel_1d=market.panel_1d, panel_1h=market.panel_1h, universe=market.universe, delist=market.delist)
    for t in ("2019-11-15", "2020-03-02", "2020-08-20"):
        bad = corrupt_after(t, rng, assets=market.assets, **inp)
        r = _run(market, _Losers(every=7), assets=market.assets, **{k: bad[k] for k in inp if k in bad})
        assert compare_until(base, r, t) == [], t
        assert compare_until(base, r, "2100-01-01") != []        # bozma gerçekten etkili
    assert len(base.fills) > 20
    assert base.daily["gross_exposure"].max() <= 1.0 + 1e-9


def test_positive_control_leak_changes_results(market):
    a = _run(market, _Losers(every=7))
    b = _run(market, _Losers(every=7, lag=-1))
    assert not np.allclose(a.daily["ret"].to_numpy(), b.daily["ret"].to_numpy())


def test_vol_target_scales_to_sigma():
    rng = np.random.default_rng(0)
    R = rng.standard_normal((200, 3)) * 0.04
    sel = np.array([True, True, False])
    w = vol_target_weights(np.array([1.0, 1.0, 1.0]), sel, R, 199, 0.20, 60, 30)
    sub = R[140:200][:, :2]
    port = sub @ w[:2]
    assert w[2] == 0 and np.isclose(port.std(ddof=1) * np.sqrt(365), 0.20, rtol=1e-6)


class _Flip(AltStrategy):
    """Hedef her gün BTC ile ETH arasında değişir."""

    def __init__(self, **kw):
        super().__init__(assets=("BTCUSDT", "ETHUSDT"), **kw)

    def compute(self, data):
        pass

    def target(self, j, v):
        out = np.zeros(len(self.data.assets))
        out[self.col["BTCUSDT" if j % 2 == 0 else "ETHUSDT"]] = 0.5
        return out


def test_hold_targets_keeps_basket_between_rebalances(market):
    a = _run(market, _Flip(every=7))
    assert len(a.fills) > 100                                  # her gün çıkış + yeniden denenen giriş
    class _Held(_Flip):
        hold_targets = True
    b = _run(market, _Held(every=7))
    days = pd.to_datetime(b.fills["decision_date"]).dt.normalize().unique()
    first = pd.Timestamp("2019-09-01")
    assert all(((d - first).days % 7) == 0 for d in days)     # yalnızca yeniden dengeleme günleri
