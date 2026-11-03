"""G7: tamponlu üç vadeli sinyal (SPEC "Strateji" §1)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trend.strategy.signal import (
    buffered_states,
    ema_on_valid,
    first_eligible_index,
    log_returns,
    rolling_std,
    trend_signal,
)


def _walk(n, seed, cols=3):
    rng = np.random.default_rng(seed)
    r = rng.standard_normal((n, cols)) * 0.04 + 0.001
    return pd.DataFrame(100 * np.exp(np.cumsum(r, axis=0)), index=pd.date_range("2020-01-01", periods=n),
                        columns=[f"X{k}" for k in range(cols)])


def test_ema_matches_pandas_ewm_adjust_false_on_valid_closes():
    c = _walk(300, 1)
    c.iloc[100:105, 1] = np.nan  # boşluk
    c.iloc[:40, 2] = np.nan      # geç listeleme
    out = ema_on_valid(c, 20)
    for j, col in enumerate(c.columns):
        ref = c[col].dropna().ewm(span=20, adjust=False).mean().reindex(c.index)
        np.testing.assert_allclose(out[:, j], ref.to_numpy(), rtol=1e-13, equal_nan=True)


def test_buffered_state_hand_example():
    # EMA = 100 sabit, σ_d = 0.02, h = 0.5 → tampon [99, 101]
    close = np.array([[100.5], [101.5], [100.0], [99.5], [98.9], [100.2], [101.0], [101.01]])
    ema = np.full_like(close, 100.0)
    sig = np.full_like(close, 0.02)
    s = buffered_states(close, ema, sig, 0.5, np.array([0]))
    # başlangıç tamponsuz (100.5 > 100 → 1); bant içinde korunur; 98.9 < 99 → 0; 101.0 = sınır → korunur
    assert s[:, 0].tolist() == [1, 1, 1, 1, 0, 0, 0, 1]
    s0 = buffered_states(close, ema, sig, 0.0, np.array([0]))  # h = 0: tamponsuz (eşitlikte korunur)
    assert s0[:, 0].tolist() == [1, 1, 1, 0, 0, 1, 1, 1]


def test_initial_state_is_unbuffered_rule_on_first_eligible_day():
    close = np.array([[100.4], [100.6], [100.2]])
    ema = np.full_like(close, 100.0)
    sig = np.full_like(close, 0.02)
    # ilk uygun gün = 1: 100.6 > 100 → 1 (tampon 101 olsa da); öncesi NaN
    s = buffered_states(close, ema, sig, 0.5, np.array([1]))
    assert np.isnan(s[0, 0]) and s[1, 0] == 1 and s[2, 0] == 1
    close2 = np.array([[100.4], [99.6], [100.9]])
    s2 = buffered_states(close2, ema, sig, 0.5, np.array([1]))
    assert s2[1, 0] == 0 and s2[2, 0] == 0  # 99.6 < 100 → 0; 100.9 bant içinde → 0 korunur


def test_gap_freezes_state():
    close = np.array([[102.0], [np.nan], [np.nan], [98.0], [100.0]])
    ema = np.array([[100.0], [np.nan], [np.nan], [100.0], [100.0]])
    sig = np.full_like(close, 0.01)
    s = buffered_states(close, ema, sig, 0.5, np.array([0]))
    assert s[:, 0].tolist() == [1, 1, 1, 0, 0]


def _reference_signal(close: pd.Series, spans, h, min_bars):
    """SPEC formülünün düz döngülü uygulaması (bağımsız referans)."""
    valid = close.dropna()
    lr = np.log(close).diff()  # takvim günü; NaN komşuluk → NaN
    sd = lr.rolling(30, min_periods=20).std().ffill()
    out = pd.Series(-1, index=close.index)
    states = {n: None for n in spans}
    emas = {n: valid.ewm(span=n, adjust=False).mean() for n in spans}
    count = 0
    for t in close.index:
        if np.isnan(close[t]):
            if all(states[n] is not None for n in spans):
                out[t] = sum(states.values())
            continue
        count += 1
        if count < min_bars:
            continue
        for n in spans:
            c, e, s = close[t], emas[n][t], sd[t]
            if states[n] is None:
                states[n] = int(c > e)
            elif c > e * (1 + h * s):
                states[n] = 1
            elif c < e * (1 - h * s):
                states[n] = 0
        out[t] = sum(states.values())
    return out.to_numpy()


def test_vectorized_signal_matches_loop_reference_and_tiers():
    c = _walk(500, 2, cols=4)
    c.iloc[260:268, 0] = np.nan
    c.iloc[:120, 3] = np.nan
    res = trend_signal(c, [20, 50, 100], 0.5, 200, 30, 20)
    for j, col in enumerate(c.columns):
        np.testing.assert_array_equal(res["S3"][:, j], _reference_signal(c[col], [20, 50, 100], 0.5, 200))
    vals = set(np.unique(res["S3"]))
    assert vals <= {-1, 0, 1, 2, 3} and {0, 3} <= vals  # S ∈ {0, 1/3, 2/3, 1}


def test_min_200_valid_bars_required():
    c = _walk(400, 3, cols=2)
    c.iloc[:150, 1] = np.nan
    c.iloc[100:130, 0] = np.nan
    res = trend_signal(c, [20, 50, 100], 0.5, 200, 30, 20)
    fe = first_eligible_index(c, 200)
    assert fe.tolist() == [229, 349]  # sütun 0: 30 günlük boşluk 200. barı 229'a iter
    assert (res["S3"][:229, 0] == -1).all() and (res["S3"][229:, 0] >= 0).all()
    assert (res["S3"][:349, 1] == -1).all() and res["S3"][349, 1] >= 0


def test_buffer_reduces_state_changes():
    c = _walk(1500, 4, cols=6)
    flips = {}
    for h in (0.0, 0.5, 1.0):
        s3 = trend_signal(c, [20, 50, 100], h, 200, 30, 20)["S3"][200:]
        flips[h] = int((np.diff(s3, axis=0) != 0).sum())
    assert flips[0.0] > flips[0.5] > flips[1.0]


def test_log_returns_and_sigma_d_definition():
    c = pd.DataFrame({"a": [100.0, 110.0, np.nan, 121.0, 133.1]})
    r = log_returns(c)["a"].to_numpy()
    assert np.isnan(r[0]) and np.isclose(r[1], np.log(1.1)) and np.isnan(r[2]) and np.isnan(r[3])
    sd = rolling_std(log_returns(c), 3, 2, ffill=True)["a"].to_numpy()
    assert np.isnan(sd[1]) and np.isnan(sd[2]) and np.isnan(sd[3])  # yalnız 1 gözlem
    assert np.isnan(sd[4])  # pencere [2,3,4]: tek geçerli getiri (r4) → hâlâ yetersiz


def test_clean_bar_count_uses_flags_only_from_known_from_plus_one():
    from trend.strategy.system import clean_bar_count

    c = _walk(400, 5, cols=2)
    d = c.index
    flags = pd.DataFrame({
        "symbol": ["X0", "X1", "X0"], "check": ["zero_volume", "wick", "dup"],
        "period_start": [d[0], d[0], d[100]], "period_end": [d[149], d[300], d[120]],
        "known_from": [d[249], d[300], d[249]], "severity": ["exclude", "flag", "error"], "detail": "",
    })
    cnt = clean_bar_count(c, flags)
    assert cnt[249, 0] == 250  # işaret t = known_from gününde henüz kullanılamaz (known_from ≤ T−1)
    assert cnt[250, 0] == 251 - 150  # örtüşen işaretler çift sayılmaz (100..120 zaten 0..149 içinde)
    assert ((cnt[:, 0] >= 200).nonzero()[0][:3] == [199, 200, 201]).all()
    assert not (cnt[250:349, 0] >= 200).any() and cnt[349, 0] == 200
    np.testing.assert_array_equal(cnt[:, 1], np.arange(1, 401))  # severity=flag sayımı etkilemez


def test_clean_bar_count_excludes_half_days():
    # PREREGISTRATION §10: yarım gün temiz gün değildir (severity=flag olsa da)
    from trend.strategy.system import clean_bar_count

    c = _walk(250, 6, cols=1)
    d = c.index
    flags = pd.DataFrame({"symbol": ["X0"], "check": ["half_day"], "period_start": [d[0]], "period_end": [d[0]],
                          "known_from": [d[0]], "severity": ["flag"], "detail": ""})
    cnt = clean_bar_count(c, flags)
    assert cnt[199, 0] == 199 and cnt[200, 0] == 200
