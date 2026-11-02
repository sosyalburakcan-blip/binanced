"""G1–G3 ağ testleri (varsayılan olarak atlanır; `pytest -m network tests/test_data_network.py`).

En kritik varsayım (SPEC G1): delist edilmiş semboller arşivde duruyor mu?
"""

import pandas as pd
import pytest

from trend.config import load_settings
from trend.data import clean, s3
from trend.data import download as dl
from trend.data.rest import RestClient

pytestmark = pytest.mark.network
CFG = load_settings()

# (sembol, aralık, beklenen ilk ay, beklenen son ay) — 2026-11-02 S3 listelemesinden
DELISTED = [("MATICUSDT", "1d", "2019-04", "2024-09"), ("RNDRUSDT", "1d", "2021-11", "2024-07"),
            ("BTCBUSD", "1d", "2019-09", "2023-12"), ("LUNABUSD", "1d", "2020-08", "2023-12")]


@pytest.mark.parametrize("sym,iv,first,last", DELISTED)
def test_delisted_symbols_in_archive(sym, iv, first, last):
    lst = s3.list_bucket(f"{s3.MONTHLY_ROOT}{sym}/{iv}/", cfg=CFG)
    months = sorted(c["key"][-11:-4] for c in lst.contents if c["key"].endswith(".zip"))
    assert months[0] == first and months[-1] == last


def test_old_luna_and_ftt_present():
    """Eski LUNA (2022-05'e kadar) ve FTTUSDT arşivde; ikisi de aynı sembolle sonradan yeniden işlem görüyor."""
    for sym, must in [("LUNAUSDT", ["2020-08", "2022-04", "2022-05"]), ("FTTUSDT", ["2019-12", "2022-11"])]:
        lst = s3.list_bucket(f"{s3.MONTHLY_ROOT}{sym}/1d/", cfg=CFG)
        months = {c["key"][-11:-4] for c in lst.contents if c["key"].endswith(".zip")}
        assert set(must) <= months


def test_rest_klines_for_delisted_symbol():
    """data-api.binance.vision delist edilmiş MATICUSDT için hâlâ veri döndürüyor (son mum 2024-09-10)."""
    df = RestClient(CFG).klines("MATICUSDT", "1d", start="2024-09-01")
    assert len(df) and df["open_time"].max() == pd.Timestamp("2024-09-10")


def test_download_and_clean_one_file(tmp_path):
    rel = "monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2025-01.zip"
    row = dl.fetch_one(rel, f"{CFG['data']['archive_base']}/{rel}", tmp_path, CFG["data"])
    assert row["status"] == "ok" and row["sha256_actual"] == row["sha256_expected"]
    df = clean.normalize(clean.read_zip(tmp_path / rel), CFG["data"]["timestamp_us_threshold"])
    assert len(df) == 31 and df["open_time"].iloc[0] == pd.Timestamp("2025-01-01")


def test_archive_matches_rest_sample():
    """Arşiv ve REST aynı mumu veriyor (küçük çapraz kontrol; G4 bunu 10 coin × 20 gün yapar)."""
    rel = "monthly/klines/ETHUSDT/1d/ETHUSDT-1d-2024-06.zip"
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        assert dl.fetch_one(rel, f"{CFG['data']['archive_base']}/{rel}", Path(d), CFG["data"])["status"] == "ok"
        a = clean.normalize(clean.read_zip(Path(d) / rel), CFG["data"]["timestamp_us_threshold"])
    b = RestClient(CFG).klines("ETHUSDT", "1d", start="2024-06-01", end="2024-06-30")
    cols = ["open_time", "open", "high", "low", "close", "volume", "number_of_trades"]
    pd.testing.assert_frame_equal(a[cols].reset_index(drop=True), b[cols].reset_index(drop=True))
