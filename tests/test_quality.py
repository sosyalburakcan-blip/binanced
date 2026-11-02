"""G4 testleri: her kontrol, tarihe bağlı known_from ve kesme değişmezi (kabul testi), sentetik veriyle."""

import numpy as np
import pandas as pd
import pytest

from trend import quality as Q
from trend.config import load_settings

CFG = load_settings()
D = pd.Timestamp
DAY = pd.Timedelta(days=1)
DATA_END = D("2020-06-30")


def make_series(start, end, p0=100.0, seed=0, interval="1d"):
    """CONTRACTS §3 şemasında düzgün bir sentetik seri (ilk/son mum half_day=True)."""
    step = Q.INTERVAL_STEP[interval]
    t = pd.date_range(start, end, freq=Q.INTERVAL_FREQ[interval], unit="ns")
    rng = np.random.default_rng(seed)
    close = p0 * np.exp(np.cumsum(rng.normal(0, 0.01, len(t))))
    open_ = np.r_[p0, close[:-1]]
    vol = rng.uniform(100, 200, len(t))
    df = pd.DataFrame({
        "open_time": t,
        "open": open_, "high": np.maximum(open_, close) * 1.01, "low": np.minimum(open_, close) * 0.99, "close": close,
        "volume": vol, "close_time": t + step - pd.Timedelta(milliseconds=1), "quote_volume": vol * close,
        "number_of_trades": rng.integers(50, 100, len(t)).astype("int64"),
        "taker_buy_base": vol / 2, "taker_buy_quote": vol * close / 2, "half_day": False,
    })
    df.loc[[0, len(df) - 1], "half_day"] = True
    return df


def _set(df, day, **kv):
    i = df.index[df["open_time"].dt.normalize() == D(day)]
    for k, v in kv.items():
        df.loc[i, k] = v


def series_aaa():
    """Tüm anomalileri içeren, data_end'den önce biten (delist) seri."""
    df = make_series("2020-01-01", "2020-06-15", seed=1)
    # Sıfır hacim dizisi 02-10..02-14 (5 gün) + kısa (2 günlük, işaretlenmez) dizi 02-20..02-21.
    for d in pd.date_range("2020-02-10", "2020-02-14"):
        _set(df, d, volume=0.0, quote_volume=0.0)
    for d in pd.date_range("2020-02-20", "2020-02-21"):
        _set(df, d, number_of_trades=0)
    # Boşluk 03-10..03-15 ve dönüşte 1:100 bölünme (fiyat /100).
    df = df.loc[~df["open_time"].between(D("2020-03-10"), D("2020-03-15"))].copy()
    after = df["open_time"] >= D("2020-03-16")
    for k in ("open", "high", "low", "close"):
        df.loc[after, k] = df.loc[after, k] / 100.0
    # İğne 04-01, kapanış sıçraması 04-20 (×2), OHLC hatası 05-05, hizasız zaman damgası 05-20 03:00.
    i = df.index[df["open_time"] == D("2020-04-01")][0]
    df.loc[i, "low"] = 0.1 * df.loc[i, "close"]
    sel = df["open_time"] >= D("2020-04-20")
    for k in ("open", "high", "low", "close"):
        df.loc[sel, k] = df.loc[sel, k] * 2.0
    i = df.index[df["open_time"] == D("2020-04-20")][0]
    df.loc[i, "open"] = df.loc[i, "close"] / 2.0  # sıçrama günü açılışı önceki kapanışta
    df.loc[i, "low"] = df.loc[i, "open"] * 0.99
    i = df.index[df["open_time"] == D("2020-05-05")][0]
    df.loc[i, "high"] = min(df.loc[i, "open"], df.loc[i, "close"]) * 0.999
    i = df.index[df["open_time"] == D("2020-05-20")][0]
    df.loc[i, "open_time"] = D("2020-05-20 03:00")
    df.loc[i, "close_time"] = D("2020-05-20") + DAY - pd.Timedelta(milliseconds=1)
    return df.reset_index(drop=True)


