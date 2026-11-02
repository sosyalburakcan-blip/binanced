"""G1 birim testleri: sonek ayrıştırma, gereken çift seti, S3 XML sayfalama (çevrimdışı)."""

import pytest

from trend.config import load_settings
from trend.data import s3

CFG = load_settings()
OQ = CFG["data"]["other_quotes"]


@pytest.mark.parametrize("sym,quote", [
    ("BTCUSDT", "USDT"), ("BUSDUSDT", "USDT"), ("USDCUSDT", "USDT"), ("FDUSDUSDT", "USDT"), ("TUSDUSDT", "USDT"),
    ("XUSDCUSDT", "USDT"),  # USDT ile bitiyor → USDT önce
    ("BTCBUSD", "BUSD"), ("BTCFDUSD", "FDUSD"), ("BTCTUSD", "TUSD"), ("BTCUSDC", "USDC"),
    ("USDTBUSD", "BUSD"), ("TUSDBUSD", "BUSD"), ("FDUSDUSDC", "USDC"),
    ("USDTTRY", None), ("BTCUSDS", None), ("ETHBTC", None), ("BNBETH", None), ("USDT", None), ("BUSD", None),
])
def test_parse_quote(sym, quote):
    assert s3.parse_quote(sym, OQ) == quote


def test_exchange_info_quote_overrides_suffix_rule():
    tq = {"BNBUSD": "USD", "USDTUSD": "USD", "BTCBUSD": "BUSD", "ETHBTC": "BTC"}
    assert s3.parse_quote("BNBUSD", OQ) == "BUSD"  # sonek kuralının bilinen hatası
    assert s3.resolve_quote("BNBUSD", OQ, tq) is None and s3.resolve_quote("USDTUSD", OQ, tq) is None
    assert s3.resolve_quote("BTCBUSD", OQ, tq) == "BUSD"
    assert s3.resolve_quote("USDSTUSD", OQ, tq) == "TUSD"  # exchangeInfo'da yok → sonek kuralı
    assert not s3.needed_pairs(["BNBUSD", "USDTUSD"], CFG, tq)


def test_needed_pairs_intervals():
    p = s3.needed_pairs(["BTCUSDT", "BTCBUSD", "USDCUSDT", "ETHBTC", "BTCFDUSD"], CFG)
    assert ("BTCUSDT", "USDT", "1d") in p and ("BTCUSDT", "USDT", "1h") in p
    assert ("BTCBUSD", "BUSD", "1d") in p and ("BTCBUSD", "BUSD", "1h") not in p
    assert ("USDCUSDT", "USDT", "1d") in p
    assert not any(s == "ETHBTC" for s, _, _ in p)
    assert len(p) == len(set(p))


def test_validate_against_exchange_info():
    ex = {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT"},
                      {"symbol": "ABUSD", "baseAsset": "AB", "quoteAsset": "USD"},  # kural BUSD sanır
                      {"symbol": "ETHBTC", "baseAsset": "ETH", "quoteAsset": "BTC"}]}
    bad = s3.validate_against_exchange_info(["BTCUSDT", "ABUSD", "ETHBTC"], ex, OQ)
    assert bad["symbol"].tolist() == ["ABUSD"]


class _Resp:
    def __init__(self, body: str, status=200):
        self.content = body.encode()
        self.text = body
        self.status_code = status

    def raise_for_status(self):
        pass


def _page(prefixes, keys, truncated, next_marker=None):
    ns = 'xmlns="http://s3.amazonaws.com/doc/2006-03-01/"'
    nm = f"<NextMarker>{next_marker}</NextMarker>" if next_marker else ""
    cp = "".join(f"<CommonPrefixes><Prefix>{p}</Prefix></CommonPrefixes>" for p in prefixes)
    ct = "".join(f"<Contents><Key>{k}</Key><LastModified>2024-01-01T00:00:00.000Z</LastModified>"
                 f"<Size>{n}</Size></Contents>" for k, n in keys)
    return (f'<?xml version="1.0"?><ListBucketResult {ns}><IsTruncated>{str(truncated).lower()}</IsTruncated>'
            f"{nm}{cp}{ct}</ListBucketResult>")


def test_list_bucket_paginates_with_next_marker(monkeypatch):
    root = "data/spot/monthly/klines/"
    pages = {None: _page([root + "AAAUSDT/", root + "BBBUSDT/"], [], True, root + "BBBUSDT/"),
             root + "BBBUSDT/": _page([root + "CCCUSDT/"], [], False)}
    seen = []

    def fake_get(url, params=None, **kw):
        seen.append(params.get("marker"))
        return _Resp(pages[params.get("marker")])

    monkeypatch.setattr(s3._http, "get", fake_get)
    assert s3.list_symbols(root, CFG) == ["AAAUSDT", "BBBUSDT", "CCCUSDT"]
    assert seen == [None, root + "BBBUSDT/"]


def test_list_bucket_without_next_marker_uses_last_key(monkeypatch):
    k = "data/spot/monthly/klines/A/1d/A-1d-2024-0{}.zip"
    pages = {None: _page([], [(k.format(1), 10), (k.format(2), 20)], True),
             k.format(2): _page([], [(k.format(3), 30)], False)}
    monkeypatch.setattr(s3._http, "get", lambda url, params=None, **kw: _Resp(pages[params.get("marker")]))
    lst = s3.list_bucket("data/spot/monthly/klines/A/1d/", cfg=CFG)
    assert [c["size"] for c in lst.contents] == [10, 20, 30]


def test_list_pair_daily_tail_marker_and_gaps(monkeypatch):
    mroot = "data/spot/monthly/klines/A/1d/"
    droot = "data/spot/daily/klines/A/1d/"
    calls = []

    def fake_get(url, params=None, **kw):
        calls.append((params["prefix"], params.get("marker")))
        if params["prefix"] == mroot:
            keys = []
            for m in ["2024-01", "2024-03"]:  # 2024-02 boş ay
                keys += [(f"{mroot}A-1d-{m}.zip", 100), (f"{mroot}A-1d-{m}.zip.CHECKSUM", 88)]
            return _Resp(_page([], keys, False))
        if params["prefix"] == f"{droot}A-1d-2024-02-":
            return _Resp(_page([], [(f"{droot}A-1d-2024-02-10.zip", 5)], False))
        if params.get("marker") == f"{droot}A-1d-2024-03-99":
            return _Resp(_page([], [(f"{droot}A-1d-2024-04-01.zip", 6), (f"{droot}A-1d-2024-04-01.zip.CHECKSUM", 88)],
                               False))
        raise AssertionError(params)

    monkeypatch.setattr(s3._http, "get", fake_get)
    rows, gaps = s3.list_pair("A", "1d", CFG, latest_month="2024-03")
    assert gaps == ["2024-02"]
    got = {(r["kind"], r["period"], r["has_checksum"]) for r in rows}
    assert got == {("monthly", "2024-01", True), ("monthly", "2024-03", True), ("daily", "2024-02-10", False),
                   ("daily", "2024-04-01", True)}
    assert all(r["rel_path"].startswith(("monthly/klines/A/1d/", "daily/klines/A/1d/")) for r in rows)
    assert rows[0]["url"].startswith(CFG["data"]["archive_base"] + "/")
    # delist edilmiş çift (son aylık ay global son aydan 1+ ay eski) → kuyruk listelenmez
    calls.clear()
    s3.list_pair("A", "1d", CFG, latest_month="2024-09")
    assert not any(m for _, m in calls)
