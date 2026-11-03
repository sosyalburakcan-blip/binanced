"""G12: kilit ve tek seferlik doğrulama (SPEC "Sıralama", PREREGISTRATION §7–§8).

    python -m trend.research.g12 snapshot --lock-date 2026-11-01  # veri anlık görüntüsü özetlenir → lock/
    python -m trend.research.g12 verify                           # anlık görüntü özetleri yeniden hesaplanır
    python -m trend.research.g12 run                              # ön kayıtlı toplu çalıştırma, tam dönem — BİR KEZ
    python -m trend.research.g12 report                           # reports/G12_lock_validation.md (önbellekten)
    python -m trend.research.g12 golden [--check]                 # altın kayıt yazılır / yeniden üretilip karşılaştırılır
    python -m trend.research.g12 dryrun --out DIR                 # kuru prova: kilit = geliştirme sonu

Tek seferlik kural: `run` çalıştırmalara başlamadan önce `lock/G12_run.json` yazılır; dosya varsa `run` reddedilir.
`run` yalnızca temiz bir çalışma ağacında (işlenmemiş değişiklik yok) ve anlık görüntü özetleri tutarken çalışır;
kullanılan commit kayda yazılır. Raporlar önbellekteki çalıştırmalardan yeniden üretilebilir (çalıştırmayı
tekrarlamaz). Çalıştırmadan sonra sonucu etkileyen bir değişiklik yapılırsa doğrulama dönemi artık doğrulama sayılmaz.

Varsayımlar (experiments.md satır 17, çalıştırmadan önce yazıldı):
- Kilit tarihi = anlık görüntüdeki son tam günlük mum.
- Anlık görüntü: birleştirilmiş 1d/1h seriler, kalite işaretleri, meta tablolar (hazine bonosu dahil), evren
  dosyaları ve indirme defteri; ham zip ve temiz seriler defterdeki checksum'larla temsil edilir.
- Kriter dönemleri: 1, 2, 6, 7, 9 tam dönem; 3, 5, 8 geliştirme (ön kayıt sıralaması); 4 doğrulama. Tam dönem
  sıfır hipotezleri, kontroller ve PBO bilgi olarak raporlanır.
- Düşüş ufku tablosu T0 ve BTC-200 için tam dönem getirilerinden.
- Altın kayıt: T0 ve BTC-200'ün tam dönem karar, dolum ve günlük kayıtları; ondalık alanlarda göreli 1e-9 tolerans.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from trend.backtest.engine import BacktestResult
from trend.config import ROOT, load_settings, path as cfg_path
from trend.evaluation import bootstrap as bs
from trend.evaluation.report import to_markdown
from trend.research import g10
from trend.research.g10 import _fmt, _ok, metrics_table, period_ret, sr
from trend.research.inputs import load_inputs
from trend.research.runner import PanelSet, RunSpec, load_run, run_many, run_one

_S = load_settings()
SNAPSHOT_KEYS = ("merged", "quality_flags", "meta", "universe", "ledger")
HASHED_FILES = ("settings.yaml", "PREREGISTRATION.md", "pyproject.toml", "uv.lock")
GOLDEN_RUNS = ("T0", "B_btc200")
GOLDEN_RTOL, GOLDEN_ATOL = 1e-9, 1e-12
DEV_IDENTICAL_TOL = 1e-12
HASH_THREADS = 8
DRY_VALIDATION_START = "2023-07-01"   # kuru prova: geliştirme döneminin son yarısı "doğrulama" gibi işlenir


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT).stdout.strip()


def lock_dir(cfg: dict) -> Path:
    """Kilit kayıtları `backtests` ile aynı kökte (`lock/`); kuru provada çıktı dizininin altında."""
    return cfg_path(cfg, "backtests").parent / "lock"


def golden_dir(cfg: dict) -> Path:
    return cfg_path(cfg, "backtests").parent / "golden"


def _write_json(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")


def read_lock(cfg: dict) -> dict:
    p = lock_dir(cfg) / "LOCK.json"
    if not p.exists():
        raise SystemExit(f"kilit kaydı yok: {p} (önce `snapshot`)")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------------------
# Veri anlık görüntüsü


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def snapshot_files(cfg: dict) -> list[Path]:
    out: list[Path] = []
    for key in SNAPSHOT_KEYS:
        p = cfg_path(cfg, key)
        out += [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file())
    return out


def build_manifest(cfg: dict) -> pd.DataFrame:
    files = snapshot_files(cfg)
    with ThreadPoolExecutor(HASH_THREADS) as ex:
        hashes = list(ex.map(sha256_file, files))
    return pd.DataFrame({"path": [_rel(f) for f in files], "bytes": [f.stat().st_size for f in files],
                         "sha256": hashes})


def manifest_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, lineterminator="\n").encode("utf-8")


def data_coverage(cfg: dict) -> dict:
    out = {}
    for iv in ("1d", "1h"):
        files = sorted((cfg_path(cfg, "merged") / iv).glob("*.parquet"))
        s = pd.Series([pq.read_table(f, columns=["open_time"]).column(0).to_pandas().max() for f in files])
        out[iv] = {"files": len(s), "last_open_time": str(s.max()), "files_at_last": int((s == s.max()).sum())}
    return out


def snapshot(cfg: dict, lock_date: str) -> dict:
    """Kilit tarihini doğrular, anlık görüntüyü özetler ve `lock/LOCK.json` + `lock/data_manifest.csv` yazar."""
    ld = lock_dir(cfg)
    if (ld / "LOCK.json").exists():
        raise SystemExit(f"kilit zaten var: {ld / 'LOCK.json'}")
    lock = pd.Timestamp(lock_date)
    cov = data_coverage(cfg)
    last_1d, last_1h = pd.Timestamp(cov["1d"]["last_open_time"]), pd.Timestamp(cov["1h"]["last_open_time"])
    if lock > last_1d or last_1h < lock + pd.Timedelta(hours=23):
        raise SystemExit(f"kilit tarihi {lock.date()} veriyle kapanmıyor (son 1d {last_1d}, son 1h {last_1h})")
    t0 = time.perf_counter()
    man = build_manifest(cfg)
    b = manifest_bytes(man)
    ld.mkdir(parents=True, exist_ok=True)
    (ld / "data_manifest.csv").write_bytes(b)
    rec = {"lock_date": str(lock.date()), "created_utc": _now(), "head_at_snapshot": git("rev-parse", "HEAD"),
           "prereg_tag": "prereg-v1", "data_manifest": _rel(ld / "data_manifest.csv"),
           "data_manifest_sha256": sha256_bytes(b), "n_files": int(len(man)), "bytes": int(man["bytes"].sum()),
           "snapshot_keys": list(SNAPSHOT_KEYS), "coverage": cov,
           "hashes": {f: sha256_file(ROOT / f) for f in HASHED_FILES if (ROOT / f).exists()},
           "hash_seconds": round(time.perf_counter() - t0, 1)}
    _write_json(ld / "LOCK.json", rec)
    return rec


def verify_snapshot(cfg: dict) -> dict:
    lk = read_lock(cfg)
    mp = lock_dir(cfg) / "data_manifest.csv"
    if sha256_file(mp) != lk["data_manifest_sha256"]:
        return {"ok": False, "n_files": None, "n_changed": None, "changed": ["data_manifest.csv özeti tutmuyor"]}
    old = pd.read_csv(mp)
    new = build_manifest(cfg)
    m = old.merge(new, on="path", how="outer", suffixes=("_lock", "_now"), indicator=True)
    bad = m[(m["_merge"] != "both") | (m["sha256_lock"] != m["sha256_now"])]
    return {"ok": bad.empty, "n_files": int(len(old)), "n_changed": int(len(bad)), "changed": bad["path"].tolist()[:20]}


# ---------------------------------------------------------------------------------------------------------------
# Tek seferlik toplu çalıştırma


def run_batch(cfg: dict, workers: int | None = None, allow_rerun: bool = False, dry: bool = False) -> dict:
    lk = read_lock(cfg)
    rp = lock_dir(cfg) / "G12_run.json"
    prev = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else None
    if not dry:
        if prev is not None and not allow_rerun:
            raise SystemExit(f"G12 toplu çalıştırması zaten yapıldı ({prev.get('started_utc')}); doğrulama dönemi "
                             "harcandı. Raporu yeniden üretmek için `report` kullanın.")
        dirty = git("status", "--porcelain", "--untracked-files=no")
        if dirty:
            raise SystemExit("çalışma ağacında işlenmemiş değişiklik var; kilit commit'i temiz olmalı:\n" + dirty)
        v = verify_snapshot(cfg)
        if not v["ok"]:
            raise SystemExit(f"anlık görüntü kilitle tutmuyor ({v['n_changed']} dosya): {v['changed']}")
    specs = g10.all_specs(cfg)
    rec = {"started_utc": _now(), "code_commit": git("rev-parse", "HEAD"), "lock_date": lk["lock_date"],
           "data_manifest_sha256": lk.get("data_manifest_sha256"), "dry_run": dry, "n_specs": len(specs) + 1,
           "specs": [s.name for s in specs] + ["B_btcvol"]}
    if prev is not None:
        rec["previous_runs"] = [*prev.get("previous_runs", []), {k: v for k, v in prev.items() if k != "previous_runs"}]
        rec["validation_spent_before"] = True
    _write_json(rp, rec)   # çalıştırmadan ÖNCE: yarıda kalsa da doğrulama dönemi harcanmış sayılır
    t0 = time.perf_counter()
    inp = load_inputs("full", lk["lock_date"], cfg=cfg)
    panels = g10.build_panels(inp, specs)
    timing = run_many(specs, inp, panels, workers, reuse=False)
    timing.update(run_many(g10.phase2_specs(inp), inp, {"real": panels["real"]}, 1, reuse=False))
    rec.update(finished_utc=_now(), n_runs=len(timing), worker_seconds=round(sum(timing.values()), 1),
               wall_seconds=round(time.perf_counter() - t0, 1))
    _write_json(rp, rec)
    return rec


# ---------------------------------------------------------------------------------------------------------------
# Analiz


def dev_consistency(inp, dev_root: Path | None = None) -> pd.DataFrame:
    """Tam dönem çalıştırmalarının geliştirme dönemi kısmı, G10 çalıştırmalarıyla (nedensellik: birebir aynı olmalı;
    kontrol panelleri ve B_btcvol tüm dönem üzerinden kurulduğu için farklıdır)."""
    dev_root = dev_root or cfg_path(_S, "backtests") / "development"
    full_root = cfg_path(inp.cfg, "backtests") / inp.stage
    d0, d1 = (pd.Timestamp(x) for x in inp.cfg["periods"]["development"])
    rows = {}
    for d in sorted(p for p in full_root.iterdir() if (p / "daily.parquet").exists()):
        q = dev_root / d.name / "daily.parquet"
        if not q.exists():
            continue
        a = pd.read_parquet(q)["ret"].loc[d0:d1]
        b = pd.read_parquet(d / "daily.parquet")["ret"].loc[d0:d1].reindex(a.index)
        spec = json.loads((d / "spec.json").read_text(encoding="utf-8"))["spec"]
        by_whole_period = not (spec["panel"] == "real" or spec["panel"].startswith("h")) or d.name == "B_btcvol"
        rows[d.name] = {"panel": spec["panel"], "days": int(len(a)), "missing": int(b.isna().sum()),
                        "max_abs_diff": float((a - b).abs().max()), "built_on_whole_period": by_whole_period}
    return pd.DataFrame(rows).T


def dev_summary() -> dict:
    p = cfg_path(_S, "backtests") / "development" / "summary.json"
    return json.loads(p.read_text(encoding="utf-8"))


def analyze_g12(inp, n_seeds: int = g10.N_CONTROL_SEEDS, verbose: bool = True, dev_root: Path | None = None,
                dev_sum: dict | None = None) -> dict:
    cfg = inp.cfg
    res = g10.analyze(inp, n_seeds, verbose=verbose, focus="full")
    periods = res["periods"]
    val, full = periods["validation"], periods["full"]
    grid = ["T0"] + [s.name for s in g10.grid_specs(cfg)]
    var = [s.name for s in g10.variant_specs()]
    res["val_grid"] = metrics_table(inp, grid, val, ["sharpe", "annual_return", "max_drawdown", "avg_gross_exposure"])
    res["val_variants"] = metrics_table(inp, ["T0"] + var, val, ["sharpe", "annual_return", "max_drawdown",
                                                                "avg_gross_exposure", "cost_annual"])
    res["val_paired"] = bs.paired_sharpe_test(period_ret(inp, "T0", val), period_ret(inp, "B_btc200", val), inp.rf,
                                              cfg=cfg)
    res["crit4"] = {"T0": sr(inp, "T0", val), "T6_cost2": sr(inp, "T6_cost2", val)}
    states = {}
    for n in ("T0", "T6_cost2", "D_T0_nostop"):
        r = load_run(inp, n)
        d = r.daily.loc[val[0]: val[1]]
        c = r.cycles
        opened = c[pd.to_datetime(c["open_date"]) >= val[0]] if len(c) else c
        states[n] = {"days": int(len(d)), "stop_days": int((d["hard_stop"] > 0).sum()),
                     "avg_gross_exposure": float(d["gross_exposure"].mean()),
                     "days_invested": int((d["gross_exposure"] > 0).sum()), "cycles_opened": int(len(opened)),
                     "return": float(d["nav"].iloc[-1] / r.daily["nav"].loc[:val[0]].iloc[-2] - 1)
                     if len(r.daily.loc[:val[0]]) > 1 else np.nan}
    vs = pd.DataFrame(states).T
    counts = ["days", "stop_days", "days_invested", "cycles_opened"]
    vs[counts] = vs[counts].astype(int)
    res["val_states"] = vs
    res["dd_horizon_btc200"] = bs.drawdown_horizon_table(period_ret(inp, "B_btc200", full), cfg=cfg)
    res["consistency"] = dev_consistency(inp, dev_root)
    res["dev"] = dev_sum or dev_summary()
    return res


def criteria(res: dict) -> list[tuple]:
    """(#, kriter, dönem, değer, geçti) — dönemler experiments.md satır 17'deki plana göre."""
    dev, p, d = res["dev"], res["paired"], res["dsr"]
    g = res["grid"].drop(columns="T0")
    k7 = bool((g.loc["sharpe"] > 0).all() and (g.loc["sharpe_vs_base"] >= 0.5).all())
    c4 = res["crit4"]
    ctl = [c[3] for c in res["controls"]]
    t5 = float(res["variants"].loc["sharpe", "T5_20"])
    m6 = res["mdd_vs_ew"]
    return [
        (1, "BTC-200'ü Sharpe'ta eşleştirilmiş bootstrap ile %95 güvenle yener", "tam",
         f"ΔSharpe {p['sharpe_diff']:.2f}, p = {p['p_value']:.4f}", bool(p["passed"])),
        (2, "DSR ≥ 0,95", "tam", f"{d['dsr']:.3f}", bool(d["dsr"] >= 0.95)),
        (3, "PBO < 0,5", "geliştirme", f"{dev['pbo']:.3f} (tam dönem {res['pbo']['pbo']:.3f}, bilgi)",
         bool(dev["pbo"] < 0.5)),
        (4, "Net Sharpe > 0, 1× ve 2× maliyet", "doğrulama", f"{_fmt(c4['T0'])} / {_fmt(c4['T6_cost2'])}",
         bool(c4["T0"] > 0 and c4["T6_cost2"] > 0)),
        (5, "İki sıfır hipotezi Sharpe'ta %95", "geliştirme",
         "p = " + ", ".join(f"{x:.4f}" for x in dev["null_p"].values()) + " (tam dönem "
         + ", ".join(f"{x['p_sharpe']:.4f}" for x in res["nulls"].values()) + ", bilgi)",
         bool(all(x < 0.05 for x in dev["null_p"].values()))),
        (6, "Bootstrap medyan MDD < evren EW'nin yarısı", "tam",
         f"{m6['median_mdd_strategy'] * 100:.1f}% / {m6['median_mdd_other'] * 100:.1f}%", bool(m6["passed"])),
        (7, "Tüm komşularda Sharpe > 0 ve ≥ temelin %50'si", "tam",
         f"en düşük {g.loc['sharpe'].min():.2f} (oran {g.loc['sharpe_vs_base'].min():.2f})", k7),
        (8, "Tüm negatif kontroller beklendiği gibi", "geliştirme",
         f"{dev['controls_ok']}/{dev['controls_n']} (tam dönem {sum(1 for x in ctl if x)}/"
         f"{sum(1 for x in ctl if x is not None)}, bilgi)", bool(dev["controls_ok"] == dev["controls_n"])),
        (9, "%20 delist cezasıyla net Sharpe > 0", "tam", f"{t5:.2f}", bool(t5 > 0)),
    ]


# ---------------------------------------------------------------------------------------------------------------
# Rapor


PCT = {"annual_return", "annual_vol", "vol_minus_target", "avg_gross_exposure", "avg_cash_share", "max_drawdown",
       "time_under_water_frac", "turnover_annual", "cost_annual", "win_rate", "top10pct_profit_share",
       "worst_1d_at_max_exposure", "worst_3d_at_max_exposure", "annual_return_simple", "cash_drag_annual",
       "annual_return_usd", "usdt_usd_min", "usdt_usd_max", "return"}


def write_report(inp, res: dict, lk: dict, run_rec: dict | None, golden: dict | None) -> Path:
    cfg = inp.cfg
    P = res["periods"]
    val, full = P["validation"], P["full"]
    crit = criteria(res)
    c1 = crit[0][4]
    phase2 = all(c[4] for c in crit[1:])
    sat = res["satellite"]
    L = ["# G12 — Kilit ve doğrulama", "",
         f"Kilit tarihi **{lk['lock_date']}**. Doğrulama dönemi {val[0].date()} – {val[1].date()}, tam dönem "
         f"{full[0].date()} – {full[1].date()}. Ön kayıt `prereg-v1`. Nakit getirisi temel varsayım %0; Sharpe ABD "
         "3 aylık hazine bonosu üzerinden, √365.", "",
         "> Doğrulama dönemi tasarımı etkileyen olayları (10 Ekim 2025, 2026 ayı piyasası) içerdiği için gerçek bir "
         "test değildir; akıl sağlığı kontrolüdür. Tek gerçek test ileriye dönük 12 aylık gölge moddur.", ""]

    # --- kilit kaydı ---
    L += ["## Kilit kaydı", "", "| Alan | Değer |", "| --- | --- |",
          f"| Kilit tarihi (son tam günlük mum) | {lk['lock_date']} |",
          f"| Anlık görüntü (UTC) | {lk.get('created_utc', '—')} |",
          f"| Özetlenen dosya | {lk.get('n_files', '—')} dosya, {(lk.get('bytes') or 0) / 1e9:.2f} GB "
          f"({', '.join(lk.get('snapshot_keys', []))}) |",
          f"| `lock/data_manifest.csv` SHA-256 | `{lk.get('data_manifest_sha256', '—')}` |"]
    for f, h in lk.get("hashes", {}).items():
        L.append(f"| `{f}` SHA-256 | `{h}` |")
    if run_rec:
        L += [f"| Toplu çalıştırma | {run_rec.get('started_utc')} → {run_rec.get('finished_utc', 'yarıda kaldı')} UTC, "
              f"{run_rec.get('n_runs', '—')} çalıştırma |",
              f"| Çalıştırmanın commit'i | `{run_rec.get('code_commit')}` |"]
        if run_rec.get("previous_runs"):
            L.append(f"| **Önceki çalıştırma** | {len(run_rec['previous_runs'])} kez; doğrulama dönemi harcanmıştı |")
    L += ["", "Toplu çalıştırma bir kez yapıldı ve `lock/G12_run.json`'a yazıldı (kayıt çalıştırmadan önce açılır). "
          "Anlık görüntü `python -m trend.research.g12 verify` ile yeniden doğrulanır.", ""]

    # --- geliştirme döneminin yeniden üretimi ---
    cs = res["consistency"]
    causal = cs[~cs["built_on_whole_period"].astype(bool)]
    other = cs[cs["built_on_whole_period"].astype(bool)]
    n_same = int((causal["max_abs_diff"] <= DEV_IDENTICAL_TOL).sum())
    L += ["## Geliştirme döneminin yeniden üretimi (geleceği görme kontrolü)", "",
          f"Tam dönem çalıştırmalarının {P['development'][0].date()} – {P['development'][1].date()} kısmı G10 "
          f"çalıştırmalarıyla karşılaştırıldı. Gerçek ve T8 panellerindeki {len(causal)} çalıştırmanın **{n_same}**'i "
          f"birebir aynı (günlük getiri farkı ≤ {DEV_IDENTICAL_TOL:g}); en büyük fark "
          f"{causal['max_abs_diff'].max():.2e}. Sonradan gelen veri geçmiş kararları değiştirmiyor."]
    if n_same < len(causal):
        bad = causal[causal["max_abs_diff"] > DEV_IDENTICAL_TOL]
        L += ["", "**Farklı çıkanlar (incelenmeli):**", "", to_markdown(bad, 6, set()), ""]
    L += ["", f"Kontrol panelleri (karıştırma, GARCH) ve B_btcvol tüm dönem üzerinden kurulduğu için farklıdır "
          f"({len(other)} çalıştırma; tasarım gereği).", ""]

    # --- geç/kal ---
    L += ["## Geç/kal kararı", "",
          "Kriter dönemleri çalıştırmadan önce experiments.md satır 17'ye yazıldı.", "",
          "| # | Kriter | Dönem | Değer | Durum |", "| --- | --- | --- | --- | --- |"]
    for k, name, per, txt, ok in crit:
        L.append(f"| {k} | {name} | {per} | {txt} | {_ok(ok)} |")
    L += ["", "**Karar (ön kayıt kuralı):**", ""]
    if c1:
        L.append("- Birincil hipotez kabul edildi: alt-coin sistemi BTC-200'ü tam dönemde %95 güvenle yeniyor.")
    else:
        L += ["- Birincil hipotez **reddedildi**. Varsayılan karar **BTC-200** (veya hiç işlem yapmamak); ana "
              "pozisyon BTC-200'dür.",
              f"- Uydu payı kuralı (tam dönem): 0,5 × SR_T0 = {sat['lhs']:.3f}, ρ × SR_BTC200 = {sat['rhs']:.3f} "
              f"(SR_T0 {sat['sr_t0']:.2f}, SR_BTC200 {sat['sr_btc200']:.2f}, ρ = {sat['rho']:.2f}) → alt-coin "
              f"sistemine **%{sat['weight'] * 100:.0f}** pay."]
    L.append(f"- Kriter 2–9: {sum(1 for c in crit[1:] if c[4])}/8 geçti → alt-coin sistemi Aşama 2'ye "
             f"{'**geçebilir**' if phase2 else '**geçemez**'}.")
    L.append("- Bu karardan sonra parametre veya kod değişikliği yapılmaz (SPEC \"Sıralama\").")
    L.append("")

    # --- doğrulama dönemi ---
    pct = PCT
    L += ["## Doğrulama dönemi", "", to_markdown(res["core"]["validation"], 3, pct), "",
          "T0'ın doğrulama dönemindeki durumu (sert sınır, maruziyet):", "",
          to_markdown(res["val_states"], 3, {"avg_gross_exposure", "return"}), ""]
    st = res["val_states"].loc["T0"]
    if st["stop_days"] >= 0.9 * st["days"]:
        L += ["T0 doğrulama döneminin tamamına yakınında −%35 sert sınırda kilitli: yeni alım yapamıyor, pozisyonlar "
              "sinyalle kapandıktan sonra nakitte (%0 getiri) bekliyor ve portföy zirvenin −%25'ine dönemediği için "
              "sınır kalkmıyor (G10 tanısı). Bu nedenle doğrulama Sharpe'ı hazine bonosunun altında kalan sıfır "
              "getiriden gelir; büyüklüğü anlamsız, işareti negatiftir.", ""]
    L += ["Izgara (doğrulama):", "", to_markdown(res["val_grid"], 3, pct), "",
          "Varyantlar (doğrulama):", "", to_markdown(res["val_variants"], 3, pct), ""]
    vp = res["val_paired"]
    L += [f"T0 − BTC-200, doğrulama (bilgi): ΔSharpe {_fmt(vp['sharpe_diff'])}, p = {vp['p_value']:.4f} "
          f"(BTC-200 Sharpe {_fmt(vp['sharpe_benchmark'])}).", ""]

    # --- tam dönem ---
    L += ["## Tam dönem", "", to_markdown(res["core"]["full"], 3, pct), ""]
    for k in [k for k in P if k.startswith("regime")]:
        L += [f"### {k}", "", to_markdown(res["core"][k], 3, pct), ""]
    ypct = {"return", "turnover", "cost"}
    L += ["### Yıl yıl (T0)", "", to_markdown(res["t0_full"]["tables"]["yearly"].T, 3, ypct), "",
          "BTC-200:", "", to_markdown(res["b200_full"]["tables"]["yearly"].T, 3, ypct), ""]
    p, d, b, pb = res["paired"], res["dsr"], res["boot_sr"], res["pbo"]
    L += ["### Birincil hipotez ve istatistik", "",
          f"- **T0 − BTC-200 (eşleştirilmiş durağan blok bootstrap, 10.000 yol):** ΔSharpe {p['sharpe_diff']:.2f}, "
          f"%95 GA {p['ci95_diff'][0]:.2f}…{p['ci95_diff'][1]:.2f}, tek yönlü p = {p['p_value']:.4f} "
          f"(T0 {b['sharpe']:.2f}, BTC-200 {p['sharpe_benchmark']:.2f})."]
    for k, v in res["paired_regimes"].items():
        L.append(f"  - {k}: ΔSharpe {v['sharpe_diff']:.2f}, p = {v['p_value']:.4f}.")
    L += [f"- **DSR:** N = max(100, deneme {d['n_experiments']} + ızgara {d['grid_size']} + varyant "
          f"{d['n_variants']}) = {d['n_trials_used']}; beklenen en büyük Sharpe {d['sr0_annual']:.2f}; T0 Sharpe "
          f"{d['sharpe_annual']:.2f} (SH {d['sharpe_se_annual']:.2f}); DSR {d['dsr']:.3f}, PSR(0) {d['psr0']:.3f}.",
          f"- **T0 Sharpe bootstrap:** %95 GA {b['ci95'][0]:.2f}…{b['ci95'][1]:.2f}.",
          f"- **PBO (tam dönem, bilgi):** {pb['pbo']:.3f} (geliştirme {res['dev']['pbo']:.3f}).",
          f"- **Minimum kayıt uzunluğu:** Sharpe {res['mintrl']['sharpe_annual']:.2f} ile "
          f"{_fmt(res['mintrl']['min_trl_years'], 1)} yıl; mevcut {res['mintrl']['track_years']:.1f} yıl."]
    m6 = res["mdd_vs_ew"]
    L += [f"- **En büyük düşüş medyanı:** T0 {m6['median_mdd_strategy'] * 100:.1f}%, evren eşit ağırlıklı al-tut "
          f"{m6['median_mdd_other'] * 100:.1f}% (yolların {m6['frac_paths_passing'] * 100:.0f}%'ında yarısından küçük).",
          ""]
    L += ["### Düşüş ufku tablosu (kilit; canlı durdurma kuralı bunu kullanır)", "",
          "T0 (tam dönem getirileri; 2023-08'den sonraki uzun nakit dönemi tabloyu iyimser yapar):", "",
          to_markdown(res["dd_horizon"], 3, {"dd_q95", "dd_median", "dd_mean"}), "",
          "BTC-200 (varsayılan karar):", "",
          to_markdown(res["dd_horizon_btc200"], 3, {"dd_q95", "dd_median", "dd_mean"}), ""]
    L += ["### Izgara ve varyantlar (tam dönem)", "",
          to_markdown(res["grid"], 3, {"annual_return", "annual_vol", "max_drawdown", "turnover_annual"}), "",
          to_markdown(res["variants"], 3, {"annual_return", "max_drawdown", "avg_gross_exposure", "cost_annual"}), "",
          "T10 (BTC-200 çekirdek + T0 uydu, aylık):", "",
          to_markdown(res["t10"], 3, {"annual_return", "max_drawdown"}), ""]
    be = res["t6_breakeven"]
    L += ["**T6 karşı taraf stresi:** T0 yıllık aşırı log getirisi "
          f"{be['log_excess']['t0'] * 100:.1f}%, BTC-200 {be['log_excess']['btc200'] * 100:.1f}%. "
          + "; ".join(f"L = %{k[1:]}: getiriyi sıfırlayan p* = {v['p_zero']:.3f}/yıl, BTC-200 düzeyine indiren "
                      f"p* = {v['p_btc200']:.3f}/yıl" for k, v in be.items() if k.startswith("L")) + ".", ""]
    f, ud = res["factor"], res["updown"]
    L += ["### Regresyon (HAC, tam dönem)", "",
          to_markdown(pd.DataFrame({"katsayı": f.params, "t": f.tvalues}), 3, set()), "",
          f"Yıllık alfa {f.extra['alpha_annual'] * 100:.1f}%, R² {f.r2:.2f}; β⁺ {ud.params['beta_up']:.2f}, "
          f"β⁻ {ud.params['beta_down']:.2f}.", "",
          "### Nakit getirisi duyarlılığı (tam dönem)", "", to_markdown(res["sens"], 3, pct), ""]
    if res.get("usd") is not None:
        L += ["### Dolar cinsinden (USDCUSDT'nin tersi vekil)", "", to_markdown(res["usd"], 3, pct), ""]
    L += ["### Sıfır hipotezleri ve kontroller (tam dönem, bilgi)", "",
          "| Sıfır | p (Sharpe) | sıfır ort. Sharpe | sıfır %95 |", "| --- | --- | --- | --- |"]
    for k, v in res["nulls"].items():
        L.append(f"| {k} | {v['p_sharpe']:.4f} | {v['null_mean']:.2f} | {v['null_q95']:.2f} |")
    L += ["", "| Kontrol | Beklenen | Sonuç | Beklendiği gibi |", "| --- | --- | --- | --- |"]
    for name, exp, txt, ok in res["controls"]:
        L.append(f"| {name} | {exp} | {txt} | {_ok(ok)} |")
    L += ["", f"Hazine bonosu tam dönem ortalaması: yıllık {res['tbill_mean'] * 100:.2f}%.", ""]

    # --- tanılar ---
    L += ["## Ön kayıt dışı tanılar (seçim için kullanılmaz)", "",
          "T0 sert sınır kapalı (`D_T0_nostop`), döneme göre Sharpe:", "", to_markdown(res["nostop"], 2, set()), "",
          "Sert sınır geçmişi (tam dönem):", "",
          to_markdown(res["stops"][res["stops"]["stop_days"] > 0], 3, {"max_drawdown"}), ""]

    # --- altın kayıt ---
    if golden:
        L += ["## Altın kayıt", "",
              f"T0 ve BTC-200'ün tam dönem karar, dolum ve günlük kayıtları `golden/` altında (commit "
              f"`{golden.get('code_commit', '?')[:7]}`). Her kod veya kütüphane değişikliğinden sonra "
              "`python -m trend.research.g12 golden --check` (ve `tests/test_golden_master.py`) aynı kararları "
              f"yeniden üretmeli (ondalık alanlarda göreli {GOLDEN_RTOL:g}).", "",
              "| Dosya | Satır | CSV SHA-256 |", "| --- | --- | --- |"]
        for fn, m in golden["files"].items():
            L.append(f"| `{fn}` | {m['rows']} | `{m['sha256_csv'][:16]}…` |")
        ck = golden.get("check")
        if ck:
            L += ["", f"Son kontrol ({ck['at_utc']}): {'**geçti**' if ck['ok'] else '**KALDI**'}; birebir aynı bayt: "
                  f"{sum(ck['byte_identical'].values())}/{len(ck['byte_identical'])} dosya."]
        L.append("")
    out = cfg_path(cfg, "reports") / "G12_lock_validation.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    summ = {"lock_date": lk["lock_date"], "criteria": {str(c[0]): c[4] for c in crit}, "primary_passed": c1,
            "phase2_eligible": phase2, "satellite_weight": sat["weight"], "paired_p": p["p_value"], "dsr": d["dsr"],
            "T0_sharpe_full": float(res["core"]["full"].loc["sharpe", "T0"]),
            "BTC200_sharpe_full": float(res["core"]["full"].loc["sharpe", "B_btc200"]),
            "T0_sharpe_validation": res["crit4"]["T0"], "T6_cost2_sharpe_validation": res["crit4"]["T6_cost2"],
            "BTC200_sharpe_validation": float(res["core"]["validation"].loc["sharpe", "B_btc200"]),
            "dev_identical": f"{n_same}/{len(causal)}"}
    _write_json(cfg_path(cfg, "backtests") / inp.stage / "summary.json", summ)
    return out


