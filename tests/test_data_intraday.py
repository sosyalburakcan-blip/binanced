"""Gün içi (15m) veri birim testleri: listeleme planı, vadeli çarpanı, bayat mum/fonlama kırpma, spot birleştirme,
zincir çakışması, bitiş kırpması, defterle kaldığı yerden devam (çevrimdışı; ağ yok)."""

import hashlib
import io
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trend import meta
from trend.config import load_settings
from trend.data import download as dl
from trend.data import intraday as it

FIX = Path(__file__).parent / "fixtures" / "intraday"
CFG = load_settings()
THR = int(CFG["data"]["timestamp_us_threshold"])

# fikstür dosyası → arşiv aynasındaki rel_path
LAYOUT = {
    "OLDUSDT-15m-2024-01.zip": "spot/monthly/klines/OLDUSDT/15m/OLDUSDT-15m-2024-01.zip",
    "NEWUSDT-15m-2024-02-01.zip": "spot/daily/klines/NEWUSDT/15m/NEWUSDT-15m-2024-02-01.zip",
    "OLDUSDTF-15m-2024-01.zip": "futures/um/monthly/klines/OLDUSDT/15m/OLDUSDT-15m-2024-01.zip",
    "1000NEWUSDT-15m-2024-02-01.zip": "futures/um/daily/klines/1000NEWUSDT/15m/1000NEWUSDT-15m-2024-02-01.zip",
    "OLDUSDT-fundingRate-2024-01.zip": "futures/um/monthly/fundingRate/OLDUSDT/OLDUSDT-fundingRate-2024-01.zip",
    "1000NEWUSDT-fundingRate-2024-02.zip":
        "futures/um/monthly/fundingRate/1000NEWUSDT/1000NEWUSDT-fundingRate-2024-02.zip",
}


def _raw(tmp_path: Path) -> it.Paths:
    paths = it.Paths(tmp_path / "intraday")
    for name, rel in LAYOUT.items():
        dest = paths.raw / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIX / name, dest)
    return paths


def _smap() -> pd.DataFrame:
    return pd.DataFrame([{"old_symbol": "OLDUSDT", "new_symbol": "NEWUSDT", "type": "REDENOM", "ratio": 10.0,
                          "old_last_trade_utc": "2024-01-31 23:00", "new_first_trade_utc": "2024-02-01 00:00",
                          "source": "test", "verified": "yes"}], columns=meta.SYMBOL_MAP_COLUMNS)


def _job(paths: it.Paths) -> it.AssetJob:
    files: dict = {}
    for rel in LAYOUT.values():
        sym = rel.split("/")[-2] if "fundingRate" in rel else rel.split("/")[-3]
        kind = "funding" if "fundingRate" in rel else ("spot" if rel.startswith("spot/") else "futures")
        files.setdefault((sym, kind), []).append(rel)
    return it.AssetJob("NEWUSDT", [("OLDUSDT", 10.0), ("NEWUSDT", 1.0)], [("OLDUSDT", 10.0), ("1000NEWUSDT", 1000.0)],
                       files, [], {}, _smap(), str(paths.root), THR)


