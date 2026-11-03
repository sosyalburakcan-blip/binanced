"""Kâğıt aracı ve çalıştırıcı (trend.live.paper): sinyal = sim.hourly_signals, giriş (ASK yürüyüşü), çıkış türleri
(TP yalnızca kesin üstünde, SL BID yürüyüşü, süre, fonlama, 3× likidasyon), yuva/öncelik ve sınır özsermayesi,
BTC-200, kapalı süre taraması, sürdürme, yapılandırma ve uçtan uca saatlik akış (sahte REST, ağ yok).
"""

import asyncio
import math

import numpy as np
import pytest

from tests._live_common import (BAR_MS, H_MS, T0_MS, FakeRest, S1, S2, make_cfg, set_book, synth_market)
from trend.config import ROOT
from trend.intraday.sim import hourly_close, hourly_signals
from trend.live.book import Books
from trend.live.paper import (Bars, Btc200, IdGen, LiveRunner, PaperBroker, Position, SignalEngine, StrategyCfg,
                              load_config, offline_exit)
from trend.live.recorder import Recorder
from trend.live.stream import FUT, SPOT, AggTrade, Depth, MarkPrice, Sym, SymbolTable

NaN = math.nan
K = T0_MS + 10 * H_MS            # k saatinin başı
B = K + H_MS                     # karar sınırı (giriş saatinin başı)
NOW = B + 2000
DEEP_ASK = [(100.0, 1e6)]
DEEP_BID = [(99.9, 1e6)]


def _sig(venue, assets, z, ok=None, top=None, closes=None, k=K, name="s1"):
    z = np.asarray(z, dtype=float)
    ok = np.isfinite(z) if ok is None else np.asarray(ok, dtype=bool)
    top = np.isfinite(z) if top is None else np.asarray(top, dtype=bool)
    closes = np.full(len(assets), 100.0) if closes is None else np.asarray(closes, dtype=float)
    return {"hour_ms": k, "venue": venue, "closes": closes, "z": {name: z}, "ok": {name: ok}, "top": {name: top}}


def _broker(tmp_path, cfg=None, slip=None):
    cfg = cfg or make_cfg()
    rec = Recorder(tmp_path / "live.db")
    books = Books()
    br = PaperBroker(cfg, books, rec, slip or {"AAA": 0.0005, "BBB": 0.001}, ids=IdGen("t"))
    return br, books, rec


def _deep(books, venue, assets, ts, ask=100.0, bid=99.9):
    for a in assets:
        set_book(books, venue, a, [(bid, 1e6)], [(ask, 1e6)], ts)


# --- sinyal ---

def test_signal_engine_equals_sim_hourly_signals():
    assets = ["AAA", "BBB", "CCC"]
    T1 = 300
    mkt = synth_market(T1, assets, seed=3, drift=[0.0006, -0.0003, 0.0])
    for x in (mkt.o, mkt.h, mkt.l, mkt.c):           # eksik HH:45 mumu → C NaN (iki tarafta da)
        x[4 * 260 + 3, 1] = np.nan
    cfg = make_cfg(strategies=[S1, S2])
    bars = Bars()
    for i in range(len(mkt.t15)):
        for j, a in enumerate(assets):
            if np.isfinite(mkt.c[i, j]):
                bars.add(SPOT, a, T0_MS + i * BAR_MS, mkt.o[i, j], mkt.h[i, j], mkt.l[i, j], mkt.c[i, j])
    eng = SignalEngine(cfg, assets)
    assert eng.keep_h == 240
    C = hourly_close(mkt)
    elig = np.ones(C.shape, dtype=bool)
    ref = {s.name: hourly_signals(C, elig, cfg.params(s)) for s in cfg.strategies}
    n_ok = 0
    for k in range(eng.keep_h, T1):
        sig = eng.compute(bars, SPOT, T0_MS + k * H_MS)
        np.testing.assert_array_equal(sig["closes"], C[k])
        for name, (z, ok, top) in ref.items():
            np.testing.assert_allclose(sig["z"][name], z[k], rtol=1e-9, atol=1e-12, equal_nan=True)
            np.testing.assert_array_equal(sig["ok"][name], ok[k])
            np.testing.assert_array_equal(sig["top"][name], top[k])
            n_ok += int(ok[k].sum())
    assert n_ok > 20 and np.isnan(eng.compute(bars, SPOT, T0_MS + 260 * H_MS)["z"]["s1"][1])


# --- giriş ---

