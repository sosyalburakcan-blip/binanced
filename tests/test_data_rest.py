"""REST istemcisi birim testleri (çevrimdışı): timeZone asla gönderilmez, ağırlık izleme, 429/418, sayfalama."""

import json
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest
import requests

from trend.config import load_settings
from trend.data.rest import IPBannedError, RestClient

DAY = 86_400_000


def _resp(status=200, body=None, headers=None):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(body if body is not None else []).encode()
    r.headers.update(headers or {})
    return r


def _kl(open_ms, unit_k=1):
    return [open_ms * unit_k, "1.0", "2.0", "0.5", "1.5", "10", (open_ms + DAY - 1) * unit_k, "15", 3, "5", "7.5", "0"]


class _Capture:
    """session.send yerine geçer; hazırlanmış istekleri kaydeder."""

    def __init__(self, responses):
        self.prepared: list[requests.PreparedRequest] = []
        self.responses = list(responses)

    def __call__(self, prep, **kw):
        self.prepared.append(prep)
        return self.responses.pop(0)


def _client(cap, limit=None):
    cfg = load_settings({"data": {"rest_klines_limit": limit}} if limit else None)
    c = RestClient(cfg)
    c.session.send = cap
    c._limits_loaded = True
    c.slept = []
    c._sleep = c.slept.append
    return c


def test_klines_never_sends_timezone():
    cap = _Capture([_resp(body=[_kl(1704067200000)])])
    c = _client(cap)
    df = c.klines("BTCUSDT", "1d", start="2024-01-01", closed_only=False)
    assert len(cap.prepared) == 1
    q = parse_qs(urlsplit(cap.prepared[0].url).query)
    assert "timeZone" not in q and not any(k.lower() == "timezone" for k in q)
    assert q["symbol"] == ["BTCUSDT"] and q["interval"] == ["1d"] and q["startTime"] == ["1704067200000"]
    assert cap.prepared[0].url.startswith(load_settings()["data"]["rest_base"])
    assert df["open_time"].iloc[0] == pd.Timestamp("2024-01-01")  # 00:00 UTC


def test_explicit_timezone_is_rejected():
    c = _client(_Capture([]))
    with pytest.raises(ValueError):
        c.get("/api/v3/klines", {"symbol": "BTCUSDT", "interval": "1d", "timeZone": "+3"})


def test_pagination_and_us_conversion():
    t0 = 1735689600000  # 2025-01-01
    pages = [[_kl(t0 + i * DAY) for i in range(2)], [_kl(t0 + 2 * DAY, unit_k=1000)]]  # ikinci sayfa µs
    cap = _Capture([_resp(body=pages[0]), _resp(body=pages[1])])
    df = _client(cap, limit=2).klines("BTCUSDT", "1d", start="2025-01-01", closed_only=False)
    assert len(cap.prepared) == 2
    assert parse_qs(urlsplit(cap.prepared[1].url).query)["startTime"] == [str(t0 + DAY + 1)]
    assert list(df["open_time"]) == list(pd.date_range("2025-01-01", periods=3, freq="D"))
    assert df["close_time"].iloc[2] == pd.Timestamp("2025-01-03 23:59:59.999")


def test_weight_pause_at_80_percent():
    c = _client(_Capture([_resp(body=[], headers={"X-MBX-USED-WEIGHT-1M": "4800"})]))
    c.weight_limit = 6000
    c.get("/api/v3/klines", {"symbol": "X", "interval": "1d"})
    assert len(c.slept) == 1 and 1 <= c.slept[0] <= 61
    c2 = _client(_Capture([_resp(body=[], headers={"X-MBX-USED-WEIGHT-1M": "4799"})]))
    c2.weight_limit = 6000
    c2.get("/api/v3/klines", {"symbol": "X", "interval": "1d"})
    assert c2.slept == []


def test_429_honors_retry_after_and_418_stops():
    c = _client(_Capture([_resp(429, headers={"Retry-After": "7"}), _resp(body=[])]))
    assert c.get("/api/v3/klines", {"symbol": "X", "interval": "1d"}).status_code == 200
    assert c.slept == [7]
    cap = _Capture([_resp(418), _resp(body=[])])
    c2 = _client(cap)
    with pytest.raises(IPBannedError):
        c2.get("/api/v3/klines", {"symbol": "X", "interval": "1d"})
    assert len(cap.prepared) == 1  # tekrar denenmez


def test_rate_limit_read_from_exchange_info():
    info = {"rateLimits": [{"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1,
                            "limit": 1200}, {"rateLimitType": "ORDERS", "interval": "SECOND", "intervalNum": 10,
                                             "limit": 50}]}
    c = _client(_Capture([_resp(body=info)]))
    c._limits_loaded = False
    c.exchange_info()
    assert c.weight_limit == 1200


def test_invalid_symbol_returns_empty():
    cap = _Capture([_resp(400, body={"code": -1121, "msg": "Invalid symbol."})])
    df = _client(cap).klines("NOPEUSDT", "1d", start="2024-01-01")
    assert df.empty and df["open_time"].dtype == "datetime64[ns]"
