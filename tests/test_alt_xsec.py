"""Araştırma v2 kesitsel adaylar (trend.alt.xsec): skor ve seçimin el hesabı, nedensellik, evren/tavan/brüt,
yeniden dengeleme takvimi, gecikme kontrolleri, delist/force_zero çıkışı. Yalnızca sentetik veri."""

import math
import statistics

import numpy as np
import pandas as pd
import pytest

from trend.alt.xsec import FAMILIES, XsLowVol, XsReversal, lowest_n
from trend.backtest.engine import run_backtest
from trend.backtest.fills import fill_prices_from_settings
from trend.backtest.interface import DayView, EngineData
from trend.backtest.lookahead import compare_until, corrupt_after
from trend.backtest.synthetic import make_market
from trend.config import load_settings

COMMON = {"vol_window": 60, "vol_min_obs": 30, "sigma_target": 0.35, "cov_window": 60, "cov_min_obs": 30,
          "drift_band": 0.25}
BASE = {"XS_REV": {"lookback": 7, "n_hold": 5, "every": 7},
        "XS_LOWVOL": {"window": 60, "n_hold": 5, "every": "monthly"}}
FAMS = ["XS_REV", "XS_LOWVOL"]
START = "2019-08-31"            # ay sonu: aylık takvimde ilk karar günü de ay sonu
DAY = pd.Timedelta(days=1)
NAN = np.nan


def _strat(fam, lag=0, **over):
    return FAMILIES[fam]({**BASE[fam], **over}, COMMON, lag=lag)


@pytest.fixture(scope="module")
def market():
    return make_market(n_assets=14, n_days=700, start="2019-01-01", seed=11, min_days=150)


def _run(mk, strat, **kw):
    kw.setdefault("panel_1d", mk.panel_1d)
    kw.setdefault("panel_1h", mk.panel_1h)
    kw.setdefault("universe", mk.universe)
    kw.setdefault("delist", mk.delist)
    kw.setdefault("start", START)
    return run_backtest(strategy=strat, hard_stop=False, assets=mk.assets, **kw)


@pytest.fixture(scope="module")
def base_runs(market):
    return {f: _run(market, _strat(f)) for f in FAMS}


def _univ(mk):
    """Karar günü → {sembol: tavan} (t kararının evreni, ay(t+1))."""
    cache = {}

    def f(t):
        k = mk.universe.key(t)
        if k not in cache:
            tbl = mk.universe(t)
            cache[k] = dict(zip(tbl["symbol"].astype(str), tbl["cap"].astype(float)))
        return cache[k]
    return f


def _reb_days(days, every):
    """Yeniden dengeleme günleri: ilk karar günü + her `every` gün (aylık: ay sonları)."""
    first = days.min()
    if every == "monthly":
        return {d for d in days if d == first or (d + DAY).day == 1}
    return {d for d in days if (d - first).days % every == 0}


def _is_retry(dec, a, t, reb):
    """t'deki giriş, son yeniden dengeleme r0'da istenip o günden t'ye her gün hedef > 0 ve pozisyon yokken mi?"""
    r0 = max(x for x in reb if x <= t)
    seg = dec[(dec["asset"] == a) & (dec["date"] >= r0) & (dec["date"] <= t)]
    return len(seg) == (t - r0).days + 1 and (seg["w_tgt"] > 0).all() and (seg["w"] == 0).all()


# --- el hesabı ---

def _prep(strat, close):
    df = pd.DataFrame(close, dtype=float)
    df.index = pd.date_range("2024-01-01", periods=len(df), freq="D")
    strat.prepare(EngineData(days=df.index, assets=list(df.columns), close=df, cfg={}, btc_idx=None))
    return strat


def _view(i, univ, force_zero=None):
    univ = np.asarray(univ, dtype=bool)
    n = univ.size
    fz = np.zeros(n, dtype=bool) if force_zero is None else np.asarray(force_zero, dtype=bool)
    z = np.zeros(n)
    return DayView(i=i, t=pd.Timestamp("2024-01-01") + i * DAY, first=False, base=1.0, nav=1.0, qty=z, w=z,
                   held=np.zeros(n, dtype=bool), frozen=np.zeros(n, dtype=bool), univ=univ,
                   cap=np.full(n, np.inf), force_zero=fz, s3_last=np.full(n, -1), mintrade=0.0)