def test_entry_walks_ask_with_fee_and_records(tmp_path):
    br, books, rec = _broker(tmp_path)
    set_book(books, SPOT, "AAA", DEEP_BID, [(100.0, 1.0), (100.5, 1e6)], NOW)
    (p,) = br.decide(_sig(SPOT, ["AAA", "BBB"], [2.0, NaN]), ["AAA", "BBB"], NOW)
    acc = br.accounts["s1/spot"]
    m = 1000.0 / 3
    q = 1.0 + (m - 100.0) / 100.5
    assert p.qty == pytest.approx(q) and p.p_in == pytest.approx(m / q) and p.margin == pytest.approx(m)
    assert p.fee_in == pytest.approx(m * 0.001) and acc.cash == pytest.approx(1000 - m - m * 0.001)
    assert p.tp_px == pytest.approx(p.p_in * 1.02) and p.sl_px == pytest.approx(p.p_in * 0.99)
    assert p.deadline_ms == B + 24 * H_MS and p.liq_px == -math.inf and p.hour_ms == B
    (f,) = rec.rows("SELECT * FROM fills")
    assert f["levels_used"] == 2 and f["side"] == "buy" and f["liquidity"] == "taker" and f["fee_rate"] == 0.001
    assert f["assumed_slip_bps"] == pytest.approx(5.0)
    assert f["slippage_bps"] == pytest.approx((p.p_in / 99.95 - 1) * 1e4)
    assert f["slip_diff_bps"] == pytest.approx(f["slippage_bps"] - 5.0) and '"asks"' in f["book_json"]
    orders = {o["type"]: o["status"] for o in rec.rows("SELECT * FROM paper_orders")}
    assert orders == {"market": "filled", "limit": "open", "stop_market": "open"}
    assert br.accounts["s1/fut1x"].cash == 1000.0                     # vadeli hesaplar spot sinyaliyle girmez


def test_entry_skipped_without_fresh_book(tmp_path):
    br, books, rec = _broker(tmp_path)
    set_book(books, SPOT, "AAA", DEEP_BID, DEEP_ASK, NOW - 60_000)    # 60 sn eski
    assert br.decide(_sig(SPOT, ["AAA"], [2.0]), ["AAA"], NOW) == []
    ev = rec.rows("SELECT * FROM events WHERE kind = 'entry_skip'")
    assert len(ev) == 1 and '"no_book"' in ev[0]["detail"]


# --- çıkışlar ---

def _one(tmp_path, venue=SPOT, cfg=None):
    br, books, rec = _broker(tmp_path, cfg)
    _deep(books, venue, ["AAA"], NOW)
    (p,) = br.decide(_sig(venue, ["AAA"], [2.0]), ["AAA"], NOW)
    return br, books, rec, p


def test_tp_fills_only_strictly_above(tmp_path):
    br, books, rec, p = _one(tmp_path)
    acc = br.accounts["s1/spot"]
    m, q = p.margin, p.qty
    br.on_trade(SPOT, "AAA", p.tp_px, NOW + 1000)                     # dokunmak yetmez
    br.on_trade(SPOT, "AAA", 101.5, NOW + 1500)
    assert "AAA" in acc.positions
    br.on_trade(SPOT, "AAA", p.tp_px * (1 + 1e-9), NOW + 2000)
    assert "AAA" not in acc.positions and p.reason == "tp" and p.p_out == p.tp_px == pytest.approx(102.0)
    fee_out = q * 102.0 * 0.001                                        # spot maker
    assert p.fee_out == pytest.approx(fee_out)
    assert acc.cash == pytest.approx(1000 - m - p.fee_in + m + q * 2.0 - fee_out)
    assert p.pnl == pytest.approx(q * 2.0 - p.fee_in - fee_out)
    st = {o["type"]: o["status"] for o in rec.rows("SELECT * FROM paper_orders")}
    assert st == {"market": "filled", "limit": "filled", "stop_market": "canceled"}
    f = rec.rows("SELECT * FROM fills WHERE reason = 'tp'")[0]
    assert f["liquidity"] == "maker" and f["assumed_slip_bps"] == 0.0 and f["vwap"] == pytest.approx(102.0)
    br.on_trade(SPOT, "AAA", 50.0, NOW + 3000)                          # kapandıktan sonra etkisiz
    assert acc.n_trades == 1


def test_sl_walks_bid_side(tmp_path):
    br, books, rec, p = _one(tmp_path)
    acc = br.accounts["s1/spot"]
    q = p.qty
    set_book(books, SPOT, "AAA", [(98.8, 1.0), (98.5, 1e6)], [(98.9, 1e6)], NOW + 5000)
    br.on_trade(SPOT, "AAA", p.sl_px + 1e-9, NOW + 5000)
    assert "AAA" in acc.positions
    br.on_trade(SPOT, "AAA", p.sl_px, NOW + 5100)                      # SL'de (≤) tetiklenir
    notional = 98.8 + (q - 1.0) * 98.5
    assert p.reason == "sl" and p.p_out == pytest.approx(notional / q)
    assert p.fee_out == pytest.approx(notional * 0.001)
    assert acc.cash == pytest.approx(1000 - p.margin - p.fee_in + notional - notional * 0.001)
    f = rec.rows("SELECT * FROM fills WHERE reason = 'sl'")[0]
    assert f["levels_used"] == 2 and f["trigger_price"] == pytest.approx(99.0)
    assert f["slip_vs_trigger_bps"] == pytest.approx((1 - p.p_out / 99.0) * 1e4)
    assert f["slippage_bps"] == pytest.approx((1 - p.p_out / 98.85) * 1e4)
    st = {o["type"]: o["status"] for o in rec.rows("SELECT * FROM paper_orders")}
    assert st["stop_market"] == "filled" and st["limit"] == "canceled"


