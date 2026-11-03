"""Toplu backtest: çalıştırma tanımları (RunSpec), paralel yürütme ve disk önbelleği (G10–G12).

Her çalıştırma aynı motoru (`run_backtest`) aynı girdilerle kullanır; kıyaslar `TargetWeightStrategy` ile ve sert
sınır kapalı çalışır (benchmarks.py varsayımı). Sonuçlar `backtests/{stage}/{name}/` altına yazılır:
`daily.parquet`, `weights.parquet` (float32), `cycles.parquet`, `spec.json`.

Varsayımlar:
- T8 (mum kapanış saati H): günlük panel ve dolum fiyatları saatlik veriden kaydırılarak kurulur; delist tablosu ana
  tablodaki varlıklar için kaydırılmış panelin son geçerli gün etiketiyle yeniden yazılır.
- Kontrol panelleri (karıştırma, GARCH) gerçek evren ve delist tablosuyla, `open_t1` dolumuyla çalışır; karşılaştırma
  gerçek veride aynı dolumla (T3) yapılır.
"""

from __future__ import annotations

import json
import os
import pickle
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from trend.backtest.engine import BacktestResult, resolve_settings, run_backtest
from trend.config import path as cfg_path
from trend.research.inputs import ResearchInputs
from trend.strategy.benchmarks import btc_200, btc_eth_200, btc_hold, trend_equal_weight, universe_equal_weight
from trend.strategy.system import TrendStrategy

BENCHMARK_KINDS = ("btc_200", "btc_eth_200", "btc_hold", "universe_ew")
TREND_KINDS = ("trend", "trend_equal", "inverse")


@dataclass(frozen=True)
class RunSpec:
    name: str
    kind: str = "trend"                 # trend | trend_equal | inverse | btc_200 | btc_eth_200 | btc_hold | universe_ew
    overrides: tuple = ()               # ((anahtar yolu, değer), ...) — hashlenebilir olsun diye düz liste
    universe: str = "main"
    panel: str = "real"                 # real | h04 … h20 (T8) | kontrol paneli adı
    leak_days: int = 0                  # < 0: sinyal gecikmesi (kontroller); > 0 yalnızca pozitif kontrol
    exchange_loss: tuple = ()           # ((tarih, oran), ...)
    sizing: str = "compound"
    weight: float = 1.0                 # btc_hold ağırlığı
    note: str = ""

    def override_dict(self) -> dict:
        out: dict = {}
        for key, val in self.overrides:
            d = out
            parts = key.split(".")
            for p in parts[:-1]:
                d = d.setdefault(p, {})
            d[parts[-1]] = val
        return out


def flat_overrides(d: dict, prefix: str = "") -> tuple:
    """İç içe geçersiz kılma sözlüğü → RunSpec.overrides biçimi."""
    out = []
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.extend(flat_overrides(v, key))
        else:
            out.append((key, tuple(v) if isinstance(v, list) else v))
    return tuple(out)


class InverseTrendStrategy(TrendStrategy):
    """Kontrol: ters sinyal (S3 → 3 − S3; uygun olmayan günler −1 kalır), geri kalan her şey T0 ile aynı."""

    def prepare(self, data) -> None:
        super().prepare(data)
        self.S3 = np.where(self.S3 >= 0, 3 - self.S3, -1).astype(np.int8)


@dataclass
class PanelSet:
    """Bir çalıştırmanın fiyat girdileri: günlük panel, dolum fiyatları (mod → çerçeve), delist tablosu."""
    panel_1d: dict
    fill_px: dict
    delist: pd.DataFrame


def make_strategy(spec: RunSpec, close: pd.DataFrame, universe, cfg: dict):
    if spec.kind == "trend":
        return TrendStrategy(leak_days=spec.leak_days)
    if spec.kind == "inverse":
        return InverseTrendStrategy(leak_days=spec.leak_days)
    if spec.kind == "trend_equal":
        return trend_equal_weight()
    if spec.kind == "btc_200":
        return btc_200(close)
    if spec.kind == "btc_eth_200":
        return btc_eth_200(close)
    if spec.kind == "btc_hold":
        return btc_hold(close, weight=spec.weight)
    if spec.kind == "universe_ew":
        return universe_equal_weight(close, universe)
    raise ValueError(f"bilinmeyen çalıştırma türü: {spec.kind!r}")


def run_one(spec: RunSpec, inp: ResearchInputs, panels: dict[str, PanelSet]) -> BacktestResult:
    cfg = resolve_settings(inp.cfg, spec.override_dict())
    ps = panels[spec.panel]
    mode = cfg["backtest"]["fill"]
    if mode not in ps.fill_px:
        raise KeyError(f"{spec.name}: '{spec.panel}' panelinde '{mode}' dolum fiyatı yok")
    uni = inp.universes[spec.universe]
    strat = make_strategy(spec, ps.panel_1d["close"], uni, cfg)
    cash = inp.tbill_rate if cfg["backtest"]["cash_yield"] != "zero" else None
    return run_backtest(
        ps.panel_1d, universe=uni, strategy=strat, fill_px=ps.fill_px[mode], delist=ps.delist, cash_rate=cash,
        quality_flags=inp.flags, settings=cfg, start=inp.start, end=inp.end, sizing=spec.sizing,
        hard_stop=spec.kind in TREND_KINDS, exchange_loss=list(spec.exchange_loss) or None,
    )