# ------------------------------------------------------------------------------------------ uçtan uca
def test_build_asset_end_to_end(tmp_path):
    paths = _raw(tmp_path)
    res = it.build_asset(_job(paths))
    assert res["warnings"] == ["NEWUSDT spot: OLDUSDT: old_last_trade sonrasındaki 3 sıfır hacimli mum atıldı (15m)"]

    s = pd.read_parquet(paths.out("spot") / "NEWUSDT.parquet")
    assert list(s.columns) == it.OUT_COLS and str(s["open_time"].dtype) == "datetime64[ns]"
    assert s["open_time"].is_monotonic_increasing and s["open_time"].is_unique
    # OLD: 22:00..23:00 (old_last_trade sonrası 3 hacimsiz bayat mum 1d/1h kuralıyla atıldı), fiyat 100/10
    old = s[s["source_symbol"] == "OLDUSDT"]
    assert list(old["open_time"]) == list(pd.date_range("2024-01-31 22:00", "2024-01-31 23:00", freq="15min"))
    assert np.allclose(old["close"], 10.0) and np.allclose(old["volume"], 30.0)
    new = s[s["source_symbol"] == "NEWUSDT"]   # µs zaman damgası → doğru UTC
    assert list(new["open_time"]) == list(pd.date_range("2024-02-01 00:00", periods=8, freq="15min"))

    f = pd.read_parquet(paths.out("futures") / "NEWUSDT.parquet")
    fo, fn = f[f["source_symbol"] == "OLDUSDT"], f[f["source_symbol"] == "1000NEWUSDT"]
    # baştaki 2 ve sondaki 2 hacimsiz mum atıldı; aradaki hacimsiz mum (22:45) kaldı
    assert list(fo["open_time"]) == list(pd.date_range("2024-01-31 22:30", "2024-01-31 23:15", freq="15min"))
    assert fo["volume"].tolist() == [40.0, 0.0, 40.0, 40.0]
    # 1000NEWUSDT: fiyat ÷1000, hacim ×1000, quote hacim değişmez
    assert np.allclose(fn["close"], 10.0) and np.allclose(fn["volume"], 1000.0)
    assert np.allclose(fn["quote_volume"], 10000.0)

    r = pd.read_parquet(paths.out("funding") / "NEWUSDT.parquet")
    assert list(r.columns) == it.FUNDING_COLS
    assert r["funding_time"].tolist() == [pd.Timestamp("2024-01-31 23:00"), pd.Timestamp("2024-02-01 00:00"),
                                          pd.Timestamp("2024-02-01 01:00")]
    assert r["source_symbol"].tolist() == ["OLDUSDT", "1000NEWUSDT", "1000NEWUSDT"]
    assert r["funding_rate"].tolist() == [0.0002, -0.0005, 0.00025]

    row = res["row"]
    assert (row["spot_n_bars"], row["futures_n_bars"], row["funding_n_rows"]) == (13, 12, 3)
    assert row["spot_missing_bars"] == 3 and row["futures_multiplier"] == "10|1000"
    assert "÷1000" in row["notes"] and "işlem aralığı dışında 2 satır" in row["notes"]


def test_spot_segments_must_match_asset_segments(tmp_path):
    paths = _raw(tmp_path)
    job = _job(paths)
    job.spot = [("OLDUSDT", 1.0), ("NEWUSDT", 1.0)]  # oran asset_segments'ten farklı → hata
    with pytest.raises(ValueError, match="asset_segments"):
        it.build_asset(job)


def test_no_futures_asset(tmp_path):
    paths = _raw(tmp_path)
    job = _job(paths)
    job.futures = []
    res = it.build_asset(job)
    assert "vadeli kontrat yok" in res["row"]["notes"]
    assert not (paths.out("futures") / "NEWUSDT.parquet").exists()


# -------------------------------------------------------------------------------------------- okuma
def test_read_funding_rounds_and_reports_offset():
    df = it.read_funding_zip(FIX / "OLDUSDT-fundingRate-2024-01.zip", THR)
    assert df["funding_time"].tolist() == [pd.Timestamp("2024-01-31 16:00"), pd.Timestamp("2024-01-31 23:00"),
                                           pd.Timestamp("2024-02-01 00:00")]
    assert np.allclose(df["offset_s"], [0.004, 0.002, -0.002])


def test_read_funding_without_header():
    body = b"1704067200000,8,0.0001\n1704096000003,8,-0.0002\n"
    df = it.read_funding_csv(body, THR)
    assert df["funding_time"].tolist() == [pd.Timestamp("2024-01-01 00:00"), pd.Timestamp("2024-01-01 08:00")]
    assert df["funding_rate"].tolist() == [0.0001, -0.0002]