def series_bbb():
    """Hâlâ işlem gören seri (son mumu data_end; temizleyici son mumu half_day işaretlemiş olsa bile işaretlenmez).
    Sıfır hacim dizisi ve boşluk serinin farklı yerlerinde; µs kökenli close_time kabul edilir."""
    df = make_series("2020-02-01", "2020-06-30", p0=5.0, seed=2)
    for d in pd.date_range("2020-06-05", "2020-06-09"):
        _set(df, d, volume=0.0)
    df = df.loc[~df["open_time"].between(D("2020-04-10"), D("2020-04-11"))].copy()
    df["close_time"] = df["open_time"] + DAY - pd.Timedelta(microseconds=1)
    return df.reset_index(drop=True)


@pytest.fixture(scope="module")
def flags_aaa():
    return Q.compute_flags(series_aaa(), "AAAUSDT", CFG, "1d", DATA_END)


def rows(f, check):
    return f.loc[f["check"] == check].reset_index(drop=True)


def test_schema_and_severity(flags_aaa):
    assert list(flags_aaa.columns) == Q.FLAG_COLUMNS
    for c in ("period_start", "period_end", "known_from"):
        assert flags_aaa[c].dtype == "datetime64[ns]"
    assert set(flags_aaa["severity"]) <= {"error", "exclude", "flag"}
    assert (flags_aaa["known_from"] >= flags_aaa["period_start"]).all()


def test_zero_volume_run_known_from(flags_aaa):
    z = rows(flags_aaa, "zero_volume")
    assert list(z["period_start"]) == list(pd.date_range("2020-02-10", "2020-02-14", unit="ns"))
    # İlk iki gün dizinin 3. gününde (02-12) bilinir; sonrakiler kendi gününde.
    assert list(z["known_from"]) == [D("2020-02-12")] * 3 + [D("2020-02-13"), D("2020-02-14")]
    assert (z["severity"] == "exclude").all() and z["detail"].str.contains("run_start=2020-02-10").all()
    # 2 günlük dizi (02-20..21) işaretlenmez.
    assert not z["period_start"].between(D("2020-02-20"), D("2020-02-21")).any()


def test_gap_and_split(flags_aaa):
    g = rows(flags_aaa, "missing_days")
    assert len(g) == 1
    assert (g.loc[0, "period_start"], g.loc[0, "period_end"], g.loc[0, "known_from"]) == (D("2020-03-10"), D("2020-03-15"), D("2020-03-16"))
    assert "n_missing=6" in g.loc[0, "detail"]
    s = rows(flags_aaa, "split_candidate")
    assert len(s) == 1
    assert (s.loc[0, "period_start"], s.loc[0, "period_end"], s.loc[0, "known_from"]) == (D("2020-03-09"), D("2020-03-16"), D("2020-03-16"))
    assert "k=2" in s.loc[0, "detail"] and "suggested_ratio=100" in s.loc[0, "detail"] and "gap_days=6" in s.loc[0, "detail"]


def test_extreme_return_wick_ohlc_timestamp(flags_aaa):
    r = rows(flags_aaa, "extreme_return")
    assert list(r["period_start"]) == [D("2020-03-16"), D("2020-04-20")]
    lr = float(r.loc[1, "detail"].split("log_return=")[1].split(";")[0])
    assert abs(lr - np.log(2.0)) < 0.05
    w = rows(flags_aaa, "extreme_wick")
    assert list(w["period_start"]) == [D("2020-04-01")] and "side=low" in w.loc[0, "detail"]
    o = rows(flags_aaa, "ohlc_inconsistent")
    assert list(o["period_start"]) == [D("2020-05-05")] and "high_lt_max_oc" in o.loc[0, "detail"]
    t = rows(flags_aaa, "timestamp")
    assert list(t["period_start"]) == [D("2020-05-20")] and "misaligned" in t.loc[0, "detail"]
    assert (t["severity"] == "error").all() and (o["severity"] == "error").all()


def test_half_day_first_and_last(flags_aaa):
    h = rows(flags_aaa, "half_day")
    assert list(h["period_start"]) == [D("2020-01-01"), D("2020-06-15")]
    assert list(h["known_from"]) == [D("2020-01-01"), D("2020-06-16")]


