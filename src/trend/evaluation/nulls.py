"""Sıfır hipotezleri (rastgele kıyas) çerçevesi — SPEC "Değerlendirme → Sıfır hipotezleri".

(a) Tarih karıştırma: her coinin döngüleri (süre ve ağırlık yolu) korunur; başlangıç tarihleri o coinin evrende
    olduğu günler içinde rastgele ve aynı coinde çakışmayacak şekilde taşınır; günlük toplam ağırlık gross_max'ı
    aşarsa o gün orantılı küçültülür.
(b) Maruziyet yolu korunur: döngüler açılış sırasıyla işlenir; her döngünün ağırlık yolu, açılış günü evrende olan
    ve döngü boyunca sentetik portföyde tutulmayan rastgele bir coine verilir. Günlük toplam maruziyet ve pozisyon
    sayısı aynen korunur; piyasa zamanlaması coin seçiminden ayrılır.
p = (1 + #{sıfır ≥ gözlenen}) / (çalıştırma + 1); sabit tohum (settings `evaluation.null_runs`, `null_seed`).

Girdiler (motor çıktısından):
- `w_hold`: (gün × asset_id) **gün içinde taşınan** ağırlık (t günü dolumundan sonra, kaymadan önce). Motor gün sonu
  ağırlık veriyorsa `start_of_day_weights` ile çevrilir. Böylece r_t = Σ w_hold·r_t geleceği görmez ve yollar
  başka coine/tarihe taşındığında kendi getirisiyle korelasyon taşımaz.
- `cycles`: metrics.CYCLE_COLUMNS (asset, open_date, close_date[NaT = açık]); yol = w_hold[asset][open..close]
  (kapanış günü 0 dahil; açık döngüde dönem sonuna kadar).
- `membership`: (gün × asset_id) bool, coin o gün evrende mi. Kolonları w_hold'dan geniş olabilir (hiç işlem
  görmemiş evren coinleri (b) için adaydır).
- `available`: (isteğe bağlı) fiyat verisi var mı; verilmezse `membership`. Yol boyunca tüm günler müsait olmalı.

Gözlenen istatistik **aynı** basitleştirilmiş getiri hesabıyla (`portfolio_returns`) üretilmelidir; motorun tam
muhasebesiyle değil. Rastgele yerleşim sıralı tekdüze seçimdir (tüm geçerli yerleşimler üzerinde tam tekdüze değil).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from trend.evaluation.common import settings

MAX_PLACEMENT_TRIES = 20


def start_of_day_weights(weights_end: pd.DataFrame, asset_returns: pd.DataFrame) -> pd.DataFrame:
    """Gün sonu (kaymış) ağırlıktan gün içi taşınan ağırlığa: u_i = w_i/(1 + r_i), w0_i = u_i/(1 − Σw + Σu).

    Nakit gün içinde sabit (nakit getirisi ve maliyet ihmal) varsayımıyla kaymanın tam tersidir.
    """
    r = asset_returns.reindex(index=weights_end.index, columns=weights_end.columns).fillna(0.0)
    w = weights_end.fillna(0.0)
    u = w / (1.0 + r)
    denom = 1.0 - w.sum(axis=1) + u.sum(axis=1)
    return u.div(denom, axis=0)


def portfolio_returns(w_hold: pd.DataFrame, asset_returns: pd.DataFrame, cost_rate: float = 0.0) -> pd.Series:
    """r_t = Σ_i w_hold_{i,t}·r_{i,t} − cost_rate·Σ_i |w_hold_{i,t} − w_hold_{i,t−1}| (yaklaşık; kayma yok sayılır).

    Tutulan coinde getiri NaN ise (boşluk: son fiyat taşınır) 0 alınır.
    """
    r = asset_returns.reindex(index=w_hold.index, columns=w_hold.columns).fillna(0.0)
    w = w_hold.fillna(0.0)
    gross = (w * r).sum(axis=1)
    turn = w.diff().abs().sum(axis=1)
    turn.iloc[0] = w.iloc[0].abs().sum()
    return (gross - cost_rate * turn).rename("ret")


def _frames(w_hold, membership, available):
    idx = w_hold.index
    cols = w_hold.columns.union(membership.columns, sort=False)
    mem = membership.astype(bool).reindex(index=idx, columns=cols, fill_value=False).to_numpy(dtype=bool)
    avl = mem if available is None else (
        available.astype(bool).reindex(index=idx, columns=cols, fill_value=False).to_numpy(dtype=bool))
    w = w_hold.reindex(columns=cols, fill_value=0.0).fillna(0.0).to_numpy(dtype=float)
    return idx, cols, mem, avl, w


def extract_cycle_paths(cycles: pd.DataFrame, w_hold: pd.DataFrame) -> list[tuple[str, int, np.ndarray]]:
    """Her döngü için (asset, başlangıç konumu, ağırlık yolu)."""
    idx = w_hold.index
    out = []
    for asset, od, cd in zip(cycles["asset"], cycles["open_date"], cycles["close_date"]):
        s = idx.get_loc(pd.Timestamp(od))
        e = len(idx) - 1 if pd.isna(cd) else idx.get_loc(pd.Timestamp(cd))
        out.append((asset, int(s), w_hold[asset].iloc[s : e + 1].fillna(0.0).to_numpy(dtype=float)))
    return out


def scale_to_gross(w: np.ndarray, gross_max: float = 1.0) -> np.ndarray:
    tot = w.sum(axis=1)
    f = np.where(tot > gross_max, gross_max / np.where(tot > 0, tot, 1.0), 1.0)
    return w * f[:, None]


def null_date_shuffle(
    cycles: pd.DataFrame,
    w_hold: pd.DataFrame,
    membership: pd.DataFrame,
    rng: np.random.Generator,
    available: pd.DataFrame | None = None,
    gross_max: float | None = None,
    max_tries: int = MAX_PLACEMENT_TRIES,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Sıfır (a): döngü başlangıçlarını coin içinde rastgele, çakışmasız taşır. Dönüş: (sentetik w_hold, tanı)."""
    gross_max = float(settings()["strategy"]["gross_max"] if gross_max is None else gross_max)
    idx, cols, mem, avl, _ = _frames(w_hold, membership, available)
    T = len(idx)
    out = np.zeros((T, len(cols)))
    paths = extract_cycle_paths(cycles, w_hold)
    col_pos = {c: i for i, c in enumerate(cols)}
    by_asset: dict[str, list[np.ndarray]] = {}
    for asset, _, p in paths:
        by_asset.setdefault(asset, []).append(p)
    dropped = 0
    for asset, plist in by_asset.items():
        j = col_pos[asset]
        best: tuple[int, list] | None = None
        for _ in range(max_tries):
            order = sorted(range(len(plist)), key=lambda k: (-len(plist[k]), rng.random()))
            occ = np.zeros(T, dtype=bool)
            placed, miss = [], 0
            for k in order:
                L = len(plist[k])
                if L > T:
                    miss += 1
                    continue
                free = avl[:, j] & ~occ
                c = np.concatenate([[0], np.cumsum(free)])
                feas = ((c[L:] - c[:-L]) == L) & mem[: T - L + 1, j]
                cand = np.flatnonzero(feas)
                if cand.size == 0:
                    miss += 1
                    continue
                s = int(rng.choice(cand))
                occ[s : s + L] = True
                placed.append((s, plist[k]))
            if best is None or miss < best[0]:
                best = (miss, placed)
            if miss == 0:
                break
        dropped += best[0]
        for s, p in best[1]:
            out[s : s + len(p), j] += p
    out = scale_to_gross(out, gross_max)
    return pd.DataFrame(out, index=idx, columns=cols), {"n_cycles": len(paths), "dropped": dropped}


