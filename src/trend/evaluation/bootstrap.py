"""Durağan blok bootstrap (Politis ve Romano 1994): Sharpe ve Sharpe farkı, en büyük düşüş dağılımı, düşüş ufku.

Yöntem: her adımda 1/b olasılıkla rastgele bir indeksten yeni blok başlar, aksi halde bir önceki indeksin ardılı
alınır (dairesel). Blok uzunlukları geometrik, ortalama b = 30 gün; yol sayısı 10.000; sabit tohum (settings
`evaluation.bootstrap`). Eşleştirilmiş örneklemede iki seri **aynı indekslerle** yeniden örneklenir (aynı günler),
böylece aralarındaki korelasyon korunur.

Tekrar üretilebilirlik: sonuç (seed, n_paths, length, chunk) için deterministiktir. Aynı seed ve uzunlukla çağrılan
fonksiyonlar aynı yolları kullanır (ör. Sharpe testi ile düşüş karşılaştırması).
Düşüşler ≤ 0 kesirdir; "%95'lik düşüş" = dağılımın %5 alt dilimi (yolların yalnız %5'inde aşılan şiddet).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import numpy as np
import pandas as pd

from trend.evaluation.common import excess_returns, periods_per_year, settings, sharpe

CHUNK_PATHS = 500  # bellek: 500 × uzunluk × seri sayısı float64


def _bcfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    return settings(cfg)["evaluation"]["bootstrap"]


def stationary_indices(
    n: int, length: int, n_paths: int, mean_block: float, rng: np.random.Generator
) -> np.ndarray:
    """(n_paths, length) indeks matrisi; vektörel. Blok başı olasılığı p = 1/mean_block, ilk adım her zaman blok başı."""
    starts = rng.integers(0, n, size=(n_paths, length), dtype=np.int64)
    new = rng.random((n_paths, length)) < (1.0 / mean_block)
    new[:, 0] = True
    t = np.arange(length, dtype=np.int64)
    last = np.where(new, t, 0)
    np.maximum.accumulate(last, axis=1, out=last)
    rows = np.arange(n_paths)[:, None]
    return (starts[rows, last] + (t - last)) % n


def iter_index_chunks(
    n: int, length: int, n_paths: int, mean_block: float, seed: int, chunk: int = CHUNK_PATHS
) -> Iterator[np.ndarray]:
    rng = np.random.default_rng(seed)
    done = 0
    while done < n_paths:
        m = min(chunk, n_paths - done)
        yield stationary_indices(n, length, m, mean_block, rng)
        done += m


def bootstrap_apply(
    data: np.ndarray,
    stat_fn: Callable[[np.ndarray], np.ndarray],
    n_paths: int | None = None,
    mean_block: float | None = None,
    seed: int | None = None,
    length: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> np.ndarray:
    """`data` (T, K) satırlarını eşleştirilmiş yeniden örnekler; `stat_fn((m, L, K)) → (m, J)`. Dönüş (n_paths, J)."""
    b = _bcfg(cfg)
    n_paths = int(n_paths or b["paths"])
    mean_block = float(mean_block or b["mean_block_days"])
    seed = int(b["seed"] if seed is None else seed)
    data = np.asarray(data, dtype=float)
    if data.ndim == 1:
        data = data[:, None]
    n = data.shape[0]
    length = int(length or n)
    out = [np.asarray(stat_fn(data[idx]), dtype=float).reshape(idx.shape[0], -1)
           for idx in iter_index_chunks(n, length, n_paths, mean_block, seed)]
    return np.concatenate(out, axis=0)


def sharpe_paths(x: np.ndarray, ppy: int) -> np.ndarray:
    """Yol başına yıllık Sharpe; x (m, L) fazla getiri."""
    sd = x.std(axis=1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(sd > 0, x.mean(axis=1) / sd * np.sqrt(ppy), np.nan)


def drawdown_paths(r: np.ndarray) -> np.ndarray:
    """(m, L) getiri → (m, L) düşüş (≤ 0); başlangıç değeri 1 zirve sayılır."""
    logw = np.cumsum(np.log1p(np.clip(r, -0.999999, None)), axis=1)
    peak = np.maximum.accumulate(np.maximum(logw, 0.0), axis=1)
    return np.expm1(logw - peak)


def max_drawdown_paths(r: np.ndarray) -> np.ndarray:
    return drawdown_paths(r).min(axis=1)


def _align(*series: pd.Series) -> pd.DataFrame:
    df = pd.concat(series, axis=1, join="inner").dropna()
    if len(df) < 2:
        raise ValueError("ortak gözlem yok")
    return df


def _ci(dist: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    a = (1 - level) / 2
    q = np.nanquantile(dist, [a, 1 - a])
    return float(q[0]), float(q[1])


def bootstrap_sharpe(
    returns: pd.Series, rf: pd.Series | float | None = None, cfg: dict[str, Any] | None = None, **kw
) -> dict[str, Any]:
    """Tek seri Sharpe'ı için bootstrap dağılımı ve %95 yüzdelik güven aralığı."""
    ppy = periods_per_year(cfg)
    ex = excess_returns(returns.dropna(), rf)
    dist = bootstrap_apply(ex.to_numpy(), lambda x: sharpe_paths(x[..., 0], ppy), cfg=cfg, **kw)[:, 0]
    return {"sharpe": sharpe(ex, ppy), "ci95": _ci(dist), "se": float(np.nanstd(dist, ddof=1)), "dist": dist}