def test_still_trading_last_candle_not_half_day():
    f = Q.compute_flags(series_bbb(), "BBBUSDT", CFG, "1d", DATA_END)
    h = rows(f, "half_day")
    assert list(h["period_start"]) == [D("2020-02-01")]
    assert rows(f, "timestamp").empty  # µs kökenli close_time (aralık − 1 µs) geçerli


def test_duplicate_and_close_time_errors():
    df = make_series("2021-01-01", "2021-01-10")
    df = pd.concat([df, df.iloc[[4]]]).sort_values("open_time").reset_index(drop=True)
    df.loc[7, "close_time"] = df.loc[7, "open_time"] + pd.Timedelta(hours=25)  # aralıktan uzun: hata
    df.loc[8, "close_time"] = df.loc[8, "open_time"] - pd.Timedelta(seconds=1)  # negatif süre: hata
    f = Q.compute_flags(df, "XUSDT", CFG, "1d", D("2021-01-10"))
    d = rows(f, "duplicate_open_time")
    assert list(d["period_start"]) == [D("2021-01-05")] and "n_rows=2" in d.loc[0, "detail"]
    t = rows(f, "timestamp")
    assert len(t) == 2 and t["detail"].str.contains("close_time").all()


def test_truncated_close_time_is_half_day_not_error():
    """Arşivde delist/askı mumunun close_time'ı kesiktir (MATICUSDT 2024-09-10 02:59:59.999): hata değil, yarım gün."""
    df = make_series("2024-09-01", "2024-09-10")
    df.loc[len(df) - 1, "close_time"] = D("2024-09-10 02:59:59.999")
    f = Q.compute_flags(df, "MATICUSDT", CFG, "1d", D("2024-12-31"))
    assert rows(f, "timestamp").empty
    h = rows(f, "half_day")
    assert list(h["period_start"]) == [D("2024-09-01"), D("2024-09-10")]
    assert "truncated_close=True" in h.loc[1, "detail"] and h.loc[1, "known_from"] == D("2024-09-11")


def test_out_of_range_timestamp_unit_error():
    df = make_series("2021-01-01", "2021-01-05")
    df.loc[2, "open_time"] = D("1970-01-19")  # ms değeri ns/µs gibi yorumlanmış
    f = Q.compute_flags(df.sort_values("open_time"), "XUSDT", CFG, "1d")
    assert "out_of_range" in rows(f, "timestamp")["detail"].str.cat()


def test_split_without_gap_and_no_false_split_on_ratio_one():
    df = make_series("2021-01-01", "2021-02-01", seed=3)
    sel = df["open_time"] >= D("2021-01-15")
    for k in ("open", "high", "low", "close"):
        df.loc[sel, k] = df.loc[sel, k] * 1000.0  # 1000:1 birleştirme (ters bölünme)
    f = Q.compute_flags(df, "XUSDT", CFG, "1d")
    s = rows(f, "split_candidate")
    assert len(s) == 1 and "k=-3" in s.loc[0, "detail"] and s.loc[0, "known_from"] == D("2021-01-15")
    # Normal günlerde oran ≈ 1 → k = 0 → aday yok
    assert len(rows(Q.compute_flags(make_series("2021-01-01", "2021-03-01"), "Y", CFG), "split_candidate")) == 0


# ---------------------------------------------------------------- kabul testi: tarih kesme değişmezi


def _upto(flags, T):
    return Q.normalize_flags(flags.loc[flags["known_from"] <= T])


@pytest.mark.parametrize("maker,sym", [(series_aaa, "AAAUSDT"), (series_bbb, "BBBUSDT")])
def test_truncation_invariance_every_day(maker, sym):
    """Veri T'de kesildiğinde known_from ≤ T işaretleri tam veriyle birebir aynı (sıfır hacim dizisi ve boşluk
    T'yi aşarken dahil). T her gün için denenir."""
    df = maker()
    full = Q.compute_flags(df, sym, CFG, "1d", DATA_END)
    lab = df["open_time"].dt.floor("D")
    checked_straddle = {"zero": False, "gap": False}
    for T in pd.date_range(lab.min() - DAY, DATA_END + 2 * DAY, unit="ns"):
        trunc = Q.compute_flags(df.loc[lab <= T], sym, CFG, "1d", min(T, DATA_END))
        a, b = _upto(full, T), _upto(trunc, T)
        assert a.equals(b), f"{sym} T={T:%Y-%m-%d}\nfull:\n{a}\ntrunc:\n{b}"
        checked_straddle["zero"] |= sym == "AAAUSDT" and D("2020-02-10") <= T < D("2020-02-14")
        checked_straddle["gap"] |= sym == "AAAUSDT" and D("2020-03-10") <= T < D("2020-03-16")
    if sym == "AAAUSDT":
        assert all(checked_straddle.values())


