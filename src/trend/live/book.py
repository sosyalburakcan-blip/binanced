"""Yerel emir defteri (piyasa × varlık başına ilk 20 kademe) ve defterde yürüyerek kâğıt dolum.

Kurallar:
- `depth20@100ms` her mesajda ilk 20 kademenin TAM anlık görüntüsünü verir → defter mesajla değiştirilir (artımlı
  güncelleme yok). `update_id` geri giderse (eski mesaj) atılır. Fiyat/miktar spot biriminde (stream.parse_message).
- walk(side, notional): "buy" ASK kademelerini artan fiyatla, "sell" BID kademelerini azalan fiyatla, istenen USDT
  tutarı dolana dek tüketir; walk_qty(side, qty) aynısı adetle. Kademenin bir kısmı alınabilir.
- vwap = dolan tutar / dolan adet; mid = (en iyi bid + en iyi ask) / 2; slippage_bps = alışta (vwap/mid − 1)·1e4,
  satışta (1 − vwap/mid)·1e4 (pozitif = maliyet). levels_used = dokunulan kademe sayısı.
- Derinlik yetmezse görünen kadarı doldurulur; eksik `shortfall_notional` / `shortfall_qty` olarak raporlanır,
  `worst` = dokunulan en kötü kademe fiyatı (çağıran kalan için kullanabilir).
- Boş taraf: vwap NaN, dolan 0.
"""

from __future__ import annotations

import math
from typing import NamedTuple

EPS = 1e-12


class Walk(NamedTuple):
    vwap: float
    filled_notional: float
    slippage_bps: float
    levels_used: int
    filled_qty: float
    shortfall_notional: float
    shortfall_qty: float
    mid: float
    worst: float


class Book:
    def __init__(self, venue: str, asset: str):
        self.venue, self.asset = venue, asset
        self.bids: tuple = ()
        self.asks: tuple = ()
        self.update_id = -1
        self.ts_ms = 0                       # son güncellemenin (düzeltilmiş) yerel zamanı

    def apply(self, bids, asks, update_id: int, ts_ms: int) -> bool:
        if update_id and update_id < self.update_id:
            return False
        self.bids = tuple(sorted(((float(p), float(q)) for p, q in bids if float(q) > 0), key=lambda x: -x[0]))
        self.asks = tuple(sorted(((float(p), float(q)) for p, q in asks if float(q) > 0), key=lambda x: x[0]))
        self.update_id, self.ts_ms = int(update_id or 0), int(ts_ms)
        return True

    @property
    def best_bid(self) -> float:
        return self.bids[0][0] if self.bids else math.nan

    @property
    def best_ask(self) -> float:
        return self.asks[0][0] if self.asks else math.nan

    @property
    def mid(self) -> float:
        return 0.5 * (self.best_bid + self.best_ask) if self.bids and self.asks else math.nan

    def empty(self) -> bool:
        return not (self.bids and self.asks)

    def walk(self, side: str, notional: float) -> Walk:
        return self._walk(side, notional=float(notional))

    def walk_qty(self, side: str, qty: float) -> Walk:
        return self._walk(side, qty=float(qty))

    def _walk(self, side: str, notional: float | None = None, qty: float | None = None) -> Walk:
        if side not in ("buy", "sell"):
            raise ValueError("side 'buy' veya 'sell'")
        levels = self.asks if side == "buy" else self.bids
        want = notional if notional is not None else qty
        rem = want
        fn = fq = 0.0
        used = 0
        worst = math.nan
        for p, q in levels:
            if rem <= EPS * max(1.0, want):
                break
            if notional is not None:
                take_n = min(rem, p * q)
                take_q = take_n / p
                rem -= take_n
            else:
                take_q = min(rem, q)
                take_n = take_q * p
                rem -= take_q
            fn += take_n
            fq += take_q
            used += 1
            worst = p
        mid = self.mid
        vwap = fn / fq if fq > 0 else math.nan
        if fq > 0 and math.isfinite(mid) and mid > 0:
            slip = (vwap / mid - 1.0) * 1e4 if side == "buy" else (1.0 - vwap / mid) * 1e4
        else:
            slip = math.nan
        rem = max(0.0, rem)
        if notional is not None:
            short_n, short_q = rem, (rem / worst if math.isfinite(worst) and worst > 0 else math.nan)
        else:
            short_q, short_n = rem, (rem * worst if math.isfinite(worst) else math.nan)
        if rem <= EPS * max(1.0, want):
            short_n = short_q = 0.0
        return Walk(vwap, fn, slip, used, fq, short_n, short_q, mid, worst)

    def snapshot(self, n: int = 20) -> dict:
        return {"venue": self.venue, "asset": self.asset, "update_id": self.update_id, "ts_ms": self.ts_ms,
                "bids": [list(x) for x in self.bids[:n]], "asks": [list(x) for x in self.asks[:n]]}


class Books:
    """(piyasa, varlık) → Book."""

    def __init__(self):
        self._d: dict[tuple[str, str], Book] = {}

    def get(self, venue: str, asset: str) -> Book | None:
        return self._d.get((venue, asset))

    def book(self, venue: str, asset: str) -> Book:
        b = self._d.get((venue, asset))
        if b is None:
            b = self._d[(venue, asset)] = Book(venue, asset)
        return b

    def apply(self, depth, ts_ms: int) -> bool:
        """stream.Depth olayını uygular."""
        return self.book(depth.venue, depth.asset).apply(depth.bids, depth.asks, depth.update_id, ts_ms)