SMALL = {"vol_window": 4, "vol_min_obs": 2, "sigma_target": 0.35, "cov_window": 4, "cov_min_obs": 2,
         "drift_band": 0.25}


def test_lowest_n_ties_and_short_list():
    s = np.array([0.0, -1.0, -1.0, NAN, -2.0])
    ok = np.array([True, True, True, False, False])
    assert np.flatnonzero(lowest_n(s, ok, 1)).tolist() == [1]          # eşitlik: düşük indeks
    assert np.flatnonzero(lowest_n(s, ok, 2)).tolist() == [1, 2]
    assert np.flatnonzero(lowest_n(s, ok, 10)).tolist() == [0, 1, 2]   # uygun < N → hepsi
    assert not lowest_n(s, np.zeros(5, dtype=bool), 3).any()


def test_xs_rev_hand_computed():
    close = {
        "A": [10, 11, 12, 11, 10, 9, 8, 9],
        "B": [20, 22, 24, 22, 20, 18, 16, 18],          # = 2·A → skor A ile birebir eşit
        "C": [5, 5, 5, NAN, 5, 4, 3, 3],                # boşluk: skor[3] ve skor[5] NaN (ileri doldurma yok)
        "D": [10, 9, 8, 7, 6, 5, 4, 3],                 # çok düşen ama evren dışı
        "E": [10, 10, 9, 8, 6, 4, 2, 2],                # en çok düşen ama force_zero
        "F": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7],  # kazanan
    }
    s = _prep(XsReversal({"lookback": 2, "n_hold": 2, "every": 7}, SMALL), close)
    names = list(close)
    exp = np.full((8, 6), NAN)
    for i in range(2, 8):
        for k, a in enumerate(names):
            p1, p0 = close[a][i], close[a][i - 2]
            if math.isfinite(p1) and math.isfinite(p0):
                exp[i, k] = math.log(p1 / p0)
    np.testing.assert_allclose(s.score, exp, rtol=1e-14, equal_nan=True)
    assert np.isnan(s.score[5, 2]) and np.isclose(s.score[6, 2], math.log(3 / 5)) and s.score[6, 0] == s.score[6, 1]

    univ = [True, True, True, False, True, True]
    fz = [False, False, False, False, True, False]

    def pick(j, n):
        x = _prep(XsReversal({"lookback": 2, "n_hold": n, "every": 7}, SMALL), close)
        return [names[k] for k in np.flatnonzero(x.select(j, _view(j, univ, fz)))]

    # j=6: C (log 0.6) < A = B (log 0.8) < F; D evren dışı, E force_zero → {C, A} (eşitlikte A)
    assert pick(6, 2) == ["A", "C"]
    assert pick(6, 3) == ["A", "B", "C"]
    assert pick(6, 5) == ["A", "B", "C", "F"]                           # yalnızca 4 uygun
    # j=5: C NaN (ileri doldurulsaydı log 0.8 < log(9/11) ile seçilirdi) → {A, B}
    assert pick(5, 2) == ["A", "B"]
    # hedef: yalnızca seçilenler, ham ağırlık 1/σ
    w = s.target(6, _view(6, univ, fz))
    assert np.flatnonzero(w > 0).tolist() == [0, 2]
    assert np.isclose(w[0] / w[2], s.sigma[6, 2] / s.sigma[6, 0])
    assert s.use_universe and s.apply_cap and s.every == 7 and s.band == 0.25