def test_future_corruption_does_not_change_past_flags():
    df = series_aaa()
    rng = np.random.default_rng(7)
    T = D("2020-03-12")  # boşluğun içinde
    full = Q.compute_flags(df, "A", CFG, "1d", DATA_END)
    bad = df.copy()
    fut = bad["open_time"] > T
    for k in ("open", "high", "low", "close", "volume"):
        bad.loc[fut, k] = rng.uniform(0, 1e6, fut.sum())
    bad = bad.loc[~(fut & (rng.uniform(size=len(bad)) < 0.3))]  # gelecekte rastgele satır sil
    corrupted = Q.compute_flags(bad, "A", CFG, "1d", DATA_END)
    assert _upto(full, T).equals(_upto(corrupted, T))


def test_flags_known_at_uses_t_minus_one(flags_aaa):
    k = Q.flags_known_at(flags_aaa, "2020-02-13")
    z = rows(k, "zero_volume")
    assert list(z["period_start"]) == list(pd.date_range("2020-02-10", "2020-02-12", unit="ns"))
    assert (k["known_from"] <= D("2020-02-12")).all()


def test_usable_days_and_clean_day_counts():
    a, b = series_aaa(), series_bbb()
    flags = pd.concat([Q.compute_flags(a, "A", CFG, "1d", DATA_END), Q.compute_flags(b, "B", CFG, "1d", DATA_END)])
    close = pd.concat({"A": a.set_index(a["open_time"].dt.floor("D"))["close"],
                       "B": b.set_index(b["open_time"].dt.floor("D"))["close"]}, axis=1, sort=True)
    asof = D("2020-02-14")
    u = Q.usable_days(close, flags, asof)
    assert u.index.max() == asof
    # A: 01-01..02-14 = 45 mum; yarım gün (01-01) ve sıfır hacim 02-10..02-13 (known_from ≤ asof−1 = 02-13) düşer → 40.
    # 02-14 sıfır hacim günü known_from=02-14 > asof−1 → henüz bilinmiyor, temiz sayılır.
    assert int(u["A"].sum()) == 45 - 1 - 4
    assert not u.loc[D("2020-02-12"), "A"] and u.loc[D("2020-02-14"), "A"]
    # B: 02-01..02-14 = 14 mum, ilk gün yarım → 13.
    assert Q.clean_day_counts(close, flags, asof).to_dict() == {"A": 40, "B": 13}
    # Bir gün sonra 02-14 de bilinir.
    assert not Q.usable_days(close, flags, D("2020-02-15")).loc[D("2020-02-14"), "A"]
    # Boşluk günleri mum olmadığı için sayılmaz; aşırı getiri/iğne günleri temiz kalır.
    u2 = Q.usable_days(close, flags, D("2020-04-30"))
    assert not u2.loc[D("2020-03-12"), "A"] and u2.loc[D("2020-04-01"), "A"] and u2.loc[D("2020-04-20"), "A"]


def test_clean_low_high_never_uses_wick():
    df = series_aaa()
    cl = Q.clean_low_high(df, CFG)
    i = df.index[df["open_time"] == D("2020-04-01")][0]
    assert cl.loc[i, "low"] == min(df.loc[i, "open"], df.loc[i, "close"])
    j = df.index[df["open_time"] == D("2020-04-02")][0]
    assert cl.loc[j, "low"] == df.loc[j, "low"] and cl.loc[j, "high"] == df.loc[j, "high"]
    assert Q.wick_mask(df, CFG)["low_wick"].sum() == 1