# ---------------------------------------------------------------------------------------------------------------
# Disk önbelleği


def run_dir(inp: ResearchInputs, name: str) -> Path:
    return cfg_path(inp.cfg, "backtests") / inp.stage / name


def save_result(d: Path, spec: RunSpec, res: BacktestResult, seconds: float) -> None:
    d.mkdir(parents=True, exist_ok=True)
    res.daily.to_parquet(d / "daily.parquet")
    if res.weights is not None:
        w = res.weights.loc[:, (res.weights != 0).any(axis=0)].astype("float32")
        w.to_parquet(d / "weights.parquet")
    res.cycles.to_parquet(d / "cycles.parquet")
    meta = {"spec": asdict(spec), "seconds": round(seconds, 1),
            "start": str(res.meta.get("start")), "end": str(res.meta.get("end"))}
    (d / "spec.json").write_text(json.dumps(meta, default=str, ensure_ascii=False, indent=1), encoding="utf-8")


@dataclass
class StoredRun:
    name: str
    daily: pd.DataFrame
    weights: pd.DataFrame | None
    cycles: pd.DataFrame
    spec: dict = field(default_factory=dict)

    @property
    def ret(self) -> pd.Series:
        return self.daily["ret"]


def load_run(inp: ResearchInputs, name: str) -> StoredRun:
    d = run_dir(inp, name)
    w = pd.read_parquet(d / "weights.parquet").astype(float) if (d / "weights.parquet").exists() else None
    spec = json.loads((d / "spec.json").read_text(encoding="utf-8"))
    return StoredRun(name, pd.read_parquet(d / "daily.parquet"), w, pd.read_parquet(d / "cycles.parquet"), spec)


def is_cached(inp: ResearchInputs, spec: RunSpec) -> bool:
    p = run_dir(inp, spec.name) / "spec.json"
    if not p.exists():
        return False
    old = json.loads(p.read_text(encoding="utf-8"))["spec"]
    return json.dumps(old, default=str, sort_keys=True) == json.dumps(
        json.loads(json.dumps(asdict(spec), default=str)), default=str, sort_keys=True)


# ---------------------------------------------------------------------------------------------------------------
# Paralel yürütme (Windows: spawn; işçiler girdileri tek bir pickle dosyasından okur)

_W: dict = {}


def _init_worker(pkl: str) -> None:
    with open(pkl, "rb") as f:
        _W["inp"], _W["panels"] = pickle.load(f)


def _work(spec: RunSpec) -> tuple[str, float, str | None]:
    t0 = time.perf_counter()
    try:
        res = run_one(spec, _W["inp"], _W["panels"])
        save_result(run_dir(_W["inp"], spec.name), spec, res, time.perf_counter() - t0)
        return spec.name, time.perf_counter() - t0, None
    except Exception as e:  # noqa: BLE001 — hatayı ana sürece raporla
        import traceback
        return spec.name, time.perf_counter() - t0, traceback.format_exc(limit=8) + f"\n{e!r}"


def run_many(specs: list[RunSpec], inp: ResearchInputs, panels: dict[str, PanelSet], workers: int | None = None,
             reuse: bool = True, verbose: bool = True) -> dict[str, float]:
    """Çalıştırmaları paralel yürütür; önbellekte aynı tanımla bulunanlar atlanır. Hata olursa sonunda yükseltir."""
    todo = [s for s in specs if not (reuse and is_cached(inp, s))]
    names = [s.name for s in specs]
    if len(set(names)) != len(names):
        raise ValueError("çalıştırma adları benzersiz olmalı")
    log = print if verbose else (lambda *a, **k: None)
    log(f"[toplu] {len(specs)} çalıştırma, {len(specs) - len(todo)} önbellekte, {len(todo)} yürütülecek")
    if not todo:
        return {}
    root = cfg_path(inp.cfg, "backtests") / inp.stage
    root.mkdir(parents=True, exist_ok=True)
    pkl = root / "_inputs.pkl"
    with open(pkl, "wb") as f:
        pickle.dump((inp, panels), f, protocol=pickle.HIGHEST_PROTOCOL)
    workers = workers or max(1, min(4, (os.cpu_count() or 2) - 1, len(todo)))
    times, errors = {}, {}
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=(str(pkl),)) as ex:
        futs = [ex.submit(_work, s) for s in todo]
        for k, fu in enumerate(as_completed(futs), start=1):
            name, sec, err = fu.result()
            times[name] = sec
            if err:
                errors[name] = err
            log(f"[toplu] {k}/{len(todo)} {name}: {sec:.0f}s{' HATA' if err else ''} "
                f"(geçen {time.perf_counter() - t0:.0f}s)")
    pkl.unlink(missing_ok=True)
    if errors:
        raise RuntimeError("başarısız çalıştırmalar:\n" + "\n\n".join(f"{k}:\n{v}" for k, v in errors.items()))
    return times