def test_xs_lowvol_hand_computed():
    p = np.array([0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.005, -0.015, 0.01, 0.0, -0.01, 0.02, -0.02, 0.01, 0.005])
    path = lambda x0, r: x0 * np.exp(np.concatenate([[0.0], np.cumsum(r)]))  # noqa: E731
    A = path(100.0, p)
    D = path(10.0, 0.1 * p)
    D[10:12] = NAN                                      # r10, r11, r12 NaN → j=15 penceresinde 9 gözlem < 10
    close = {
        "A": A,
        "B": 2.0 * A,                                   # σ A ile birebir eşit
        "C": path(50.0, 3.0 * p[::-1]),                 # en oynak
        "D": D,                                         # en az oynak ama NaN
        "E": path(30.0, 0.05 * p),                      # az oynak ama evren dışı
        "F": path(20.0, 0.5 * p),                       # A'dan az oynak
        "G": np.full(16, 7.0),                          # σ = 0 → uygun değil
    }
    names = list(close)
    W = 12                                              # en az gözlem max(10, 6) = 10
    s = _prep(XsLowVol({"window": W, "n_hold": 2, "every": "monthly"}, COMMON), close)
    exp = np.full((16, len(names)), NAN)
    for k, a in enumerate(names):
        c = np.asarray(close[a], dtype=float)
        r = [NAN] + [math.log(c[i] / c[i - 1]) if math.isfinite(c[i]) and math.isfinite(c[i - 1]) else NAN
                     for i in range(1, 16)]
        for j in range(16):
            obs = [x for x in r[max(0, j - W + 1): j + 1] if math.isfinite(x)]
            if len(obs) >= 10:
                exp[j, k] = statistics.stdev(obs) * math.sqrt(365.0)
    np.testing.assert_allclose(s.score, exp, rtol=1e-9, atol=1e-12, equal_nan=True)
    assert np.isnan(s.score[15, 3]) and s.score[15, 0] == s.score[15, 1] and s.score[15, 6] == 0.0
    assert np.isnan(s.score[9, 0]) and np.isfinite(s.score[10, 0])

    univ = [True, True, True, True, False, True, True]
    sel = lambda fz=None: [names[k] for k in np.flatnonzero(s.select(15, _view(15, univ, fz)))]  # noqa: E731
    assert sel() == ["A", "F"]                          # F < A = B < C; D NaN, E evren dışı, G σ = 0
    assert sel([False] * 5 + [True, False]) == ["A", "B"]   # F force_zero → sıradaki
    w = s.target(15, _view(15, univ))
    assert np.flatnonzero(w > 0).tolist() == [0, 5]
    assert np.isclose(w[5] / w[0], s.score[15, 0] / s.score[15, 5])
    assert s.every == "monthly" and s.use_universe and s.apply_cap


def test_families_and_contract():
    assert FAMILIES == {"XS_REV": XsReversal, "XS_LOWVOL": XsLowVol}
    for fam in FAMS:
        st = _strat(fam, lag=3)
        assert st.lag == 3 and st.band == COMMON["drift_band"] and st.every == BASE[fam]["every"]
    with pytest.raises(ValueError):
        XsLowVol({"window": 60, "n_hold": 5, "every": "weekly"}, COMMON)


# --- backtest (sentetik piyasa) ---

@pytest.mark.parametrize("fam", FAMS)
def test_lookahead_corruption_leaves_decisions_unchanged(market, base_runs, fam):
    base = base_runs[fam]
    rng = np.random.default_rng(3)
    inp = dict(panel_1d=market.panel_1d, panel_1h=market.panel_1h, universe=market.universe, delist=market.delist)
    for t in ("2019-11-15", "2020-03-02", "2020-08-20"):
        bad = corrupt_after(t, rng, assets=market.assets, **inp)
        r = _run(market, _strat(fam), **{k: bad[k] for k in inp if k in bad})
        assert compare_until(base, r, t) == [], (fam, t)
        assert compare_until(base, r, "2100-01-01") != [], (fam, t)      # bozma gerçekten etkili
    assert len(base.fills) > 20


