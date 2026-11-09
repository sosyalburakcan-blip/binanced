"""Testnet emir yürütücüsü (Binance USDT-M vadeli testnet/demo) — canlı botun aynısı, gerçek para yok.

Piyasa verisi, sinyal, emir fiyatları ve tetikler GERÇEK Binance'ten gelir (LiveRunner'ın websocket/REST'i); yalnızca
emirler testnete gider. Testnetin kendi defteri gerçek değildir (05.11.2026 ölçümü: fiyat ~7 bps kayık, sığ): dolumlar
testnet defterine göre olur; aynı kararla gerçek veride çalışan kâğıt hesapla farkı raporlanır.

Güvenlik:
- `SignedRest` yalnızca `TESTNET_HOSTS`'a istek atar; başka bir adres verilirse ValueError (gerçek hesaba emir gidemez).
- Anahtar `testnet.env_file`'dan: BINANCE_TESTNET_API_KEY + _API_SECRET (HMAC) ya da _PRIVATE_KEY_PATH (Ed25519);
  bunlar yoksa BINANCE_API_KEY + BINANCE_API_SECRET (kullanıcı kararı 05.11.2026: anahtar `.env`'de). Adres kısıtı
  nedeniyle anahtar hangi ortamın olursa olsun istekler yalnızca testnete gider.

Bot kuralları (karar paper.py Kural 4 ile aynı; emirler gerçek API ile):
1. Hazırlık: her sembolde izole marjin ve kaldıraç L (L ≤ MAX_LEVERAGE = 3, fazlası ValueError); tek yönlü pozisyon
   kipi; testnet exchangeInfo emir kuralları. Ayardan sonra positionRisk geri okunur: kaldıracı > 3 ya da izole
   olmayan sembol `blocked` (yeni giriş yok, canlı giriş emri iptal); her mutabakatta yeniden denetlenir, bozulmuşsa
   kaldıraç/izole yeniden ayarlanır (kullanıcı arayüzden değiştirse bile).
2. Giriş: saatlik kararda aday sırası (azalan z) ve yuva sayısı kâğıtla aynı. Bütçe borsadan (kullanıcı kararı
   05.11.2026): taban = min(USDT cüzdan bakiyesi, kullanılabilir bakiye + botun kendi kilitli marjini) — açılışta ve
   her mutabakatta (`reconcile_s`) /fapi/v2/balance'tan; bütçe = taban · `balance_frac` (≤ MAX_BALANCE_FRAC = %20).
   Botun toplam marjini (açık pozisyonlar + canlı giriş emirleri) bütçeyi aşmaz: margin = min(bütçe / yuva,
   bütçe − kilitli) / (1 + L·taker) (giriş ücreti dahil). Bakiye `balance_max_age_s`'den eskiyse giriş yok
   (`no_balance`). Adet = margin·L / gerçek en iyi BID, adım aşağı; post-only (GTX) limit alış gerçek en iyi BID'de.
   Ret (EXPIRED / -5022: karşıya geçerdi) → `maker_reprice_s` sonra gerçek en iyi BID'den yeniden. Gerçek BID emrin
   üstüne çıkarsa (en sık `maker_reprice_s`) iptal + kalan adetle yeniden. Sonraki karar sınırından `entry_lead_s`
   önce iptal; kısmi dolum pozisyon olur.
3. Acil stop (kullanıcı kararı 05.11.2026): pozisyonda dolan ilk adetten itibaren BORSADA duran koşullu emir — Algo
   Order API (/fapi/v1/algoOrder; eski uç STOP_MARKET'i −4120 ile reddeder), STOP_MARKET SELL closePosition,
   tetik = p_in(1 − `emergency_sl`) (adım aşağı; sl < emergency_sl < likidasyon mesafesi), `emergency_working_type`
   (MARK_PRICE). Bot kapalı/kopuk olsa da pozisyonu borsa kapatır. Tetiklenen piyasa emrinin clientOrderId'si
   clientAlgoId'dir → dolumlar normal yoldan (çıkış nedeni `estop`). Durum ALGO_UPDATE'ten; mutabakatta borsada
   yoksa yeniden konur; pozisyon kapanınca (her çıkışta) iptal. Yeniden başlatmada benimsenen pozisyonun stopu
   korunur, sahipsiz `tn` stoplar iptal edilir. Tetik fiyatı zaten geçilmişse (−2021) SL çıkışı başlar.
4. Pozisyon: p_in = testnet dolumlarının VWAP'ı; TP = p_in(1 + tp) (adım yukarı) azaltmalı GTC limit satış testnette.
   SL = p_in(1 − sl) (adım aşağı): GERÇEK aggTrade ≤ SL → TP iptal, gerçek en iyi ASK'ta GTX azaltmalı satış, geride
   kalırsa taşınır; `sl_maker_s` dolmazsa iptal + azaltmalı piyasa satışı. Süre (hour_ms + max_hold_h): aynısı
   `time_maker_s` ile; süre satışı sürerken SL tetiklenirse SL beklemesine geçer.
5. Dolumlar kullanıcı akışından (ORDER_TRADE_UPDATE: adet, fiyat, komisyon, maker/taker); likidasyon emri çıkış
   sayılır; fonlama ACCOUNT_UPDATE (FUNDING_FEE). `reconcile_s`'de bir REST mutabakatı: borsadaki pozisyon miktarı ≠
   bizim hesap → işlem geçmişinden (userTrades) yeniden kurulur (`exec_mismatch`); bilinmeyen açık emrimiz iptal.
6. Yeniden başlatma: bizim (tn önekli) açık emirler iptal; açık pozisyon borsadan benimsenir (giriş saati kayıttan,
   yoksa şimdi), TP yeniden konur.
7. Kayıt: hesap `{strateji}/testnet{L}x`, piyasa "testnet" — paper_orders (cid, borsa durumu, gecikme), fills (borsa
   komisyonu, maker/taker, aynı andaki GERÇEK orta fiyata göre bps), positions, equity, events (exec_*).
Her slotta aynı anda en fazla bir REST isteği (`busy`); durum makinesi `_drive` her olayda bir sonraki adımı seçer.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import math
import time
import traceback
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

import requests

from trend.live.exchange import Filters, filters_from_info
from trend.live.stream import FUT, SymbolTable

TESTNET_HOSTS = frozenset({"demo-fapi.binance.com", "testnet.binancefuture.com"})
MAX_LEVERAGE = 3                  # kullanıcı kararı 05.11.2026: işlemler 3×'ten fazla açılmaz
MAX_BALANCE_FRAC = 0.20           # kullanıcı kararı 05.11.2026: bakiyenin en fazla %20'si (botun toplam marjini)
DEFAULTS = {"enabled": False, "env_file": ".env.testnet", "rest": "https://demo-fapi.binance.com",
            "ws": "wss://demo-fstream.binance.com", "leverage": 3, "entry_lead_s": 3.0, "reconcile_s": 60.0,
            "book_stale_s": 10.0, "recv_window_ms": 5000, "balance_frac": 0.20, "balance_max_age_s": 300.0,
            "emergency_sl": 0.06, "emergency_working_type": "MARK_PRICE", "emergency_retry_s": 10.0}
H_MS = 3_600_000
EPS = 1e-12


class ExchangeError(Exception):
    def __init__(self, http: int, code, msg: str):
        super().__init__(f"HTTP {http} {code}: {msg}")
        self.http, self.code, self.msg = http, code, msg


def read_env(path: Path) -> dict:
    out = {}
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _dec(step: float) -> int:
    if not step > 0:
        return 8
    return max(0, min(12, -int(math.floor(math.log10(step) + 1e-9))))


def fmt(x: float, step: float) -> str:
    return f"{x:.{_dec(step)}f}"


class SignedRest:
    """İmzalı REST (yalnızca testnet). HMAC-SHA256 ya da Ed25519 (base64 imza)."""

    def __init__(self, base: str, api_key: str, secret: str | None = None, private_key_path: str | None = None,
                 clock=None, recv_window: int = 5000, session: requests.Session | None = None):
        host = urllib.parse.urlparse(base).hostname
        if host not in TESTNET_HOSTS:
            raise ValueError(f"yalnızca testnet adresine izin var ({sorted(TESTNET_HOSTS)}): {base}")
        if not api_key or not (secret or private_key_path):
            raise ValueError("testnet anahtarı eksik (API key + secret ya da Ed25519 özel anahtar yolu)")
        self.base, self.key, self.recv_window = base.rstrip("/"), api_key, int(recv_window)
        self.clock = clock or (lambda: time.time() * 1000)
        self._secret = secret.encode() if secret else None
        self._ed = None
        if private_key_path:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key  # noqa: PLC0415
            self._ed = load_pem_private_key(Path(private_key_path).read_bytes(), password=None)
        self.session = session or requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": api_key, "User-Agent": "trend-testnet/0.1"})

    def _sign(self, payload: str) -> str:
        if self._ed is not None:
            return urllib.parse.quote(base64.b64encode(self._ed.sign(payload.encode())).decode(), safe="")
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

    def request(self, method: str, path: str, params: dict | None = None, signed: bool = True):
        p = {k: v for k, v in (params or {}).items() if v is not None}
        if signed:
            p["timestamp"] = int(self.clock())
            p["recvWindow"] = self.recv_window
        q = urllib.parse.urlencode(p)
        if signed:
            q += "&signature=" + self._sign(q)
        r = self.session.request(method, f"{self.base}{path}" + (f"?{q}" if q else ""), timeout=(5, 15))
        try:
            data = r.json()
        except ValueError:
            data = {"code": None, "msg": r.text[:200]}
        if r.status_code >= 400 or (isinstance(data, dict) and isinstance(data.get("code"), int) and data["code"] < 0):
            raise ExchangeError(r.status_code, data.get("code") if isinstance(data, dict) else None,
                                (data.get("msg") if isinstance(data, dict) else str(data))[:300])
        return data

    # --- uçlar ---
    def exchange_info(self):
        return self.request("GET", "/fapi/v1/exchangeInfo", signed=False)

    def new_order(self, **p):
        return self.request("POST", "/fapi/v1/order", {**p, "newOrderRespType": "RESULT"})

    def cancel_order(self, symbol: str, cid: str):
        return self.request("DELETE", "/fapi/v1/order", {"symbol": symbol, "origClientOrderId": cid})

    def open_orders(self):
        return self.request("GET", "/fapi/v1/openOrders")

    def new_algo(self, **p):
        """Koşullu emir (STOP_MARKET vb.): 2025 sonundan beri yalnızca Algo Order API (eski uç −4120)."""
        return self.request("POST", "/fapi/v1/algoOrder", {"algoType": "CONDITIONAL", **p})

    def cancel_algo(self, cid: str):
        return self.request("DELETE", "/fapi/v1/algoOrder", {"clientAlgoId": cid})

    def open_algo_orders(self):
        return self.request("GET", "/fapi/v1/openAlgoOrders")

    def positions(self):
        return self.request("GET", "/fapi/v2/positionRisk")

    def balance(self):
        return self.request("GET", "/fapi/v2/balance")

    def income(self, kind: str, start_ms: int):
        return self.request("GET", "/fapi/v1/income", {"incomeType": kind, "startTime": int(start_ms), "limit": 1000})

    def user_trades(self, symbol: str, start_ms: int):
        return self.request("GET", "/fapi/v1/userTrades", {"symbol": symbol, "startTime": int(start_ms), "limit": 1000})

    def leverage(self, symbol: str, lev: int):
        return self.request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": int(lev)})

    def margin_type(self, symbol: str, kind: str = "ISOLATED"):
        return self.request("POST", "/fapi/v1/marginType", {"symbol": symbol, "marginType": kind})

    def dual_side(self):
        return self.request("GET", "/fapi/v1/positionSide/dual")

    def set_dual_side(self, dual: bool):
        return self.request("POST", "/fapi/v1/positionSide/dual", {"dualSidePosition": "true" if dual else "false"})

    def listen_key(self):
        return self.request("POST", "/fapi/v1/listenKey", signed=False)["listenKey"]

    def keepalive(self):
        return self.request("PUT", "/fapi/v1/listenKey", signed=False)


# ---------------------------------------------------------------------------------------------------------------


@dataclass
class Order:
    cid: str
    kind: str                     # en (giriş) / tp / sx (maker çıkış) / mx (piyasa çıkış) / es (borsadaki acil stop)
    side: str
    price: float
    qty: float
    sent_ms: int
    status: str = "sending"       # sending → NEW/PARTIALLY_FILLED (canlı) → FILLED/CANCELED/EXPIRED (bitti)
    order_id: int | None = None
    filled: float = 0.0
    latency_ms: float | None = None
    canceling: bool = False
    ack_ms: int | None = None     # borsanın emri kabul ettiğini ilk öğrendiğimiz an (REST onayı ya da akış)

    @property
    def live(self) -> bool:                                # TRIGGERING/TRIGGERED: tetiklenen acil stop (algo)
        return self.status in ("sending", "NEW", "PARTIALLY_FILLED", "TRIGGERING", "TRIGGERED")


@dataclass
class Slot:
    asset: str
    symbol: str
    pos_id: str
    hour_ms: int
    z: float
    target: float                 # giriş emri toplam adedi
    start_ms: int
    state: str = "entry"          # entry → open → exit → closed
    entry_deadline: int = 0
    q: float = 0.0                # dolan giriş adedi
    cost: float = 0.0
    fee_in: float = 0.0
    xq: float = 0.0               # çıkış dolumları (TP, maker, piyasa, likidasyon)
    xn: float = 0.0
    xfee: float = 0.0
    funding: float = 0.0
    p_in: float = math.nan
    tp_px: float = math.inf
    sl_px: float = -math.inf
    deadline_ms: int | None = None
    exit_reason: str | None = None
    exit_deadline: int | None = None
    exit_ms: int | None = None
    orders: dict = field(default_factory=dict)       # kind → Order (en son)
    history: list = field(default_factory=list)      # bu slotun tüm emirleri (geçmişten yeniden kurma için)
    busy: bool = False
    retry_ms: int = 0
    es_retry_ms: int = 0          # acil stop yeniden deneme zamanı
    moved_ms: int = 0
    n_moves: int = 0
    n_rejects: int = 0
    flags: str = ""
    entry_ms: int | None = None
    ref_mid: float = math.nan

    @property
    def pos(self) -> float:
        return max(0.0, self.q - self.xq)


class TestnetBroker:
    """Gerçek veriyle karar, testnete gerçek API emirleri (modül notu). LiveRunner olayları: decide, on_book,
    on_trade, on_timer; kullanıcı akışı: on_user; mutabakat: reconcile."""

    __test__ = False                                     # pytest bunu test sınıfı sanmasın

    def __init__(self, cfg, tn: dict, books, rec, rest, symbols: SymbolTable, *, now_fn, log=None, note=None,
                 sync: bool = False):
        self.cfg, self.tn, self.books, self.rec, self.rest, self.symbols = cfg, tn, books, rec, rest, symbols
        self.strat = cfg.strategies[0]
        self.lev = float(tn["leverage"])
        if not (1 <= self.lev <= MAX_LEVERAGE and self.lev == int(self.lev)):
            raise ValueError(f"testnet kaldıracı 1..{MAX_LEVERAGE} tam sayı olmalı: {tn['leverage']}")
        self.frac = float(tn["balance_frac"])
        if not 0 < self.frac <= MAX_BALANCE_FRAC:
            raise ValueError(f"balance_frac 0 < x ≤ {MAX_BALANCE_FRAC} olmalı: {tn['balance_frac']}")
        self.bal_age_ms = int(float(tn["balance_max_age_s"]) * 1000)
        self.es = float(tn["emergency_sl"])                  # 0 = acil stop yok
        liq = 1.0 / self.lev - float(cfg.costs[FUT].mmr)     # izole likidasyon mesafesi (yaklaşık)
        if self.es and not self.strat.sl < self.es < liq:
            raise ValueError(f"emergency_sl {self.es} botun SL'inden ({self.strat.sl}) büyük, likidasyon mesafesinden "
                             f"({liq:.3f}) küçük olmalı")
        self.es_wt = str(tn["emergency_working_type"]).upper()
        if self.es_wt not in ("MARK_PRICE", "CONTRACT_PRICE"):
            raise ValueError(f"emergency_working_type MARK_PRICE ya da CONTRACT_PRICE: {self.es_wt}")
        self.es_retry_ms = int(float(tn["emergency_retry_s"]) * 1000)
        self.bal: dict | None = None                         # son borsa bakiyesi (wallet, avail, base, budget, ts)
        self.blocked: dict[str, str] = {}                     # varlık → neden (kaldıraç/marjin denetimi geçmedi)
        self.capital, self.slots_n = float(cfg.capital), int(cfg.slots)   # capital: açılışta bütçeyle değişir (kayıt)
        self.taker = float(cfg.costs[FUT].taker)
        self.acc_id = f"{self.strat.name}/testnet{self.lev:g}x"
        self.now_fn = now_fn
        self.log = log or (lambda m: None)
        self.note = note or (lambda m: None)
        self.sync = sync
        run = cfg.run
        self.reprice_ms = int(float(run["maker_reprice_s"]) * 1000)
        self.wait_ms = {"sl": int(float(run["sl_maker_s"]) * 1000), "time": int(float(run["time_maker_s"]) * 1000)}
        self.lead_ms = int(float(tn["entry_lead_s"]) * 1000)
        self.stale_ms = int(float(tn["book_stale_s"]) * 1000)
        self.filters: dict[str, Filters] = {}
        self.slots: dict[str, Slot] = {}
        self.cids: dict[str, tuple[str, str]] = {}           # cid → (varlık, tür)
        self.closed_pnl = 0.0
        self.ready = False
        self.stats: dict[str, int] = {}
        n, s = int(time.time() * 1000), ""
        while n:
            n, r = divmod(n, 36)
            s = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + s
        self._prefix, self._n = s, 0

    # --- yardımcılar ---
    def _id(self, kind: str) -> str:
        self._n += 1
        return f"tn{kind}{self._prefix}{self._n}"

    def _stat(self, k: str) -> None:
        self.stats[k] = self.stats.get(k, 0) + 1

    def _event(self, kind: str, detail: dict, tb: str | None = None) -> None:
        self.rec.event(self.now_fn(), kind, "testnet", detail, tb)

    def _book(self, asset: str, now: int):
        b = self.books.get(FUT, asset)
        return b if b is not None and not b.empty() and now - b.ts_ms <= self.stale_ms else None

    def _real_mid(self, asset: str) -> float:
        b = self.books.get(FUT, asset)
        return b.mid if b is not None and not b.empty() else math.nan

    def locked(self) -> float:
        """Botun kendi kullandığı marjin: dolan girişler (açık pozisyon) + canlı giriş emirlerinin kalan kısmı."""
        locked = 0.0
        for s in self.slots.values():
            locked += max(0.0, s.cost - (s.cost / s.q * s.xq if s.q > EPS else 0.0)) / self.lev
            if s.state == "entry":
                o = s.orders.get("en")
                if o is not None and o.live:
                    locked += max(0.0, o.qty - o.filled) * o.price / self.lev
        return locked

    def equity(self, px_fn=None) -> tuple[float, float]:
        """(özsermaye, kilitli marjin): kayıt sermayesi (açılıştaki bütçe) + kapanan PnL + açık pozisyonların gerçek
        fiyatla değeri. Boyutlandırma bunu değil borsa bakiyesini kullanır (`budget`)."""
        eq = self.capital + self.closed_pnl
        for s in self.slots.values():
            px = px_fn(s.asset) if px_fn else self._real_mid(s.asset)
            if not (isinstance(px, float) and math.isfinite(px)):
                px = s.p_in if math.isfinite(s.p_in) else 0.0
            eq += s.xn + s.pos * px - s.cost - s.fee_in - s.xfee - s.funding
        return eq, self.locked()

    # --- borsa bakiyesi ve kaldıraç denetimi ---
    def _set_balance(self, rows, now: int) -> None:
        u = next((b for b in rows or [] if b.get("asset") == "USDT"), None)
        if u is None:
            self._event("exec_error", {"call": "balance", "error": "USDT satırı yok"})
            return
        wallet, avail = float(u["balance"]), float(u["availableBalance"])
        base = max(0.0, min(wallet, avail + self.locked()))
        self.bal = {"wallet": wallet, "avail": avail, "base": base, "budget": self.frac * base, "ts": int(now)}

    def budget(self, now: int) -> float | None:
        """Botun toplam marjin sınırı (USDT) ya da bakiye eski/yoksa None."""
        if self.bal is None or now - self.bal["ts"] > self.bal_age_ms:
            return None
        return self.bal["budget"]

    def _check_leverage(self, prows, fix: bool = False) -> None:
        """positionRisk satırlarından her sembolün kaldıraç ≤ MAX_LEVERAGE ve izole olduğunu doğrular."""
        by = {p.get("symbol"): p for p in prows or []}
        for a, f in self.filters.items():
            p, why = by.get(f.symbol), None
            if p is None:
                why = "kaldıraç okunamadı"
            else:
                try:
                    lev = float(p.get("leverage"))
                except (TypeError, ValueError):
                    lev = math.nan
                iso = str(p.get("marginType", "")).lower() == "isolated" or p.get("isolated") is True
                if not lev <= MAX_LEVERAGE:                      # NaN da geçmez
                    why = f"kaldıraç {p.get('leverage')}× > {MAX_LEVERAGE}×"
                elif not iso:
                    why = f"marjin {p.get('marginType')} (izole değil)"
            old = self.blocked.get(a)
            if why:
                self.blocked[a] = why
                if old != why:
                    self._event("exec_guard", {"asset": a, "symbol": f.symbol, "why": why, "blocked": True})
                    self.note(f"⚠️ TESTNET {a}: {why} → yeni giriş durduruldu, düzeltiliyor")
                slot = self.slots.get(a)
                if slot is not None and slot.state == "entry":
                    self._drive(slot, int(self.now_fn()))        # canlı giriş emri hemen iptal
                if fix:
                    self._call(None, "leverage fix", self.rest.leverage, f.symbol, int(self.lev))
                    if "izole" in why:
                        self._call(None, "margin fix", self.rest.margin_type, f.symbol, "ISOLATED")
            elif old:
                self.blocked.pop(a)
                self._event("exec_guard", {"asset": a, "symbol": f.symbol, "why": "düzeldi", "blocked": False})

    # --- REST çağrısı (slot başına tek istek) ---
    def _call(self, slot: Slot | None, label: str, fn, *args, ok=None, err=None, **kw) -> bool:
        if slot is not None:
            if slot.busy:
                return False
            slot.busy = True

        def done(res, exc, dt):
            if slot is not None:
                slot.busy = False
            try:
                if exc is None:
                    if ok:
                        ok(res, dt)
                elif isinstance(exc, ExchangeError):
                    if err:
                        err(exc)
                    else:
                        self._event("exec_error", {"call": label, "error": str(exc)})
                else:
                    self._event("exec_error", {"call": label, "error": repr(exc)[:300]},
                                "".join(traceback.format_exception(exc))[-2000:])
            finally:
                if slot is not None and slot.state != "closed":
                    self._drive(slot, self.now_fn())

        if self.sync:
            t0 = time.perf_counter()
            try:
                res, exc = fn(*args, **kw), None
            except Exception as e:  # noqa: BLE001
                res, exc = None, e
            done(res, exc, (time.perf_counter() - t0) * 1000)
            return True

        async def go():
            t0 = time.perf_counter()
            try:
                res, exc = await asyncio.to_thread(fn, *args, **kw), None
            except Exception as e:  # noqa: BLE001
                res, exc = None, e
            done(res, exc, (time.perf_counter() - t0) * 1000)
        asyncio.get_running_loop().create_task(go())
        return True

    # --- hazırlık ve benimseme ---
    def setup(self, assets: list[str]) -> None:
        """Eşzamanlı (başlangıçta bir kez, iş parçacığında çağrılır): kurallar, marjin tipi, kaldıraç, pozisyon kipi,
        bizim eski açık emirlerin iptali, açık pozisyonların benimsenmesi."""
        info = self.rest.exchange_info()
        self.filters = filters_from_info(info, self.symbols, FUT)
        missing = [a for a in assets if a not in self.filters]
        if missing:
            self._event("exec_setup", {"missing_on_testnet": missing})
        try:
            if self.rest.dual_side().get("dualSidePosition"):
                self.rest.set_dual_side(False)
        except ExchangeError as e:
            self._event("exec_error", {"call": "positionSide", "error": str(e)})
        for a in assets:
            f = self.filters.get(a)
            if f is None:
                continue
            try:
                self.rest.margin_type(f.symbol, "ISOLATED")
            except ExchangeError as e:
                if e.code != -4046:                       # "No need to change margin type"
                    self._event("exec_error", {"call": "marginType", "asset": a, "error": str(e)})
            try:
                self.rest.leverage(f.symbol, int(self.lev))
            except ExchangeError as e:
                self._event("exec_error", {"call": "leverage", "asset": a, "error": str(e)})
        prows = self.rest.positions()                    # geri okuma: kaldıraç ≤ 3× ve izole mi (borsanın kendisi)
        self._check_leverage(prows)
        sym2asset = {f.symbol: a for a, f in self.filters.items()}
        for o in self.rest.open_orders():
            if str(o.get("clientOrderId", "")).startswith("tn") and o.get("symbol") in sym2asset:
                try:
                    self.rest.cancel_order(o["symbol"], o["clientOrderId"])
                except ExchangeError:
                    pass
        known = {r["asset"]: r for r in self.rec.rows("SELECT * FROM positions WHERE account = ? AND status = 'open'",
                                                       (self.acc_id,))}
        self.closed_pnl = sum(float(r["pnl"] or 0) for r in
                              self.rec.rows("SELECT pnl FROM positions WHERE account = ? AND status = 'closed'",
                                            (self.acc_id,)))
        now = int(self.now_fn())
        adopted = []
        for p in prows:
            a = sym2asset.get(p.get("symbol"))
            amt = float(p.get("positionAmt") or 0)
            if a is None or abs(amt) <= EPS:
                continue
            if amt < 0:
                self._event("exec_error", {"call": "adopt", "asset": a, "error": f"kısa pozisyon {amt}"})
                continue
            r = known.pop(a, None)
            ep = float(p["entryPrice"])
            s = Slot(a, self.filters[a].symbol, r["pos_id"] if r else self._id("p"), int(r["hour_ms"]) if r else now,
                     float(r["z"]) if r and r["z"] is not None else math.nan, amt, int(r["entry_ms"]) if r else now,
                     state="open", q=amt, cost=amt * ep, fee_in=float(r["fee_in"]) if r else 0.0,
                     funding=float(r["funding"] or 0) if r else 0.0, flags="adopted", entry_ms=int(r["entry_ms"]) if r else now)
            self._arm(s)
            self.slots[a] = s
            adopted.append(a)
        try:                                             # acil stoplar: benimsenen pozisyonunki korunur, gerisi iptal
            algos = self.rest.open_algo_orders()
        except ExchangeError as e:
            algos = []
            self._event("exec_error", {"call": "openAlgoOrders", "error": str(e)})
        kept = []
        for o in algos:
            cid, a = str(o.get("clientAlgoId", "")), sym2asset.get(o.get("symbol"))
            if not cid.startswith("tn") or a is None:
                continue
            s = self.slots.get(a)
            if s is not None and "es" not in s.orders and o.get("side") == "SELL":
                od = Order(cid, "es", "SELL", float(o.get("triggerPrice") or "nan"), s.pos, now, status="NEW",
                           order_id=o.get("algoId"), ack_ms=now)
                s.orders["es"] = od
                s.history.append(od)
                self.cids[cid] = (a, "es")
                kept.append(a)
            else:
                try:
                    self.rest.cancel_algo(cid)
                except ExchangeError:
                    pass
        if kept:
            self._event("exec_stop", {"adopted": kept})
        for a, r in known.items():                       # kayıtta açık ama borsada yok: kapanmış (kapalıyken)
            self.rec.add("positions", **{**r, "status": "closed", "exit_ms": now, "reason": "unknown_offline",
                                         "flags": (r.get("flags") or "") + ",closed_while_down", "updated_ms": now})
        if adopted:
            self._event("exec_adopt", {"assets": adopted})
        try:
            self._set_balance(self.rest.balance(), now)
        except ExchangeError as e:                       # mutabakatta yeniden denenir; o zamana dek giriş yok
            self._event("exec_error", {"call": "balance", "error": str(e)})
        # kayıt sermayesi: ilk açılıştaki bütçe; işlem geçmişi varsa ilk değer korunur (raporların başlangıcı)
        acc = self.rec.rows("SELECT * FROM accounts WHERE account = ?", (self.acc_id,))
        traded = self.rec.rows("SELECT 1 FROM positions WHERE account = ? LIMIT 1", (self.acc_id,))
        if acc and traded:
            self.capital = float(acc[0]["capital"])
        else:
            if self.bal is not None:
                self.capital = self.bal["budget"]
            self.rec.add("accounts", account=self.acc_id, strategy=self.strat.name, venue="testnet", leverage=self.lev,
                         capital=self.capital, params={"strategy": self.strat.__dict__, "venue": "testnet",
                                                       "leverage": self.lev, "capital": self.capital,
                                                       "sizing": "exchange_balance", "balance_frac": self.frac,
                                                       "max_leverage": MAX_LEVERAGE, "rest": self.tn["rest"]},
                         created_ms=int(acc[0]["created_ms"]) if acc else now)
        self.ready = True
        self._event("exec_ready", {"account": self.acc_id, "assets": sorted(self.filters), "adopted": adopted,
                                   "closed_pnl": self.closed_pnl, "balance": self.bal, "blocked": self.blocked,
                                   "leverage": self.lev, "balance_frac": self.frac})

    def _arm(self, s: Slot) -> None:
        f = self.filters[s.asset]
        s.p_in = s.cost / s.q
        s.tp_px = f.ceil_px(s.p_in * (1.0 + self.strat.tp))
        s.sl_px = f.floor_px(s.p_in * (1.0 - self.strat.sl))
        s.deadline_ms = int(s.hour_ms) + self.strat.max_hold_h * H_MS

    # --- karar ---
    def decide(self, sig: dict, assets: list[str], now: int) -> list[str]:
        if not self.ready:
            return []
        name = self.strat.name
        z, ok, top = sig["z"][name], sig["ok"][name], sig["top"][name]
        sel = top & ok
        B = int(sig["hour_ms"]) + H_MS
        placed = []
        if not sel.any():
            return placed
        cand = sorted((j for j in range(len(assets)) if sel[j]), key=lambda j: (-z[j], j))
        free = self.slots_n - len(self.slots)
        budget, locked = self.budget(now), self.locked()
        for j in cand:
            a = assets[j]
            if a in self.slots:
                continue
            why = None
            f, book = self.filters.get(a), self._book(a, now)
            if free <= 0:
                why = "no_slot"
            elif f is None:
                why = "not_on_testnet"
            elif a in self.blocked:
                why = f"guard: {self.blocked[a]}"
            elif budget is None:
                why = "no_balance"
            elif book is None:
                why = "no_book"
            if why is None:
                m = min(budget / self.slots_n, budget - locked) / (1.0 + self.lev * self.taker)
                px = f.floor_px(book.best_bid)
                qty = f.floor_qty(m * self.lev / px) if m > 0 else 0.0
                why = f.check(qty, px)
            if why:
                self.rec.event(now, "entry_skip", "testnet", {"account": self.acc_id, "asset": a, "why": why,
                                                               "z": float(z[j])})
                continue
            self._event("exec_size", {"asset": a, "qty": qty, "price": px, "notional": qty * px,
                                      "margin": qty * px / self.lev, "leverage": self.lev, "budget": budget,
                                      "locked_before": locked, "base": self.bal["base"], "frac": self.frac})
            s = Slot(a, f.symbol, self._id("p"), B, float(z[j]), qty, int(now), entry_deadline=B + H_MS - self.lead_ms,
                     ref_mid=book.mid)
            self.slots[a] = s
            locked += qty * px / self.lev
            free -= 1
            placed.append(a)
            self._drive(s, now)
        return placed

    # --- piyasa olayları (GERÇEK veri) ---
    def on_book(self, venue: str, asset: str, ts: int, ex_ms=None) -> None:
        s = self.slots.get(asset) if venue == FUT else None
        if s is not None:
            self._drive(s, int(ts))

    def on_trade(self, venue: str, asset: str, price: float, ts: int, qty: float = 0.0, buyer_maker=None,
                 ex_ms=None) -> None:
        s = self.slots.get(asset) if venue == FUT else None
        if s is None:
            return
        if s.state == "open" and price <= s.sl_px:
            self._begin_exit(s, "sl", int(ts), {"trade_px": price})
        elif s.state == "exit" and s.exit_reason == "time" and price <= s.sl_px:
            s.exit_reason = "sl"
            s.exit_deadline = min(s.exit_deadline, int(ts) + self.wait_ms["sl"])
        self._drive(s, int(ts))

    def on_timer(self, now: int) -> None:
        for s in list(self.slots.values()):
            if s.state == "open" and s.deadline_ms is not None and now >= s.deadline_ms:
                self._begin_exit(s, "time", now)
            self._drive(s, now)

    def _begin_exit(self, s: Slot, reason: str, now: int, detail: dict | None = None) -> None:
        s.state, s.exit_reason, s.exit_deadline = "exit", reason, now + self.wait_ms[reason]
        self._event("exec_exit_start", {"asset": s.asset, "reason": reason, "pos": s.pos, **(detail or {})})

    # --- durum makinesi ---
    def _drive(self, s: Slot, now: int) -> None:
        if s.busy or s.state == "closed":
            return
        if self.es and s.pos > EPS:                       # koruma önce: borsada acil stop yoksa koy
            o_es = s.orders.get("es")
            if (o_es is None or not o_es.live) and now >= s.es_retry_ms:
                self._place_stop(s, now)
                return
        o_en, o_tp, o_sx, o_mx = (s.orders.get(k) for k in ("en", "tp", "sx", "mx"))
        if s.state == "entry":
            if now >= s.entry_deadline or s.asset in self.blocked:
                if o_en is not None and o_en.live:
                    self._cancel(s, o_en)
                    return
                self._finish_entry(s, now)
                return
            if o_en is None or not o_en.live:
                rem = s.target - s.q
                f = self.filters[s.asset]
                if rem < f.min_qty - EPS:
                    self._finish_entry(s, now)
                    return
                if now >= s.retry_ms:
                    book = self._book(s.asset, now)
                    if book is not None:
                        self._place(s, "en", "BUY", f.floor_px(book.best_bid), f.floor_qty(rem), now)
                return
            self._maybe_move(s, o_en, now)
            return
        if s.state == "open":
            if (o_tp is None or not o_tp.live) and s.pos > EPS and now >= s.retry_ms:
                f = self.filters[s.asset]
                self._place(s, "tp", "SELL", s.tp_px, f.floor_qty(s.pos), now, tif="GTC", reduce=True)
            return
        if s.state == "exit":
            if s.pos <= EPS:
                self._close(s, now)
                return
            if o_tp is not None and o_tp.live:
                self._cancel(s, o_tp)
                return
            f = self.filters[s.asset]
            if now >= s.exit_deadline:
                if o_sx is not None and o_sx.live:
                    self._cancel(s, o_sx)
                    return
                if o_mx is None or not o_mx.live:
                    qty = f.floor_qty(s.pos, market=True)
                    if qty < f.mkt_min_qty - EPS:
                        s.flags = ",".join(x for x in (s.flags, "dust") if x)
                        self._close(s, now)
                        return
                    self._place(s, "mx", "SELL", math.nan, qty, now, typ="MARKET", reduce=True)
                return
            if o_sx is None or not o_sx.live:
                if now >= s.retry_ms:
                    book = self._book(s.asset, now)
                    if book is None:                     # taze gerçek defter yok → piyasa satışı
                        s.exit_deadline = now
                        self._drive(s, now)
                        return
                    self._place(s, "sx", "SELL", f.ceil_px(book.best_ask), f.floor_qty(s.pos), now, reduce=True)
                return
            self._maybe_move(s, o_sx, now)

    def _maybe_move(self, s: Slot, o: Order, now: int) -> None:
        """Gerçek en iyi fiyat emrin önüne geçtiyse (en sık reprice) iptal; sonraki adımda yeni fiyattan konur."""
        if o.status == "sending" or now - s.moved_ms < self.reprice_ms:
            return
        book = self._book(s.asset, now)
        if book is None:
            return
        behind = book.best_bid > o.price if o.side == "BUY" else book.best_ask < o.price
        if behind:
            s.moved_ms, s.n_moves = now, s.n_moves + 1
            self._cancel(s, o)

    # --- emir gönderme / iptal ---
    def _place(self, s: Slot, kind: str, side: str, price: float, qty: float, now: int, typ: str = "LIMIT",
               tif: str = "GTX", reduce: bool = False) -> None:
        f = self.filters[s.asset]
        cid = self._id(kind)
        o = Order(cid, kind, side, price, qty, int(now))
        s.orders[kind] = o
        s.history.append(o)
        self.cids[cid] = (s.asset, kind)
        p = {"symbol": s.symbol, "side": side, "type": typ, "quantity": fmt(qty, f.mkt_step if typ == "MARKET" else f.step),
             "newClientOrderId": cid}
        if typ == "LIMIT":
            p.update(price=fmt(price, f.tick), timeInForce=tif)
        if reduce:
            p["reduceOnly"] = "true"
        if tif == "GTX" and typ == "LIMIT":
            s.moved_ms = now                               # taşıma en erken reprice_s sonra (kâğıtla aynı)
        self._order_row(s, o, now)

        def ok(r, dt):
            o.latency_ms, o.order_id = dt, r.get("orderId")
            o.ack_ms = o.ack_ms or int(self.now_fn())
            st = r.get("status", "NEW")
            if o.status == "sending":
                o.status = st
            o.filled = max(o.filled, float(r.get("executedQty") or 0))
            if st == "EXPIRED" and o.filled <= EPS:           # GTX karşıya geçerdi
                self._reject(s, o)
            self._order_row(s, o, self.now_fn(), {"ack_status": st, "latency_ms": round(dt, 1)})
            if s.state == "closed" and o.live:              # slot bu arada kapandı (ör. acil stop) → emri bırakma
                self._cleanup(s)

        def err(e: ExchangeError):
            o.status = "REJECTED"
            if e.code == -5022:
                self._reject(s, o)
            else:
                self._stat("errors")
                self._event("exec_error", {"call": f"order {kind}", "asset": s.asset, "error": str(e), "params": p})
                if kind == "en" and s.q <= EPS:
                    s.entry_deadline = 0                       # giriş vazgeçilir
                elif kind in ("sx", "tp"):
                    s.retry_ms = int(self.now_fn()) + max(self.reprice_ms, 2000)
                elif kind == "mx":
                    s.retry_ms = int(self.now_fn()) + 5000
                    self._resync(s)
            self._order_row(s, o, self.now_fn(), {"error": str(e)})
        self._call(s, f"order {kind}", self.rest.new_order, ok=ok, err=err, **p)

    def _place_stop(self, s: Slot, now: int) -> None:
        """Borsada duran acil stop: STOP_MARKET SELL closePosition (Algo Order API), tetik p_in(1 − emergency_sl)."""
        f = self.filters[s.asset]
        ref = s.p_in if math.isfinite(s.p_in) else s.cost / s.q
        px = f.floor_px(ref * (1.0 - self.es))
        cid = self._id("es")
        o = Order(cid, "es", "SELL", px, s.pos, int(now))
        s.orders["es"] = o
        s.history.append(o)
        self.cids[cid] = (s.asset, "es")
        p = {"symbol": s.symbol, "side": "SELL", "type": "STOP_MARKET", "triggerPrice": fmt(px, f.tick),
             "closePosition": "true", "workingType": self.es_wt, "clientAlgoId": cid}
        self._order_row(s, o, now)

        def ok(r, dt):
            o.latency_ms, o.order_id = dt, r.get("algoId")
            o.ack_ms = o.ack_ms or int(self.now_fn())
            st = r.get("algoStatus", "NEW")
            if o.status == "sending":
                o.status = st
            self._order_row(s, o, self.now_fn(), {"ack_status": st, "latency_ms": round(dt, 1), "algo": True})
            self._event("exec_stop", {"asset": s.asset, "cid": cid, "status": st, "trigger": px, "p_in": ref,
                                      "pct": -self.es, "working_type": self.es_wt})
            if s.state == "closed" and o.live:
                self._cleanup(s)

        def err(e: ExchangeError):
            o.status = "REJECTED"
            s.es_retry_ms = int(self.now_fn()) + self.es_retry_ms
            self._stat("errors")
            self._event("exec_error", {"call": "order es", "asset": s.asset, "error": str(e), "params": p})
            self._order_row(s, o, self.now_fn(), {"error": str(e)})
            if e.code == -2021 and s.state == "open":        # tetik fiyatı zaten geçilmiş → hemen SL çıkışı
                self._begin_exit(s, "sl", int(self.now_fn()), {"why": "acil stop tetiği geçilmiş"})
        self._call(s, "order es", self.rest.new_algo, ok=ok, err=err, **p)

    def _cleanup(self, s: Slot) -> None:
        """Kapanan slotun borsada kalan emirlerini (acil stop, TP, giriş) iptal eder; slot kilidi yok."""
        for o in s.orders.values():
            if not o.live or o.canceling or o.status == "sending":
                continue
            o.canceling = True

            def ok(r, dt, o=o):
                o.status = "CANCELED"
                self._order_row(s, o, self.now_fn(), {"cleanup": True})

            def err(e: ExchangeError, o=o):
                if e.code in (-2011, -2013):                 # zaten yok (borsa kendisi kapattı: azaltmalı emirler
                    o.status = "GONE"                        # ve closePosition stop pozisyon sıfırlanınca düşer)
                    self._order_row(s, o, self.now_fn(), {"cleanup": True, "already_gone": True})
                else:
                    o.canceling = False
                    self._event("exec_error", {"call": f"cleanup {o.kind}", "asset": s.asset, "error": str(e)})
            if o.kind == "es":
                self._call(None, "cleanup es", self.rest.cancel_algo, o.cid, ok=ok, err=err)
            else:
                self._call(None, f"cleanup {o.kind}", self.rest.cancel_order, s.symbol, o.cid, ok=ok, err=err)

    def _reject(self, s: Slot, o: Order) -> None:
        s.n_rejects += 1
        s.retry_ms = int(self.now_fn()) + self.reprice_ms
        self._stat("rejects")
        self.rec.event(self.now_fn(), "maker_reject", "testnet", {"account": self.acc_id, "asset": s.asset,
                                                                   "kind": o.kind, "price": o.price})

    def _cancel(self, s: Slot, o: Order) -> None:
        if o.canceling:
            return
        o.canceling = True

        def ok(r, dt):
            o.status = r.get("status", "CANCELED")
            o.filled = max(o.filled, float(r.get("executedQty") or 0))
            self._order_row(s, o, self.now_fn(), {"cancel_latency_ms": round(dt, 1)})

        def err(e: ExchangeError):
            if e.code == -2011:                              # bilinmeyen emir: dolmuş/iptal olmuş → geçmişten kur
                o.status = "UNKNOWN"
                self._resync(s)
            else:
                o.canceling = False
                self._event("exec_error", {"call": f"cancel {o.kind}", "asset": s.asset, "error": str(e)})
        if o.kind == "es":
            self._call(s, "cancel es", self.rest.cancel_algo, o.cid, ok=ok, err=err)
        else:
            self._call(s, f"cancel {o.kind}", self.rest.cancel_order, s.symbol, o.cid, ok=ok, err=err)

    # --- durum geçişleri ---
    def _finish_entry(self, s: Slot, now: int) -> None:
        if s.q <= EPS:
            s.state = "closed"
            self.slots.pop(s.asset, None)
            self.rec.event(now, "entry_skip", "testnet", {"account": self.acc_id, "asset": s.asset, "why": "unfilled",
                                                         "z": s.z, "n_moves": s.n_moves, "n_rejects": s.n_rejects})
            self.note(f"🧪⚪ TESTNET GİRİŞ DOLMADI {s.asset} ({s.n_moves} taşıma, {s.n_rejects} ret) · iptal")
            return
        if s.q < s.target - EPS:
            s.flags = ",".join(x for x in (s.flags, "partial") if x)
        s.state = "open"
        s.entry_ms = s.entry_ms or now
        self._arm(s)
        self._pos_row(s, now)
        self._stat("entries")
        mid = s.ref_mid
        vs = f" · karar anındaki gerçek ortaya göre {(s.p_in / mid - 1) * 1e4:+.1f}bps" if math.isfinite(mid) else ""
        self.log(f"TESTNET GİRİŞ {s.asset} {s.q:g} @ {s.p_in:.6g}{vs}")
        bud = f" (bütçe {self.bal['budget']:.0f}$ = bakiyenin %{self.frac * 100:g}'i)" if self.bal else ""
        self.note(f"🧪🟢 TESTNET GİRİŞ {s.asset} {s.q:g} @ {s.p_in:.6g} · {s.cost:.0f}$ {self.lev:g}× · marjin "
                  f"{s.cost / self.lev:.0f}${bud} · ücret {s.fee_in:.3f}${vs}\n   kâr al {s.tp_px:.6g} · zarar kes "
                  f"{s.sl_px:.6g}")
        self._drive(s, now)

    def _close(self, s: Slot, now: int) -> None:
        s.state = "closed"
        s.exit_ms = now
        self.slots.pop(s.asset, None)
        self._cleanup(s)                                   # acil stop ve kalan emirler borsada kalmasın
        pnl = s.xn - s.cost - s.fee_in - s.xfee - s.funding
        self.closed_pnl += pnl
        self._pos_row(s, now, pnl=pnl)
        self._stat(f"exit_{s.exit_reason}")
        p_out = s.xn / s.xq if s.xq > 0 else math.nan
        self.log(f"TESTNET ÇIKIŞ {s.asset} {s.exit_reason} p_out={p_out:.6g} pnl={pnl:+.2f}")
        self.note(f"🧪{'✅' if pnl > 0 else '🔴'} TESTNET ÇIKIŞ {s.asset} {s.exit_reason} @ {p_out:.6g} · {pnl:+.2f}$"
                  f" · ücret {s.fee_in + s.xfee:.3f}$")

    # --- kullanıcı akışı ---
    def on_user(self, msg: dict) -> None:
        e = msg.get("e")
        if e == "ORDER_TRADE_UPDATE":
            self._on_order(msg["o"], int(msg.get("E") or self.now_fn()))
        elif e == "ACCOUNT_UPDATE":
            a = msg.get("a", {})
            if a.get("m") == "FUNDING_FEE":              # tutar mutabakatta gelir kaydından (sembol başına)
                self.rec.event(self.now_fn(), "exec_funding", "testnet",
                               {"balance_change": [b.get("bc") for b in a.get("B", []) if b.get("a") == "USDT"]})
        elif e == "ALGO_UPDATE":
            self._on_algo(msg.get("o", {}), int(msg.get("E") or self.now_fn()))
        elif e == "listenKeyExpired":
            self._event("exec_stream", {"info": "listenKeyExpired"})

    def _on_algo(self, o: dict, E: int) -> None:
        """Acil stop durumu: NEW → TRIGGERING → TRIGGERED (ai = piyasa emri) → FINISHED; CANCELED/EXPIRED/REJECTED."""
        cid = o.get("caid", "")
        hit = self.cids.get(cid)
        s = self.slots.get(hit[0]) if hit else None
        od = s.orders.get("es") if s is not None else None
        if od is None or od.cid != cid:
            return
        st = o.get("X", od.status)
        od.ack_ms = od.ack_ms or int(self.now_fn())
        if od.status not in ("FILLED", "PARTIALLY_FILLED") or st in ("CANCELED", "EXPIRED", "REJECTED"):
            od.status = st
        if st in ("TRIGGERING", "TRIGGERED", "EXPIRED", "REJECTED"):
            self._event("exec_stop", {"asset": s.asset, "cid": cid, "status": st, "order_id": o.get("ai"),
                                      "trigger": o.get("tp")})
            if st == "TRIGGERING":                          # sıra: TRIGGERING → dolumlar → TRIGGERED → FINISHED
                self.note(f"🧪🛑 TESTNET ACİL STOP TETİKLENDİ {s.asset} @ {o.get('tp')} (borsadaki emir) · "
                          f"pozisyon {s.pos:g}")
            elif st in ("EXPIRED", "REJECTED"):
                s.es_retry_ms = int(self.now_fn()) + self.es_retry_ms
        self._order_row(s, od, E, {"algo_status": st})
        self._drive(s, int(self.now_fn()))

    def _on_order(self, o: dict, E: int) -> None:
        cid, sym = o.get("c", ""), o.get("s")
        hit = self.cids.get(cid)
        if hit is None and (o.get("o") == "LIQUIDATION" or cid.startswith("autoclose")):
            a = next((s.asset for s in self.slots.values() if s.symbol == sym), None)
            hit = (a, "liq") if a else None
        if hit is None:
            return
        asset, kind = hit
        s = self.slots.get(asset)
        if s is None:
            return
        od = s.orders.get(kind)
        if od is not None and od.cid == cid:
            od.ack_ms = od.ack_ms or int(self.now_fn())
            od.status, od.order_id = o.get("X", od.status), o.get("i", od.order_id)
            od.filled = max(od.filled, float(o.get("z") or 0))
        if o.get("x") == "TRADE":
            l, L = float(o.get("l") or 0), float(o.get("L") or 0)
            fee = float(o.get("n") or 0)
            if o.get("N") not in (None, "USDT"):
                self._event("exec_fee_asset", {"asset": o.get("N"), "fee": fee})
            self._fill(s, kind, cid, l, L, fee, bool(o.get("m")), int(o.get("T") or E))
        if od is not None and od.cid == cid:
            self._order_row(s, od, E)
        self._drive(s, int(self.now_fn()))

    def _fill(self, s: Slot, kind: str, cid: str, l: float, L: float, fee: float, maker: bool, T: int) -> None:
        if l <= 0:
            return
        if kind == "en":
            s.q += l
            s.cost += l * L
            s.fee_in += fee
            s.entry_ms = s.entry_ms or T
        else:
            s.xq += l
            s.xn += l * L
            s.xfee += fee
        mid = self._real_mid(s.asset)
        side = "buy" if kind == "en" else "sell"
        bps = ((L / mid - 1) * 1e4 if side == "buy" else (1 - L / mid) * 1e4) if math.isfinite(mid) and mid > 0 else None
        self.rec.add("fills", fill_id=f"{cid}-{T}-{l}", order_id=cid, pos_id=s.pos_id, ts_ms=T, account=self.acc_id,
                     strategy=self.strat.name, venue="testnet", leverage=self.lev, asset=s.asset, side=side,
                     reason={"en": "entry", "tp": "tp", "liq": "liq", "es": "estop"}.get(kind, s.exit_reason),
                     liquidity="maker" if maker
                     else "taker", qty=l, notional=l * L, vwap=L, mid=mid, slippage_bps=bps, fee=fee,
                     fee_rate=fee / (l * L) if l * L > 0 else None, flags="testnet,vs_real_mid")
        if kind == "en" and s.state == "entry" and s.q >= s.target - EPS:
            self._finish_entry(s, int(self.now_fn()))
        elif kind != "en" and s.pos <= EPS and s.state != "closed":
            if kind in ("tp", "liq"):
                s.exit_reason = kind
            elif kind == "es":
                s.exit_reason = "estop"
            self._close(s, int(self.now_fn()))

    # --- mutabakat ---
    def reconcile(self) -> None:
        """Eşzamanlı (iş parçacığında): borsadaki pozisyon miktarı ve açık emirler ↔ bizim durum."""
        t_fetch = int(self.now_fn())
        prows = self.rest.positions()
        pos = {p["symbol"]: float(p.get("positionAmt") or 0) for p in prows}
        opened = {o["clientOrderId"] for o in self.rest.open_orders() if str(o.get("clientOrderId", "")).startswith("tn")}
        t0 = min((s.start_ms for s in self.slots.values()), default=None)
        fund = self.rest.income("FUNDING_FEE", t0) if t0 is not None else []
        algos = {str(o.get("clientAlgoId", "")): o.get("symbol") for o in self.rest.open_algo_orders()}
        return pos, opened, fund, self.rest.balance(), prows, algos, t_fetch

    def apply_reconcile(self, pos: dict, opened: set, fund: list | None = None, bal=None, prows=None,
                        algos: dict | None = None, t_fetch: int | None = None) -> None:
        if bal is not None:
            self._set_balance(bal, int(self.now_fn()))
        if prows is not None:
            self._check_leverage(prows, fix=True)
        for s in self.slots.values():                   # fonlama: borsanın gelir kaydı (sembol başına, + alınan)
            paid = -sum(float(r["income"]) for r in fund or [] if r.get("symbol") == s.symbol
                        and int(r.get("time") or 0) >= s.start_ms)
            if abs(paid - s.funding) > 1e-9:
                s.funding = paid
                self._pos_row(s, int(self.now_fn()))
        for s in list(self.slots.values()):
            if s.busy:
                continue
            for k, o in s.orders.items():
                # Yalnızca sorgu başlamadan önce borsanın kabul ettiği emir "borsada yok" sayılır. Yoksa yarış: sorgu
                # (iş parçacığı) → yeni emir → onay → uygulama, canlı emri GONE yapar → ikinci giriş emri → bütçe aşımı.
                before = o.ack_ms is not None and (t_fetch is None or o.ack_ms < t_fetch)
                if k == "es":                              # borsada yoksa (elle iptal, süresi bitti) → yeniden konur
                    if algos is not None and o.live and o.status == "NEW" and o.cid not in algos and before:
                        o.status = "GONE"
                        self._event("exec_stop", {"asset": s.asset, "cid": o.cid, "status": "GONE"})
                    continue
                if o.live and o.status != "sending" and o.cid not in opened and before:
                    o.status = "GONE"
            amt = pos.get(s.symbol, 0.0)
            step = self.filters[s.asset].step
            if abs(amt - s.pos) > step / 2:
                self._event("exec_mismatch", {"asset": s.asset, "exchange": amt, "ours": s.pos})
                self._resync(s)
        known = {o.cid for s in self.slots.values() for o in s.orders.values() if o.live}
        for cid in opened - known:
            hit = self.cids.get(cid)
            sym = self.filters[hit[0]].symbol if hit and hit[0] in self.filters else None
            if sym:
                self._call(None, "cancel stray", self.rest.cancel_order, sym, cid, err=self._quiet_unknown("stray"))
        ours = {f.symbol for f in self.filters.values()}
        for cid, sym in (algos or {}).items():           # sahipsiz acil stop (pozisyonu olmayan sembolde) → iptal
            if cid.startswith("tn") and sym in ours and cid not in known:
                self._event("exec_stop", {"cid": cid, "symbol": sym, "status": "stray_cancel"})
                self._call(None, "cancel stray es", self.rest.cancel_algo, cid, err=self._quiet_unknown("stray es"))
        for s in list(self.slots.values()):
            self._drive(s, int(self.now_fn()))

    def _quiet_unknown(self, label: str):
        def err(e: ExchangeError):
            if e.code not in (-2011, -2013):                 # zaten yok → sorun değil
                self._event("exec_error", {"call": f"cancel {label}", "error": str(e)})
        return err

    def _resync(self, s: Slot) -> None:
        """Bu slotun dolumlarını borsanın işlem geçmişinden (userTrades) yeniden kurar."""
        def ok(trades, dt):
            q = cost = fee = xq = xn = xfee = 0.0
            known_ids = {o.order_id for o in s.history if o.order_id is not None}
            mine = [t for t in trades if t.get("orderId") in known_ids
                    or (t.get("side") == "SELL" and int(t.get("time") or 0) >= s.start_ms)]   # likidasyon dahil
            for t in mine:
                l, L, n = float(t["qty"]), float(t["price"]), float(t.get("commission") or 0)
                if t.get("side") == "BUY":
                    q, cost, fee = q + l, cost + l * L, fee + n
                else:
                    xq, xn, xfee = xq + l, xn + l * L, xfee + n
            if q > 0:
                s.q, s.cost, s.fee_in = q, cost, fee
            s.xq, s.xn, s.xfee = xq, xn, xfee
            self._event("exec_resync", {"asset": s.asset, "trades": len(mine), "q": s.q, "xq": s.xq})
            if s.state in ("open", "exit") and s.pos <= EPS:
                s.exit_reason = s.exit_reason or "unknown"
                self._close(s, int(self.now_fn()))
        self._call(s, "userTrades", self.rest.user_trades, s.symbol, s.start_ms - 60_000, ok=ok)

    # --- kayıt ---
    def _order_row(self, s: Slot, o: Order, ts, extra: dict | None = None) -> None:
        typ = {"en": "limit_maker", "tp": "limit", "sx": "limit_maker", "mx": "market", "es": "stop_market"}[o.kind]
        reason = {"en": "entry", "tp": "tp", "es": "estop"}.get(o.kind, s.exit_reason)
        self.rec.add("paper_orders", order_id=o.cid, ts_ms=o.sent_ms, account=self.acc_id, strategy=self.strat.name,
                     venue="testnet", leverage=self.lev, asset=s.asset, side=o.side.lower(), type=typ, qty=o.qty,
                     notional=o.qty * o.price if math.isfinite(o.price) else None,
                     price=o.price if math.isfinite(o.price) else None, reason=reason, status=o.status,
                     pos_id=s.pos_id, updated_ms=int(ts),
                     detail={"order_id": o.order_id, "filled": o.filled, "latency_ms": o.latency_ms, **(extra or {})})

    def _pos_row(self, s: Slot, ts: int, pnl=None) -> None:
        self.rec.add("positions", pos_id=s.pos_id, account=self.acc_id, strategy=self.strat.name, venue="testnet",
                     leverage=self.lev, asset=s.asset, hour_ms=s.hour_ms, entry_ms=s.entry_ms or ts, p_in=s.p_in,
                     qty=s.q, margin=s.cost / self.lev, notional=s.cost, fee_in=s.fee_in, tp_px=s.tp_px, sl_px=s.sl_px,
                     liq_px=None, deadline_ms=s.deadline_ms, z=s.z, status="closed" if s.state == "closed" else "open",
                     exit_ms=s.exit_ms, p_out=s.xn / s.xq if s.xq > 0 else None, reason=s.exit_reason,
                     fee_out=s.xfee, funding=s.funding, exit_flow=None, pnl=pnl, flags=s.flags, updated_ms=int(ts),
                     x_qty=s.xq, x_notional=s.xn, x_fee=s.xfee)

    def snapshot(self, ts: int) -> None:
        eq, _ = self.equity()
        pv = 0.0
        for s in self.slots.values():
            px = self._real_mid(s.asset)
            pv += s.cost / self.lev + s.pos * ((px if math.isfinite(px) else s.p_in) - s.p_in) if s.pos > 0 else 0.0
        self.rec.add("equity", ts_ms=int(ts), account=self.acc_id, strategy=self.strat.name, venue="testnet",
                     leverage=self.lev, cash=eq - pv, pos_value=pv, equity=eq,
                     n_open=sum(1 for s in self.slots.values() if s.state != "entry"))

    def summary(self) -> str:
        eq, _ = self.equity()
        n = sum(1 for s in self.slots.values() if s.state != "entry")
        b = (f" · demo bakiye {self.bal['base']:.0f}$, bot payı %{self.frac * 100:g} = {self.bal['budget']:.0f}$, "
             f"kullanılan {self.locked():.0f}$") if self.bal else " · bakiye okunamadı"
        return f"🧪 testnet {self.lev:g}× {eq:.1f}" + (f" ({n} açık)" if n else "") + b


class UserStream:
    """Testnet kullanıcı veri akışı: listenKey, 30 dk'da bir yenileme, kopunca yeniden bağlanma + mutabakat."""

    def __init__(self, broker: TestnetBroker, ws_base: str, on_status=None):
        self.b, self.ws_base = broker, ws_base.rstrip("/")
        self.on_status = on_status or (lambda kind, detail: None)
        self.connected = False

    async def run(self, stop: asyncio.Event) -> None:
        import websockets  # noqa: PLC0415
        attempt = 0
        while not stop.is_set():
            try:
                lk = await asyncio.to_thread(self.b.rest.listen_key)
                async with websockets.connect(f"{self.ws_base}/ws/{lk}", ping_interval=20, ping_timeout=60,
                                              open_timeout=20, max_size=2 ** 22) as ws:
                    self.connected, attempt = True, 0
                    self.on_status("exec_stream", {"info": "connect"})
                    await reconcile_once(self.b)
                    last_ka = time.monotonic()
                    while not stop.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except TimeoutError:
                            raw = None
                        if raw is not None:
                            try:
                                self.b.on_user(json.loads(raw))
                            except Exception as e:  # noqa: BLE001
                                self.on_status("exec_error", {"call": "on_user", "error": repr(e)[:300]})
                        if time.monotonic() - last_ka > 1800:
                            await asyncio.to_thread(self.b.rest.keepalive)
                            last_ka = time.monotonic()
            except Exception as e:  # noqa: BLE001
                self.on_status("exec_stream", {"info": "disconnect", "error": repr(e)[:300]})
            self.connected = False
            if stop.is_set():
                break
            attempt += 1
            try:
                await asyncio.wait_for(stop.wait(), timeout=min(60.0, 2.0 ** attempt))
            except TimeoutError:
                pass


