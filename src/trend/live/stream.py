"""Canlı piyasa verisi (yalnızca herkese açık): Binance spot ve USDT-M vadeli birleşik websocket akışları + REST.

KURAL: yalnızca kâğıt işlem. Emir, hesap veya kullanıcı verisi uç noktası hiç çağrılmaz; API anahtarı ve `.env`
okunmaz. REST çağrıları `PublicRest.ALLOWED` dışındaki her yol için hata verir (imza/anahtar başlığı yok).

Akışlar (sembol başına; birleşik akış `<taban>/stream?streams=a/b/c`, mesaj = {"stream": ad, "data": yük}):
- spot `wss://stream.binance.com:9443`: `<s>@kline_15m`, `<s>@bookTicker`, `<s>@depth20@100ms`, `<s>@aggTrade`.
- vadeli: aynıları + `<s>@markPrice@1s` (işaret fiyatı `p`, fonlama oranı `r`, sonraki
  fonlama zamanı `T`).
Ayrıştırıcılar yükü küçük dataclass'lara çevirir. Varlık kimliği = spot asset_id; fiyatlar spot biriminde: vadeli fiyat
/ çarpan, miktar × çarpan (çarpan `data/intraday/inventory.csv` `futures_multiplier`, ör. 1000PEPEUSDT → 1000; yalnızca
okunur). Kısmi derinlik yükü spotta sembol içermez → sembol akış adından alınır.

Bağlantı yöneticisi (`StreamManager`, bağlantı başına bir tane, asyncio):
- Bağlantı hatası veya kopmada üstel bekleme: min(max_s, base_s·2^deneme)·(1 + jitter·U[0,1)); bağlantıda en az bir
  mesaj alındıysa deneme sayacı sıfırlanır.
- Binance bağlantıyı 24 saatte keser: bağlantı yaşı `max_age_s`'yi (23,5 sa) geçince, 15 dk sınırının
  ±`boundary_guard_s` dışında kalan ilk anda bilinçli olarak yeniden bağlanılır (mum kapanışı kaçmasın), beklemesiz.
- Bayat akış: `stale_s` boyunca hiç mesaj gelmezse ("stale") veya izlenen akışlardan (`watch`: depth, markPrice) biri
  `stream_stale_s` boyunca susarsa ("stale_stream") bağlantı kapatılıp yeniden açılır.
- Her bağlantı, kopma (neden + traceback), bayatlık, bağlantı hatası ve kesinti süresi ("gap": kopmadan yeniden
  bağlanmaya kadar) `on_status(tür, ayrıntı, traceback)` ile olay olarak bildirilir. İşleyici (handler) hatası
  bağlantıyı düşürmez; aynı hata 60 sn içinde tekrarlanırsa sayılır, bir kez kaydedilir.
- ping/pong websockets kütüphanesinde: sunucu ping'ine otomatik pong, istemci ping'i 20 sn.
Saat: `clock_offset_ms` = sunucu zamanı − istek ortasındaki yerel zaman (REST `/api/v3/time`, en kısa gidiş-dönüşlü
örnek).

Varsayımlar:
- Güncel sembol, envanterdeki `spot_symbols`/`futures_symbols` zincirinin SON elemanıdır (MATICUSDT|POLUSDT → POLUSDT;
  çarpan zinciri de aynı sırada). Vadeli son mum tarihi envanterdeki en geç vadeli tarihten `FUT_STALE_DAYS` günden
  eskiyse vadeli yok sayılır (ör. 1000BTTCUSDT, 2022'de bitti).
- REST tabanları: spot `data-api.binance.vision` (yalnızca piyasa verisi sunan alan adı; settings.yaml `rest_base`),
  vadeli `fapi.binance.com`. Websocket ve REST tabanları çağırandan değiştirilebilir.
- websockets kütüphanesi yalnızca `ws_connect` içinde içe aktarılır; çekirdek mantık onsuz test edilir.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests

from trend.config import ROOT

SPOT, FUT = "spot", "futures"
VENUES = (SPOT, FUT)
WS_BASE = {SPOT: "wss://stream.binance.com:9443/stream?streams=",
           FUT: "wss://fstream.binance.com/market/stream?streams="}
# Binance vadeli akışları iki uca ayrıldı (2026-11-03 canlı denemede doğrulandı: eski `/stream` ucu markPrice ve
# aggTrade göndermiyor): emir defteri/en iyi fiyat `/public`, işlem/mum/işaret fiyatı `/market`.
FUT_PUBLIC_BASE = "wss://fstream.binance.com/public/stream?streams="
FUT_PUBLIC_KINDS = ("depth", "bookTicker")
REST_BASE = {SPOT: "https://data-api.binance.vision", FUT: "https://fapi.binance.com"}
KINDS = {SPOT: ("kline_15m", "bookTicker", "depth20@100ms", "aggTrade"),
         FUT: ("kline_15m", "bookTicker", "depth20@100ms", "aggTrade", "markPrice@1s")}
MAX_STREAMS = {SPOT: 1024, FUT: 200}     # bağlantı başına akış sınırı (Binance)
INVENTORY = ROOT / "data" / "intraday" / "inventory.csv"
FUT_STALE_DAYS = 7
BAR_MS = 15 * 60_000


# ---------------------------------------------------------------------------------------------------------------
# Semboller


@dataclass(frozen=True)
class Sym:
    asset: str
    venue: str
    symbol: str
    mult: float = 1.0


class SymbolTable:
    """(piyasa, borsa sembolü) ↔ varlık ve vadeli fiyat çarpanı."""

    def __init__(self, syms):
        self.syms = list(syms)
        self._by_sym = {(s.venue, s.symbol.upper()): s for s in self.syms}
        self._by_asset = {(s.venue, s.asset): s for s in self.syms}

    @classmethod
    def from_inventory(cls, path: Path | str = INVENTORY, assets=None) -> SymbolTable:
        inv = pd.read_csv(path, dtype=str, keep_default_na=False)
        fl = pd.to_datetime(inv["futures_last"].where(inv["futures_last"] != ""), errors="coerce")
        newest = fl.max()
        out = []
        for i, r in inv.iterrows():
            a = r["asset_id"]
            if assets is not None and a not in assets:
                continue
            spot = [s for s in r["spot_symbols"].split("|") if s]
            if spot:
                out.append(Sym(a, SPOT, spot[-1], 1.0))
            fut = [s for s in r["futures_symbols"].split("|") if s]
            mult = [m for m in r["futures_multiplier"].split("|") if m]
            if fut and pd.notna(fl.iloc[i]) and fl.iloc[i] >= newest - pd.Timedelta(days=FUT_STALE_DAYS):
                out.append(Sym(a, FUT, fut[-1], float(mult[-1]) if mult else 1.0))
        return cls(out)

    def get(self, venue: str, asset: str) -> Sym | None:
        return self._by_asset.get((venue, asset))

    def lookup(self, venue: str, symbol: str) -> Sym | None:
        return self._by_sym.get((venue, symbol.upper()))

    def assets(self, venue: str) -> list[str]:
        return [s.asset for s in self.syms if s.venue == venue]

    def to_json(self) -> list[dict]:
        return [{"asset": s.asset, "venue": s.venue, "symbol": s.symbol, "mult": s.mult} for s in self.syms]

    @classmethod
    def from_json(cls, rows: list[dict]) -> SymbolTable:
        return cls(Sym(r["asset"], r["venue"], r["symbol"], float(r["mult"])) for r in rows)


def stream_names(venue: str, symbols, kinds=None) -> list[str]:
    return [f"{s.lower()}@{k}" for s in symbols for k in (kinds or KINDS[venue])]


def stream_urls(venue: str, symbols, kinds=None, base: str | None = None, max_streams: int | None = None) -> list[str]:
    """Birleşik akış URL'leri (bağlantı başına en fazla `max_streams` akış)."""
    names = stream_names(venue, symbols, kinds)
    n = int(max_streams or MAX_STREAMS[venue])
    if venue == FUT and base is None:     # vadeli: defter akışları /public, diğerleri /market
        pub = [x for x in names if x.split("@", 1)[1].startswith(FUT_PUBLIC_KINDS)]
        mkt = [x for x in names if x not in pub]
        return ([FUT_PUBLIC_BASE + "/".join(pub[i: i + n]) for i in range(0, len(pub), n)]
                + [WS_BASE[FUT] + "/".join(mkt[i: i + n]) for i in range(0, len(mkt), n)])
    return [(base or WS_BASE[venue]) + "/".join(names[i: i + n]) for i in range(0, len(names), n)]