@pytest.mark.parametrize("fam", FAMS)
def test_universe_cap_and_gross(market, base_runs, fam):
    r = base_runs[fam]
    U = _univ(market)
    band = COMMON["drift_band"]
    close = market.panel_1d["close"]
    assert r.daily["gross_exposure"].max() <= 1.0 + 1e-9
    d = r.decisions
    pos = d[d["w_tgt"] > 0]
    assert len(pos) > 50
    for t, a, wt in zip(pos["date"], pos["asset"], pos["w_tgt"]):
        cap = U(t)
        assert a in cap and wt <= cap[a] + 1e-12, (t, a, wt)
    # çıkış dışı dolumlar yalnızca üyelerde; dolum sonrası ağırlık ≤ tavan·(1 + bant)
    f = r.fills[r.fills["kind"].isin(["entry", "tier"])]
    assert len(f) > 10
    for t, a, pw in zip(f["decision_date"], f["asset"], f["post_weight"]):
        cap = U(t)
        assert a in cap and pw <= cap[a] * (1.0 + band), (t, a, pw)
    # gün sonu tutulan her varlık önceki kararın evren üyesi; değilse o karar çıkıştı (dolmadı) ya da boşluktaydı
    W = r.weights
    reason = d.set_index(["date", "asset"])["reason"]
    for k in range(1, len(W.index)):
        dp = W.index[k - 1]
        cap = U(dp)
        for a in W.columns[W.iloc[k].to_numpy() > 0]:
            if a not in cap:
                assert reason.get((dp, a)) == "exit" or not np.isfinite(close.at[dp, a]), (W.index[k], a)


def _check_timing(r, every) -> int:
    """Çıkış dışı işlemler yalnızca yeniden dengeleme günlerinde veya dolmamış girişin tekrarı; tekrar sayısı."""
    reb = _reb_days(r.daily.index, every)
    if every == "monthly":
        assert all((t + DAY).day == 1 for t in reb)
    d = r.decisions
    trades = d[(d["delta"] != 0) & (d["reason"] != "exit")]
    on = trades["date"].isin(reb)
    assert on.sum() > 10
    assert set(trades.loc[on, "reason"]) <= {"entry", "tier"}
    for t, a, rs in zip(trades.loc[~on, "date"], trades.loc[~on, "asset"], trades.loc[~on, "reason"]):
        assert rs == "entry" and _is_retry(d, a, t, reb), (t, a, rs)
    allowed = set(zip(trades["date"], trades["asset"]))
    f = r.fills[r.fills["kind"].isin(["entry", "tier"])]
    assert all((t, a) in allowed for t, a in zip(f["decision_date"], f["asset"]))
    return int((~on).sum())


@pytest.mark.parametrize("fam,over", [("XS_REV", {}), ("XS_REV", {"every": 3}),
                                      ("XS_LOWVOL", {}), ("XS_LOWVOL", {"every": 10})])
def test_rebalance_timing(market, fam, over):
    r = _run(market, _strat(fam, **over))
    _check_timing(r, {**BASE[fam], **over}["every"])


@pytest.mark.parametrize("fam", FAMS)
def test_failed_entry_is_retried_off_schedule(market, base_runs, fam):
    base = base_runs[fam]
    fp = fill_prices_from_settings(load_settings(), market.panel_1d, market.panel_1h)
    assert compare_until(base, _run(market, _strat(fam), fill_px=fp), "2100-01-01") == []   # aynı dolum fiyatları
    reb = _reb_days(base.daily.index, BASE[fam]["every"])
    tgt = base.decisions.set_index(["date", "asset"])["w_tgt"]
    e = base.fills[(base.fills["kind"] == "entry") & base.fills["decision_date"].isin(reb)]
    e = e[[tgt.get((t, a), 0.0) > 0 and t not in reb for t, a in zip(e["date"], e["asset"])]]
    t, a = e["date"].iloc[0], e["asset"].iloc[0]       # dolum günü t ara gün ve varlık t'de hâlâ hedefte
    fp2 = fp.copy()
    fp2.loc[t, a] = NAN                                # giriş dolmaz → t kararında yeniden denenir
    r = _run(market, _strat(fam), fill_px=fp2)
    row = r.decisions[(r.decisions["date"] == t) & (r.decisions["asset"] == a)].iloc[0]
    assert row["reason"] == "entry" and row["delta"] > 0 and row["w"] == 0
    assert ((r.fills["asset"] == a) & (r.fills["decision_date"] == t) & (r.fills["kind"] == "entry")).any()
    assert _check_timing(r, BASE[fam]["every"]) >= 1