def test_time_stop_market_sell_and_book_wait(tmp_path):
    br, books, rec, p = _one(tmp_path)
    acc = br.accounts["s1/spot"]
    br.on_timer(p.deadline_ms - 1)
    assert "AAA" in acc.positions
    br.on_timer(p.deadline_ms)                                         # defter bayat: beklenir
    assert "AAA" in acc.positions
    set_book(books, SPOT, "AAA", [(101.0, 1e6)], [(101.1, 1e6)], p.deadline_ms + 100)
    br.on_timer(p.deadline_ms + 200)
    assert p.reason == "time" and p.p_out == pytest.approx(101.0) and p.exit_ms == p.deadline_ms + 200
    assert p.fee_out == pytest.approx(p.qty * 101.0 * 0.001)
    # taze defter hiç gelmezse book_wait_s sonra eski defterle kapanır, işaretlenir
    br2, books2, _, p2 = _one(tmp_path / "b")
    br2.on_timer(p2.deadline_ms + 60_000)
    assert "AAA" in br2.accounts["s1/spot"].positions
    br2.on_timer(p2.deadline_ms + 121_000)
    assert p2.reason == "time" and "stale_book" in p2.flags and p2.p_out == pytest.approx(99.9)


def test_funding_charged_between_entry_and_exit(tmp_path):
    br, books, rec, p = _one(tmp_path, FUT, make_cfg(leverage=[1]))
    acc = br.accounts["s1/fut1x"]
    c0, q = acc.cash, p.qty
    assert br.on_funding("AAA", B, 0.001, 100.0, B + 500) == 0.0        # giriş fonlamadan sonra → yok
    T1 = B + 8 * H_MS
    amt = br.on_funding("AAA", T1, 0.0001, 101.0, T1 + 500)
    assert amt == pytest.approx(q * 101.0 * 0.0001) and acc.cash == pytest.approx(c0 - amt) and p.funding == amt
    assert br.on_funding("AAA", T1, 0.0001, 101.0, T1 + 900) == 0.0     # aynı fonlama iki kez alınmaz
    neg = br.on_funding("AAA", T1 + 8 * H_MS, -0.0002, 100.0, T1 + 8 * H_MS)
    assert neg == pytest.approx(-q * 100.0 * 0.0002) and acc.cash == pytest.approx(c0 - amt - neg)
    # süre çıkışı fonlama anında (T ≤ çıkış): kapandıktan sonra gelen fonlama da tahsil edilir
    _deep(books, FUT, ["AAA"], p.deadline_ms)
    br.on_timer(p.deadline_ms)
    pnl0 = p.pnl
    late = br.on_funding("AAA", p.deadline_ms, 0.0001, 100.0, p.deadline_ms + 800)
    assert late == pytest.approx(q * 100.0 * 0.0001) and p.pnl == pytest.approx(pnl0 - late)
    assert p.funding == pytest.approx(amt + neg + late)
    rows = rec.rows("SELECT * FROM funding ORDER BY funding_ms")
    assert len(rows) == 3 and rows[0]["rate"] == 0.0001 and rows[0]["account"] == "s1/fut1x"
    assert p.pnl == pytest.approx(p.exit_flow - p.margin - p.fee_in - p.funding)


def test_liquidation_at_3x_loses_whole_margin(tmp_path):
    br, books, rec, p = _one(tmp_path, FUT, make_cfg(leverage=[3]))
    acc = br.accounts["s1/fut3x"]
    m = 1000.0 / 3
    assert p.margin == pytest.approx(m) and p.notional == pytest.approx(1000.0) and p.qty == pytest.approx(10.0)
    assert p.fee_in == pytest.approx(0.5) and p.liq_px == pytest.approx(100.0 * (1 - 1 / 3 + 0.01))
    br.on_mark("AAA", p.liq_px + 1e-6, NOW + 1000)
    assert "AAA" in acc.positions
    br.on_mark("AAA", 67.0, NOW + 2000)
    assert p.reason == "liq" and "AAA" not in acc.positions
    assert acc.cash == pytest.approx(1000 - m - 0.5) and p.pnl == pytest.approx(-m - 0.5)
    assert rec.rows("SELECT liquidity FROM fills WHERE reason = 'liq'")[0]["liquidity"] == "liquidation"
    # stop likidasyon fiyatının altında dolarsa likidasyon sayılır (sim.py)
    deep_sl = StrategyCfg("s1", lookback_h=6, z_entry=0.5, confirm_h=1, tp=0.02, sl=0.5, max_hold_h=24)
    br2, books2, rec2, p2 = _one(tmp_path / "b", FUT, make_cfg(strategies=[deep_sl], leverage=[3]))
    set_book(books2, FUT, "AAA", [(45.0, 1e6)], [(45.1, 1e6)], NOW + 3000)
    br2.on_trade(FUT, "AAA", 49.0, NOW + 3000)
    assert p2.reason == "liq" and "sl_below_liq" in p2.flags


