"""G3 birim testleri: ms/µs dönüşümü, UTC 00:00 hizası, tekrarlar, yarım gün, belirlenimci hash."""

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trend.config import load_settings
from trend.data import clean
from trend.data.download import LEDGER_COLS

FIX = Path(__file__).parent / "fixtures" / "data"
THR = load_settings()["data"]["timestamp_us_threshold"]
DAY_MS = 86_400_000


def _row(open_ms, close=1.0, unit="ms", vol=10.0):
    k = 1000 if unit == "us" else 1
    return [open_ms * k, close, close + 1, close - 0.5, close, vol, (open_ms + DAY_MS - 1) * k, vol * close, 7,
            vol / 2, vol * close / 2, 0]


def _csv(rows, header=False) -> bytes:
    s = io.StringIO()
    if header:
        s.write(",".join(clean.KLINE_COLS) + "\n")
    for r in rows:
        s.write(",".join(str(x) for x in r) + "\n")
    return s.getvalue().encode()


def _zip(p: Path, rows, header=False):
    p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(p.name.replace(".zip", ".csv"), _csv(rows, header))


def _ms(ts: str) -> int:
    return int(pd.Timestamp(ts).value // 1_000_000)


# ------------------------------------------------------------------------------------------------ zaman
def test_ms_and_us_both_sides_of_2025():
    vals = [_ms("2024-12-31"), _ms("2024-12-31") + DAY_MS - 1,             # ms (2024)
            _ms("2025-01-01") * 1000, (_ms("2025-01-01") + DAY_MS - 1) * 1000 + 999]  # µs (2025)
    got = clean.ts_to_datetime(vals, THR)
    assert got.dtype == np.dtype("datetime64[ns]")
    assert list(pd.DatetimeIndex(got)) == [pd.Timestamp("2024-12-31"), pd.Timestamp("2024-12-31 23:59:59.999"),
                                           pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-01 23:59:59.999")]
    # Eşik: 1e14 ms ≈ 5138 yılı; ms değerleri asla eşiği geçmez, µs değerleri 1973'ten beri geçer.
    assert _ms("2100-01-01") < THR < _ms("1974-01-01") * 1000


def test_real_archive_files_across_us_switch():
    """Gerçek arşiv örnekleri: BTCUSDT 1d 2024-12 (ms) ve 2025-01 (µs) → kesintisiz, UTC 00:00 hizalı günler."""
    df24 = clean.normalize(clean.read_zip(FIX / "BTCUSDT-1d-2024-12.zip"), THR)
    df25 = clean.normalize(clean.read_zip(FIX / "BTCUSDT-1d-2025-01.zip"), THR)
    raw25 = clean.read_zip(FIX / "BTCUSDT-1d-2025-01.zip")
    assert raw25["open_time"].min() > THR  # 2025 dosyası gerçekten µs
    assert clean.read_zip(FIX / "BTCUSDT-1d-2024-12.zip")["open_time"].max() < THR
    both = pd.concat([df24, df25], ignore_index=True)
    idx = pd.DatetimeIndex(both["open_time"])
    assert (idx == pd.date_range("2024-12-01", "2025-01-31", freq="D")).all()
    assert (idx == idx.normalize()).all()  # günlük mumlar 00:00 UTC
    assert (both["close_time"] == both["open_time"] + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)).all()


def test_daily_candles_align_to_midnight_utc(tmp_path):
    rows = [_row(_ms("2024-12-30")), _row(_ms("2024-12-31")), _row(_ms("2025-01-01"), unit="us")]
    _zip(tmp_path / "x.zip", rows)
    df = clean.normalize(clean.read_zip(tmp_path / "x.zip"), THR)
    t = pd.DatetimeIndex(df["open_time"])
    assert (t.hour == 0).all() and (t.minute == 0).all() and (t == t.normalize()).all()
    assert t.tz is None


def test_header_row_is_skipped():
    rows = [_row(_ms("2024-01-01")), _row(_ms("2024-01-02"))]
    a = clean.read_kline_csv(_csv(rows, header=True))
    b = clean.read_kline_csv(_csv(rows, header=False))
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 2 and a["open_time"].dtype == "int64"


# ------------------------------------------------------------------------------------------ sembol kurulumu
def _setup(tmp_path, files: dict[str, list]) -> tuple[dict, pd.DataFrame]:
    raw = tmp_path / "raw"
    for rel, rows in files.items():
        _zip(raw / rel, rows)
    led = pd.DataFrame([{"rel_path": rel, "url": "u", "sha256_expected": "h" + rel, "sha256_actual": "h" + rel,
                         "size_bytes": 1, "downloaded_at_utc": "t", "status": "ok"} for rel in files],
                       columns=LEDGER_COLS)
    led.to_csv(tmp_path / "ledger.csv", index=False)
    cfg = load_settings({"paths": {"raw": str(raw), "ledger": str(tmp_path / "ledger.csv"),
                                   "clean": str(tmp_path / "clean")}})
    return cfg, clean.ledger_files(cfg)


def _days(start, n, **kw):
    return [_row(_ms(start) + i * DAY_MS, close=1.0 + i, **kw) for i in range(n)]


def test_build_duplicates_priority_and_half_day(tmp_path):
    files = {
        "monthly/klines/AAAUSDT/1d/AAAUSDT-1d-2024-01.zip": _days("2024-01-10", 22),
        # günlük dosya aylık dosyası olan ayda → kullanılmaz (farklı değer olsa bile)
        "daily/klines/AAAUSDT/1d/AAAUSDT-1d-2024-01-31.zip": [_row(_ms("2024-01-31"), close=999.0)],
        "daily/klines/AAAUSDT/1d/AAAUSDT-1d-2024-02-01.zip": [_row(_ms("2024-02-01"), close=5.0)],
        # aynı open_time iki günlük dosyada: biri birebir aynı, diğeri farklı → exact ve conflict
        "daily/klines/AAAUSDT/1d/AAAUSDT-1d-2024-02-02.zip": [_row(_ms("2024-02-02"), close=6.0),
                                                              _row(_ms("2024-02-02"), close=6.0)],
        "daily/klines/AAAUSDT/1d/AAAUSDT-1d-2024-02-03.zip": [_row(_ms("2024-02-03"), close=7.0),
                                                              _row(_ms("2024-02-03"), close=8.0)],
        "monthly/klines/BBBUSDT/1d/BBBUSDT-1d-2024-01.zip": _days("2024-01-01", 15),
    }
    cfg, lf = _setup(tmp_path, files)
    ge = lf["end"].max()
    assert ge == pd.Timestamp("2024-02-04")
    a = lf[lf.symbol == "AAAUSDT"]
    df, dups = clean.build_frame(a, Path(cfg["paths"]["raw"]), THR, ge, "AAAUSDT", "1d")
    assert list(df.columns) == clean.CLEAN_COLS
    assert df.dtypes.astype(str).to_dict() == {c: str(np.dtype(t)) for c, t in clean.CLEAN_DTYPES.items()}
    assert df["open_time"].is_unique and df["open_time"].is_monotonic_increasing
    assert df.loc[df.open_time == "2024-01-31", "close"].item() == 22.0  # aylık kazanır
    assert df.loc[df.open_time == "2024-02-03", "close"].item() == 7.0  # ilk satır tutulur
    assert sorted(dups["kind"]) == ["conflict", "exact"]
    # AAA global sona ulaşıyor → yalnız ilk mum yarım gün
    assert df["half_day"].tolist() == [True] + [False] * (len(df) - 1)
    b = lf[lf.symbol == "BBBUSDT"]
    dfb, _ = clean.build_frame(b, Path(cfg["paths"]["raw"]), THR, ge, "BBBUSDT", "1d")
    assert dfb["half_day"].iloc[0] and dfb["half_day"].iloc[-1] and dfb["half_day"].sum() == 2  # sona ermiş


def test_half_day_segments():
    """Kesik mum (delist/askı) ve boşluktan sonraki yeniden açılış mumu da yarım gün (eski/yeni LUNA örneği)."""
    ot = pd.Series(pd.to_datetime(["2022-05-11", "2022-05-12", "2022-05-13", "2022-05-31", "2022-06-01"]))
    ct = ot + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    ct[2] = pd.Timestamp("2022-05-13 00:39:59.999")  # eski LUNA son mum
    hd = clean.half_day_flags(ot, ct, pd.Timedelta(days=1), pd.Timestamp("2022-06-02"))
    assert hd.tolist() == [True, False, True, True, False]
    hd2 = clean.half_day_flags(ot, ct, pd.Timedelta(days=1), pd.Timestamp("2022-07-01"))  # çift sona ermiş
    assert hd2.tolist() == [True, False, True, True, True]
    assert clean.interval_td("1h") == pd.Timedelta(hours=1) and clean.interval_td("1d") == pd.Timedelta(days=1)


def test_rebuild_is_deterministic_and_incremental(tmp_path):
    files = {"monthly/klines/AAAUSDT/1d/AAAUSDT-1d-2024-01.zip": _days("2024-01-01", 31),
             "monthly/klines/AAAUSDT/1d/AAAUSDT-1d-2025-01.zip": _days("2025-01-01", 31, unit="us"),
             "monthly/klines/BBBUSDT/1d/BBBUSDT-1d-2025-01.zip": _days("2025-01-05", 20, unit="us")}
    cfg, _ = _setup(tmp_path, files)
    s1 = clean.build(cfg, workers=1, progress=False)
    out = Path(cfg["paths"]["clean"]) / "1d"
    m1 = clean._load_manifest(out / clean.MANIFEST)
    h_file = clean.content_hash(pd.read_parquet(out / "AAAUSDT.parquet"))
    assert s1["1d"]["built"] == 2 and h_file == m1["AAAUSDT"]["content_hash"]
    s2 = clean.build(cfg, workers=1, progress=False)  # hiçbir şey değişmedi → kurulum yok
    assert s2["1d"]["built"] == 0 and s2["1d"]["skipped"] == 2
    clean.build(cfg, workers=1, progress=False, force=True)
    m3 = clean._load_manifest(out / clean.MANIFEST)
    assert {k: v["content_hash"] for k, v in m3.items()} == {k: v["content_hash"] for k, v in m1.items()}
    back = pd.read_parquet(out / "AAAUSDT.parquet")
    assert back["open_time"].dtype == "datetime64[ns]" and back["open_time"].dt.tz is None


def test_content_hash_sensitive_to_values():
    df = pd.DataFrame({"a": [1.0, 2.0], "b": [True, False]})
    df2 = df.copy()
    df2.loc[1, "a"] = 2.0000001
    assert clean.content_hash(df) == clean.content_hash(df.copy())
    assert clean.content_hash(df) != clean.content_hash(df2)


def test_parse_rel():
    m = clean.parse_rel("monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-02.zip")
    assert (m["symbol"], m["interval"], m["period"]) == ("BTCUSDT", "1h", "2024-02")
    assert m["end"] == pd.Timestamp("2024-03-01")
    d = clean.parse_rel("daily/klines/BTCUSDT/1d/BTCUSDT-1d-2026-11-01.zip")
    assert d["period"] == "2026-11-01" and d["end"] == pd.Timestamp("2026-11-02")


@pytest.mark.parametrize("unit", ["ms", "us"])
def test_normalize_keeps_values(unit):
    raw = clean.read_kline_csv(_csv([_row(_ms("2025-03-01"), close=2.5, unit=unit)]))
    df = clean.normalize(raw, THR)
    assert df["open_time"].item() == pd.Timestamp("2025-03-01")
    assert df["close"].item() == 2.5 and df["number_of_trades"].item() == 7
