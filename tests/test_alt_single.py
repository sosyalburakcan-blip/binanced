"""Araştırma v2 tek/çift varlık adayları (trend.alt.single): el hesabı, nedensellik, yürütme ve gecikme kontrolleri."""

import math

import numpy as np
import pandas as pd
import pytest

from trend.alt.single import FAMILIES, MeanRevBTC, RatioRotationETHBTC, VolManagedBTC
from trend.backtest.engine import run_backtest
from trend.backtest.interface import EngineData
from trend.backtest.lookahead import compare_until, corrupt_after
from trend.backtest.synthetic import make_market
from trend.config import load_settings

CFG = load_settings()
BTC, ETH = CFG["universe"]["btc_asset"], CFG["universe"]["eth_asset"]
BASE = {"VM_BTC": {"sigma_target": 0.50, "window": 30, "band": 0.20},
        "MR_BTC": {"window": 20, "entry_z": 2.0},
        "RV_ETHBTC": {"window": 90, "z_band": 1.0, "band": 0.25}}
SIGNALS = {"VM_BTC": ("sig",), "MR_BTC": ("z", "state"), "RV_ETHBTC": ("x", "z")}   # compute() dizileri
NaN = np.nan


def _make(fam, lag=0, **over):
    return FAMILIES[fam]({**BASE[fam], **over}, {}, lag)


def _prep(strat, close: dict):
    """Elle verilmiş kapanışlarla (gün × varlık) yalnızca prepare/compute."""
    df = pd.DataFrame(close, dtype=float)
    df.index = pd.date_range("2024-01-01", periods=len(df), freq="D").as_unit("ns")
    cols = list(df.columns)
    strat.prepare(EngineData(days=df.index, assets=cols, close=df, cfg=CFG, btc_idx=cols.index(BTC)))
    return strat


def _tgt(strat, asset):
    return np.array([strat.target(j, None)[strat.col[asset]] for j in range(strat.n_days)])


@pytest.fixture(scope="module")
def market():
    return make_market(n_assets=6, n_days=800, start="2019-01-01", seed=5, min_days=200)


def _run(mk, strat, start="2019-09-01", **kw):
    kw.setdefault("panel_1d", mk.panel_1d)
    kw.setdefault("panel_1h", mk.panel_1h)
    kw.setdefault("universe", mk.universe)
    kw.setdefault("delist", mk.delist)
    return run_backtest(strategy=strat, start=start, hard_stop=False, **kw)


# --- sözleşme ---

def test_constructor_contract():
    for fam, cls in FAMILIES.items():
        s = cls(dict(BASE[fam]), {"sigma_target": 0.35}, 3)
        assert s.every == 1 and s.lag == 3 and not s.use_universe and not s.apply_cap
    assert _make("VM_BTC").band == 0.20 and _make("VM_BTC").required_assets() == [BTC]
    assert _make("MR_BTC").band >= 1e9 and _make("MR_BTC").required_assets() == [BTC]
    assert _make("RV_ETHBTC").band == 0.25 and _make("RV_ETHBTC").required_assets() == [BTC, ETH]
    assert (FAMILIES["VM_BTC"], FAMILIES["MR_BTC"], FAMILIES["RV_ETHBTC"]) == (
        VolManagedBTC, MeanRevBTC, RatioRotationETHBTC)


# --- el hesabı ---

def test_vm_weights_by_hand():
    a = 0.05
    C = 100.0 * np.exp(np.concatenate([[0.0], np.cumsum([a, -a] * 8)]))   # 17 kapanış, log getiri ±a
    # W=6, min_obs=5: i=5'te 5 getiri (ort a/5), i≥6'da 6 getiri (ort 0); ikisinde de std = a·√1.2
    sig = a * math.sqrt(1.2) * math.sqrt(365)
    s = _prep(_make("VM_BTC", window=6, sigma_target=0.5), {BTC: C})
    np.testing.assert_allclose(s.sig[5:], sig, rtol=1e-9)
    assert np.isnan(s.sig[:5]).all()
    np.testing.assert_allclose(_tgt(s, BTC), [0.0] * 5 + [0.5 / sig] * 12, rtol=1e-9)
    assert 0.47 < 0.5 / sig < 0.48
    s = _prep(_make("VM_BTC", window=6, sigma_target=5.0), {BTC: C})       # S/σ > 1 → tavan 1
    np.testing.assert_array_equal(_tgt(s, BTC), [0.0] * 5 + [1.0] * 12)
    # boşluk: C[10] yok → r[10], r[11] NaN; i=11..15 pencerede 4 getiri < 5 → 0
    C2 = C.copy()
    C2[10] = NaN
    s = _prep(_make("VM_BTC", window=6, sigma_target=0.5), {BTC: C2})
    w = 0.5 / sig
    np.testing.assert_allclose(_tgt(s, BTC), [0.0] * 5 + [w] * 6 + [0.0] * 5 + [w], rtol=1e-9)
    # sabit fiyat: σ = 0 → 0
    s = _prep(_make("VM_BTC", window=6), {BTC: np.full(12, 7.0)})
    assert (_tgt(s, BTC) == 0).all()