def test_flags_to_assets_asof_mapping():
    flags = pd.DataFrame({
        "symbol": ["LUNAUSDT", "LUNAUSDT", "LUNAUSDT", "RNDRUSDT"],
        "check": ["half_day", "missing_days", "half_day", "extreme_return"],
        "period_start": [D("2020-08-21"), D("2022-05-14"), D("2022-05-31"), D("2021-01-05")],
        "period_end": [D("2020-08-21"), D("2022-05-30"), D("2022-05-31"), D("2021-01-05")],
        "known_from": [D("2020-08-21"), D("2022-05-31"), D("2022-05-31"), D("2021-01-05")],
        "severity": ["flag"] * 4, "detail": ["a", "b", "c", "d"],
    })
    seg = pd.DataFrame({
        "asset_id": ["LUNAUSDT_until_20220513", "LUNAUSDT", "RENDERUSDT", "RENDERUSDT"],
        "source_symbol": ["LUNAUSDT", "LUNAUSDT", "RNDRUSDT", "RENDERUSDT"],
        "start": ["2020-08-21 00:00:00", "2022-05-31 00:00:00", "2020-06-11 00:00:00", "2024-07-26 00:00:00"],
        "end": ["2022-05-13 00:00:00", "2026-11-01 00:00:00", "2024-07-22 00:00:00", "2026-11-01 00:00:00"],
        "ratio": [1.0, 1.0, 1.0, 1.0],
    })
    m = Q.flags_to_assets(flags, seg).set_index("detail")["symbol"].to_dict()
    assert m == {"a": "LUNAUSDT_until_20220513", "b": "LUNAUSDT_until_20220513", "c": "LUNAUSDT", "d": "RENDERUSDT"}


def test_1h_structural_checks():
    df = make_series("2021-01-01", "2021-01-03 23:00", interval="1h")
    df = df.loc[~df["open_time"].between(D("2021-01-02 05:00"), D("2021-01-02 07:00"))]
    f = Q.compute_flags(df, "XUSDT", CFG, "1h")
    g = rows(f, "missing_hours")
    assert len(g) == 1 and "n_missing=3" in g.loc[0, "detail"] and g.loc[0, "known_from"] == D("2021-01-02")
    assert set(f["check"]) == {"missing_hours"}


def test_flags_hash_deterministic(flags_aaa):
    again = Q.compute_flags(series_aaa(), "AAAUSDT", CFG, "1d", DATA_END)
    assert Q.flags_hash(flags_aaa) == Q.flags_hash(again.sample(frac=1, random_state=1))


# ---------------------------------------------------------------- REST karşılaştırma (ağsız)