# --- yuvalar ve öncelik ---

def test_slots_priority_and_held_asset(tmp_path):
    assets = ["A", "B", "C", "D", "E"]
    br, books, rec = _broker(tmp_path, slip={})
    _deep(books, SPOT, assets, NOW)
    acc = br.accounts["s1/spot"]
    br.open(acc, "D", 100.0, B - H_MS, NOW - H_MS)                      # D zaten elde
    opened = br.decide(_sig(SPOT, assets, [3.0, 1.0, 2.0, 4.0, 5.0], ok=[1, 1, 1, 1, 0]), assets, NOW)
    assert [p.asset for p in opened] == ["A", "C"]                       # azalan z, boş yuva 2
    sk = rec.rows("SELECT detail FROM events WHERE kind = 'entry_skip'")
    assert len(sk) == 1 and '"B"' in sk[0]["detail"] and "no_slot" in sk[0]["detail"]
    # eşit z → küçük sütun önce
    br2, books2, _ = _broker(tmp_path / "b", slip={})
    _deep(books2, SPOT, assets, NOW)
    br2.accounts["s1/spot"].slots = 1
    (p,) = br2.decide(_sig(SPOT, assets, [1.0, 2.0, 2.0, NaN, 0.5]), assets, NOW)
    assert p.asset == "B"


def test_boundary_rule_positions_closed_after_B_still_occupy(tmp_path):
    assets = ["A", "B", "C", "D"]
    br, books, rec = _broker(tmp_path, slip={})
    _deep(books, SPOT, assets, NOW)
    acc = br.accounts["s1/spot"]
    d = br.open(acc, "D", 100.0, B - H_MS, NOW - H_MS)
    assert acc.cash == pytest.approx(1000 - 100 - 0.1) and d.qty == pytest.approx(1.0)
    br.exit_tp(acc, d, B + 500, 103.0)                                   # B'den sonra TP: akış 101.898
    assert acc.cash == pytest.approx(899.9 + 100 + 2.0 - 0.102)
    opened = br.decide(_sig(SPOT, assets, [3.0, 1.0, 2.0, 5.0], closes=[100, 100, 100, 101.0]), assets, NOW)
    assert [p.asset for p in opened] == ["A", "C"]                       # D hâlâ yuva ve varlık tutar
    eq = 899.9 + (100 + 1.0 * (101.0 - 100.0))                           # B anındaki nakit + D, k kapanışıyla
    assert opened[0].margin == pytest.approx(eq / 3) and opened[1].margin == pytest.approx(eq / 3)
    # B'den önce kapanan pozisyon yuva tutmaz ve akışı özsermayede
    br2, books2, _ = _broker(tmp_path / "b", slip={})
    _deep(books2, SPOT, assets, NOW)
    acc2 = br2.accounts["s1/spot"]
    d2 = br2.open(acc2, "D", 100.0, B - H_MS, NOW - H_MS)
    br2.exit_tp(acc2, d2, B - 1000, 103.0)
    opened = br2.decide(_sig(SPOT, assets, [3.0, 1.0, 2.0, 5.0]), assets, NOW)
    assert [p.asset for p in opened] == ["D", "A", "C"]
    assert opened[0].margin == pytest.approx((899.9 + 101.898) / 3)


def test_margin_capped_by_cash(tmp_path):
    br, books, rec = _broker(tmp_path, make_cfg(leverage=[3]))
    _deep(books, FUT, ["A", "B", "C"], NOW)
    acc = br.accounts["s1/fut3x"]
    acc.cash = 500.0
    acc.capital = 500.0
    opened = br.decide(_sig(FUT, ["A", "B", "C"], [3.0, 2.0, 1.0]), ["A", "B", "C"], NOW)
    assert [("margin_capped" in p.flags) for p in opened] == [False, False, True]
    assert opened[0].margin == pytest.approx(500 / 3)
    assert opened[2].margin < 500 / 3 and acc.cash == pytest.approx(0.0, abs=1e-9)    # nakit eksiye düşmez


# --- BTC-200 ---

