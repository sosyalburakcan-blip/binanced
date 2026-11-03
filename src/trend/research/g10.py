"""G10–G11: geliştirme dönemi değerlendirmesi ve sağlamlık (yalnızca 2019-07 – 2023-12).

    python -m trend.research.g10 run      # tüm çalıştırmalar (önbellekli, paralel)
    python -m trend.research.g10 report   # reports/G10_development.md ve reports/G11_robustness.md
    python -m trend.research.g10 all

Doğrulama dönemi (2024-01 sonrası) bu modülde hiçbir şekilde yüklenmez (inputs.stage="development").
Ön kayıt: PREREGISTRATION.md (tag prereg-v1). Kontrol eşikleri ve ızgara yorumu: experiments.md satır 10.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time

import numpy as np
import pandas as pd

from trend.backtest.engine import resolve_settings
from trend.backtest.fills import daily_from_hourly, open_fill_prices, vwap_fill_prices
from trend.backtest.variants import T6_EXCHANGE_LOSS_DATE, variant_runs
from trend.config import load_settings, path as cfg_path
from trend.evaluation import bootstrap as bs
from trend.evaluation.common import sharpe
from trend.evaluation.dsr import deflated_sharpe_ratio, n_trials_for_dsr
from trend.evaluation.metrics import compute_metrics, periods_from_settings
from trend.evaluation.mintrl import min_track_record_from_returns
from trend.evaluation.nulls import null_date_shuffle, null_p_value, null_random_coin, percentile_rank, run_null
from trend.evaluation.pbo import pbo_cscv
from trend.evaluation.regression import factor_regression, up_down_beta
from trend.evaluation.report import to_markdown
from trend.evaluation.satellite import satellite_from_returns
from trend.research import controls as C
from trend.research.inputs import HOURLY_T8_FIELDS, ResearchInputs, hourly_end_time, load_fields, load_inputs
from trend.research.runner import PanelSet, RunSpec, flat_overrides, load_run, run_many
from trend.strategy.benchmarks import core_satellite

_S = load_settings()
N_CONTROL_SEEDS = 5          # karıştırma ve GARCH panelleri için tohum sayısı (her biri tam bir backtest)
OTHER_COIN_RUNS = 200
CONTROL_SEED = int(_S["evaluation"]["null_seed"])
GRID_BASE = {"target_vol": float(_S["strategy"]["target_vol"]), "span_scale": 1.0, "universe_size": 20,
             "drift_rel": float(_S["strategy"]["rebalance"]["drift_rel"]),
             "buffer_h": float(_S["strategy"]["buffer_h"])}
KEY_METRICS = ["annual_return", "annual_vol", "vol_minus_target", "avg_gross_exposure", "avg_cash_share", "sharpe",
               "sortino", "calmar", "max_drawdown", "mdd_peak", "mdd_trough", "mdd_duration_days",
               "longest_underwater_days", "time_under_water_frac", "skewness",
               "turnover_annual", "cost_annual", "n_cycles", "win_rate", "avg_win", "avg_loss",
               "top10pct_profit_share", "n_profitable_coins", "n_coins_traded", "worst_1d_at_max_exposure",
               "worst_3d_at_max_exposure"]


# ---------------------------------------------------------------------------------------------------------------
# Çalıştırma tanımları


def grid_specs(cfg: dict) -> list[RunSpec]:
    """Temel ayar (T0) + tek eksenli komşular (experiments.md satır 10)."""
    g = cfg["evaluation"]["grid"]
    spans = [int(s) for s in cfg["strategy"]["spans"]]
    out = []
    for v in g["target_vol"]:
        if v != GRID_BASE["target_vol"]:
            out.append(RunSpec(f"G_vol{round(v * 100)}", overrides=(("strategy.target_vol", v),)))
    for v in g["span_scale"]:
        if v != GRID_BASE["span_scale"]:
            out.append(RunSpec(f"G_span{v:g}", overrides=(("strategy.spans", tuple(round(s * v) for s in spans)),)))
    for v in g["universe_size"]:
        if v != GRID_BASE["universe_size"]:
            out.append(RunSpec(f"G_univ{v}", universe=f"size_{v}"))
    for v in g["drift_rel"]:
        if v != GRID_BASE["drift_rel"]:
            out.append(RunSpec(f"G_drift{round(v * 100)}", overrides=(("strategy.rebalance.drift_rel", v),)))
    for v in g["buffer_h"]:
        if v != GRID_BASE["buffer_h"]:
            out.append(RunSpec(f"G_h{v:g}", overrides=(("strategy.buffer_h", v),)))
    return out


def variant_specs() -> list[RunSpec]:
    out = []
    for vr in variant_runs():
        if vr.code == "T0":
            continue
        kw: dict = {"overrides": flat_overrides(vr.overrides)}
        p = vr.params
        if "exchange_loss_frac" in p:
            kw["exchange_loss"] = ((str(T6_EXCHANGE_LOSS_DATE.date()), float(p["exchange_loss_frac"])),)
        if p.get("usdt_only"):
            kw["universe"] = "usdt_only"
        if "close_hour" in p:
            kw["panel"] = f"h{int(p['close_hour']):02d}"
        out.append(RunSpec(vr.code, **kw))
    return out


def benchmark_specs() -> list[RunSpec]:
    return [
        RunSpec("B_btc200", kind="btc_200"),
        RunSpec("B_btceth200", kind="btc_eth_200"),
        RunSpec("B_btchold", kind="btc_hold"),
        RunSpec("B_btc5050", kind="btc_hold", weight=0.5),
        RunSpec("B_univew", kind="universe_ew"),
        RunSpec("B_trendew", kind="trend_equal"),
    ]


def sensitivity_specs() -> list[RunSpec]:
    out = []
    for mode, tag in (("tbill_minus_1_5", "m15"), ("tbill", "tb")):
        out.append(RunSpec(f"T0_cash_{tag}", overrides=(("backtest.cash_yield", mode),)))
        out.append(RunSpec(f"B_btc200_cash_{tag}", kind="btc_200", overrides=(("backtest.cash_yield", mode),)))
    out.append(RunSpec("T0_fixed", sizing="fixed"))
    return out


def control_specs(n_seeds: int = N_CONTROL_SEEDS) -> list[RunSpec]:
    out = [RunSpec("C_lag1", leak_days=-1), RunSpec("C_lag3", leak_days=-3), RunSpec("C_lag365", leak_days=-365),
           RunSpec("C_inverse", kind="inverse"), RunSpec("C_leak1", leak_days=1, note="pozitif kontrol")]
    o = (("backtest.fill", "open_t1"),)
    out += [RunSpec(f"C_shuffle{k}", panel=f"shuffle{k}", overrides=o) for k in range(n_seeds)]
    out += [RunSpec(f"C_garch{k}", panel=f"garch{k}", overrides=o) for k in range(n_seeds)]
    return out


def diagnostic_specs(n_seeds: int = N_CONTROL_SEEDS) -> list[RunSpec]:
    """Ön kayıt dışı tanılar (experiments.md'ye yazılır, N'ye eklenir; seçim için kullanılmaz)."""
    o = (("backtest.fill", "open_t1"),)
    return ([RunSpec("D_T0_nostop", hard_stop=False, note="sert sınır kapalı (tanı)")]
            + [RunSpec(f"D_shuffledm{k}", panel=f"shuffledm{k}", overrides=o) for k in range(n_seeds)])


def all_specs(cfg: dict, n_seeds: int = N_CONTROL_SEEDS) -> list[RunSpec]:
    return ([RunSpec("T0", note="temel ayar")] + benchmark_specs() + grid_specs(cfg) + variant_specs()
            + sensitivity_specs() + control_specs(n_seeds) + diagnostic_specs(n_seeds))


# ---------------------------------------------------------------------------------------------------------------
# Paneller


def _relabel_delist(delist: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    d = delist.copy()
    end = close.index[-1]
    for k in range(len(d)):
        a, ld = str(d.iloc[k]["asset"]), d.iloc[k]["last_day"]
        if a in close.columns and pd.notna(ld) and ld <= end:
            lv = close[a].last_valid_index()
            if lv is not None:
                d.iloc[k, d.columns.get_loc("last_day")] = lv
    return d


def build_panels(inp: ResearchInputs, specs: list[RunSpec], verbose: bool = True) -> dict[str, PanelSet]:
    log = print if verbose else (lambda *a, **k: None)
    panels = {"real": PanelSet(inp.panel_1d, inp.fill_px, inp.delist)}
    need = sorted({s.panel for s in specs} - {"real"})
    hours = sorted({int(p[1:]) for p in need if p.startswith("h")})
    for H in hours:
        h1 = (inp.hourly if inp.hourly is not None
              else load_fields("1h", inp.assets, HOURLY_T8_FIELDS, hourly_end_time(inp.end, H), inp.cfg))
        p1d = daily_from_hourly(h1, H)
        p1d = {k: v.loc[: inp.end] for k, v in p1d.items()}
        h0, h_1 = inp.cfg["backtest"]["fill_windows"]["vwap_00_02"]
        fp = vwap_fill_prices(h1, int(h0), int(h_1), offset_hours=H)
        panels[f"h{H:02d}"] = PanelSet(p1d, {"vwap_00_02": fp}, _relabel_delist(inp.delist, p1d["close"]))
        del h1
        log(f"[paneller] T8 h{H:02d} hazır")
    close = inp.panel_1d["close"]
    fits = None
    for p in need:
        if p.startswith("shuffledm"):
            rng = np.random.default_rng(CONTROL_SEED + 400 + int(p[9:]))
            pan = C.shuffled_panel(close, rng, demean=True)
        elif p.startswith("shuffle"):
            rng = np.random.default_rng(CONTROL_SEED + 100 + int(p[7:]))
            pan = C.shuffled_panel(close, rng)
        elif p.startswith("garch"):
            if fits is None:
                t0 = time.perf_counter()
                fits = C.garch_fits(close)
                log(f"[paneller] GARCH uydurma: {len(fits)} coin, {time.perf_counter() - t0:.0f}s")
            rng = np.random.default_rng(CONTROL_SEED + 200 + int(p[5:]))
            pan = C.garch_panel(close, rng, fits)
        else:
            continue
        panels[p] = PanelSet(pan, {"open_t1": open_fill_prices(pan)}, inp.delist)
    return panels


def phase2_specs(inp: ResearchInputs) -> list[RunSpec]:
    """Stratejinin oynaklığına ölçeklenmiş BTC al-tut: ağırlık = σ(T0) / σ(BTC al-tut), en fazla 1 (geliştirme
    döneminin gerçekleşen oynaklıkları; kıyas olduğu için dönem sonu bilgisi kullanılır, raporda belirtilir)."""
    t0, bh = load_run(inp, "T0").ret, load_run(inp, "B_btchold").ret
    w = float(min(1.0, t0.std() / bh.std()))
    return [RunSpec("B_btcvol", kind="btc_hold", weight=round(w, 6), note="T0 oynaklığına ölçekli")]


# ---------------------------------------------------------------------------------------------------------------
# Analiz yardımcıları


def _spec(run) -> RunSpec:
    s = dict(run.spec["spec"])
    s["overrides"] = tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in s["overrides"])
    s["exchange_loss"] = tuple(tuple(x) for x in s["exchange_loss"])
    if "params" in s:
        s["params"] = tuple(tuple(x) for x in s["params"])
    return RunSpec(**s)


def metrics_table(inp: ResearchInputs, names: list[str], period: tuple, keys=KEY_METRICS) -> pd.DataFrame:
    cols = {}
    for n in names:
        r = load_run(inp, n)
        cfg = resolve_settings(inp.cfg, _spec(r).override_dict())
        m = compute_metrics(r.daily, r.cycles, inp.rf, inp.rf, period[0], period[1], r.weights, cfg)["scalars"]
        cols[n] = {k: m.get(k, np.nan) for k in keys}
    df = pd.DataFrame(cols)
    df.index.name = "metrik"
    return df


def period_ret(inp, name: str, period: tuple) -> pd.Series:
    return load_run(inp, name).ret.loc[period[0]: period[1]]


def sr(inp, name: str, period: tuple) -> float:
    r = period_ret(inp, name, period)
    return sharpe(r - inp.rf.reindex(r.index).fillna(0.0), 365)


def git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=cfg_path(_S, "reports").parent).stdout.strip()
    except OSError:
        return "?"


def n_experiments(cfg: dict) -> int:
    """experiments.md'de N'ye eklenen satır sayısı (son sütun 'Evet' ile başlayanlar)."""
    rows = [ln for ln in cfg_path(cfg, "experiments").read_text(encoding="utf-8").splitlines()
            if ln.startswith("| ") and not ln.startswith("| #") and not ln.startswith("| ---")]
    return sum(1 for ln in rows if ln.rstrip(" |").split("|")[-1].strip().startswith("Evet"))


def _fmt(x, nd=2, pct=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x * 100:.{nd - 1 if nd > 1 else 1}f}%" if pct else f"{x:.{nd}f}"


# ---------------------------------------------------------------------------------------------------------------
# Rapor


def analyze(inp: ResearchInputs, n_seeds: int = N_CONTROL_SEEDS, verbose: bool = True,
            focus: str = "development") -> dict:
    """Tüm istatistikler `focus` döneminde (G10–G11: geliştirme; G12: tam dönem). Metrik tabloları her dönem için."""
    log = print if verbose else (lambda *a, **k: None)
    cfg = inp.cfg
    periods = periods_from_settings(cfg, inp.stage, inp.end if inp.stage == "full" else None)
    per = periods[focus]
    reg_names = [k for k in periods if k.startswith("regime")]
    out: dict = {"periods": periods}

    # --- metrik tabloları (T0 ve kıyaslar) ---
    core = ["T0", "B_btc200", "B_btceth200", "B_btchold", "B_btcvol", "B_btc5050", "B_univew", "B_trendew"]
    out["core"] = {p: metrics_table(inp, core, periods[p]) for p in periods}
    t0 = load_run(inp, "T0")
    t0_cfg = resolve_settings(cfg, {})
    out["t0_full"] = compute_metrics(t0.daily, t0.cycles, inp.rf, inp.rf, per[0], per[1], t0.weights, t0_cfg)
    btc200_full = load_run(inp, "B_btc200")
    out["b200_full"] = compute_metrics(btc200_full.daily, btc200_full.cycles, inp.rf, inp.rf, per[0], per[1],
                                       btc200_full.weights, t0_cfg)

    # --- nakit getirisi duyarlılığı, sabit tutar ---
    sens = ["T0", "T0_cash_m15", "T0_cash_tb", "B_btc200", "B_btc200_cash_m15", "B_btc200_cash_tb", "T0_fixed"]
    out["sens"] = metrics_table(inp, sens, per, ["annual_return", "annual_return_simple", "sharpe", "max_drawdown",
                                                 "avg_cash_share", "cash_drag_annual"])

    # --- dolar cinsinden (USDCUSDT'nin tersi vekil) ---
    out["usd"] = usd_table(inp, ["T0", "B_btc200"], per)

    # --- regresyon ---
    r0, rb, rew = (period_ret(inp, n, per) for n in ("T0", "B_btchold", "B_univew"))
    out["factor"] = factor_regression(r0, rb, rew, inp.rf)
    out["updown"] = up_down_beta(r0, rb, inp.rf)

    # --- sıfır hipotezleri (basitleştirilmiş getiri) ---
    log("[analiz] sıfır hipotezleri")
    close = inp.panel_1d["close"]
    rets_all = C.asset_returns(close)
    w_end = t0.weights.loc[per[0]: per[1]]
    mem = C.membership(inp.universes["main"], w_end.index, list(close.columns))
    rets = rets_all.reindex(index=w_end.index)
    w_hold = C.hold_weights(w_end, rets[w_end.columns])
    cyc = t0.cycles.copy()
    cyc = cyc[pd.to_datetime(cyc["open_date"]) >= w_end.index[0]]
    cost = C.simple_cost_rate(cfg)
    avail = rets.notna() | close.reindex(w_end.index).notna()
    obs = C.simple_stats(w_hold, rets, cost, inp.rf)
    nulls = {}
    for key, gen in (("a_tarih_karistirma", lambda rng: null_date_shuffle(cyc, w_hold, mem, rng, avail)[0]),
                     ("b_rastgele_coin", lambda rng: null_random_coin(cyc, w_hold, mem, rng, avail)[0])):
        t1 = time.perf_counter()
        res = run_null(gen, lambda w: C.simple_stats(w, rets, cost, inp.rf), cfg=cfg)
        nulls[key] = {"p_sharpe": null_p_value(obs[0], res[:, 0]), "null_mean": float(np.nanmean(res[:, 0])),
                      "null_q95": float(np.nanquantile(res[:, 0], 0.95)),
                      "mdd_pct_rank": percentile_rank(obs[1], res[:, 1]), "null_mdd_median": float(np.nanmedian(res[:, 1])),
                      "n": int(res.shape[0])}
        log(f"[analiz] sıfır {key}: {time.perf_counter() - t1:.0f}s")
    out["nulls"], out["simple_obs"] = nulls, obs

    # --- kontroller ---
    log("[analiz] kontroller")
    s_t0 = sr(inp, "T0", per)
    s_t3 = sr(inp, "T3", per)
    ctl = []

    def shuffle_like(prefix, label):
        s = [sr(inp, f"{prefix}{k}", per) for k in range(n_seeds)]
        a = [compute_metrics(load_run(inp, f"{prefix}{k}").daily, None, inp.rf, None, per[0], per[1])["scalars"]
             for k in range(n_seeds)]
        ann = float(np.mean([x["annual_return"] for x in a]))
        costa = float(np.mean([x.get("cost_annual", np.nan) for x in a]))
        ok = ann < 0 and float(np.mean(s)) <= 0
        ctl.append((label, "Avantaj kaybolur (maliyet kadar zarar)",
                    f"Sharpe ort. {np.mean(s):.2f} (aralık {min(s):.2f}…{max(s):.2f}), yıllık getiri ort. "
                    f"{ann * 100:.1f}%, yıllık maliyet ort. {costa * 100:.1f}%; kıyas T3 Sharpe {s_t3:.2f}", ok))

    shuffle_like("C_shuffle", f"Getiriler tarihe göre birlikte karıştırıldı ({n_seeds} tohum)")
    shuffle_like("C_garch", f"Oynaklığı eşleştirilmiş GARCH serileri ({n_seeds} tohum)")
    rng = np.random.default_rng(CONTROL_SEED + 300)
    oc = C.other_coin_control(w_hold, rets, cost, inp.rf, rng, OTHER_COIN_RUNS)
    med = float(np.nanmedian(oc[:, 0]))
    ok = (med < 0.5 * obs[0]) if obs[0] > 0 else None
    ctl.append(("Bir coinin sinyali başka coinin getirisine", "Avantaj büyük ölçüde kaybolur",
                f"{OTHER_COIN_RUNS} eşleme medyan Sharpe {med:.2f} (gözlenen, basit hesap {obs[0]:.2f})", ok))
    s365 = sr(inp, "C_lag365", per)
    ctl.append(("Sinyal 365 gün gecikmeli", "Avantaj kaybolur", f"Sharpe {s365:.2f} (T0 {s_t0:.2f})",
                (s365 <= 0.5 * s_t0) if s_t0 > 0 else None))
    inv = bs.paired_sharpe_test(period_ret(inp, "T0", per), period_ret(inp, "C_inverse", per), inp.rf, cfg=cfg)
    ctl.append(("Orijinal − ters sinyal", "Anlamlı ölçüde sıfırın üzerinde",
                f"ΔSharpe {inv['sharpe_diff']:.2f}, %95 GA {inv['ci95_diff'][0]:.2f}…{inv['ci95_diff'][1]:.2f}, "
                f"p = {inv['p_value']:.4f} (ters sinyal Sharpe {inv['sharpe_benchmark']:.2f})", inv["passed"]))
    for lag in (1, 3):
        s_l = sr(inp, f"C_lag{lag}", per)
        ctl.append((f"Kararlar {lag} gün gecikmeli (sinyal gecikmesi)", "Biraz bozulur, çökmez",
                    f"Sharpe {s_l:.2f} (T0 {s_t0:.2f})", (s_l >= 0.5 * s_t0) if s_t0 > 0 else None))
    t8 = {n: sr(inp, n, per) for n in [s.name for s in variant_specs() if s.name.startswith("T8")]}
    ctl.append(("Mum zamanlaması değişir (T8, 5 saat + 6 giriş günü)", "Benzer sonuç",
                f"Sharpe aralığı {min(t8.values()):.2f}…{max(t8.values()):.2f} (T0 {s_t0:.2f})",
                (min(t8.values()) >= 0.5 * s_t0) if s_t0 > 0 else None))
    dy = C.drop_year_sharpes(period_ret(inp, "T0", per), inp.rf)
    ctl.append(("Bir yıl çıkarılır", "Sonuç tek bir yıla bağlı olmamalı",
                "Sharpe: " + ", ".join(f"{y}: {v:.2f}" for y, v in dy["sharpe"].items()), bool((dy["sharpe"] > 0).all())))
    w5 = C.remove_top_cycles(w_hold, cyc, 5)
    s5 = C.simple_stats(w5, rets, cost, inp.rf)[0]
    ctl.append(("En iyi 5 döngü çıkarılır", "Sıfıra yakın veya pozitif",
                f"Sharpe (basit hesap) {s5:.2f}, tüm döngülerle {obs[0]:.2f}", bool(s5 >= -0.10)))
    s_leak = sr(inp, "C_leak1", per)
    ctl.append(("Pozitif kontrol: sinyale 1 gün sızıntı", "Sharpe belirgin yükselir (yakalanmalı)",
                f"Sharpe {s_leak:.2f} (T0 {s_t0:.2f})", bool(s_leak >= s_t0 + 1.0)))
    out["controls"], out["drop_year"], out["other_coin"] = ctl, dy, oc

    # --- ızgara, PBO ---
    log("[analiz] ızgara, PBO, DSR, bootstrap")
    grid = ["T0"] + [s.name for s in grid_specs(cfg)]
    gt = metrics_table(inp, grid, per, ["sharpe", "annual_return", "annual_vol", "max_drawdown", "turnover_annual"])
    gt.loc["sharpe_vs_base"] = gt.loc["sharpe"] / gt.loc["sharpe", "T0"]
    out["grid"] = gt
    out["grid_regimes"] = pd.DataFrame({p: {n: sr(inp, n, periods[p]) for n in grid} for p in reg_names})
    trials = pd.concat({n: period_ret(inp, n, per) - inp.rf.reindex(period_ret(inp, n, per).index).fillna(0.0)
                        for n in grid}, axis=1).dropna()
    out["pbo"] = pbo_cscv(trials.to_numpy())

    # --- varyantlar ---
    var = [s.name for s in variant_specs()]
    out["variants"] = metrics_table(inp, ["T0"] + var, per, ["sharpe", "annual_return", "max_drawdown",
                                                             "avg_gross_exposure", "cost_annual"])
    out["variants_regimes"] = pd.DataFrame({p: {n: sr(inp, n, periods[p]) for n in ["T0"] + var} for p in reg_names})
    nav0, navb = load_run(inp, "T0").daily["nav"], load_run(inp, "B_btc200").daily["nav"]
    t10 = {}
    for wc in cfg["evaluation"]["core_satellite_core_weights"]:
        nav = core_satellite(navb.loc[per[0]: per[1]], nav0.loc[per[0]: per[1]], float(wc))
        r = nav.pct_change().dropna()
        t10[f"T10_core{round(wc * 100)}"] = {"sharpe": sharpe(r - inp.rf.reindex(r.index).fillna(0.0), 365),
                                             "annual_return": float(nav.iloc[-1] ** (365 / len(r)) - 1),
                                             "max_drawdown": float((nav / nav.cummax() - 1).min())}
    out["t10"] = pd.DataFrame(t10)

    # --- DSR ---
    n_exp = n_experiments(cfg)
    n_var = len(var) + len(t10)
    trial_sr = np.array([out["grid"].loc["sharpe", n] for n in grid] + [out["variants"].loc["sharpe", n] for n in var]
                        + [t10[k]["sharpe"] for k in t10])
    n_trials = n_trials_for_dsr(n_exp, len(grid), n_var, cfg)
    out["dsr"] = deflated_sharpe_ratio(period_ret(inp, "T0", per), n_trials, trial_sharpes_annual=trial_sr,
                                       rf=inp.rf, cfg=cfg)
    out["dsr"].update(n_experiments=n_exp, grid_size=len(grid), n_variants=n_var)

    # --- bootstrap ---
    r_t0, r_b200 = period_ret(inp, "T0", per), period_ret(inp, "B_btc200", per)
    out["boot_sr"] = bs.bootstrap_sharpe(r_t0, inp.rf, cfg=cfg)
    out["paired"] = bs.paired_sharpe_test(r_t0, r_b200, inp.rf, cfg=cfg)
    out["paired_regimes"] = {p: bs.paired_sharpe_test(period_ret(inp, "T0", periods[p]),
                                                      period_ret(inp, "B_btc200", periods[p]), inp.rf, cfg=cfg)
                             for p in reg_names}
    out["mdd_vs_ew"] = bs.paired_drawdown_comparison(r_t0, period_ret(inp, "B_univew", per), cfg=cfg)
    out["dd_horizon"] = bs.drawdown_horizon_table(r_t0, cfg=cfg)
    out["mintrl"] = min_track_record_from_returns(r_t0, inp.rf)
    out["satellite"] = satellite_from_returns(r_t0, r_b200, inp.rf, cfg)

    # --- T6 başabaş yıllık kayıp olasılığı ---
    ex0 = np.log1p(r_t0) - np.log1p(inp.rf.reindex(r_t0.index).fillna(0.0))
    exb = np.log1p(r_b200) - np.log1p(inp.rf.reindex(r_b200.index).fillna(0.0))
    g0, gb = float(ex0.mean() * 365), float(exb.mean() * 365)
    out["t6_breakeven"] = {f"L{round(L * 100)}": {"p_zero": g0 / -np.log1p(-L) if g0 > 0 else 0.0,
                                                   "p_btc200": (g0 - gb) / -np.log1p(-L) if g0 > gb else 0.0}
                           for L in cfg["backtest"]["stress"]["exchange_losses"]}
    out["t6_breakeven"]["log_excess"] = {"t0": g0, "btc200": gb}

    # --- ön kayıt dışı tanılar ---
    stops = {}
    for s in all_specs(cfg, n_seeds) + phase2_specs(inp):
        d = load_run(inp, s.name).daily.loc[per[0]: per[1]]
        hs = d["hard_stop"]
        stops[s.name] = {"stop_days": int(hs.sum()), "first_stop": hs[hs > 0].index.min(),
                         "stopped_at_end": bool(hs.iloc[-1] > 0), "max_drawdown": float(d["drawdown"].min())}
    out["stops"] = pd.DataFrame(stops).T
    out["nostop"] = pd.DataFrame({p: {n: sr(inp, n, periods[p]) for n in ("T0", "D_T0_nostop")} for p in periods})
    out["nostop_metrics"] = metrics_table(inp, ["T0", "D_T0_nostop"], per, ["annual_return", "sharpe", "max_drawdown",
                                                                           "avg_gross_exposure"])
    dm = [sr(inp, f"D_shuffledm{k}", per) for k in range(n_seeds)]
    dma = [compute_metrics(load_run(inp, f"D_shuffledm{k}").daily, None, inp.rf, None, per[0], per[1])["scalars"]
           for k in range(n_seeds)]
    out["shuffle_dm"] = {"sharpe_mean": float(np.mean(dm)), "sharpe_min": float(min(dm)), "sharpe_max": float(max(dm)),
                         "ann_mean": float(np.mean([x["annual_return"] for x in dma])),
                         "cost_mean": float(np.mean([x["cost_annual"] for x in dma]))}

    # --- yatırımcı çıtası ---
    tb = inp.tbill_pct.loc[per[0]: per[1]]
    out["tbill_mean"] = float(tb.mean() / 100.0)
    return out


def usd_table(inp: ResearchInputs, names: list[str], period: tuple) -> pd.DataFrame | None:
    p = cfg_path(inp.cfg, "merged") / "1d" / "USDCUSDT.parquet"
    if not p.exists():
        return None
    u = pd.read_parquet(p, columns=["open_time", "close"]).set_index("open_time")["close"]
    u.index = pd.DatetimeIndex(u.index).as_unit("ns")
    usd_per_usdt = (1.0 / u).loc[: inp.end]
    rows = {}
    for n in names:
        nav = load_run(inp, n).daily["nav"].loc[period[0]: period[1]]
        conv = usd_per_usdt.reindex(nav.index).ffill()
        nav_usd = (nav * conv).dropna()
        r = nav_usd.pct_change().dropna()
        rows[n] = {"annual_return_usd": float((nav_usd.iloc[-1] / nav_usd.iloc[0]) ** (365 / len(r)) - 1),
                   "sharpe_usd": sharpe(r - inp.rf.reindex(r.index).fillna(0.0), 365),
                   "usdt_usd_min": float(conv.min()), "usdt_usd_max": float(conv.max())}
    return pd.DataFrame(rows)


def _ok(x) -> str:
    return "uygulanamaz" if x is None else ("**evet**" if x else "**HAYIR**")


def write_reports(inp: ResearchInputs, res: dict, timing: dict | None = None) -> tuple:
    rep = cfg_path(inp.cfg, "reports")
    dev = res["periods"]["development"]
    head = (f"Aşama: geliştirme ({dev[0].date()} – {dev[1].date()}); veri sonu {inp.end.date()}; doğrulama dönemi "
            f"yüklenmedi. Kod `{git_head()}`, ön kayıt `prereg-v1`. Nakit getirisi temel varsayım %0; Sharpe ABD 3 aylık "
            f"hazine bonosu üzerinden, √365.")
    pct = {"annual_return", "annual_vol", "vol_minus_target", "avg_gross_exposure", "avg_cash_share", "max_drawdown",
           "time_under_water_frac", "turnover_annual", "cost_annual", "win_rate", "top10pct_profit_share",
           "worst_1d_at_max_exposure", "worst_3d_at_max_exposure", "annual_return_simple", "cash_drag_annual",
           "annual_return_usd", "usdt_usd_min", "usdt_usd_max"}
    L = ["# G10 — Geliştirme dönemi değerlendirmesi", "", head, "",
         "> Birincil hipotez, DSR ve geç/kal kararları **tam dönemde** (kilitten sonra, G12) verilir. Bu rapordaki "
         "testler yalnızca geliştirme dönemidir ve ön bilgi niteliğindedir.", ""]
    L += ["## Metrikler: T0 ve kıyaslar", "",
          "B_btc200 birincil kıyas; B_btceth200 BTC/ETH eşit ağırlık (kendi SMA200'leri); B_btchold BTC al-tut; "
          "B_btcvol T0'ın gerçekleşen oynaklığına ölçekli BTC al-tut (dönem sonu bilgisiyle ölçeklendi); B_btc5050 "
          "%50 BTC + %50 nakit; B_univew evrenin eşit ağırlıklı al-tutu (aylık); B_trendew aynı trend sinyali, "
          "oynaklık ayarsız eşit ağırlık.", ""]
    for p, df in res["core"].items():
        L += [f"### {p}", "", to_markdown(df, 3, pct), ""]
    t0 = res["t0_full"]["tables"]
    ypct = {"return", "turnover", "cost"}
    L += ["## T0 yıl yıl getiri ve maliyet", "", to_markdown(t0["yearly"].T, 3, ypct), ""]
    b2 = res["b200_full"]["tables"]
    L += ["BTC-200:", "", to_markdown(b2["yearly"].T, 3, ypct), ""]
    if t0.get("holding_times") is not None:
        L += ["## T0 tutma süreleri (gün)", "", to_markdown(t0["holding_times"], 1, set()), ""]
    w = t0["worst_losses"]
    if w is not None and len(w):
        L += ["## Maksimum maruziyette en kötü 1 ve 3 günlük kayıplar (T0)", "",
              to_markdown(w.set_index(w.columns[0]) if w.index.name is None else w, 4, set()), ""]
    rs = t0["rolling_sharpe_12m"].dropna()
    if len(rs):
        L += [f"Kayan 12 aylık Sharpe (T0): en düşük {rs.min():.2f}, medyan {rs.median():.2f}, en yüksek {rs.max():.2f}.", ""]
    L += ["## Nakit getirisi duyarlılığı ve sabit tutarlı sonuç", "", to_markdown(res["sens"], 3, pct), ""]
    if res["usd"] is not None:
        L += ["## Dolar cinsinden (USDT/USD vekili: USDCUSDT'nin tersi)", "", to_markdown(res["usd"], 3, pct), ""]
    f, ud = res["factor"], res["updown"]
    L += ["## Regresyon (HAC)", "", "T0 aşırı getirisi ~ BTC + evren eşit ağırlıklı:", "",
          to_markdown(pd.DataFrame({"katsayı": f.params, "t": f.tvalues}), 3, set()), "",
          f"Yıllık alfa {f.extra['alpha_annual'] * 100:.1f}%, R² {f.r2:.2f}. Yükselen/düşen piyasa betası (BTC): "
          f"β⁺ {ud.params['beta_up']:.2f}, β⁻ {ud.params['beta_down']:.2f}, eşitlik Wald p = {ud.extra['wald_p']:.3f}.", ""]
    L += ["## Yatırımcı çıtaları", "",
          f"- ABD 3 aylık hazine bonosu, geliştirme dönemi ortalaması: yıllık {res['tbill_mean'] * 100:.2f}%.",
          "- Stopaj sonrası TL mevduatı: geçmiş seri indirilmedi (TCMB EVDS gerekir). SPEC'teki 2026 değeri "
          "(yaklaşık %35,5 TL, dolar cinsinden kabaca +%13) yalnızca bugünkü fırsat maliyetini gösterir.", ""]
    L += ["## Sıfır hipotezleri (Sharpe, basitleştirilmiş getiri)", "",
          f"Gözlenen (aynı basit hesap, maliyet oranı {C.simple_cost_rate(inp.cfg) * 100:.2f}% ciro): Sharpe "
          f"{res['simple_obs'][0]:.2f}, en büyük düşüş {res['simple_obs'][1] * 100:.1f}%.", "",
          "| Sıfır | çalıştırma | sıfır ort. Sharpe | sıfır %95 | p (Sharpe) | %95'te geçer | MDD yüzdelik sırası | sıfır medyan MDD |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k, v in res["nulls"].items():
        L.append(f"| {k} | {v['n']} | {v['null_mean']:.2f} | {v['null_q95']:.2f} | {v['p_sharpe']:.4f} | "
                 f"{_ok(v['p_sharpe'] < 0.05)} | {v['mdd_pct_rank']:.2f} | {v['null_mdd_median'] * 100:.1f}% |")
    L += ["", "## Negatif ve pozitif kontroller", "",
          "Eşikler sonuçlardan önce experiments.md satır 10'a yazıldı.", "",
          "| Kontrol | Beklenen | Sonuç | Beklendiği gibi |", "| --- | --- | --- | --- |"]
    for name, exp, txt, ok in res["controls"]:
        L.append(f"| {name} | {exp} | {txt} | {_ok(ok)} |")
    L += ["", "GARCH kontrolünün ilk kurulumunda simüle edilen log getirinin ortalaması sıfırdı; bu, coin başına σ²/2 "
          "kadar pozitif aritmetik kayma (günlük %5 oynaklıkta yılda yaklaşık %50) taşıyordu ve kontrolü geçersiz "
          "kılıyordu. Tablodaki satır düzeltilmiş kurulumdur (basit getirinin beklentisi sıfır); ilk sonuç ve düzeltme "
          "experiments.md'de."]
    sd = res["shuffle_dm"]
    L += ["", "## Ön kayıt dışı tanılar (seçim için kullanılmaz; experiments.md'ye yazıldı, N'ye eklendi)", "",
          "**Ortalamadan arındırılmış karıştırma** (her coinin basit getirisi kendi ortalamasından arındırılıp aynı "
          f"şekilde karıştırıldı, {len(res['controls']) and N_CONTROL_SEEDS} tohum): Sharpe ort. {sd['sharpe_mean']:.2f} "
          f"(aralık {sd['sharpe_min']:.2f}…{sd['sharpe_max']:.2f}), yıllık getiri ort. {sd['ann_mean'] * 100:.1f}%, "
          f"yıllık maliyet ort. {sd['cost_mean'] * 100:.1f}%. SPEC'in karıştırma kontrolü coinlerin dönem boyunca "
          "toplam kaymasını korur; uzun pozisyonlu bir sistem bu kaymadan zamanlama becerisi olmadan da kazanır. "
          "Kayma kaldırılınca kalan sonuç zamanlama ve geleceği görme için temiz bir sıfırdır.", "",
          "**−%35 sert sınır ve nakitte kilitlenme.** Sert sınır yeni alımları durdurur ve portföy zirvenin −%25'ine "
          "dönünce kalkar. Pozisyonlar sinyalle kapandıktan sonra nakit %0 getirdiği için portföy toparlanamaz ve "
          "durdurma dönem sonuna kadar sürer. Çalıştırmaların durdurma geçmişi:", "",
          to_markdown(res["stops"][res["stops"]["stop_days"] > 0], 3, {"max_drawdown"}), "",
          "T0 ile aynı ayar, sert sınır kapalı (tanı):", "", to_markdown(res["nostop_metrics"], 3, pct), "",
          "Döneme göre Sharpe:", "", to_markdown(res["nostop"], 2, set()), ""]
    if timing:
        L += ["", f"Toplam backtest süresi: {sum(timing.values()) / 60:.0f} dk işçi süresi, {len(timing)} çalıştırma."]
    g10 = rep / "G10_development.md"
    g10.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    # ---- G11 ----
    M = ["# G11 — Geliştirme dönemi sağlamlık ve istatistik", "", head, "",
         "> Tüm sonuçlar raporlanır, hiçbiri seçilmez. Kriterler 1, 2 ve 4 tam dönem / doğrulama dönemi içindir; "
         "aşağıdaki karşılıkları ön bilgidir.", ""]
    g = res["grid"]
    M += ["## Parametre ızgarası (temel + 10 komşu)", "", to_markdown(g, 3, {"annual_return", "annual_vol",
                                                                              "max_drawdown", "turnover_annual"}), "",
          "Rejimlere göre Sharpe:", "", to_markdown(res["grid_regimes"], 2, set()), ""]
    nb = g.drop(columns="T0")
    k7 = bool((nb.loc["sharpe"] > 0).all() and (nb.loc["sharpe_vs_base"] >= 0.5).all())
    pb = res["pbo"]
    M += [f"**PBO (CSCV, S = {pb['n_splits']}, {pb['n_combinations']} kombinasyon, 11 nokta):** {pb['pbo']:.3f}. "
          f"Örneklem dışı kayıp olasılığı {pb['prob_oos_loss']:.2f}; bozulma eğimi {pb['degradation_slope']:.2f}.", ""]
    d = res["dsr"]
    M += ["## Deflated Sharpe (geliştirme dönemi, ön bilgi)", "",
          f"N = max(100, deneme {d['n_experiments']} + ızgara {d['grid_size']} + varyant {d['n_variants']}) = "
          f"{d['n_trials_used']}; deneme Sharpe varyansı {d['var_trial_sharpe_annual']:.3f}; beklenen en büyük Sharpe "
          f"{d['sr0_annual']:.2f}. T0 Sharpe {d['sharpe_annual']:.2f} (SH {d['sharpe_se_annual']:.2f}); "
          f"**DSR {d['dsr']:.3f}**, PSR(0) {d['psr0']:.3f}.", ""]
    b, p = res["boot_sr"], res["paired"]
    M += ["## Bootstrap (durağan blok, ortalama 30 gün, 10.000 yol)", "",
          f"- T0 Sharpe {b['sharpe']:.2f}, %95 GA {b['ci95'][0]:.2f}…{b['ci95'][1]:.2f}.",
          f"- T0 − BTC-200 (eşleştirilmiş, geliştirme): ΔSharpe {p['sharpe_diff']:.2f}, %95 GA "
          f"{p['ci95_diff'][0]:.2f}…{p['ci95_diff'][1]:.2f}, tek yönlü p = {p['p_value']:.4f} "
          f"(BTC-200 Sharpe {p['sharpe_benchmark']:.2f})."]
    for k, v in res["paired_regimes"].items():
        M.append(f"- {k}: ΔSharpe {v['sharpe_diff']:.2f}, p = {v['p_value']:.4f}.")
    m6 = res["mdd_vs_ew"]
    M += [f"- En büyük düşüş medyanı: T0 {m6['median_mdd_strategy'] * 100:.1f}%, evren eşit ağırlıklı al-tut "
          f"{m6['median_mdd_other'] * 100:.1f}% (kriter 6: yarısından küçük → {_ok(m6['passed'])}; yolların "
          f"{m6['frac_paths_passing'] * 100:.0f}%'ında geçiyor).", "",
          "Düşüş ufku tablosu (ön bilgi; canlı kural kilitteki tabloyu kullanır):", "",
          to_markdown(res["dd_horizon"], 3, {"dd_q95", "dd_median", "dd_mean"}), ""]
    mt = res["mintrl"]
    M += [f"**Minimum kayıt uzunluğu:** gözlenen Sharpe {mt['sharpe_annual']:.2f} ile {_fmt(mt['min_trl_years'], 1)} "
          f"yıl gerekir; mevcut kayıt {mt['track_years']:.1f} yıl.", ""]
    M += ["## Varyantlar T1–T10", "", to_markdown(res["variants"], 3, {"annual_return", "max_drawdown",
                                                                     "avg_gross_exposure", "cost_annual"}), "",
          "Rejimlere göre Sharpe:", "", to_markdown(res["variants_regimes"], 2, set()), "",
          "T10 (BTC-200 çekirdek + T0 uydu, aylık):", "", to_markdown(res["t10"], 3, {"annual_return", "max_drawdown"}), ""]
    be = res["t6_breakeven"]
    M += ["**T6 karşı taraf stresi — sistemin hâlâ anlamlı kaldığı yıllık beklenen kayıp olasılığı:** T0 yıllık "
          f"aşırı log getirisi {be['log_excess']['t0'] * 100:.1f}%, BTC-200 {be['log_excess']['btc200'] * 100:.1f}%. "
          + "; ".join(f"L = %{k[1:]}: getiriyi sıfırlayan p* = {v['p_zero']:.3f}/yıl, BTC-200 düzeyine indiren "
                      f"p* = {v['p_btc200']:.3f}/yıl" for k, v in be.items() if k.startswith("L")) + ".", ""]
    s = res["satellite"]
    M += ["## Uydu payı kuralı (geliştirme dönemi, ön bilgi)", "",
          f"0,5 × SR_T0 = {s['lhs']:.3f}; ρ × SR_BTC200 = {s['rhs']:.3f} (ρ = {s['rho']:.2f}). Kural sonucu: "
          f"**%{s['weight'] * 100:.0f}**. Kesin hesap tam dönemde yapılır.", ""]
    t0s = res["core"]["development"]
    v = res["variants"]
    nulls_ok = all(x["p_sharpe"] < 0.05 for x in res["nulls"].values())
    ctl_ok = [c[3] for c in res["controls"]]
    M += ["## Geç/kal kriterleri — geliştirme dönemi karşılıkları (ön bilgi)", "",
          "| # | Kriter | Geliştirme dönemi | Durum |", "| --- | --- | --- | --- |",
          f"| 1 | BTC-200'ü Sharpe'ta %95 güvenle yener (tam dönemde) | p = {p['p_value']:.4f} | {_ok(p['passed'])} (ön bilgi) |",
          f"| 2 | DSR ≥ 0,95 (tam dönemde) | {d['dsr']:.3f} | {_ok(d['dsr'] >= 0.95)} (ön bilgi) |",
          f"| 3 | Geliştirmede PBO < 0,5 | {pb['pbo']:.3f} | {_ok(pb['pbo'] < 0.5)} |",
          f"| 4 | Doğrulamada net Sharpe > 0, 1× ve 2× maliyet | geliştirmede {t0s.loc['sharpe', 'T0']:.2f} / "
          f"{v.loc['sharpe', 'T6_cost2']:.2f} | doğrulamada ölçülecek |",
          f"| 5 | İki sıfır hipotezi %95 | p = {', '.join(f'{x['p_sharpe']:.4f}' for x in res['nulls'].values())} | {_ok(nulls_ok)} |",
          f"| 6 | Bootstrap medyan MDD < evren EW'nin yarısı | {m6['median_mdd_strategy'] * 100:.1f}% / "
          f"{m6['median_mdd_other'] * 100:.1f}% | {_ok(m6['passed'])} |",
          f"| 7 | Tüm komşularda Sharpe > 0 ve ≥ temelin %50'si | en düşük {nb.loc['sharpe'].min():.2f} "
          f"(oran {nb.loc['sharpe_vs_base'].min():.2f}) | {_ok(k7)} |",
          f"| 8 | Tüm negatif kontroller beklendiği gibi | {sum(1 for x in ctl_ok if x)}/{sum(1 for x in ctl_ok if x is not None)} | "
          f"{_ok(all(x for x in ctl_ok if x is not None))} |",
          f"| 9 | %20 delist cezasıyla Sharpe > 0 | {v.loc['sharpe', 'T5_20']:.2f} | {_ok(v.loc['sharpe', 'T5_20'] > 0)} |", ""]
    g11 = rep / "G11_robustness.md"
    g11.write_text("\n".join(M) + "\n", encoding="utf-8", newline="\n")
    summary = {"T0_sharpe_dev": float(t0s.loc["sharpe", "T0"]), "BTC200_sharpe_dev": float(t0s.loc["sharpe", "B_btc200"]),
               "pbo": pb["pbo"], "dsr": d["dsr"], "paired_p": p["p_value"],
               "null_p": {k: x["p_sharpe"] for k, x in res["nulls"].items()},
               "controls_ok": sum(1 for x in ctl_ok if x), "controls_n": sum(1 for x in ctl_ok if x is not None),
               "neighbors_ok": k7, "mdd_vs_ew_passed": bool(m6["passed"]),
               "T5_20_sharpe_dev": float(v.loc["sharpe", "T5_20"])}
    (cfg_path(inp.cfg, "backtests") / inp.stage / "summary.json").write_text(json.dumps(summary, indent=1),
                                                                             encoding="utf-8")
    return g10, g11


# ---------------------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m trend.research.g10")
    ap.add_argument("cmd", choices=["run", "report", "all"])
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--seeds", type=int, default=N_CONTROL_SEEDS)
    ap.add_argument("--only", nargs="*", default=None, help="yalnızca bu çalıştırmalar (hata ayıklama)")
    ap.add_argument("--no-reuse", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    inp = load_inputs("development")
    timing = None
    if a.cmd in ("run", "all"):
        specs = all_specs(inp.cfg, a.seeds)
        if a.only:
            specs = [s for s in specs if s.name in set(a.only)]
        panels = build_panels(inp, specs)
        timing = run_many(specs, inp, panels, a.workers, reuse=not a.no_reuse)
        if not a.only:
            p2 = phase2_specs(inp)
            timing.update(run_many(p2, inp, {"real": panels["real"]}, 1, reuse=not a.no_reuse))
    if a.cmd in ("report", "all"):
        res = analyze(inp, a.seeds)
        paths = write_reports(inp, res, timing)
        print("rapor →", *paths)
    print(f"bitti: {time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
