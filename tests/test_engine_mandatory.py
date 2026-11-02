"""G8 zorunlu testleri (SPEC "Zorunlu testler" 1–5). Yalnızca sentetik veri."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trend.backtest.engine import run_backtest
from trend.backtest.ledger import compare_golden, golden_bytes, golden_digest, save_golden
from trend.backtest.lookahead import compare_until, corrupt_after
from trend.backtest.synthetic import StaticUniverse, make_market, tiny_inputs
from trend.config import load_settings
from trend.strategy.benchmarks import TargetWeightStrategy
from trend.strategy.system import TrendStrategy

FIXTURES = Path(__file__).parent / "fixtures" / "engine"
START = "2020-01-01"
T_CHECKS = ["2020-02-29", "2020-06-14", "2020-09-30", "2021-01-17", "2021-05-31"]
VARIANT_OV = {
    "T0": None,
    "T1_T9": {"strategy": {"regime_filter": {"enabled": True}, "relative_strength": {"enabled": True}}},
    "tbill_fixed": {"backtest": {"cash_yield": "tbill"}},
}


@pytest.fixture(scope="module")
def market():
    return make_market(n_assets=14, n_days=1000, seed=11, n_delist=3, n_gaps=3)


def _flags(mk) -> pd.DataFrame:
    """Sentetik tarihe bağlı kalite işaretleri (bazıları t'den önce, bazıları sonra bilinir)."""
    rng = np.random.default_rng(3)
    days = mk.panel_1d["close"].index
    rows = []
    for _ in range(40):
        a = str(rng.choice(mk.assets))
        e = int(rng.integers(50, len(days) - 1))
        s = max(e - int(rng.integers(0, 60)), 0)
        rows.append((a, "zero_volume", days[s], days[e], days[e], str(rng.choice(["exclude", "flag", "error"])), ""))
    return pd.DataFrame(rows, columns=["symbol", "check", "period_start", "period_end", "known_from", "severity",
                                       "detail"])


def _rate(mk) -> pd.Series:
    days = mk.panel_1d["close"].index
    return pd.Series(np.linspace(0.01, 0.05, len(days)), index=days)


def _run(inp, ov, leak=0, assets=None, sizing="compound"):
    return run_backtest(inp["panel_1d"], panel_1h=inp["panel_1h"], universe=inp["universe"], delist=inp["delist"],
                        quality_flags=inp["quality_flags"], cash_rate=inp["cash_rate"], start=START,
                        strategy=TrendStrategy(leak_days=leak), overrides=ov, assets=assets, sizing=sizing)


def _inputs(mk):
    return dict(panel_1d=mk.panel_1d, panel_1h=mk.panel_1h, universe=mk.universe, delist=mk.delist,
                quality_flags=_flags(mk), cash_rate=_rate(mk))


# ---------------------------------------------------------------- 1. geleceği görme testi
@pytest.mark.parametrize("variant", list(VARIANT_OV))
def test_1_lookahead_corrupting_future_prices_and_meta_leaves_decisions_unchanged(market, variant):
    ov = VARIANT_OV[variant]
    inp = _inputs(market)
    sizing = "fixed" if variant == "tbill_fixed" else "compound"
    base_fixed = _run(inp, ov, assets=market.assets, sizing=sizing)
    base_auto = _run(inp, ov, sizing=sizing)
    rng = np.random.default_rng(2026)
    for t in T_CHECKS:
        bad = corrupt_after(t, rng, assets=market.assets, **inp)
        # sabit varlık kümesi: bayt düzeyinde eşitlik
        r = _run(bad, ov, assets=market.assets, sizing=sizing)
        assert compare_until(base_fixed, r, t) == [], f"t={t}"
        # motorun kendi seçtiği varlık kümesi (bozulmuş evrenle değişir) — yine birebir
        r2 = _run(bad, ov, sizing=sizing)
        assert compare_until(base_auto, r2, t) == [], f"t={t} (auto assets)"
        # bozma gerçekten etkili olmalı: t sonrası farklı
        assert compare_until(base_fixed, r, "2100-01-01") != []


def test_1b_precomputed_indicators_equal_truncated_recomputation(market):
    """Ön hesaplanan göstergelerin t satırı, veri t'de kesilerek yeniden hesaplananla aynı olmalı."""
    from trend.strategy.risk import annualized_vol
    from trend.strategy.signal import trend_signal

    cfg = load_settings()
    s = cfg["strategy"]
    close = market.panel_1d["close"]
    full = trend_signal(close, s["spans"], s["buffer_h"], s["min_signal_bars"], 30, 20)
    vol_full = annualized_vol(close, s["vol_windows"], s["vol_min_obs"], s["vol_floor"], 365)
    for t in [250, 400, 611, 999]:
        cut = close.iloc[: t + 1]
        part = trend_signal(cut, s["spans"], s["buffer_h"], s["min_signal_bars"], 30, 20)
        np.testing.assert_array_equal(part["S3"][t], full["S3"][t])
        np.testing.assert_array_equal(annualized_vol(cut, s["vol_windows"], s["vol_min_obs"], s["vol_floor"], 365)[t],
                                      vol_full[t])


# ---------------------------------------------------------------- 2. pozitif kontrol
@pytest.mark.parametrize("variant", ["T0", "T1_T9"])
def test_2_positive_control_one_day_signal_leak_is_caught(market, variant):
    ov = VARIANT_OV[variant]
    inp = _inputs(market)
    base = _run(inp, ov, leak=1, assets=market.assets)
    rng = np.random.default_rng(2026)
    caught = 0
    for t in T_CHECKS:
        bad = corrupt_after(t, rng, assets=market.assets, **inp)
        caught += bool(compare_until(base, _run(bad, ov, leak=1, assets=market.assets), t))
    assert caught == len(T_CHECKS), f"1 günlük sızıntı yalnızca {caught}/{len(T_CHECKS)} noktada yakalandı"


# ---------------------------------------------------------------- 3. elle hesap
def test_3_hand_calculation_two_coins_ten_days():
    """2 coin, 10 gün, komisyon %0,10, kayma A %0,05 / B %0,10. Hedefler (karar günü):
    g1: A 0.5, B 0.3 ; g5: A 0, B 0.6 ; g8: A 0.4 (B 0.6 aynı) → g9 alımı nakit yetmediği için orantılı küçülür."""
    cA = [100, 102, 104, 103, 105, 110, 108, 111, 115, 120]
    cB = [50, 48, 47, 49, 50, 52, 51, 53, 55, 54]
    pA = [np.nan, 101, 103, 104, 104, 106, 109, 108, 112, 116]  # dolum günü VWAP (00–02)
    pB = [np.nan, 49, 48, 47, 49, 51, 52, 51, 54, 55]
    panel, fp = tiny_inputs({"AAAUSDT": cA, "BBBUSDT": cB}, {"AAAUSDT": pA, "BBBUSDT": pB})
    days = panel["close"].index
    tw = pd.DataFrame({"AAAUSDT": [.5, .5, .5, .5, 0, 0, 0, .4, .4, .4],
                       "BBBUSDT": [.3, .3, .3, .3, .6, .6, .6, .6, .6, .6]}, index=days)
    uni = StaticUniverse([("AAAUSDT", "B", 0.5, 0.0005), ("BBBUSDT", "B", 0.5, 0.0010)])
    res = run_backtest(panel, fill_px=fp, universe=uni, strategy=TargetWeightStrategy(tw), hard_stop=False)
    c, sA, sB = 0.001, 0.0005, 0.0010

    # --- el hesabı ---
    nav, cash = [], []
    # g1: hiç pozisyon yok
    cash1 = 10000.0
    nav.append(cash1), cash.append(cash1)
    qA = 0.5 * 10000 / 100            # = 50
    qB = 0.3 * 10000 / 50             # = 60
    # g2: alımlar 101·1.0005 ve 49·1.001; komisyon işlem tutarının %0,1'i
    costA = qA * 101 * (1 + sA) * (1 + c)     # 5057.577525
    costB = qB * 49 * (1 + sB) * (1 + c)      # 2945.88294
    cash2 = 10000 - costA - costB             # 1996.539535
    assert cash2 == pytest.approx(1996.539535, rel=1e-12)
    for k in range(1, 5):                     # g2..g5 değerleme
        nav.append(cash2 + qA * cA[k] + qB * cB[k]), cash.append(cash2)
    nav5 = nav[4]                             # 10246.539535
    assert nav5 == pytest.approx(10246.539535, rel=1e-12)
    # g5 kararı: A tam çıkış (50 adet), B 0.6'ya: Δ = 0.6 − 60·50/NAV5 → adet = Δ·NAV5/50
    dqB = (0.6 - qB * cB[4] / nav5) * nav5 / cB[4]   # 62.95847442
    assert dqB == pytest.approx(62.95847442, rel=1e-9)
    # g6: önce satış 106·(1−0.0005), sonra alım 51·1.001
    proceedsA = qA * 106 * (1 - sA)
    cash6 = cash2 + proceedsA * (1 - c)
    cash6 -= dqB * 51 * (1 + sB) * (1 + c)
    qB2 = qB + dqB
    for k in (5, 6, 7):                       # g6..g8 değerleme
        nav.append(cash6 + qB2 * cB[k]), cash.append(cash6)
    nav8 = nav[7]
    # g8 kararı: A giriş 0.4 → adet 0.4·NAV8/111 ; g9 dolum 112·1.0005, maliyet nakdi aşar → orantılı küçült
    qA9 = 0.4 * nav8 / 111
    need = qA9 * 112 * (1 + sA) * (1 + c)
    assert need > cash6
    qA9 *= cash6 / need
    cash9 = 0.0
    for k in (8, 9):
        nav.append(cash9 + qA9 * cA[k] + qB2 * cB[k]), cash.append(cash9)

    np.testing.assert_allclose(res.daily["nav"].to_numpy(), nav, rtol=1e-12, atol=1e-9)
    np.testing.assert_allclose(res.daily["cash"].to_numpy(), cash, rtol=1e-12, atol=1e-9)
    f = res.fills
    assert list(f["side"]) == ["buy", "buy", "sell", "buy", "buy"]
    assert list(f["kind"]) == ["entry", "entry", "exit", "tier", "entry"]
    np.testing.assert_allclose(f["qty"].to_numpy(), [qA, qB, qA, dqB, qA9], rtol=1e-12)
    np.testing.assert_allclose(f["commission"].to_numpy()[:2], [qA * 101 * (1 + sA) * c, qB * 49 * (1 + sB) * c],
                               rtol=1e-12)
    # döngüler: A1 kapandı, B ve A2 açık
    cy = res.cycles.set_index(["asset", "cycle"])
    a1 = cy.loc[("AAAUSDT", 1)]
    assert a1["status"] == "closed" and a1["duration_days"] == 4
    assert a1["profit"] == pytest.approx(proceedsA * (1 - c) - costA, rel=1e-12)
    assert cy.loc[("BBBUSDT", 1), "status"] == "open"
    assert cy.loc[("BBBUSDT", 1), "market_value"] == pytest.approx(qB2 * 54, rel=1e-12)


# ---------------------------------------------------------------- 4. al-tut eşdeğerliği
def _zero_cost_bh(fill_mode: str, entry_above_close: bool):
    mk = make_market(n_assets=2, n_days=400, seed=21, n_late=0, n_delist=0, n_gaps=0, min_days=1)
    close = mk.panel_1d["close"][["BTCUSDT"]]
    panel = {k: v[["BTCUSDT"]] for k, v in mk.panel_1d.items()}
    tw = pd.DataFrame({"BTCUSDT": 1.0}, index=close.index)
    uni = StaticUniverse([("BTCUSDT", "A", 1.0, 0.0)])
    ov = {"backtest": {"commission": 0.0, "fill": fill_mode}}
    fp = None
    if fill_mode == "vwap_00_02":
        fp = mk.panel_1d["open"][["BTCUSDT"]] * (1.01 if entry_above_close else 0.99)
    res = run_backtest(panel, panel_1h={k: v[["BTCUSDT"]] for k, v in mk.panel_1h.items()}, fill_px=fp,
                       universe=uni, strategy=TargetWeightStrategy(tw), overrides=ov, hard_stop=False)
    return res, close["BTCUSDT"], fp


def test_4_buy_and_hold_equivalence_open_fill():
    res, c, _ = _zero_cost_bh("open_t1", True)
    assert len(res.fills) == 1  # tek alım, sonra hiç işlem yok
    entry = res.fills["price"].iloc[0]
    assert entry == pytest.approx(c.iloc[0], rel=1e-12)  # açılış = önceki kapanış
    bh = 10000.0 * c / entry
    np.testing.assert_allclose(res.nav.iloc[1:].to_numpy(), bh.iloc[1:].to_numpy(), rtol=1e-12)
    r = res.returns().iloc[2:]
    np.testing.assert_allclose(r.to_numpy(), c.pct_change().iloc[2:].to_numpy(), rtol=1e-9, atol=1e-13)


def test_4b_buy_and_hold_equivalence_vwap_fill_cash_constrained():
    """Dolum fiyatı karar kapanışının üstündeyse alım nakde göre orantılı küçülür → tüm nakit yatırılır."""
    res, c, fp = _zero_cost_bh("vwap_00_02", True)
    entry = fp["BTCUSDT"].iloc[1]
    assert res.daily["cash"].iloc[1:].max() <= 1e-9
    np.testing.assert_allclose(res.nav.iloc[1:].to_numpy(), (10000.0 * c / entry).iloc[1:].to_numpy(), rtol=1e-12)


def test_4c_entry_below_close_leaves_documented_cash_residual():
    """adet = Δw·NAV/C(t) (SPEC); dolum C(t)'nin altındaysa artık nakit kalır: NAV = artık + adet·C."""
    res, c, fp = _zero_cost_bh("vwap_00_02", False)
    q = 10000.0 / c.iloc[0]
    resid = 10000.0 - q * fp["BTCUSDT"].iloc[1]
    np.testing.assert_allclose(res.nav.iloc[1:].to_numpy(), (resid + q * c).iloc[1:].to_numpy(), rtol=1e-12)


# ---------------------------------------------------------------- 5. altın kayıt altyapısı
def test_5_golden_master_rerun_is_byte_identical(market, tmp_path):
    inp = _inputs(market)
    a = _run(inp, VARIANT_OV["T1_T9"])
    b = _run(inp, VARIANT_OV["T1_T9"])
    assert golden_bytes(a) == golden_bytes(b)
    p = tmp_path / "golden.bin"
    digest = save_golden(a, p)
    assert digest == golden_digest(b)
    ok, msg = compare_golden(b, p)
    assert ok, msg
    # bozulmuş bir karar yakalanmalı
    b.decisions.loc[b.decisions.index[len(b.decisions) // 2], "w_tgt"] += 1e-15
    ok, msg = compare_golden(b, p)
    assert not ok and "satır" in msg


def test_5b_golden_digest_independent_of_process(market):
    """Ayrı bir Python sürecinde (farklı hash tohumu) aynı özet."""
    code = ("from trend.backtest.synthetic import make_market;from trend.backtest.engine import run_backtest;"
            "from trend.backtest.ledger import golden_digest;"
            "mk=make_market(n_assets=8,n_days=700,seed=4);"
            "r=run_backtest(mk.panel_1d,panel_1h=mk.panel_1h,universe=mk.universe,delist=mk.delist,start='2019-12-01');"
            "print(golden_digest(r))")
    env = dict(os.environ, PYTHONHASHSEED="12345")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    mk = make_market(n_assets=8, n_days=700, seed=4)
    r = run_backtest(mk.panel_1d, panel_1h=mk.panel_1h, universe=mk.universe, delist=mk.delist, start="2019-12-01")
    assert out.stdout.strip() == golden_digest(r)


def test_5c_recorded_golden_fixture_if_present():
    """G12'de kaydedilecek gerçek altın kayıt için yer tutucu: sentetik fikstür varsa birebir karşılaştır.
    Kayıt: TREND_RECORD_GOLDEN=1 pytest tests/test_engine_mandatory.py -k fixture"""
    p = FIXTURES / "golden_synthetic.bin"
    mk = make_market(n_assets=8, n_days=700, seed=4)
    r = run_backtest(mk.panel_1d, panel_1h=mk.panel_1h, universe=mk.universe, delist=mk.delist, start="2019-12-01")
    if os.environ.get("TREND_RECORD_GOLDEN") == "1":
        FIXTURES.mkdir(parents=True, exist_ok=True)
        save_golden(r, p)
    if not p.exists():
        pytest.skip("altın kayıt fikstürü yok (G12'de kaydedilir)")
    ok, msg = compare_golden(r, p)
    assert ok, msg
