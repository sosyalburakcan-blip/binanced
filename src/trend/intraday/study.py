"""Araştırma v4: gün içi momentum (PREREGISTRATION_v4, research_v4.yaml) — tek seferlik toplu çalıştırma ve değerlendirme.

    python -m trend.intraday.study run      # ön kayıtlı ızgara × piyasalar + kontroller, BİR KEZ (lock/V4_run.json)
    python -m trend.intraday.study report   # reports/V4_intraday_momentum.md (önbellekten)

Girdiler (G12 anlık görüntüsüne dokunmaz):
- 15 dk barlar ve fonlama: `data/intraday/{spot_15m,futures_15m,funding}/{ASSET}.parquet` (trend.data.intraday).
- Bilinen coin listesi (nokta zamanlı): ay m'deki karar saatleri için `universe/{m}.csv` (ana evren, ay başında
  bilinen veriyle kurulmuş); ay başında en az `min_age_days` gündür listelenen (asset_segments ilk başlangıç)
  üyelerden likidite sırasına göre ilk `top_n`.
- Kayma: aynı evren dosyasının `slippage` kolonu (yoksa en yüksek kademe).
Sonuçlar `backtests/v4/{venue}/{config}.parquet` (günlük NAV) ve `.../trades/` altında.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import pickle
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from trend.config import ROOT, load_settings, path as cfg_path
from trend.evaluation import bootstrap as bs
from trend.evaluation import rates
from trend.evaluation.common import sharpe
from trend.evaluation.dsr import deflated_sharpe_ratio, n_trials_for_dsr
from trend.evaluation.pbo import pbo_cscv
from trend.evaluation.report import to_markdown
from trend.research import g12
from trend.research.g10 import _ok, n_experiments

_S = load_settings()
V4_FILE = ROOT / "research_v4.yaml"
OUT = cfg_path(_S, "backtests") / "v4"
INTRA = ROOT / "data" / "intraday"


def load_v4(path=None) -> dict:
    with open(path or V4_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------------------------------------------
# Girdiler


def well_known_assets(v4: dict) -> list[str]:
    """Kilit döneminde en az bir ay bilinen coin listesine giren varlıklar (sütun kümesi)."""
    elig, assets, _ = eligibility(v4, pd.date_range(v4["design"][0], v4["end"], freq="h"))
    return [a for j, a in enumerate(assets) if elig[:, j].any()]


def eligibility(v4: dict, hours: pd.DatetimeIndex, assets: list[str] | None = None):
    """(saat × varlık) bilinen coin maskesi ve kayma; varlık listesi verilmezse tüm aday birleşimi."""
    seg = pd.read_csv(cfg_path(_S, "meta") / "asset_segments.csv", parse_dates=["start"])
    first = seg.groupby("asset_id")["start"].min()
    root = cfg_path(_S, "universe")
    months = pd.period_range(hours[0], hours[-1], freq="M")
    tables = {}
    for m in months:
        f = root / f"{m.strftime('%Y-%m')}.csv"
        u = pd.read_csv(f) if f.exists() else pd.DataFrame(columns=["symbol", "rank", "slippage"])
        t0 = m.start_time
        u = u[[(t0 - first.get(s, t0)).days >= int(v4["universe"]["min_age_days"]) for s in u["symbol"]]]
        tables[m] = u.sort_values("rank").head(int(v4["universe"]["top_n"]))
    if assets is None:
        assets = sorted(set().union(*[set(t["symbol"]) for t in tables.values()]))
    col = {a: j for j, a in enumerate(assets)}
    elig = np.zeros((len(hours), len(assets)), dtype=bool)
    slip = np.full((len(hours), len(assets)), float(v4["costs"]["slip_default"]), dtype=np.float32)
    per = hours.to_period("M")
    for m, u in tables.items():
        rows = np.flatnonzero(per == m)
        for s, sl in zip(u["symbol"], u.get("slippage", pd.Series(dtype=float))):
            if s in col:
                elig[rows, col[s]] = True
                if pd.notna(sl):
                    slip[rows, col[s]] = float(sl)
    return elig, assets, slip


def load_market(venue: str, assets: list[str], t15: pd.DatetimeIndex):
    from trend.intraday.sim import Market
    sub = "spot_15m" if venue == "spot" else "futures_15m"
    shape = (len(t15), len(assets))
    arr = {k: np.full(shape, np.nan, dtype=np.float32) for k in ("o", "h", "l", "c")}
    fund = np.zeros(shape, dtype=np.float32) if venue != "spot" else None
    for j, a in enumerate(assets):
        p = INTRA / sub / f"{a}.parquet"
        if p.exists():
            df = pd.read_parquet(p, columns=["open_time", "open", "high", "low", "close"]).set_index("open_time")
            df = df[~df.index.duplicated()].reindex(t15)
            for k, src in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close")):
                arr[k][:, j] = df[src].to_numpy(dtype=np.float32)
        if fund is not None:
            q = INTRA / "funding" / f"{a}.parquet"
            if q.exists():
                fr = pd.read_parquet(q, columns=["funding_time", "funding_rate"])
                pos = t15.get_indexer(pd.DatetimeIndex(fr["funding_time"]).floor("15min"))
                ok = pos >= 0
                np.add.at(fund[:, j], pos[ok], fr["funding_rate"].to_numpy(dtype=np.float32)[ok])
    return Market(assets=assets, t15=t15, o=arr["o"], h=arr["h"], l=arr["l"], c=arr["c"], funding=fund)


# ---------------------------------------------------------------------------------------------------------------
# Çalıştırma tanımları


def grid(v4: dict) -> list[dict]:
    g = v4["grid"]
    keys = list(g)
    return [dict(zip(keys, vals)) for vals in itertools.product(*(g[k] for k in keys))]


def cfg_name(p: dict) -> str:
    return (f"L{p['lookback_h']}_z{p['z_entry']:g}_k{p['confirm_h']}_tp{p['tp'] * 100:g}_sl{p['sl'] * 100:g}"
            f"_h{p['max_hold_h']}")


def venues(v4: dict) -> list[tuple[str, str, float]]:
    """(çalıştırma kümesi adı, piyasa, kaldıraç)."""
    out = [("spot", "spot", 1.0)]
    out += [(f"fut{lev:g}x", "futures", float(lev)) for lev in v4["leverage"]]
    return out


def costs_for(v4: dict, market: str, mult: float = 1.0, fee_mult: float = 1.0, tax_add: float = 0.0):
    """mult: ücret + vergi çarpanı (2× maliyet stresi); fee_mult: yalnızca ücret (BNB indirimi); tax_add: işlem vergisi."""
    from trend.intraday.sim import Costs
    c = v4["costs"][market]
    tax = float(v4["costs"]["tax_per_side"][market]) + tax_add
    return Costs(taker=float(c["taker"]) * mult * fee_mult, maker=float(c["maker"]) * mult * fee_mult,
                 tax_per_side=tax * mult,
                 mmr=float(c.get("mmr", 0.0)), liq_fee=float(c.get("liq_fee", 0.0)))


# ---------------------------------------------------------------------------------------------------------------
# Paralel yürütme (Windows: spawn; işçiler pazarı tek pickle dosyasından okur)

_W: dict = {}


def _init(pkl: str) -> None:
    with open(pkl, "rb") as f:
        _W.update(pickle.load(f))


def _job(job: dict) -> tuple[str, float, str | None]:
    from trend.intraday.sim import Params, simulate
    t0 = time.perf_counter()
    try:
        p = Params(**job["params"], vol_window_h=int(_W["v4"]["fixed"]["vol_window_h"]),
                   n_top=int(_W["v4"]["fixed"]["n_top"]), slots=int(_W["v4"]["fixed"]["slots"]),
                   leverage=float(job["leverage"]))
        rng = np.random.default_rng(job["seed"]) if job.get("seed") is not None else None
        k = costs_for(_W["v4"], _W["market"], job.get("cost_mult", 1.0), job.get("fee_mult", 1.0), job.get("tax_add", 0.0))
        res = simulate(_W["mkt"], _W["elig"], _W["slip"], p, k,
                       start=_W["v4"]["design"][0], end=_W["v4"]["end"], lag_h=int(job.get("lag_h", 0)),
                       rng=rng, random_entries=job.get("random_entries"))
        d = Path(_W["out"]) / job["set"]
        d.mkdir(parents=True, exist_ok=True)
        res.nav.rename("nav").to_frame().to_parquet(d / f"{job['name']}.parquet")
        if job.get("keep_trades"):
            (d / "trades").mkdir(exist_ok=True)
            res.trades.to_parquet(d / "trades" / f"{job['name']}.parquet")
        meta = {"job": job, "n_trades": int(len(res.trades)), "diag": res.diag,
                "reasons": res.trades["reason"].value_counts().to_dict() if len(res.trades) else {}}
        (d / f"{job['name']}.json").write_text(json.dumps(meta, default=str), encoding="utf-8")
        return f"{job['set']}/{job['name']}", time.perf_counter() - t0, None
    except Exception as e:  # noqa: BLE001
        import traceback
        return f"{job['set']}/{job['name']}", time.perf_counter() - t0, traceback.format_exc(limit=8) + repr(e)


def run_jobs(jobs: list[dict], mkt, elig, slip, market: str, v4: dict, workers: int) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    pkl = OUT / f"_inputs_{market}.pkl"
    with open(pkl, "wb") as f:      # çıktı dizini de geçer: işçiler (spawn) modülü yeniden yükler
        pickle.dump({"mkt": mkt, "elig": elig, "slip": slip, "market": market, "v4": v4, "out": str(OUT)}, f,
                    protocol=pickle.HIGHEST_PROTOCOL)
    times, errors = {}, {}
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(str(pkl),)) as ex:
        futs = [ex.submit(_job, j) for j in jobs]
        for k, fu in enumerate(as_completed(futs), start=1):
            name, sec, err = fu.result()
            times[name] = sec
            if err:
                errors[name] = err
            if k % 100 == 0 or k == len(jobs):
                print(f"[v4] {market}: {k}/{len(jobs)} (geçen {time.perf_counter() - t0:.0f}s, hata {len(errors)})",
                      flush=True)
    pkl.unlink(missing_ok=True)
    if errors:
        raise RuntimeError("başarısız işler:\n" + "\n\n".join(f"{k}:\n{v}" for k, v in list(errors.items())[:5]))
    return times


def design_top(v4: dict, set_name: str = "spot", k: int | None = None) -> list[str]:
    """Tasarım döneminde net Sharpe'a göre sıralı yapılandırma adları (ilk k)."""
    D = (pd.Timestamp(v4["design"][0]), pd.Timestamp(v4["design"][1]))
    s = {cfg_name(p): sr_of(nav_of(set_name, cfg_name(p)), D) for p in grid(v4)}
    order = sorted(s, key=lambda n: -np.nan_to_num(s[n], nan=-9e9))
    return order[:k] if k else order


