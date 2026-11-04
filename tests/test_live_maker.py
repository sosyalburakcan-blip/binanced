"""Maker yürütme (trend.live.paper Kural 11): BID'de post-only alış, kuyruk/kesin geçiş dolumu, BID takibi ve süre
sonu iptali, SL'de maker satış → süre dolunca piyasa satışı, süre çıkışının SL'ye geçmesi, yeniden başlatmada iptal,
bildirim metinleri ve sağlık kontrolünde "dolmadı" açıklaması (ağ yok).
"""

import json
import math

import pytest

from tests._live_common import H_MS, make_cfg, set_book
from tests.test_live_paper import B, NOW, _sig
from trend.live.book import Books
from trend.live.paper import IdGen, PaperBroker, trade_text
from trend.live.recorder import Recorder
from trend.live.stream import SPOT

M = 1000.0 / 3                   # yuva başına margin (spot 1×)


def _maker(tmp_path, **run):
    cfg = make_cfg(execution="maker", **run)
    rec = Recorder(tmp_path / "live.db")
    books = Books()
    br = PaperBroker(cfg, books, rec, {"AAA": 0.0005, "BBB": 0.001}, ids=IdGen("t"))
    notes = []
    br.notify = lambda kind, acc, pos, **info: notes.append((kind, acc.acc_id, pos.asset, info))
    br.restore(NOW - 1000)
    return br, books, rec, notes


def _place(br, books, bid=99.9, bid_qty=50.0, ts=NOW):
    set_book(books, SPOT, "AAA", [(bid, bid_qty), (bid - 0.1, 1e6)], [(bid + 0.1, 1e6)], ts)
    (p,) = br.decide(_sig(SPOT, ["AAA", "BBB"], [2.0, math.nan]), ["AAA", "BBB"], ts)
    return p


def _orders(rec):
    return {(o["reason"], o["type"]): (o["status"], o["price"]) for o in rec.rows("SELECT * FROM paper_orders")}


def test_entry_rests_at_bid_and_fills_after_queue_or_trade_through(tmp_path):
    br, books, rec, notes = _maker(tmp_path)
    p = _place(br, books)
    acc = br.accounts["s1/spot"]
    fee = M * 0.001
    assert p.status == "pending" and acc.pending == {"AAA": p} and not acc.positions
    assert acc.cash == pytest.approx(1000 - M - fee) and br.equity(acc)[2] == pytest.approx(1000.0)
    assert _orders(rec)[("entry", "limit_maker")] == ("open", 99.9) and not rec.rows("SELECT * FROM positions")
    br.on_trade(SPOT, "AAA", 99.95, NOW + 10, 100.0, False)        # BID'in üstünde: dolmaz
    br.on_trade(SPOT, "AAA", 99.9, NOW + 20, 30.0, True)           # kuyruk 50 + kendi adedimiz ≈ 3.34
    br.on_trade(SPOT, "AAA", 99.9, NOW + 30, 40.0, False)          # alıcı başlatan: BID kuyruğunu tüketmez
    assert acc.pending
    br.on_trade(SPOT, "AAA", 99.9, NOW + 40, 25.0, True)           # 55 ≥ 53.34 → dolum
    pos = acc.positions["AAA"]
    assert not acc.pending and pos.status == "open" and pos.entry_ms == NOW + 40 and pos.p_in == 99.9
    assert pos.qty == pytest.approx(M / 99.9) and pos.fee_in == pytest.approx(fee)
    assert pos.tp_px == pytest.approx(99.9 * 1.02) and pos.sl_px == pytest.approx(99.9 * 0.99)
    assert pos.deadline_ms == B + 24 * H_MS and acc.cash == pytest.approx(1000 - M - fee)
    (f,) = rec.rows("SELECT * FROM fills")
    assert f["liquidity"] == "maker" and f["fee_rate"] == 0.001 and f["vwap"] == 99.9 and "maker" in f["flags"]
    o = _orders(rec)
    assert o[("entry", "limit_maker")][0] == "filled" and o[("sl", "stop_maker")][0] == "open"
    assert o[("tp", "limit")][0] == "open"
    detail = json.loads(rec.rows("SELECT detail FROM paper_orders WHERE type = 'limit_maker'")[0]["detail"])
    assert detail["n_moves"] == 0 and detail["queue"] == 50.0 and detail["wait_s"] == pytest.approx(0.04)
    assert [n[0] for n in notes] == ["entry"] and notes[0][3]["maker"] is True
    assert notes[0][3]["slip_bps"] == pytest.approx((99.9 / 99.95 - 1) * 1e4)

    br2, books2, _, _ = _maker(tmp_path / "b")
    p2 = _place(br2, books2)
    br2.on_trade(SPOT, "AAA", 99.89, NOW + 5, 0.001, False)        # fiyat emrin kesin altında → hemen dolar
    assert p2.status == "open" and p2.p_in == 99.9


def test_entry_follows_bid_then_cancels_at_next_decision(tmp_path):
    br, books, rec, notes = _maker(tmp_path)
    p = _place(br, books)
    o = p.maker
    set_book(books, SPOT, "AAA", [(100.2, 7.0)], [(100.3, 1e6)], NOW + 500)
    br.on_book(SPOT, "AAA", NOW + 500)                             # 1 sn dolmadan taşınmaz
    assert o.price == 99.9 and o.n_moves == 0
    br.on_book(SPOT, "AAA", NOW + 1500)
    assert o.price == 100.2 and o.queue == 7.0 and o.n_moves == 1 and o.traded == 0.0
    set_book(books, SPOT, "AAA", [(100.0, 9.0)], [(100.1, 1e6)], NOW + 3000)
    br.on_book(SPOT, "AAA", NOW + 3000)                            # BID geri çekildi: emir yerinde kalır
    assert o.price == 100.2
    acc = br.accounts["s1/spot"]
    br.on_timer(B + H_MS - 1)
    assert acc.pending
    br.on_timer(B + H_MS)
    assert not acc.pending and not acc.positions and acc.cash == pytest.approx(1000.0)
    assert _orders(rec)[("entry", "limit_maker")] == ("canceled", 100.2)
    (e,) = rec.rows("SELECT detail FROM events WHERE kind = 'entry_skip'")
    assert json.loads(e["detail"])["why"] == "unfilled"
    assert notes == [("unfilled", "s1/spot", "AAA", {"moves": 1})]
    assert _place(br, books, ts=B + H_MS + 2000).status == "pending"   # yuva ve varlık yeniden serbest


