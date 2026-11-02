"""metrics.py: bilinen cevaplı sentetik örnekler."""

import numpy as np
import pandas as pd
import pytest

from trend.evaluation import metrics as M
from trend.evaluation.report import to_markdown


def _idx(n, start="2020-01-01"):
    return pd.date_range(start, periods=n, freq="D")


def _ret_from_nav(navs, start="2020-01-01"):
    nav = pd.Series(navs, index=_idx(len(navs), start), dtype=float)
    return nav.pct_change().iloc[1:]


def test_annual_return_and_vol_known():
    r = pd.Series(0.001, index=_idx(730))
    assert M.annual_return(r, 365) == pytest.approx(1.001**365 - 1)
    alt = pd.Series(np.tile([0.01, -0.01], 500), index=_idx(1000))
    assert M.annual_volatility(alt, 365) == pytest.approx(alt.std(ddof=1) * np.sqrt(365))
    assert alt.std(ddof=1) == pytest.approx(0.01, rel=1e-3)


def test_sharpe_with_rf_series_and_sortino():
    r = pd.Series([0.011, -0.019, 0.031, -0.009], index=_idx(4))
    rf = pd.Series(0.001, index=_idx(4))
    ex = np.array([0.01, -0.02, 0.03, -0.01])
    assert M.sharpe_ratio(r, rf, 365) == pytest.approx(ex.mean() / ex.std(ddof=1) * np.sqrt(365))
    down = np.sqrt((0.02**2 + 0.01**2) / 4)
    assert M.sortino_ratio(r, rf, 365) == pytest.approx(ex.mean() / down * np.sqrt(365))
    with pytest.raises(ValueError):
        M.sharpe_ratio(r, rf.iloc[:2], 365)  # rf eksik → hata


def test_drawdown_peak_trough_recovery_duration():
    r = _ret_from_nav([100, 110, 99, 88, 110, 121, 100])
    info = M.max_drawdown_info(r)
    assert info["max_drawdown"] == pytest.approx(88 / 110 - 1)
    assert info["mdd_peak"] == pd.Timestamp("2020-01-02")
    assert info["mdd_trough"] == pd.Timestamp("2020-01-04")
    assert info["mdd_recovery"] == pd.Timestamp("2020-01-05")
    assert info["mdd_duration_days"] == 2
    uw = M.underwater_info(r)
    assert uw["time_under_water_frac"] == pytest.approx(3 / 6)
    assert uw["longest_underwater_days"] == 2 and uw["current_underwater_days"] == 1
    assert M.calmar_ratio(r, 365) == pytest.approx(M.annual_return(r, 365) / 0.2)


def test_drawdown_first_day_loss_counts_and_unrecovered():
    r = _ret_from_nav([100, 90, 95, 80])
    info = M.max_drawdown_info(r)
    assert info["max_drawdown"] == pytest.approx(-0.2)
    assert info["mdd_peak"] == pd.Timestamp("2020-01-01")  # dönem başı değeri
    assert pd.isna(info["mdd_recovery"]) and info["mdd_duration_days"] == 3


def test_yearly_returns_and_rolling_sharpe():
    r = pd.Series(0.001, index=pd.date_range("2020-12-30", periods=5, freq="D"))
    y = M.yearly_returns(r)
    assert y.loc[2020, "return"] == pytest.approx(1.001**2 - 1) and y.loc[2021, "n_days"] == 3
    rng = np.random.default_rng(1)
    r2 = pd.Series(rng.normal(0.001, 0.02, 800), index=_idx(800))
    rs = M.rolling_sharpe(r2, 0.0, window=365, ppy=365)
    assert rs.iloc[:364].isna().all()
    w = r2.iloc[400 - 364 : 401]
    assert rs.iloc[400] == pytest.approx(w.mean() / w.std(ddof=1) * np.sqrt(365))


def _ledger():
    return pd.DataFrame({
        "asset": ["A", "A", "B", "B", "C", "C", "D", "D", "E", "E"],
        "open_date": pd.to_datetime(["2020-01-01", "2020-02-01", "2020-01-05", "2020-03-01", "2020-01-10",
                                     "2020-02-10", "2020-01-15", "2020-03-15", "2020-01-20", "2020-04-01"]),
        "close_date": pd.to_datetime(["2020-01-11", "2020-02-21", "2020-01-08", "2020-03-31", "2020-01-30",
                                      "2020-02-12", "2020-01-16", "2020-04-14", "2020-02-29", None]),
        "profit": [100.0, -50.0, 30.0, -20.0, 200.0, 10.0, -5.0, 0.0, 60.0, 40.0],
        "is_open": [False] * 9 + [True],
    })


def test_cycle_stats_known():
    st = M.cycle_stats(_ledger())
    assert st["n_cycles"] == 10 and st["n_open_cycles"] == 1
    assert st["win_rate"] == pytest.approx(0.6)  # 0 kâr kaybeden sayılır
    assert st["avg_win"] == pytest.approx((100 + 30 + 200 + 10 + 60 + 40) / 6)
    assert st["avg_loss"] == pytest.approx((-50 - 20 - 5 + 0) / 4)
    assert st["top10pct_profit_share"] == pytest.approx(200 / 365)
    # coin toplamları: A 50, B 10, C 210, D -5, E 100
    assert st["n_coins_traded"] == 5 and st["n_profitable_coins"] == 4
    ht = M.holding_time_table(_ledger())
    # kazanan kapanmış: A1 10, B1 3, C1 20, C2 2, E1 40 (E2 açık → hariç)
    assert ht.loc["winners", "n"] == 5 and ht.loc["winners", "median"] == 10
    assert ht.loc["winners", "p10"] == pytest.approx(np.quantile([10, 3, 20, 2, 40], 0.1))
    # kaybeden: A2 20, B2 30, D1 1, D2 30
    assert ht.loc["losers", "median"] == pytest.approx(25)
    assert st["hold_p90_losers"] == pytest.approx(np.quantile([20, 30, 1, 30], 0.9))


