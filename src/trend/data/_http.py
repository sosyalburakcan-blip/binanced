"""Ortak HTTP yardımcıları: iş parçacığı başına oturum ve artan beklemeli yeniden deneme."""

from __future__ import annotations

import random
import sys
import threading
import time

import requests
from requests.adapters import HTTPAdapter

from trend.config import load_settings

_local = threading.local()

# 404/403: uzak dosya yok (CloudFront/S3 eksik anahtar için ikisini de dönebilir) → yeniden deneme yapılmaz.
NOT_FOUND = (403, 404)
RETRY_STATUS = (429, 500, 502, 503, 504)
TIMEOUT_S = tuple(load_settings()["data"]["http_timeout_s"])  # (bağlantı, okuma)


def utf8_stdout() -> None:
    """CLI çıktısı dosyaya yönlendirildiğinde Windows'ta cp1254 yerine UTF-8 yazılsın."""
    for st in (sys.stdout, sys.stderr):
        if hasattr(st, "reconfigure"):
            st.reconfigure(encoding="utf-8", errors="replace")


def session(pool: int = 16) -> requests.Session:
    """İş parçacığına özel requests oturumu (Session thread-safe değildir)."""
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        ad = HTTPAdapter(pool_connections=pool, pool_maxsize=pool)
        s.mount("https://", ad)
        s.mount("http://", ad)
        s.headers["User-Agent"] = "trend-research/0.1"
        _local.session = s
    return s


def backoff_sleep(attempt: int, base_s: float) -> None:
    """Üstel bekleme: base × 2^attempt, %25 rastgele sapma (eşzamanlı yeniden denemeler yığılmasın)."""
    d = base_s * (2**attempt)
    time.sleep(d * (1 + 0.25 * random.random()))


def get(url: str, *, params: dict | None = None, max_retries: int = 5, backoff_base_s: float = 1.0,
        stream: bool = False) -> requests.Response:
    """GET; ağ hatası ve 429/5xx'te yeniden dener. 404/403 ve diğer 4xx yanıtları olduğu gibi döner.
    Son denemede de ağ hatası varsa istisna yükseltir."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            r = session().get(url, params=params, timeout=TIMEOUT_S, stream=stream)
        except requests.RequestException as e:
            last_exc = e
        else:
            if r.status_code not in RETRY_STATUS:
                return r
            last_exc = requests.HTTPError(f"HTTP {r.status_code} {url}", response=r)
            ra = r.headers.get("Retry-After")
            r.close()
            if ra and ra.isdigit() and attempt < max_retries:
                time.sleep(int(ra))
                continue
        if attempt < max_retries:
            backoff_sleep(attempt, backoff_base_s)
    assert last_exc is not None
    raise last_exc