def paired_sharpe_test(
    strategy: pd.Series,
    benchmark: pd.Series,
    rf: pd.Series | float | None = None,
    alpha: float = 0.05,
    cfg: dict[str, Any] | None = None,
    **kw,
) -> dict[str, Any]:
    """Birincil hipotez testi: SR(strateji) − SR(kıyas) > 0, eşleştirilmiş durağan blok bootstrap.

    p (tek yönlü, yüzdelik) = (1 + #{ΔSR* ≤ 0}) / (B + 1); geçiş ⇔ p < alpha ⇔ tek yönlü %95 alt sınır > 0.
    Ayrıca merkezlenmiş p = (1 + #{ΔSR* − ΔSR ≥ ΔSR}) / (B + 1) raporlanır (simetrik dağılımda ikisi eşittir).
    Girdiler ham günlük getiri; ikisinden de aynı rf düşülür.
    """
    ppy = periods_per_year(cfg)
    df = _align(strategy.rename("s"), benchmark.rename("b"))
    ex = pd.DataFrame({c: excess_returns(df[c], rf) for c in df.columns})

    def stat(x):
        return np.column_stack([sharpe_paths(x[..., 0], ppy), sharpe_paths(x[..., 1], ppy)])

    d = bootstrap_apply(ex.to_numpy(), stat, cfg=cfg, **kw)
    diff = d[:, 0] - d[:, 1]
    valid = ~np.isnan(diff)
    diff_v = diff[valid]
    sr_s, sr_b = sharpe(ex["s"], ppy), sharpe(ex["b"], ppy)
    obs = sr_s - sr_b
    B = diff_v.size
    p = (1 + np.sum(diff_v <= 0)) / (B + 1)
    p_c = (1 + np.sum(diff_v - obs >= obs)) / (B + 1)
    lower_1s = float(np.quantile(diff_v, alpha))
    return {
        "sharpe_strategy": sr_s, "sharpe_benchmark": sr_b, "sharpe_diff": obs,
        "ci95_strategy": _ci(d[:, 0]), "ci95_benchmark": _ci(d[:, 1]), "ci95_diff": _ci(diff_v),
        "lower_one_sided": lower_1s, "p_value": float(p), "p_value_centered": float(p_c),
        "passed": bool(p < alpha), "n_obs": int(len(ex)), "n_paths": int(B), "dist_diff": diff_v,
    }


def max_drawdown_distribution(returns: pd.Series, cfg: dict[str, Any] | None = None, **kw) -> dict[str, Any]:
    """En büyük düşüş dağılımı (bootstrap yolları): gözlenen, medyan, %5/%50/%95 dilimler."""
    r = returns.dropna()
    dist = bootstrap_apply(r.to_numpy(), lambda x: max_drawdown_paths(x[..., 0]), cfg=cfg, **kw)[:, 0]
    obs = float(max_drawdown_paths(r.to_numpy()[None, :])[0])
    q = np.quantile(dist, [0.05, 0.5, 0.95])
    return {"observed": obs, "median": float(q[1]), "q05": float(q[0]), "q95": float(q[2]), "dist": dist}


def paired_drawdown_comparison(
    strategy: pd.Series, other: pd.Series, ratio: float = 0.5, cfg: dict[str, Any] | None = None, **kw
) -> dict[str, Any]:
    """Geç/kal kriteri 6: |medyan MDD(strateji)| < ratio · |medyan MDD(diğer)|, eşleştirilmiş yollarla.

    `other` = evrenin eşit ağırlıklı al-tutu. Ayrıca yol bazında |MDD_s| < ratio·|MDD_o| olan yolların payı.
    """
    df = _align(strategy.rename("s"), other.rename("o"))

    def stat(x):
        return np.column_stack([max_drawdown_paths(x[..., 0]), max_drawdown_paths(x[..., 1])])

    d = bootstrap_apply(df.to_numpy(), stat, cfg=cfg, **kw)
    med_s, med_o = float(np.median(d[:, 0])), float(np.median(d[:, 1]))
    return {
        "median_mdd_strategy": med_s, "median_mdd_other": med_o, "ratio": ratio,
        "passed": bool(abs(med_s) < ratio * abs(med_o)),
        "frac_paths_passing": float(np.mean(np.abs(d[:, 0]) < ratio * np.abs(d[:, 1]))),
        "dist": d,
    }


def drawdown_horizon_table(
    returns: pd.Series,
    horizons: list[int] | None = None,
    q: float = 0.95,
    cfg: dict[str, Any] | None = None,
    **kw,
) -> pd.DataFrame:
    """Düşüş ufku tablosu: h günlük pencerede (pencere başı = zirve) en büyük düşüşün %q'luk değeri.

    Durağan bootstrap yolları durağandır; her yolun ilk h günü h uzunluğunda geçerli bir örnektir. Yollar ana
    dağılımla aynıdır (uzunluk = max(seri uzunluğu, max h), aynı tohum). Canlı durdurma kuralı bu tabloyu kullanır.
    """
    cfg = settings(cfg)
    horizons = sorted(horizons or cfg["evaluation"]["drawdown_horizons"])
    r = returns.dropna().to_numpy()
    length = max(len(r), max(horizons))
    cols = np.array(horizons) - 1

    def stat(x):
        running_mdd = np.minimum.accumulate(drawdown_paths(x[..., 0]), axis=1)
        return running_mdd[:, cols]

    d = bootstrap_apply(r, stat, length=length, cfg=cfg, **kw)
    return pd.DataFrame(
        {
            f"dd_q{round(q * 100)}": np.quantile(d, 1 - q, axis=0),
            "dd_median": np.median(d, axis=0),
            "dd_mean": d.mean(axis=0),
        },
        index=pd.Index(horizons, name="horizon_days"),
    )
