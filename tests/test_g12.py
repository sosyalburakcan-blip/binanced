"""G12 kilit hattı: anlık görüntü özeti, tek seferlik koruma, tam dönem analizi, nedensellik ve altın kayıt
(sentetik veri; gerçek veriyle altın kayıt testi tests/test_golden_master.py)."""

import io
import json

import numpy as np
import pandas as pd
import pytest

from trend.backtest.fills import fill_prices_from_settings, open_fill_prices
from trend.backtest.synthetic import make_market
from trend.config import load_settings
from trend.research import g10, g12
from trend.research.inputs import ResearchInputs, hourly_end_time
from trend.research.runner import PanelSet, RunSpec, run_dir, run_one, save_result

LOCK = "2020-03-31"
DEV_END = "2019-12-31"


def _cfg(tmp):
    return load_settings({
        "periods": {"data_start": "2018-06-01", "development": ["2019-07-01", DEV_END],
                    "validation_start": "2020-01-01",
                    "regimes": [["2019-07-01", "2019-10-31"], ["2019-11-01", None]]},
        "paths": {"backtests": str(tmp / "backtests"), "reports": str(tmp / "reports")},
    })


def _inputs(cfg, mk, stage, end):
    end = pd.Timestamp(end)
    days = pd.date_range("2018-06-01", periods=670, freq="D")
    tb = pd.Series(2.0, index=days)
    h = {k: v.loc[: hourly_end_time(end, max(cfg["backtest"]["t8_close_hours"]))] for k, v in mk.panel_1h.items()}
    p1d = {k: v.loc[:end] for k, v in mk.panel_1d.items()}
    fp = {}
    for m in ("vwap_00_02", "vwap_06_07", "vwap_14_15"):
        c = {**cfg, "backtest": {**cfg["backtest"], "fill": m}}
        fp[m] = fill_prices_from_settings(c, p1d, mk.panel_1h)
    fp["open_t1"] = open_fill_prices(p1d)
    unis = {k: mk.universe for k in ("main", "size_30", "size_50", "usdt_only")}
    flags = pd.DataFrame(columns=["symbol", "check", "period_start", "period_end", "known_from", "severity", "detail"])
    return ResearchInputs(cfg=cfg, stage=stage, start=pd.Timestamp("2019-07-01"), end=end, assets=list(mk.assets),
                          panel_1d=p1d, universes=unis, delist=mk.delist, flags=flags, tbill_pct=tb.loc[:end],
                          rf=(tb / 100 / 365).loc[:end], fill_px=fp, hourly=h)


@pytest.fixture(scope="module")
def market():
    cfg = load_settings({"periods": {"data_start": "2018-06-01"}})
    return make_market(n_assets=10, n_days=670, start="2018-06-01", seed=11, cfg=cfg, min_days=200)


@pytest.fixture(scope="module")
def full(tmp_path_factory, market):
    tmp = tmp_path_factory.mktemp("g12")
    cfg = _cfg(tmp)
    (tmp / "reports").mkdir()
    return _inputs(cfg, market, "full", LOCK)


def test_full_stage_is_causal_dev_part_identical(full, market):
    dev = _inputs(full.cfg, market, "development", DEV_END)
    specs = [RunSpec("T0"), RunSpec("B_btc200", kind="btc_200"), RunSpec("C_lag3", leak_days=-3)] + [
        s for s in g10.variant_specs() if s.name in ("T1", "T9", "T8_h04")]
    pd_, pf = g10.build_panels(dev, specs, verbose=False), g10.build_panels(full, specs, verbose=False)
    for spec in specs:
        a = run_one(spec, dev, pd_).daily["ret"]
        b = run_one(spec, full, pf).daily["ret"]
        assert b.index[-1] == pd.Timestamp(LOCK)
        assert np.array_equal(a.to_numpy(), b.loc[a.index].to_numpy()), spec.name


