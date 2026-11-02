"""Sentetik piyasa verisi (yalnızca test ve hız ölçümü için; gerçek veri kullanılmaz).

Saatlik log fiyat yolları (ortak piyasa faktörü + coin'e özgü, Markov rejimli trend sürüklenmesi) üretilir; günlük
mumlar saatlikten toplanır, böylece 1d ve 1h tutarlıdır. Kademeli listeleme, delist (veri biter) ve seri ortası
boşluklar (1d ve 1h birlikte NaN) eklenir. Evren, G6 kurallarının basit bir taklidiyle (yalnızca T'ye kadarki veri)
aylık kurulur.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trend.backtest.providers import MonthlyUniverse, tier_slippage
from trend.backtest.rules import delist_info_from_panel


@dataclass
class SyntheticMarket:
    panel_1d: dict
    panel_1h: dict
    universe: MonthlyUniverse
    delist: pd.DataFrame
    assets: list
    listing: dict
    gaps: dict


def asset_names(n: int) -> list[str]:
    base = ["BTCUSDT", "ETHUSDT"]
    return (base + [f"C{k:03d}USDT" for k in range(2, n)])[:n]


def make_market(
    n_assets: int = 12,
    n_days: int = 900,
    start: str = "2019-01-01",
    seed: int = 7,
    n_late: int | None = None,
    n_delist: int = 2,
    n_gaps: int = 2,
    hourly: bool = True,
    universe_size: int = 20,
    min_days: int = 365,
    cfg: dict | None = None,
) -> SyntheticMarket:
    rng = np.random.default_rng(seed)
    names = asset_names(n_assets)
    H = n_days * 24
    # piyasa faktörü + rejimli sürüklenme (günlük rejim, saate yayılır)
    mkt_reg = _regimes(rng, n_days, 1, p_switch=1 / 90.0, levels=(-1.2, 0.0, 1.5))[:, 0]
    reg = _regimes(rng, n_days, n_assets, p_switch=1 / 60.0, levels=(-2.0, 0.0, 2.5))
    vol_d = rng.uniform(0.025, 0.07, n_assets)
    vol_d[0] = 0.035
    beta = rng.uniform(0.6, 1.3, n_assets)
    beta[0] = 1.0
    mu_d = (mkt_reg[:, None] * beta[None, :] * 0.6 + reg * 0.4) / 365.0  # günlük log sürüklenme
    m_h = rng.standard_normal(H) * (0.03 / np.sqrt(24))
    e_h = rng.standard_normal((H, n_assets)) * (vol_d / np.sqrt(24))[None, :]
    r_h = np.repeat(mu_d / 24.0, 24, axis=0) + m_h[:, None] * beta[None, :] + e_h * 0.8
    p0 = np.exp(rng.uniform(np.log(0.05), np.log(500.0), n_assets))
    p0[0], p0[1 % n_assets] = 8000.0, 300.0
    logc = np.log(p0)[None, :] + np.cumsum(r_h, axis=0)
    close_h = np.exp(logc)
    open_h = np.vstack([p0[None, :], close_h[:-1]])
    wig = np.abs(rng.standard_normal((H, n_assets))) * (vol_d / np.sqrt(24) * 0.5)[None, :]
    high_h = np.maximum(open_h, close_h) * np.exp(wig)
    low_h = np.minimum(open_h, close_h) * np.exp(-wig * rng.uniform(0.5, 1.0, (H, n_assets)))
    base_qv = np.exp(rng.uniform(np.log(2e6), np.log(5e8), n_assets)) / 24.0
    base_qv[0] = 2e9 / 24.0
    qv_h = base_qv[None, :] * np.exp(rng.standard_normal((H, n_assets)) * 0.5)
    typ = np.clip((open_h + close_h) / 2.0 * np.exp(rng.standard_normal((H, n_assets)) * 0.001), low_h, high_h)
    vol_h = qv_h / typ
    # bazı saatlerde sıfır hacim (VWAP saat ekleme kuralını sınamak için)
    zero = rng.random((H, n_assets)) < 0.01
    qv_h[zero] = 0.0
    vol_h[zero] = 0.0

    # listeleme, delist, boşluklar
    mask_d = np.ones((n_days, n_assets), dtype=bool)
    n_late = n_late if n_late is not None else max(n_assets // 3, 0)
    listing = {}
    late = rng.choice(np.arange(2, n_assets), size=min(n_late, max(n_assets - 2, 0)), replace=False) if n_assets > 2 else []
    for j in late:
        s = int(rng.integers(30, max(n_days // 2, 31)))
        mask_d[:s, j] = False
        listing[names[j]] = s
    rest = [j for j in range(2, n_assets) if j not in set(late)]
    dl = rng.choice(rest, size=min(n_delist, len(rest)), replace=False) if rest else []
    for j in dl:
        e = int(rng.integers(int(n_days * 0.6), max(n_days - 30, int(n_days * 0.6) + 1)))
        mask_d[e + 1:, j] = False
    gaps = {}
    cand = [j for j in range(1, n_assets) if j not in set(dl)]
    for j in (rng.choice(cand, size=min(n_gaps, len(cand)), replace=False) if cand else []):
        g0 = int(rng.integers(int(n_days * 0.4), int(n_days * 0.8)))
        gl = int(rng.integers(2, 12))
        mask_d[g0:g0 + gl, j] = False
        gaps[names[j]] = (g0, gl)
    mask_h = np.repeat(mask_d, 24, axis=0)

    hidx = pd.date_range(start, periods=H, freq="h").as_unit("ns")
    didx = pd.date_range(start, periods=n_days, freq="D").as_unit("ns")

    def hf(a):
        return pd.DataFrame(np.where(mask_h, a, np.nan), index=hidx, columns=names)

    panel_1h = {"open": hf(open_h), "high": hf(high_h), "low": hf(low_h), "close": hf(close_h),
                "volume": hf(vol_h), "quote_volume": hf(qv_h)}
    blk = lambda a: a.reshape(n_days, 24, n_assets)  # noqa: E731
    d = {
        "open": blk(open_h)[:, 0, :], "close": blk(close_h)[:, -1, :],
        "high": blk(high_h).max(axis=1), "low": blk(low_h).min(axis=1),
        "volume": blk(vol_h).sum(axis=1), "quote_volume": blk(qv_h).sum(axis=1),
    }
    panel_1d = {k: pd.DataFrame(np.where(mask_d, v, np.nan), index=didx, columns=names) for k, v in d.items()}
    panel_1d["trades"] = panel_1d["volume"].notna().astype(float).where(panel_1d["volume"].notna())
    if not hourly:
        panel_1h = None
    from trend.config import load_settings

    cfg = cfg or load_settings()
    univ = synthetic_universe(panel_1d, cfg, size=universe_size, min_days=min_days)
    delist = delist_info_from_panel(panel_1d["close"], int(cfg["backtest"]["delist_stale_days"]))
    return SyntheticMarket(panel_1d, panel_1h, univ, delist, names, listing, gaps)


def _regimes(rng, n_days: int, n: int, p_switch: float, levels: tuple) -> np.ndarray:
    lv = np.asarray(levels)
    out = np.empty((n_days, n))
    cur = rng.integers(0, len(lv), n)
    for t in range(n_days):
        sw = rng.random(n) < p_switch
        cur = np.where(sw, rng.integers(0, len(lv), n), cur)
        out[t] = lv[cur]
    return out


def synthetic_universe(panel_1d: dict, cfg: dict, size: int = 20, min_days: int = 365) -> MonthlyUniverse:
    """G6 taklidi: ay M için T = önceki ayın son günü; T'de işlem gören, ≥ min_days geçerli barı olan coinler,
    30 günlük medyan quote hacmine göre ilk `size`; kademe/tavan/kayma ayarlardan. Yalnızca ≤ T verisi kullanılır."""
    close = panel_1d["close"]
    qv = panel_1d["quote_volume"]
    days = pd.DatetimeIndex(close.index)
    cnt = np.cumsum(np.isfinite(close.to_numpy()), axis=0)
    med = qv.rolling(30, min_periods=10).median().to_numpy()
    tiers = cfg["universe"]["tiers"]
    a_syms = {str(s) + "USDT" for s in tiers["A"]["symbols"]}
    tables = {}
    month_ends = days[(days + pd.Timedelta(days=1)).day == 1]
    for T in month_ends:
        i = days.get_loc(T)
        ok = np.isfinite(close.to_numpy()[i]) & (cnt[i] >= min_days) & np.isfinite(med[i])
        cols = np.nonzero(ok)[0]
        order = cols[np.argsort(-med[i, cols], kind="stable")][:size]
        rows = []
        for r, j in enumerate(order, start=1):
            sym = str(close.columns[j])
            ml = float(med[i, j])
            if sym in a_syms:
                tier = "A"
            else:
                tier = "B" if r <= int(tiers["B"]["ranks"][1]) else "C"
            cap = float(tiers[tier]["cap"])
            rows.append((sym, r, ml, tier, cap, tier_slippage(tier, ml, cfg)))
        key = (T + pd.Timedelta(days=1)).strftime("%Y-%m")
        tables[key] = pd.DataFrame(rows, columns=["symbol", "rank", "median_liquidity", "tier", "cap", "slippage"])
    return MonthlyUniverse(tables)


class StaticUniverse:
    """Her karar günü aynı evren tablosu (küçük el hesabı testleri için)."""

    def __init__(self, rows: list[tuple]):
        self.table = pd.DataFrame(rows, columns=["symbol", "tier", "cap", "slippage"])
        self.table["rank"] = np.arange(1, len(rows) + 1)
        self.table["median_liquidity"] = 1e9

    def key(self, t) -> str:
        return "static"

    def __call__(self, t) -> pd.DataFrame:
        return self.table


def tiny_inputs(close: dict, fill: dict | None = None, start: str = "2024-01-01",
                open_: dict | None = None) -> tuple[dict, pd.DataFrame | None]:
    """Elle verilmiş kapanış (ve dolum günü indeksli dolum fiyatı) listelerinden panel + fill_px."""
    n = len(next(iter(close.values())))
    idx = pd.date_range(start, periods=n, freq="D").as_unit("ns")
    panel = {"close": pd.DataFrame(close, index=idx, dtype=float)}
    if open_ is not None:
        panel["open"] = pd.DataFrame(open_, index=idx, dtype=float)
    fp = pd.DataFrame(fill, index=idx, dtype=float) if fill is not None else None
    return panel, fp
