"""Canlı akış (trend.live.stream): belgelenmiş biçimde mesaj ayrıştırma, sembol tablosu, URL'ler, yeniden bağlanma ve
üstel bekleme, bayat akış, 24 saat öncesi bilinçli yeniden bağlanma, saat sapması, REST yol koruması.

Ağ bağlantısı açılmaz: bağlantılar sahte nesnelerdir.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from trend.live import stream as st
from trend.live.stream import (FUT, SPOT, AggTrade, BookTicker, Depth, Kline, MarkPrice, PublicRest, StreamManager, Sym,
                               SymbolTable, clock_offset_ms, parse_message, rest_bars, stream_urls)

FIX = json.loads((Path(__file__).parent / "fixtures" / "live" / "messages.json").read_text(encoding="utf-8"))
TABLE = SymbolTable([Sym("BTCUSDT", SPOT, "BTCUSDT"), Sym("PEPEUSDT", FUT, "1000PEPEUSDT", 1000.0),
                     Sym("PEPEUSDT", SPOT, "PEPEUSDT")])


# --- ayrıştırma ---

def test_parse_spot_messages():
    k, bt, d, a = (parse_message(SPOT, json.dumps(m), TABLE) for m in FIX["spot"])
    assert isinstance(k, Kline) and k.asset == "BTCUSDT" and k.closed
    assert (k.open_ms, k.close_ms, k.o, k.h, k.l, k.c) == (1762170300000, 1762171199999, 107010.5, 107250.0,
                                                             106900.1, 107120.0)
    assert isinstance(bt, BookTicker) and (bt.bid, bt.bid_qty, bt.ask, bt.ask_qty) == (107119.99, 1.25, 107120.0, 0.4)
    assert isinstance(d, Depth) and d.asset == "BTCUSDT" and d.update_id == 160       # sembol akış adından
    assert d.bids == ((107119.99, 1.5), (107119.5, 2.0)) and d.asks[0] == (107120.0, 0.4)
    assert isinstance(a, AggTrade) and (a.price, a.qty, a.trade_ms, a.buyer_maker) == (107120.0, 0.015,
                                                                                       1762171200499, True)


def test_parse_futures_messages_converted_to_spot_units():
    k, bt, d, a, mp = (parse_message(FUT, m, TABLE) for m in FIX["futures"])
    assert k.asset == "PEPEUSDT" and not k.closed
    assert k.c == pytest.approx(0.01234 / 1000) and k.volume == pytest.approx(5e6 * 1000)
    assert bt.bid == pytest.approx(1.233e-5) and bt.ask_qty == pytest.approx(4e7)
    assert d.update_id == 390497878 and d.bids[0] == pytest.approx((1.233e-5, 2e6)) and len(d.asks) == 2
    # aynı fiyat-adet çarpımı (notional) birim dönüşümünde korunur
    assert d.asks[0][0] * d.asks[0][1] == pytest.approx(0.01235 * 1000)
    assert a.price == pytest.approx(1.234e-5) and a.qty == pytest.approx(1e5) and not a.buyer_maker
    assert isinstance(mp, MarkPrice) and mp.mark == pytest.approx(1.234e-5)
    assert mp.funding_rate == pytest.approx(0.00038167) and mp.next_funding_ms == 1562306400000


def test_parse_ignores_unknown():
    assert parse_message(SPOT, {"result": None, "id": 1}, TABLE) is None              # abonelik yanıtı
    assert parse_message(SPOT, {"stream": "ethusdt@aggTrade", "data": {}}, TABLE) is None
    assert parse_message(FUT, FIX["spot"][0], TABLE) is None                           # spot sembolü vadelide yok
    assert parse_message(SPOT, {"stream": "btcusdt@trade", "data": {"p": "1"}}, TABLE) is None


def test_symbol_table_from_inventory(tmp_path):
    p = tmp_path / "inventory.csv"
    p.write_text(
        "asset_id,spot_symbols,futures_symbols,futures_multiplier,futures_last\n"
        "BTCUSDT,BTCUSDT,BTCUSDT,1,2026-11-01 23:45\n"
        "POLUSDT,MATICUSDT|POLUSDT,MATICUSDT|POLUSDT,1|1,2026-11-01 23:45\n"
        "PEPEUSDT,PEPEUSDT,1000PEPEUSDT,1000,2026-11-01 23:45\n"
        "BTTCUSDT,BTTUSDT|BTTCUSDT,BTTUSDT|1000BTTCUSDT,1000|1000,2022-04-11 08:45\n"
        "TFUELUSDT,TFUELUSDT,,,\n", encoding="utf-8")
    t = SymbolTable.from_inventory(p)
    assert t.get(SPOT, "POLUSDT").symbol == "POLUSDT" and t.get(FUT, "POLUSDT").symbol == "POLUSDT"
    assert t.get(FUT, "PEPEUSDT") == Sym("PEPEUSDT", FUT, "1000PEPEUSDT", 1000.0)
    assert t.lookup(FUT, "1000pepeusdt").asset == "PEPEUSDT"
    assert t.get(FUT, "BTTCUSDT") is None and t.get(SPOT, "BTTCUSDT").symbol == "BTTCUSDT"   # eski vadeli atılır
    assert t.get(FUT, "TFUELUSDT") is None
    assert SymbolTable.from_inventory(p, assets={"BTCUSDT"}).assets(SPOT) == ["BTCUSDT"]
    assert SymbolTable.from_json(t.to_json()).get(FUT, "PEPEUSDT").mult == 1000.0


def test_stream_urls():
    (u,) = stream_urls(SPOT, ["BTCUSDT", "ETHUSDT"])
    assert u == ("wss://stream.binance.com:9443/stream?streams=btcusdt@kline_15m/btcusdt@bookTicker/"
                 "btcusdt@depth20@100ms/btcusdt@aggTrade/ethusdt@kline_15m/ethusdt@bookTicker/"
                 "ethusdt@depth20@100ms/ethusdt@aggTrade")
    fu = stream_urls(FUT, ["BTCUSDT", "1000PEPEUSDT", "ETHUSDT"], max_streams=6)
    # vadeli: defter akışları /public, işlem/mum/işaret fiyatı /market (2026'da ayrıldı)
    pub = [x for x in fu if x.startswith("wss://fstream.binance.com/public/stream?streams=")]
    mkt = [x for x in fu if x.startswith("wss://fstream.binance.com/market/stream?streams=")]
    assert len(pub) + len(mkt) == len(fu) == 3
    assert all("depth" in x or "bookTicker" in x for x in "/".join(p.split("streams=")[1] for p in pub).split("/"))
    assert not any("depth" in x or "bookTicker" in x for x in "/".join(p.split("streams=")[1] for p in mkt).split("/"))
    names = "/".join(x.split("streams=")[1] for x in fu).split("/")
    assert len(names) == 15 and "1000pepeusdt@markPrice@1s" in names


# --- bağlantı yöneticisi ---

class FakeConn:
    """recv: sıradaki mesaj; mesajlar bitince `then`: 'raise' (kopma), 'block' (sessiz), 'stop' (durdur + sessiz),
    'repeat' (son mesajı sonsuza dek, `gap` sn arayla)."""

    def __init__(self, msgs, then="raise", stop=None, gap=0.0):
        self.msgs, self.then, self.stop, self.gap = list(msgs), then, stop, gap
        self.last = None
        self.closed = False

    async def recv(self):
        if self.msgs:
            self.last = self.msgs.pop(0)
            return self.last
        if self.then == "raise":
            raise ConnectionError("sunucu kapattı")
        if self.then == "repeat":
            await asyncio.sleep(self.gap)
            return self.last
        if self.then == "stop" and self.stop is not None:
            self.stop.set()
        await asyncio.sleep(3600)

    async def close(self):
        self.closed = True


SPOT_URL = stream_urls(SPOT, ["BTCUSDT"])[0]


def _manager(plan, events, got, **kw):
    async def connect(url):
        step = plan.pop(0)
        if isinstance(step, Exception):
            raise step
        return step
    delays = []

    async def sleep(d):
        delays.append(d)
    kw = {"rng": lambda: 0.0, "base_s": 1.0, "max_s": 8.0, "poll_s": 0.01, **kw}
    m = StreamManager(SPOT, SPOT_URL, TABLE, got.append, lambda k, d, tb: events.append((k, d, tb)),
                      connect=connect, sleep=sleep, **kw)
    return m, delays


def test_reconnect_with_exponential_backoff():
    async def go():
        stop = asyncio.Event()
        msgs = [json.dumps(m) for m in FIX["spot"]]
        c1, c2 = FakeConn(msgs, "raise"), FakeConn([], "stop", stop)
        events, got = [], []
        m, delays = _manager([OSError("ağ yok"), OSError("ağ yok"), c1, OSError("ağ yok"), c2], events, got)
        await asyncio.wait_for(m.run(stop), 5)
        return m, delays, events, got, c1, c2
    m, delays, events, got, c1, c2 = asyncio.run(go())
    assert delays == [1.0, 2.0, 1.0, 2.0]                 # mesaj alan bağlantıdan sonra sayaç sıfırlandı
    kinds = [e[0] for e in events]
    assert kinds == ["connect_error", "connect_error", "connect", "gap", "disconnect", "connect_error", "connect", "gap",
                     "disconnect"]
    disc = [e for e in events if e[0] == "disconnect"]
    assert "ConnectionError" in disc[0][1]["reason"] and "ConnectionError" in disc[0][2]   # traceback kaydı
    assert disc[1][1]["reason"] == "stop"
    gap = next(e for e in events if e[0] == "gap")[1]
    assert gap["to_ms"] >= gap["from_ms"] and gap["down_s"] >= 0
    assert [type(x).__name__ for x in got] == ["Kline", "BookTicker", "Depth", "AggTrade"]
    assert c1.closed and c2.closed and m.stats["connects"] == 2 and m.stats["messages"] == 4


def test_backoff_cap_and_jitter():
    m = StreamManager(SPOT, SPOT_URL, TABLE, lambda e: None, base_s=1.0, max_s=8.0, jitter=0.25, rng=lambda: 0.5)
    assert m.backoff(0) == pytest.approx(1.125)
    assert m.backoff(3) == pytest.approx(9.0) and m.backoff(10) == pytest.approx(9.0)   # 8 · 1.125


def test_stale_connection_detected():
    async def go():
        stop = asyncio.Event()
        events, got = [], []
        m, delays = _manager([FakeConn([json.dumps(FIX["spot"][3])], "block"), FakeConn([], "stop", stop)],
                             events, got, stale_s=0.05)
        await asyncio.wait_for(m.run(stop), 5)
        return events, delays
    events, delays = asyncio.run(go())
    kinds = [e[0] for e in events]
    assert "stale" in kinds and events[kinds.index("stale")][1]["silent_s"] >= 0.05
    assert next(e for e in events if e[0] == "disconnect")[1]["reason"] == "stale"
    assert delays == [1.0]


def test_stale_single_stream_detected():
    async def go():
        stop = asyncio.Event()
        events, got = [], []
        kl = json.dumps(FIX["spot"][0])                   # yalnızca kline gelir; depth susar
        m, _ = _manager([FakeConn([kl], "repeat"), FakeConn([], "stop", stop)], events, got,
                        stale_s=10.0, stream_stale_s=0.05)
        await asyncio.wait_for(m.run(stop), 5)
        return events, got
    events, got = asyncio.run(go())
    ss = next(e for e in events if e[0] == "stale_stream")[1]
    assert ss["streams"] == ["btcusdt@depth20@100ms"] and len(got) > 1


def test_proactive_reconnect_before_24h_cut():
    t = [0.0]

    def clock():
        t[0] += 1000.0
        return t[0]

    async def go():
        stop = asyncio.Event()
        events, got = [], []
        m, delays = _manager([FakeConn([json.dumps(FIX["spot"][3])], "repeat"), FakeConn([], "stop", stop)],
                             events, got, clock=clock, wall=lambda: 450.0, max_age_s=5000.0,
                             stream_stale_s=1e9)
        await asyncio.wait_for(m.run(stop), 5)
        return events, delays
    events, delays = asyncio.run(go())
    assert [e[0] for e in events][:3] == ["connect", "max_age", "disconnect"]
    assert events[2][1]["reason"] == "max_age" and delays == []          # beklemesiz yeniden bağlantı
    m = StreamManager(SPOT, SPOT_URL, TABLE, lambda e: None, wall=lambda: 900.0 * 7 + 30.0)
    assert m.near_boundary()                                             # 15 dk sınırına 30 sn: bekle
    m.wall = lambda: 900.0 * 7 + 400.0
    assert not m.near_boundary()


def test_handler_error_does_not_drop_connection():
    def bad(ev):
        raise RuntimeError("işleyici hatası")

    async def go():
        stop = asyncio.Event()
        events = []
        msgs = [json.dumps(FIX["spot"][3])] * 3

        async def connect(url):
            return FakeConn(msgs, "stop", stop)
        m = StreamManager(SPOT, SPOT_URL, TABLE, bad, lambda k, d, tb: events.append((k, d, tb)), connect=connect,
                          poll_s=0.01)
        await asyncio.wait_for(m.run(stop), 5)
        return events, m
    events, m = asyncio.run(go())
    he = [e for e in events if e[0] == "handler_error"]
    assert len(he) == 1 and "RuntimeError" in he[0][2] and m.stats["errors"] == 3
    assert [e[1]["reason"] for e in events if e[0] == "disconnect"] == ["stop"]


# --- saat ve REST ---

def test_clock_offset_uses_shortest_round_trip():
    walls = iter([100.0, 100.4, 200.0, 200.02, 300.0, 300.1])
    servers = iter([100_500.0, 200_250.0, 300_000.0])
    off, rtt = clock_offset_ms(lambda: next(servers), wall=lambda: next(walls), samples=3)
    assert rtt == pytest.approx(20.0) and off == pytest.approx(200_250.0 - 200_010.0)


class _Resp:
    def __init__(self, payload, status=200, headers=None):
        self._p, self.status_code, self.headers, self.text = payload, status, headers or {}, ""

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Session:
    def __init__(self, pages):
        self.pages, self.calls, self.headers = list(pages), [], {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return self.pages.pop(0)


def test_public_rest_only_public_paths():
    s = _Session([])
    r = PublicRest(session=s)
    for bad in ("/api/v3/order", "/api/v3/account", "/fapi/v1/order", "/fapi/v2/account", "/sapi/v1/capital/config/getall",
                "/api/v3/userDataStream", "/fapi/v1/listenKey"):
        with pytest.raises(ValueError):
            r.get(SPOT, bad)
    assert s.calls == []
    assert not any(w in p.lower() for p in PublicRest.ALLOWED for w in ("order", "account", "listen", "user", "sapi"))
    assert "X-MBX-APIKEY" not in s.headers


def test_public_rest_klines_paginates_and_retries():
    row = lambda t: [t, "1", "2", "0.5", "1.5", "10", t + 899_999, "15", 3, "5", "7", "0"]  # noqa: E731
    pages = [_Resp([row(i * 900_000) for i in range(3)]), _Resp({}, 503), _Resp([row(3 * 900_000)])]
    s = _Session(pages)
    sleeps = []
    r = PublicRest(session=s, sleep=sleeps.append)
    r.LIMIT = {SPOT: 3, FUT: 3}
    rows = r.klines(SPOT, "BTCUSDT", "15m", 0, 10 * 900_000)
    assert [x[0] for x in rows] == [0, 900_000, 1_800_000, 2_700_000] and sleeps == [1]
    assert s.calls[0][0] == "https://data-api.binance.vision/api/v3/klines"
    assert s.calls[2][1]["startTime"] == 1_800_000 + 1
    bars = rest_bars(rows, mult=1000.0, now_ms=2_700_000 + 899_999)        # son mum kapanmamış → atılır
    assert len(bars) == 3 and bars[0] == (0, 0.001, 0.002, 0.0005, 0.0015)


def test_websockets_imported_lazily():
    assert "websockets" not in sys.modules or not hasattr(st, "websockets")
    src = (Path(st.__file__)).read_text(encoding="utf-8")
    top = src.split("async def ws_connect")[0]
    assert "import websockets" not in top