def test_analyze_g12_and_report(full):
    specs = g10.all_specs(full.cfg, 1)
    panels = g10.build_panels(full, specs, verbose=False)
    for s in specs:
        save_result(run_dir(full, s.name), s, run_one(s, full, panels), 0.0)
    for s in g10.phase2_specs(full):
        save_result(run_dir(full, s.name), s, run_one(s, full, panels), 0.0)
    dev_sum = {"pbo": 0.4, "null_p": {"a": 0.01, "b": 0.02}, "controls_ok": 11, "controls_n": 11}
    root = g10.cfg_path(full.cfg, "backtests") / "full"
    res = g12.analyze_g12(full, n_seeds=1, verbose=False, dev_root=root, dev_sum=dev_sum)
    assert {"validation", "full"} <= set(res["periods"])
    assert res["periods"]["validation"] == (pd.Timestamp("2020-01-01"), pd.Timestamp(LOCK))
    assert (res["consistency"]["max_abs_diff"] == 0).all()
    crit = g12.criteria(res)
    assert [c[0] for c in crit] == list(range(1, 10))
    assert crit[2][4] is True and crit[4][4] is True and crit[7][4] is True   # geliştirme değerleri dev_sum'dan
    lk = {"lock_date": LOCK, "n_files": 3, "bytes": 10, "data_manifest_sha256": "x", "hashes": {}}
    out = g12.write_report(full, res, lk, {"started_utc": "a", "finished_utc": "b", "n_runs": 1, "code_commit": "c"},
                           None)
    t = out.read_text(encoding="utf-8")
    assert "Geç/kal kararı" in t and "Düşüş ufku tablosu" in t and "Doğrulama dönemi" in t
    summ = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    assert set(summ["criteria"]) == {str(k) for k in range(1, 10)}


def _snapshot_cfg(tmp):
    for d in ("merged/1d", "merged/1h", "meta", "universe"):
        (tmp / d).mkdir(parents=True, exist_ok=True)
    t = pd.date_range("2020-01-01", "2020-01-05", freq="D")
    pd.DataFrame({"open_time": t, "close": 1.0}).to_parquet(tmp / "merged/1d/A.parquet")
    th = pd.date_range("2020-01-01", "2020-01-05 23:00", freq="h")
    pd.DataFrame({"open_time": th, "close": 1.0}).to_parquet(tmp / "merged/1h/A.parquet")
    pd.DataFrame({"x": [1]}).to_parquet(tmp / "flags.parquet")
    (tmp / "meta/m.csv").write_text("a\n1\n", encoding="utf-8")
    (tmp / "universe/2020-01.csv").write_text("symbol\nA\n", encoding="utf-8")
    (tmp / "ledger.csv").write_text("f,sha\n", encoding="utf-8")
    return load_settings({"paths": {"merged": str(tmp / "merged"), "quality_flags": str(tmp / "flags.parquet"),
                                    "meta": str(tmp / "meta"), "universe": str(tmp / "universe"),
                                    "ledger": str(tmp / "ledger.csv"), "backtests": str(tmp / "backtests")}})


def test_snapshot_verify_and_once_only_guard(tmp_path):
    cfg = _snapshot_cfg(tmp_path)
    with pytest.raises(SystemExit):
        g12.snapshot(cfg, "2020-01-06")          # veri kilit gününü kapsamıyor
    rec = g12.snapshot(cfg, "2020-01-05")
    assert rec["n_files"] == 6 and len(rec["data_manifest_sha256"]) == 64
    with pytest.raises(SystemExit):
        g12.snapshot(cfg, "2020-01-05")          # kilit iki kez açılmaz
    assert g12.verify_snapshot(cfg)["ok"]
    (tmp_path / "meta/m.csv").write_text("a\n2\n", encoding="utf-8")
    v = g12.verify_snapshot(cfg)
    assert not v["ok"] and v["changed"] == [g12._rel(tmp_path / "meta/m.csv")]
    (g12.lock_dir(cfg) / "G12_run.json").write_text(json.dumps({"started_utc": "x"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="zaten yapıldı"):
        g12.run_batch(cfg)


def test_golden_tables_roundtrip_and_detect_change(full, tmp_path):
    r = run_one(RunSpec("T0"), full, {"real": PanelSet(full.panel_1d, full.fill_px, full.delist)})
    tabs = g12.golden_tables(r)
    assert len(tabs["decisions"]) > 0 and len(tabs["fills"]) > 0
    for k, df in tabs.items():
        b = g12.canonical_csv(df)
        p1, p2 = tmp_path / f"{k}1.csv.gz", tmp_path / f"{k}2.csv.gz"
        g12._gzip_write(p1, b)
        g12._gzip_write(p2, b)
        assert p1.read_bytes() == p2.read_bytes()            # gzip belirlenimci (mtime = 0)
        old = pd.read_csv(p1, compression="gzip")
        assert g12.compare_tables(old, pd.read_csv(io.BytesIO(b)))["ok"]
    dec = pd.read_csv(io.BytesIO(g12.canonical_csv(tabs["decisions"])))
    bad = dec.copy()
    bad.loc[bad.index[0], "w_tgt"] = bad["w_tgt"].iloc[0] + 1e-6
    assert g12.compare_tables(dec, bad)["bad_columns"] == ["w_tgt"]
    bad = dec.copy()
    bad.loc[bad.index[0], "reason"] = "x"
    assert not g12.compare_tables(dec, bad)["ok"]
