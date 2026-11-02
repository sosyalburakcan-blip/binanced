"""Binance REST istemcisi — yalnız piyasa verisi (`data.rest_base` = https://data-api.binance.vision).

Kullanım: günlük güncelleme ve G4 çapraz kontrolü. Kurallar (SPEC "REST API"):
- `GET /api/v3/klines` istek başına en fazla `data.rest_klines_limit` (1000) mum; sayfalama startTime ile.
- `X-MBX-USED-WEIGHT-1M` izlenir; limitin `data.rest_weight_pause_frac` (%80) oranına ulaşınca bir sonraki dakika
  başına kadar beklenir. Limit `exchangeInfo.rateLimits`'ten (REQUEST_WEIGHT / MINUTE / 1) okunur, okunamazsa
  `data.rest_weight_limit_default`.
- 429'da `Retry-After` kadar beklenip tekrar denenir; 418 (IP yasağı) → `IPBannedError`, hiç tekrar yok.
- `timeZone` parametresi **asla** gönderilmez (günlük mumlar UTC 00:00'da açılır); gönderilmeye çalışılırsa hata.
- Zaman damgaları `clean.normalize` ile aynı kuralla çevrilir (REST varsayılan ms döndürür; >1e14 ise µs).

G1 bulgusu: data-api.binance.vision delist edilmiş çiftler için de (ör. MATICUSDT, BTCBUSD) klines döndürüyor;
yani SPEC'teki "exchangeInfo'dan kaldırılınca veri alınamaz" bu uç nokta için 2026-11-02'de geçerli değil.
"""

from __future__ import annotations

import time

import pandas as pd
import requests

from trend.config import load_settings
from trend.data.clean import KLINE_COLS, normalize

MAX_429_RETRIES = int(load_settings()["data"]["rest_max_429_retries"])


class IPBannedError(RuntimeError):
    """HTTP 418: IP yasaklandı — tüm REST çağrıları durur."""


class RestClient:
    def __init__(self, cfg: dict | None = None, session: requests.Session | None = None):
        cfg = cfg or load_settings()
        d = cfg["data"]
        self.base = d["rest_base"].rstrip("/")
        self.limit = int(d["rest_klines_limit"])
        self.pause_frac = float(d["rest_weight_pause_frac"])
        self.weight_limit = int(d["rest_weight_limit_default"])
        self.threshold = int(d["timestamp_us_threshold"])
        self.max_retries = int(d["max_retries"])
        self.backoff = float(d["backoff_base_s"])
        self.session = session or requests.Session()
        self.used_weight = 0
        self._limits_loaded = False
        self._sleep = time.sleep  # testlerde değiştirilebilir

    # ------------------------------------------------------------------------------------- çekirdek istek
    def get(self, endpoint: str, params: dict | None = None) -> requests.Response:
        params = dict(params or {})
        if any(k.lower() == "timezone" for k in params):
            raise ValueError("timeZone parametresi gönderilmez (SPEC: günlük mumlar UTC 00:00)")
        req = self.session.prepare_request(requests.Request("GET", self.base + endpoint, params=params))
        n429 = nerr = 0
        while True:
            try:
                r = self.session.send(req, timeout=(10, 30))
            except requests.RequestException:
                if nerr >= self.max_retries:
                    raise
                self._sleep(self.backoff * 2**nerr)
                nerr += 1
                continue
            self._track_weight(r)
            if r.status_code == 418:
                raise IPBannedError(f"418 IP yasağı: {r.text[:200]}")
            if r.status_code == 429:
                if n429 >= MAX_429_RETRIES:
                    r.raise_for_status()
                wait_s = int(r.headers.get("Retry-After", "60"))
                self._sleep(wait_s)
                n429 += 1
                continue
            if r.status_code >= 500 and nerr < self.max_retries:
                self._sleep(self.backoff * 2**nerr)
                nerr += 1
                continue
            return r

    def _track_weight(self, r: requests.Response) -> None:
        w = r.headers.get("X-MBX-USED-WEIGHT-1M")
        if w is None:
            return
        self.used_weight = int(w)
        if self.used_weight >= self.pause_frac * self.weight_limit:
            # Dakikalık pencere dakika başında sıfırlanır; bir sonraki dakika başı + 1 sn beklenir.
            self._sleep(60 - time.time() % 60 + 1)
            self.used_weight = 0

    # ---------------------------------------------------------------------------------------- uç noktalar
    def exchange_info(self, **params) -> dict:
        r = self.get("/api/v3/exchangeInfo", params)
        r.raise_for_status()
        info = r.json()
        self._load_limits(info)
        return info

    def _load_limits(self, info: dict) -> None:
        for rl in info.get("rateLimits", []):
            if rl.get("rateLimitType") == "REQUEST_WEIGHT" and rl.get("interval") == "MINUTE" \
                    and int(rl.get("intervalNum", 0)) == 1:
                self.weight_limit = int(rl["limit"])
        self._limits_loaded = True

    def ensure_limits(self) -> None:
        """Gerçek ağırlık limitini bir kez exchangeInfo'dan okur (hata olursa varsayılan kalır)."""
        if not self._limits_loaded:
            try:
                self.exchange_info(symbol="BTCUSDT")
            except (requests.RequestException, ValueError):
                self._limits_loaded = True

    def klines_raw(self, symbol: str, interval: str, start_ms: int | None = None,
                   end_ms: int | None = None) -> list[list]:
        """Klines (ham liste). startTime/endTime dahil. `start_ms` yoksa tek istek (end'e kadarki son `limit` mum);
        varsa startTime ileri kaydırılarak sayfalanır. Geçersiz/bilinmeyen sembol (HTTP 400) → boş liste."""
        self.ensure_limits()
        out: list[list] = []
        cur = start_ms
        while True:
            p = {"symbol": symbol, "interval": interval, "limit": self.limit}
            if cur is not None:
                p["startTime"] = int(cur)
            if end_ms is not None:
                p["endTime"] = int(end_ms)
            r = self.get("/api/v3/klines", p)
            if r.status_code == 400:  # ör. {"code":-1121,"msg":"Invalid symbol."}
                return out
            r.raise_for_status()
            rows = r.json()
            out += rows
            if start_ms is None or len(rows) < self.limit:
                return out
            cur = int(rows[-1][0]) + 1
            if end_ms is not None and cur > end_ms:
                return out

    def klines(self, symbol: str, interval: str, start=None, end=None, closed_only: bool = True) -> pd.DataFrame:
        """Klines → temiz şema (CONTRACTS §3; half_day=False — REST yarım gün işaretlemez).
        `start`/`end`: tz-naive UTC zaman (open_time aralığı, dahil). REST henüz kapanmamış güncel mumu da döndürür;
        `closed_only=True` iken close_time'ı şimdiden sonra olan mum atılır."""
        def to_ms(t):
            return None if t is None else int(pd.Timestamp(t).value // 1_000_000)

        rows = self.klines_raw(symbol, interval, to_ms(start), to_ms(end))
        raw = pd.DataFrame(rows, columns=KLINE_COLS)
        raw = raw.astype({c: ("int64" if c in ("open_time", "close_time", "number_of_trades") else "float64")
                          for c in KLINE_COLS[:11]})
        df = normalize(raw, self.threshold)
        if closed_only:
            df = df[df["close_time"] < pd.Timestamp.now(tz="UTC").tz_localize(None)]
        return df.drop_duplicates("open_time").sort_values("open_time", ignore_index=True)
