"""G5 testleri: tablo doğrulama, RENAME/REDENOM/ASSET_CHANGE birleştirme aritmetiği (1d ve 1h), aday üretimi."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trend import meta as M
from trend.config import ROOT, load_settings

FIX = Path(__file__).parent / "fixtures" / "meta"
D = pd.Timestamp
CFG = load_settings()


def series(start, end, price, interval="1d", vol=100.0, drop=()):
    """Sabit artışlı, tam bilinen değerli sentetik temiz seri (CONTRACTS §3)."""
    step = M.INTERVAL_STEP[interval]
    t = pd.date_range(start, end, freq=M.INTERVAL_FREQ[interval], unit="ns")
    t = t[~t.isin(pd.DatetimeIndex(list(drop)))]
    n = len(t)
    close = price * (1 + 0.001 * np.arange(n))
    df = pd.DataFrame({
        "open_time": t, "open": close * 0.999, "high": close * 1.01, "low": close * 0.98, "close": close,
        "volume": np.full(n, vol), "close_time": t + step - pd.Timedelta(milliseconds=1), "quote_volume": vol * close,
        "number_of_trades": np.arange(n, dtype="int64") + 10, "taker_buy_base": np.full(n, vol / 2),
        "taker_buy_quote": vol * close / 2, "half_day": False,
    })
    df.loc[[0, n - 1], "half_day"] = True
    return df


def frames_1d():
    return {
        "OLDUSDT": series("2021-01-01", "2021-01-10", 10.0),
        "NEWUSDT": series("2021-01-13", "2021-01-20", 10.5),
        "ERDUSDT": series("2021-01-15", "2021-02-05", 0.02, vol=1e6),
        "EGLDUSDT": series("2021-02-07", "2021-02-20", 21.0, vol=900.0),
        "BNXUSDT": pd.concat([series("2021-02-01", "2021-03-05", 50.0), series("2021-03-11", "2021-05-01", 0.52, vol=9000.0)], ignore_index=True),
        "FORMUSDT": series("2021-05-02", "2021-05-31", 0.6, vol=9000.0),
        "LUNAUSDT": pd.concat([series("2021-01-01", "2021-04-13", 80.0), series("2021-04-30", "2021-06-30", 5.0)], ignore_index=True),
        "OCEANUSDT": series("2021-01-01", "2021-06-01", 0.5),
        "FETUSDT": series("2021-01-01", "2021-06-30", 0.3),
        "CANDUSDT": series("2021-01-01", "2021-01-20", 1.0),
        "CAND2USDT": series("2021-01-25", "2021-02-10", 1.0),
        "BTCUSDT": series("2021-01-01", "2021-06-30", 30000.0),
    }


@pytest.fixture(scope="module")
def smap():
    return M.load_symbol_map(FIX / "symbol_map_synthetic.csv")


@pytest.fixture(scope="module")
def merged_1d(smap):
    return M.merge_frames(frames_1d(), smap, "1d")


# ---------------------------------------------------------------- doğrulama


def test_fixture_map_loads_with_types(smap):
    assert list(smap.columns) == M.SYMBOL_MAP_COLUMNS
    assert smap["ratio"].dtype == "float64"
    assert np.isnan(smap.loc[smap["type"] == "ASSET_CHANGE", "ratio"]).all()


@pytest.mark.parametrize("row,needle", [
    ("AUSDT,BUSDT,RENAMED,1,,,src,yes", "type"),
    ("AUSDT,BUSDT,RENAME,2,,,src,yes", "RENAME oranı 1"),
    ("AUSDT,BUSDT,REDENOM,-5,,,src,yes", "oran > 0"),
    ("AUSDT,BUSDT,REDENOM,abc,,,src,yes", "sayı değil"),
    ("AUSDT,BUSDT,ASSET_CHANGE,,2021-01-01,2021-02-01,src,yes", "old == new"),
    ("AUSDT,AUSDT,ASSET_CHANGE,,2021-01-01,,src,yes", "iki zaman"),
    ("AUSDT,BUSDT,RENAME,1,,,,yes", "kaynak boş"),
    ("AUSDT,BUSDT,RENAME,1,2021/01/01,,src,yes", "zaman biçimi"),
    ("AUSDT,BUSDT,RENAME,1,2021-02-01,2021-01-01,src,yes", "old_last_trade_utc <"),
    ("AUSDT,BUSDT,DELIST,,2021-01-01,,src,yes", "DELIST'te new_symbol"),
    ("AUSDT,BUSDT,RENAME,1,,,src,approved", "verified"),
    ("ausdt,BUSDT,RENAME,1,,,src,yes", "old_symbol geçersiz"),
])
def test_invalid_rows_rejected(tmp_path, row, needle):
    p = tmp_path / "m.csv"
    p.write_text(",".join(M.SYMBOL_MAP_COLUMNS) + "\n" + row + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=needle):
        M.load_symbol_map(p)


def test_extra_column_rejected(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text(",".join(M.SYMBOL_MAP_COLUMNS) + ",note\nAUSDT,BUSDT,RENAME,1,,,src,yes,x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fazla kolon"):
        M.load_symbol_map(p)


def test_project_meta_tables_are_valid():
    """Projedeki gerçek meta/*.csv dosyaları şemaya uyar ve her satırın kaynağı var."""
    res = M.validate_all(CFG)
    assert res == {"symbol_map.csv": [], "fee_promotions.csv": [], "delist_announcements.csv": []}, res
    sm = M.load_symbol_map(cfg=CFG)
    # SPEC "Kaynaklarla doğrulanmış satırlar" tablosunun tüm satırları verified=yes ile var.
    yes = sm.loc[sm["verified"] == "yes"]
    pairs = set(zip(yes["old_symbol"], yes["new_symbol"], yes["type"]))
    for t in [("ERDUSDT", "EGLDUSDT", "REDENOM"), ("BTTUSDT", "BTTCUSDT", "REDENOM"), ("LUNAUSDT", "", "DELIST"),
              ("LUNAUSDT", "LUNAUSDT", "ASSET_CHANGE"), ("BNXUSDT", "BNXUSDT", "REDENOM"), ("OCEANUSDT", "FETUSDT", "MERGE_INTO_EXISTING"),
              ("AGIXUSDT", "FETUSDT", "MERGE_INTO_EXISTING"), ("GALUSDT", "GUSDT", "REDENOM"), ("RNDRUSDT", "RENDERUSDT", "RENAME"),
              ("MATICUSDT", "POLUSDT", "RENAME"), ("FTMUSDT", "SUSDT", "RENAME"), ("BNXUSDT", "FORMUSDT", "RENAME"),
              ("EOSUSDT", "AUSDT", "RENAME"), ("MKRUSDT", "SKYUSDT", "REDENOM")]:
        assert t in pairs, t
    r = yes.set_index(["old_symbol", "new_symbol", "type"])["ratio"]
    assert r[("ERDUSDT", "EGLDUSDT", "REDENOM")] == 0.001 and r[("MKRUSDT", "SKYUSDT", "REDENOM")] == 24000
    assert r[("OCEANUSDT", "FETUSDT", "MERGE_INTO_EXISTING")] == 0.433226 and r[("GALUSDT", "GUSDT", "REDENOM")] == 60
    # Gerçek tablo zincirleri planlanabilir (bilinen semboller mevcutmuş gibi).
    syms = sorted(set(sm["old_symbol"]) | set(sm["new_symbol"]) - {""})
    M.build_plan(sm, syms, "1d", include_candidates=True)
    M.build_plan(sm, syms, "1h", include_candidates=False)


# ---------------------------------------------------------------- birleştirme (1d)


def test_rename_joined_unchanged(merged_1d):
    out, seg, _ = merged_1d
    assert "OLDUSDT" not in out and "NEWUSDT" in out
    m = out["NEWUSDT"]
    f = frames_1d()
    assert len(m) == 10 + 8 and m["open_time"].is_monotonic_increasing and m["open_time"].dtype == "datetime64[ns]"
    old = m.loc[m["source_symbol"] == "OLDUSDT"].reset_index(drop=True)
    pd.testing.assert_frame_equal(old.drop(columns="source_symbol"), f["OLDUSDT"])
    s = seg.loc[seg["asset_id"] == "NEWUSDT"]
    assert list(s["source_symbol"]) == ["OLDUSDT", "NEWUSDT"] and list(s["ratio"]) == [1.0, 1.0]
    assert s["start"].iloc[0] == D("2021-01-01") and s["end"].iloc[0] == D("2021-01-10") and s["start"].iloc[1] == D("2021-01-13")
    assert list(M.merge_frames(frames_1d(), M.load_symbol_map(FIX / "symbol_map_synthetic.csv"), "1d")[0]["NEWUSDT"].columns)[-1] == "source_symbol"


def test_redenom_symbol_change_arithmetic(merged_1d):
    out, seg, _ = merged_1d
    f = frames_1d()
    m = out["EGLDUSDT"]
    erd = f["ERDUSDT"]
    part = m.loc[m["source_symbol"] == "ERDUSDT"].reset_index(drop=True)
    for c in ("open", "high", "low", "close"):
        np.testing.assert_allclose(part[c], erd[c] / 0.001, rtol=0, atol=0)  # eski fiyat / oran (tam)
    np.testing.assert_array_equal(part["volume"], erd["volume"] * 0.001)  # taban hacim × oran
    np.testing.assert_array_equal(part["taker_buy_base"], erd["taker_buy_base"] * 0.001)
    np.testing.assert_array_equal(part["quote_volume"], erd["quote_volume"])  # quote değişmez
    np.testing.assert_array_equal(part["taker_buy_quote"], erd["taker_buy_quote"])
    np.testing.assert_array_equal(part["number_of_trades"], erd["number_of_trades"])
    # Quote/base ≈ fiyat tutarlılığı korunur
    np.testing.assert_allclose(part["quote_volume"] / part["volume"], part["close"])
    new = m.loc[m["source_symbol"] == "EGLDUSDT"].reset_index(drop=True)
    pd.testing.assert_frame_equal(new.drop(columns="source_symbol"), f["EGLDUSDT"])
    assert seg.loc[seg["source_symbol"] == "ERDUSDT", "ratio"].item() == 0.001


def test_same_symbol_split_with_gap_then_rename_chain(merged_1d):
    """BNX tarzı: aynı sembolde 1:100 bölünme (arşiv boşluğuyla) ve ardından BNX→FORM; asset_id = FORMUSDT."""
    out, seg, _ = merged_1d
    assert "BNXUSDT" not in out
    m = out["FORMUSDT"]
    bnx = frames_1d()["BNXUSDT"]
    pre = bnx.loc[bnx["open_time"] <= D("2021-03-05")].reset_index(drop=True)
    post = bnx.loc[bnx["open_time"] >= D("2021-03-11")].reset_index(drop=True)
    got_pre = m.loc[m["open_time"] <= D("2021-03-05")].reset_index(drop=True)
    assert len(got_pre) == len(pre) and (got_pre["source_symbol"] == "BNXUSDT").all()
    np.testing.assert_array_equal(got_pre["close"], pre["close"] / 100.0)
    np.testing.assert_array_equal(got_pre["volume"], pre["volume"] * 100.0)
    np.testing.assert_array_equal(got_pre["quote_volume"], pre["quote_volume"])
    got_post = m.loc[(m["open_time"] >= D("2021-03-11")) & (m["source_symbol"] == "BNXUSDT")].reset_index(drop=True)
    np.testing.assert_array_equal(got_post["close"], post["close"])
    assert not m["open_time"].between(D("2021-03-06"), D("2021-03-10")).any()  # boşluk korunur (motor taşır)
    s = seg.loc[seg["asset_id"] == "FORMUSDT"]
    assert list(zip(s["source_symbol"], s["ratio"])) == [("BNXUSDT", 100.0), ("BNXUSDT", 1.0), ("FORMUSDT", 1.0)]
    # Bölünme çevresinde düzeltilmiş fiyat süreklidir (50×1.032/100 ≈ 0.516 → 0.52)
    jump = m.loc[m["open_time"] == D("2021-03-11"), "close"].item() / m.loc[m["open_time"] == D("2021-03-05"), "close"].item()
    assert 0.9 < jump < 1.1


def test_asset_change_splits_series(merged_1d):
    out, seg, _ = merged_1d
    old, new = out["LUNAUSDT_until_20210413"], out["LUNAUSDT"]
    assert old["open_time"].max() == D("2021-04-13") and old["open_time"].min() == D("2021-01-01")
    assert new["open_time"].min() == D("2021-04-30")  # 06:00 açılış → 1d mumu 04-30 00:00 yeni varlığa ait
    assert (old["close"] > 70).all() and (new["close"] < 10).all()
    assert set(seg.loc[seg["source_symbol"] == "LUNAUSDT", "asset_id"]) == {"LUNAUSDT_until_20210413", "LUNAUSDT"}
    assert (seg.loc[seg["source_symbol"] == "LUNAUSDT", "ratio"] == 1.0).all()


def test_merge_into_existing_delist_and_candidates_untouched(merged_1d, smap):
    out, seg, _ = merged_1d
    f = frames_1d()
    for s in ("OCEANUSDT", "FETUSDT", "BTCUSDT", "CANDUSDT", "CAND2USDT"):
        pd.testing.assert_frame_equal(out[s].drop(columns="source_symbol"), f[s])
    # candidate satırı yalnız açıkça istenirse uygulanır
    out2, _, _ = M.merge_frames(f, smap, "1d", include_candidates=True)
    assert "CANDUSDT" not in out2 and len(out2["CAND2USDT"]) == len(f["CANDUSDT"]) + len(f["CAND2USDT"])
    # Her kaynak mum tam olarak bir kez kullanılır
    assert sum(len(v) for v in out.values()) == sum(len(v) for v in f.values())


def test_unassignable_rows_between_cuts_warned(smap):
    f = frames_1d()
    extra = series("2021-03-08", "2021-03-08", 0.5)
    f["BNXUSDT"] = pd.concat([f["BNXUSDT"], extra]).sort_values("open_time").reset_index(drop=True)
    out, _, warns = M.merge_frames(f, smap, "1d")
    assert not (out["FORMUSDT"]["open_time"] == D("2021-03-08")).any()
    assert any("atanamadı" in w and "BNXUSDT" in w for w in warns)


def test_overlap_resolved_in_favour_of_new_pair(smap):
    f = frames_1d()
    f["OLDUSDT"] = series("2021-01-01", "2021-01-14", 10.0)  # yeni çift 01-13'te başlıyor → 2 gün çakışma
    out, _, warns = M.merge_frames(f, smap, "1d")
    m = out["NEWUSDT"]
    assert not m["open_time"].duplicated().any()
    assert m.loc[m["open_time"] == D("2021-01-13"), "source_symbol"].item() == "NEWUSDT"
    assert any("çakışıyor" in w for w in warns) and any("old_last_trade sonrasında" in w for w in warns)


# ---------------------------------------------------------------- birleştirme (1h)


def test_hourly_boundaries(smap):
    f = {
        "LUNAUSDT": pd.concat([series("2021-04-12 00:00", "2021-04-13 03:00", 80.0, "1h"),
                               series("2021-04-30 06:00", "2021-05-01 23:00", 5.0, "1h")], ignore_index=True),
        "BNXUSDT": pd.concat([series("2021-03-04 00:00", "2021-03-05 23:00", 50.0, "1h"),
                              series("2021-03-11 00:00", "2021-03-12 23:00", 0.5, "1h")], ignore_index=True),
    }
    out, seg, warns = M.merge_frames(f, smap, "1h")
    old = out["LUNAUSDT_until_20210413"]
    # old_last 00:40 → 00:00 mumu dahil, 01:00–03:00 mumları iki sınır arasında: atanamaz, uyarıyla düşer
    assert old["open_time"].max() == D("2021-04-13 00:00")
    assert out["LUNAUSDT"]["open_time"].min() == D("2021-04-30 06:00")
    assert any("LUNAUSDT" in w and "3 mum atanamadı" in w for w in warns)
    b = out["BNXUSDT"]  # FORMUSDT verisi yok → zincir BNX'te biter (uyarı)
    assert any("FORMUSDT" in w for w in warns)
    pre = b.loc[b["open_time"] <= D("2021-03-05 23:00")]
    assert len(pre) == 48
    np.testing.assert_array_equal(pre["close"].to_numpy(), f["BNXUSDT"]["close"].to_numpy()[:48] / 100.0)
    assert list(seg.loc[seg["asset_id"] == "BNXUSDT", "ratio"]) == [100.0, 1.0]


# ---------------------------------------------------------------- dosyaya yazma


def test_build_merged_writes_files(tmp_path):
    clean = tmp_path / "clean" / "1d"
    clean.mkdir(parents=True)
    meta = tmp_path / "meta"
    meta.mkdir()
    for s, df in frames_1d().items():
        df.to_parquet(clean / f"{s}.parquet", index=False)
    pd.DataFrame({"open_time": [D("2021-01-01")]}).to_parquet(clean / "BTCBUSD.parquet")  # USDT dışı: birleştirilmez
    (meta / "symbol_map.csv").write_text((FIX / "symbol_map_synthetic.csv").read_text(encoding="utf-8"), encoding="utf-8")
    cfg = load_settings({"paths": {"clean": str(tmp_path / "clean"), "meta": str(meta), "merged": str(tmp_path / "merged")}})
    (tmp_path / "merged" / "1d").mkdir(parents=True)
    pd.DataFrame({"x": [1]}).to_parquet(tmp_path / "merged" / "1d" / "STALEUSDT.parquet")
    seg = M.build_merged("1d", cfg)
    files = sorted(p.stem for p in (tmp_path / "merged" / "1d").glob("*.parquet"))
    assert "STALEUSDT" not in files and "BTCBUSD" not in files and "OLDUSDT" not in files
    assert {"NEWUSDT", "EGLDUSDT", "FORMUSDT", "LUNAUSDT", "LUNAUSDT_until_20210413", "BTCUSDT"} <= set(files)
    s = pd.read_csv(meta / "asset_segments.csv")
    assert list(s.columns) == M.SEGMENT_COLUMNS and len(s) == len(seg)
    assert s.loc[s["asset_id"] == "EGLDUSDT", "start"].iloc[0] == "2021-01-15 00:00:00"
    m = pd.read_parquet(tmp_path / "merged" / "1d" / "FORMUSDT.parquet")
    assert m["open_time"].dtype == "datetime64[ns]" and m["number_of_trades"].dtype == "int64" and "source_symbol" in m
    assert "CANDUSDT->CAND2USDT" in (meta / "merge_log_1d.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------- adaylar, kampanyalar, duyurular


def test_find_candidates_from(smap):
    summ = pd.DataFrame([
        {"symbol": "XAUSDT", "first": D("2020-01-01"), "last": D("2021-01-10"), "first_open": 1.0, "last_close": 10.0},
        {"symbol": "XBUSDT", "first": D("2021-01-13"), "first_open": 0.1, "last": D("2021-06-30"), "last_close": 0.2},  # 1:100
        {"symbol": "GALAUSDT", "first": D("2020-01-01"), "last": D("2021-02-01"), "first_open": 1.0, "last_close": 3.7},
        {"symbol": "GUSDT", "first": D("2021-02-04"), "last": D("2021-06-30"), "first_open": 0.06, "last_close": 0.1},  # isim öneki
        {"symbol": "USDPUSDT", "first": D("2020-01-01"), "last": D("2021-03-01"), "first_open": 1.0, "last_close": 1.0},
        {"symbol": "FDUSDUSDT", "first": D("2021-03-03"), "last": D("2021-06-30"), "first_open": 1.0, "last_close": 1.0},  # stable: hariç
        {"symbol": "OLDUSDT", "first": D("2020-01-01"), "last": D("2021-01-10"), "first_open": 1.0, "last_close": 10.0},  # tabloda
        {"symbol": "NEWUSDT", "first": D("2021-01-13"), "last": D("2021-06-30"), "first_open": 10.0, "last_close": 1.0},
        {"symbol": "ZZUSDT", "first": D("2021-05-01"), "last": D("2021-06-30"), "first_open": 3.3, "last_close": 1.0},
    ])
    flags = pd.DataFrame({"symbol": ["QQUSDT", "BNXUSDT", "RRUSDT", "BNXUSDT", "SSUSDT"],
                          "check": ["split_candidate", "split_candidate", "extreme_return", "extreme_return", "extreme_return"],
                          "period_start": [D("2021-02-01"), D("2021-03-05"), D("2021-04-10"), D("2021-03-11"), D("2021-04-10")],
                          "period_end": [D("2021-02-05"), D("2021-03-11"), D("2021-04-10"), D("2021-03-11"), D("2021-04-10")],
                          "known_from": [D("2021-02-05"), D("2021-03-11"), D("2021-04-10"), D("2021-03-11"), D("2021-04-10")],
                          "severity": ["flag"] * 5,
                          "detail": ["k=3;suggested_ratio=1000", "k=2;suggested_ratio=100",
                                     f"log_return={-np.log(100) + 0.08:.10g};prev_close=1;close=0.01;gap_days=4",  # boşlukta %8 oynamış 1:100
                                     f"log_return={-np.log(100):.10g};prev_close=1;close=0.01;gap_days=5",  # tabloda (BNX)
                                     f"log_return={-np.log(100):.10g};prev_close=1;close=0.01;gap_days=0"]})  # boşluksuz: aday değil
    c = M.find_candidates_from(summ, flags, smap, D("2021-06-30"), CFG)
    got = {(r.old_symbol, r.new_symbol): r for r in c.itertuples(index=False)}
    assert got[("XAUSDT", "XBUSDT")].type == "REDENOM" and got[("XAUSDT", "XBUSDT")].ratio == 100.0
    assert "pair_name_hint" in got[("GALAUSDT", "GUSDT")].method
    assert ("USDPUSDT", "FDUSDUSDT") not in got and ("OLDUSDT", "NEWUSDT") not in got
    assert got[("QQUSDT", "QQUSDT")].ratio == 1000.0 and got[("QQUSDT", "QQUSDT")].method == "split_check"
    assert ("BNXUSDT", "BNXUSDT") not in got  # tabloda zaten var
    rr = got[("RRUSDT", "RRUSDT")]
    assert rr.method == "return_check" and rr.ratio == 100.0 and rr.old_last_trade_utc == "2021-04-05" and rr.new_first_trade_utc == "2021-04-10"
    assert ("SSUSDT", "SSUSDT") not in got
    assert (c["verified"] == "candidate").all() and list(c.columns) == M.CANDIDATE_COLUMNS


def test_fee_promotions_and_mask(tmp_path):
    p = tmp_path / "f.csv"
    p.write_text("symbol,start,end,source\nBTCUSDT,2022-07-08 00:00,2023-03-22 00:00,src\nBTCTUSD,2023-03-22 00:00,,src\n"
                 "ETHBUSD,2022-09-01,2022-09-30,src\n", encoding="utf-8")
    f = M.load_fee_promotions(p)
    days = pd.date_range("2022-07-07", "2023-03-23", unit="ns")
    m = M.promo_mask(f, ["BTCUSDT", "BTCTUSD", "ETHBUSD"], days)
    assert not m.loc[D("2022-07-07"), "BTCUSDT"] and m.loc[D("2022-07-08"), "BTCUSDT"]
    assert m.loc[D("2023-03-21"), "BTCUSDT"] and not m.loc[D("2023-03-22"), "BTCUSDT"]
    assert m.loc[D("2023-03-22"), "BTCTUSD"] and not m.loc[D("2023-03-21"), "BTCTUSD"]
    assert m.loc[D("2022-09-30"), "ETHBUSD"] and not m.loc[D("2022-10-01"), "ETHBUSD"]  # yalnız tarih: gün dahil
    bad = tmp_path / "b.csv"
    bad.write_text("symbol,start,end,source\nBTCUSDT,2023-01-01,2022-01-01,src\n", encoding="utf-8")
    with pytest.raises(ValueError, match="end > start"):
        M.load_fee_promotions(bad)


def test_delist_announcements_known_at(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("symbol,announced_utc,delist_utc,kind,source\nFTTUSDT,2022-11-10 12:00,2022-11-15 03:00,delist,src\n"
                 "XUSDT,2023-08-01,,monitoring_tag,src\n", encoding="utf-8")
    a = M.load_delist_announcements(p)
    assert list(M.announcements_known_at(a, "2022-11-09")["symbol"]) == []
    assert list(M.announcements_known_at(a, "2022-11-10")["symbol"]) == ["FTTUSDT"]
    bad = tmp_path / "b.csv"
    bad.write_text("symbol,announced_utc,delist_utc,kind,source\nFTTUSDT,2022-11-10,,removed,src\n", encoding="utf-8")
    with pytest.raises(ValueError, match="kind"):
        M.load_delist_announcements(bad)


def test_g5_report_auto_section_preserves_manual_text(tmp_path):
    rp = tmp_path / "G5.md"
    rp.write_text(f"# başlık\n\nelle not\n\n{M.AUTO_BEGIN}\neski\n{M.AUTO_END}\n\nson not\n", encoding="utf-8")
    M.write_g5_report(CFG, rp)
    t = rp.read_text(encoding="utf-8")
    assert "elle not" in t and "son not" in t and "ESKI_OTOMATIK_ICERIK" not in t and "Onaylandı 2026-11-03" in t
    assert t.count(M.AUTO_BEGIN) == 1 and t.count(M.AUTO_END) == 1
