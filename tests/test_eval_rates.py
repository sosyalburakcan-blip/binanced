"""rates.py: FRED ayrıştırma, 7/24 takvim + ileri taşıma (geleceği görme yok), günlük oran, nakit getirisi."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trend.evaluation import rates

FIX = Path(__file__).parent / "fixtures" / "eval" / "dtb3_sample.csv"


def _tbill():
    df = rates.parse_fred_csv(FIX.read_text())
    return df.set_index("date")["tbill_3m_pct"].dropna()


def test_parse_fred_handles_blank_and_dot():
    df = rates.parse_fred_csv(FIX.read_text())
    assert list(df.columns) == ["date", "tbill_3m_pct"]
    assert df.loc[df["date"] == "2024-01-15", "tbill_3m_pct"].isna().all()
    assert df.loc[df["date"] == "2024-01-17", "tbill_3m_pct"].isna().all()
    assert df["tbill_3m_pct"].notna().sum() == 12


def test_parse_old_fred_header():
    df = rates.parse_fred_csv("DATE,DTB3\n2020-01-02,1.5\n2020-01-03,.\n")
    assert df["tbill_3m_pct"].iloc[0] == 1.5 and np.isnan(df["tbill_3m_pct"].iloc[1])


def test_daily_calendar_forward_fill_with_lag():
    idx = pd.date_range("2024-01-01", "2024-01-21", freq="D")
    s = rates.daily_tbill_pct(idx, _tbill(), lag_days=1)
    assert len(s) == len(idx)
    assert np.isnan(s["2024-01-01"]) and np.isnan(s["2024-01-02"])  # ilk gözlem 01-03'te bilinir
    assert s["2024-01-03"] == 5.20
    assert s["2024-01-06"] == 5.23 and s["2024-01-07"] == 5.23 and s["2024-01-08"] == 5.23  # hafta sonu
    assert s["2024-01-09"] == 5.24
    assert s["2024-01-16"] == 5.28 and s["2024-01-17"] == 5.30  # tatil (01-15 boş)
    assert s["2024-01-18"] == 5.30  # 01-17 "." → taşınır
    assert s["2024-01-19"] == 1.00 and s["2024-01-21"] == 1.20


def test_lag_zero_uses_same_day():
    idx = pd.date_range("2024-01-02", "2024-01-05", freq="D")
    s = rates.daily_tbill_pct(idx, _tbill(), lag_days=0)
    assert s.tolist() == [5.20, 5.21, 5.22, 5.23]


def test_no_lookahead_truncation_invariance():
    tb = _tbill()
    idx = pd.date_range("2024-01-01", "2024-01-25", freq="D")
    full = rates.daily_tbill_pct(idx, tb, max_stale_days=None)
    cut = pd.Timestamp("2024-01-10")
    trunc = rates.daily_tbill_pct(idx, tb[tb.index <= cut], max_stale_days=None)
    known = idx[idx <= cut + pd.Timedelta(days=1)]
    pd.testing.assert_series_equal(full[known], trunc[known])


def test_stale_values_become_nan():
    idx = pd.date_range("2024-01-20", "2024-02-15", freq="D")
    s = rates.daily_tbill_pct(idx, _tbill(), lag_days=1, max_stale_days=10)
    assert s["2024-01-30"] == 1.20  # son gözlem 01-19, bilinir 01-20; 10 gün
    assert np.isnan(s["2024-01-31"])


def test_pct_to_daily_and_rf():
    assert rates.pct_to_daily(3.65, 365) == pytest.approx(0.0001)
    idx = pd.date_range("2024-01-04", "2024-01-06", freq="D")
    rf = rates.rf_daily(idx, _tbill())
    assert rf.iloc[0] == pytest.approx(5.21 / 100 / 365)


def test_cash_yield_modes():
    tb = pd.Series([1.0, 1.5, 4.0])
    assert rates.cash_yield_pct(tb, "zero").tolist() == [0.0, 0.0, 0.0]
    assert rates.cash_yield_pct(tb, "tbill_minus_1_5").tolist() == pytest.approx([0.0, 0.0, 2.5])
    assert rates.cash_yield_pct(tb, "tbill").tolist() == [1.0, 1.5, 4.0]
    with pytest.raises(ValueError):
        rates.cash_yield_pct(tb, "bogus")
    idx = pd.date_range("2024-01-04", "2024-01-06", freq="D")
    assert (rates.cash_yield_daily(idx, "zero", _tbill()) == 0).all()  # settings varsayılanı: zero
    assert (rates.cash_yield_daily(idx) == 0).all()
    cy = rates.cash_yield_daily(idx, "tbill_minus_1_5", _tbill())
    assert cy.iloc[0] == pytest.approx((5.21 - 1.5) / 100 / 365)


def test_download_offline_roundtrip(tmp_path, monkeypatch):
    class Resp:
        text = FIX.read_text()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(rates.requests, "get", lambda url, timeout: Resp())
    dest = tmp_path / "tbill_3m.csv"
    rates.download_tbill(dest)
    s = rates.load_tbill(dest)
    assert len(s) == 12 and s.iloc[0] == 5.20
    assert rates.tbill_downloaded_at(dest).endswith("Z")
    assert pd.read_csv(dest).columns.tolist() == ["date", "tbill_3m_pct", "downloaded_at_utc"]


def test_committed_meta_file_loads_if_present():
    p = rates.tbill_path()
    if not p.exists():
        pytest.skip("meta/tbill_3m.csv yok")
    s = rates.load_tbill(p)
    assert s.index.is_monotonic_increasing and s.between(-1, 25).all()
    assert s.index[0] <= pd.Timestamp("2017-08-01")


@pytest.mark.network
def test_download_fred_network(tmp_path):
    dest = tmp_path / "tbill_3m.csv"
    df = rates.download_tbill(dest, start="2024-01-01")
    assert df["tbill_3m_pct"].notna().sum() > 100
    s = rates.load_tbill(dest)
    assert s.between(0, 20).all()
