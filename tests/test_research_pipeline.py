"""G10–G11 hattının sentetik piyasada uçtan uca duman testi (gerçek veri kullanmaz)."""

import numpy as np
import pandas as pd
import pytest

from trend.backtest.fills import fill_prices_from_settings, open_fill_prices
from trend.backtest.synthetic import make_market
from trend.config import load_settings
from trend.research import controls as C
from trend.research import g10
from trend.research.inputs import ResearchInputs, map_announcements
from trend.research.runner import RunSpec, flat_overrides, is_cached, run_many, run_one, save_result, run_dir


@pytest.fixture(scope="module")
def inp(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("research")
    cfg = load_settings({
        "periods": {"data_start": "2018-06-01", "development": ["2019-07-01", "2020-03-31"],
                    "regimes": [["2019-07-01", "2019-11-30"], ["2020-01-01", None]]},
        "paths": {"backtests": str(tmp / "backtests"), "reports": str(tmp / "reports")},
    })
    (tmp / "reports").mkdir()
    mk = make_market(n_assets=10, n_days=670, start="2018-06-01", seed=11, cfg=cfg, min_days=200)
    days = pd.date_range("2018-06-01", periods=670, freq="D")
    tb = pd.Series(2.0, index=days)
    fp = {}
    for m in ("vwap_00_02", "vwap_06_07", "vwap_14_15"):
        c = {**cfg, "backtest": {**cfg["backtest"], "fill": m}}
        fp[m] = fill_prices_from_settings(c, mk.panel_1d, mk.panel_1h)
    fp["open_t1"] = open_fill_prices(mk.panel_1d)
    end = pd.Timestamp("2020-03-31")
    p1d = {k: v.loc[:end] for k, v in mk.panel_1d.items()}
    unis = {k: mk.universe for k in ("main", "size_30", "size_50", "usdt_only")}
    flags = pd.DataFrame(columns=["symbol", "check", "period_start", "period_end", "known_from", "severity", "detail"])
    return ResearchInputs(cfg=cfg, stage="development", start=pd.Timestamp("2019-07-01"), end=end,
                          assets=list(mk.assets), panel_1d=p1d, universes=unis, delist=mk.delist, flags=flags,
                          tbill_pct=tb, rf=tb / 100 / 365, fill_px=fp, hourly=mk.panel_1h)


def test_specs_cover_preregistered_runs(inp):
    names = [s.name for s in g10.all_specs(inp.cfg, 2)]
    assert len(names) == len(set(names))
    grid = [s.name for s in g10.grid_specs(inp.cfg)]
    assert len(grid) == 10 and "G_h0" in grid and "G_span0.8" in grid
    var = {s.name for s in g10.variant_specs()}
    assert {"T1", "T3", "T5_20", "T6_cost2", "T6_loss20", "T6_loss50", "T7", "T9", "T8_h04", "T8_wd0"} <= var
    t6 = next(s for s in g10.variant_specs() if s.name == "T6_loss50")
    assert t6.exchange_loss == (("2022-11-08", 0.5),)
    assert next(s for s in g10.grid_specs(inp.cfg) if s.name == "G_span1.2").override_dict() == {
        "strategy": {"spans": (24, 60, 120)}}


def test_flat_overrides_roundtrip():
    d = {"strategy": {"rebalance": {"drift_rel": 0.15}, "spans": [1, 2]}, "backtest": {"fill": "open_t1"}}
    spec = RunSpec("x", overrides=flat_overrides(d))
    assert spec.override_dict() == {"strategy": {"rebalance": {"drift_rel": 0.15}, "spans": (1, 2)},
                                    "backtest": {"fill": "open_t1"}}


def test_map_announcements_uses_segment_covering_announcement():
    seg = pd.DataFrame({"asset_id": ["LUNAUSDT_until_20220513", "LUNAUSDT"], "source_symbol": ["LUNAUSDT"] * 2,
                        "start": ["2020-08-21", "2022-05-31"], "end": ["2022-05-13", "2026-11-01"], "ratio": [1, 1]})
    ann = pd.DataFrame({"symbol": ["LUNAUSDT"], "announced_utc": ["2022-05-13 00:40"], "delist_utc": ["x"],
                        "kind": ["delist"], "source": ["s"]})
    assert map_announcements(ann, seg)["symbol"].tolist() == ["LUNAUSDT_until_20220513"]


def test_control_panels_keep_availability_and_destroy_order(inp):
    close = inp.panel_1d["close"]
    rng = np.random.default_rng(0)
    sh = C.shuffled_panel(close, rng)["close"]
    assert (sh.notna() == close.notna()).all().all()
    ga = C.garch_panel(close, rng)["close"]
    assert (ga.notna() == close.notna()).all().all()
    a = close["BTCUSDT"].dropna()
    assert np.isclose(sh["BTCUSDT"].dropna().iloc[0], a.iloc[0])
    assert not np.allclose(sh["BTCUSDT"].dropna().to_numpy(), a.to_numpy())


def test_full_pipeline_runs_and_writes_reports(inp):
    specs = g10.all_specs(inp.cfg, 1)
    panels = g10.build_panels(inp, specs, verbose=False)
    for s in specs:
        res = run_one(s, inp, panels)
        save_result(run_dir(inp, s.name), s, res, 0.0)
    for s in g10.phase2_specs(inp):
        save_result(run_dir(inp, s.name), s, run_one(s, inp, panels), 0.0)
    assert is_cached(inp, specs[0])
    res = g10.analyze(inp, n_seeds=1, verbose=False)
    assert 0.0 <= res["pbo"]["pbo"] <= 1.0
    assert res["dsr"]["n_trials_used"] >= 100
    assert set(res["nulls"]) == {"a_tarih_karistirma", "b_rastgele_coin"}
    assert len(res["controls"]) == 11
    p10, p11 = g10.write_reports(inp, res)
    t = p11.read_text(encoding="utf-8")
    assert "PBO" in t and "Geç/kal" in t
    assert "Sıfır hipotezleri" in p10.read_text(encoding="utf-8")


def test_run_many_parallel_and_cache(inp):
    specs = [RunSpec("P_T0"), RunSpec("P_btc200", kind="btc_200")]
    panels = {"real": g10.PanelSet(inp.panel_1d, inp.fill_px, inp.delist)}
    t = run_many(specs, inp, panels, workers=2, verbose=False)
    assert set(t) == {"P_T0", "P_btc200"}
    assert run_many(specs, inp, panels, workers=2, verbose=False) == {}
