"""Yerel emir defteri (trend.live.book): el hesabı defter yürüyüşü, eksik derinlik, eski güncelleme."""

import math

import pytest

from trend.live.book import Book, Books
from trend.live.stream import SPOT, Depth

ASKS = [(100.0, 1.0), (101.0, 2.0), (102.0, 5.0)]
BIDS = [(99.0, 1.0), (98.0, 3.0)]


def _book():
    b = Book(SPOT, "AAA")
    assert b.apply(BIDS, ASKS, 10, 1000)
    return b


def test_walk_buy_notional_hand_example():
    b = _book()
    assert b.mid == 99.5 and b.best_bid == 99.0 and b.best_ask == 100.0
    w = b.walk("buy", 250.0)
    q = 1.0 + 150.0 / 101.0                         # 100 USDT ilk kademeden, 150 USDT ikinciden
    assert w.filled_notional == pytest.approx(250.0) and w.filled_qty == pytest.approx(q)
    assert w.vwap == pytest.approx(250.0 / q) and w.levels_used == 2 and w.worst == 101.0
    assert w.slippage_bps == pytest.approx((250.0 / q / 99.5 - 1) * 1e4)
    vwap, filled, slip, levels = w[:4]              # (vwap, filled_notional, slippage_bps_vs_mid, levels_used)
    assert (filled, levels) == (pytest.approx(250.0), 2)
    assert w.shortfall_notional == 0.0 and w.shortfall_qty == 0.0


def test_walk_exact_first_level():
    w = _book().walk("buy", 100.0)
    assert w.levels_used == 1 and w.vwap == 100.0 and w.slippage_bps == pytest.approx((100 / 99.5 - 1) * 1e4)


def test_walk_insufficient_depth_reports_shortfall():
    w = _book().walk("buy", 10_000.0)
    assert w.filled_notional == pytest.approx(100 + 202 + 510) and w.levels_used == 3
    assert w.shortfall_notional == pytest.approx(10_000 - 812) and w.shortfall_qty == pytest.approx((10_000 - 812) / 102)
    assert w.filled_qty == pytest.approx(8.0)


def test_walk_sell_qty_on_bids():
    b = _book()
    w = b.walk_qty("sell", 2.0)
    assert w.filled_qty == 2.0 and w.filled_notional == pytest.approx(197.0) and w.vwap == pytest.approx(98.5)
    assert w.slippage_bps == pytest.approx((1 - 98.5 / 99.5) * 1e4) and w.levels_used == 2
    w = b.walk_qty("sell", 10.0)
    assert w.filled_qty == 4.0 and w.shortfall_qty == pytest.approx(6.0) and w.shortfall_notional == pytest.approx(588.0)
    ws = b.walk("sell", 99.0)
    assert ws.levels_used == 1 and ws.filled_qty == pytest.approx(1.0)


def test_empty_side_and_bad_side():
    b = Book(SPOT, "AAA")
    b.apply(BIDS, [], 1, 0)
    w = b.walk("buy", 100.0)
    assert math.isnan(w.vwap) and w.filled_notional == 0.0 and w.levels_used == 0 and math.isnan(b.mid)
    assert b.empty()
    with pytest.raises(ValueError):
        b.walk("short", 1.0)


def test_stale_update_ignored_and_snapshot():
    books = Books()
    d1 = Depth(SPOT, "AAA", 50, tuple(BIDS), tuple(ASKS), 0)
    d0 = Depth(SPOT, "AAA", 49, ((1.0, 1.0),), ((2.0, 1.0),), 0)
    assert books.apply(d1, 5000)
    assert not books.apply(d0, 6000)                # geri giden update_id
    b = books.get(SPOT, "AAA")
    assert b.best_ask == 100.0 and b.ts_ms == 5000
    snap = b.snapshot()
    assert snap["asks"][0] == [100.0, 1.0] and snap["update_id"] == 50 and len(snap["bids"]) == 2
    # sıfır miktarlı kademe atılır, sıralama düzeltilir
    b.apply([(98.0, 1.0), (99.0, 0.0), (99.5, 2.0)], [(101.0, 1.0), (100.5, 1.0)], 51, 7000)
    assert b.bids == ((99.5, 2.0), (98.0, 1.0)) and b.asks[0] == (100.5, 1.0)