def test_mr_z_and_state_by_hand():
    r3 = math.sqrt(3) / 2
    # giriş (z=−1.5), z ≥ 0 ile çıkış, dışarıdayken NaN, yeniden giriş
    s = _prep(_make("MR_BTC", window=4, entry_z=1.0), {BTC: [2, 2, 2, 1, 1, 2, 2, NaN, 2, 2, 2, 1]})
    np.testing.assert_allclose(s.z, [NaN, NaN, NaN, -1.5, -r3, r3, r3, NaN, NaN, NaN, NaN, -1.5], rtol=1e-12)
    np.testing.assert_array_equal(s.state, [0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 1])
    np.testing.assert_array_equal(_tgt(s, BTC), s.state)
    # giriş eşiği kesin: z = −1.5 < −1.5 değil
    s = _prep(_make("MR_BTC", window=4, entry_z=1.5), {BTC: [2, 2, 2, 1, 1, 2, 2, NaN, 2, 2, 2, 1]})
    assert (s.state == 0).all()
    # doğrusal düşüş: z = −1.5/√(5/3) her gün; W=4 gün sonra süre çıkışı, ertesi gün yeniden giriş; z = 0 → çıkış
    zl = -1.5 / math.sqrt(5 / 3)
    s = _prep(_make("MR_BTC", window=4, entry_z=1.0), {BTC: [10, 9, 8, 7, 6, 5, 4, 3, 2, 3]})
    np.testing.assert_allclose(s.z[3:], [zl] * 6 + [0.0], rtol=1e-12, atol=1e-15)
    np.testing.assert_array_equal(s.state, [0, 0, 0, 1, 1, 1, 1, 0, 1, 0])
    # içerideyken NaN: durum korunur, gün sayılır → girişten 4 gün sonra (z hâlâ NaN) çıkış
    s = _prep(_make("MR_BTC", window=4, entry_z=1.0), {BTC: [2, 2, 2, 1, NaN, 1, 2, 1, 3]})
    assert np.isnan(s.z[4:8]).all() and s.z[8] > 0
    np.testing.assert_array_equal(s.state, [0, 0, 0, 1, 1, 1, 1, 0, 0])


def test_rv_z_and_state_by_hand():
    x = np.array([0, 1, 3, -3, NaN, 0, 0, NaN, 2, -1, -5], dtype=float)
    cb = np.full(11, 100.0)
    cb[[6, 7]] = NaN                                     # 6: yalnız ETH, 7: ikisi de yok
    ce = 100.0 * np.exp(x)
    ce[[4, 7]] = NaN                                     # 4: yalnız BTC
    s = _prep(_make("RV_ETHBTC", window=4, z_band=1.0), {BTC: cb, ETH: ce})
    np.testing.assert_allclose(s.x, [0, 1, 3, -3, NaN, 0, NaN, NaN, 2, -1, -5], atol=1e-12)
    r2 = 1 / math.sqrt(2)
    want = [NaN, r2, (5 / 3) / math.sqrt(7 / 3), -1.3, NaN, 0.0, NaN, NaN, r2, -r2, -11 / math.sqrt(111)]
    np.testing.assert_allclose(s.z, want, rtol=1e-9, atol=1e-12)     # W=4, en az 2 gözlem, NaN atlanır
    np.testing.assert_array_equal(_tgt(s, BTC), [.5, .5, 1, 0, 1, .5, 0, 0, .5, .5, 0])
    np.testing.assert_array_equal(_tgt(s, ETH), [.5, .5, 0, 1, 0, .5, 1, 0, .5, .5, 1])
    # W=6 → en az 3 gözlem: i=1 (2 gözlem) NaN, i=2 (3 gözlem) aynı z
    s = _prep(_make("RV_ETHBTC", window=6, z_band=1.0), {BTC: cb, ETH: ce})
    assert np.isnan(s.z[1]) and np.isclose(s.z[2], (5 / 3) / math.sqrt(7 / 3), rtol=1e-9)


# --- nedensellik ---

