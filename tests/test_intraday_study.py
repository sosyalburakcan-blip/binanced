"""Araştırma v4 hattının sentetik piyasada uçtan uca duman testi (gerçek fiyat verisi kullanmaz)."""

import copy

import numpy as np
import pandas as pd
import pytest

from trend.intraday import study
from trend.intraday.sim import Market

START, HOLD, END = "2019-07-01", "2020-01-01", "2020-03-31"


def _market(seed, assets, t15, funding=False):
    rng = np.random.default_rng(seed)
    n = len(t15)
    r = rng.standard_normal((n, len(assets))) * 0.004 + 0.00002
    c = 100 * np.exp(np.cumsum(r, axis=0))
    o = np.vstack([c[:1], c[:-1]])
    h = np.maximum(o, c) * (1 + np.abs(rng.standard_normal(c.shape)) * 0.001)
    lo = np.minimum(o, c) * (1 - np.abs(rng.standard_normal(c.shape)) * 0.001)
    f = None
    if funding:
        f = np.zeros_like(c)
        f[(t15.hour % 8 == 0) & (t15.minute == 0)] = 0.0001
    return Market(assets=assets, t15=t15, o=o.astype(np.float32), h=h.astype(np.float32), l=lo.astype(np.float32),
                  c=c.astype(np.float32), funding=None if f is None else f.astype(np.float32))


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("v4")
    v4 = copy.deepcopy(study.load_v4())
    v4.update(design=[START, "2019-12-31"], holdout_start=HOLD, end=END)
    v4["grid"] = {"lookback_h": [3, 6], "z_entry": [1.0], "confirm_h": [1], "tp": [0.02], "sl": [0.02],
                  "max_hold_h": [24]}
    v4["leverage"] = [2]
    v4["controls"] = {"top_k": 1, "n_random": 3, "random_grids": 1}
    v4["evaluation"]["toplist_size"] = 2
    t15 = pd.date_range(pd.Timestamp(START) - pd.Timedelta(days=14), pd.Timestamp(END) + pd.Timedelta(hours=23, minutes=45),
                        freq="15min")
    assets = ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"]
    elig = np.ones((len(t15) // 4, len(assets)), dtype=bool)
    slip = np.full(elig.shape, 0.0005, dtype=np.float32)
    mk = {"spot": _market(1, assets, t15), "futures": _market(1, assets, t15, funding=True)}
    study.set_out(tmp / "backtests")
    return v4, mk, elig, slip, tmp


def test_grid_and_names_are_unique():
    v4 = study.load_v4()
    names = [study.cfg_name(p) for p in study.grid(v4)]
    assert len(names) == len(set(names)) == 648
    assert [v[0] for v in study.venues(v4)] == ["spot", "fut1x", "fut2x", "fut3x", "fut5x"]


def test_pipeline_end_to_end(setup, monkeypatch):
    v4, mk, elig, slip, tmp = setup
    timing = study.run_pipeline(v4, lambda m: mk[m], elig, slip, workers=2)
    # 2 yapılandırma × 2 piyasa + kontroller (6 + 3 rastgele) + 1 rastgele ızgara (2)
    assert len(timing) == 4 + 9 + 2
    assert (tmp / "backtests" / "spot" / "L3_z1_k1_tp2_sl2_h24.parquet").exists()
    monkeypatch.setattr(study, "btc200_ret", lambda per: pd.Series(0.0, index=pd.date_range(per[0], per[1])))
    res = study.analyze(v4)
    assert [c[0] for c in res["criteria"]] == list(range(1, 9))
    assert set(res["leverage"].columns) == {"spot", "fut2x"}
    assert len(res["toplist"]) == 2
    out = study.write_report(res, v4, None, out_dir=tmp)
    t = out.read_text(encoding="utf-8")
    assert "En iyi liste" in t and "Kaldıraç ve spot farkı" in t and "vergi duyarlılığı" in t
    assert list(res["tax_table"].columns)[:2] == ["temel", "BNB indirimi"]


def test_after_tax_growth_taxes_only_positive_years():
    idx = pd.date_range("2020-01-01", "2022-12-31", freq="D")
    nav = pd.Series(1.0, index=idx)
    nav[idx.year == 2020] = np.linspace(1.0, 1.5, (idx.year == 2020).sum())
    nav[idx.year == 2021] = np.linspace(1.5, 0.75, (idx.year == 2021).sum())
    nav[idx.year == 2022] = np.linspace(0.75, 1.5, (idx.year == 2022).sum())
    g = study.after_tax_growth(nav, 0.15)
    assert np.isclose(g, (1 + 0.5 * 0.85) * 0.5 * (1 + 1.0 * 0.85))
    assert np.isclose(study.after_tax_growth(nav, 0.0), 1.5)
