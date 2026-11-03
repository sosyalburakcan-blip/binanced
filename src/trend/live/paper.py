"""Canlı kâğıt işlem (gölge mod): v4 gün içi momentum + BTC-200 kıyası, yalnızca herkese açık Binance verisiyle.

    python -m uv run python -m trend.live.paper --config live_v4.yaml [--minutes N] [--db data/live/live.db]

KURAL: GERÇEK EMİR YOK. Hiçbir emir/hesap/kullanıcı verisi uç noktası çağrılmaz, API anahtarı ve `.env` okunmaz;
tüm "emirler" bellekte ve SQLite kaydında yaşayan kâğıt emirlerdir (stream.PublicRest yalnızca izinli yolları açar).

Yapılandırma (`live_v4.yaml`, proje kökü):
    capital_usdt: 1000
    leverage: [1, 2, 3]              # vadeli kâğıt hesaplar; spot her zaman 1×
    baseline: btc_200                # isteğe bağlı kıyas izi
    strategies:
      - {name: s1, lookback_h: 24, z_entry: 2.0, confirm_h: 3, tp: 0.04, sl: 0.02, max_hold_h: 24}
    run: {close_grace_s: 10}         # isteğe bağlı çalışma ayarları (RUN_DEFAULTS)
vol_window_h, n_top, slots ve maliyetler (spot/vadeli taker, maker, vergi, mmr, liq_fee) research_v4.yaml'dan okunur
(backtestle aynı); live_v4.yaml'da farklı vol_window_h/n_top/slots verilirse hata.

Hesaplar: her strateji için `{ad}/spot` (1×) ve her kaldıraç L için `{ad}/fut{L}x`; kıyas `btc_200/spot`. Hepsi
`capital_usdt` ile başlar.

Kurallar (sim.py modül notunun canlı karşılığı):
1. Evren: en son `universe/{YYYY-MM}.csv` (içinde bulunulan aydan yeni olmayan) için `study.eligibility` → bilinen
   coin listesi, çalışma boyunca sabit (daha yeni ay dosyası çıkarsa günde bir olay; yeniden başlatma gerekir).
   Sütun sırası alfabetik = backtestteki eşitlik kırımı. Kayma varsayımı aynı dosyanın `slippage` kolonu.
2. Isınma: REST 15 dk mumları (son `keep_h` saat; keep_h ≥ vol_window_h + en büyük lookback + en büyük confirm + 2)
   → ilk saat kapanışında sinyal hazır. Başlangıçtaki son tamamlanmış saatin sinyali `warmup` fazıyla kaydedilir,
   giriş yapılmaz. BTC-200 için REST 1d mumları. Vadeli fonlama durumu REST premiumIndex.
3. Saatlik karar: k saatinin son 15 dk mumu (HH:45, kapanış HH:59:59.999) kapanınca, piyasa başına: tüm varlıkların
   mumu geldiğinde ya da sınır B = k + 1 sa'ten `close_grace_s` sonra (eksikler REST'ten tamamlanır, yine yoksa NaN —
   backtestteki "bar yok"). Sinyal `sim.hourly_signals` ile kayan saatlik kapanış matrisinin (C_k = HH:45 mumunun
   kapanışı) son satırı; vadeli hesaplar vadeli kapanışlarla (spot biriminde). Her saat × piyasa × strateji × varlık
   için z/ok/top kaydedilir. Karar B'den `max_late_s` sonraya kalırsa sinyal `late` kaydedilir, giriş yapılmaz.
4. Aday = top ∧ ok ∧ elde değil; azalan z (eşitlikte sütun sırası), boş yuva kaldıkça. Yuva ve özsermaye backtestle
   aynı: B'den sonra (≥ B) kapanan pozisyonlar hâlâ açık sayılır; nakit B anındaki haliyle (≥ B çıkış ve fonlama
   akışları hariç), pozisyonlar k kapanışıyla değerlenir; özsermaye saat başına bir kez ölçülür. margin =
   özsermaye / slots, en fazla nakit / (1 + L·(taker + vergi)).
5. Giriş: kararın hemen ardından canlı defterin ASK tarafında notional = margin·L yürünerek (gerçek VWAP, kayma);
   derinlik yetmezse dolan kadar (margin = dolan / L). Ücret notional·(taker + vergi). Defter yok veya
   `book_stale_s`'den eski → giriş atlanır (olay).
6. Çıkışlar (canlı veri): TP = p_in(1 + tp) dinlenen limit satış: yalnızca bir aggTrade TP'nin KESİN ÜSTÜNDE
   basılınca (dokunmak yetmez), tam TP fiyatından, maker. SL = p_in(1 − sl) stop-market: aggTrade ≤ SL → o anki
   BID tarafında qty yürünür, taker. Süre: giriş saatinin başı + max_hold_h dolunca BID yürünerek piyasa satışı, taker.
   Likidasyon (vadeli, L > 1, izole marjin): işaret fiyatı ≤ p_in(1 − 1/L + mmr) → marjinin tamamı kaybedilir, ücret
   notional·(liq_fee + vergi). SL/süre dolumu likidasyon fiyatının altına düşerse likidasyon sayılır (sim.py gibi).
7. Fonlama: markPrice akışında `T` (sonraki fonlama) ilerleyince önceki T'de, T'den önceki son `r` ve işaret
   fiyatıyla nakit −= qty·mark·r (pozitif oranı uzunlar öder); giriş < T ≤ çıkış olan (arada kapanmış dahil) vadeli
   pozisyonlara. Son markPrice T'den 60 sn'den eskiyse `estimated` işaretlenir.
8. BTC-200: her gün 00:00 UTC'de, BTC spot günlük kapanışı (23:45 mumunun kapanışı) > son 200 günlük kapanışın
   ortalaması (strategy.signal.sma_on_valid) → tüm nakitle BTC (ASK yürünerek, spot taker), değilse elde ise satış
   (BID). Başlangıçta son tamamlanmış günün kararı defter gelir gelmez uygulanır.
9. Özsermaye: her 15 dk sınırında hesap başına nakit + Σ (margin + qty·(fiyat − p_in)) (son işlem fiyatı; yoksa
   orta fiyat; izole vadelide pozisyon değeri ≥ 0).
10. Sürdürme: aynı veritabanıyla yeniden başlatılınca hesaplar `positions` tablosundan kurulur (nakit = sermaye +
    Σ kapanan pnl − Σ açık (margin + giriş ücreti + fonlama)); parametreleri değişmiş hesap → hata (yeni --db).
    Kapalı geçen süre için açık pozisyonlar REST 15 dk mumlarıyla sim.py kurallarıyla taranır (aynı mumda önce
    likidasyon/SL; TP yüksek > TP; SL ve süre dolumu fiyat·(1 − varsayılan kayma)) ve REST fundingRate ile fonlama
    tahsil edilir; bu çıkışlar `offline` işaretlenir.

Varsayımlar:
- TP dolumu tek seferde tam miktar (kuyruk önceliği yok sayılır; "kesin üstünde" kuralı bunu temkinli karşılar).
- Kopma sırasında aggTrade görülmez: o aralıkta TP/SL tetiklenmez (kesinti olay olarak kaydedilir); süre durdurma
  zamanlayıcıyla, likidasyon işaret fiyatıyla sürer. Süre çıkışında taze defter yoksa `book_wait_s` beklenir, sonra
  eldeki (bayat) defterde yürünür (`stale_book`, defter yaşı kayıtlı); hiç defter yoksa son fiyat·(1 − varsayılan
  kayma) (`no_book`).
- Satışta derinlik yetmezse kalan adet dokunulan en kötü kademe fiyatından dolmuş sayılır (`shortfall`).
- Zaman damgaları sunucu saatine göre düzeltilmiş yerel saat (REST /api/v3/time, saatte bir).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from trend.config import ROOT, load_settings
from trend.config import path as cfg_path
from trend.intraday import study
from trend.intraday.sim import Costs, Params, hourly_signals
from trend.live.book import Books
from trend.live.recorder import DB_PATH, Recorder
from trend.live.stream import (FUT, INVENTORY, SPOT, AggTrade, BookTicker, Depth, Kline, MarkPrice, PublicRest,
                               StreamManager, SymbolTable, clock_offset_ms, rest_bars, stream_urls)
from trend.strategy.signal import sma_on_valid

H_MS = 3_600_000
BAR_MS = 900_000
DAY_MS = 86_400_000
_S = load_settings()
BTC = _S["universe"]["btc_asset"]
BENCH_SMA = int(_S["evaluation"]["benchmark_sma"])

RUN_DEFAULTS = {
    "db": str(DB_PATH.relative_to(ROOT)),
    "research": "research_v4.yaml",
    "warmup_h": 240,            # ısınma / kayan pencere (saat); gereken en az değerden küçükse o kullanılır
    "close_grace_s": 10.0,      # saat kapanışından sonra eksik mum beklemesi (sonra REST)
    "max_late_s": 300.0,        # karar bundan geç kalırsa giriş yok
    "book_stale_s": 10.0,       # girişte defter en fazla bu kadar eski olabilir
    "book_wait_s": 120.0,       # süre çıkışında taze defter beklemesi (kopma sonrası yeniden bağlanma payı)
    "stale_s": 30.0,            # bağlantıda hiç mesaj yoksa yeniden bağlan
    "stream_stale_s": 120.0,    # izlenen tek akış (depth, markPrice) susarsa yeniden bağlan
    "max_conn_age_h": 23.5,
    "backoff_base_s": 1.0,
    "backoff_max_s": 60.0,
    "flush_s": 5.0,
    "tick_s": 0.5,
    "clock_sync_min": 60,
    "universe_month": None,     # None = en son ay dosyası
    "spot_ws": None, "futures_ws": None, "spot_rest": None, "futures_rest": None,
    "spot_streams": None, "futures_streams": None,   # None = stream.KINDS (ör. bookTicker çıkarılabilir)
}


def _utc(ms) -> str:
    return pd.Timestamp(int(ms), unit="ms").strftime("%Y-%m-%d %H:%M:%S")


def _fin(x) -> bool:
    return x is not None and isinstance(x, (int, float, np.floating)) and math.isfinite(float(x))


# ---------------------------------------------------------------------------------------------------------------
# Yapılandırma


@dataclass(frozen=True)
class StrategyCfg:
    name: str
    lookback_h: int
    z_entry: float
    confirm_h: int
    tp: float
    sl: float
    max_hold_h: int


@dataclass
class LiveConfig:
    capital: float
    leverage: list[float]
    strategies: list[StrategyCfg]
    baseline: str | None
    vol_window_h: int
    n_top: int
    slots: int
    costs: dict
    slip_default: float
    run: dict = field(default_factory=lambda: dict(RUN_DEFAULTS))
    v4: dict | None = None

    def params(self, s: StrategyCfg, lev: float = 1.0) -> Params:
        return Params(lookback_h=s.lookback_h, z_entry=s.z_entry, confirm_h=s.confirm_h, tp=s.tp, sl=s.sl,
                      max_hold_h=s.max_hold_h, vol_window_h=self.vol_window_h, n_top=self.n_top, slots=self.slots,
                      leverage=float(lev))

    def keep_h(self) -> int:
        if not self.strategies:
            return int(self.run["warmup_h"])
        need = self.vol_window_h + max(s.lookback_h for s in self.strategies) + max(s.confirm_h for s in self.strategies) + 2
        return max(int(self.run["warmup_h"]), need)

    def account_specs(self) -> list[tuple]:
        out = []
        for s in self.strategies:
            out.append((f"{s.name}/spot", s, SPOT, 1.0))
            out += [(f"{s.name}/fut{lev:g}x", s, FUT, float(lev)) for lev in self.leverage]
        if self.baseline:
            out.append((f"{self.baseline}/spot", None, SPOT, 1.0))
        return out

    def to_json(self) -> dict:
        return {"capital_usdt": self.capital, "leverage": self.leverage, "baseline": self.baseline,
                "strategies": [s.__dict__ for s in self.strategies], "vol_window_h": self.vol_window_h,
                "n_top": self.n_top, "slots": self.slots, "slip_default": self.slip_default,
                "costs": {k: c.__dict__ for k, c in self.costs.items()}, "keep_h": self.keep_h(),
                "run": {k: v for k, v in self.run.items()}}


def load_config(path, research_path=None) -> LiveConfig:
    with open(path, encoding="utf-8") as f:
        y = yaml.safe_load(f) or {}
    run = {**RUN_DEFAULTS, **(y.get("run") or {})}
    rp = Path(research_path or run["research"])
    v4 = study.load_v4(rp if rp.is_absolute() else ROOT / rp)
    fixed = v4["fixed"]
    for k in ("vol_window_h", "n_top", "slots"):
        if k in y and int(y[k]) != int(fixed[k]):
            raise ValueError(f"{k}: live_v4.yaml {y[k]} ≠ research_v4.yaml {fixed[k]} (backtestle aynı olmalı)")
    strategies = []
    for s in y.get("strategies") or []:
        sc = StrategyCfg(name=str(s["name"]), lookback_h=int(s["lookback_h"]), z_entry=float(s["z_entry"]),
                         confirm_h=int(s["confirm_h"]), tp=float(s["tp"]), sl=float(s["sl"]),
                         max_hold_h=int(s["max_hold_h"]))
        if "/" in sc.name or not sc.name:
            raise ValueError(f"strateji adı boş olamaz ve '/' içeremez: {sc.name!r}")
        if min(sc.lookback_h, sc.confirm_h, sc.max_hold_h) < 1 or not (sc.tp > 0 and 0 < sc.sl <= 1):
            raise ValueError(f"geçersiz strateji parametresi: {sc}")
        strategies.append(sc)
    if len({s.name for s in strategies}) != len(strategies):
        raise ValueError("strateji adları benzersiz olmalı")
    baseline = y.get("baseline")
    if baseline not in (None, "btc_200"):
        raise ValueError(f"bilinmeyen kıyas: {baseline} (yalnızca btc_200)")
    lev = [float(x) for x in (y.get("leverage") or [])]
    if any(not x >= 1 for x in lev):
        raise ValueError("kaldıraç ≥ 1 olmalı")
    return LiveConfig(capital=float(y.get("capital_usdt", 1000.0)), leverage=lev, strategies=strategies,
                      baseline=baseline, vol_window_h=int(fixed["vol_window_h"]), n_top=int(fixed["n_top"]),
                      slots=int(fixed["slots"]),
                      costs={SPOT: study.costs_for(v4, "spot"), FUT: study.costs_for(v4, "futures")},
                      slip_default=float(v4["costs"]["slip_default"]), run=run, v4=v4)


def latest_universe(v4: dict, now: pd.Timestamp, month: str | None = None) -> tuple[str, list[str], dict]:
    """(ay, bilinen coin listesi, varlık → kayma kesri): içinde bulunulan aydan yeni olmayan en son ay dosyası."""
    root = cfg_path(_S, "universe")
    if month is None:
        ts = pd.Timestamp(now)
        cur = (ts.tz_convert("UTC").tz_localize(None) if ts.tzinfo is not None else ts).to_period("M")
        months = sorted(pd.Period(p.stem, "M") for p in root.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].csv"))
        months = [m for m in months if m <= cur]
        if not months:
            raise SystemExit(f"{root} altında evren dosyası yok")
        m = months[-1]
    else:
        m = pd.Period(month, "M")
    elig, assets, slip = study.eligibility(v4, pd.date_range(m.start_time, periods=1, freq="h"))
    sel = [j for j in range(len(assets)) if elig[0, j]]
    return str(m), sorted(assets[j] for j in sel), {assets[j]: float(slip[0, j]) for j in sel}


# ---------------------------------------------------------------------------------------------------------------
# Mumlar ve sinyal


class Bars:
    """Kapanmış 15 dk mumlar: (piyasa, varlık) → {open_ms: (o, h, l, c)}, spot biriminde."""

    def __init__(self):
        self.d: dict[tuple[str, str], dict[int, tuple]] = defaultdict(dict)
        self._last: dict[tuple[str, str], int] = {}

    def add(self, venue: str, asset: str, open_ms: int, o: float, h: float, l: float, c: float) -> bool:  # noqa: E741
        key = (venue, asset)
        d = self.d[key]
        new = open_ms not in d
        d[int(open_ms)] = (float(o), float(h), float(l), float(c))
        if open_ms > self._last.get(key, -1):
            self._last[key] = int(open_ms)
        return new

    def get(self, venue: str, asset: str, open_ms: int):
        d = self.d.get((venue, asset))
        return d.get(int(open_ms)) if d else None

    def last_open(self, venue: str, asset: str) -> int | None:
        return self._last.get((venue, asset))

    def series(self, venue: str, asset: str, start_ms: int, end_ms: int) -> list[tuple]:
        d = self.d.get((venue, asset)) or {}
        return [(t, *d[t]) for t in sorted(d) if start_ms <= t <= end_ms]

    def prune(self, before_ms: int) -> None:
        for d in self.d.values():
            for t in [t for t in d if t < before_ms]:
                del d[t]


def _valid_bar(b) -> bool:
    """sim._present ile aynı: o/h/l/c sonlu, açılış ve kapanış > 0."""
    o, h, l, c = b  # noqa: E741
    return all(math.isfinite(x) for x in b) and o > 0 and c > 0


def hourly_matrix(bars: Bars, venue: str, assets: list[str], hours_ms) -> np.ndarray:
    """(saat × varlık) C_k = k saatinin HH:45 mumunun kapanışı (yoksa NaN) — sim.hourly_close tanımı."""
    C = np.full((len(hours_ms), len(assets)), np.nan)
    for j, a in enumerate(assets):
        d = bars.d.get((venue, a))
        if not d:
            continue
        for i, h in enumerate(hours_ms):
            b = d.get(int(h) + 3 * BAR_MS)
            if b is not None and _valid_bar(b):
                C[i, j] = b[3]
    return C


class SignalEngine:
    """Saatlik sinyal: kayan kapanış matrisinde sim.hourly_signals, son satır."""

    def __init__(self, cfg: LiveConfig, assets: list[str]):
        self.cfg, self.assets = cfg, list(assets)
        self.keep_h = cfg.keep_h()
        self.params = {s.name: cfg.params(s) for s in cfg.strategies}

    def compute(self, bars: Bars, venue: str, hour_ms: int) -> dict:
        hours = int(hour_ms) - H_MS * np.arange(self.keep_h - 1, -1, -1, dtype=np.int64)
        C = hourly_matrix(bars, venue, self.assets, hours)
        elig = np.ones(C.shape, dtype=bool)          # sütunlar = bilinen coin listesi
        out = {"hour_ms": int(hour_ms), "venue": venue, "closes": C[-1].copy(), "z": {}, "ok": {}, "top": {}}
        for name, p in self.params.items():
            z, ok, top = hourly_signals(C, elig, p)
            out["z"][name], out["ok"][name], out["top"][name] = z[-1].copy(), ok[-1].copy(), top[-1].copy()
        return out


# ---------------------------------------------------------------------------------------------------------------
# Kâğıt aracı


class IdGen:
    def __init__(self, prefix: str | None = None):
        if prefix is None:
            n, s = int(time.time() * 1000), ""
            while n:
                n, r = divmod(n, 36)
                s = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + s
            prefix = s
        self.prefix, self.n = prefix, 0

    def next(self, kind: str) -> str:
        self.n += 1
        return f"{kind}-{self.prefix}-{self.n}"


@dataclass
class Position:
    pos_id: str
    account: str
    strategy: str
    venue: str
    lev: float
    asset: str
    hour_ms: int                   # karar sınırı B (giriş saatinin başı)
    entry_ms: int
    p_in: float
    qty: float
    margin: float
    notional: float
    fee_in: float
    tp_px: float = math.inf
    sl_px: float = -math.inf
    liq_px: float = -math.inf
    deadline_ms: int | None = None
    z: float = math.nan
    funding: float = 0.0
    status: str = "open"
    exit_ms: int | None = None
    p_out: float | None = None
    reason: str | None = None
    fee_out: float = 0.0
    exit_flow: float = 0.0
    pnl: float | None = None
    flags: str = ""
    tp_order: str | None = None
    sl_order: str | None = None
    funded: set = field(default_factory=set)

    def value(self, px: float) -> float:
        v = self.margin + self.qty * (px - self.p_in)
        return max(0.0, v) if self.lev > 1 else v

    def row(self, now_ms: int) -> dict:
        return dict(pos_id=self.pos_id, account=self.account, strategy=self.strategy, venue=self.venue,
                    leverage=self.lev, asset=self.asset, hour_ms=self.hour_ms, entry_ms=self.entry_ms, p_in=self.p_in,
                    qty=self.qty, margin=self.margin, notional=self.notional, fee_in=self.fee_in, tp_px=self.tp_px,
                    sl_px=self.sl_px, liq_px=self.liq_px, deadline_ms=self.deadline_ms, z=self.z, status=self.status,
                    exit_ms=self.exit_ms, p_out=self.p_out, reason=self.reason, fee_out=self.fee_out,
                    funding=self.funding, exit_flow=self.exit_flow, pnl=self.pnl, flags=self.flags, updated_ms=now_ms)

    @classmethod
    def from_row(cls, r: dict) -> Position:
        def f(k, d):
            return float(r[k]) if r.get(k) is not None else d
        return cls(pos_id=r["pos_id"], account=r["account"], strategy=r["strategy"], venue=r["venue"],
                   lev=float(r["leverage"]), asset=r["asset"], hour_ms=int(r["hour_ms"]), entry_ms=int(r["entry_ms"]),
                   p_in=float(r["p_in"]), qty=float(r["qty"]), margin=float(r["margin"]), notional=float(r["notional"]),
                   fee_in=float(r["fee_in"]), tp_px=f("tp_px", math.inf), sl_px=f("sl_px", -math.inf),
                   liq_px=f("liq_px", -math.inf),
                   deadline_ms=int(r["deadline_ms"]) if r.get("deadline_ms") is not None else None,
                   z=f("z", math.nan), funding=f("funding", 0.0), flags=r.get("flags") or "")


@dataclass
class Account:
    acc_id: str
    strategy: StrategyCfg | None
    venue: str
    lev: float
    costs: Costs
    slots: int
    capital: float
    cash: float
    positions: dict = field(default_factory=dict)      # varlık → açık Position
    recent: list = field(default_factory=list)         # son bir günde kapananlar (fonlama, yuva kuralı)
    ledger: list = field(default_factory=list)         # (olay zamanı ms, nakit akışı): çıkışlar ve fonlama
    n_trades: int = 0

    @property
    def name(self) -> str:
        return self.strategy.name if self.strategy is not None else self.acc_id.split("/")[0]


def _join(*flags) -> str:
    return ",".join(f for f in flags if f)


class PaperBroker:
    """Kâğıt hesaplar, girişler (ASK yürüyüşü), çıkışlar (TP/SL/süre/likidasyon), fonlama ve kayıt."""

    def __init__(self, cfg: LiveConfig, books: Books, rec: Recorder, assumed_slip: dict, ids: IdGen | None = None,
                 price_fn=None, log=None):
        self.cfg, self.books, self.rec = cfg, books, rec
        self.slip = dict(assumed_slip)
        self.ids = ids or IdGen()
        self.price_fn = price_fn or (lambda venue, asset: math.nan)
        self.log = log or (lambda msg: None)
        self.accounts: dict[str, Account] = {}
        for acc_id, s, venue, lev in cfg.account_specs():
            self.accounts[acc_id] = Account(acc_id, s, venue, lev, cfg.costs[venue], cfg.slots, cfg.capital,
                                            cfg.capital)
        self._by_venue = {v: [a for a in self.accounts.values() if a.venue == v] for v in (SPOT, FUT)}
        self.orders: dict[str, dict] = {}
        self.book_stale_ms = int(float(cfg.run["book_stale_s"]) * 1000)
        self.book_wait_ms = int(float(cfg.run["book_wait_s"]) * 1000)
        self.stats: dict[str, int] = defaultdict(int)

    # --- yardımcılar ---
    def assumed(self, asset: str) -> float:
        s = self.slip.get(asset)
        return float(s) if _fin(s) else float(self.cfg.slip_default)

    def fresh_book(self, venue: str, asset: str, now_ms: int):
        b = self.books.get(venue, asset)
        return b if b is not None and not b.empty() and now_ms - b.ts_ms <= self.book_stale_ms else None

    def px(self, venue: str, pos: Position) -> float:
        p = self.price_fn(venue, pos.asset)
        return float(p) if _fin(p) and p > 0 else pos.p_in

    def account_params(self, acc: Account) -> dict:
        return json.loads(json.dumps({"strategy": acc.strategy.__dict__ if acc.strategy else acc.name,
                                      "venue": acc.venue, "leverage": acc.lev, "capital": acc.capital,
                                      "slots": acc.slots, "costs": acc.costs.__dict__,
                                      "vol_window_h": self.cfg.vol_window_h, "n_top": self.cfg.n_top}))

    def _order(self, oid, ts, acc, pos, side, typ, qty, notional, price, reason, status, detail=None) -> None:
        row = dict(order_id=oid, ts_ms=ts, account=acc.acc_id, strategy=acc.name, venue=acc.venue, leverage=acc.lev,
                   asset=pos.asset, side=side, type=typ, qty=qty, notional=notional, price=price, reason=reason,
                   status=status, pos_id=pos.pos_id, updated_ms=ts, detail=detail)
        if status == "open":
            self.orders[oid] = row
        self.rec.add("paper_orders", **row)

    def _order_done(self, oid, status, ts, detail=None) -> None:
        row = self.orders.pop(oid, None) if oid else None
        if row is not None:
            row.update(status=status, updated_ms=ts)
            if detail is not None:
                row["detail"] = detail
            self.rec.add("paper_orders", **row)

    def _fill(self, oid, ts, acc, pos, side, reason, liquidity, qty, notional, vwap, w, fee, rate, book,
              trigger=None, assumed_bps=None, flags="") -> None:
        mid = w.mid if w is not None else (book.mid if book is not None else math.nan)
        if _fin(mid) and mid > 0 and _fin(vwap):            # Walk.slippage_bps ile aynı tanım (eksik dolum dahil)
            slip = (vwap / mid - 1.0) * 1e4 if side == "buy" else (1.0 - vwap / mid) * 1e4
        else:
            slip = math.nan
        diff = slip - assumed_bps if _fin(slip) and _fin(assumed_bps) else None
        vs_trig = (1.0 - vwap / trigger) * 1e4 if _fin(trigger) and trigger > 0 and _fin(vwap) else None
        self.rec.add("fills", fill_id=self.ids.next("f"), order_id=oid, pos_id=pos.pos_id, ts_ms=ts,
                     account=acc.acc_id, strategy=acc.name, venue=acc.venue, leverage=acc.lev, asset=pos.asset,
                     side=side, reason=reason, liquidity=liquidity, qty=qty, notional=notional, vwap=vwap, mid=mid,
                     slippage_bps=slip, levels_used=w.levels_used if w is not None else 0,
                     shortfall_qty=w.shortfall_qty if w is not None else None, assumed_slip_bps=assumed_bps,
                     slip_diff_bps=diff, trigger_price=trigger, slip_vs_trigger_bps=vs_trig, fee=fee, fee_rate=rate,
                     book_age_ms=ts - book.ts_ms if book is not None else None,
                     book_json=book.snapshot() if book is not None else None, flags=flags)

    def _skip(self, acc, asset, ts, why, z) -> None:
        self.stats[f"skip_{why}"] += 1
        self.rec.event(ts, "entry_skip", acc.venue, {"account": acc.acc_id, "asset": asset, "why": why, "z": z})

    # --- giriş ---
    def decide(self, sig: dict, assets: list[str], now_ms: int, enter: bool = True) -> list[Position]:
        """Kural 4–5: tek piyasanın saatlik sinyaliyle o piyasadaki strateji hesaplarına girişler."""
        venue = sig["venue"]
        B = int(sig["hour_ms"]) + H_MS
        col = {a: j for j, a in enumerate(assets)}
        opened = []
        for acc in self._by_venue[venue]:
            if acc.strategy is None:
                continue
            name = acc.strategy.name
            z, ok, top = sig["z"][name], sig["ok"][name], sig["top"][name]
            sel = top & ok
            if not enter or not sel.any():
                continue
            cand = [int(j) for j in np.argsort(np.where(sel, -z, np.inf), kind="stable") if sel[j]]
            occ = list(acc.positions.values()) + [p for p in acc.recent if p.exit_ms is not None and p.exit_ms >= B]
            held = {p.asset for p in occ}
            free = acc.slots - len(occ)
            adj = sum(a for t, a in acc.ledger if t >= B)       # B ve sonrası akışlar: backtestte henüz nakitte değil
            eq = None
            for j in cand:
                a = assets[j]
                if a in held:
                    continue
                if free <= 0:
                    self._skip(acc, a, now_ms, "no_slot", float(z[j]))
                    continue
                if self.fresh_book(venue, a, now_ms) is None:
                    self._skip(acc, a, now_ms, "no_book", float(z[j]))
                    continue
                cash_b = acc.cash - adj
                if eq is None:
                    eq = cash_b + sum(p.value(self._close_px(sig, col, p)) for p in occ)
                m = eq / acc.slots
                cap = cash_b / (1.0 + acc.lev * (acc.costs.taker + acc.costs.tax_per_side))
                capped = m > cap
                if capped:
                    m = cap
                if not m > 0:
                    self._skip(acc, a, now_ms, "no_cash", float(z[j]))
                    continue
                pos = self.open(acc, a, m, B, now_ms, z=float(z[j]), flags="margin_capped" if capped else "")
                if pos is not None:
                    opened.append(pos)
                    held.add(a)
                    free -= 1
        return opened

    def _close_px(self, sig: dict, col: dict, p: Position) -> float:
        c = sig["closes"][col[p.asset]] if p.asset in col else math.nan
        return float(c) if _fin(c) else self.px(sig["venue"], p)

    def open(self, acc: Account, asset: str, margin: float, B: int, now_ms: int, z: float = math.nan,
             flags: str = "", reason: str = "entry") -> Position | None:
        book = self.books.get(acc.venue, asset)
        if book is None or book.empty():
            self._skip(acc, asset, now_ms, "no_book", z)
            return None
        w = book.walk("buy", margin * acc.lev)
        if not w.filled_qty > 0:
            self._skip(acc, asset, now_ms, "empty_book", z)
            return None
        N, q, p_in = w.filled_notional, w.filled_qty, w.vwap
        m = N / acc.lev
        rate = acc.costs.taker + acc.costs.tax_per_side
        fee = N * rate
        acc.cash -= m + fee
        s = acc.strategy
        pos = Position(pos_id=self.ids.next("p"), account=acc.acc_id, strategy=acc.name, venue=acc.venue,
                       lev=acc.lev, asset=asset, hour_ms=int(B), entry_ms=int(now_ms), p_in=p_in, qty=q, margin=m,
                       notional=N, fee_in=fee, z=z, flags=_join(flags, "shortfall" if w.shortfall_notional > 0 else ""))
        if s is not None:
            pos.tp_px, pos.sl_px = p_in * (1.0 + s.tp), p_in * (1.0 - s.sl)
            pos.deadline_ms = int(B) + s.max_hold_h * H_MS
        if acc.lev > 1:
            pos.liq_px = p_in * (1.0 - 1.0 / acc.lev + acc.costs.mmr)
        acc.positions[asset] = pos
        oid = self.ids.next("o")
        self._order(oid, now_ms, acc, pos, "buy", "market", q, N, None, reason, "filled",
                    {"requested_notional": margin * acc.lev})
        self._fill(oid, now_ms, acc, pos, "buy", reason, "taker", q, N, p_in, w, fee, rate, book,
                   assumed_bps=self.assumed(asset) * 1e4, flags=pos.flags)
        if s is not None:
            pos.tp_order, pos.sl_order = self.ids.next("o"), self.ids.next("o")
            self._order(pos.tp_order, now_ms, acc, pos, "sell", "limit", q, None, pos.tp_px, "tp", "open")
            self._order(pos.sl_order, now_ms, acc, pos, "sell", "stop_market", q, None, pos.sl_px, "sl", "open")
        self.rec.add("positions", **pos.row(now_ms))
        self.stats["entries"] += 1
        self.log(f"GİRİŞ {acc.acc_id} {asset} p_in={p_in:.6g} notional={N:.2f} kayma={w.slippage_bps:.1f}bps")
        return pos

    # --- çıkışlar ---
    def on_trade(self, venue: str, asset: str, price: float, ts_ms: int) -> None:
        for acc in self._by_venue[venue]:
            pos = acc.positions.get(asset)
            if pos is None:
                continue
            if price <= pos.sl_px:
                self.exit_market(acc, pos, ts_ms, "sl", trigger=pos.sl_px, detail={"trade_px": price})
            elif price > pos.tp_px:
                self.exit_tp(acc, pos, ts_ms, price)

    def on_mark(self, asset: str, mark: float, ts_ms: int) -> None:
        for acc in self._by_venue[FUT]:
            pos = acc.positions.get(asset)
            if pos is not None and acc.lev > 1 and mark <= pos.liq_px:
                self.liquidate(acc, pos, ts_ms, mark)

    def on_timer(self, now_ms: int) -> None:
        for acc in self.accounts.values():
            for pos in list(acc.positions.values()):
                if pos.deadline_ms is None or now_ms < pos.deadline_ms:
                    continue
                if self.fresh_book(acc.venue, pos.asset, now_ms) is None and now_ms - pos.deadline_ms < self.book_wait_ms:
                    continue                               # taze defter beklenir
                self.exit_market(acc, pos, now_ms, "time")
            if acc.recent and acc.recent[0].exit_ms < now_ms - DAY_MS:
                acc.recent = [p for p in acc.recent if p.exit_ms >= now_ms - DAY_MS]
            if acc.ledger and acc.ledger[0][0] < now_ms - DAY_MS:
                acc.ledger = [x for x in acc.ledger if x[0] >= now_ms - DAY_MS]

    def exit_market(self, acc: Account, pos: Position, ts_ms: int, reason: str, trigger: float | None = None,
                    detail: dict | None = None) -> None:
        """Piyasa satışı (SL tetiklendi, süre doldu veya kıyas kararı): BID tarafında qty yürünür, taker."""
        book = self.books.get(acc.venue, pos.asset)
        flags = ""
        w = book.walk_qty("sell", pos.qty) if book is not None and not book.empty() else None
        if w is not None and w.filled_qty > 0:
            notional = w.filled_notional + (w.shortfall_qty * w.worst if w.shortfall_qty > 0 else 0.0)
            p_out = notional / pos.qty
            if w.shortfall_qty > 0:
                flags = "shortfall"
            if ts_ms - book.ts_ms > self.book_stale_ms:
                flags = _join(flags, "stale_book")
        else:
            ref = trigger if _fin(trigger) else self.px(acc.venue, pos)
            p_out = ref * (1.0 - self.assumed(pos.asset))
            notional = pos.qty * p_out
            flags, w = "no_book", None
        if acc.lev > 1 and p_out <= pos.liq_px:
            self.liquidate(acc, pos, ts_ms, p_out, flags=_join(flags, f"{reason}_below_liq"))
            return
        rate = acc.costs.taker + acc.costs.tax_per_side
        fee = notional * rate
        flow = pos.margin + pos.qty * (p_out - pos.p_in) - fee
        oid = self._exit_order(acc, pos, ts_ms, reason, "market", notional, None)
        self._close(acc, pos, ts_ms, p_out, reason, fee, flow, flags, filled=oid, detail=detail)
        self._fill(oid, ts_ms, acc, pos, "sell", reason, "taker", pos.qty, notional, p_out, w, fee, rate, book,
                   trigger=trigger, assumed_bps=self.assumed(pos.asset) * 1e4, flags=flags)

    def _exit_order(self, acc, pos, ts_ms, reason, typ, notional, price) -> str:
        """Dinlenen TP/SL emri varsa onun kimliği; yoksa yeni (dolmuş) çıkış emri."""
        oid = {"tp": pos.tp_order, "sl": pos.sl_order}.get(reason)
        if oid is None:
            oid = self.ids.next("o")
            self._order(oid, ts_ms, acc, pos, "sell", typ, pos.qty, notional, price, reason, "filled")
        return oid

    def exit_tp(self, acc: Account, pos: Position, ts_ms: int, trade_px: float) -> None:
        """Dinlenen limit satış: tam TP fiyatından, maker (kayma varsayımı 0, backtestteki gibi)."""
        book = self.books.get(acc.venue, pos.asset)
        p_out = pos.tp_px
        rate = acc.costs.maker + acc.costs.tax_per_side
        fee = pos.qty * p_out * rate
        flow = pos.margin + pos.qty * (p_out - pos.p_in) - fee
        oid = self._exit_order(acc, pos, ts_ms, "tp", "limit", pos.qty * p_out, p_out)
        self._close(acc, pos, ts_ms, p_out, "tp", fee, flow, "", filled=oid, detail={"trade_px": trade_px})
        self._fill(oid, ts_ms, acc, pos, "sell", "tp", "maker", pos.qty, pos.qty * p_out, p_out, None, fee,
                   rate, book, trigger=None, assumed_bps=0.0)

    def liquidate(self, acc: Account, pos: Position, ts_ms: int, mark: float, flags: str = "") -> None:
        """İzole marjin: marjinin tamamı kaybedilir; ücret notional·(liq_fee + vergi)."""
        rate = acc.costs.liq_fee + acc.costs.tax_per_side
        fee = pos.notional * rate
        oid = self.ids.next("o")
        self._order(oid, ts_ms, acc, pos, "sell", "liquidation", pos.qty, pos.qty * mark, mark, "liq", "filled")
        self._close(acc, pos, ts_ms, float(mark), "liq", fee, -fee, flags)
        self._fill(oid, ts_ms, acc, pos, "sell", "liq", "liquidation", pos.qty, pos.qty * mark, float(mark), None,
                   fee, rate, None, trigger=pos.liq_px, assumed_bps=None, flags=flags)

    def close_offline(self, acc: Account, pos: Position, ts_ms: int, p_out: float, reason: str) -> None:
        """Kapalıyken geçen sürede mumlarla bulunan çıkış (Kural 10)."""
        if reason == "liq":
            rate = acc.costs.liq_fee + acc.costs.tax_per_side
            fee, flow = pos.notional * rate, -pos.notional * rate
        else:
            rate = (acc.costs.maker if reason == "tp" else acc.costs.taker) + acc.costs.tax_per_side
            fee = pos.qty * p_out * rate
            flow = pos.margin + pos.qty * (p_out - pos.p_in) - fee
        oid = self._exit_order(acc, pos, ts_ms, reason, "offline", pos.qty * p_out, p_out)
        self._close(acc, pos, ts_ms, p_out, reason, fee, flow, "offline", filled=oid)
        self._fill(oid, ts_ms, acc, pos, "sell", reason, "offline", pos.qty, pos.qty * p_out, p_out, None, fee, rate,
                   None, assumed_bps=None, flags="offline")

    def _close(self, acc, pos, ts_ms, p_out, reason, fee, flow, flags, filled=None, detail=None) -> None:
        pos.status, pos.exit_ms, pos.p_out, pos.reason = "closed", int(ts_ms), float(p_out), reason
        pos.fee_out, pos.exit_flow = float(fee), float(flow)
        pos.pnl = pos.exit_flow - pos.margin - pos.fee_in - pos.funding
        pos.flags = _join(pos.flags, flags)
        acc.cash += flow
        acc.ledger.append((int(ts_ms), float(flow)))
        acc.positions.pop(pos.asset, None)
        acc.recent.append(pos)
        acc.n_trades += 1
        for oid in (pos.tp_order, pos.sl_order):
            if oid:
                self._order_done(oid, "filled" if oid == filled else "canceled", ts_ms,
                                 detail if oid == filled else None)
        self.rec.add("positions", **pos.row(ts_ms))
        self.stats[f"exit_{reason}"] += 1
        self.log(f"ÇIKIŞ {acc.acc_id} {pos.asset} {reason} p_out={p_out:.6g} pnl={pos.pnl:+.2f}")

    # --- fonlama ---
    def on_funding(self, asset: str, funding_ms: int, rate: float, mark: float, ts_ms: int,
                   estimated: bool = False) -> float:
        """Kural 7: giriş < T ≤ çıkış olan vadeli pozisyonlara qty·mark·rate."""
        total = 0.0
        if not (_fin(rate) and _fin(mark)):
            return total
        T = int(funding_ms)
        for acc in self._by_venue[FUT]:
            ps = [p for p in acc.positions.values() if p.asset == asset and p.entry_ms < T]
            ps += [p for p in acc.recent if p.asset == asset and p.entry_ms < T <= (p.exit_ms or 0)]
            for p in ps:
                if T in p.funded:
                    continue
                amt = p.qty * float(mark) * float(rate)
                p.funded.add(T)
                p.funding += amt
                if p.status == "closed" and p.pnl is not None:
                    p.pnl -= amt
                acc.cash -= amt
                acc.ledger.append((T, -amt))
                total += amt
                self.rec.add("funding", funding_ms=T, pos_id=p.pos_id, ts_ms=ts_ms, account=acc.acc_id, asset=asset,
                             qty=p.qty, mark=mark, rate=rate, amount=amt, estimated=bool(estimated))
                self.rec.add("positions", **p.row(ts_ms))
        return total

    # --- özsermaye ---
    def equity(self, acc: Account) -> tuple[float, float, float, int]:
        pv = sum(p.value(self.px(acc.venue, p)) for p in acc.positions.values())
        return acc.cash, pv, acc.cash + pv, len(acc.positions)

    def snapshot(self, ts_ms: int) -> None:
        for acc in self.accounts.values():
            cash, pv, eq, n = self.equity(acc)
            self.rec.add("equity", ts_ms=int(ts_ms), account=acc.acc_id, strategy=acc.name, venue=acc.venue,
                         leverage=acc.lev, cash=cash, pos_value=pv, equity=eq, n_open=n)

    # --- sürdürme ---
    def restore(self, now_ms: int) -> list[Position]:
        """Kural 10: hesap tanımları ve açık pozisyonlar veritabanından."""
        known = {r["account"]: r for r in self.rec.rows("SELECT * FROM accounts")}
        restored = []
        for acc in self.accounts.values():
            params = self.account_params(acc)
            r = known.get(acc.acc_id)
            if r is None:
                self.rec.add("accounts", account=acc.acc_id, strategy=acc.name, venue=acc.venue, leverage=acc.lev,
                             capital=acc.capital, params=params, created_ms=now_ms)
                continue
            if json.loads(r["params"]) != params:
                raise SystemExit(f"{acc.acc_id}: veritabanındaki parametreler yapılandırmadan farklı — yeni bir --db "
                                 "kullanın veya strateji adını değiştirin")
            cash, n = acc.capital, 0
            for p in self.rec.rows("SELECT * FROM positions WHERE account = ? ORDER BY entry_ms", (acc.acc_id,)):
                if p["status"] == "closed":
                    cash += float(p["pnl"] or 0.0)
                    n += 1
                    continue
                pos = Position.from_row(p)
                cash -= pos.margin + pos.fee_in + pos.funding
                pos.funded = {int(x["funding_ms"]) for x in
                              self.rec.rows("SELECT funding_ms FROM funding WHERE pos_id = ?", (pos.pos_id,))}
                for o in self.rec.rows("SELECT * FROM paper_orders WHERE pos_id = ? AND status = 'open'", (pos.pos_id,)):
                    self.orders[o["order_id"]] = o
                    if o["reason"] == "tp":
                        pos.tp_order = o["order_id"]
                    elif o["reason"] == "sl":
                        pos.sl_order = o["order_id"]
                acc.positions[pos.asset] = pos
                restored.append(pos)
            acc.cash, acc.n_trades = cash, n
        return restored


def offline_exit(pos: Position, bars: list[tuple], slip: float):
    """Kural 10: (zaman, p_out, neden) veya None — mumlar sırayla, sim.py tarama düzeni (TP yüksek > TP)."""
    for t, o, h, l, c in bars:  # noqa: E741
        if pos.deadline_ms is not None and t >= pos.deadline_ms:
            if o <= pos.liq_px:
                return t, o, "liq"
            if o <= pos.sl_px:
                return t, o * (1.0 - slip), "sl"
            if o > pos.tp_px:
                return t, pos.tp_px, "tp"
            return t, o * (1.0 - slip), "time"
        if l <= max(pos.sl_px, pos.liq_px):
            if pos.liq_px >= pos.sl_px or o <= pos.liq_px:
                return t, min(o, pos.liq_px), "liq"
            return t, min(o, pos.sl_px) * (1.0 - slip), "sl"
        if h > pos.tp_px:
            return t, pos.tp_px, "tp"
    return None


class Btc200:
    """Kural 8: BTC kapanışı > SMA200 → %100 BTC, aksi halde nakit; günlük karar 00:00 UTC."""

    def __init__(self, broker: PaperBroker, acc_id: str, asset: str = BTC, window: int = BENCH_SMA):
        self.broker, self.acc_id, self.asset, self.window = broker, acc_id, asset, int(window)
        self.closes: dict[int, float] = {}        # gün başı ms → günlük kapanış

    def signal(self, day_ms: int) -> tuple[int | None, float, float]:
        if day_ms not in self.closes:
            return None, math.nan, math.nan
        days = sorted(d for d in self.closes if d <= day_ms)
        s = pd.Series([self.closes[d] for d in days], index=pd.to_datetime(days, unit="ms"))
        sma = float(sma_on_valid(s, self.window).iloc[-1])
        c = float(self.closes[day_ms])
        return (int(c > sma) if math.isfinite(sma) else None), c, sma

    def apply(self, day_ms: int, now_ms: int) -> int | None:
        sig, c, sma = self.signal(day_ms)
        acc = self.broker.accounts[self.acc_id]
        pos = acc.positions.get(self.asset)
        act = "hold"
        if sig == 1 and pos is None:
            rate = acc.costs.taker + acc.costs.tax_per_side
            if self.broker.open(acc, self.asset, acc.cash / (1.0 + rate), now_ms, now_ms, reason="baseline"):
                act = "buy"
        elif sig == 0 and pos is not None:
            self.broker.exit_market(acc, pos, now_ms, "baseline")
            act = "sell"
        self.broker.rec.event(now_ms, "baseline", SPOT, {"day": _utc(day_ms)[:10], "signal": sig, "close": c,
                                                          "sma": sma, "action": act})
        return sig


# ---------------------------------------------------------------------------------------------------------------
# Çalıştırıcı


class LiveRunner:
    """Akışlar → defter/mumlar → saatlik sinyal → kâğıt aracı; zamanlayıcı, ısınma, kayıt."""

    def __init__(self, cfg: LiveConfig, *, assets: list[str] | None = None, slip: dict | None = None,
                 month: str | None = None, symbols: SymbolTable | None = None, rest=None, rec: Recorder | None = None,
                 connect=None, now_fn=None, verbose: bool = True):
        self.cfg = cfg
        run = cfg.run
        if assets is None:
            month, assets, slip = latest_universe(cfg.v4, pd.Timestamp.now(tz="UTC"), run.get("universe_month"))
        self.month = month
        self.assets = sorted(assets)
        self.slip = dict(slip or {})
        need = set(self.assets) | ({BTC} if cfg.baseline else set())
        self.symbols = symbols or SymbolTable.from_inventory(INVENTORY, need)
        self.rest = rest or PublicRest(base={k: v for k, v in ((SPOT, run.get("spot_rest")),
                                                              (FUT, run.get("futures_rest"))) if v})
        if rec is None:
            p = Path(run["db"])
            rec = Recorder(p if p.is_absolute() else ROOT / p)
        self.rec = rec
        self.connect = connect
        self._now_fn = now_fn
        self.verbose = verbose
        self.offset_ms = 0.0
        self.books, self.bars = Books(), Bars()
        self.last_px: dict[tuple[str, str], float] = {}
        self.tickers: dict[tuple[str, str], BookTicker] = {}
        self.broker = PaperBroker(cfg, self.books, rec, self.slip, price_fn=self.price, log=self.log)
        self.engine = SignalEngine(cfg, self.assets)
        self.venues = [SPOT] + ([FUT] if cfg.leverage and cfg.strategies else [])
        self.baseline = Btc200(self.broker, f"{cfg.baseline}/spot") if cfg.baseline else None
        self.last_hour: dict[str, int] = {}
        self.last_day: int | None = None
        self.baseline_pending: int | None = None
        self.next_snap: int | None = None
        self.backfills: dict = {}
        self.fund: dict[str, tuple] = {}
        self.restored: list[Position] = []
        self._next_hourly: int | None = None
        self._tick_err = (None, 0)
        self._closed = False
        self.stop: asyncio.Event | None = None

    # --- yardımcılar ---
    def now_ms(self) -> int:
        if self._now_fn is not None:
            return int(self._now_fn())
        return int(time.time() * 1000 + self.offset_ms)

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"[{_utc(self.now_ms())}] {msg}", flush=True)

    def price(self, venue: str, asset: str) -> float:
        p = self.last_px.get((venue, asset))
        if _fin(p):
            return p
        b = self.books.get(venue, asset)
        if b is not None and _fin(b.mid):
            return b.mid
        t = self.bars.last_open(venue, asset)
        return self.bars.get(venue, asset, t)[3] if t is not None else math.nan

    def venue_assets(self, venue: str) -> list[str]:
        return [a for a in self.assets if self.symbols.get(venue, a) is not None]

    def stream_assets(self, venue: str) -> list[str]:
        out = self.venue_assets(venue)
        if venue == SPOT and self.baseline and BTC not in out and self.symbols.get(SPOT, BTC):
            out.append(BTC)
        return out

    def snapshot_json(self) -> dict:
        return {"config": self.cfg.to_json(), "universe_month": self.month, "assets": self.assets,
                "slip": self.slip, "symbols": self.symbols.to_json(), "venues": self.venues,
                "keep_h": self.engine.keep_h}

    # --- olaylar ---
    def on_event(self, ev) -> None:
        t = self.now_ms()
        if isinstance(ev, AggTrade):
            self.last_px[(ev.venue, ev.asset)] = ev.price
            self.broker.on_trade(ev.venue, ev.asset, ev.price, t)
        elif isinstance(ev, Depth):
            self.books.apply(ev, t)
        elif isinstance(ev, Kline):
            if ev.closed:
                self.on_bar(ev.venue, ev.asset, ev.open_ms, ev.o, ev.h, ev.l, ev.c, t)
        elif isinstance(ev, MarkPrice):
            self.on_mark(ev, t)
        elif isinstance(ev, BookTicker):
            self.tickers[(ev.venue, ev.asset)] = ev

    def on_bar(self, venue, asset, open_ms, o, h, l, c, t) -> None:  # noqa: E741
        last = self.bars.last_open(venue, asset)
        self.bars.add(venue, asset, open_ms, o, h, l, c)
        if last is not None and open_ms > last + BAR_MS:
            n = (open_ms - last) // BAR_MS - 1
            self.rec.event(t, "kline_gap", venue, {"asset": asset, "from": _utc(last + BAR_MS),
                                                   "to": _utc(open_ms - BAR_MS), "n": int(n)})
            self.spawn_backfill(venue, [asset], last + BAR_MS, open_ms - 1, ("gap", venue, asset, open_ms))

    def on_mark(self, ev: MarkPrice, t: int) -> None:
        T_new = round(ev.next_funding_ms / 60_000) * 60_000 if ev.next_funding_ms else 0
        prev = self.fund.get(ev.asset)
        if prev is not None and prev[0] and T_new > prev[0]:     # borsa T'yi ilerletti → önceki T'de fonlama oldu
            T, r, mark, seen = prev
            est = (T - seen) > 60_000
            if est:
                self.rec.event(t, "funding_estimated", FUT, {"asset": ev.asset, "funding": _utc(T),
                                                             "last_seen": _utc(seen)})
            self.broker.on_funding(ev.asset, T, r, mark, t, estimated=est)
        self.fund[ev.asset] = (T_new, ev.funding_rate, ev.mark, t)
        self.broker.on_mark(ev.asset, ev.mark, t)

    def on_status(self, kind: str, detail: dict, tb: str | None) -> None:
        self.rec.event(self.now_ms(), kind, detail.get("venue"), detail, tb)
        if kind in ("connect", "disconnect", "stale", "stale_stream", "connect_error", "max_age", "handler_error"):
            self.log(f"{detail.get('venue')}: {kind} {json.dumps({k: v for k, v in detail.items() if k != 'venue'}, default=str)[:200]}")

    # --- REST tamamlama ---
    def spawn_backfill(self, venue, assets, start_ms, end_ms, tag):
        if tag in self.backfills:
            return self.backfills[tag]
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        task = loop.create_task(self.backfill(venue, assets, start_ms, end_ms))
        self.backfills[tag] = task
        return task

    async def backfill(self, venue: str, assets: list[str], start_ms: int, end_ms: int, interval: str = "15m") -> int:
        n = 0
        for a in assets:
            s = self.symbols.get(venue, a)
            if s is None:
                continue
            try:
                rows = await asyncio.to_thread(self.rest.klines, venue, s.symbol, interval, int(start_ms), int(end_ms))
            except Exception as e:  # noqa: BLE001
                self.rec.event(self.now_ms(), "backfill_error", venue, {"asset": a, "error": repr(e)[:300]},
                               traceback.format_exc(limit=6))
                continue
            for b in rest_bars(rows, s.mult, self.now_ms()):
                if self.bars.get(venue, a, b[0]) is None:
                    self.bars.add(venue, a, *b)
                    n += 1
        self.rec.event(self.now_ms(), "backfill", venue, {"assets": assets, "from": _utc(start_ms),
                                                          "to": _utc(end_ms), "added": n})
        return n

    # --- ısınma ---
    async def sync_clock(self) -> None:
        try:
            off, rtt = await asyncio.to_thread(clock_offset_ms, lambda: self.rest.server_time_ms(SPOT))
            self.offset_ms = off
            self.rec.event(self.now_ms(), "clock", SPOT, {"offset_ms": round(off, 1), "rtt_ms": round(rtt, 1)})
        except Exception as e:  # noqa: BLE001
            self.rec.event(self.now_ms(), "clock_error", SPOT, {"error": repr(e)[:300]}, traceback.format_exc(limit=6))

    async def warmup(self) -> None:
        now = self.now_ms()
        k_last = now // H_MS * H_MS - H_MS
        start = k_last - (self.engine.keep_h - 1) * H_MS
        last_seen = self.rec.get_state("last_seen_ms")
        if self.restored and last_seen:
            start = min(start, int(last_seen) // BAR_MS * BAR_MS)
        for venue in self.venues:
            await self.backfill(venue, self.stream_assets(venue), start, now)
        if self.baseline:
            s = self.symbols.get(SPOT, BTC)
            rows = await asyncio.to_thread(self.rest.klines, SPOT, s.symbol, "1d",
                                           now - (self.baseline.window + 40) * DAY_MS, now)
            for t, o, h, l, c in rest_bars(rows, 1.0, now):  # noqa: E741
                self.baseline.closes[t] = c
            self.last_day = now // DAY_MS * DAY_MS - DAY_MS
            self.baseline_pending = self.last_day
        if FUT in self.venues:
            for a in self.venue_assets(FUT):
                s = self.symbols.get(FUT, a)
                try:
                    d = await asyncio.to_thread(self.rest.premium_index, s.symbol)
                    T = round(int(d["nextFundingTime"]) / 60_000) * 60_000
                    self.fund[a] = (T, float(d["lastFundingRate"]), float(d["markPrice"]) / s.mult, now)
                except Exception as e:  # noqa: BLE001
                    self.rec.event(now, "rest_error", FUT, {"asset": a, "what": "premiumIndex", "error": repr(e)[:200]})
        await self.resolve_offline(now, last_seen)
        for venue in self.venues:
            sig = self.engine.compute(self.bars, venue, k_last)
            self.record_signals(sig, "warmup", now)
            self.last_hour[venue] = k_last
        self.rec.event(now, "warmup", None, {"hour": _utc(k_last), "keep_h": self.engine.keep_h,
                                             "bars": {f"{v}/{a}": len(d) for (v, a), d in self.bars.d.items()}})
        self.rec.flush()

    async def resolve_offline(self, now: int, last_seen) -> None:
        """Kural 10: geri yüklenen açık pozisyonlar için kapalı geçen süre (mumlar + REST fonlama)."""
        if not self.restored or not last_seen:
            return
        last_seen = int(last_seen)
        for pos in self.restored:
            acc = self.broker.accounts[pos.account]
            if pos.asset not in acc.positions:
                continue
            bars = self.bars.series(pos.venue, pos.asset, max(pos.entry_ms, last_seen) // BAR_MS * BAR_MS, now)
            hit = offline_exit(pos, bars, self.broker.assumed(pos.asset))
            if hit is not None:
                self.broker.close_offline(acc, pos, int(hit[0]), float(hit[1]), hit[2])
        for a in sorted({p.asset for p in self.restored if p.venue == FUT}):
            s = self.symbols.get(FUT, a)
            if s is None:
                continue
            try:
                rows = await asyncio.to_thread(self.rest.funding_rate, s.symbol, last_seen + 1, now)
            except Exception as e:  # noqa: BLE001
                self.rec.event(now, "rest_error", FUT, {"asset": a, "what": "fundingRate", "error": repr(e)[:200]})
                continue
            for r in rows:
                T = round(int(r["fundingTime"]) / 60_000) * 60_000
                mk = r.get("markPrice")
                mark = float(mk) / s.mult if mk not in (None, "") else self.price(FUT, a)
                self.broker.on_funding(a, T, float(r["fundingRate"]), mark, now)
        self.rec.event(now, "offline_resolved", None, {"since": _utc(last_seen), "positions": len(self.restored)})

    # --- karar ve zamanlayıcı ---
    def record_signals(self, sig: dict, phase: str, now: int) -> None:
        k, venue = sig["hour_ms"], sig["venue"]
        for name in sig["z"]:
            z, ok, top = sig["z"][name], sig["ok"][name], sig["top"][name]
            for j, a in enumerate(self.assets):
                self.rec.add("signals", hour_ms=k, hour=_utc(k), venue=venue, strategy=name, asset=a,
                             close=float(sig["closes"][j]), z=float(z[j]), ok=bool(ok[j]), top=bool(top[j]),
                             eligible=True, phase=phase, ts_ms=now)

    def decide(self, venue: str, k: int, now: int) -> list[Position]:
        sig = self.engine.compute(self.bars, venue, k)
        late = now - (k + H_MS) > float(self.cfg.run["max_late_s"]) * 1000
        self.record_signals(sig, "late" if late else "live", now)
        if late:
            self.rec.event(now, "decision_late", venue, {"hour": _utc(k), "late_s": (now - k - H_MS) / 1000})
        opened = self.broker.decide(sig, self.assets, now, enter=not late)
        sel = {n: [self.assets[j] for j in np.flatnonzero(sig["top"][n] & sig["ok"][n])] for n in sig["z"]}
        self.log(f"karar {venue} {_utc(k)[:13]}h: aday {sel} → {len(opened)} giriş")
        return opened

    def check_decisions(self, now: int) -> None:
        grace = float(self.cfg.run["close_grace_s"]) * 1000
        for venue in self.venues:
            if venue not in self.last_hour:
                continue
            k = self.last_hour[venue] + H_MS
            B = k + H_MS
            if now < B:
                continue
            bar = k + 3 * BAR_MS
            missing = [a for a in self.venue_assets(venue) if self.bars.get(venue, a, bar) is None]
            tag = ("hour", venue, k)
            if missing:
                if now < B + grace:
                    continue
                task = self.backfills.get(tag)
                if task is None:
                    if self.spawn_backfill(venue, missing, bar, bar + BAR_MS - 1, tag) is not None:
                        continue
                elif not task.done():
                    continue
            self.backfills.pop(tag, None)
            self.last_hour[venue] = k
            self.decide(venue, k, now)

    def check_baseline(self, now: int) -> None:
        if self.baseline is None or self.last_day is None:
            return
        b = self.books.get(SPOT, BTC)
        fresh = self.broker.fresh_book(SPOT, BTC, now) is not None
        if self.baseline_pending is not None and fresh:
            d, self.baseline_pending = self.baseline_pending, None
            self.baseline.apply(d, now)
        d = self.last_day + DAY_MS
        end = d + DAY_MS
        if now < end:
            return
        bar = end - BAR_MS
        tag = ("day", d)
        if self.bars.get(SPOT, BTC, bar) is None:
            if now < end + float(self.cfg.run["close_grace_s"]) * 1000:
                return
            task = self.backfills.get(tag)
            if task is None:
                if self.spawn_backfill(SPOT, [BTC], bar, end - 1, tag) is not None:
                    return
            elif not task.done():
                return
        self.backfills.pop(tag, None)
        bb = self.bars.get(SPOT, BTC, bar)
        if bb is not None:
            self.baseline.closes[d] = bb[3]
        self.last_day = d
        if now - end > float(self.cfg.run["max_late_s"]) * 1000:     # günlük kıyas geç de uygulanır, işaretlenir
            self.rec.event(now, "decision_late", SPOT, {"baseline_day": _utc(d)[:10], "late_s": (now - end) / 1000})
        if b is None or not fresh:
            self.baseline_pending = d
        else:
            self.baseline.apply(d, now)

    def check_snapshot(self, now: int) -> None:
        if self.next_snap is None:
            self.next_snap = (now // BAR_MS + 1) * BAR_MS
        if now >= self.next_snap:
            self.broker.snapshot(self.next_snap)
            self.next_snap = (now // BAR_MS + 1) * BAR_MS

    def hourly_chores(self, now: int) -> None:
        if self._next_hourly is None:
            self._next_hourly = (now // H_MS + 1) * H_MS
        if now < self._next_hourly:
            return
        self._next_hourly = (now // H_MS + 1) * H_MS
        self.bars.prune(now - (self.engine.keep_h + 48) * H_MS)
        self.backfills = {k: t for k, t in self.backfills.items() if k[0] != "gap" or not t.done()}
        parts = []
        for acc in self.broker.accounts.values():
            _, _, eq, n = self.broker.equity(acc)
            parts.append(f"{acc.acc_id}={eq:.2f}({n})")
        self.log("özsermaye: " + " ".join(parts))
        if (now // H_MS) % 24 == 0 and self.month:
            cur = pd.Timestamp(now, unit="ms").to_period("M")
            f = cfg_path(_S, "universe") / f"{cur.strftime('%Y-%m')}.csv"
            if str(cur) != self.month and f.exists():
                self.rec.event(now, "universe_stale", None, {"running": self.month, "available": str(cur)})

    def tick(self, now: int) -> None:
        self.broker.on_timer(now)
        self.check_decisions(now)
        self.check_baseline(now)
        self.check_snapshot(now)
        self.hourly_chores(now)

    async def _timer(self, stop: asyncio.Event) -> None:
        run = self.cfg.run
        last_flush = last_sync = time.monotonic()
        while not stop.is_set():
            now = self.now_ms()
            try:
                self.tick(now)
            except Exception as e:  # noqa: BLE001 — zamanlayıcı durmaz; aynı hata dakikada bir kaydedilir
                key = repr(e)[:300]
                if key != self._tick_err[0] or now - self._tick_err[1] > 60_000:
                    self.rec.event(now, "error", None, {"where": "tick", "error": key}, traceback.format_exc(limit=10))
                    self._tick_err = (key, now)
            m = time.monotonic()
            if m - last_flush >= float(run["flush_s"]):
                self.rec.set_state("last_seen_ms", now)
                self.rec.flush()
                last_flush = m
            if m - last_sync >= float(run["clock_sync_min"]) * 60:
                last_sync = m
                asyncio.get_running_loop().create_task(self.sync_clock())
            try:
                await asyncio.wait_for(stop.wait(), timeout=float(run["tick_s"]))
            except TimeoutError:
                pass

    def managers(self) -> list[StreamManager]:
        run = self.cfg.run
        out = []
        for venue in self.venues:
            syms = [self.symbols.get(venue, a).symbol for a in self.stream_assets(venue)]
            for url in stream_urls(venue, syms, kinds=run.get(f"{venue}_streams"), base=run.get(f"{venue}_ws")):
                out.append(StreamManager(venue, url, self.symbols, self.on_event, self.on_status,
                                         connect=self.connect, base_s=float(run["backoff_base_s"]),
                                         max_s=float(run["backoff_max_s"]), stale_s=float(run["stale_s"]),
                                         stream_stale_s=float(run["stream_stale_s"]),
                                         max_age_s=float(run["max_conn_age_h"]) * 3600))
        return out

    async def run(self, minutes: float | None = None) -> None:
        self.stop = asyncio.Event()
        now = self.now_ms()
        self.rec.add("config", ts_ms=now, json=self.snapshot_json())
        self.rec.event(now, "start", None, {"universe_month": self.month, "assets": self.assets,
                                            "accounts": list(self.broker.accounts), "minutes": minutes})
        self.log(f"başlıyor: evren {self.month} {self.assets}; hesaplar {list(self.broker.accounts)}")
        self.restored = self.broker.restore(now)
        if self.restored:
            self.log(f"{len(self.restored)} açık pozisyon geri yüklendi")
        tasks = []
        try:
            await self.sync_clock()
            await self.warmup()
            tasks = [asyncio.create_task(m.run(self.stop)) for m in self.managers()]
            tasks.append(asyncio.create_task(self._timer(self.stop)))
            if minutes:
                tasks.append(asyncio.create_task(self._stop_after(float(minutes) * 60)))
            await asyncio.gather(*tasks)
        finally:
            self.stop.set()
            self.shutdown()

    async def _stop_after(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self.stop.wait(), timeout=seconds)
        except TimeoutError:
            self.log(f"{seconds / 60:g} dk doldu, duruluyor")
            self.stop.set()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        now = self.now_ms()
        try:
            self.broker.snapshot(now)
            self.rec.event(now, "stop", None, {"stats": dict(self.broker.stats)})
            self.rec.set_state("last_seen_ms", now)
        finally:
            self.rec.close()
        self.log("kayıt kapatıldı")


def main(argv: list[str] | None = None) -> int:
    from trend.data._http import utf8_stdout
    ap = argparse.ArgumentParser(prog="python -m trend.live.paper", description="Canlı kâğıt takip (gerçek emir yok)")
    ap.add_argument("--config", default="live_v4.yaml")
    ap.add_argument("--minutes", type=float, default=None, help="N dakika sonra dur (yoksa durdurulana kadar)")
    ap.add_argument("--db", default=None, help="SQLite yolu (varsayılan data/live/live.db)")
    a = ap.parse_args(argv)
    utf8_stdout()
    p = Path(a.config)
    cfg = load_config(p if p.is_absolute() else ROOT / p)
    if a.db:
        cfg.run["db"] = a.db
    runner = LiveRunner(cfg)
    try:
        asyncio.run(runner.run(a.minutes))
    except KeyboardInterrupt:
        print("durduruldu (Ctrl+C)", flush=True)
    finally:
        runner.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
