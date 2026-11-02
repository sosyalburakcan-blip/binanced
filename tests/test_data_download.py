"""G2 birim testleri: CHECKSUM, defter, yeniden indirme kuralı, idempotent plan (çevrimdışı)."""

import hashlib

import pandas as pd
import pytest

from trend.config import load_settings
from trend.data import download as dl

D = load_settings()["data"]
URL = "https://data.binance.vision/data/spot/monthly/klines/AAAUSDT/1d/AAAUSDT-1d-2024-01.zip"
REL = "monthly/klines/AAAUSDT/1d/AAAUSDT-1d-2024-01.zip"


class _Resp:
    def __init__(self, body: bytes = b"", status=200):
        self.content, self.status_code = body, status
        self.text = body.decode(errors="replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))


def _fake(monkeypatch, bodies: list[bytes], checksum: bytes | None, zip_status=200):
    """Her zip isteğinde `bodies` sırayla döner; çağrı sayısı döndürülen listeye yazılır."""
    calls = []

    def get(url, **kw):
        if url.endswith(".CHECKSUM"):
            calls.append("checksum")
            return _Resp(checksum, 200) if checksum is not None else _Resp(b"", 404)
        calls.append("zip")
        if zip_status != 200:
            return _Resp(b"", zip_status)
        return _Resp(bodies[min(len([c for c in calls if c == "zip"]) - 1, len(bodies) - 1)])

    monkeypatch.setattr(dl._http, "get", get)
    return calls


def _ck(body: bytes) -> bytes:
    return f"{hashlib.sha256(body).hexdigest()}  AAAUSDT-1d-2024-01.zip\n".encode()


def test_parse_checksum():
    h = "a" * 64
    assert dl.parse_checksum(f"{h.upper()}  file.zip\n") == h
    with pytest.raises(ValueError):
        dl.parse_checksum("<html>not found</html>")


def test_fetch_ok(tmp_path, monkeypatch):
    calls = _fake(monkeypatch, [b"good"], _ck(b"good"))
    row = dl.fetch_one(REL, URL, tmp_path, D)
    assert row["status"] == "ok" and row["sha256_actual"] == row["sha256_expected"] and row["size_bytes"] == 4
    assert (tmp_path / REL).read_bytes() == b"good" and sorted(calls) == ["checksum", "zip"]
    assert set(row) == set(dl.LEDGER_COLS)


def test_mismatch_redownloads_once_then_reports(tmp_path, monkeypatch):
    calls = _fake(monkeypatch, [b"bad1", b"bad2", b"good"], _ck(b"good"))
    row = dl.fetch_one(REL, URL, tmp_path, D)
    assert row["status"] == "checksum_mismatch" and calls.count("zip") == 2


def test_mismatch_then_ok(tmp_path, monkeypatch):
    calls = _fake(monkeypatch, [b"bad", b"good"], _ck(b"good"))
    assert dl.fetch_one(REL, URL, tmp_path, D)["status"] == "ok" and calls.count("zip") == 2


def test_404_is_missing_remote_without_retry(tmp_path, monkeypatch):
    calls = _fake(monkeypatch, [b""], _ck(b"x"), zip_status=404)
    assert dl.fetch_one(REL, URL, tmp_path, D)["status"] == "missing_remote" and calls.count("zip") == 1


def test_missing_checksum_is_error(tmp_path, monkeypatch):
    _fake(monkeypatch, [b"good"], None)
    assert dl.fetch_one(REL, URL, tmp_path, D)["status"] == "error"


def test_valid_local_file_is_not_downloaded(tmp_path, monkeypatch):
    (tmp_path / REL).parent.mkdir(parents=True)
    (tmp_path / REL).write_bytes(b"good")
    calls = _fake(monkeypatch, [b"other"], _ck(b"good"))
    assert dl.fetch_one(REL, URL, tmp_path, D)["status"] == "ok" and calls == ["checksum"]


def _row(rel, status="ok", size=4):
    return {"rel_path": rel, "url": "u/" + rel, "sha256_expected": "e", "sha256_actual": "a", "size_bytes": size,
            "downloaded_at_utc": "2026-01-01T00:00:00Z", "status": status}


def test_ledger_append_compact_and_partial_line(tmp_path):
    p = tmp_path / "ledger.csv"
    lg = dl.Ledger(p)
    lg.put(_row("a.zip", "error"))
    lg.put(_row("a.zip", "ok"))
    lg.put(_row("b.zip", "missing_remote"))
    lg._fh.close()  # kapanmadan "çöktü"
    with open(p, "a", encoding="utf-8") as f:
        f.write("c.zip,u,e")  # yarım satır
    df = dl.read_ledger(p)
    assert df["rel_path"].tolist() == ["a.zip", "b.zip"] and df.loc[0, "status"] == "ok"
    lg2 = dl.Ledger(p)
    lg2.close()
    assert len(pd.read_csv(p)) == 2 and list(pd.read_csv(p).columns) == dl.LEDGER_COLS


def test_plan_skips_ok_and_detects_changes(tmp_path):
    raw = tmp_path / "raw"
    for rel in ["x/a.zip", "x/b.zip"]:
        (raw / rel).parent.mkdir(parents=True, exist_ok=True)
        (raw / rel).write_bytes(b"1234")
    lg = dl.Ledger(tmp_path / "ledger.csv")
    lg.put(_row("x/a.zip", "ok"))
    lg.put(_row("x/b.zip", "ok"))
    lg.put(_row("x/c.zip", "checksum_mismatch"))
    inv = pd.DataFrame({"rel_path": ["x/a.zip", "x/b.zip", "x/c.zip", "x/d.zip"], "size_bytes": [4, 5, 4, 4]})
    todo = dl.plan(inv, lg, raw)
    lg.close()
    # a: ok ve aynı boyut → atla; b: S3 boyutu değişti → indir; c: başarısız → indir; d: yeni → indir
    assert todo["rel_path"].tolist() == ["x/b.zip", "x/c.zip", "x/d.zip"]


def test_run_then_rerun_downloads_nothing(tmp_path, monkeypatch):
    _fake(monkeypatch, [b"good"], _ck(b"good"))
    lg = dl.Ledger(tmp_path / "ledger.csv")
    st = dl.run([(REL, URL, 4)], lg, tmp_path / "raw", load_settings())
    assert st["ok"] == 1 and not st["interrupted"]
    inv = pd.DataFrame({"rel_path": [REL], "size_bytes": [4]})
    assert dl.plan(inv, lg, tmp_path / "raw").empty
    lg.close()


def test_filter_inventory_since_until():
    inv = pd.DataFrame({"symbol": ["A", "A", "B"], "interval": ["1d", "1h", "1d"],
                        "period": ["2023-12", "2024-02-03", "2024-05"]})
    assert len(dl.filter_inventory(inv, since="2024-01")) == 2
    assert dl.filter_inventory(inv, symbols=["A"], intervals=["1h"])["period"].tolist() == ["2024-02-03"]
    assert dl.filter_inventory(inv, until="2024-02")["period"].tolist() == ["2023-12", "2024-02-03"]
