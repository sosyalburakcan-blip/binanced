"""G7: T1 rejim filtresi ve T9 Bitcoin'e göre güç kapısı durum makineleri."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trend.strategy.filters import RelativeStrengthGate, regime_state, relative_strength


def _reference_regime(c: pd.Series, n=200, lo=0.97, hi=1.03):
    sma = c.rolling(n).mean()
    out, st = [], None
    for x, m in zip(c, sma):
        if np.isnan(m):
            out.append(np.nan)
            continue
        if st is None:
            st = 1.0 if x > m else 0.0
        elif x < lo * m:
            st = 0.0
        elif x > hi * m:
            st = 1.0
        out.append(st)
    return np.array(out)


def test_regime_hysteresis_hand_scenario():
    # 200 gün 100'de sabit → SMA 100; başlangıç C > SMA değil → KAPALI
    p = [100.0] * 200 + [102.0, 106.0, 101.0, 98.0, 96.0, 99.0, 104.0]
    st = regime_state(pd.Series(p), 200, 0.97, 1.03)
    assert np.isnan(st[198]) and st[199] == 0
    # 102: SMA≈100.01 → 1.03·SMA≈103.0 → kapalı kalır; 106 → AÇIK; 101 ve 98 → açık kalır (> 0.97·SMA);
    # 96 < 0.97·SMA(≈97.1) → KAPALI; 99 → kapalı; 104 > 1.03·SMA(≈103.1) → AÇIK
    assert st[200:].tolist() == [0, 1, 1, 1, 0, 0, 1]


def test_regime_matches_loop_reference():
    rng = np.random.default_rng(3)
    c = pd.Series(100 * np.exp(np.cumsum(rng.standard_normal(1500) * 0.03)))
    np.testing.assert_array_equal(regime_state(c, 200, 0.97, 1.03), _reference_regime(c))
    # histerezis rejim değişimini azaltır
    plain = (c > c.rolling(200).mean()).astype(float)[199:]
    assert np.abs(np.diff(regime_state(c, 200, 0.97, 1.03)[199:])).sum() < np.abs(np.diff(plain)).sum()


def test_relative_strength_definition():
    idx = pd.date_range("2020-01-01", periods=40)
    btc = pd.Series(np.linspace(100, 139, 40), index=idx)
    alt = pd.Series(np.linspace(10, 49, 40), index=idx)
    close = pd.DataFrame({"BTCUSDT": btc, "ALTUSDT": alt})
    rel = relative_strength(close, "BTCUSDT", 30)
    exp = np.log(alt.iloc[35] / alt.iloc[5]) - np.log(btc.iloc[35] / btc.iloc[5])
    assert np.isclose(rel[35, 1], exp) and np.isnan(rel[29, 1]) and np.isnan(rel[:, 0]).all()


def test_rs_gate_state_machine():
    g = RelativeStrengthGate(5, 2 / 3, 1 / 3, -0.05)
    uni = np.ones(5, bool)
    nan = np.nan
    # gün 1 (başlangıç): q = [1, .75, .5, .25] → 1, 1, 0 (arada → başlangıçta 0), 0
    out = g.step(np.array([nan, 0.10, 0.02, -0.01, -0.08]), uni, uni, btc_idx=0)
    assert out.tolist() == [1, 1, 1, 0, 0]
    # gün 2: q = [.75, .5, 1, .25] → 1 (açık), 1 (arada, korunur), 1 (açık), 0
    out = g.step(np.array([nan, 0.01, -0.02, 0.05, -0.03]), uni, uni, btc_idx=0)
    assert out.tolist() == [1, 1, 1, 1, 0]
    # gün 3: q = [.5, .25, 1, .75] → 1 (korunur), 0 (q < 1/3), 1, 1
    out = g.step(np.array([nan, 0.0, -0.06, 0.04, 0.03]), uni, uni, btc_idx=0)
    assert out.tolist() == [1, 1, 0, 1, 1]
    # gün 4: rel < −0.05 → 0 (q yüksek olsa da); tanımsız rel → 0 ve durum sıfırlanır
    out = g.step(np.array([nan, -0.051, -0.2, nan, -0.3]), uni, uni, btc_idx=0)
    assert out.tolist() == [1, 0, 0, 0, 0]
    assert g.state[3] == -1


def test_rs_gate_held_out_of_universe_ranked_as_inserted():
    g = RelativeStrengthGate(4, 2 / 3, 1 / 3, -0.05)
    uni = np.array([True, True, True, False])
    cand = np.ones(4, bool)
    # E (BTC hariç) = {1, 2}; coin 3 (H) rel en yüksek → eklenmiş sıra 3/3 = 1 → açık
    out = g.step(np.array([np.nan, 0.01, 0.02, 0.05]), uni, cand, btc_idx=0)
    assert out.tolist() == [1, 0, 1, 1]