@pytest.mark.parametrize("fam", FAMS)
def test_positive_control_leak_changes_results(market, base_runs, fam):
    b = _run(market, _strat(fam, lag=-1))
    assert not np.allclose(base_runs[fam].daily["ret"].to_numpy(), b.daily["ret"].to_numpy())


@pytest.mark.parametrize("fam", FAMS)
def test_lag_365_zero_target_first_year(market, fam):
    start = pd.Timestamp(market.panel_1d["close"].index[0])
    cut = start + 365 * DAY
    a = _run(market, _strat(fam), start=start)
    b = _run(market, _strat(fam, lag=365), start=start)
    da, db = a.decisions, b.decisions
    assert (da.loc[da["date"] < cut, "w_tgt"] > 0).any()             # gecikmesiz: ilk yılda hedef var
    assert (db.loc[db["date"] < cut, "w_tgt"] == 0).all()
    assert not (b.fills["decision_date"] < cut).any()
    assert (b.daily.loc[: cut - DAY, "gross_exposure"] == 0).all()
    assert (db.loc[db["date"] >= cut, "w_tgt"] > 0).any()


@pytest.mark.parametrize("how", ["announced", "delisted"])
@pytest.mark.parametrize("fam", FAMS)
def test_force_zero_asset_is_exited(market, base_runs, fam, how):
    """Tutulan ve hâlâ hedefte olan bir varlığa ara günde delist duyurusu (karar çıkışı) veya son mum günü (motor
    delist satışı) eklenir; veri sürse de bir daha hedeflenmez/alınmaz."""
    r = base_runs[fam]
    reb = _reb_days(r.daily.index, BASE[fam]["every"])
    close = market.panel_1d["close"]
    tgt = r.decisions.set_index(["date", "asset"])["w_tgt"]
    dead = set(market.delist["asset"])
    pick = None
    for t in r.weights.index[r.weights.index >= "2020-02-01"]:
        if t in reb:
            continue
        for a in r.weights.columns[r.weights.loc[t - DAY].to_numpy() > 0]:
            if (a not in dead and tgt.get((t, a), 0.0) > 0 and r.weights.at[t, a] > 0
                    and np.isfinite(close.at[t, a]) and np.isfinite(close.at[t + DAY, a])):
                pick = (t, a)
                break
        if pick:
            break
    assert pick is not None
    t, a = pick                                          # ara gün, hedefte ve tutuluyor → yalnızca delist çıkarır
    ld, ad = (pd.NaT, t) if how == "announced" else (t, pd.NaT)
    dl = pd.concat([market.delist, pd.DataFrame({"asset": [a], "last_day": [ld], "announced_day": [ad]})],
                   ignore_index=True)
    r2 = _run(market, _strat(fam), delist=dl)
    assert compare_until(r, r2, t - DAY) == []
    d2, f2 = r2.decisions, r2.fills
    assert (d2.loc[(d2["asset"] == a) & (d2["date"] >= t), "w_tgt"] == 0).all()
    if how == "announced":
        row = d2[(d2["date"] == t) & (d2["asset"] == a)].iloc[0]
        assert row["reason"] == "exit" and row["w"] > 0 and row["delta"] == -row["w"]
        ex = f2[(f2["asset"] == a) & (f2["decision_date"] == t)]
        assert ex["kind"].tolist() == ["exit"] and ex["side"].tolist() == ["sell"]
    else:
        ex = f2[(f2["asset"] == a) & (f2["date"] == t)]
        assert ex["kind"].tolist() == ["delist"] and ex["side"].tolist() == ["sell"]
    assert (r2.weights.loc[ex["date"].iloc[0]:, a] == 0).all()
    assert not ((f2["asset"] == a) & (f2["date"] > t) & (f2["side"] == "buy")).any()
