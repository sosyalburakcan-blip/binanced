"""Zorunlu test 1–2 altyapısı: t sonrasındaki fiyat ve meta veriyi rastgele bozup t'ye kadarki kararları karşılaştırır.

Bozulanlar (t = son karar günü):
- 1d panel: gün etiketi > t olan tüm satırlar (değerler rastgele çarpılır, rastgele NaN eklenir/silinir)
- 1h panel ve hazır dolum fiyatları: zaman ≥ t+1 00:00 (t kararının dolumu t+1'de olduğu için t'yi etkilemez)
- evren: karar anı T (= ay başından bir gün önce) > t olan ayların tabloları rastgele üyelik/kademe/kayma ile
- delist bilgisi: last_day veya announced_day > t olan satırlar başka > t tarihlere; ayrıca yeni sahte satırlar
- kalite işaretleri: known_from ≥ t olanlar (t kararında görünmez: known_from ≤ t−1 kuralı) + yeni sahte işaretler
- nakit faizi: > t
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trend.backtest.providers import MonthlyUniverse


def _corrupt_frame(df: pd.DataFrame, after: pd.Timestamp, rng: np.random.Generator, inclusive: bool) -> pd.DataFrame:
    idx = pd.DatetimeIndex(df.index)
    rows = idx >= after if inclusive else idx > after
    a = df.to_numpy(dtype=float, copy=True)
    k = int(rows.sum())
    if k == 0:
        return df.copy()
    sub = a[rows]
    noise = np.exp(rng.standard_normal(sub.shape) * 0.8)
    last = pd.DataFrame(a).ffill().to_numpy()[-1]  # sütunun son geçerli değeri (diriltme için ölçek)
    fill = np.where(np.isfinite(last), last, 1.0)
    new = np.where(np.isfinite(sub), sub * noise, np.nan)
    resurrect = rng.random(sub.shape) < 0.05
    new = np.where(resurrect & ~np.isfinite(new), fill[None, :] * noise, new)
    kill = rng.random(sub.shape) < 0.05
    new[kill] = np.nan
    a[rows] = new
    return pd.DataFrame(a, index=df.index, columns=df.columns)


def corrupt_after(t, rng: np.random.Generator, panel_1d=None, panel_1h=None, fill_px=None, universe=None,
                  delist=None, quality_flags=None, cash_rate=None, assets=None) -> dict:
    """t sonrasını bozulmuş girdiler sözlüğü (verilmeyenler None)."""
    t = pd.Timestamp(t)
    t1 = t + pd.Timedelta(days=1)
    out: dict = {}
    if panel_1d is not None:
        out["panel_1d"] = {k: _corrupt_frame(v, t, rng, inclusive=False) for k, v in panel_1d.items()}
    if panel_1h is not None:
        out["panel_1h"] = {k: _corrupt_frame(v, t1, rng, inclusive=True) for k, v in panel_1h.items()}
    if fill_px is not None:
        out["fill_px"] = _corrupt_frame(fill_px, t, rng, inclusive=False)
    if universe is not None:
        syms = list(assets) if assets is not None else sorted({s for df in universe.tables.values() for s in df["symbol"]})
        tables = {}
        for key, df in universe.tables.items():
            T = pd.Timestamp(key + "-01") - pd.Timedelta(days=1)
            if T > t:
                n = int(rng.integers(0, min(len(syms), 25) + 1))
                pick = list(rng.choice(syms, size=n, replace=False)) if n else []
                tiers = rng.choice(["A", "B", "C"], size=n)
                tables[key] = pd.DataFrame({
                    "symbol": pick, "rank": np.arange(1, n + 1), "median_liquidity": rng.uniform(1e6, 1e9, n),
                    "tier": tiers, "cap": rng.choice([0.03, 0.05, 0.10, 0.5], size=n),
                    "slippage": rng.choice([0.0005, 0.001, 0.002, 0.05], size=n)})
            else:
                tables[key] = df
        out["universe"] = MonthlyUniverse(tables)
    def rand_after() -> pd.Timestamp:
        return t + pd.Timedelta(days=int(rng.integers(1, 400)))

    if delist is not None:
        d = delist.copy()
        ld, ad = [], []
        for x, y in zip(d["last_day"], d["announced_day"]):
            ld.append(rand_after() if pd.notna(x) and pd.Timestamp(x) > t else x)
            ad.append((rand_after() if rng.random() < 0.7 else pd.NaT) if (pd.isna(y) or pd.Timestamp(y) > t) else y)
        d["last_day"] = pd.to_datetime(pd.Series(ld, dtype="object"))
        d["announced_day"] = pd.to_datetime(pd.Series(ad, dtype="object"))
        if assets is not None:
            extra = [a for a in assets if a not in set(d["asset"])]
            pick = list(rng.choice(extra, size=min(3, len(extra)), replace=False)) if extra else []
            add = pd.DataFrame({"asset": pick, "last_day": [rand_after() for _ in pick],
                                "announced_day": [rand_after() for _ in pick]})
            d = pd.concat([d, add], ignore_index=True)
        out["delist"] = d
    if quality_flags is not None:
        q = quality_flags.copy()
        keep = pd.to_datetime(q["known_from"]) < t
        q = q[keep]
        syms = list(assets) if assets is not None else list(quality_flags["symbol"].unique())
        rows = []
        for _ in range(20):
            kf = rand_after() - pd.Timedelta(days=1)  # known_from ≥ t
            ps = kf - pd.Timedelta(days=int(rng.integers(0, 2000)))
            rows.append((str(rng.choice(syms)), "fake", ps, kf, kf, str(rng.choice(["error", "exclude", "flag"])), "x"))
        q = pd.concat([q, pd.DataFrame(rows, columns=["symbol", "check", "period_start", "period_end", "known_from",
                                                      "severity", "detail"])], ignore_index=True)
        out["quality_flags"] = q
    if cash_rate is not None:
        r = cash_rate.copy()
        m = pd.DatetimeIndex(r.index) > t
        r[m] = rng.uniform(0.0, 0.5, int(m.sum()))
        out["cash_rate"] = r
    return out


def compare_until(a, b, t, exact: bool = True, rtol: float = 1e-9) -> list[str]:
    """İki sonucu t'ye kadar (karar ≤ t, dolum ≤ t, günlük ≤ t) karşılaştırır; farkların listesi."""
    t = pd.Timestamp(t)
    diffs = []
    da = a.decisions[a.decisions["date"] <= t].reset_index(drop=True)
    db = b.decisions[b.decisions["date"] <= t].reset_index(drop=True)
    diffs += _cmp_frames("decisions", da, db, ["date", "asset", "s3_raw", "s3", "reason"], ["w", "w_tgt", "delta", "qty"],
                         exact, rtol)
    fa = a.fills[a.fills["date"] <= t].reset_index(drop=True)
    fb = b.fills[b.fills["date"] <= t].reset_index(drop=True)
    diffs += _cmp_frames("fills", fa, fb, ["date", "asset", "side", "kind"], ["qty", "price", "cash_flow"], exact, rtol)
    ya = a.daily.loc[:t, ["nav", "cash"]].reset_index()
    yb = b.daily.loc[:t, ["nav", "cash"]].reset_index()
    diffs += _cmp_frames("daily", ya, yb, ["date"], ["nav", "cash"], exact, rtol)
    return diffs


def _cmp_frames(name, x, y, keys, nums, exact, rtol) -> list[str]:
    if len(x) != len(y):
        return [f"{name}: satır sayısı {len(x)} ≠ {len(y)}"]
    out = []
    for k in keys:
        ne = (x[k].astype(str).to_numpy() != y[k].astype(str).to_numpy())
        if ne.any():
            r = int(np.argmax(ne))
            out.append(f"{name}.{k} satır {r}: {x[k].iloc[r]!r} ≠ {y[k].iloc[r]!r}")
    for c in nums:
        u, v = x[c].to_numpy(dtype=float), y[c].to_numpy(dtype=float)
        if exact:
            ne = ~((u == v) | (np.isnan(u) & np.isnan(v)))
        else:
            ne = ~(np.isclose(u, v, rtol=rtol, atol=1e-12) | (np.isnan(u) & np.isnan(v)))
        if ne.any():
            r = int(np.argmax(ne))
            out.append(f"{name}.{c} satır {r}: {u[r]!r} ≠ {v[r]!r}")
    return out