# ---------------------------------------------------------------------------------------------------------------
# Mesajlar


@dataclass(frozen=True, slots=True)
class Kline:
    venue: str
    asset: str
    open_ms: int
    close_ms: int
    o: float
    h: float
    l: float  # noqa: E741
    c: float
    volume: float
    closed: bool
    event_ms: int


@dataclass(frozen=True, slots=True)
class BookTicker:
    venue: str
    asset: str
    update_id: int
    bid: float
    bid_qty: float
    ask: float
    ask_qty: float
    event_ms: int


@dataclass(frozen=True, slots=True)
class Depth:
    venue: str
    asset: str
    update_id: int
    bids: tuple          # ((fiyat, miktar), ...) azalan fiyat
    asks: tuple          # artan fiyat
    event_ms: int


@dataclass(frozen=True, slots=True)
class AggTrade:
    venue: str
    asset: str
    trade_id: int
    price: float
    qty: float
    trade_ms: int
    buyer_maker: bool
    event_ms: int


@dataclass(frozen=True, slots=True)
class MarkPrice:
    asset: str
    mark: float
    index: float
    funding_rate: float
    next_funding_ms: int
    event_ms: int
    venue: str = FUT


def _levels(rows, m: float) -> tuple:
    return tuple((float(p) / m, float(q) * m) for p, q in rows)


