"""Araştırma v2 hattının sentetik piyasada uçtan uca duman testi (gerçek veri kullanmaz)."""

import copy

import pandas as pd
import pytest

from trend.alt import study
from trend.alt.registry import families, load_v2
from trend.backtest.fills import fill_prices_from_settings, open_fill_prices
from trend.backtest.synthetic import make_market
from trend.config import ROOT, load_settings
from trend.research import g10
from trend.research.inputs import ResearchInputs
from trend.research.runner import run_dir, run_one, save_result

END = "2020-03-31"


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("v2")
    cfg = load_settings({
        "periods": {"data_start": "2018-06-01", "development": ["2019-07-01", "2019-12-31"],
                    "regimes": [["2019-07-01", "2019-10-31"], ["2019-11-01", None]]},
        "paths": {"backtests": str(tmp / "backtests"), "reports": str(tmp / "reports")},
    })
    (tmp / "reports").mkdir()
    mk = make_market(n_assets=10, n_days=670, start="2018-06-01", seed=11, cfg=cfg, min_days=200)
    end = pd.Timestamp(END)
    p1d = {k: v.loc[:end] for k, v in mk.panel_1d.items()}
    fp = {"vwap_00_02": fill_prices_from_settings(cfg, p1d, mk.panel_1h), "open_t1": open_fill_prices(p1d)}
    days = pd.date_range("2018-06-01", end, freq="D")
    tb = pd.Series(2.0, index=days)
    flags = pd.DataFrame(columns=["symbol", "check", "period_start", "period_end", "known_from", "severity", "detail"])
    inp = ResearchInputs(cfg=cfg, stage="full", start=pd.Timestamp("2019-07-01"), end=end, assets=list(mk.assets),
                         panel_1d=p1d, universes={k: mk.universe for k in ("main", "size_30", "size_50", "usdt_only")},
                         delist=mk.delist, flags=flags, tbill_pct=tb, rf=tb / 100 / 365, fill_px=fp)
    v2 = copy.deepcopy(load_v2())
    v2.update(design=["2019-07-01", "2019-12-31"], holdout_start="2020-01-01", lock_date=END)
    v2["evaluation"]["n_control_seeds"] = 1
    return inp, v2


def test_registry_covers_preregistered_families():
    v2 = load_v2()
    assert set(v2["families"]) <= set(families())
    names = [s.name for s in study.candidate_specs(v2)]
    assert len(names) == len(set(names)) == 27
    assert "XS_REV_lookback3" in names and "VM_BTC_sigma_target0.35" in names


def test_v2_pipeline_end_to_end(setup):
    inp, v2 = setup
    specs = study.all_specs(v2)
    assert len({s.name for s in specs}) == len(specs)
    panels = g10.build_panels(inp, specs, verbose=False)
    for s in specs:
        save_result(run_dir(inp, s.name), s, run_one(s, inp, panels), 0.0)
    res = study.analyze(inp, v2, verbose=False)
    assert set(res["families"]) == set(v2["families"])
    for f, r in res["families"].items():
        assert [c[0] for c in r["criteria"]] == list(range(1, 8))
        assert study.decision(r) in ("gölge mod adayı", "uydu dilimi adayı", "reddedildi")
    out = study.write_report(inp, res, None)
    t = out.read_text(encoding="utf-8")
    assert "## Sonuç" in t and "XS_REV" in t and "RV_ETHBTC" in t


def _v3(setup_v2):
    v3 = copy.deepcopy(load_v2(ROOT / "research_v3.yaml"))
    v3.update(design=setup_v2["design"], holdout_start=setup_v2["holdout_start"], lock_date=END)
    v3["evaluation"]["n_control_seeds"] = 1
    return v3


def test_v3_config_registry_and_controls():
    v3 = load_v2(ROOT / "research_v3.yaml")
    assert set(v3["families"]) <= set(families())
    names = [s.name for s in study.candidate_specs(v3)]
    assert len(names) == len(set(names)) == 13
    ctl = {s.name: s for s in study.control_specs(v3)}
    assert ctl["TS_W_leak7"].leak_days == 7 and ctl["TS_D_leak1"].leak_days == 1 and ctl["XS_MOM_leak7"]
    assert not study.is_xsec("TS_D") and study.is_xsec("XS_MOM")
    assert study.meta(v3, "report") == "V3_short_trend.md" and study.meta(load_v2(), "tag") == "v2"


def test_v3_pipeline_end_to_end(setup):
    inp, v2 = setup
    v3 = _v3(v2)
    specs = study.all_specs(v3)
    panels = g10.build_panels(inp, specs, verbose=False)
    for s in specs:
        save_result(run_dir(inp, s.name), s, run_one(s, inp, panels), 0.0)
    res = study.analyze(inp, v3, verbose=False)
    assert set(res["families"]) == {"TS_D", "TS_W", "XS_MOM"}
    assert res["dsr_n"]["prior"] == 62 and res["dsr_n"]["this"] == 13
    out = study.write_report(inp, res, None, v3)
    assert out.name == "V3_short_trend.md"
    t = out.read_text(encoding="utf-8")
    assert "kısa vadeli trend" in t and "7 gün sızıntı" in t
