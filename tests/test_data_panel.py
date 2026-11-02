"""Panel yükleyici birim testi (CONTRACTS §7): hizalama, NaN, ileri taşıma yok, tarih süzgeci."""

import numpy as np
import pandas as pd
import pytest

from trend.config import load_settings
from trend.data import panel
from trend.data.clean import CLEAN_COLS


def _frame(days, close0):
    t = pd.DatetimeIndex(days)
    n = len(t)
    return pd.DataFrame({"open_time": t, "open": close0 + np.arange(n), "high": close0 + np.arange(n) + 1,
                         "low": close0 + np.arange(n) - 1, "close": close0 + np.arange(n), "volume": 1.0,
                         "close_time": t + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1),
                         "quote_volume": 2.0, "number_of_trades": np.int64(5), "taker_buy_base": 0.5,
                         "taker_buy_quote": 1.0, "half_day": False})[CLEAN_COLS]


@pytest.fixture
def cfg(tmp_path):
    d = tmp_path / "clean" / "1d"
    d.mkdir(parents=True)
    _frame(pd.date_range("2024-01-01", periods=5), 10.0).to_parquet(d / "AAAUSDT.parquet", index=False)
    # BBB: 01-03 ve 01-05 eksik (boşluk) ve 01-06'ya uzanıyor
    _frame(["2024-01-02", "2024-01-04", "2024-01-06"], 100.0).to_parquet(d / "BBBUSDT.parquet", index=False)
    pd.DataFrame({"x": [1]}).to_parquet(d / "_meta.parquet")  # "_" ile başlayan dosyalar yok sayılır
    return load_settings({"paths": {"clean": str(tmp_path / "clean")}})


def test_load_panel_alignment_no_ffill(cfg):
    p = panel.load_panel("1d", source="clean", cfg=cfg)
    assert set(p) == {"open", "high", "low", "close", "volume", "quote_volume", "trades"}
    c = p["close"]
    assert list(c.columns) == ["AAAUSDT", "BBBUSDT"]
    assert isinstance(c.index, pd.DatetimeIndex) and c.index.tz is None and c.index.is_monotonic_increasing
    assert list(c.index) == list(pd.date_range("2024-01-01", "2024-01-06"))
    assert np.isnan(c.loc["2024-01-03", "BBBUSDT"])  # taşınmaz
    assert np.isnan(c.loc["2024-01-06", "AAAUSDT"])
    assert c.loc["2024-01-04", "BBBUSDT"] == 101.0
    assert p["trades"].dtypes.eq("float64").all() and p["trades"].loc["2024-01-01", "AAAUSDT"] == 5


def test_load_panel_subset_and_dates(cfg):
    p = panel.load_panel("1d", symbols=["BBBUSDT"], source="clean", start="2024-01-03", end="2024-01-05", cfg=cfg)
    assert list(p["close"].columns) == ["BBBUSDT"]
    assert list(p["close"].index) == [pd.Timestamp("2024-01-04")]


def test_load_panel_errors(cfg):
    with pytest.raises(FileNotFoundError):
        panel.load_panel("1d", symbols=["ZZZUSDT"], source="clean", cfg=cfg)
    with pytest.raises(ValueError):
        panel.load_panel("1d", source="raw", cfg=cfg)