def parse_message(venue: str, msg: Any, table: SymbolTable):
    """Birleşik akış mesajı → olay dataclass'ı; tanınmayan akış veya sembol → None."""
    if isinstance(msg, (str, bytes, bytearray)):
        msg = json.loads(msg)
    stream, data = msg.get("stream"), msg.get("data")
    if not stream or data is None:
        return None                               # ör. abonelik yanıtı {"result": null, "id": 1}
    sym, _, kind = stream.partition("@")
    s = table.lookup(venue, sym)
    if s is None:
        return None
    m = s.mult
    E = int(data.get("E") or 0)
    if kind.startswith("kline"):
        k = data["k"]
        return Kline(venue, s.asset, int(k["t"]), int(k["T"]), float(k["o"]) / m, float(k["h"]) / m,
                     float(k["l"]) / m, float(k["c"]) / m, float(k["v"]) * m, bool(k["x"]), E)
    if kind == "bookTicker":
        return BookTicker(venue, s.asset, int(data.get("u") or 0), float(data["b"]) / m, float(data["B"]) * m,
                          float(data["a"]) / m, float(data["A"]) * m, E)
    if kind.startswith("depth"):
        bids = data["bids"] if "bids" in data else data["b"]
        asks = data["asks"] if "asks" in data else data["a"]
        uid = data["lastUpdateId"] if "lastUpdateId" in data else data.get("u", 0)
        return Depth(venue, s.asset, int(uid), _levels(bids, m), _levels(asks, m), E)
    if kind == "aggTrade":
        return AggTrade(venue, s.asset, int(data["a"]), float(data["p"]) / m, float(data["q"]) * m, int(data["T"]),
                        bool(data["m"]), E)
    if kind.startswith("markPrice"):
        r, i = data.get("r"), data.get("i")
        return MarkPrice(s.asset, float(data["p"]) / m, float(i) / m if i not in (None, "") else math.nan,
                         float(r) if r not in (None, "") else 0.0, int(data.get("T") or 0), E)
    return None


# ---------------------------------------------------------------------------------------------------------------
# Bağlantı yöneticisi


async def ws_connect(url: str):
    """Gerçek websocket bağlantısı; websockets burada (geç) içe aktarılır."""
    import websockets  # noqa: PLC0415 — bağımlılık yalnızca canlı çalıştırmada gerekir
    return await websockets.connect(url, ping_interval=20, ping_timeout=60, close_timeout=5, open_timeout=20,
                                    max_size=2 ** 22, max_queue=4096)


