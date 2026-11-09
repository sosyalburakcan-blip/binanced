"""Borsa emir kuralları (yalnızca herkese açık `exchangeInfo`): sembol eşlemesi, fiyat ve miktar adımları, en küçük
emir. Kâğıt emirler gerçek borsanın kabul edeceği biçime getirilir (canlıyla birebir dolum için).

Kurallar:
- Vadeli sembol: varlık `{BASE}USDT` için önek adayları "", 1000, 1000000, 1M sırayla aranır (USDT, PERPETUAL,
  TRADING); çarpan önekten (1000PEPEUSDT → 1000). Spot: aynı adlı TRADING sembol, çarpan 1.
- Filtreler spot biriminde saklanır: fiyat adımı / çarpan, miktar adımı × çarpan (stream.parse_message ile aynı).
  PRICE_FILTER tickSize; LOT_SIZE (limit emir) ve MARKET_LOT_SIZE (piyasa emri) stepSize/minQty/maxQty; en küçük
  tutar vadelide MIN_NOTIONAL.notional, spotta NOTIONAL/MIN_NOTIONAL minNotional; PERCENT_PRICE çarpanları.
- Yuvarlama: adet ve zarar kes tetiği aşağı, kâr al yukarı (hedef hiçbir zaman ön kayıtlı yüzdeden yakın olmaz);
  kayan nokta artığı için 1e-9 adım payı.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from trend.live.stream import FUT, SPOT, Sym, SymbolTable

PREFIXES = (("", 1.0), ("1000", 1000.0), ("1000000", 1_000_000.0), ("1M", 1_000_000.0))


def _floor(x: float, step: float) -> float:
    if not (step > 0) or not math.isfinite(x):
        return x
    return round(math.floor(x / step + 1e-9) * step, 12)


def _ceil(x: float, step: float) -> float:
    if not (step > 0) or not math.isfinite(x):
        return x
    return round(math.ceil(x / step - 1e-9) * step, 12)


@dataclass(frozen=True)
class Filters:
    symbol: str
    tick: float
    step: float
    min_qty: float
    max_qty: float
    mkt_step: float
    mkt_min_qty: float
    mkt_max_qty: float
    min_notional: float
    pct_up: float = math.inf
    pct_down: float = 0.0

    def floor_qty(self, q: float, market: bool = False) -> float:
        return _floor(q, self.mkt_step if market else self.step)

    def floor_px(self, p: float) -> float:
        return _floor(p, self.tick)

    def ceil_px(self, p: float) -> float:
        return _ceil(p, self.tick)

    def check(self, qty: float, price: float, market: bool = False) -> str | None:
        """None = geçerli; aksi halde neden (borsanın reddedeceği emir)."""
        lo = self.mkt_min_qty if market else self.min_qty
        hi = self.mkt_max_qty if market else self.max_qty
        if not qty > 0 or qty < lo - 1e-12:
            return "min_qty"
        if qty > hi + 1e-12:
            return "max_qty"
        if qty * price < self.min_notional - 1e-9:
            return "min_notional"
        return None


def symbols_from_info(info: dict, assets, venue: str) -> list[Sym]:
    out = []
    if venue == FUT:
        ok = {s["symbol"]: s for s in info.get("symbols", []) if s.get("status") == "TRADING"
              and s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT"}
        for a in assets:
            base = a[:-4] if a.endswith("USDT") else a
            for p, m in PREFIXES:
                if f"{p}{base}USDT" in ok:
                    out.append(Sym(a, FUT, f"{p}{base}USDT", m))
                    break
    else:
        ok = {s["symbol"] for s in info.get("symbols", []) if s.get("status") == "TRADING"}
        out = [Sym(a, SPOT, a, 1.0) for a in assets if a in ok]
    return out


def table_from_info(infos: dict, assets) -> SymbolTable:
    """infos: piyasa → exchangeInfo yanıtı."""
    syms = []
    for venue, info in infos.items():
        syms += symbols_from_info(info, assets, venue)
    return SymbolTable(syms)


def filters_from_info(info: dict, table: SymbolTable, venue: str) -> dict[str, Filters]:
    """varlık → Filters (spot biriminde)."""
    by = {s["symbol"]: s for s in info.get("symbols", [])}
    out = {}
    for sym in table.syms:
        if sym.venue != venue or sym.symbol not in by:
            continue
        f = {x["filterType"]: x for x in by[sym.symbol].get("filters", [])}
        m = sym.mult
        pf, lot = f.get("PRICE_FILTER", {}), f.get("LOT_SIZE", {})
        mkt = f.get("MARKET_LOT_SIZE", lot)
        if venue == FUT:
            mn = float(f.get("MIN_NOTIONAL", {}).get("notional", 0) or 0)
        else:
            mn = float((f.get("NOTIONAL") or f.get("MIN_NOTIONAL") or {}).get("minNotional", 0) or 0)
        pp = f.get("PERCENT_PRICE", {})

        def g(d, k, default):
            v = d.get(k)
            return float(v) if v not in (None, "") else default
        out[sym.asset] = Filters(
            symbol=sym.symbol, tick=g(pf, "tickSize", 0.0) / m, step=g(lot, "stepSize", 0.0) * m,
            min_qty=g(lot, "minQty", 0.0) * m, max_qty=g(lot, "maxQty", math.inf) * m,
            mkt_step=g(mkt, "stepSize", 0.0) * m, mkt_min_qty=g(mkt, "minQty", 0.0) * m,
            mkt_max_qty=g(mkt, "maxQty", math.inf) * m, min_notional=mn,
            pct_up=g(pp, "multiplierUp", math.inf), pct_down=g(pp, "multiplierDown", 0.0))
    return out