def null_random_coin(
    cycles: pd.DataFrame,
    w_hold: pd.DataFrame,
    membership: pd.DataFrame,
    rng: np.random.Generator,
    available: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Sıfır (b): her döngünün ağırlık yolu (aynı tarihlerde) rastgele uygun bir coine verilir."""
    idx, cols, mem, avl, _ = _frames(w_hold, membership, available)
    T, A = len(idx), len(cols)
    out = np.zeros((T, A))
    occ = np.zeros((T, A), dtype=bool)
    paths = extract_cycle_paths(cycles, w_hold)
    order = sorted(range(len(paths)), key=lambda k: (paths[k][1], rng.random()))
    col_pos = {c: i for i, c in enumerate(cols)}
    dropped = fallback = 0
    for k in order:
        asset, s, p = paths[k]
        e = s + len(p)
        free = ~occ[s:e].any(axis=0)
        cand = np.flatnonzero(mem[s] & avl[s:e].all(axis=0) & free)
        if cand.size == 0:
            j0 = col_pos[asset]
            if not free[j0]:
                dropped += 1
                continue
            cand, fallback = np.array([j0]), fallback + 1
        j = int(rng.choice(cand))
        out[s:e, j] = p
        occ[s:e, j] = True
    return pd.DataFrame(out, index=idx, columns=cols), {"n_cycles": len(paths), "dropped": dropped,
                                                        "fallback_original": fallback}


def null_p_value(observed: float, null_stats: np.ndarray) -> float:
    """p = (1 + #{sıfır ≥ gözlenen}) / (n + 1)."""
    x = np.asarray(null_stats, dtype=float)
    x = x[~np.isnan(x)]
    return float((1 + np.sum(x >= observed)) / (x.size + 1))


def percentile_rank(observed: float, null_stats: np.ndarray) -> float:
    """Gözlenenin sıfır dağılımındaki yüzdelik sırası = P(sıfır ≤ gözlenen) (ör. en büyük düşüş için)."""
    x = np.asarray(null_stats, dtype=float)
    x = x[~np.isnan(x)]
    return float(np.mean(x <= observed))


def run_null(
    generator: Callable[[np.random.Generator], pd.DataFrame],
    stat_fn: Callable[[pd.DataFrame], float | np.ndarray],
    n_runs: int | None = None,
    seed: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> np.ndarray:
    """`n_runs` sentetik ağırlık yolu üretir, her biri için `stat_fn` (ör. (Sharpe, MDD)). Dönüş (n_runs, J)."""
    ev = settings(cfg)["evaluation"]
    n_runs = int(n_runs or ev["null_runs"])
    rng = np.random.default_rng(int(ev["null_seed"] if seed is None else seed))
    res = [np.atleast_1d(np.asarray(stat_fn(generator(rng)), dtype=float)) for _ in range(n_runs)]
    return np.vstack(res)