class StreamManager:
    """Tek birleşik akış bağlantısı: bağlan → oku → ayrıştır → işleyiciye ver; kopunca yeniden bağlan."""

    def __init__(self, venue: str, url: str, table: SymbolTable, handler: Callable, on_status: Callable | None = None,
                 *, connect: Callable | None = None, sleep: Callable | None = None, clock: Callable = time.monotonic,
                 wall: Callable = time.time, rng: Callable = random.random, base_s: float = 1.0, max_s: float = 60.0,
                 jitter: float = 0.25, stale_s: float = 30.0, stream_stale_s: float = 120.0,
                 watch: tuple = ("@depth", "@markPrice"), max_age_s: float = 23.5 * 3600,
                 boundary_guard_s: float = 60.0, poll_s: float = 1.0):
        self.venue, self.url, self.table, self.handler, self.on_status = venue, url, table, handler, on_status
        self.connect = connect or ws_connect
        self.sleep = sleep
        self.clock, self.wall, self.rng = clock, wall, rng
        self.base_s, self.max_s, self.jitter = float(base_s), float(max_s), float(jitter)
        self.stale_s, self.stream_stale_s, self.watch = float(stale_s), float(stream_stale_s), tuple(watch)
        self.max_age_s, self.boundary_guard_s, self.poll_s = float(max_age_s), float(boundary_guard_s), float(poll_s)
        self.streams = url.split("streams=", 1)[1].split("/") if "streams=" in url else []
        self.stats = dict.fromkeys(("connects", "disconnects", "messages", "stale", "errors"), 0)
        self._got = False
        self._err_key, self._err_t, self._suppressed = None, -math.inf, 0

    def backoff(self, attempt: int) -> float:
        return min(self.max_s, self.base_s * 2 ** attempt) * (1.0 + self.jitter * self.rng())

    def near_boundary(self) -> bool:
        s = self.wall() % 900.0
        return s < self.boundary_guard_s or s > 900.0 - self.boundary_guard_s

    def _status(self, kind: str, detail: dict | None = None, tb: str | None = None) -> None:
        if self.on_status is not None:
            try:
                self.on_status(kind, {"venue": self.venue, **(detail or {})}, tb)
            except Exception:  # noqa: BLE001 — kayıt hatası akışı durdurmaz
                pass

    async def _pause(self, delay: float, stop: asyncio.Event) -> None:
        if delay <= 0 or stop.is_set():
            return
        if self.sleep is not None:
            await self.sleep(delay)
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except TimeoutError:
            pass

    async def run(self, stop: asyncio.Event) -> None:
        attempt = 0
        down_since: float | None = None
        while not stop.is_set():
            try:
                conn = await self.connect(self.url)
            except Exception as e:  # noqa: BLE001
                self.stats["errors"] += 1
                self._status("connect_error", {"attempt": attempt, "error": repr(e)[:300]}, traceback.format_exc(limit=6))
                if down_since is None:
                    down_since = self.wall()
                await self._pause(self.backoff(attempt), stop)
                attempt += 1
                continue
            self.stats["connects"] += 1
            t_up = self.wall()
            self._status("connect", {"attempt": attempt, "streams": len(self.streams)})
            if down_since is not None:
                self._status("gap", {"from_ms": int(down_since * 1000), "to_ms": int(t_up * 1000),
                                     "down_s": round(t_up - down_since, 3)})
            reason, tb = "error", None
            self._got = False
            try:
                reason = await self._consume(conn, stop)
            except Exception as e:  # noqa: BLE001
                reason, tb = f"error: {e!r}"[:300], traceback.format_exc(limit=8)
            finally:
                try:
                    await asyncio.wait_for(conn.close(), timeout=5)
                except Exception:  # noqa: BLE001
                    pass
            down_since = self.wall()
            self.stats["disconnects"] += 1
            self._status("disconnect", {"reason": reason, "up_s": round(down_since - t_up, 3)}, tb)
            if stop.is_set():
                break
            if self._got:
                attempt = 0
            if reason == "max_age":
                delay = 0.0
            else:
                delay = self.backoff(attempt)
                attempt += 1
            await self._pause(delay, stop)

    async def _consume(self, conn, stop: asyncio.Event) -> str:
        t0 = self.clock()
        last = last_check = t0
        seen: dict[str, float] = {}
        watched = [s for s in self.streams if any(w in s for w in self.watch)]
        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(conn.recv(), timeout=self.poll_s)
            except TimeoutError:
                raw = None
            now = self.clock()
            if raw is not None:
                last = now
                self._got = True
                self.stats["messages"] += 1
                self._dispatch(raw, seen, now)
            elif now - last >= self.stale_s:
                self.stats["stale"] += 1
                self._status("stale", {"silent_s": round(now - last, 3)})
                return "stale"
            if now - last_check >= self.poll_s:
                last_check = now
                bad = [s for s in watched if now - seen.get(s, t0) >= self.stream_stale_s]
                if bad:
                    self.stats["stale"] += 1
                    self._status("stale_stream", {"n": len(bad), "streams": bad[:10]})
                    return "stale_stream"
                if now - t0 >= self.max_age_s and not self.near_boundary():
                    self._status("max_age", {"age_s": round(now - t0, 1)})
                    return "max_age"
        return "stop"

    def _dispatch(self, raw, seen: dict, now: float) -> None:
        try:
            msg = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
            st = msg.get("stream")
            if st:
                seen[st] = now
            ev = parse_message(self.venue, msg, self.table)
            if ev is not None:
                self.handler(ev)
        except Exception as e:  # noqa: BLE001 — işleyici hatası bağlantıyı düşürmez
            self.stats["errors"] += 1
            key = repr(e)[:300]
            if key != self._err_key or now - self._err_t >= 60.0:
                self._status("handler_error", {"error": key, "suppressed": self._suppressed},
                             traceback.format_exc(limit=8))
                self._err_key, self._err_t, self._suppressed = key, now, 0
            else:
                self._suppressed += 1