def test_worst_loss_at_max_exposure_scaling():
    n = 10
    idx = _idx(n)
    r = pd.Series(0.0, index=idx)
    r.iloc[5] = -0.20  # %50 maruziyet, riskli kısım −%40
    nav = 100 * (1 + r).cumprod()
    # gün içi maruziyet 0,5 → gün sonu nakit = 0,5·NAV(t−1)
    cash = nav.shift(1).fillna(100) * 0.5
    daily = pd.DataFrame({"nav": nav, "cash": cash}, index=idx)
    g0 = M.intraday_exposure(daily, r)
    assert g0.to_numpy() == pytest.approx(0.5)
    t = M.worst_losses_at_max_exposure(daily, r, windows=(1, 3), max_exposure=1.0, top=2)
    one = t[t.window_days == 1].iloc[0]
    assert one["end"] == idx[5] and one["loss_at_max_exposure"] == pytest.approx(-0.40)
    assert one["actual_return"] == pytest.approx(-0.20)
    three = t[t.window_days == 3]
    assert three.iloc[0]["loss_at_max_exposure"] == pytest.approx(-0.40)
    assert len(three) == 2 and abs(idx.get_loc(three.iloc[1]["end"]) - idx.get_loc(three.iloc[0]["end"])) >= 3


def test_cash_drag_and_turnover_cost():
    idx = _idx(4, "2020-12-30")
    cs = pd.Series(0.5, index=idx)
    assert M.cash_drag(cs, pd.Series(0.0001, index=idx), 365) == pytest.approx(0.5 * 0.0001 * 365)
    daily = pd.DataFrame({"nav": [100.0, 100.0, 200.0, 200.0], "turnover": [1.0, 0.5, 0.2, 0.0],
                          "cost": [0.1, 0.1, 0.2, 0.0]}, index=idx)
    cf = M.cost_fraction(daily)
    assert cf.iloc[0] == pytest.approx(0.1 / 100.1) and cf.iloc[2] == pytest.approx(0.2 / 100)
    tc = M.turnover_cost_by_year(daily, cf)
    assert tc.loc[2020, "turnover"] == 1.5 and tc.loc[2021, "turnover"] == pytest.approx(0.2)


def test_periods_from_settings():
    p = M.periods_from_settings(stage="development")
    assert p["development"] == (pd.Timestamp("2019-07-01"), pd.Timestamp("2023-12-31"))
    assert p["regime_2019-07_2021-11"] == (pd.Timestamp("2019-07-01"), pd.Timestamp("2021-11-30"))
    assert p["regime_2022-01_end"] == (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31"))
    assert "validation" not in p
    with pytest.raises(ValueError):
        M.periods_from_settings(stage="full")
    f = M.periods_from_settings(stage="full", lock_date="2026-12-31")
    assert f["validation"] == (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-12-31"))
    assert f["full"][0] == pd.Timestamp("2019-07-01") and f["regime_2022-01_end"][1] == pd.Timestamp("2026-12-31")


def _synthetic_engine(n=900, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-06-01", periods=n, freq="D")
    g = np.clip(0.4 + 0.1 * np.sin(np.arange(n) / 50), 0, 1)
    r = g * rng.normal(0.002, 0.04, n)
    r[0] = 0.0
    nav = 10000 * np.cumprod(1 + r)
    cash = nav * (1 - g) / (1 + r) * 1.0  # gün sonu nakit tutarlı yaklaşık
    daily = pd.DataFrame({"nav": nav, "cash": cash, "gross_exposure": 1 - cash / nav,
                          "turnover": rng.uniform(0, 0.05, n), "cost": nav * 1e-5}, index=idx)
    return daily


def test_compute_metrics_integration_and_periods():
    daily = _synthetic_engine()
    rf = pd.Series(0.03 / 365, index=daily.index)
    led = _ledger().assign(open_date=lambda d: d.open_date + pd.DateOffset(years=0))
    res = M.compute_metrics(daily, led, rf, rf, start="2019-07-01", end="2020-06-30")
    sc = res["scalars"]
    r = daily["nav"].pct_change().loc["2019-07-01":"2020-06-30"]
    assert sc["n_days"] == len(r) and sc["start"] == pd.Timestamp("2019-07-01")
    assert sc["annual_return"] == pytest.approx(M.annual_return(r, 365))
    assert sc["sharpe"] == pytest.approx(M.sharpe_ratio(r, rf, 365))
    assert sc["vol_minus_target"] == pytest.approx(sc["annual_vol"] - 0.35)
    assert sc["avg_cash_share"] + sc["avg_gross_exposure"] == pytest.approx(1.0)
    assert sc["n_cycles"] == 10 and np.isfinite(sc["cash_drag_annual"])
    assert np.isfinite(sc["worst_1d_at_max_exposure"]) and sc["worst_1d_at_max_exposure"] <= sc["worst_1d_actual"]
    assert set(res["tables"]) >= {"yearly", "rolling_sharpe_12m", "exposure_monthly", "worst_losses"}
    periods = M.periods_from_settings(stage="development")
    table, tabs = M.evaluate_periods(daily, {k: v for k, v in periods.items() if k != "regime_2022-01_end"},
                                     rf_daily=rf, tbill_daily=rf)
    assert list(table.columns) == ["development", "regime_2019-07_2021-11"]
    md = to_markdown(table.loc[["sharpe", "annual_return", "max_drawdown"]])
    assert "| sharpe |" in md and "%" in md