# ---------------------------------------------------------------------------------------------------------------
# Altın kayıt


def golden_tables(res: BacktestResult) -> dict[str, pd.DataFrame]:
    return {"decisions": res.decisions, "fills": res.fills, "daily": res.daily.reset_index()}


def canonical_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, float_format="%.17g", lineterminator="\n",
                     date_format="%Y-%m-%d %H:%M:%S").encode("utf-8")


def _gzip_write(p: Path, b: bytes) -> None:
    with open(p, "wb") as fh, gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
        gz.write(b)


def golden_rerun(cfg: dict, lock_date: str) -> tuple[dict[str, BacktestResult], object]:
    inp = load_inputs("full", lock_date, cfg=cfg, fill_modes=("vwap_00_02",), verbose=False)
    panels = {"real": PanelSet(inp.panel_1d, inp.fill_px, inp.delist)}
    specs = {s.name: s for s in [RunSpec("T0", note="temel ayar")] + g10.benchmark_specs()}
    return {n: run_one(specs[n], inp, panels) for n in GOLDEN_RUNS}, inp


def golden_write(cfg: dict) -> dict:
    lk = read_lock(cfg)
    gd = golden_dir(cfg)
    gd.mkdir(parents=True, exist_ok=True)
    runs, inp = golden_rerun(cfg, lk["lock_date"])
    man = {"lock_date": lk["lock_date"], "code_commit": git("rev-parse", "HEAD"), "created_utc": _now(),
           "data_manifest_sha256": lk.get("data_manifest_sha256"), "rtol": GOLDEN_RTOL, "atol": GOLDEN_ATOL,
           "cache_max_abs_diff": {}, "files": {}}
    for n, r in runs.items():
        cached = load_run(inp, n).ret
        man["cache_max_abs_diff"][n] = float((r.daily["ret"] - cached.reindex(r.daily.index)).abs().max())
        for k, df in golden_tables(r).items():
            b = canonical_csv(df)
            fn = f"{n}_{k}.csv.gz"
            _gzip_write(gd / fn, b)
            man["files"][fn] = {"sha256_csv": sha256_bytes(b), "rows": int(len(df))}
    _write_json(gd / "manifest.json", man)
    return man