def test_sl_tries_maker_then_market(tmp_path):
    for case in ("maker", "timeout"):
        br, books, rec, _ = _maker(tmp_path / case)
        _place(br, books)
        br.on_trade(SPOT, "AAA", 99.8, NOW + 10, 1.0, True)           # giriş dolar (kesin altında)
        acc = br.accounts["s1/spot"]
        pos = acc.positions["AAA"]
        t = NOW + 60_000
        set_book(books, SPOT, "AAA", [(98.8, 1e6)], [(98.9, 5.0)], t)
        br.on_trade(SPOT, "AAA", 98.85, t, 1.0, True)                 # ≤ SL (98.901) → maker satış ASK'ta
        assert pos.maker is not None and pos.maker.price == 98.9 and pos.maker.deadline_ms == t + 30_000
        o = _orders(rec)
        assert o[("sl", "stop_maker")][0] == "triggered" and o[("tp", "limit")][0] == "canceled"
        assert o[("sl", "limit_maker")] == ("open", 98.9)
        if case == "maker":
            br.on_trade(SPOT, "AAA", 98.95, t + 5000, 1.0, False)     # ASK'ın kesin üstünde → dolar
            assert pos.status == "closed" and pos.reason == "sl" and pos.p_out == 98.9
            assert pos.fee_out == pytest.approx(pos.qty * 98.9 * 0.001) and "maker_exit" in pos.flags
            assert _orders(rec)[("sl", "limit_maker")][0] == "filled"
            assert rec.rows("SELECT liquidity FROM fills WHERE side = 'sell'")[0]["liquidity"] == "maker"
        else:
            br.on_timer(t + 29_999)
            assert pos.status == "open"
            br.on_timer(t + 30_000)
            assert pos.status == "closed" and pos.reason == "sl" and pos.p_out == pytest.approx(98.8)
            assert "maker_timeout" in pos.flags
            o = _orders(rec)
            assert o[("sl", "limit_maker")][0] == "canceled" and o[("sl", "market")][0] == "filled"
            assert rec.rows("SELECT liquidity FROM fills WHERE side = 'sell'")[0]["liquidity"] == "taker"
            assert "maker dolmadı → piyasa satışı" in trade_text("exit", acc, pos)
        assert pos.pnl == pytest.approx(pos.qty * (pos.p_out - 99.9) - pos.fee_in - pos.fee_out)
        assert acc.cash == pytest.approx(1000 + pos.pnl)


def test_time_exit_is_maker_and_switches_to_sl_wait(tmp_path):
    br, books, rec, _ = _maker(tmp_path)
    _place(br, books)
    br.on_trade(SPOT, "AAA", 99.8, NOW + 10, 1.0, True)
    pos = br.accounts["s1/spot"].positions["AAA"]
    d = pos.deadline_ms
    set_book(books, SPOT, "AAA", [(99.0, 1e6)], [(99.1, 1e6)], d)
    br.on_timer(d)
    assert pos.maker.reason == "time" and pos.maker.price == 99.1 and pos.maker.deadline_ms == d + 300_000
    br.on_trade(SPOT, "AAA", 98.9, d + 1000, 1.0, True)              # süre satışı sürerken SL tetiklendi
    assert pos.maker.reason == "sl" and pos.maker.deadline_ms == d + 31_000
    br.on_timer(d + 31_000)
    assert pos.status == "closed" and pos.reason == "sl" and "maker_timeout" in pos.flags


def test_restart_cancels_working_maker_orders(tmp_path):
    br, books, rec, _ = _maker(tmp_path)
    _place(br, books)
    rec.flush()
    br2 = PaperBroker(make_cfg(execution="maker"), books, rec, {}, ids=IdGen("u"))
    assert br2.restore(NOW + 5000) == []
    (o,) = rec.rows("SELECT * FROM paper_orders")
    assert o["status"] == "canceled" and json.loads(o["detail"]) == {"why": "restart"}
    assert br2.accounts["s1/spot"].cash == 1000.0 and not br2.accounts["s1/spot"].pending


def test_maker_texts_and_config(tmp_path):
    br, books, _, _ = _maker(tmp_path)
    p = _place(br, books)
    acc = br.accounts["s1/spot"]
    assert trade_text("unfilled", acc, p, moves=3) == "⚪ GİRİŞ DOLMADI s1/spot AAA · maker alış 99.9 (3 kez taşındı) · iptal"
    br.on_trade(SPOT, "AAA", 99.8, NOW + 10, 1.0, True)
    s = trade_text("entry", acc, acc.positions["AAA"], slip_bps=-0.5, maker=True)
    assert s.startswith("🟢 GİRİŞ s1/spot AAA @ 99.9") and "· maker · karar fiyatına göre -0.5bps" in s
    from tests.test_live_paper import ROOT, load_config
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text("leverage: [3]\nstrategies: []\nrun: {execution: hızlı}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="execution"):
        load_config(cfg_file, ROOT / "research_v4.yaml")
