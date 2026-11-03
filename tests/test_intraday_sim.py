"""Gün içi simülatör (trend.intraday.sim): el hesabı sinyal, çıkış türleri, muhasebe, nedensellik, kontroller, hız.

Yalnızca sentetik 15 dk piyasalar (gerçek veri kullanılmaz).
"""

import math
import statistics
import time

import numpy as np
import pandas as pd
import pytest

from trend.intraday.sim import Costs, Market, Params, hourly_close, hourly_signals, simulate

T0 = "2024-01-01"
NaN = np.nan
P0 = Params(lookback_h=2, z_entry=0.0, confirm_h=1, tp=0.02, sl=0.03, max_hold_h=6, vol_window_h=4, n_top=1, slots=2)
K0 = Costs(taker=0.001, maker=0.0005, tax_per_side=0.0002, mmr=0.005, liq_fee=0.01)
SLIP = 0.001
P_IN = 100.0 * (1 + SLIP)           # zorunlu girişin dolum fiyatı (bar 96 açılışı 100)
ZERO = Costs(taker=0.0, maker=0.0)


# --- yardımcılar ---

def _flat(n_days=3, n_assets=1, px=100.0, futures=False) -> Market:
    T = 96 * n_days
    o = np.full((T, n_assets), px)
    return Market(assets=[f"A{j}" for j in range(n_assets)], t15=pd.date_range(T0, periods=T, freq="15min"),
                  o=o, h=o.copy(), l=o.copy(), c=o.copy(), funding=np.zeros((T, n_assets)) if futures else None)


def _bar(m, j, o, h, l, c, a=0):  # noqa: E741
    m.o[j, a], m.h[j, a], m.l[j, a], m.c[j, a] = o, h, l, c


def _from(m, j, px, a=0):
    for x in (m.o, m.h, m.l, m.c):
        x[j:, a] = px


def _one(m, p=P0, k=K0, slip=SLIP, k0=23, a=0, **kw):
    """Tek zorunlu giriş: yalnızca k0 saatinde uygun + random_entries = 1 → giriş 4(k0+1) = 96 barında."""
    T1 = len(m.t15) // 4
    el = np.zeros((T1, len(m.assets)), dtype=bool)
    el[k0, a] = True
    return simulate(m, el, np.full(el.shape, slip), p, k, start=T0, random_entries=1.0, rng=0, **kw)


def _pnl(N, p_out, out_fee, k=K0, p_in=P_IN):
    q = N / p_in
    return q * (p_out - p_in) - N * (k.taker + k.tax_per_side) - q * p_out * (out_fee + k.tax_per_side)


def _rw(n_days, n_assets, seed, vol=0.004, amp=0.0015, futures=False, T=None) -> Market:
    """Rejimli sürüklenmeli rastgele yürüyüş (15 dk), tutarlı o/h/l/c; vadelide 8 saatte bir fonlama."""
    g = np.random.default_rng(seed)
    T = T or 96 * n_days
    t = np.arange(T)[:, None]
    mu = amp * np.sin(2 * np.pi * t / (96 * 3) + g.uniform(0, 2 * np.pi, n_assets))
    c = 100.0 * np.exp(np.cumsum(mu + g.normal(0, vol, (T, n_assets)), axis=0))
    o = np.vstack([np.full((1, n_assets), 100.0), c[:-1]]) * np.exp(g.normal(0, vol / 4, (T, n_assets)))
    h = np.maximum(o, c) * np.exp(np.abs(g.normal(0, vol / 2, (T, n_assets))))
    l = np.minimum(o, c) * np.exp(-np.abs(g.normal(0, vol / 2, (T, n_assets))))  # noqa: E741
    fund = None
    if futures:
        fund = np.zeros((T, n_assets))
        fund[::32] = g.normal(1e-4, 2e-4, fund[::32].shape)
    return Market(assets=[f"C{j}" for j in range(n_assets)], t15=pd.date_range(T0, periods=T, freq="15min"),
                  o=o, h=h, l=l, c=c, funding=fund)


def _inputs(m, slip=0.0005):
    T1 = len(m.t15) // 4
    return np.ones((T1, len(m.assets)), dtype=bool), np.full((T1, len(m.assets)), slip)


SIG = Params(lookback_h=6, z_entry=0.5, confirm_h=2, tp=0.02, sl=0.015, max_hold_h=6, vol_window_h=24, n_top=3,
             slots=3)


