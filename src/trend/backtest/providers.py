"""Motorun dış girdileri için bağdaştırıcılar: evren sağlayıcısı (CONTRACTS §6) ve nakit faizi serisi.

Evren sağlayıcısı = çağrılabilir `provider(t) -> DataFrame` (kolonlar: symbol, tier, cap, slippage; isteğe bağlı rank,
median_liquidity). CONTRACTS §1: **t günündeki karar (t + 1 gün)'ün ayının evrenini kullanır.** `key(t)` metodu varsa
motor sonucu ay anahtarıyla önbelleğe alır.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

UNIVERSE_COLUMNS = ["symbol", "rank", "median_liquidity", "tier", "cap", "slippage"]


def month_key_for_decision(t: pd.Timestamp) -> str:
    """t kararının kullandığı evren ayı: (t + 1 gün)'ün ayı, 'YYYY-MM'."""
    return (pd.Timestamp(t) + pd.Timedelta(days=1)).strftime("%Y-%m")


class MonthlyUniverse:
    """Aylık evren tabloları ({'YYYY-MM': DataFrame}) üzerinden sağlayıcı. Eksik ay → boş evren."""

    def __init__(self, tables: Mapping[str, pd.DataFrame]):
        self.tables = {k: _normalize(v) for k, v in tables.items()}
        self._empty = pd.DataFrame({c: pd.Series(dtype=float if c in ("cap", "slippage", "median_liquidity", "rank")
                                                 else object) for c in UNIVERSE_COLUMNS})

    @classmethod
    def from_dir(cls, path: str | Path) -> "MonthlyUniverse":
        """`universe/{YYYY-MM}.csv` dosyalarını okur (alt dizinler, ör. usdt_only, ayrı bir sağlayıcıdır)."""
        p = Path(path)
        tables = {f.stem: pd.read_csv(f) for f in sorted(p.glob("*.csv")) if len(f.stem) == 7 and f.stem[4] == "-"}
        return cls(tables)

    def key(self, t: pd.Timestamp) -> str:
        return month_key_for_decision(t)

    def __call__(self, t: pd.Timestamp) -> pd.DataFrame:
        return self.tables.get(self.key(t), self._empty)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["symbol"] = df["symbol"].astype(str)
    return df


def universe_arrays(
    df: pd.DataFrame,
    col_index: Mapping[str, int],
    n_assets: int,
    cfg: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Evren tablosunu (üyelik maskesi, tavan, kayma) dizilerine çevirir; panelde olmayan semboller atlanır.

    `cap`/`slippage` kolonu yoksa ayarlardaki kademe kurallarından türetilir (SPEC "Likidite kademeleri").
    """
    mask = np.zeros(n_assets, dtype=bool)
    cap = np.full(n_assets, np.nan)
    slip = np.full(n_assets, np.nan)
    if df is None or len(df) == 0:
        return mask, cap, slip
    syms = df["symbol"].astype(str).to_numpy()
    idx = np.array([col_index.get(s, -1) for s in syms], dtype=np.int64)
    keep = idx >= 0
    if not keep.any():
        return mask, cap, slip
    sub = df.loc[keep]
    j = idx[keep]
    mask[j] = True
    if "cap" in sub.columns:
        cap[j] = sub["cap"].to_numpy(dtype=float)
    else:
        tiers = cfg["universe"]["tiers"]
        cap[j] = [float(tiers[str(t)]["cap"]) for t in sub["tier"]]
    if "slippage" in sub.columns:
        slip[j] = sub["slippage"].to_numpy(dtype=float)
    else:
        slip[j] = [tier_slippage(str(t), float(m), cfg) for t, m in zip(sub["tier"], sub["median_liquidity"])]
    return mask, cap, slip


def tier_slippage(tier: str, median_liquidity: float, cfg: dict) -> float:
    s = cfg["universe"]["slippage"]
    if tier == "A":
        return float(s["A"])
    for row in s["by_liquidity"]:
        if median_liquidity >= float(row["min_liquidity"]):
            return float(row["slippage"])
    return float(s["by_liquidity"][-1]["slippage"])


def default_slippage(asset: str, cfg: dict) -> float:
    """Hiç evren satırı görülmemiş varlık için kayma: A kademesi sembolleri A, diğerleri en kötü kademe (kötümser)."""
    bases = [str(b) for b in cfg["universe"]["tiers"]["A"]["symbols"]]
    if any(asset == b + "USDT" for b in bases):
        return float(cfg["universe"]["slippage"]["A"])
    return float(max(r["slippage"] for r in cfg["universe"]["slippage"]["by_liquidity"]))


def daily_cash_rate(rate: pd.Series | None, days: pd.DatetimeIndex, mode: str, haircut: float) -> np.ndarray:
    """Günlük uygulanacak yıllık nakit getirisi oranı (ondalık). mode: zero | tbill_minus_1_5 | tbill.

    `rate` yıllık hazine bonosu faizi (ondalık, ör. 0.05); takvime nedensel ileri doldurma ile hizalanır.
    """
    if mode == "zero":
        return np.zeros(len(days))
    if rate is None:
        raise ValueError(f"cash_yield={mode!r} için nakit faizi serisi (cash_rate) gerekli")
    r = rate.copy()
    r.index = pd.DatetimeIndex(r.index).as_unit("ns")
    r = r.sort_index()
    aligned = r.reindex(r.index.union(days)).ffill().reindex(days).fillna(0.0).to_numpy(dtype=float)
    if mode == "tbill":
        return aligned
    if mode == "tbill_minus_1_5":
        return np.maximum(aligned - haircut, 0.0)
    raise ValueError(f"bilinmeyen cash_yield: {mode!r}")