async def reconcile_once(b: TestnetBroker) -> None:
    try:
        b.apply_reconcile(*await asyncio.to_thread(b.reconcile))
    except Exception as e:  # noqa: BLE001
        b._event("exec_error", {"call": "reconcile", "error": repr(e)[:300]})


async def reconcile_loop(b: TestnetBroker, stop: asyncio.Event, every_s: float) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=every_s)
        except TimeoutError:
            await reconcile_once(b)


def make_broker(cfg, tn: dict, books, rec, symbols, root: Path, now_fn, log=None, note=None):
    """Anahtar dosyasından imzalı istemci ve yürütücü; anahtar yoksa (None, neden)."""
    p = Path(tn["env_file"])
    env = read_env(p if p.is_absolute() else root / p)
    key = env.get("BINANCE_TESTNET_API_KEY") or env.get("BINANCE_API_KEY", "")      # ayrı testnet satırı yoksa .env'deki
    secret = env.get("BINANCE_TESTNET_API_SECRET") or env.get("BINANCE_API_SECRET") or None
    pk = env.get("BINANCE_TESTNET_PRIVATE_KEY_PATH") or env.get("BINANCE_PRIVATE_KEY_PATH") or None
    if not key or not (secret or pk):
        return None, f"anahtar yok ({tn['env_file']})"
    rest = SignedRest(tn["rest"], key, secret, pk, clock=now_fn, recv_window=int(tn["recv_window_ms"]))
    return TestnetBroker(cfg, tn, books, rec, rest, symbols, now_fn=now_fn, log=log, note=note), None