# ---------------------------------------------------------------------------------------------------------------
# Saat ve herkese açık REST


def clock_offset_ms(fetch_server_ms: Callable[[], float], wall: Callable = time.time,
                    samples: int = 3) -> tuple[float, float]:
    """(sapma ms, gidiş-dönüş ms): sunucu − yerel; en kısa gidiş-dönüşlü örnek."""
    best: tuple[float, float] | None = None
    for _ in range(max(1, int(samples))):
        t0 = wall()
        s = float(fetch_server_ms())
        t1 = wall()
        rtt = (t1 - t0) * 1000.0
        off = s - (t0 + t1) * 500.0
        if best is None or rtt < best[1]:
            best = (off, rtt)
    assert best is not None
    return best


class PublicRest:
    """Yalnızca herkese açık piyasa verisi; `ALLOWED` dışı yol → ValueError. Anahtar, imza, hesap yok."""

    ALLOWED = frozenset({"/api/v3/klines", "/api/v3/time", "/fapi/v1/klines", "/fapi/v1/time",
                         "/fapi/v1/premiumIndex", "/fapi/v1/fundingRate"})
    LIMIT = {SPOT: 1000, FUT: 1500}

    def __init__(self, base: dict | None = None, session: requests.Session | None = None,
                 timeout: tuple = (10, 30), retries: int = 4, sleep: Callable = time.sleep):
        self.base = {**REST_BASE, **(base or {})}
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = "trend-research-paper/0.1"
        self.timeout, self.retries, self._sleep = timeout, int(retries), sleep

    def get(self, venue: str, path: str, params: dict | None = None):
        if path not in self.ALLOWED:
            raise ValueError(f"izinli olmayan REST yolu: {path} (yalnızca herkese açık piyasa verisi)")
        url = self.base[venue].rstrip("/") + path
        for attempt in range(self.retries + 1):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException:
                if attempt >= self.retries:
                    raise
                self._sleep(2 ** attempt)
                continue
            if r.status_code == 418:
                raise RuntimeError(f"418 IP yasağı: {r.text[:200]}")
            if r.status_code == 429 or r.status_code >= 500:
                if attempt >= self.retries:
                    r.raise_for_status()
                ra = r.headers.get("Retry-After", "")
                self._sleep(int(ra) if ra.isdigit() else 2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("erişilemez")

    def server_time_ms(self, venue: str = SPOT) -> int:
        return int(self.get(venue, "/api/v3/time" if venue == SPOT else "/fapi/v1/time")["serverTime"])

    def klines(self, venue: str, symbol: str, interval: str, start_ms: int, end_ms: int | None = None) -> list[list]:
        """[start_ms, end_ms] aralığında açılan mumlar (ham satırlar, sayfalı)."""
        path = "/api/v3/klines" if venue == SPOT else "/fapi/v1/klines"
        lim = self.LIMIT[venue]
        out: list[list] = []
        cur = int(start_ms)
        while True:
            p = {"symbol": symbol, "interval": interval, "limit": lim, "startTime": cur}
            if end_ms is not None:
                p["endTime"] = int(end_ms)
            rows = self.get(venue, path, p)
            out += rows
            if len(rows) < lim:
                return out
            cur = int(rows[-1][0]) + 1
            if end_ms is not None and cur > end_ms:
                return out

    def premium_index(self, symbol: str) -> dict:
        return self.get(FUT, "/fapi/v1/premiumIndex", {"symbol": symbol})

    def funding_rate(self, symbol: str, start_ms: int, end_ms: int) -> list[dict]:
        return self.get(FUT, "/fapi/v1/fundingRate", {"symbol": symbol, "startTime": int(start_ms),
                                                      "endTime": int(end_ms), "limit": 1000})


def rest_bars(rows: list[list], mult: float = 1.0, now_ms: int | None = None) -> list[tuple]:
    """REST klines → kapanmış mumlar [(open_ms, o, h, l, c)], spot biriminde (close_time ≥ now_ms olan atılır)."""
    out = []
    for r in rows:
        if now_ms is not None and int(r[6]) >= now_ms:
            continue
        out.append((int(r[0]), float(r[1]) / mult, float(r[2]) / mult, float(r[3]) / mult, float(r[4]) / mult))
    return out
