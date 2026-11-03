"""G8: delist ve boşluk kuralları, emir sırası ve orantılı küçültme, küsürat, minimum emir, sert sınır, nakit getirisi,
borsa kaybı (T6), maliyet çarpanı, sabit tutarlı büyüklük, haftalık giriş, evrenden çıkan coinler."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trend.backtest.engine import run_backtest
from trend.backtest.interface import Decision
from trend.backtest.providers import MonthlyUniverse
from trend.backtest.rules import HardStop, delist_info_from_panel
from trend.backtest.synthetic import StaticUniverse, make_market, tiny_inputs
from trend.strategy.benchmarks import TargetWeightStrategy
from trend.strategy.rebalance import ENTRY

NAT = pd.NaT
FLAT = [100.0] * 10


def _tw(close, fill, targets, uni=None, panel_extra=None, **kw):
    panel, fp = tiny_inputs(close, fill)
    if panel_extra:
        panel.update(panel_extra)
    tw = pd.DataFrame(targets, index=panel["close"].index)
    uni = uni or StaticUniverse([(a, "B", 1.0, 0.001) for a in close])
    kw.setdefault("hard_stop", False)
    return run_backtest(panel, fill_px=fp, universe=uni, strategy=TargetWeightStrategy(tw), **kw), panel


def _days(n=10):
    return pd.date_range("2024-01-01", periods=n, freq="D")


# ------------------------------------------------------------------ delist
def test_delist_without_announcement_exits_at_last_day_vwap_with_penalty():
    d = _days()
    cB = [50.0] * 6 + [np.nan] * 4
    fB = [np.nan, 50, 50, 50, 50, 48] + [np.nan] * 4
    dl = pd.DataFrame({"asset": ["BBBUSDT"], "last_day": [d[5]], "announced_day": [NAT]})
    res, _ = _tw({"AAAUSDT": FLAT, "BBBUSDT": cB}, {"AAAUSDT": FLAT, "BBBUSDT": fB},
                 {"AAAUSDT": 0.0, "BBBUSDT": 0.5}, delist=dl)
    f = res.fills
    assert f["kind"].tolist() == ["entry", "delist"]
    x = f.iloc[1]
    assert x.date == d[5] and x.price == pytest.approx(48 * 0.95) and x.penalty_cost == pytest.approx(100 * 48 * .05)
    assert x.qty_after == 0 and x.commission == pytest.approx(100 * 48 * 0.95 * 0.001)
    cash = 10000 - 100 * 50 * 1.001 * 1.001 + 100 * 48 * 0.95 * 0.999
    np.testing.assert_allclose(res.nav.iloc[5:].to_numpy(), cash, rtol=1e-12)
    # son günün değil önceki kapanışın (50) fiyatından satılmadı; sonra yeniden alım yok
    assert (res.decisions.query("asset == 'BBBUSDT' and date > @d[5]")["delta"] == 0).all()


def test_delist_fallback_to_daily_vwap_when_window_has_no_trades():
    d = _days()
    cB = [50.0] * 6 + [np.nan] * 4
    fB = [np.nan, 50, 50, 50, 50, np.nan] + [np.nan] * 4
    qv = pd.DataFrame({"AAAUSDT": 1e6, "BBBUSDT": [5e3] * 5 + [4700.0] + [np.nan] * 4}, index=d)
    vol = pd.DataFrame({"AAAUSDT": 1e4, "BBBUSDT": [100.0] * 6 + [np.nan] * 4}, index=d)
    dl = pd.DataFrame({"asset": ["BBBUSDT"], "last_day": [d[5]], "announced_day": [NAT]})
    res, _ = _tw({"AAAUSDT": FLAT, "BBBUSDT": cB}, {"AAAUSDT": FLAT, "BBBUSDT": fB},
                 {"AAAUSDT": 0.0, "BBBUSDT": 0.5}, delist=dl, panel_extra={"quote_volume": qv, "volume": vol})
    assert res.fills.iloc[1].price == pytest.approx(47 * 0.95)


def test_delist_with_announcement_sells_next_day_at_normal_cost_and_never_reenters():
    d = _days()
    cB = [50.0] * 6 + [np.nan] * 4
    fB = [np.nan, 50, 50, 50, 50, 48] + [np.nan] * 4
    dl = pd.DataFrame({"asset": ["BBBUSDT"], "last_day": [d[5]], "announced_day": [d[2]]})
    res, _ = _tw({"AAAUSDT": FLAT, "BBBUSDT": cB}, {"AAAUSDT": FLAT, "BBBUSDT": fB},
                 {"AAAUSDT": 0.0, "BBBUSDT": 0.5}, delist=dl)
    f = res.fills
    assert f["kind"].tolist() == ["entry", "exit"]
    x = f.iloc[1]
    assert x.date == d[3] and x.price == pytest.approx(50 * 0.999) and x.penalty_cost == 0


def test_announced_asset_can_reenter_after_series_resumes_from_long_gap():
    # FTTUSDT tipi: duyuru → satış; seri delist_stale_days'ten uzun boşluktan dönünce yeniden alınabilir
    n = 30
    d = pd.date_range("2024-01-01", periods=n, freq="D")
    cB = [50.0] * 5 + [np.nan] * 12 + [60.0] * 13
    dl = pd.DataFrame({"asset": ["BBBUSDT"], "last_day": [NAT], "announced_day": [d[2]]})
    res, _ = _tw({"AAAUSDT": [100.0] * n, "BBBUSDT": cB}, {"AAAUSDT": [100.0] * n, "BBBUSDT": cB},
                 {"AAAUSDT": 0.0, "BBBUSDT": 0.5}, delist=dl)
    f = res.fills
    assert f["kind"].tolist() == ["entry", "exit", "entry"]
    assert f.iloc[1].date == d[3] and f.iloc[2].date == d[18]  # dönüş günü (d[17]) kararı, d[18] dolumu


def test_delist_info_from_panel_uses_last_candle_and_stale_rule():
    idx = _days(30)
    c = pd.DataFrame({"A": 1.0, "B": [1.0] * 10 + [np.nan] * 20, "C": [1.0] * 25 + [np.nan] * 5}, index=idx)
    ann = pd.DataFrame({"symbol": ["B", "C"], "announced_utc": ["2024-01-05 14:00", "2024-01-20 00:00"],
                        "delist_utc": ["2024-01-11", "2024-01-26"], "kind": ["delist", "monitoring_tag"],
                        "source": ["x", "y"]})
    info = delist_info_from_panel(c, 7, ann).set_index("asset")
    assert list(info.index) == ["B"]  # C'nin son mumu 5 gün önce (≤ 7) → delist değil; monitoring tag satmaz
    assert info.loc["B", "last_day"] == idx[9] and info.loc["B", "announced_day"] == pd.Timestamp("2024-01-05")


# ------------------------------------------------------------------ boşluk
def test_gap_carries_last_price_freezes_and_resumes():
    d = _days()
    cB = [50.0, 50, 52, np.nan, np.nan, np.nan, 55, 56, 57, 58]
    fB = [np.nan, 50, 51, np.nan, np.nan, np.nan, 54, 55.5, 56, 57]
    tB = [0.5] * 4 + [0.2] * 6  # hedef boşluk sırasında değişir
    res, _ = _tw({"BBBUSDT": cB}, {"BBBUSDT": fB}, {"BBBUSDT": tB})
    f = res.fills
    assert f["date"].tolist() == [d[1], d[7]]  # boşlukta işlem yok; değişiklik seri dönünce uygulanır
    cash = 10000 - 100 * 50 * 1.001 * 1.001
    np.testing.assert_allclose(res.nav.iloc[3:6].to_numpy(), cash + 100 * 52, rtol=1e-12)  # son fiyat taşınır
    assert f.iloc[1].side == "sell"


def test_rename_style_gap_holds_position_through_gap():
    mk = make_market(n_assets=10, n_days=900, seed=23, n_gaps=4, n_delist=0)
    res = run_backtest(mk.panel_1d, panel_1h=mk.panel_1h, universe=mk.universe, delist=mk.delist, start="2020-01-01")
    days = mk.panel_1d["close"].index
    n_held_gaps = 0
    for a, (g0, gl) in mk.gaps.items():
        gap_days = days[g0:g0 + gl]
        assert not res.fills["date"].isin(gap_days).any() or not (res.fills.loc[res.fills["date"].isin(gap_days),
                                                                                   "asset"] == a).any()
        if a in res.weights.columns and days[g0 - 1] >= res.daily.index[0]:
            q = res.decisions.query("asset == @a and date in @gap_days")
            assert (q["delta"] == 0).all()
            held = q[q["w"] > 0]
            assert (held["reason"] == "frozen").all()
            n_held_gaps += len(held) > 0
            # pozisyon değeri sabit fiyattan taşınır → ağırlık·NAV sabit
            mv = (res.weights[a] * res.nav).loc[gap_days]
            if (mv > 0).any():
                assert np.allclose(mv, mv.iloc[0], rtol=1e-12)
    assert n_held_gaps >= 2  # test boş geçmesin: boşluk boyunca tutulan pozisyonlar var


# ------------------------------------------------------------------ emir sırası, küsürat, minimum emir
def test_sells_first_then_buys_scaled_pro_rata():
    c = {"AAAUSDT": FLAT, "BBBUSDT": FLAT, "CCCUSDT": FLAT}
    f = {"AAAUSDT": [np.nan] + [100.0] * 9, "BBBUSDT": [np.nan] + [100] * 2 + [106] * 7,
         "CCCUSDT": [np.nan] + [100] * 2 + [104] * 7}
    t = {"AAAUSDT": [0.9] * 2 + [0.0] * 8, "BBBUSDT": [0.0] * 2 + [0.5] * 8, "CCCUSDT": [0.0] * 2 + [0.5] * 8}
    res, _ = _tw(c, f, t)
    fl = res.fills.set_index(["date", "asset"])
    d = _days()
    assert res.fills[res.fills.date == d[3]]["side"].tolist() == ["sell", "buy", "buy"]
    ordered = res.decisions.query("date == @d[2]").set_index("asset")["qty"]
    fb = fl.loc[(d[3], "BBBUSDT"), "qty"] / ordered["BBBUSDT"]
    fc = fl.loc[(d[3], "CCCUSDT"), "qty"] / ordered["CCCUSDT"]
    assert fb < 1 and fb == pytest.approx(fc, rel=1e-12)
    assert res.daily["cash"].min() >= 0 and res.daily["cash"].iloc[3] == pytest.approx(0.0, abs=1e-9)


def test_dust_below_min_order_is_written_off():
    cA = [100.0] * 4 + [40.0] * 6
    fA = [np.nan] + [100.0] * 3 + [40.0] * 6
    res, _ = _tw({"AAAUSDT": cA}, {"AAAUSDT": fA}, {"AAAUSDT": [0.012] * 5 + [0.0] * 5}, initial_capital=1000)
    f = res.fills
    assert f["kind"].tolist() == ["entry", "dust"]
    x = f.iloc[1]
    assert x.cash_flow == 0 and x.qty_after == 0 and x.price == 0
    cash = res.daily["cash"]
    assert cash.iloc[6] == cash.iloc[5] and res.nav.iloc[6] == pytest.approx(res.nav.iloc[5] - 0.12 * 40)


class _ConstDecider:
    """Her gün sabit Δw isteyen test karar vericisi (motor filtrelerini sınamak için)."""

    def __init__(self, first_delta: dict, daily_delta: dict):
        self.first, self.daily = first_delta, daily_delta

    def required_assets(self):
        return list(set(self.first) | set(self.daily))

    def prepare(self, data):
        self.assets = data.assets

    def observe(self, i):
        pass

    def decide(self, v):
        n = len(self.assets)
        d = np.zeros(n)
        src = self.first if v.first else self.daily
        for a, x in src.items():
            d[self.assets.index(a)] = x
        return Decision(delta=d, w_tgt=np.maximum(v.w + d, 0), s3=np.full(n, -1),
                        reason=np.where(d != 0, ENTRY, 0).astype(np.int8))


def test_non_exit_order_below_min_notional_is_skipped():
    panel, fp = tiny_inputs({"AAAUSDT": FLAT}, {"AAAUSDT": FLAT})
    res = run_backtest(panel, fill_px=fp, universe=StaticUniverse([("AAAUSDT", "B", 1.0, 0.001)]),
                       strategy=_ConstDecider({"AAAUSDT": 0.0009}, {"AAAUSDT": 0.0011}), hard_stop=False)
    r = res.decisions.set_index("date")["reason"]
    assert r.iloc[0] == "skip_minorder" and (r.iloc[1:] == "entry").all()
    assert res.fills["date"].min() == _days()[2]


def test_hard_stop_blocks_buys_until_recovery():
    cA = [100, 100, 100, 40, 40, 40, 70, 95, 100, 100.0]
    c = {"AAAUSDT": cA, "BBBUSDT": FLAT}
    fills = {"AAAUSDT": [np.nan] + cA[:-1], "BBBUSDT": FLAT}
    panel, fp = tiny_inputs(c, fills)
    res = run_backtest(panel, fill_px=fp, universe=StaticUniverse([("AAAUSDT", "B", 1.0, 0.0),
                                                                    ("BBBUSDT", "B", 1.0, 0.0)]),
                       strategy=_ConstDecider({"AAAUSDT": 0.8}, {"BBBUSDT": 0.01}),
                       overrides={"backtest": {"commission": 0.0}}, hard_stop=True)
    dd = res.daily["drawdown"]
    stop = res.daily["hard_stop"].astype(bool)
    assert stop.any() and dd[stop].max() <= -0.25 and dd[stop.idxmax()] <= -0.35
    b = res.decisions[res.decisions.asset == "BBBUSDT"].set_index("date")["reason"]
    assert (b.loc[stop[stop].index] == "skip_hardstop").all()
    free = stop.index[1:][~stop.iloc[1:].to_numpy()]
    assert len(free) > 0 and (b.loc[free] == "entry").all()
    resumed = stop.index[(~stop) & stop.shift(1, fill_value=False)]
    assert len(resumed) == 1 and dd[resumed[0]] >= -0.25


def test_hard_stop_state_machine():
    hs = HardStop(-0.35, -0.25)
    out = [hs.update(x) for x in [100, 90, 64, 70, 74, 76, 60]]
    assert out == [False, False, True, True, True, False, True]


# ------------------------------------------------------------------ nakit getirisi, T6
def test_cash_yield_modes():
    d = _days()
    rate = pd.Series(0.0365, index=d)
    res, _ = _tw({"AAAUSDT": FLAT}, {"AAAUSDT": FLAT}, {"AAAUSDT": 0.0}, cash_rate=rate,
                 overrides={"backtest": {"cash_yield": "tbill"}})
    np.testing.assert_allclose(res.nav.to_numpy(), 10000 * (1 + 0.0001) ** np.arange(10), rtol=1e-12)
    res2, _ = _tw({"AAAUSDT": FLAT}, {"AAAUSDT": FLAT}, {"AAAUSDT": 0.0}, cash_rate=rate * 0 + 0.01,
                  overrides={"backtest": {"cash_yield": "tbill_minus_1_5"}})
    assert (res2.nav == 10000).all()  # max(0, %1 − 1,5 puan) = 0
    res3, _ = _tw({"AAAUSDT": FLAT}, {"AAAUSDT": FLAT}, {"AAAUSDT": 0.0}, cash_rate=rate * 0 + 0.05,
                  overrides={"backtest": {"cash_yield": "tbill_minus_1_5"}})
    assert res3.nav.iloc[1] == pytest.approx(10000 * (1 + 0.035 / 365))
    res4, _ = _tw({"AAAUSDT": FLAT}, {"AAAUSDT": FLAT}, {"AAAUSDT": 0.0}, cash_rate=rate)
    assert (res4.nav == 10000).all()  # temel varsayım: %0


def test_exchange_loss_one_off():
    d = _days()
    res, _ = _tw({"AAAUSDT": FLAT}, {"AAAUSDT": FLAT}, {"AAAUSDT": 0.5}, exchange_loss=[(d[5], 0.2)],
                 overrides={"backtest": {"commission": 0.0}}, uni=StaticUniverse([("AAAUSDT", "B", 1.0, 0.0)]))
    assert res.nav.iloc[4] == pytest.approx(10000) and res.nav.iloc[5] == pytest.approx(8000)
    assert res.daily["exchange_loss"].iloc[5] == 0.2


def test_cost_multiplier_doubles_commission_and_slippage():
    c = {"AAAUSDT": FLAT}
    a, _ = _tw(c, c, {"AAAUSDT": 0.5})
    b, _ = _tw(c, c, {"AAAUSDT": 0.5}, overrides={"backtest": {"cost_multiplier": 2.0}})
    fa, fb = a.fills.iloc[0], b.fills.iloc[0]
    assert fb.price == pytest.approx(100 * 1.002) and fa.price == pytest.approx(100 * 1.001)
    assert fb.commission == pytest.approx(fb.notional * 0.002)


def test_fixed_amount_sizing_uses_initial_capital():
    cA = [100, 100, 200, 200, 200, 200, 200, 200, 200, 200.0]
    c = {"AAAUSDT": cA, "BBBUSDT": [50.0] * 10}
    f = {"AAAUSDT": [np.nan] + cA[:-1], "BBBUSDT": [50.0] * 10}
    t = {"AAAUSDT": 0.4, "BBBUSDT": [0.0] * 4 + [0.3] * 6}
    uni = StaticUniverse([("AAAUSDT", "B", 1.0, 0.0), ("BBBUSDT", "B", 1.0, 0.0)])
    ov = {"backtest": {"commission": 0.0}}
    fx, _ = _tw(c, f, t, uni=uni, overrides=ov, sizing="fixed")
    cp, _ = _tw(c, f, t, uni=uni, overrides=ov, sizing="compound")
    qf = fx.fills.query("asset == 'BBBUSDT'")["qty"].iloc[0]
    qc = cp.fills.query("asset == 'BBBUSDT'")["qty"].iloc[0]
    assert qf == pytest.approx(0.3 * 10000 / 50) and qc == pytest.approx(0.3 * cp.nav.iloc[4] / 50)


def test_open_fill_variant_t3():
    mk = make_market(n_assets=6, n_days=700, seed=5)
    res = run_backtest(mk.panel_1d, universe=mk.universe, delist=mk.delist, start="2020-01-01",
                       overrides={"backtest": {"fill": "open_t1"}})
    f = res.fills[res.fills.kind != "delist"]
    o = mk.panel_1d["open"]
    ref = np.array([o.loc[d, a] for d, a in zip(f["date"], f["asset"])])
    np.testing.assert_allclose(f["vwap"].to_numpy(), ref)


# ------------------------------------------------------------------ strateji motorda: haftalık giriş, çıkış, evren
@pytest.fixture(scope="module")
def mk():
    return make_market(n_assets=14, n_days=1100, seed=17, n_delist=3, n_gaps=3)


@pytest.fixture(scope="module")
def t0(mk):
    return run_backtest(mk.panel_1d, panel_1h=mk.panel_1h, universe=mk.universe, delist=mk.delist,
                        start="2020-01-01")


def test_weekly_entry_daily_exit_in_engine(mk, t0):
    f = t0.fills
    buys = f[f.side == "buy"]
    assert len(buys) > 20 and (pd.to_datetime(buys["date"]).dt.day_of_week == 0).all()  # pazar kararı → pazartesi
    sells = f[f.side == "sell"]
    assert (pd.to_datetime(sells["date"]).dt.day_of_week != 0).any()
    daily = run_backtest(mk.panel_1d, panel_1h=mk.panel_1h, universe=mk.universe, delist=mk.delist,
                         start="2020-01-01", overrides={"strategy": {"weekly_entry": {"enabled": False}}})
    assert (pd.to_datetime(daily.fills.query("side == 'buy'")["date"]).dt.day_of_week != 0).any()


def test_full_exit_leaves_no_residual(mk, t0):
    f = t0.fills
    assert (f.loc[f.kind.isin(["exit", "delist", "dust"]), "qty_after"] == 0).all()
    ex = t0.decisions[t0.decisions.reason == "exit"]
    fp_days = set(zip(f["date"], f["asset"]))
    for d, a in zip(ex["date"], ex["asset"]):
        nd = d + pd.Timedelta(days=1)
        if nd <= t0.daily.index[-1] and np.isfinite(mk.panel_1h["volume"].loc[nd:nd + pd.Timedelta(hours=23), a]).any():
            assert (nd, a) in fp_days
    # hedefi 0 olan ve dolum yapılabilen coinde ertesi kapanışta pozisyon kalmaz
    w = t0.weights
    zero_t = t0.decisions[(t0.decisions.w_tgt == 0) & (t0.decisions.reason != "frozen")]
    for d, a in list(zip(zero_t["date"], zero_t["asset"]))[:500]:
        nd = d + pd.Timedelta(days=1)
        if nd in w.index and (nd, a) in fp_days:
            assert w.loc[nd, a] == 0


def test_targets_respect_caps_vol_and_gross(mk, t0):
    dec = t0.decisions
    tot = dec.groupby("date")["w_tgt"].sum()
    assert tot.max() <= 1.0 + 1e-9
    assert dec["w_tgt"].max() <= 0.10 + 1e-12
    assert t0.daily["cash"].min() >= 0
    # S kademesi: hedef > 0 ⇔ etkin S3 > 0 (evrendeki coinler için)
    pos = dec[(dec.w_tgt > 0) & (dec.reason != "frozen")]
    assert (pos["s3"] > 0).all()


def test_coin_leaving_universe_can_only_shrink(mk, t0):
    held = t0.fills.query("side == 'buy'")["asset"].value_counts()
    victim = [a for a in held.index if a not in ("BTCUSDT", "ETHUSDT")][0]
    cut = "2020-09"
    tables = {k: (v[v.symbol != victim] if k >= cut else v) for k, v in mk.universe.tables.items()}
    res = run_backtest(mk.panel_1d, panel_1h=mk.panel_1h, universe=MonthlyUniverse(tables), delist=mk.delist,
                       start="2020-01-01")
    after = pd.Timestamp(cut + "-01") - pd.Timedelta(days=1)
    f = res.fills.query("asset == @victim and decision_date >= @after")
    assert (f["side"] == "sell").all()
    d = res.decisions.query("asset == @victim and date >= @after")
    assert (d["w_tgt"] <= d["w"] + 1e-15).all()


# ------------------------------------------------------------------ evren sağlayıcısı
def test_universe_timing_and_tier_fallback(tmp_path):
    from trend.backtest.providers import universe_arrays
    from trend.config import load_settings

    jan = pd.DataFrame({"symbol": ["BTCUSDT", "XUSDT"], "rank": [1, 2], "median_liquidity": [1e9, 3e7],
                        "tier": ["A", "B"], "cap": [0.10, 0.05], "slippage": [0.0005, 0.001]})
    feb = jan.iloc[:1]
    jan.to_csv(tmp_path / "2024-01.csv", index=False)
    feb.to_csv(tmp_path / "2024-02.csv", index=False)
    u = MonthlyUniverse.from_dir(tmp_path)
    # CONTRACTS §1: t kararı ay(t+1) evrenini kullanır → 31 Ocak kararı Şubat evreni
    assert len(u(pd.Timestamp("2024-01-30"))) == 2 and len(u(pd.Timestamp("2024-01-31"))) == 1
    assert len(u(pd.Timestamp("2024-03-31"))) == 0  # eksik ay → boş evren
    cfg = load_settings()
    m, cap, slip = universe_arrays(jan.drop(columns=["cap", "slippage"]), {"BTCUSDT": 0, "XUSDT": 1, "Y": 2}, 3, cfg)
    assert m.tolist() == [True, True, False]
    assert cap[:2].tolist() == [0.10, 0.05] and slip[:2].tolist() == [0.0005, 0.0010]