def _ref_signals(C, elig, L, W, n_conf, n_top, z_entry):
    """Döngülerle el hesabı (kural 1–3)."""
    T1, A = C.shape
    z = np.full((T1, A), np.nan)
    for a in range(A):
        for k in range(L, T1):
            if not (np.isfinite(C[k, a]) and np.isfinite(C[k - L, a])):
                continue
            rs = [math.log(C[j, a] / C[j - 1, a]) for j in range(max(1, k - W + 1), k + 1)
                  if np.isfinite(C[j, a]) and np.isfinite(C[j - 1, a])]
            if len(rs) < max(2, W // 2):
                continue
            sd = statistics.stdev(rs)
            if sd > 0:
                z[k, a] = math.log(C[k, a] / C[k - L, a]) / (sd * math.sqrt(L))
    ok = np.zeros((T1, A), dtype=bool)
    top = np.zeros((T1, A), dtype=bool)
    for k in range(T1):
        for a in range(A):
            ok[k, a] = k >= n_conf - 1 and all(np.isfinite(z[j, a]) and z[j, a] >= z_entry
                                               for j in range(k - n_conf + 1, k + 1))
        cands = sorted((-z[k, a], a) for a in range(A) if elig[k, a] and np.isfinite(z[k, a]))
        for _, a in cands[:n_top]:
            top[k, a] = True
    return z, ok, top


# --- sinyal: el hesabı ---

def _tiny():
    r = np.array([[0, .01, .03, -.01, .02, .015, .02, -.005],
                  [0, -.01, .01, .02, .02, .03, .04, .045],
                  [0, .005, -.005, .01, .03, .02, .01, .012]]).T
    C = 100.0 * np.exp(np.cumsum(r, axis=0))
    C[4, 2] = NaN                                        # A2'nin 4. saat kapanışı yok
    T = 4 * C.shape[0]
    bars = np.repeat(C * 1.01, 4, axis=0)                # saat içi tuzak kapanışlar
    bars[3::4] = C                                       # saatlik kapanış = 4k+3 barı
    bars[4 * 4 + 3, 2] = NaN
    m = Market(assets=["A0", "A1", "A2"], t15=pd.date_range(T0, periods=T, freq="15min"), o=bars.copy(),
               h=bars.copy(), l=bars.copy(), c=bars.copy(), funding=None)
    return m, C


def test_hourly_close_and_signals_match_hand_computation():
    m, C = _tiny()
    Ch = hourly_close(m)
    np.testing.assert_allclose(Ch, C, equal_nan=True)
    elig = np.ones(C.shape, dtype=bool)
    elig[6, 1] = False
    p = Params(lookback_h=2, z_entry=0.3, confirm_h=2, tp=0.1, sl=0.1, max_hold_h=1, vol_window_h=4, n_top=2)
    z, ok, top = hourly_signals(Ch, elig, p)
    # A0, k = 4: r_1..r_4 = .01 .03 −.01 .02 → ortalama .0125, Σ sapma² = 8.75e-4; mom = r_3 + r_4 = .01
    assert z[4, 0] == pytest.approx(0.01 / (math.sqrt(8.75e-4 / 3) * math.sqrt(2)), rel=1e-9)
    assert np.isnan(z[:2]).all() and np.isnan(z[4, 2]) and np.isnan(z[6, 2]) and np.isfinite(z[5, 2])
    rz, rok, rtop = _ref_signals(C, elig, 2, 4, 2, 2, 0.3)
    np.testing.assert_allclose(z, rz, rtol=1e-9, equal_nan=True)
    np.testing.assert_array_equal(ok, rok)
    np.testing.assert_array_equal(top, rtop)
    assert not top[6, 1] and ok.any() and (~ok & top).any()          # uygunluk süzgeci; liste ≠ takip
    assert (top.sum(axis=1) <= 2).all()


def _prio_market():
    """3 varlık, saat içi düz barlar; 23. saatte üçü de aday (z_entry çok düşük)."""
    T1 = 36
    k = np.arange(T1)[:, None]
    mu = np.array([0.001, 0.004, 0.0025])
    C = 100.0 * np.exp(mu * k + 0.003 * np.sin(1.7 * k + np.arange(3)))
    bars = np.repeat(C, 4, axis=0)
    m = Market(assets=["A0", "A1", "A2"], t15=pd.date_range(T0, periods=4 * T1, freq="15min"), o=bars.copy(),
               h=bars.copy(), l=bars.copy(), c=bars.copy(), funding=None)
    return m, C


def test_top_list_priority_by_z_slots_and_eligibility():
    m, C = _prio_market()
    T1 = C.shape[0]
    p = Params(lookback_h=3, z_entry=-10.0, confirm_h=2, tp=1.0, sl=0.99, max_hold_h=100, vol_window_h=8, n_top=3,
               slots=1)
    elig = np.zeros((T1, 3), dtype=bool)
    elig[23] = True                                      # yalnızca 23. saat kararı
    slip = np.zeros((T1, 3))
    z, _, _ = _ref_signals(C, np.ones((T1, 3), bool), 3, 8, 2, 3, -10.0)
    rank = np.argsort(-z[23])
    assert rank[0] != 0 and np.isfinite(z[23]).all()       # öncelik sütun sırasıyla aynı değil
    r = simulate(m, elig, slip, p, ZERO, start=T0)
    assert list(r.trades["asset"]) == [m.assets[rank[0]]]
    assert r.trades["entry_time"].iloc[0] == pd.Timestamp("2024-01-02 00:00")
    r2 = simulate(m, elig, slip, Params(**{**p.__dict__, "slots": 2}), ZERO, start=T0)
    assert set(r2.trades["asset"]) == {m.assets[rank[0]], m.assets[rank[1]]}
    assert r2.trades["margin"].nunique() == 1                         # aynı saatte tek özsermaye ölçümü
    r3 = simulate(m, elig, slip, Params(**{**p.__dict__, "slots": 2, "n_top": 1}), ZERO, start=T0)
    assert list(r3.trades["asset"]) == [m.assets[rank[0]]]           # liste dışı aday yok
    el2 = elig.copy()
    el2[23, rank[0]] = False
    r4 = simulate(m, el2, slip, p, ZERO, start=T0)
    assert list(r4.trades["asset"]) == [m.assets[rank[1]]]


# --- çıkış türleri ---

def test_take_profit_maker_no_slippage_fees_both_sides():
    m = _flat()
    _bar(m, 98, 100, 103, 99.5, 101)
    r = _one(m)
    t = r.trades.iloc[0]
    assert len(r.trades) == 1 and t.reason == "tp"
    assert t.entry_time == m.t15[96] and t.exit_time == m.t15[98]
    assert t.p_in == pytest.approx(P_IN) and t.p_out == pytest.approx(P_IN * 1.02)
    N, q = 0.5, 0.5 / P_IN
    assert t.margin == pytest.approx(0.5) and t.notional == pytest.approx(N)
    assert t.fees == pytest.approx(N * 0.0012 + q * P_IN * 1.02 * 0.0007)
    assert t.pnl == pytest.approx(_pnl(N, P_IN * 1.02, K0.maker))
    assert r.nav.iloc[0] == 1.0 and r.nav.iloc[-1] == pytest.approx(1 + t.pnl)
    assert r.diag["same_bar_ambiguous"] == 0


def test_stop_loss_with_slippage_and_gap_fills_at_open():
    m = _flat()
    _bar(m, 99, 100, 100, 95, 96)
    t = _one(m).trades.iloc[0]
    sl_px = P_IN * 0.97
    assert t.reason == "sl" and t.exit_time == m.t15[99]
    assert t.p_out == pytest.approx(sl_px * (1 - SLIP))
    assert t.pnl == pytest.approx(_pnl(0.5, sl_px * (1 - SLIP), K0.taker))
    m = _flat()
    _bar(m, 99, 96, 96.5, 95, 96)                        # açılış SL'nin altında → açılıştan
    t = _one(m).trades.iloc[0]
    assert t.reason == "sl" and t.p_out == pytest.approx(96 * (1 - SLIP))
    assert t.fees == pytest.approx(0.5 * 0.0012 + 0.5 / P_IN * 96 * (1 - SLIP) * 0.0012)


def test_time_stop_and_missing_bars_count_toward_it():
    p = Params(**{**P0.__dict__, "max_hold_h": 2})
    m = _flat()
    _from(m, 104, 101.0)
    t = _one(m, p).trades.iloc[0]
    assert t.reason == "time" and t.exit_time == m.t15[96 + 8] and t.p_out == pytest.approx(101 * (1 - SLIP))
    assert t.pnl == pytest.approx(_pnl(0.5, 101 * (1 - SLIP), K0.taker))
    m.l[100:104, 0] = 50.0                               # eksik barlar tetiklemez
    for x in (m.o, m.h, m.l, m.c):
        x[100:104, 0] = NaN
    t = _one(m, p).trades.iloc[0]
    assert t.reason == "time" and t.exit_time == m.t15[104]
    for x in (m.o, m.h, m.l, m.c):
        x[104, 0] = NaN                                  # süre barı yok → ilk mevcut barın açılışı
    t = _one(m, p).trades.iloc[0]
    assert t.reason == "time" and t.exit_time == m.t15[105]


def test_same_bar_tp_and_sl_assumes_sl_first():
    m = _flat()
    _bar(m, 98, 100, 103, 95, 100)
    r = _one(m)
    t = r.trades.iloc[0]
    assert t.reason == "sl" and t.p_out == pytest.approx(P_IN * 0.97 * (1 - SLIP))
    assert r.diag["same_bar_ambiguous"] == 1


@pytest.mark.parametrize("lev,sl,bar,reason,px", [
    (3, 0.5, (60, 61, 59, 60), "liq", 60.0),                       # boşluk: açılış ≤ likidasyon
    (3, 0.5, (100, 100, 65, 99), "liq", P_IN * (1 - 1 / 3 + 0.005)),  # SL likidasyonun altında → önce likidasyon
    (5, 0.1, (75, 76, 74, 75), "liq", 75.0),                       # 5×: boşluk SL'yi de geçer
    (5, 0.1, (100, 100, 70, 95), "sl", P_IN * 0.9 * (1 - SLIP)),   # 5×: SL likidasyondan önce
])
def test_liquidation_on_gap_3x_5x(lev, sl, bar, reason, px):
    m = _flat(futures=True)
    _bar(m, 100, *bar)
    _from(m, 101, bar[3])
    p = Params(**{**P0.__dict__, "leverage": float(lev), "sl": sl})
    r = _one(m, p)
    t = r.trades.iloc[0]
    N = 0.5 * lev
    assert t.reason == reason and t.exit_time == m.t15[100] and t.p_out == pytest.approx(px)
    if reason == "liq":
        assert t.pnl == pytest.approx(-0.5 - N * (K0.taker + K0.tax_per_side) - N * (K0.liq_fee + K0.tax_per_side))
        assert t.fees == pytest.approx(N * (K0.taker + K0.tax_per_side) + N * (K0.liq_fee + K0.tax_per_side))
    else:
        assert t.pnl == pytest.approx(_pnl(N, px, K0.taker)) and t.pnl > -0.5
    assert r.nav.iloc[-1] == pytest.approx(1 + t.pnl)


def test_funding_charged_only_while_held():
    m = _flat(futures=True)
    m.funding[96, 0] = 0.01                              # giriş barı: alınmaz
    m.funding[128, 0] = 0.001
    m.funding[136, 0] = 0.002                            # çıkış barı: alınır
    m.funding[160, 0] = 0.005                            # çıkıştan sonra: alınmaz
    _bar(m, 128, 102, 102, 100, 100)
    p = Params(**{**P0.__dict__, "max_hold_h": 10, "tp": 0.05, "leverage": 2.0})
    r = _one(m, p)
    t = r.trades.iloc[0]
    q = 1.0 / P_IN
    assert t.reason == "time" and t.exit_time == m.t15[136]
    assert t.funding == pytest.approx(q * 102 * 0.001 + q * 100 * 0.002)
    assert t.pnl == pytest.approx(_pnl(1.0, 100 * (1 - SLIP), K0.taker) - t.funding)
    assert r.nav.iloc[-1] == pytest.approx(1 + t.pnl)
    m.funding[:] = 0.0
    assert _one(m, p).trades["funding"].iloc[0] == 0.0


def test_spot_requires_leverage_one():
    m = _flat()
    with pytest.raises(ValueError):
        _one(m, Params(**{**P0.__dict__, "leverage": 2.0}))


# --- muhasebe ---

def test_zero_cost_always_in_equals_buy_and_hold():
    m = _rw(6, 1, seed=3)
    el, _ = _inputs(m)
    p = Params(lookback_h=2, z_entry=0.0, confirm_h=1, tp=1e6, sl=1.0, max_hold_h=10 ** 6, vol_window_h=4, slots=1)
    r = simulate(m, el, np.zeros(el.shape), p, ZERO, start=T0, random_entries=1.0, rng=1)
    assert len(r.trades) == 1 and r.trades["reason"].iloc[0] == "end"
    days = pd.date_range(T0, periods=6, freq="D")
    last = np.arange(1, 7) * 96 - 1
    bh = m.c[last, 0] / m.o[96, 0]
    bh[0] = 1.0
    np.testing.assert_allclose(r.nav.to_numpy(), bh, rtol=1e-12)
    assert list(r.nav.index) == list(days)
    assert r.trades["pnl"].iloc[0] == pytest.approx(m.c[-1, 0] / m.o[96, 0] - 1)


@pytest.mark.parametrize("futures,lev", [(False, 1.0), (True, 3.0)])
def test_equity_identity_cash_plus_positions(futures, lev):
    m = _rw(20, 5, seed=11, futures=futures)
    el, sl = _inputs(m)
    p = Params(**{**SIG.__dict__, "leverage": lev})
    r = simulate(m, el, sl, p, K0, start=T0)
    tr = r.trades
    assert len(tr) > 30
    assert r.nav.iloc[0] == 1.0
    assert r.nav.iloc[-1] == pytest.approx(1 + tr["pnl"].sum(), rel=1e-10)
    np.testing.assert_allclose(r.daily["cash"] + r.daily["pos_value"], r.nav, rtol=1e-12)
    if futures:
        return
    # bağımsız yeniden kurulum (spot, fonlama yok): nakit ve pozisyonlar işlem tablosundan
    cf = pd.DataFrame(m.c).ffill().to_numpy()
    col = {a: j for j, a in enumerate(m.assets)}
    fee_in = tr["notional"] * (K0.taker + K0.tax_per_side)
    for d in r.nav.index:
        jd = int(m.t15.searchsorted(d + pd.Timedelta(days=1))) - 1
        td = m.t15[jd]
        ent, ext = tr["entry_time"] <= td, tr["exit_time"] <= td
        cash = 1.0 - (tr["margin"] + fee_in)[ent].sum() + (tr["pnl"] + tr["margin"] + fee_in)[ext].sum()
        op = tr[ent & ~ext]
        pos = sum(row.margin + row.qty * (cf[jd, col[row.asset]] - row.p_in) for row in op.itertuples())
        assert cash + pos == pytest.approx(r.nav.loc[d], rel=1e-10)
        assert len(op) <= p.slots


# --- nedensellik ---

@pytest.mark.parametrize("mode", ["signal_spot", "signal_fut", "random"])
def test_causality_future_changes_do_not_affect_past(mode):
    fut = mode == "signal_fut"
    m = _rw(30, 6, seed=21, futures=fut)
    el, sl = _inputs(m)
    el[::7, 2] = False
    p = Params(**{**SIG.__dict__, "leverage": 2.0 if fut else 1.0, "slots": 2})
    kw = {"random_entries": 0.05, "rng": 5} if mode == "random" else {}
    cut_day = pd.Timestamp("2024-01-15")
    J = int(m.t15.searchsorted(cut_day + pd.Timedelta(days=1)))    # ilk değişen bar (k = 15 Ocak 23:00 saati)
    kh = J // 4
    m2 = _rw(30, 6, seed=99, futures=fut)
    alt = Market(assets=m.assets, t15=m.t15, o=m.o.copy(), h=m.h.copy(), l=m.l.copy(), c=m.c.copy(),
                 funding=None if m.funding is None else m.funding.copy())
    for x, y in ((alt.o, m2.o), (alt.h, m2.h), (alt.l, m2.l), (alt.c, m2.c)):
        x[J:] = y[J:] * 1.3
    if fut:
        alt.funding[J:] = m2.funding[J:] * 5
    el2, sl2 = el.copy(), sl.copy()
    el2[kh:] = ~el2[kh:]
    sl2[kh:] *= 3
    r1 = simulate(m, el, sl, p, K0, start=T0, **kw)
    r2 = simulate(alt, el2, sl2, p, K0, start=T0, **kw)
    tJ = m.t15[J]
    a1, a2 = r1.trades[r1.trades["entry_time"] < tJ], r2.trades[r2.trades["entry_time"] < tJ]
    assert len(a1) > 5
    cols = ["asset", "entry_time", "p_in", "margin", "notional", "qty"]
    pd.testing.assert_frame_equal(a1[cols].reset_index(drop=True), a2[cols].reset_index(drop=True))
    b1, b2 = r1.trades[r1.trades["exit_time"] < tJ], r2.trades[r2.trades["exit_time"] < tJ]
    pd.testing.assert_frame_equal(b1.reset_index(drop=True), b2.reset_index(drop=True))
    pd.testing.assert_series_equal(r1.nav.loc[:cut_day], r2.nav.loc[:cut_day])
    assert not r1.nav.loc[cut_day + pd.Timedelta(days=2):].equals(r2.nav.loc[cut_day + pd.Timedelta(days=2):])


# --- kontroller ---

def test_lag_controls():
    m = _rw(12, 4, seed=7)
    el, sl = _inputs(m)
    r0 = simulate(m, el, sl, SIG, K0, start=T0)
    rl = simulate(m, el, sl, SIG, K0, start=T0, lag_h=-1)
    assert len(r0.trades) > 10
    assert not r0.nav.equals(rl.nav)
    assert rl.nav.iloc[-1] > r0.nav.iloc[-1]                      # sızıntı kazandırır
    # +1: tek varlık, süre çıkışlı 1 saatlik işlemler, uygunluk penceresi ortada → tüm girişler tam 1 saat kayar
    m1 = _rw(10, 1, seed=8)
    T1 = len(m1.t15) // 4
    el1 = np.zeros((T1, 1), dtype=bool)
    el1[24 * 3: 24 * 7] = True
    p = Params(lookback_h=3, z_entry=0.3, confirm_h=1, tp=10.0, sl=1.0, max_hold_h=1, vol_window_h=12, n_top=1, slots=1)
    s0 = simulate(m1, el1, np.zeros((T1, 1)), p, ZERO, start=T0)
    s1 = simulate(m1, el1, np.zeros((T1, 1)), p, ZERO, start=T0, lag_h=1)
    assert len(s0.trades) >= 5 and (s0.trades["reason"] == "time").all()
    pd.testing.assert_series_equal(s1.trades["entry_time"], s0.trades["entry_time"] + pd.Timedelta(hours=1))


def test_random_entries_reproducible_with_seed():
    m = _rw(10, 5, seed=4)
    el, sl = _inputs(m)
    a = simulate(m, el, sl, SIG, K0, start=T0, random_entries=0.05, rng=123)
    b = simulate(m, el, sl, SIG, K0, start=T0, random_entries=0.05, rng=np.random.default_rng(123))
    c = simulate(m, el, sl, SIG, K0, start=T0, random_entries=0.05, rng=124)
    assert len(a.trades) > 10
    pd.testing.assert_frame_equal(a.trades, b.trades)
    pd.testing.assert_series_equal(a.nav, b.nav)
    assert not a.trades["entry_time"].equals(c.trades["entry_time"])


def test_slots_limit_and_one_position_per_asset():
    m = _rw(10, 6, seed=9)
    el, sl = _inputs(m)
    p = Params(**{**SIG.__dict__, "slots": 2, "max_hold_h": 4, "tp": 0.03, "sl": 0.02})
    r = simulate(m, el, sl, p, K0, start=T0, random_entries=0.2, rng=0)
    tr = r.trades
    assert len(tr) > 20 and r.diag["skipped_no_slot"] > 0
    e, x = tr["entry_time"].to_numpy(), tr["exit_time"].to_numpy()
    over = [int(((e <= ei) & (x >= ei)).sum()) for ei in e]        # [giriş, çıkış] barı kapalı aralık
    assert max(over) == 2
    for _, g in tr.groupby("asset"):
        assert (g["entry_time"].to_numpy()[1:] > g["exit_time"].to_numpy()[:-1]).all()
    assert (r.daily["n_open"] <= 2).all()


# --- hız ---

def test_benchmark_250k_bars_10_assets():
    m = _rw(0, 10, seed=1, T=250_000, futures=True)
    el, sl = _inputs(m)
    p = Params(lookback_h=24, z_entry=1.5, confirm_h=2, tp=0.03, sl=0.02, max_hold_h=24)
    for lev, mk in ((1.0, Market(**{**m.__dict__, "funding": None})), (3.0, m)):
        t0 = time.perf_counter()
        r = simulate(mk, el, sl, Params(**{**p.__dict__, "leverage": lev}), K0)
        dt = time.perf_counter() - t0
        print(f"\n[benchmark] 250k bar × 10 varlık, kaldıraç {lev:g}: {dt:.2f} s, {len(r.trades)} işlem")
        assert len(r.trades) > 1000
        assert dt < 5.0