def test_btc200_daily_decision(tmp_path):
    cfg = make_cfg(strategies=[], leverage=[], baseline="btc_200")
    br, books, rec = _broker(tmp_path, cfg, slip={"BTCUSDT": 0.0005})
    bl = Btc200(br, "btc_200/spot", asset="BTCUSDT", window=3)
    D = 86_400_000
    for i, c in enumerate([10.0, 11.0, 12.0]):
        bl.closes[T0_MS + i * D] = c
    assert bl.signal(T0_MS + D)[0] is None                              # pencere dolmadı
    set_book(books, SPOT, "BTCUSDT", [(11.9, 1e9)], [(12.0, 1e9)], T0_MS + 3 * D)
    assert bl.apply(T0_MS + 2 * D, T0_MS + 3 * D) == 1                  # 12 > 11
    acc = br.accounts["btc_200/spot"]
    p = acc.positions["BTCUSDT"]
    assert acc.cash == pytest.approx(0.0, abs=1e-9) and p.qty == pytest.approx(1000 / 1.001 / 12.0)
    assert p.tp_px == math.inf and p.deadline_ms is None
    br.on_trade(SPOT, "BTCUSDT", 1e9, T0_MS + 3 * D + 1)                  # TP/SL yok
    br.on_timer(T0_MS + 400 * D)
    assert "BTCUSDT" in acc.positions
    assert bl.apply(T0_MS + 2 * D, T0_MS + 3 * D + 10) == 1 and len(acc.positions) == 1   # elde: işlem yok
    bl.closes[T0_MS + 3 * D] = 9.0                                       # 9 < (11+12+9)/3
    set_book(books, SPOT, "BTCUSDT", [(9.0, 1e9)], [(9.1, 1e9)], T0_MS + 4 * D)
    assert bl.apply(T0_MS + 3 * D, T0_MS + 4 * D) == 0
    assert not acc.positions and acc.cash == pytest.approx(p.qty * 9.0 * (1 - 0.001))
    assert [e["kind"] for e in rec.rows("SELECT kind FROM events WHERE kind = 'baseline'")] == ["baseline"] * 3


# --- kapalı süre taraması ---

def test_offline_exit_rules():
    p = Position("p", "a", "s", SPOT, 1.0, "A", 0, 0, 100.0, 1.0, 100.0, 100.0, 0.1, tp_px=102.0, sl_px=99.0,
                 deadline_ms=10)
    assert offline_exit(p, [(1, 100, 101, 99.5, 100)], 0.001) is None
    assert offline_exit(p, [(1, 100, 102.0, 99.5, 100)], 0.001) is None             # TP'ye dokunmak yetmez
    assert offline_exit(p, [(1, 100, 102.5, 99.5, 100)], 0.001) == (1, 102.0, "tp")
    t, px, why = offline_exit(p, [(2, 100, 102.5, 98.0, 100)], 0.001)               # aynı mumda önce SL
    assert why == "sl" and px == pytest.approx(99.0 * 0.999)
    t, px, why = offline_exit(p, [(3, 98.0, 98.5, 97.0, 98)], 0.001)                # boşlukla açılış
    assert px == pytest.approx(98.0 * 0.999)
    assert offline_exit(p, [(10, 100.5, 101, 100, 100)], 0.001) == (10, pytest.approx(100.5 * 0.999), "time")
    q = Position("q", "a", "s", FUT, 3.0, "A", 0, 0, 100.0, 10.0, 333.3, 1000.0, 0.5, tp_px=102.0, sl_px=60.0,
                 liq_px=67.67, deadline_ms=10**9)
    assert offline_exit(q, [(1, 70.0, 71, 65.0, 66)], 0.001) == (1, 67.67, "liq")


# --- sürdürme ---

def test_restore_rebuilds_cash_and_positions(tmp_path):
    cfg = make_cfg(leverage=[3])
    br, books, rec = _broker(tmp_path, cfg)
    br.restore(NOW)
    _deep(books, SPOT, ["AAA", "BBB"], NOW)
    _deep(books, FUT, ["AAA", "BBB"], NOW)
    br.decide(_sig(SPOT, ["AAA", "BBB"], [2.0, 1.0]), ["AAA", "BBB"], NOW)
    br.decide(_sig(FUT, ["AAA", "BBB"], [2.0, 1.0]), ["AAA", "BBB"], NOW)
    spot = br.accounts["s1/spot"]
    br.exit_tp(spot, spot.positions["AAA"], NOW + 5000, 103.0)
    br.on_funding("AAA", B + 8 * H_MS, 0.0003, 100.0, B + 8 * H_MS)
    rec.flush()
    br2 = PaperBroker(cfg, Books(), rec, {"AAA": 0.0005, "BBB": 0.001}, ids=IdGen("u"))
    restored = br2.restore(NOW + 10_000)
    assert sorted((p.account, p.asset) for p in restored) == [("s1/fut3x", "AAA"), ("s1/fut3x", "BBB"),
                                                              ("s1/spot", "BBB")]
    for aid, acc in br.accounts.items():
        acc2 = br2.accounts[aid]
        assert acc2.cash == pytest.approx(acc.cash) and set(acc2.positions) == set(acc.positions)
        for a, p in acc.positions.items():
            p2 = acc2.positions[a]
            assert (p2.p_in, p2.qty, p2.tp_px, p2.sl_px, p2.liq_px, p2.deadline_ms) == pytest.approx(
                (p.p_in, p.qty, p.tp_px, p.sl_px, p.liq_px, p.deadline_ms))
            assert p2.tp_order == p.tp_order and p2.sl_order == p.sl_order and p2.funded == p.funded
    assert br2.accounts["s1/spot"].n_trades == 1
    other = make_cfg(strategies=[StrategyCfg("s1", 6, 0.5, 1, 0.03, 0.01, 24)], leverage=[3])
    with pytest.raises(SystemExit):
        PaperBroker(other, Books(), rec, {}).restore(NOW)


