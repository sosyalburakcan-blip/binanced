"""Canlı kâğıt takip testleri için ortak yardımcılar (ağ yok, gerçek veri yok)."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from trend.intraday.sim import Costs, Market
from trend.live.paper import RUN_DEFAULTS, LiveConfig, StrategyCfg
from trend.live.stream import FUT, SPOT

H_MS = 3_600_000
BAR_MS = 900_000
T0 = "2026-01-01"
T0_MS = int(pd.Timestamp(T0).value // 1_000_000)
COSTS = {SPOT: Costs(taker=0.001, maker=0.001),
         FUT: Costs(taker=0.0005, maker=0.0002, mmr=0.01, liq_fee=0.0)}
S1 = StrategyCfg("s1", lookback_h=6, z_entry=0.5, confirm_h=1, tp=0.02, sl=0.01, max_hold_h=24)
S2 = StrategyCfg("s2", lookback_h=24, z_entry=1.0, confirm_h=3, tp=0.04, sl=0.02, max_hold_h=72)


def make_cfg(strategies=(S1,), leverage=(1, 3), baseline=None, capital=1000.0, **run) -> LiveConfig:
    return LiveConfig(capital=capital, leverage=[float(x) for x in leverage], strategies=list(strategies),
                      baseline=baseline, vol_window_h=168, n_top=3, slots=3, costs=COSTS, slip_default=0.002,
                      run={**RUN_DEFAULTS, **run})


def set_book(books, venue, asset, bids, asks, ts_ms, uid=0):
    return books.book(venue, asset).apply(bids, asks, uid, ts_ms)


def synth_market(n_hours: int, assets: list[str], seed: int = 7, drift=None) -> Market:
    """Rastgele yürüyüş 15 dk mumları (tutarlı o/h/l/c); `drift` varlık başına bar sürüklenmesi."""
    g = np.random.default_rng(seed)
    T, A = 4 * n_hours, len(assets)
    r = g.normal(0.0, 0.004, (T, A)) + (np.asarray(drift, dtype=float) if drift is not None else 0.0)
    c = 100.0 * np.exp(np.cumsum(r, axis=0))
    o = np.vstack([c[:1] * 0.999, c[:-1]])
    h = np.maximum(o, c) * (1 + g.uniform(0, 0.002, (T, A)))
    l = np.minimum(o, c) * (1 - g.uniform(0, 0.002, (T, A)))  # noqa: E741
    return Market(assets=list(assets), t15=pd.date_range(T0, periods=T, freq="15min"), o=o, h=h, l=l, c=c)


def bar_ms(i: int) -> int:
    return T0_MS + i * BAR_MS


def raw_rows(mkt: Market, j: int, start_ms: int, end_ms: int, mult: float = 1.0) -> list[list]:
    """Binance REST klines biçiminde satırlar (fiyatlar borsa biriminde: spot × çarpan)."""
    out = []
    for i in range(len(mkt.t15)):
        t = bar_ms(i)
        if t < start_ms or t > end_ms or not np.isfinite(mkt.c[i, j]):
            continue
        px = [repr(float(x[i, j]) * mult) for x in (mkt.o, mkt.h, mkt.l, mkt.c)]
        out.append([t, *px, "1.0", t + BAR_MS - 1, "100.0", 10, "0.5", "50.0", "0"])
    return out


class FakeRest:
    """PublicRest yerine: sentetik pazardan klines; diğer çağrılar sayılır."""

    def __init__(self, markets: dict | None = None, symbols=None):
        self.markets = markets or {}           # piyasa → Market
        self.symbols = symbols
        self.calls: list[tuple] = []

    def klines(self, venue, symbol, interval, start_ms, end_ms=None):
        self.calls.append(("klines", venue, symbol, interval))
        mkt = self.markets.get(venue)
        s = next((x for x in self.symbols.syms if x.venue == venue and x.symbol == symbol), None)
        if mkt is None or s is None or interval != "15m":
            return []
        return raw_rows(mkt, mkt.assets.index(s.asset), int(start_ms), int(end_ms if end_ms is not None else 2**62),
                        s.mult)

    def premium_index(self, symbol):
        self.calls.append(("premium", symbol))
        return {"nextFundingTime": 0, "lastFundingRate": "0", "markPrice": "1"}

    def funding_rate(self, symbol, start_ms, end_ms):
        self.calls.append(("funding", symbol))
        return []

    def server_time_ms(self, venue=SPOT):
        self.calls.append(("time", venue))
        return time.time() * 1000.0