def run_batch(workers: int | None = None, allow_rerun: bool = False, v4: dict | None = None) -> dict:
    v4 = v4 or load_v4()
    base = load_settings()
    rp = g12.lock_dir(base) / "V4_run.json"
    if rp.exists() and not allow_rerun:
        raise SystemExit(f"v4 toplu çalıştırması zaten yapıldı ({rp}); raporu `report` ile üretin.")
    dirty = g12.git("status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise SystemExit("çalışma ağacında işlenmemiş değişiklik var; ön kayıt commit'i temiz olmalı:\n" + dirty)
    v = g12.verify_snapshot(base)
    if not v["ok"]:
        raise SystemExit(f"G12 anlık görüntüsü tutmuyor ({v['n_changed']} dosya)")
    workers = workers or int(v4["run"]["workers"])
    rec = {"started_utc": g12._now(), "code_commit": g12.git("rev-parse", "HEAD"),
           "intraday_inventory_sha256": g12.sha256_file(INTRA / "inventory.csv"), "n_configs": len(grid(v4))}
    g12._write_json(rp, rec)          # çalıştırmadan ÖNCE
    t15 = pd.date_range(pd.Timestamp(v4["design"][0]) - pd.Timedelta(days=int(v4["warmup_days"])),
                        pd.Timestamp(v4["end"]) + pd.Timedelta(hours=23, minutes=45), freq="15min")
    elig, assets, slip = eligibility(v4, t15[::4])
    timing = run_pipeline(v4, lambda market: load_market(market, assets, t15), elig, slip, workers)
    rec.update(finished_utc=g12._now(), n_runs=len(timing), worker_seconds=round(sum(timing.values()), 1))
    g12._write_json(rp, rec)
    return rec


def run_pipeline(v4: dict, get_market, elig, slip, workers: int) -> dict:
    """Ön kayıtlı küme: her piyasa/kaldıraçta tam ızgara; spotta en iyi top_k için kontroller ve sıfırlar, rastgele
    sinyalli ızgaralar. `get_market(piyasa)` pazarı yükler (bellek için piyasa başına bir kez)."""
    timing = {}
    for set_name, market, lev in venues(v4):
        mkt = get_market(market)
        jobs = [{"set": set_name, "name": cfg_name(p), "params": p, "leverage": lev} for p in grid(v4)]
        timing.update(run_jobs(jobs, mkt, elig, slip, market, v4, workers))
        if set_name == "spot":
            top = design_top(v4, "spot", int(v4["controls"]["top_k"]))
            ctl = []
            for n in top:
                p = next(q for q in grid(v4) if cfg_name(q) == n)
                ctl += [{"set": "spot_ctl", "name": f"{n}__lag1", "params": p, "leverage": 1.0, "lag_h": 1},
                        {"set": "spot_ctl", "name": f"{n}__leak1", "params": p, "leverage": 1.0, "lag_h": -1},
                        {"set": "spot_ctl", "name": f"{n}__cost2", "params": p, "leverage": 1.0, "cost_mult": 2.0},
                        {"set": "spot_ctl", "name": f"{n}__bnb", "params": p, "leverage": 1.0,
                         "fee_mult": 1.0 - float(v4["costs"]["spot_bnb_discount"])},
                        {"set": "spot_ctl", "name": f"{n}__txtax", "params": p, "leverage": 1.0,
                         "tax_add": float(v4["costs"]["tr_tx_tax_sensitivity"])},
                        {"set": "spot_ctl", "name": n, "params": p, "leverage": 1.0, "keep_trades": True}]
                rate = entry_rate(v4, n, elig)
                ctl += [{"set": "spot_null", "name": f"{n}__rnd{s}", "params": p, "leverage": 1.0, "seed": 1000 + s,
                         "random_entries": rate} for s in range(int(v4["controls"]["n_random"]))]
            for r in range(int(v4["controls"]["random_grids"])):
                for q in grid(v4):
                    rate = entry_rate(v4, cfg_name(q), elig)
                    ctl.append({"set": f"spot_rgrid{r}", "name": cfg_name(q), "params": q, "leverage": 1.0,
                                "seed": 50000 + 1000 * r + grid(v4).index(q), "random_entries": rate})
            timing.update(run_jobs(ctl, mkt, elig, slip, market, v4, workers))
        del mkt
    return timing


def entry_rate(v4: dict, name: str, elig: np.ndarray) -> float:
    """Rastgele giriş sıfırı: gerçek yapılandırmanın işlem sayısı / uygun varlık-saat (tasarım + bekletme)."""
    meta = json.loads((OUT / "spot" / f"{name}.json").read_text(encoding="utf-8"))
    return float(meta["n_trades"]) / max(1, int(elig.sum()))


def set_out(path) -> None:
    """Çıktı kökü (testler geçici dizin verir)."""
    global OUT
    OUT = Path(path)


# ---------------------------------------------------------------------------------------------------------------
# Değerlendirme

_RF = None


def rf() -> pd.Series:
    global _RF
    if _RF is None:
        days = pd.date_range(_S["periods"]["data_start"], "2026-11-01", freq="D")
        _RF = rates.rf_daily(days)
    return _RF


def nav_of(set_name: str, name: str) -> pd.Series:
    return pd.read_parquet(OUT / set_name / f"{name}.parquet")["nav"]


def ret_of(nav: pd.Series, per: tuple) -> pd.Series:
    r = nav.pct_change()
    r.iloc[0] = nav.iloc[0] - 1.0
    return r.loc[per[0]: per[1]]


def sr_of(nav: pd.Series, per: tuple) -> float:
    r = ret_of(nav, per)
    return sharpe(r - rf().reindex(r.index).fillna(0.0), 365) if len(r) > 30 else np.nan


def stats(set_name: str, name: str, per: tuple) -> dict:
    nav = nav_of(set_name, name)
    r = ret_of(nav, per)
    g = float((1 + r).prod())
    yrs = len(r) / 365
    meta = json.loads((OUT / set_name / f"{name}.json").read_text(encoding="utf-8"))
    tp = OUT / set_name / "trades" / f"{name}.parquet"
    out = {"sharpe": sr_of(nav, per), "annual_return": g ** (1 / yrs) - 1 if yrs > 0 else np.nan,
           "growth_1000": 1000 * g, "max_drawdown": float(((1 + r).cumprod() / (1 + r).cumprod().cummax() - 1).min()),
           "n_trades": meta["n_trades"]}
    if tp.exists():
        t = pd.read_parquet(tp)
        t = t[(pd.to_datetime(t["entry_time"]) >= per[0]) & (pd.to_datetime(t["entry_time"]) <= per[1] + pd.Timedelta(days=1))]
        if len(t):
            out.update(trades_per_year=len(t) / yrs, win_rate=float((t["pnl"] > 0).mean()),
                       avg_trade=float(t["ret_margin"].mean()),
                       cost_share=float((t["fees"] + t["funding"].clip(lower=0)).sum() / max(1e-12, t["notional"].sum())))
    return out


def after_tax_growth(nav: pd.Series, rate: float) -> float:
    """Her takvim yılının pozitif net kazancından yıl sonunda `rate` kadar vergi (zarar devri yok; USD cinsinden —
    TL cinsinden matrah kur artışıyla daha büyük olur)."""
    v, prev = 1.0, float(nav.iloc[0])
    for _, g in nav.groupby(nav.index.year):
        gain = float(g.iloc[-1]) / prev - 1.0
        v *= 1.0 + gain - (rate * gain if gain > 0 else 0.0)
        prev = float(g.iloc[-1])
    return v


def btc200_ret(per: tuple) -> pd.Series:  # kıyas: v3 toplu çalıştırmasının BTC-200'ü (aynı veri, aynı maliyet)
    d = pd.read_parquet(cfg_path(_S, "backtests") / "v3" / "full" / "B_btc200" / "daily.parquet")["ret"]
    return d.loc[per[0]: per[1]]


def analyze(v4: dict | None = None) -> dict:
    v4 = v4 or load_v4()
    ev = v4["evaluation"]
    D = (pd.Timestamp(v4["design"][0]), pd.Timestamp(v4["design"][1]))
    H = (pd.Timestamp(v4["holdout_start"]), pd.Timestamp(v4["end"]))
    F = (D[0], H[1])
    P = {"design": D, "holdout": H, "full": F}
    names = [cfg_name(p) for p in grid(v4)]
    out: dict = {"periods": P}
    rank = design_top(v4, "spot")
    top_k = int(v4["controls"]["top_k"])
    out["rank"] = rank
    # tüm ızgara (spot) özet dağılımı
    sr = {per: np.array([sr_of(nav_of("spot", n), P[per]) for n in names]) for per in P}
    out["grid_dist"] = {per: {"median": float(np.nanmedian(v)), "q90": float(np.nanquantile(v, 0.9)),
                              "max": float(np.nanmax(v)), "frac_pos": float(np.mean(v > 0))} for per, v in sr.items()}
    out["design_vs_holdout_corr"] = float(pd.Series(sr["design"]).corr(pd.Series(sr["holdout"]), method="spearman"))
    # en iyi listesi (tasarımda seçildi)
    rows = []
    for i, n in enumerate(rank[: int(ev["toplist_size"])], start=1):
        src = "spot_ctl" if i <= top_k else "spot"
        st_d, st_h, st_f = stats(src, n, D), stats(src, n, H), stats(src, n, F)
        rows.append({"sıra": i, "yapılandırma": n, "tasarım_sharpe": st_d["sharpe"], "bekletme_sharpe": st_h["sharpe"],
                     "tam_sharpe": st_f["sharpe"], "tasarım_yıllık": st_d["annual_return"],
                     "bekletme_yıllık": st_h["annual_return"], "tam_1000": st_f["growth_1000"],
                     "tam_mdd": st_f["max_drawdown"], "işlem": st_f["n_trades"],
                     "kazanma": st_f.get("win_rate", np.nan), "ort_işlem": st_f.get("avg_trade", np.nan)})
    out["toplist"] = pd.DataFrame(rows).set_index("sıra")
    # kaldıraç / spot farkı (en iyi 10 ve medyan)
    lev = {}
    for set_name, market, L in venues(v4):
        vals = [stats(set_name, n, F) for n in rank[:top_k]]
        allsr = np.array([sr_of(nav_of(set_name, n), F) for n in names])
        lev[set_name] = {"top_sharpe_mean": float(np.nanmean([x["sharpe"] for x in vals])),
                         "top_annual_mean": float(np.nanmean([x["annual_return"] for x in vals])),
                         "top_mdd_mean": float(np.nanmean([x["max_drawdown"] for x in vals])),
                         "grid_sharpe_median": float(np.nanmedian(allsr)), "grid_frac_pos": float(np.mean(allsr > 0)),
                         "liquidations": int(sum(json.loads((OUT / set_name / f"{n}.json").read_text(encoding='utf-8'))
                                                 ["reasons"].get("liq", 0) for n in names))}
    out["leverage"] = pd.DataFrame(lev)
    # birinci yapılandırma: kriterler
    best = rank[0]
    rb = ret_of(nav_of("spot", best), F)
    out["primary"] = bs.paired_sharpe_test(rb, btc200_ret(F).reindex(rb.index).fillna(0.0), rf(),
                                           alpha=float(ev["alpha"]), cfg=_S)
    n_exp = n_experiments(_S)
    n_all = n_trials_for_dsr(n_exp, int(ev["dsr_trials_prior"]), len(names) * len(venues(v4)), _S)
    out["dsr"] = deflated_sharpe_ratio(rb, n_all, trial_sharpes_annual=sr["full"], rf=rf(), cfg=_S)
    out["dsr"]["N"] = n_all
    trials = pd.concat({n: ret_of(nav_of("spot", n), D) - rf().reindex(ret_of(nav_of("spot", n), D).index).fillna(0.0)
                        for n in names}, axis=1).dropna()
    out["pbo"] = pbo_cscv(trials.to_numpy())
    rnd = np.array([sr_of(nav_of("spot_null", f"{best}__rnd{s}"), D) for s in range(int(v4["controls"]["n_random"]))])
    s_best = sr_of(nav_of("spot_ctl", best), D)
    out["null_random_entry"] = {"p": float((1 + np.sum(rnd >= s_best)) / (len(rnd) + 1)), "mean": float(np.nanmean(rnd)),
                                "q95": float(np.nanquantile(rnd, 0.95)), "obs": s_best}
    rg = []
    for r in range(int(v4["controls"]["random_grids"])):
        v = np.array([sr_of(nav_of(f"spot_rgrid{r}", n), D) for n in names])
        hv = np.array([sr_of(nav_of(f"spot_rgrid{r}", n), H) for n in names])
        rg.append({"best_design": float(np.nanmax(v)), "best_holdout": float(hv[int(np.nanargmax(v))]),
                   "median_design": float(np.nanmedian(v))})
    out["random_grids"] = rg
    ctl = {k: sr_of(nav_of("spot_ctl", f"{best}__{k}"), D) for k in ("lag1", "leak1", "cost2")}
    ctl["cost2_holdout"] = sr_of(nav_of("spot_ctl", f"{best}__cost2"), H)
    out["controls"] = ctl
    # maliyet ve vergi duyarlılığı (en iyi top_k, tam dönem, 1.000 $'ın vardığı değer)
    tax_rows = {}
    for n in rank[:top_k]:
        row = {"temel": stats("spot_ctl", n, F)["growth_1000"],
               "BNB indirimi": stats("spot_ctl", f"{n}__bnb", F)["growth_1000"],
               "işlem vergisi %0,03": stats("spot_ctl", f"{n}__txtax", F)["growth_1000"],
               "2× maliyet": stats("spot_ctl", f"{n}__cost2", F)["growth_1000"]}
        nav = nav_of("spot_ctl", n).loc[F[0]: F[1]]
        for rate in v4["costs"]["tr_gain_tax_rates"]:
            row[f"yıllık kazanç vergisi %{rate * 100:.0f}"] = 1000 * after_tax_growth(nav, float(rate))
        tax_rows[n] = row
    out["tax_table"] = pd.DataFrame(tax_rows).T
    g = v4["grid"]
    p_best = next(q for q in grid(v4) if cfg_name(q) == best)
    nb = []
    for k, vals in g.items():
        i = vals.index(p_best[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                q = {**p_best, k: vals[j]}
                nb.append((cfg_name(q), sr_of(nav_of("spot", cfg_name(q)), D)))
    out["neighbors"] = nb
    h_best = sr_of(nav_of("spot_ctl", best), H)
    out["criteria"] = [
        (1, "Bekletmede net Sharpe > 0 (1× ve 2× maliyet)", f"{h_best:.2f} / {ctl['cost2_holdout']:.2f}",
         bool(h_best > 0 and ctl["cost2_holdout"] > 0)),
        (2, "Tam dönemde BTC-200'ü yener (p < 0,05)",
         f"ΔSharpe {out['primary']['sharpe_diff']:.2f}, p = {out['primary']['p_value']:.4f}", bool(out["primary"]["passed"])),
        (3, "DSR ≥ 0,95", f"{out['dsr']['dsr']:.3f} (N = {n_all})", bool(out["dsr"]["dsr"] >= 0.95)),
        (4, f"PBO < 0,5 ({len(names)} yapılandırma, tasarım)", f"{out['pbo']['pbo']:.3f}", bool(out["pbo"]["pbo"] < 0.5)),
        (5, "Rastgele giriş sıfırı p < 0,05 (tasarım)", f"p = {out['null_random_entry']['p']:.3f}",
         bool(out["null_random_entry"]["p"] < 0.05)),
        (6, "Gerçek ızgaranın en iyisi rastgele ızgaraların en iyisini geçer (tasarım)",
         f"{s_best:.2f} vs {', '.join(f'{x['best_design']:.2f}' for x in rg)}",
         bool(all(s_best > x["best_design"] for x in rg))),
        (7, "Pozitif kontrol: 1 saat sızıntı Sharpe ≥ temel + 1", f"{ctl['leak1']:.2f} (temel {s_best:.2f})",
         bool(ctl["leak1"] >= s_best + 1.0)),
        (8, "Komşular (tasarım) Sharpe > 0", f"en düşük {min(x[1] for x in nb):.2f}", bool(all(x[1] > 0 for x in nb))),
    ]
    out["best"] = best
    return out


def write_report(res: dict, v4: dict | None = None, run_rec: dict | None = None, out_dir: Path | None = None) -> Path:
    v4 = v4 or load_v4()
    P = res["periods"]
    crit = res["criteria"]
    passed = all(c[3] for c in crit if c[0] != 7)
    L = ["# Araştırma v4 — gün içi momentum (spot ve kaldıraçlı vadeli)", "",
         f"Tasarım {P['design'][0].date()} – {P['design'][1].date()}, kirlenmiş bekletme {P['holdout'][0].date()} – "
         f"{P['holdout'][1].date()}. Ön kayıt `PREREGISTRATION_v4.md` (tag `prereg-v4`). {len(grid(v4))} yapılandırma × "
         f"{len(venues(v4))} piyasa/kaldıraç; komisyon, kayma ve vergi dahil, nakit %0.", ""]
    if run_rec:
        L += [f"Toplu çalıştırma: {run_rec.get('started_utc')} → {run_rec.get('finished_utc', 'yarıda')} UTC, "
              f"{run_rec.get('n_runs', '—')} çalıştırma, commit `{str(run_rec.get('code_commit'))[:7]}` "
              "(`lock/V4_run.json`).", ""]
    L += ["## Sonuç", "", f"En iyi yapılandırma (tasarımda seçildi): `{res['best']}` → **"
          f"{'gölge mod adayı' if passed else 'reddedildi'}**.", "",
          "| # | Kriter | Değer | Durum |", "| --- | --- | --- | --- |"]
    for k, name, txt, ok in crit:
        L.append(f"| {k} | {name} | {txt} | {_ok(ok)} |")
    gd = res["grid_dist"]
    L += ["", "## Izgaranın tamamı (spot, 1×)", "",
          "| Dönem | medyan Sharpe | %90 | en iyi | Sharpe > 0 olan pay |", "| --- | --- | --- | --- | --- |"]
    for per, x in gd.items():
        L.append(f"| {per} | {x['median']:.2f} | {x['q90']:.2f} | {x['max']:.2f} | %{x['frac_pos'] * 100:.0f} |")
    L += ["", f"Tasarım ve bekletme Sharpe'larının sıra korelasyonu (Spearman): {res['design_vs_holdout_corr']:.2f} "
          "(tasarımda iyi olan bekletmede de iyi mi?).", "",
          "## En iyi liste (tasarım dönemi net Sharpe'ına göre)", "",
          to_markdown(_fmt_toplist(res["toplist"]), 2, set()), "",
          "`tam_1000`: tam dönemde 1.000 $'ın vardığı değer; `kazanma` ve `ort_işlem` (marjine göre net işlem getirisi) "
          f"yalnızca en iyi {int(v4['controls']['top_k'])} için.", "",
          f"## Kaldıraç ve spot farkı (en iyi {int(v4['controls']['top_k'])} yapılandırmanın ortalaması, tam dönem)", "",
          to_markdown(res["leverage"], 3, {"top_annual_mean", "top_mdd_mean", "grid_frac_pos"}), "",
          f"## Maliyet ve vergi duyarlılığı (en iyi {int(v4['controls']['top_k'])}, tam dönemde 1.000 $ →)", "",
          "Türkiye'de kripto için yürürlükte işlem vergisi veya stopaj yok (2026'da önerildi, Mart'ta Meclis'te "
          "çıkarıldı); kazancın gelir vergisindeki niteliği belirsiz. Yıllık kazanç vergisi senaryoları USD üzerinden, "
          "zarar devri olmadan hesaplandı (reports/V4_fees_tax.md).", "",
          to_markdown(res["tax_table"].map(lambda x: f"{x:,.0f}"), 0, set()), "",
          "## Kontroller ve sıfırlar (en iyi yapılandırma, tasarım)", ""]
    c = res["controls"]
    nr = res["null_random_entry"]
    L += [f"- 1 saat gecikme Sharpe {c['lag1']:.2f}; 1 saat sızıntı {c['leak1']:.2f}; 2× maliyet {c['cost2']:.2f} "
          f"(bekletmede {c['cost2_holdout']:.2f}).",
          f"- Rastgele giriş (aynı kâr al/zarar kes/süre, aynı giriş sıklığı, {int(v4['controls']['n_random'])} tekrar): "
          f"ortalama Sharpe {nr['mean']:.2f}, %95 {nr['q95']:.2f}; gözlenen {nr['obs']:.2f}, p = {nr['p']:.3f}.",
          "- Rastgele sinyalli ızgaralar: " + "; ".join(
              f"en iyi tasarım {x['best_design']:.2f} → bekletmede {x['best_holdout']:.2f} (medyan {x['median_design']:.2f})"
              for x in res["random_grids"]) + ".",
          "- Komşular: " + ", ".join(f"{n} {s:.2f}" for n, s in res["neighbors"]) + ".", ""]
    out = Path(out_dir or cfg_path(_S, "reports")) / "V4_intraday_momentum.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    return out


def _fmt_toplist(t: pd.DataFrame) -> pd.DataFrame:
    t = t.copy()
    for c in ("tasarım_yıllık", "bekletme_yıllık", "tam_mdd", "kazanma", "ort_işlem"):
        t[c] = [("—" if not np.isfinite(x) else f"{x * 100:.1f}%") for x in t[c].astype(float)]
    t["tam_1000"] = [f"{x:,.0f}" for x in t["tam_1000"]]
    t["işlem"] = t["işlem"].astype(int).astype(str)
    return t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m trend.intraday.study")
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    if a.cmd == "run":
        print(json.dumps(run_batch(a.workers), indent=1))
    else:
        rp = g12.lock_dir(load_settings()) / "V4_run.json"
        rec = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else None
        print("rapor →", write_report(analyze(), run_rec=rec))
    print(f"bitti: {time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