# --- yapılandırma ---

def test_load_config_reads_research_yaml(tmp_path):
    p = tmp_path / "live_v4.yaml"
    p.write_text("capital_usdt: 500\nleverage: [1, 2, 3]\nbaseline: btc_200\nstrategies:\n"
                 "  - {name: a, lookback_h: 24, z_entry: 2.0, confirm_h: 3, tp: 0.04, sl: 0.02, max_hold_h: 24}\n"
                 "run: {close_grace_s: 5}\n", encoding="utf-8")
    cfg = load_config(p, ROOT / "research_v4.yaml")
    assert cfg.capital == 500 and cfg.leverage == [1.0, 2.0, 3.0] and cfg.baseline == "btc_200"
    assert (cfg.vol_window_h, cfg.n_top, cfg.slots) == (168, 3, 3) and cfg.run["close_grace_s"] == 5
    assert cfg.costs[SPOT].taker == 0.001 and cfg.costs[FUT].maker == 0.0002 and cfg.costs[FUT].mmr == 0.01
    assert [a[0] for a in cfg.account_specs()] == ["a/spot", "a/fut1x", "a/fut2x", "a/fut3x", "btc_200/spot"]
    p.write_text(p.read_text(encoding="utf-8") + "slots: 4\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p, ROOT / "research_v4.yaml")


# --- uçtan uca saatlik akış ---

ASSETS = ["AAA", "BBB"]
SYMS = SymbolTable([Sym("AAA", SPOT, "AAAUSDT"), Sym("BBB", SPOT, "BBBUSDT"), Sym("AAA", FUT, "1000AAAUSDT", 1000.0),
                    Sym("BBB", FUT, "BBBUSDT")])


def _runner(tmp_path, k=250):
    mkt = synth_market(k + 2, ASSETS, seed=11, drift=[0.002, 0.0])
    now = [T0_MS + (k + 1) * H_MS + 1500]
    rest = FakeRest({SPOT: mkt, FUT: mkt}, SYMS)
    rr = LiveRunner(make_cfg(strategies=[S1], leverage=[2]), assets=ASSETS, slip={"AAA": 0.0005, "BBB": 0.001},
                    month="2026-01", symbols=SYMS, rest=rest, rec=Recorder(tmp_path / "r.db"),
                    now_fn=lambda: now[0], verbose=False)
    for venue in (SPOT, FUT):
        for i in range(4 * (k + 1)):
            for j, a in enumerate(ASSETS):
                rr.on_bar(venue, a, T0_MS + i * BAR_MS, mkt.o[i, j], mkt.h[i, j], mkt.l[i, j], mkt.c[i, j], now[0])
        rr.last_hour[venue] = T0_MS + (k - 1) * H_MS
    return rr, mkt, now


def _books(rr, mkt, i):
    for venue in (SPOT, FUT):
        for j, a in enumerate(ASSETS):
            c = float(mkt.c[i, j])
            rr.on_event(Depth(venue, a, 1, ((c * 0.9999, 1e9),), ((c * 1.0001, 1e9),), 0))


def test_runner_hourly_decision_exits_and_funding(tmp_path):
    k = 250
    rr, mkt, now = _runner(tmp_path, k)
    _books(rr, mkt, 4 * k + 3)
    rr.tick(now[0])
    assert rr.last_hour == {SPOT: T0_MS + k * H_MS, FUT: T0_MS + k * H_MS}
    sig = rr.rec.rows("SELECT * FROM signals WHERE phase = 'live' ORDER BY venue, asset")
    assert len(sig) == 4
    z, ok, top = hourly_signals(hourly_close(mkt), np.ones((k + 2, 2), dtype=bool), rr.cfg.params(S1))
    assert sig[0]["z"] == pytest.approx(z[k, 0]) and sig[0]["close"] == pytest.approx(mkt.c[4 * k + 3, 0])
    assert bool(ok[k, 0]) and "AAA" in rr.broker.accounts["s1/spot"].positions
    pf = rr.broker.accounts["s1/fut2x"].positions["AAA"]
    assert pf.lev == 2.0 and pf.notional == pytest.approx(2 * pf.margin)
    # TP: kesin üstünde işlem (spot)
    ps = rr.broker.accounts["s1/spot"].positions["AAA"]
    rr.on_event(AggTrade(SPOT, "AAA", 1, ps.tp_px * 1.0001, 1.0, 0, False, 0))
    assert ps.reason == "tp"
    # fonlama: T ilerleyince önceki T'de tahsil
    F = T0_MS + (k + 5) * H_MS
    mk = float(mkt.c[4 * k + 3, 0])
    rr.on_event(MarkPrice("AAA", mk, NaN, 0.0001, F, 0))
    now[0] = F + 300
    rr.on_event(MarkPrice("AAA", mk, NaN, 0.0002, F + 8 * H_MS, 0))
    assert pf.funding == pytest.approx(pf.qty * mk * 0.0001) and pf.status == "open"
    assert rr.rec.rows("SELECT * FROM events WHERE kind = 'funding_estimated'")      # son r, T'den 4 sa önce
    rr.on_event(MarkPrice("AAA", pf.liq_px * 0.99, NaN, 0.0002, F + 8 * H_MS, 0))  # işaret fiyatı ≤ likidasyon
    assert pf.reason == "liq"
    # mum boşluğu olayı
    last = rr.bars.last_open(SPOT, "BBB")
    rr.on_bar(SPOT, "BBB", last + 3 * BAR_MS, 1, 1, 1, 1, now[0])
    assert rr.rec.rows("SELECT * FROM events WHERE kind = 'kline_gap'")[0]["venue"] == SPOT
    # 15 dk özsermaye anlık görüntüsü
    rr.check_snapshot(now[0])
    rr.check_snapshot(now[0] + BAR_MS)
    eq = rr.rec.rows("SELECT * FROM equity")
    assert len(eq) >= len(rr.broker.accounts) and len(eq) % len(rr.broker.accounts) == 0
    assert all(r["ts_ms"] % BAR_MS == 0 for r in eq)


def test_runner_waits_then_backfills_missing_bar(tmp_path):
    k = 250
    rr, mkt, now = _runner(tmp_path, k)
    bar = T0_MS + k * H_MS + 3 * BAR_MS
    del rr.bars.d[(SPOT, "BBB")][bar]
    _books(rr, mkt, 4 * k + 3)
    B_ = T0_MS + (k + 1) * H_MS

    async def go():
        rr.tick(B_ + 500)                                                 # eksik mum, süre içinde: bekle
        assert rr.last_hour[SPOT] == T0_MS + (k - 1) * H_MS and rr.last_hour[FUT] == T0_MS + k * H_MS
        rr.tick(B_ + 10_500)                                              # süre doldu: REST tamamlaması
        task = rr.backfills[("hour", SPOT, T0_MS + k * H_MS)]
        assert rr.last_hour[SPOT] == T0_MS + (k - 1) * H_MS
        await task
        rr.tick(B_ + 11_000)
    asyncio.run(go())
    assert rr.last_hour[SPOT] == T0_MS + k * H_MS
    assert rr.bars.get(SPOT, "BBB", bar)[3] == pytest.approx(mkt.c[4 * k + 3, 1])
    assert rr.rec.rows("SELECT * FROM events WHERE kind = 'backfill'")[0]["venue"] == SPOT


def test_runner_warmup_from_rest(tmp_path):
    k = 250
    mkt = synth_market(k + 2, ASSETS, seed=11, drift=[0.002, 0.0])
    now = T0_MS + (k + 1) * H_MS + 5 * 60_000
    rest = FakeRest({SPOT: mkt, FUT: mkt}, SYMS)
    rr = LiveRunner(make_cfg(strategies=[S1], leverage=[2]), assets=ASSETS, slip={}, month="2026-01", symbols=SYMS,
                    rest=rest, rec=Recorder(tmp_path / "w.db"), now_fn=lambda: now, verbose=False)
    asyncio.run(rr.warmup())
    assert rr.last_hour == {SPOT: T0_MS + k * H_MS, FUT: T0_MS + k * H_MS}
    assert rr.bars.last_open(FUT, "AAA") == T0_MS + (4 * k + 3) * BAR_MS          # açık mum alınmaz
    assert rr.bars.get(FUT, "AAA", T0_MS) is None                                     # pencere dışı
    assert rr.bars.get(FUT, "AAA", T0_MS + (k - 239) * H_MS) is not None              # keep_h = 240 saat
    assert rr.bars.get(FUT, "AAA", T0_MS + 4 * k * BAR_MS)[3] == pytest.approx(mkt.c[4 * k, 0])  # çarpan geri alındı
    sig = rr.rec.rows("SELECT * FROM signals WHERE phase = 'warmup'")
    assert len(sig) == 4 and all(r["hour_ms"] == T0_MS + k * H_MS for r in sig)
    assert not any(c[0] in ("order", "account") for c in rest.calls)


class _Conn:
    """Sahte websocket: birkaç belgelenmiş biçimli mesaj, sonra sessizlik."""

    def __init__(self, msgs):
        self.msgs = list(msgs)

    async def recv(self):
        if self.msgs:
            return self.msgs.pop(0)
        await asyncio.sleep(3600)

    async def close(self):
        pass


def _run_runner(tmp_path):
    import json
    urls = []

    async def connect(url):
        urls.append(url)
        sym = "aaausdt" if "fstream" not in url else "1000aaausdt"
        return _Conn([json.dumps({"stream": f"{sym}@depth20@100ms",
                                  "data": {"lastUpdateId": 1, "bids": [["99", "1"]], "asks": [["101", "1"]]}})])
    rest = FakeRest({SPOT: synth_market(10, ASSETS), FUT: synth_market(10, ASSETS)}, SYMS)
    rr = LiveRunner(make_cfg(strategies=[S1], leverage=[2], flush_s=0.1, tick_s=0.05), assets=ASSETS, slip={},
                    month="2026-01", symbols=SYMS, rest=rest, rec=Recorder(tmp_path / "run.db"), connect=connect,
                    verbose=False)
    return rr, urls, rest


def test_runner_run_minutes_and_shutdown(tmp_path):
    rr, urls, rest = _run_runner(tmp_path)
    asyncio.run(asyncio.wait_for(rr.run(minutes=0.01), 20))
    # spot tek bağlantı; vadeli /public (defter) + /market (işlem, mum, işaret fiyatı)
    assert rr.rec.closed and len(urls) == 3 and urls[0].startswith("wss://stream.binance.com:9443/stream?streams=")
    rec = Recorder(tmp_path / "run.db")
    kinds = [e["kind"] for e in rec.rows("SELECT kind FROM events ORDER BY id")]
    assert kinds[0] == "start" and kinds[-1] == "stop" and "warmup" in kinds and kinds.count("connect") == 3
    assert {r["account"] for r in rec.rows("SELECT account FROM accounts")} == {"s1/spot", "s1/fut2x"}
    assert rec.get_state("last_seen_ms") > 0 and rec.rows("SELECT * FROM config")
    assert len(rec.rows("SELECT * FROM equity")) >= 2
    assert rr.books.get(FUT, "AAA").best_ask == pytest.approx(0.101)            # 1000AAAUSDT / 1000
    assert {c[0] for c in rest.calls} <= {"klines", "premium", "funding", "time"}
    rec.close()


def test_runner_cancel_flushes_db(tmp_path):
    rr, urls, rest = _run_runner(tmp_path)

    async def go():
        t = asyncio.create_task(rr.run())
        await asyncio.sleep(0.5)
        t.cancel()                                                     # Ctrl+C: asyncio.run ana görevi iptal eder
        with pytest.raises(asyncio.CancelledError):
            await t
    asyncio.run(go())
    assert rr.rec.closed
    rec = Recorder(tmp_path / "run.db")
    assert [e["kind"] for e in rec.rows("SELECT kind FROM events ORDER BY id")][-1] == "stop"
    rec.close()


def test_runner_baseline_daily_flow(tmp_path):
    D = 86_400_000
    syms = SymbolTable([Sym("BTCUSDT", SPOT, "BTCUSDT")])
    now = [T0_MS + 1000]
    rr = LiveRunner(make_cfg(strategies=[], leverage=[], baseline="btc_200"), assets=["BTCUSDT"],
                    slip={"BTCUSDT": 0.0005}, month="2026-01", symbols=syms, rest=FakeRest({}, syms),
                    rec=Recorder(tmp_path / "b.db"), now_fn=lambda: now[0], verbose=False)
    assert rr.venues == [SPOT]
    for i in range(200):                                                # yükselen günlük kapanışlar
        rr.baseline.closes[T0_MS - (200 - i) * D] = 100.0 + i
    rr.last_day = rr.baseline_pending = T0_MS - D
    acc = rr.broker.accounts["btc_200/spot"]
    rr.tick(now[0])
    assert not acc.positions and rr.baseline_pending is not None          # defter yok: bekler
    rr.on_event(Depth(SPOT, "BTCUSDT", 1, ((299.0, 1e6),), ((300.0, 1e6),), 0))
    rr.tick(now[0])
    assert "BTCUSDT" in acc.positions and rr.baseline_pending is None     # başlangıçta son günün kararı
    rr.on_bar(SPOT, "BTCUSDT", T0_MS + D - BAR_MS, 50.0, 50.0, 50.0, 50.0, now[0])   # günün 23:45 mumu
    now[0] = T0_MS + D + 2000
    rr.on_event(Depth(SPOT, "BTCUSDT", 2, ((49.0, 1e6),), ((50.0, 1e6),), 0))
    rr.tick(now[0])
    assert rr.last_day == T0_MS and rr.baseline.closes[T0_MS] == 50.0 and not acc.positions
    assert acc.cash == pytest.approx(1000 / 1.001 / 300.0 * 49.0 * 0.999)