def compare_tables(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    if list(old.columns) != list(new.columns) or len(old) != len(new):
        return {"ok": False, "why": f"şekil {old.shape} → {new.shape}", "bad_columns": [], "max_rel_diff": np.nan}
    bad, worst = [], 0.0
    for c in old.columns:
        a, b = old[c], new[c]
        if pd.api.types.is_float_dtype(a) or pd.api.types.is_float_dtype(b):
            x, y = a.to_numpy(dtype=float), b.to_numpy(dtype=float)
            same = (np.isnan(x) & np.isnan(y)) | np.isclose(x, y, rtol=GOLDEN_RTOL, atol=GOLDEN_ATOL)
            fin = np.isfinite(x) & np.isfinite(y)
            if fin.any():
                worst = max(worst, float(np.max(np.abs(x[fin] - y[fin]) / np.maximum(np.abs(x[fin]), 1.0))))
            if not same.all():
                bad.append(c)
        elif not (a.astype("string").fillna("<NA>").to_numpy() == b.astype("string").fillna("<NA>").to_numpy()).all():
            bad.append(c)
    return {"ok": not bad, "why": "", "bad_columns": bad, "max_rel_diff": worst}


def golden_check(cfg: dict, record: bool = True) -> dict:
    gd = golden_dir(cfg)
    man = json.loads((gd / "manifest.json").read_text(encoding="utf-8"))
    runs, _ = golden_rerun(cfg, man["lock_date"])
    out = {"at_utc": _now(), "code_commit": git("rev-parse", "HEAD"), "tables": {}, "byte_identical": {}}
    for n, r in runs.items():
        for k, df in golden_tables(r).items():
            fn = f"{n}_{k}.csv.gz"
            b = canonical_csv(df)
            out["byte_identical"][fn] = sha256_bytes(b) == man["files"][fn]["sha256_csv"]
            old = pd.read_csv(gd / fn, compression="gzip")
            out["tables"][fn] = compare_tables(old, pd.read_csv(io.BytesIO(b)))
    out["ok"] = all(v["ok"] for v in out["tables"].values())
    if record:
        man["check"] = {k: v for k, v in out.items() if k != "tables"} | {
            "bad": {k: v["bad_columns"] for k, v in out["tables"].items() if not v["ok"]}}
        _write_json(gd / "manifest.json", man)
    return out


# ---------------------------------------------------------------------------------------------------------------


def dry_settings(out: Path) -> dict:
    return load_settings({"paths": {"backtests": str(out / "backtests"), "reports": str(out / "reports")},
                          "periods": {"validation_start": DRY_VALIDATION_START}})


def dryrun(out: Path, workers: int | None = None) -> dict:
    """Kuru prova: kilit = geliştirme sonu, 'doğrulama' = geliştirmenin son yarısı; geliştirme dışı veri okunmaz.
    Tam dönem çalıştırmaları G10 çalıştırmalarıyla tamamen aynı çıkmalı (tutarlılık tablosu: hepsi 0)."""
    cfg = dry_settings(out)
    for k in ("backtests", "reports"):
        cfg_path(cfg, k).mkdir(parents=True, exist_ok=True)
    ld = lock_dir(cfg)
    ld.mkdir(parents=True, exist_ok=True)
    _write_json(ld / "LOCK.json", {"lock_date": cfg["periods"]["development"][1], "dry_run": True,
                                   "created_utc": _now()})
    rec = run_batch(cfg, workers, dry=True)
    lk = read_lock(cfg)
    inp = load_inputs("full", lk["lock_date"], cfg=cfg, fill_modes=("open_t1",))
    res = analyze_g12(inp)
    gm = golden_write(cfg)
    gm["check"] = golden_check(cfg)
    rep = write_report(inp, res, lk, rec, gm)
    return {"report": str(rep), "consistency_max": float(res["consistency"]["max_abs_diff"].max()),
            "golden_ok": gm["check"]["ok"], "golden_cache_diff": gm["cache_max_abs_diff"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m trend.research.g12")
    ap.add_argument("cmd", choices=["snapshot", "verify", "run", "report", "golden", "dryrun"])
    ap.add_argument("--lock-date")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--check", action="store_true", help="golden: yeniden üret ve karşılaştır")
    ap.add_argument("--out", type=Path, help="dryrun çıktı dizini")
    ap.add_argument("--allow-rerun-validation-spent", action="store_true",
                    help="run: doğrulama dönemi harcanmış olsa da yeniden çalıştır (kayda yazılır)")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    cfg = load_settings()
    if a.cmd == "snapshot":
        if not a.lock_date:
            ap.error("snapshot için --lock-date gerekir")
        r = snapshot(cfg, a.lock_date)
        print(json.dumps({k: r[k] for k in ("lock_date", "n_files", "bytes", "data_manifest_sha256")}, indent=1))
    elif a.cmd == "verify":
        v = verify_snapshot(cfg)
        print(json.dumps(v, indent=1, ensure_ascii=False))
        return 0 if v["ok"] else 1
    elif a.cmd == "run":
        print(json.dumps(run_batch(cfg, a.workers, allow_rerun=a.allow_rerun_validation_spent), indent=1,
                         ensure_ascii=False)[:2000])
    elif a.cmd == "report":
        lk = read_lock(cfg)
        rp = lock_dir(cfg) / "G12_run.json"
        rec = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else None
        inp = load_inputs("full", lk["lock_date"], cfg=cfg, fill_modes=("open_t1",))
        res = analyze_g12(inp)
        gp = golden_dir(cfg) / "manifest.json"
        gm = json.loads(gp.read_text(encoding="utf-8")) if gp.exists() else None
        print("rapor →", write_report(inp, res, lk, rec, gm))
    elif a.cmd == "golden":
        if a.check:
            r = golden_check(cfg)
            print(json.dumps({k: v for k, v in r.items() if k != "tables"}, indent=1, ensure_ascii=False))
            for k, v in r["tables"].items():
                print(k, "tamam" if v["ok"] else f"FARKLI {v['bad_columns']} {v['why']}", f"{v['max_rel_diff']:.2e}")
            return 0 if r["ok"] else 1
        m = golden_write(cfg)
        print(json.dumps({"files": len(m["files"]), "cache_max_abs_diff": m["cache_max_abs_diff"]}, indent=1))
    elif a.cmd == "dryrun":
        if not a.out:
            ap.error("dryrun için --out gerekir")
        print(json.dumps(dryrun(a.out, a.workers), indent=1, ensure_ascii=False))
    print(f"bitti: {time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