def test_load_klines_clips_at_end(tmp_path):
    rel = "futures/um/daily/klines/XUSDT/15m/XUSDT-15m-2026-11-01.zip"
    p = tmp_path / "raw" / rel
    p.parent.mkdir(parents=True)
    t0 = int(pd.Timestamp("2026-11-01 23:30").value // 10**6)
    rows = [f"{t0 + i * 900000},1,1,1,1,5,{t0 + (i + 1) * 900000 - 1},5,1,2,2,0" for i in range(3)]
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("XUSDT-15m-2026-11-01.csv", "\n".join(rows) + "\n")
    df, _ = it.load_klines([rel], tmp_path / "raw", "futures", "XUSDT", THR)
    assert df["open_time"].max() == it.END == pd.Timestamp("2026-11-01 23:45") and len(df) == 2


def test_trim_inactive_all_zero():
    df = pd.DataFrame({"open_time": pd.date_range("2024-01-01", periods=3, freq="15min"), "volume": [0.0] * 3})
    out, lead, trail = it.trim_inactive(df)
    assert out.empty and (lead, trail) == (3, 0)


# ------------------------------------------------------------------------------------------ zincirler
def _frame(start, n, close, sym):
    ot = pd.date_range(start, periods=n, freq="15min")
    return pd.DataFrame({"open_time": ot, "open": close, "high": close, "low": close, "close": close,
                         "volume": 1.0, "quote_volume": close, "source_symbol": sym})


def test_futures_chain_new_symbol_wins_on_overlap():
    frames = {"AUSDT": _frame("2024-01-01 00:00", 8, 1.0, "AUSDT"), "BUSDT": _frame("2024-01-01 01:00", 4, 2.0, "BUSDT")}
    w: list[str] = []
    df, segs = it._merge(["AUSDT", "BUSDT"], frames.__getitem__, it.chain_map([["AUSDT", "BUSDT"]]), w)
    assert df["open_time"].is_unique and len(df) == 8
    assert (df.loc[df["open_time"] >= "2024-01-01 01:00", "source_symbol"] == "BUSDT").all()
    assert [s["source_symbol"] for s in segs] == ["AUSDT", "BUSDT"] and any("çakışıyor" in x for x in w)


def test_futures_plan_prefixes_and_redenom():
    sources = {"SHIBUSDT": [("SHIBUSDT", 1.0)], "BTTCUSDT": [("BTTUSDT", 1000.0), ("BTTCUSDT", 1.0)],
               "TFUELUSDT": [("TFUELUSDT", 1.0)], "POLUSDT": [("MATICUSDT", 1.0), ("POLUSDT", 1.0)]}
    kl = {"1000SHIBUSDT", "BTTUSDT", "1000BTTCUSDT", "MATICUSDT", "POLUSDT", "SUSDT"}
    plan = it.futures_plan(sources, kl, {"1000SHIBUSDT", "POLUSDT"})
    m = dict(zip(plan["futures_symbol"], plan["multiplier"]))
    assert m == {"1000SHIBUSDT": 1000.0, "BTTUSDT": 1000.0, "1000BTTCUSDT": 1000.0, "MATICUSDT": 1.0, "POLUSDT": 1.0}
    assert "TFUELUSDT" not in set(plan["asset_id"])
    inv = pd.DataFrame({"symbol": ["POLUSDT", "MATICUSDT", "BTTUSDT", "1000BTTCUSDT", "1000SHIBUSDT"],
                        "kind": "futures", "period": ["2024-09", "2020-10", "2021-04", "2022-01", "2021-05"]})
    o = it.order_futures(plan, inv)
    assert o.loc[o["asset_id"] == "POLUSDT", "futures_symbol"].tolist() == ["MATICUSDT", "POLUSDT"]
    assert o.loc[o["asset_id"] == "BTTCUSDT", "futures_symbol"].tolist() == ["BTTUSDT", "1000BTTCUSDT"]


def test_spot_sources_from_segments():
    seg = pd.DataFrame({"asset_id": ["POLUSDT", "POLUSDT", "BTCUSDT"], "source_symbol": ["POLUSDT", "MATICUSDT", "BTCUSDT"],
                        "start": ["2024-09-13", "2019-04-26", "2017-08-17"], "end": "", "ratio": [1.0, 1.0, 1.0]})
    assert it.spot_sources(seg, ["POLUSDT", "BTCUSDT"])["POLUSDT"] == [("MATICUSDT", 1.0), ("POLUSDT", 1.0)]
    with pytest.raises(ValueError):
        it.spot_sources(seg, ["XUSDT"])


# ------------------------------------------------------------------------------------------ listeleme
def test_list_files_monthly_gap_and_tail(monkeypatch):
    base = "data/futures/um/monthly/klines/XUSDT/15m/"
    dbase = "data/futures/um/daily/klines/XUSDT/15m/"

    def c(k):
        return {"key": k, "size": 10, "last_modified": "2026-11-02T00:00:00Z"}

    listing = {
        base: [c(base + "XUSDT-15m-2026-08.zip"), c(base + "XUSDT-15m-2026-08.zip.CHECKSUM"),
               c(base + "XUSDT-15m-2026-10.zip"), c(base + "XUSDT-15m-2026-10.zip.CHECKSUM")],
        dbase + "XUSDT-15m-2026-09-": [c(dbase + "XUSDT-15m-2026-09-30.zip"), c(dbase + "XUSDT-15m-2026-09-30.zip.CHECKSUM")],
    }
    tail = [c(dbase + "XUSDT-15m-2026-11-01.zip"), c(dbase + "XUSDT-15m-2026-11-01.zip.CHECKSUM"),
            c(dbase + "XUSDT-15m-2026-11-02.zip")]
    calls = []

    def fake(prefix, cfg=None, marker=None, delimiter="/"):
        calls.append((prefix, marker))
        if marker:
            assert marker == dbase + "XUSDT-15m-2026-10-99"
            return it.s3.Listing([], tail)
        return it.s3.Listing([], listing.get(prefix, []))

    monkeypatch.setattr(it.s3, "list_bucket", fake)
    rows = it.list_files("futures", "XUSDT", CFG)
    rels = [r["rel_path"] for r in rows]
    assert rels == ["futures/um/monthly/klines/XUSDT/15m/XUSDT-15m-2026-08.zip",
                    "futures/um/monthly/klines/XUSDT/15m/XUSDT-15m-2026-10.zip",
                    "futures/um/daily/klines/XUSDT/15m/XUSDT-15m-2026-09-30.zip",
                    "futures/um/daily/klines/XUSDT/15m/XUSDT-15m-2026-11-01.zip"]  # 11-02 bitişten sonra
    assert rows[0]["url"] == "https://data.binance.vision/data/" + rels[0]
    assert all(r["has_checksum"] for r in rows)
    assert {r["freq"] for r in rows} == {"monthly", "daily"} and {r["kind"] for r in rows} == {"futures"}


def test_listing_gaps():
    inv = pd.DataFrame({"symbol": "XUSDT", "kind": "spot", "period": ["2024-01", "2024-04", "2024-03-05"]})
    assert it.listing_gaps(inv, "XUSDT", "spot") == ["2024-02"]


def test_gap_stats_and_zero_runs():
    t = pd.Series(list(pd.date_range("2024-01-01", periods=4, freq="15min"))
                  + [pd.Timestamp("2024-01-03 00:00")])
    g = it.gap_stats(t)
    assert g["missing"] == int((pd.Timestamp("2024-01-03") - pd.Timestamp("2024-01-01 00:45")) / it.STEP) - 1
    assert len(g["long"]) == 1
    df = pd.DataFrame({"open_time": pd.date_range("2024-01-01", periods=200, freq="15min"),
                       "volume": [1.0] * 50 + [0.0] * 100 + [1.0] * 50})
    assert it.zero_volume_runs(df) == ["2024-01-01 12:30→2024-01-02 13:15 (100 mum)"]


# ------------------------------------------------------------------------------------- indirme/devam
def test_download_resumes_from_ledger(tmp_path, monkeypatch):
    paths = it.Paths(tmp_path / "intraday")
    body = (FIX / "OLDUSDT-fundingRate-2024-01.zip").read_bytes()
    rel = LAYOUT["OLDUSDT-fundingRate-2024-01.zip"]
    inv = pd.DataFrame([{"rel_path": rel, "url": "https://data.binance.vision/data/" + rel, "size_bytes": len(body),
                         "last_modified": "", "symbol": "OLDUSDT", "kind": "funding", "freq": "monthly",
                         "period": "2024-01", "has_checksum": True}], columns=it.INVENTORY_COLS)
    calls = []

    class R:
        def __init__(self, b):
            self.content, self.status_code, self.text = b, 200, b.decode(errors="replace")

        def raise_for_status(self):
            pass

    def get(url, **kw):
        calls.append(url)
        if url.endswith(".CHECKSUM"):
            return R(f"{hashlib.sha256(body).hexdigest()}  x.zip\n".encode())
        return R(body)

    monkeypatch.setattr(dl._http, "get", get)
    st = it.download_files(inv, paths, CFG)
    assert st["ok"] == 1 and (paths.raw / rel).read_bytes() == body
    led = dl.read_ledger(paths.ledger)
    assert led["status"].tolist() == ["ok"] and list(led.columns) == dl.LEDGER_COLS
    n = len(calls)
    st2 = it.download_files(inv, paths, CFG)
    assert st2["todo"] == 0 and len(calls) == n
    assert it.ok_files(inv, paths)["status"].tolist() == ["ok"]


def test_constants():
    assert len(it.ASSETS) == 57 and len(set(it.ASSETS)) == 57
    assert it.INTERVAL_STEP["15m"] == pd.Timedelta(minutes=15)
    assert it.archive_root(CFG) == "https://data.binance.vision/data"


def test_off_grid_reported():
    t = pd.Series([pd.Timestamp("2018-02-09 09:45"), pd.Timestamp("2018-02-09 09:58:14.789"),
                   pd.Timestamp("2018-02-09 10:13:14.789")])
    notes = it.off_grid(pd.DataFrame({"open_time": t}), "spot")
    assert notes == ["spot ızgara dışı open_time 2 mum (2018-02-09 09:58→2018-02-09 10:13)"]