def test_parse_and_compare_rest():
    df = make_series("2021-01-01", "2021-01-03")
    rest_raw = [[int(t.value // 10**6), f"{o}", f"{h}", f"{l}", f"{c}", f"{v}", int(t.value // 10**6) + 86399999, f"{qv}", int(n), f"{tb}", f"{tq}", "0"]
                for t, o, h, l, c, v, qv, n, tb, tq in zip(df["open_time"], df["open"], df["high"], df["low"], df["close"], df["volume"],
                                                          df["quote_volume"], df["number_of_trades"], df["taker_buy_base"], df["taker_buy_quote"])]
    rest = Q.parse_rest_klines(rest_raw)
    assert rest["open_time"].dtype == "datetime64[ns]" and rest["open_time"].iloc[0] == D("2021-01-01")
    res = Q.compare_with_rest("XUSDT", df, rest)
    assert res["match"].all() and len(res) == 3 * len(Q.REST_FIELDS)
    rest.loc[1, "close"] *= 1.001
    res = Q.compare_with_rest("XUSDT", df, rest.iloc[:2])
    bad = res.loc[~res["match"]]
    assert set(zip(bad["open_time"], bad["field"])) == {(D("2021-01-02"), "close"), (D("2021-01-03"), "row")}


@pytest.mark.network
def test_rest_klines_reachable_and_ms():
    import requests

    r = requests.get(CFG["data"]["rest_base"] + "/api/v3/klines",
                     params={"symbol": "BTCUSDT", "interval": "1d", "startTime": 1577836800000, "limit": 2}, timeout=20)
    r.raise_for_status()
    k = Q.parse_rest_klines(r.json())
    assert list(k["open_time"]) == [D("2020-01-01"), D("2020-01-02")]


# ---------------------------------------------------------------- uçtan uca (sentetik data/clean ile CLI fonksiyonları)


def test_end_to_end_flags_report_candidates(tmp_path):
    """run_flags → write_report → find_candidates → build_merged zinciri gerçek dizin düzeniyle çalışır."""
    import shutil

    from trend import meta as M

    clean = tmp_path / "clean" / "1d"
    clean.mkdir(parents=True)
    (tmp_path / "meta").mkdir()
    shutil.copy(M.ROOT / "meta" / "symbol_map.csv", tmp_path / "meta" / "symbol_map.csv")
    w = make_series("2025-09-01", "2025-10-31", p0=4000.0, seed=5)
    i = w.index[w["open_time"] == D("2025-10-10")][0]
    w.loc[i, "low"] = 430.0  # bilinen wBETH iğnesi
    w.to_parquet(clean / "WBETHUSDT.parquet", index=False)
    make_series("2025-01-01", "2025-10-31", p0=60000.0, seed=6).to_parquet(clean / "BTCUSDT.parquet", index=False)
    make_series("2025-01-01", "2025-10-31", p0=60000.0, seed=6).to_parquet(clean / "BTCFDUSD.parquet", index=False)
    old = make_series("2025-01-01", "2025-03-01", p0=1.0, seed=7)  # biten çift
    old.to_parquet(clean / "XOLDUSDT.parquet", index=False)
    new = make_series("2025-03-04", "2025-10-31", p0=old["close"].iloc[-1] / 100.0, seed=8)  # 1:100, 3 gün sonra
    new.to_parquet(clean / "XNEWUSDT.parquet", index=False)
    pd.DataFrame({"symbol": ["BTCUSDT", "BTCUSDT"], "interval": ["1d", "1d"], "open_time": ["2025-05-05", "2025-06-06"],
                  "kind": ["conflict", "exact"], "n": [2, 2], "sources": ["a;b", "a;b"]}).to_csv(clean / "_duplicates.csv", index=False)
    cfg = load_settings({"paths": {"clean": str(tmp_path / "clean"), "quality_flags": str(tmp_path / "qf.parquet"),
                                   "reports": str(tmp_path / "reports"), "meta": str(tmp_path / "meta"),
                                   "merged": str(tmp_path / "merged")}})
    flags = Q.run_flags(cfg)
    assert (tmp_path / "qf.parquet").exists() and Q.flags_hash(Q.load_flags(cfg)) == Q.flags_hash(flags)
    wick = flags.loc[(flags["symbol"] == "WBETHUSDT") & (flags["check"] == "extreme_wick")]
    assert list(wick["period_start"]) == [D("2025-10-10")]
    # Hâlâ işlem gören çiftlerin son mumu yarım gün sayılmaz; biten XOLD'unki sayılır
    hd = flags.loc[flags["check"] == "half_day"]
    last = hd.loc[hd["detail"].str.contains("half_day_column")]
    assert list(last["symbol"]) == ["XOLDUSDT"] and last["known_from"].iloc[0] == D("2025-03-02")
    dup = flags.loc[flags["check"] == "duplicate_open_time"]
    assert list(zip(dup["symbol"], dup["period_start"], dup["severity"])) == [("BTCUSDT", D("2025-05-05"), "error")]
    rep = Q.write_report(cfg).read_text(encoding="utf-8")
    assert "conflict 1" in rep and "exact 1" in rep
    assert "WBETHUSDT | 430.0 | 430.0" in rep and "| True |" in rep and "GEÇTİ" in rep
    cand = M.find_candidates(cfg)
    assert ("XOLDUSDT", "XNEWUSDT") in set(zip(cand["old_symbol"], cand["new_symbol"]))
    seg = M.build_merged("1d", cfg)
    assert set(seg["asset_id"]) == {"WBETHUSDT", "BTCUSDT", "XOLDUSDT", "XNEWUSDT"}  # FDUSD çifti birleştirilmez
