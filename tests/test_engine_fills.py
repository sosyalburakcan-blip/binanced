"""G8: dolum fiyatları (VWAP, saat ekleme, T3/T4), T8 kaydırılmış mumlar, döngü defteri."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trend.backtest.fills import daily_from_hourly, open_fill_prices, vwap_fill_prices
from trend.backtest.ledger import build_cycles
from trend.backtest.synthetic import make_market


def _hourly(vol: dict[int, float], qv: dict[int, float], n_days=3) -> dict:
    idx = pd.date_range("2024-01-01", periods=24 * n_days, freq="h")
    v = pd.DataFrame({"X": 0.0}, index=idx)
    q = pd.DataFrame({"X": 0.0}, index=idx)
    for h, x in vol.items():
        v.iloc[h, 0] = x
    for h, x in qv.items():
        q.iloc[h, 0] = x
    return {"volume": v, "quote_volume": q}


def test_vwap_is_sum_quote_over_sum_volume_and_zero_volume_adds_next_hour():
    # gün 2 (saat 24, 25): hacim 2 ve 3, quote 200 ve 330 → 530/5 = 106
    # gün 3: 00–02 hacim sıfır → saat 02 eklenir (hacim 4, quote 400 → 100)
    p = _hourly({24: 2, 25: 3, 50: 4, 60: 1}, {24: 200, 25: 330, 50: 400, 60: 999})
    fp = vwap_fill_prices(p, 0, 2)
    assert np.isnan(fp.iloc[0, 0])          # gün 1: hiç hacim yok → dolum yok
    assert fp.iloc[1, 0] == pytest.approx(106.0)
    assert fp.iloc[2, 0] == pytest.approx(100.0)
    # T4: 06–07 penceresi (gün 3 saat 06 = 54: hacim yok → 07..11 boş → saat 12 (60) eklenir)
    fp4 = vwap_fill_prices(p, 6, 7)
    assert fp4.iloc[2, 0] == pytest.approx(999.0)


def test_vwap_from_synthetic_matches_manual():
    mk = make_market(n_assets=3, n_days=40, seed=1, n_late=0, n_delist=0, n_gaps=0, min_days=1)
    fp = vwap_fill_prices(mk.panel_1h, 0, 2)
    q, v = mk.panel_1h["quote_volume"], mk.panel_1h["volume"]
    d = 10
    sl = slice(d * 24, d * 24 + 2)
    exp = q.iloc[sl].sum() / v.iloc[sl].sum()
    np.testing.assert_allclose(fp.iloc[d].to_numpy(), exp.to_numpy(), rtol=1e-12)


def test_open_fill_is_daily_open():
    mk = make_market(n_assets=3, n_days=40, seed=1, n_late=0, n_delist=0, n_gaps=0, min_days=1)
    fp = open_fill_prices(mk.panel_1d)
    np.testing.assert_allclose(fp.to_numpy(), mk.panel_1d["open"].to_numpy())
    # sentetikte açılış = önceki kapanış (Binance günlük mumlarında da pratikte öyle)
    np.testing.assert_allclose(fp.iloc[1:].to_numpy(), mk.panel_1d["close"].iloc[:-1].to_numpy(), rtol=1e-12)


def test_daily_from_hourly_standard_and_shifted():
    mk = make_market(n_assets=4, n_days=60, seed=2, n_late=1, n_delist=1, n_gaps=1, min_days=1)
    d0 = daily_from_hourly(mk.panel_1h, 0)
    for k in ("open", "close", "high", "low", "volume", "quote_volume"):
        np.testing.assert_allclose(d0[k].to_numpy(), mk.panel_1d[k].to_numpy(), rtol=1e-12, equal_nan=True)
    d4 = daily_from_hourly(mk.panel_1h, 4)
    h = mk.panel_1h
    t = pd.Timestamp("2019-01-10")
    assert d4["open"].loc[t, "BTCUSDT"] == h["open"].loc[t + pd.Timedelta(hours=4), "BTCUSDT"]
    assert d4["close"].loc[t, "BTCUSDT"] == h["close"].loc[t + pd.Timedelta(hours=27), "BTCUSDT"]
    # kaydırılmış dolum: blok d'nin ilk iki saati = [d 04:00, d 06:00)
    fp4 = vwap_fill_prices(h, 0, 2, offset_hours=4)
    sl = slice(9 * 24 + 4, 9 * 24 + 6)
    exp = h["quote_volume"].iloc[sl, 0].sum() / h["volume"].iloc[sl, 0].sum()
    assert fp4.loc[t, "BTCUSDT"] == pytest.approx(exp, rel=1e-12)


def test_cycle_ledger_definition():
    d = pd.to_datetime(["2024-01-02", "2024-01-05", "2024-01-09", "2024-01-12", "2024-01-20", "2024-01-03"])
    fills = pd.DataFrame({
        "date": d, "asset": ["A", "A", "A", "A", "A", "B"],
        "cash_flow": [-1000.0, -500.0, 700.0, 900.0, -300.0, -200.0],
        "qty_after": [10.0, 15.0, 8.0, 0.0, 3.0, 2.0],
    }).sort_values("date", kind="stable")
    cy = build_cycles(fills, {"A": 3.0, "B": 2.0}, {"A": 110.0, "B": 90.0}, pd.Timestamp("2024-01-31"))
    a1 = cy[(cy.asset == "A") & (cy.cycle == 1)].iloc[0]
    assert a1.status == "closed" and a1.n_fills == 4 and a1.duration_days == 10
    assert a1.profit == pytest.approx(100.0) and bool(a1.win) and a1.ret == pytest.approx(100 / 1500)
    a2 = cy[(cy.asset == "A") & (cy.cycle == 2)].iloc[0]
    assert a2.status == "open" and a2.market_value == pytest.approx(330.0) and a2.profit == pytest.approx(30.0)
    b1 = cy[cy.asset == "B"].iloc[0]
    assert b1.profit == pytest.approx(-20.0) and not bool(b1.win)
