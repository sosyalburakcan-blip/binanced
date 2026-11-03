"""Araştırma v2/v3: aday aileler — toplu çalıştırma ve değerlendirme (PREREGISTRATION_v2, PREREGISTRATION_v3).

    python -m trend.alt.study run [--config research_v3.yaml]     # ön kayıtlı küme, BİR KEZ (lock/{TAG}_run.json)
    python -m trend.alt.study report [--config research_v3.yaml]  # rapor (önbellekten)

Ayar dosyası varsayılanı research_v2.yaml. Çalıştırmalar `backtests/{tag}/full/` altında; veri G12 anlık görüntüsü
(kilit tarihi ayar dosyasında). `run` yalnızca temiz çalışma ağacında, anlık görüntü kilitle tutarken ve bir kez
çalışır (G12 ile aynı kural). Ayar dosyasındaki `tag`, `title`, `prereg`, `report` anahtarları yoksa v2 değerleri;
ailede `leak_days` yoksa pozitif kontrol 1 gün sızıntıdır.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from trend.alt.registry import families, load_v2
from trend.config import load_settings, path as cfg_path
from trend.evaluation import bootstrap as bs
from trend.evaluation.dsr import deflated_sharpe_ratio, n_trials_for_dsr
from trend.evaluation.metrics import compute_metrics
from trend.evaluation.nulls import null_date_shuffle, null_p_value, null_random_coin, run_null
from trend.evaluation.pbo import pbo_cscv
from trend.evaluation.report import to_markdown
from trend.evaluation.satellite import satellite_from_returns
from trend.research import controls as C
from trend.research import g10, g12
from trend.research.g10 import _fmt, _ok, metrics_table, n_experiments, period_ret, sr
from trend.research.inputs import load_inputs
from trend.research.runner import RunSpec, load_run, run_many

_S = load_settings()
V2 = load_v2()
DEFAULTS = {"tag": "v2", "title": "Araştırma v2 — trend takibi dışındaki stratejiler",
            "prereg": "PREREGISTRATION_v2.md", "prereg_tag": "prereg-v2", "report": "V2_alternatives.md"}
BTC, ETH = _S["universe"]["btc_asset"], _S["universe"]["eth_asset"]
BENCH = ["B_btc200", "B_btchold", "B_btceth5050", "B_univew", "T0"]
KEYS = ["annual_return", "annual_vol", "sharpe", "sortino", "max_drawdown", "avg_gross_exposure", "turnover_annual",
        "cost_annual", "n_cycles"]
PCT = {"annual_return", "annual_vol", "max_drawdown", "avg_gross_exposure", "turnover_annual", "cost_annual",
       "growth_1000"}


def meta(v2: dict, key: str) -> str:
    return str(v2.get(key, DEFAULTS[key]))


def v2_settings(base: dict | None = None, tag: str = "v2") -> dict:
    base = base or _S
    return load_settings({"paths": {"backtests": str(cfg_path(base, "backtests") / tag)}})


def is_xsec(f: str) -> bool:
    """Kesitsel aile mi (evren üyeleri arasından seçim)? Sıfır hipotezi türünü belirler."""
    return bool(getattr(families()[f], "use_universe", False))


def leak_days(v2: dict, f: str) -> int:
    return int(v2["families"][f].get("leak_days", 1))


# ---------------------------------------------------------------------------------------------------------------
# Çalıştırma tanımları


def _name(f: str, k: str, x) -> str:
    return f"{f}_{k}{x:g}" if isinstance(x, (int, float)) else f"{f}_{k}{x}"


def candidate_specs(v2: dict = V2) -> list[RunSpec]:
    out = []
    for f, d in v2["families"].items():
        base = d["base"]
        out.append(RunSpec(f, kind=f"alt:{f}", params=tuple(base.items()), note="temel"))
        for k, vals in d["grid"].items():
            for x in vals:
                out.append(RunSpec(_name(f, k, x), kind=f"alt:{f}", params=tuple({**base, k: x}.items())))
    return out


def neighbors(f: str, v2: dict = V2) -> list[str]:
    return [_name(f, k, x) for k, vals in v2["families"][f]["grid"].items() for x in vals]


def control_specs(v2: dict = V2) -> list[RunSpec]:
    n = int(v2["evaluation"]["n_control_seeds"])
    o = (("backtest.fill", "open_t1"),)
    cm = float(_S["backtest"]["stress"]["cost_multiplier"])
    out = []
    for f, d in v2["families"].items():
        p, k = tuple(d["base"].items()), f"alt:{f}"
        out += [RunSpec(f"{f}_cost2", kind=k, params=p, overrides=(("backtest.cost_multiplier", cm),)),
                RunSpec(f"{f}_lag365", kind=k, params=p, leak_days=-365),
                RunSpec(f"{f}_leak{leak_days(v2, f)}", kind=k, params=p, leak_days=leak_days(v2, f),
                        note="pozitif kontrol")]
        out += [RunSpec(f"{f}_shdm{s}", kind=k, params=p, panel=f"shuffledm{s}", overrides=o) for s in range(n)]
        out += [RunSpec(f"{f}_garch{s}", kind=k, params=p, panel=f"garch{s}", overrides=o) for s in range(n)]
    return out


def benchmark_specs() -> list[RunSpec]:
    return [RunSpec("B_btc200", kind="btc_200"), RunSpec("B_btchold", kind="btc_hold"),
            RunSpec("B_btceth5050", kind="alt:HOLD", params=(("mix", ((BTC, 0.5), (ETH, 0.5))),)),
            RunSpec("B_univew", kind="universe_ew"), RunSpec("T0", note="v1 temel ayar (sert sınırlı)")]


def all_specs(v2: dict = V2) -> list[RunSpec]:
    return benchmark_specs() + candidate_specs(v2) + control_specs(v2)


# ---------------------------------------------------------------------------------------------------------------
# Tek seferlik toplu çalıştırma


def run_batch(workers: int | None = None, allow_rerun: bool = False, v2: dict = V2) -> dict:
    base = load_settings()
    tag = meta(v2, "tag")
    rp = g12.lock_dir(base) / f"{tag.upper()}_run.json"
    if rp.exists() and not allow_rerun:
        raise SystemExit(f"{tag} toplu çalıştırması zaten yapıldı ({rp}); raporu `report` ile üretin.")
    dirty = g12.git("status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise SystemExit("çalışma ağacında işlenmemiş değişiklik var; ön kayıt commit'i temiz olmalı:\n" + dirty)
    v = g12.verify_snapshot(base)
    if not v["ok"]:
        raise SystemExit(f"anlık görüntü kilitle tutmuyor ({v['n_changed']} dosya): {v['changed']}")
    cfg = v2_settings(base, tag)
    specs = all_specs(v2)
    rec = {"started_utc": g12._now(), "code_commit": g12.git("rev-parse", "HEAD"), "lock_date": v2["lock_date"],
           "data_manifest_sha256": g12.read_lock(base)["data_manifest_sha256"], "n_specs": len(specs),
           "specs": [s.name for s in specs]}
    g12._write_json(rp, rec)          # çalıştırmadan ÖNCE
    t0 = time.perf_counter()
    inp = load_inputs("full", v2["lock_date"], cfg=cfg, fill_modes=("vwap_00_02", "open_t1"))
    panels = g10.build_panels(inp, specs)
    timing = run_many(specs, inp, panels, workers, reuse=False)
    rec.update(finished_utc=g12._now(), n_runs=len(timing), worker_seconds=round(sum(timing.values()), 1),
               wall_seconds=round(time.perf_counter() - t0, 1))
    g12._write_json(rp, rec)
    return rec


# ---------------------------------------------------------------------------------------------------------------
# Değerlendirme


def periods(inp, v2: dict = V2) -> dict:
    d0, d1 = (pd.Timestamp(x) for x in v2["design"])
    (r1s, r1e), (r2s, _) = inp.cfg["periods"]["regimes"]
    return {"full": (d0, inp.end), "design": (d0, d1), "holdout": (pd.Timestamp(v2["holdout_start"]), inp.end),
            f"regime_{r1s[:7]}_{r1e[:7]}": (pd.Timestamp(r1s), pd.Timestamp(r1e)),
            f"regime_{r2s[:7]}_end": (pd.Timestamp(r2s), inp.end)}


def growth(inp, name: str, per: tuple) -> float:
    """Dönem başında 1 → dönem sonunda (ilk günün getirisi dahil)."""
    r = period_ret(inp, name, per)
    return float((1.0 + r).prod())


def yearly(inp, name: str, per: tuple) -> pd.Series:
    r = period_ret(inp, name, per)
    return (1.0 + r).groupby(r.index.year).prod() - 1.0


def null_tests(inp, f: str, per: tuple, cfg: dict) -> dict:
    run = load_run(inp, f)
    close = inp.panel_1d["close"]
    w_end = run.weights.loc[per[0]: per[1]]
    rets = C.asset_returns(close).reindex(index=w_end.index)
    w_hold = C.hold_weights(w_end, rets[w_end.columns])
    cost = C.simple_cost_rate(cfg)
    obs = C.simple_stats(w_hold, rets, cost, inp.rf)

    def stat(w):
        return C.simple_stats(w, rets, cost, inp.rf)

    if is_xsec(f):
        mem = C.membership(inp.universes["main"], w_end.index, list(close.columns))
        avail = rets.notna() | close.reindex(w_end.index).notna()
        od = pd.to_datetime(run.cycles["open_date"])
        cyc = run.cycles[(od >= w_end.index[0]) & (od <= w_end.index[-1])].copy()
        # dönem sonundan sonra kapanan döngü dönem sonunda kesilir (çalıştırmalar tam dönem, sıfırlar tasarımda)
        cyc.loc[pd.to_datetime(cyc["close_date"]) > w_end.index[-1], "close_date"] = pd.NaT
        gens = {"tarih_karistirma": lambda rng: null_date_shuffle(cyc, w_hold, mem, rng, avail)[0],
                "rastgele_coin": lambda rng: null_random_coin(cyc, w_hold, mem, rng, avail)[0]}
    else:
        T, W = len(w_hold), w_hold.to_numpy()

        def shift(rng):
            return pd.DataFrame(np.roll(W, int(rng.integers(30, T - 30)), axis=0), index=w_hold.index,
                                columns=w_hold.columns)
        gens = {"dairesel_kaydirma": shift}
    out = {"obs_sharpe": float(obs[0])}
    for k, g in gens.items():
        res = run_null(g, stat, cfg=cfg)
        out[k] = {"p": null_p_value(obs[0], res[:, 0]), "null_mean": float(np.nanmean(res[:, 0])),
                  "null_q95": float(np.nanquantile(res[:, 0], 0.95)), "n": int(res.shape[0])}
    return out


def controls(inp, f: str, per: tuple, v2: dict = V2) -> list[tuple]:
    ev = v2["evaluation"]
    n = int(ev["n_control_seeds"])
    s0 = sr(inp, f, per)
    out = []
    s_lag = sr(inp, f"{f}_lag365", per)
    out.append(("Sinyal 365 gün gecikmeli", f"Sharpe ≤ temelin %{ev['lag_max_ratio'] * 100:.0f}'i",
                f"{s_lag:.2f} (temel {s0:.2f})", (s_lag <= ev["lag_max_ratio"] * s0) if s0 > 0 else None))
    lk = leak_days(v2, f)
    s_leak = sr(inp, f"{f}_leak{lk}", per)
    out.append((f"Pozitif kontrol: {lk} gün sızıntı", f"Sharpe ≥ temel + {ev['leak_min_gain']:g}",
                f"{s_leak:.2f} (temel {s0:.2f})", bool(s_leak >= s0 + ev["leak_min_gain"])))
    for pre, label in (("shdm", "Ortalamadan arındırılmış karıştırma"), ("garch", "GARCH serileri")):
        s = [sr(inp, f"{f}_{pre}{k}", per) for k in range(n)]
        a = [compute_metrics(load_run(inp, f"{f}_{pre}{k}").daily, None, inp.rf, None, per[0], per[1])["scalars"]
             for k in range(n)]
        ann = float(np.mean([x["annual_return"] for x in a]))
        out.append((f"{label} ({n} tohum)", "yıllık getiri < 0 ve Sharpe ≤ 0",
                    f"Sharpe ort. {np.mean(s):.2f} ({min(s):.2f}…{max(s):.2f}), yıllık {ann * 100:.1f}%",
                    bool(ann < 0 and float(np.mean(s)) <= 0)))
    return out


def analyze(inp, v2: dict = V2, verbose: bool = True) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    cfg, ev = inp.cfg, v2["evaluation"]
    P = periods(inp, v2)
    F, D, H = P["full"], P["design"], P["holdout"]
    fams = list(v2["families"])
    cands = [s.name for s in candidate_specs(v2)]
    out: dict = {"periods": P, "families": {}}
    names = BENCH + fams
    out["metrics"] = {p: metrics_table(inp, names, P[p], KEYS) for p in P}
    for p in ("full", "design", "holdout"):
        out["metrics"][p].loc["growth_1000"] = [growth(inp, n, P[p]) for n in names]
    out["yearly"] = pd.DataFrame({n: yearly(inp, n, F) for n in names}).T
    cand_sr = np.array([sr(inp, n, F) for n in cands])
    n_exp = n_experiments(cfg)
    prior = int(ev.get("dsr_trials_prior", ev.get("dsr_trials_v1", 0)))
    n_trials = n_trials_for_dsr(n_exp, prior, len(cands), cfg)
    out["dsr_n"] = {"n_experiments": n_exp, "prior": prior, "this": len(cands), "N": n_trials,
                    "alpha": alpha_fam(v2)}
    alpha = alpha_fam(v2)
    rb = period_ret(inp, "B_btc200", F)
    for f in fams:
        log(f"[{meta(v2, 'tag')}] {f}")
        r = {}
        rf_ = period_ret(inp, f, F)
        r["primary"] = bs.paired_sharpe_test(rf_, rb, inp.rf, alpha=alpha, cfg=cfg)
        r["dsr"] = deflated_sharpe_ratio(rf_, n_trials, trial_sharpes_annual=cand_sr, rf=inp.rf, cfg=cfg)
        r["sr"] = {f"{n}|{p}": sr(inp, n, P[p]) for n in (f, f"{f}_cost2") for p in ("design", "holdout", "full")}
        grid = [f] + neighbors(f, v2)
        trials = pd.concat({n: period_ret(inp, n, D) - inp.rf.reindex(period_ret(inp, n, D).index).fillna(0.0)
                            for n in grid}, axis=1).dropna()
        r["pbo"] = pbo_cscv(trials.to_numpy())
        r["neighbors"] = {n: sr(inp, n, F) for n in grid}
        r["nulls"] = null_tests(inp, f, D, cfg)
        r["controls"] = controls(inp, f, D, v2)
        r["satellite"] = satellite_from_returns(rf_, rb, inp.rf, cfg)
        r["criteria"] = criteria(f, r, v2)
        out["families"][f] = r
    return out


def alpha_fam(v2: dict) -> float:
    ev = v2["evaluation"]
    return float(ev["alpha"]) / int(ev["n_families"])


def criteria(f: str, r: dict, v2: dict = V2) -> list[tuple]:
    ev = v2["evaluation"]
    p, d, s = r["primary"], r["dsr"], r["sr"]
    base = r["neighbors"][f]
    nb = {k: v for k, v in r["neighbors"].items() if k != f}
    c3 = all(s[f"{n}|{q}"] > 0 for n in (f, f"{f}_cost2") for q in ("design", "holdout"))
    nulls = {k: v for k, v in r["nulls"].items() if isinstance(v, dict)}
    ctl = [c[3] for c in r["controls"]]
    k7 = bool(nb) and all(v > 0 and v >= ev["neighbor_min_ratio"] * base for v in nb.values())
    return [
        (1, f"BTC-200'ü yener (p < {alpha_fam(v2):.4f})",
         f"ΔSharpe {p['sharpe_diff']:.2f}, p = {p['p_value']:.4f}", bool(p["passed"])),
        (2, "DSR ≥ 0,95", f"{d['dsr']:.3f}", bool(d["dsr"] >= 0.95)),
        (3, "Tasarım ve bekletmede Sharpe > 0 (1× ve 2× maliyet)",
         f"{s[f'{f}|design']:.2f} / {s[f'{f}|holdout']:.2f}; 2×: {s[f'{f}_cost2|design']:.2f} / "
         f"{s[f'{f}_cost2|holdout']:.2f}", bool(c3)),
        (4, "PBO < 0,5", f"{r['pbo']['pbo']:.3f}", bool(r["pbo"]["pbo"] < ev["pbo_max"])),
        (5, "Sıfır hipotezleri p < 0,05", ", ".join(f"{k} {v['p']:.3f}" for k, v in nulls.items()),
         bool(all(v["p"] < float(ev["alpha"]) for v in nulls.values()))),
        (6, "Kontroller beklendiği gibi", f"{sum(1 for x in ctl if x)}/{sum(1 for x in ctl if x is not None)}",
         bool(all(x for x in ctl if x is not None))),
        (7, "Komşularda Sharpe > 0 ve ≥ temelin %50'si",
         f"en düşük {min(nb.values()):.2f}" if nb else "—", k7),
    ]


def decision(r: dict) -> str:
    c = r["criteria"]
    if all(x[3] for x in c):
        return "gölge mod adayı"
    if all(x[3] for x in c[1:]) and r["satellite"]["weight"] > 0:
        return "uydu dilimi adayı"
    return "reddedildi"


# ---------------------------------------------------------------------------------------------------------------
# Rapor


def write_report(inp, res: dict, run_rec: dict | None, v2: dict = V2) -> object:
    P = res["periods"]
    F = P["full"]
    fams = list(res["families"])
    tag = meta(v2, "tag")
    L = [f"# {meta(v2, 'title')}", "",
         f"Tam dönem {F[0].date()} – {F[1].date()}; tasarım {P['design'][0].date()} – {P['design'][1].date()}; "
         f"kirlenmiş bekletme {P['holdout'][0].date()} – {P['holdout'][1].date()}. Ön kayıt `{meta(v2, 'prereg')}` "
         f"(tag `{meta(v2, 'prereg_tag')}`). Maliyetler, dolum ve evren v1 ile aynı; nakit %0; sert sınır yok.", "",
         "> Bu veride gerçek örneklem dışı dönem yok (2024 sonrası G12'de görüldü). Geçen bir aile bile ancak gölge "
         "mod adayıdır.", ""]
    if run_rec:
        L += [f"Toplu çalıştırma: {run_rec.get('started_utc')} → {run_rec.get('finished_utc', 'yarıda')} UTC, "
              f"{run_rec.get('n_runs', '—')} çalıştırma, commit `{str(run_rec.get('code_commit'))[:7]}` "
              f"(`lock/{tag.upper()}_run.json`).", ""]
    L += ["## Sonuç", "", "| Aile | Yıllık getiri | Sharpe | En büyük düşüş | 1.000 $ → | Kriter | Karar |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    m = res["metrics"]["full"]
    for n in BENCH + fams:
        r = res["families"].get(n)
        crit = f"{sum(1 for c in r['criteria'] if c[3])}/7" if r else "kıyas"
        L.append(f"| {n} | {m.loc['annual_return', n] * 100:.1f}% | {m.loc['sharpe', n]:.2f} | "
                 f"{m.loc['max_drawdown', n] * 100:.1f}% | {m.loc['growth_1000', n] * 1000:,.0f} | {crit} | "
                 f"{decision(r) if r else '—'} |")
    d = res["dsr_n"]
    L += ["", f"DSR için N = max(100, deneme {d['n_experiments']} + önceki araştırmalar {d['prior']} + bu araştırma "
          f"{d['this']}) = {d['N']}. Birincil test Bonferroni ile p < {d['alpha']:.4f}.", ""]
    for p in P:
        L += [f"## Metrikler: {p}", "", to_markdown(res["metrics"][p], 3, PCT), ""]
    L += ["## Yıl yıl getiri", "", to_markdown(res["yearly"], 3, set(res["yearly"].index)), ""]
    for f in fams:
        r = res["families"][f]
        L += [f"## {f}", "", "| # | Kriter | Değer | Durum |", "| --- | --- | --- | --- |"]
        for k, name, txt, ok in r["criteria"]:
            L.append(f"| {k} | {name} | {txt} | {_ok(ok)} |")
        s = r["satellite"]
        L += ["", f"Karar: **{decision(r)}**. Uydu kuralı: 0,5 × {s['sr_t0']:.2f} = {s['lhs']:.3f} vs ρ × SR_BTC200 = "
              f"{s['rhs']:.3f} (ρ = {s['rho']:.2f}).", "",
              "Komşular (tam dönem Sharpe): " + ", ".join(f"{k} {v:.2f}" for k, v in r["neighbors"].items()) + ".", "",
              "| Kontrol | Beklenen | Sonuç | Beklendiği gibi |", "| --- | --- | --- | --- |"]
        for name, exp, txt, ok in r["controls"]:
            L.append(f"| {name} | {exp} | {txt} | {_ok(ok)} |")
        nl = r["nulls"]
        L += ["", f"Sıfır hipotezleri (tasarım, basit hesap Sharpe {nl['obs_sharpe']:.2f}): "
              + "; ".join(f"{k}: p = {v['p']:.3f}, sıfır ort. {v['null_mean']:.2f}, %95 {v['null_q95']:.2f}"
                          for k, v in nl.items() if isinstance(v, dict)) + ".", ""]
    out = cfg_path(inp.cfg, "reports") / meta(v2, "report")
    out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    summ = {f: {"decision": decision(r), "criteria": {str(c[0]): c[3] for c in r["criteria"]},
                "sharpe_full": float(res["metrics"]["full"].loc["sharpe", f]),
                "annual_return_full": float(res["metrics"]["full"].loc["annual_return", f])}
            for f, r in res["families"].items()}
    g12._write_json(cfg_path(inp.cfg, "backtests") / inp.stage / f"summary_{tag}.json", summ)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m trend.alt.study")
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--config", default=None, help="ayar dosyası (varsayılan research_v2.yaml)")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    v2 = load_v2(a.config) if a.config else V2
    if a.cmd == "run":
        print(json.dumps({k: v for k, v in run_batch(a.workers, v2=v2).items() if k != "specs"}, indent=1))
    else:
        base = load_settings()
        tag = meta(v2, "tag")
        rp = g12.lock_dir(base) / f"{tag.upper()}_run.json"
        rec = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else None
        inp = load_inputs("full", v2["lock_date"], cfg=v2_settings(base, tag), fill_modes=("open_t1",))
        print("rapor →", write_report(inp, analyze(inp, v2), rec, v2))
    print(f"bitti: {time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