@pytest.mark.parametrize("fam", list(FAMILIES))
def test_lookahead_corruption_leaves_decisions_unchanged(market, fam):
    s0 = _make(fam)
    base = _run(market, s0, assets=market.assets)
    rng = np.random.default_rng(1)
    inp = dict(panel_1d=market.panel_1d, panel_1h=market.panel_1h, universe=market.universe, delist=market.delist)
    for t in ("2019-11-15", "2020-03-02", "2020-08-20"):
        bad = corrupt_after(t, rng, assets=market.assets, **inp)
        s1 = _make(fam)
        r = _run(market, s1, assets=market.assets, **{k: bad[k] for k in inp if k in bad})
        assert compare_until(base, r, t) == [], t
        assert compare_until(base, r, "2100-01-01") != []        # bozma gerçekten etkili
        k = s0.data.days.get_loc(pd.Timestamp(t))
        for a in SIGNALS[fam]:
            np.testing.assert_array_equal(getattr(s0, a)[:k + 1], getattr(s1, a)[:k + 1])
            assert not np.array_equal(getattr(s0, a), getattr(s1, a), equal_nan=True)
    assert len(base.fills) > 5


# --- yürütme ---

def test_vm_exposure_and_band(market):
    r = _run(market, _make("VM_BTC"))
    assert r.daily["gross_exposure"].max() <= 1.0 + 1e-9
    assert set(r.fills["asset"]) == {BTC} and set(r.fills["kind"]) <= {"entry", "exit", "tier"}
    d = r.decisions[r.decisions["asset"] == BTC]
    assert d["w_tgt"].max() <= 1.0 and d["w_tgt"].min() < 0.9            # oynaklık ölçeklemesi etkin
    held = d[(d["w"] > 0) & (d["w_tgt"] > 0)]
    out = ((held["w"] - held["w_tgt"]).abs() > 0.20 * held["w_tgt"]).to_numpy()
    np.testing.assert_array_equal(held["reason"].to_numpy() == "tier", out)   # işlem ⇔ |w − w*| > B·w*
    assert 3 <= out.sum() < len(held) / 5
    tier = held[out]
    np.testing.assert_allclose(tier["delta"], tier["w_tgt"] - tier["w"], atol=1e-12)
    assert set(d.loc[d["w"] == 0, "reason"]) <= {"entry", "none"}


def test_mr_full_in_or_out_never_resized(market):
    s = _make("MR_BTC")
    r = _run(market, s)
    f = r.fills
    assert set(f["asset"]) == {BTC} and set(f["kind"]) <= {"entry", "exit"} and (f["kind"] == "entry").sum() >= 3
    assert "tier" not in set(r.decisions["reason"])
    g = r.daily["gross_exposure"].to_numpy()
    assert np.all((g < 1e-12) | (g > 0.99))
    days, i0 = s.data.days, s.data.start_idx
    for dd, kind in zip(f["decision_date"], f["kind"]):        # dolumlar durum geçişlerinde
        i = days.get_loc(dd)
        if kind == "entry":
            assert s.state[i] == 1 and (i == i0 or s.state[i - 1] == 0)
        else:
            assert s.state[i] == 0 and s.state[i - 1] == 1
    assert r.cycles["duration_days"].max() <= s.max_hold


def test_rv_always_invested_btc_eth_only(market):
    r = _run(market, _make("RV_ETHBTC"))
    f = r.fills
    assert set(f["asset"]) == {BTC, ETH}
    g = r.daily["gross_exposure"]
    assert g.loc[f["date"].min():].min() > 0.97 and g.max() <= 1.0 + 1e-9
    others = [c for c in r.weights.columns if c not in (BTC, ETH)]
    assert others and (r.weights[others].to_numpy() == 0).all()
    dec = r.decisions
    assert (dec.loc[~dec["asset"].isin([BTC, ETH]), "w_tgt"] == 0).all()
    tg = dec.pivot(index="date", columns="asset", values="w_tgt").reindex(columns=[BTC, ETH]).fillna(0.0)
    combos = set(map(tuple, tg.to_numpy().round(9).tolist()))
    assert {(1.0, 0.0), (0.0, 1.0), (0.5, 0.5)} <= combos


# --- gecikme kontrolleri ---

@pytest.mark.parametrize("fam", list(FAMILIES))
def test_lag_controls(market, fam):
    a = _run(market, _make(fam), start=None)
    b = _run(market, _make(fam, lag=-1), start=None)               # pozitif kontrol: yarının satırı
    assert not np.allclose(a.daily["ret"].to_numpy(), b.daily["ret"].to_numpy())
    s = _make(fam, lag=365)
    c = _run(market, s, start=None)
    days = s.data.days
    cut = days[365]
    dec = c.decisions
    assert (dec.loc[dec["date"] < cut, "w_tgt"] == 0).all()
    assert (c.daily.loc[:cut, "gross_exposure"] == 0).all() and c.fills["date"].min() > cut
    late = dec[dec["date"] >= cut]
    assert (late["w_tgt"] > 0).any()
    want = [s.target(days.get_loc(t) - 365, None)[s.col[x]] for t, x in zip(late["date"], late["asset"])]
    np.testing.assert_array_equal(late["w_tgt"].to_numpy(), want)
