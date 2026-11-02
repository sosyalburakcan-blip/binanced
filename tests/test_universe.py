"""G6 kabul testleri: geleceği görme, meta veri sızıntısı, isim dışlaması, stablecoin çevrimi, kampanya, max kuralı,
365 gün, kademeler, N varyantları, performans. Tüm veriler sentetiktir (CONTRACTS biçimlerinde)."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from trend import universe as U
from trend.config import load_settings

CFG = load_settings()
M = 1e6


# --- sentetik veri -------------------------------------------------------------------------------------------------

def mark_half(df: pd.DataFrame) -> pd.DataFrame:
    """CONTRACTS §3: her çiftin (source_symbol koşusu) ilk ve son mumu half_day."""
    df = df.sort_values("open_time").reset_index(drop=True)
    src = df["source_symbol"].to_numpy(object)
    h = np.zeros(len(df), bool)
    if len(df):
        chg = np.r_[True, src[1:] != src[:-1]]
        h |= chg
        h |= np.r_[chg[1:], True]
    return df.assign(half_day=h)


def asset(start, end, qv=10 * M, vol=0.04, seed=0, p0=100.0, source=None, symbol="X"):
    days = pd.date_range(start, end, freq="D")
    rng = np.random.default_rng(seed)
    close = p0 * np.exp(np.cumsum(rng.normal(0.0, vol, len(days))))
    q = np.broadcast_to(np.asarray(qv, float), (len(days),)).copy()
    src = source if source is not None else symbol
    df = pd.DataFrame({"open_time": days, "close": close, "quote_volume": q,
                       "source_symbol": np.broadcast_to(np.asarray(src, object), (len(days),)).copy()})
    return mark_half(df)


def pair(start, end, qv):
    days = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"open_time": days, "quote_volume": np.broadcast_to(np.asarray(qv, float), (len(days),)).copy()})


def stable(start, end, px=1.0):
    days = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"open_time": days, "close": np.broadcast_to(np.asarray(px, float), (len(days),)).copy()})


def flag(symbol, start, end, known, severity="exclude", check="zero_volume"):
    return {"symbol": symbol, "check": check, "period_start": pd.Timestamp(start), "period_end": pd.Timestamp(end),
            "known_from": pd.Timestamp(known), "severity": severity, "detail": ""}


def flags_df(rows):
    cols = ["symbol", "check", "period_start", "period_end", "known_from", "severity", "detail"]
    return pd.DataFrame(rows, columns=cols)


def promos_df(rows):
    df = pd.DataFrame(rows, columns=["symbol", "start", "end", "source"])
    return df.assign(start=pd.to_datetime(df["start"]), end=pd.to_datetime(df["end"]))


def build(merged, month, other=None, stables=None, promos=None, flags=None, size=None, liquidity="max", cfg=CFG):
    data = U.prepare_data(merged, other_quote=other, stable_closes=stables, promotions=promos, cfg=cfg)
    return U.build_universe_month(data, month, cfg=cfg, flags=flags, size=size, liquidity=liquidity)


def syms(df):
    return list(df["symbol"])


# --- yardımcı fonksiyonlar -----------------------------------------------------------------------------------------

def test_base_asset_and_timing_helpers():
    assert U.base_asset("BTCUSDT") == "BTC"
    assert U.base_asset("RENDERUSDT") == "RENDER"
    assert U.base_asset("LUNAUSDT_until_20220513") == "LUNA"
    assert U.split_other_quote("ETHFDUSD", ["BUSD", "FDUSD", "USDC", "TUSD"]) == ("ETH", "FDUSD")
    assert U.split_other_quote("BTCTUSD", ["BUSD", "FDUSD", "USDC", "TUSD"]) == ("BTC", "TUSD")
    assert U.split_other_quote("USDCUSDT", ["BUSD", "FDUSD", "USDC", "TUSD"]) is None
    assert U.decision_time("2020-03") == pd.Timestamp("2020-02-29")
    assert U.decision_time("2021-01") == pd.Timestamp("2020-12-31")
    assert U.universe_month_for_decision_day("2020-02-29") == "2020-03"   # T → yeni ayın evreni
    assert U.universe_month_for_decision_day("2020-02-28") == "2020-02"
    assert U.universe_month_for_decision_day(pd.Timestamp("2020-12-31")) == "2021-01"


def test_size_for_capital_and_default_sizes():
    assert U.size_for_capital(2000, CFG) == 10
    assert U.size_for_capital(2999.99, CFG) == 10
    assert U.size_for_capital(3000, CFG) == 20
    assert U.size_for_capital(14999, CFG) == 20
    assert U.size_for_capital(20000, CFG) == 30
    assert U.default_sizes(CFG) == [10, 20, 30, 50]


# --- isim dışlaması ve stablecoin yedeği ---------------------------------------------------------------------------

def test_name_list_exclusion_and_stable_fallback():
    s, e = "2018-01-01", "2019-06-30"
    merged = {f"{b}USDT": asset(s, e, qv=50 * M, seed=i, symbol=f"{b}USDT")
              for i, b in enumerate(["BTC", "ETH", "JUP", "BTCUP", "BNB", "WBTC", "FTT", "PAXG", "ETHDOWN"])}
    merged["USDCUSDT"] = asset(s, e, qv=50 * M, vol=0.0005, p0=1.0, symbol="USDCUSDT")
    merged["NEWSTABLEUSDT"] = asset(s, e, qv=50 * M, vol=0.0005, p0=1.0, symbol="NEWSTABLEUSDT")  # listede yok
    merged["CALMUSDT"] = asset(s, e, qv=50 * M, vol=0.005, symbol="CALMUSDT")    # non-A, std < %1 → yedekle çıkar
    merged["BTCUSDT"] = asset(s, e, qv=60 * M, vol=0.005, symbol="BTCUSDT")      # A kademesi yedekten muaf
    out = build(merged, "2019-07")
    assert set(syms(out)) == {"BTCUSDT", "ETHUSDT", "JUPUSDT"}


def test_name_exclusion_uses_source_symbol_at_T():
    s, e = "2018-01-01", "2019-06-30"
    a = asset(s, e, qv=50 * M, symbol="XYZUSDT")
    a.loc[a["open_time"] >= "2019-06-01", "source_symbol"] = "BTCUPUSDT"   # T'de kaynak çift listede
    merged = {"BTCUSDT": asset(s, e, qv=60 * M, symbol="BTCUSDT"), "XYZUSDT": mark_half(a)}
    assert syms(build(merged, "2019-07")) == ["BTCUSDT"]


# --- likidite: çevrim, max kuralı, kampanya ------------------------------------------------------------------------

T_JUN = pd.Timestamp("2019-06-30")   # 2019-07 evreninin karar günü


def _liq_world(busd_px=0.9):
    s, e = "2018-01-01", "2019-08-31"
    merged = {"BTCUSDT": asset(s, e, qv=100 * M, symbol="BTCUSDT"), "XYZUSDT": asset(s, e, qv=1 * M, symbol="XYZUSDT")}
    other = {"XYZBUSD": pair(s, e, 10 * M), "XYZFDUSD": pair(s, e, 7 * M), "XYZTUSD": pair(s, e, 3 * M)}
    stables = {"BUSDUSDT": stable(s, e, busd_px), "FDUSDUSDT": stable(s, e, 1.0), "TUSDUSDT": stable(s, e, 1.0)}
    return merged, other, stables


def _med(df, sym):
    return float(df.loc[df["symbol"] == sym, "median_liquidity"].iloc[0])


def test_stablecoin_conversion_and_max_not_sum():
    merged, other, stables = _liq_world(0.9)
    out = build(merged, "2019-07", other, stables)
    assert _med(out, "XYZUSDT") == pytest.approx(9 * M)          # max(1, 10×0.9, 7, 3), toplam (18M) değil
    usdt = build(merged, "2019-07", other, stables, liquidity="usdt")
    assert syms(usdt) == ["BTCUSDT"]                              # T7: XYZ yalnız 1M USDT hacmi
    # max kuralı eşiği belirler: 4 + 3 + 3 = 10M toplanırsa geçerdi, max = 4M < 5M → elenir
    merged["XYZUSDT"] = asset("2018-01-01", "2019-08-31", qv=4 * M, symbol="XYZUSDT")
    other = {"XYZBUSD": pair("2018-01-01", "2019-08-31", 3 * M), "XYZTUSD": pair("2018-01-01", "2019-08-31", 3 * M)}
    assert syms(build(merged, "2019-07", other, stables)) == ["BTCUSDT"]


def test_conversion_uses_only_past_closes():
    merged, other, stables = _liq_world(0.9)
    st = stables["BUSDUSDT"]
    st = st[(st["open_time"] < T_JUN - pd.Timedelta(days=2)) | (st["open_time"] > T_JUN)]  # T−2..T kapanışı yok
    st.loc[st["open_time"] > T_JUN, "close"] = 5.0             # T sonrası kapanış kullanılmamalı
    out = build(merged, "2019-07", other, {**stables, "BUSDUSDT": st})
    assert _med(out, "XYZUSDT") == pytest.approx(9 * M)
    # hiç BUSDUSDT yoksa BUSD çifti sayılmaz → max(1, 7, 3) = 7M
    with pytest.warns(UserWarning):
        out = build(merged, "2019-07", other, {k: v for k, v in stables.items() if k != "BUSDUSDT"})
    assert _med(out, "XYZUSDT") == pytest.approx(7 * M)


def test_promotion_pairs_excluded_only_during_window():
    merged, other, stables = _liq_world(1.0)
    # tüm pencere boyunca kampanya → BUSD dışarıda → max(1, 7, 3) = 7M
    p = promos_df([("XYZBUSD", "2019-05-01", "2019-07-31", "test")])
    assert _med(build(merged, "2019-07", other, stables, p), "XYZUSDT") == pytest.approx(7 * M)
    # son 20 gün kampanya: 10 gün 10M, 20 gün 7M → medyan 7M; son 10 gün: 20 gün 10M → medyan 10M
    p20 = promos_df([("XYZBUSD", T_JUN - pd.Timedelta(days=19), None, "test")])
    assert _med(build(merged, "2019-07", other, stables, p20), "XYZUSDT") == pytest.approx(7 * M)
    p10 = promos_df([("XYZBUSD", T_JUN - pd.Timedelta(days=9), "2019-12-31", "test")])
    assert _med(build(merged, "2019-07", other, stables, p10), "XYZUSDT") == pytest.approx(10 * M)
    # kampanya pencereden önce bittiyse veya T'den sonra başlıyorsa etkisi yok
    pout = promos_df([("XYZBUSD", "2018-06-01", "2019-05-15", "t"), ("XYZBUSD", "2019-07-01", None, "t")])
    assert _med(build(merged, "2019-07", other, stables, pout), "XYZUSDT") == pytest.approx(10 * M)
    # USDT çiftinin kampanyası USDT hacmini dışlamaz
    pu = promos_df([("BTCUSDT", "2019-01-01", None, "t"), ("XYZUSDT", "2019-01-01", None, "t")])
    out = build(merged, "2019-07", other, stables, pu, liquidity="usdt")
    assert _med(out, "BTCUSDT") == pytest.approx(100 * M)


def test_other_quote_pairs_follow_symbol_segments():
    s, e = "2018-01-01", "2019-08-31"
    ren = asset(s, e, qv=1 * M, symbol="RENDERUSDT")
    ren.loc[ren["open_time"] <= "2019-03-31", "source_symbol"] = "RNDRUSDT"
    ren = mark_half(ren[(ren["open_time"] <= "2019-03-31") | (ren["open_time"] >= "2019-04-04")])
    old = asset(s, "2019-05-13", qv=1 * M, symbol="LUNAUSDT")
    new = asset("2019-05-31", e, qv=1 * M, symbol="LUNAUSDT")
    merged = {"BTCUSDT": asset(s, e, symbol="BTCUSDT"), "RENDERUSDT": ren,
              "LUNAUSDT_until_20190513": old, "LUNAUSDT": new}
    other = {"RNDRBUSD": pair(s, e, 20 * M), "LUNABUSD": pair(s, e, 30 * M)}
    data = U.prepare_data(merged, other, {"BUSDUSDT": stable(s, e)}, cfg=CFG)
    oq = pd.DataFrame(data.other_qv, index=pd.DatetimeIndex(data.dates), columns=data.assets)
    assert (oq.loc[:"2019-03-31", "RENDERUSDT"] == 20 * M).all()      # RNDR segmenti
    assert oq.loc["2019-04-01":, "RENDERUSDT"].isna().all()           # RENDER segmentinde RNDRBUSD sayılmaz
    assert (oq.loc[:"2019-05-13", "LUNAUSDT_until_20190513"] == 30 * M).all()
    assert oq.loc["2019-05-14":, "LUNAUSDT_until_20190513"].isna().all()
    assert oq.loc[:"2019-05-30", "LUNAUSDT"].isna().all() and (oq.loc["2019-05-31":, "LUNAUSDT"] == 30 * M).all()


# --- 365 temiz gün ve meta veri sızıntısı --------------------------------------------------------------------------

def _age_world(n_days):
    """XYZ'nin T'de tam n_days mumu var (ilk mum half_day)."""
    start = T_JUN - pd.Timedelta(days=n_days - 1)
    return {"BTCUSDT": asset("2017-08-17", "2019-08-31", qv=100 * M, symbol="BTCUSDT"),
            "XYZUSDT": asset(start, "2019-08-31", qv=20 * M, symbol="XYZUSDT")}


def test_365_clean_day_rule_counts_half_days_out():
    assert "XYZUSDT" not in syms(build(_age_world(365), "2019-07"))   # 365 mum − 1 half_day = 364
    assert "XYZUSDT" in syms(build(_age_world(366), "2019-07"))       # 365 temiz gün


def test_half_day_mark_on_T_is_ignored():
    w = _age_world(366)
    x = w["XYZUSDT"]
    w["XYZUSDT"] = x.assign(half_day=x["half_day"] | (x["open_time"] == T_JUN))  # veri T'de kesilmiş gibi
    assert "XYZUSDT" in syms(build(w, "2019-07"))


def test_quality_flags_respect_known_from_and_severity():
    w = _age_world(376)                                   # 375 temiz gün
    p0, p1 = "2019-01-01", "2019-01-20"                   # 20 gün → 355
    t1 = T_JUN - pd.Timedelta(days=1)
    for sev, known, inside in [("exclude", t1, False), ("error", t1, False), ("flag", t1, True),
                               ("exclude", T_JUN, True), ("exclude", "2023-05-01", True)]:
        f = flags_df([flag("XYZUSDT", p0, p1, known, sev)])
        assert ("XYZUSDT" in syms(build(w, "2019-07", flags=f))) is inside, (sev, known)
    # asset_id ile eşleşen işaret de sayılır; başka çiftin işareti sayılmaz
    assert "XYZUSDT" not in syms(build(w, "2019-07", flags=flags_df([flag("XYZUSDT", p0, p1, t1)])))
    assert "XYZUSDT" in syms(build(w, "2019-07", flags=flags_df([flag("XYZBUSD", p0, p1, t1)])))


def test_meta_leak_flag_known_after_T_minus_1_has_no_effect():
    """known_from > T−1 olan işaret ay M'yi etkilemez; ay M+1'i etkileyebilir."""
    w = _age_world(376)
    f = flags_df([flag("XYZUSDT", "2019-01-01", "2019-01-20", known=T_JUN, severity="exclude")])
    assert build(w, "2019-07", flags=f).equals(build(w, "2019-07"))
    assert "XYZUSDT" not in syms(build(w, "2019-08", flags=flags_df(
        [flag("XYZUSDT", "2019-01-01", "2019-03-31", known=T_JUN, severity="exclude")])))


# --- kademeler, tavanlar, kayma, N varyantları ---------------------------------------------------------------------

def _tier_world():
    s, e = "2018-01-01", "2019-06-30"
    levels = {"BTCUSDT": 500 * M, "AAAUSDT": 300 * M, "ETHUSDT": 250 * M, "HUNUSDT": 100 * M, "BELUSDT": 99 * M,
              "TWEUSDT": 20 * M, "SUBUSDT": 19.9 * M}
    levels |= {f"C{i:02d}USDT": (18 - 0.3 * i) * M for i in range(28)}      # 18M … 9.9M
    levels |= {"LOWUSDT": 4.9 * M}
    return {k: asset(s, e, qv=v, seed=i, symbol=k) for i, (k, v) in enumerate(levels.items())}


def test_tiers_caps_slippage():
    w = _tier_world()
    out = build(w, "2019-07", size=30).set_index("symbol")
    assert list(out.index[:3]) == ["BTCUSDT", "AAAUSDT", "ETHUSDT"] and list(out["rank"]) == list(range(1, 31))
    assert tuple(out.loc["BTCUSDT", ["tier", "cap", "slippage"]]) == ("A", 0.10, 0.0005)
    assert tuple(out.loc["ETHUSDT", ["tier", "cap", "slippage"]]) == ("A", 0.10, 0.0005)
    assert tuple(out.loc["AAAUSDT", ["tier", "cap", "slippage"]]) == ("B", 0.05, 0.0005)   # sıra 2, A değil → B
    assert out.loc["HUNUSDT", "slippage"] == 0.0005 and out.loc["BELUSDT", "slippage"] == 0.0010
    assert out.loc["TWEUSDT", "slippage"] == 0.0010 and out.loc["SUBUSDT", "slippage"] == 0.0020
    assert set(out.loc[out["rank"] <= 20, "tier"]) == {"A", "B"}
    assert set(out.loc[out["rank"] > 20, "tier"]) == {"C"} and set(out.loc[out["rank"] > 20, "cap"]) == {0.03}
    assert "LOWUSDT" not in out.index                    # < 5M
    t, c, s = U.assign_tiers(["ETH"], [7], [6 * M], CFG)   # A kaymasi likiditeden bağımsız
    assert (t, c, s) == (["A"], [0.10], [0.0005])


def test_size_variants_are_prefixes():
    w = _tier_world()
    data = U.prepare_data(w, cfg=CFG)
    b = U.build_universes(data, months=["2019-07"], cfg=CFG, sizes=[10, 20, 30, 50])
    full = b.tables["size_50"]["2019-07"]
    assert len(full) == 35                               # 36 coin, LOW < 5M
    assert len(b.tables["main"]["2019-07"]) == 20 and set(b.tables["main"]["2019-07"]["tier"]) == {"A", "B"}
    for n in (10, 30):
        assert b.tables[f"size_{n}"]["2019-07"].equals(full.head(n))
    assert b.tables["main"]["2019-07"].equals(full.head(20))
    with pytest.raises(ValueError):
        U.build_universes(data, months=["2019-07"], cfg=CFG, size=60)


# --- geleceği görme ------------------------------------------------------------------------------------------------

def _world(seed=7):
    rng = np.random.default_rng(seed)
    s, e = "2018-01-01", "2020-12-31"
    days = pd.date_range(s, e, freq="D")
    merged = {"BTCUSDT": asset(s, e, qv=300 * M * rng.lognormal(0, 0.3, len(days)), seed=1, symbol="BTCUSDT"),
              "ETHUSDT": asset(s, e, qv=150 * M * rng.lognormal(0, 0.3, len(days)), seed=2, symbol="ETHUSDT"),
              "BNBUSDT": asset(s, e, qv=80 * M, seed=3, symbol="BNBUSDT")}
    starts = pd.to_datetime(rng.choice(pd.date_range("2018-01-01", "2019-10-01", freq="D"), 22))
    for i, st in enumerate(starts):
        sym = f"C{i:02d}USDT"
        end = "2019-11-15" if i == 5 else e
        n = len(pd.date_range(st, end, freq="D"))
        lvl = np.exp(rng.uniform(np.log(1.5 * M), np.log(60 * M)))
        merged[sym] = asset(st, end, qv=lvl * rng.lognormal(0, 0.6, n), seed=10 + i, symbol=sym)
    ren = asset(s, e, qv=8 * M * rng.lognormal(0, 0.5, len(days)), seed=99, symbol="RENDERUSDT")
    ren.loc[ren["open_time"] <= "2019-06-30", "source_symbol"] = "RNDRUSDT"
    merged["RENDERUSDT"] = mark_half(ren[(ren["open_time"] <= "2019-06-30") | (ren["open_time"] >= "2019-07-03")])
    other = {f"{b}{q}": pair(s, e, rng.lognormal(np.log(6 * M), 0.7, len(days)))
             for b, q in [("C03", "BUSD"), ("C07", "TUSD"), ("C10", "USDC"), ("RNDR", "BUSD"), ("BTC", "BUSD"),
                          ("C12", "FDUSD")]}
    stables = {"BUSDUSDT": stable("2018-06-01", e, 1.0 + rng.normal(0, 0.001, len(pd.date_range("2018-06-01", e)))),
               "TUSDUSDT": stable(s, e, 0.999), "USDCUSDT": stable(s, e, 1.001), "FDUSDUSDT": stable(s, e, 1.0)}
    promos = promos_df([("BTCBUSD", "2019-07-01", "2019-12-31", "t"), ("C03BUSD", "2020-01-15", "2020-02-15", "t"),
                        ("C07TUSD", "2019-03-20", None, "t"), ("C10USDC", "2019-01-20", "2020-03-10", "t")])
    fl = []
    names = list(merged)
    for _ in range(60):
        sym = names[rng.integers(len(names))]
        p0 = pd.Timestamp("2018-01-01") + pd.Timedelta(days=int(rng.integers(0, 1000)))
        p1 = p0 + pd.Timedelta(days=int(rng.integers(0, 40)))
        fl.append(flag(sym, p0, p1, p1 + pd.Timedelta(days=int(rng.integers(0, 60))),
                       ["exclude", "error", "flag"][rng.integers(3)]))
    fl.append(flag("RNDRUSDT", "2018-03-01", "2018-03-10", "2018-03-11"))
    return merged, other, stables, promos, flags_df(fl)


def _truncate(world, t_day):
    merged, other, stables, promos, fl = world
    cut = lambda d: {k: v[v["open_time"] <= t_day] for k, v in d.items() if (v["open_time"] <= t_day).any()}
    m2 = {k: mark_half(v) for k, v in cut(merged).items()}            # temiz katman T'de yeniden kurulmuş gibi
    pr = promos[promos["start"] <= t_day].copy()
    pr.loc[pr["end"] > t_day, "end"] = pd.NaT                          # bitişi henüz bilinmiyor
    return m2, cut(other), cut(stables), pr, fl[fl["known_from"] <= t_day - pd.Timedelta(days=1)]


def _perturb(world, t_day, seed):
    rng = np.random.default_rng(seed)
    merged, other, stables, promos, fl = world
    after = lambda df: df["open_time"] > t_day

    def jig(df, cols):
        df = df.copy()
        k = after(df)
        for c in cols:
            df.loc[k, c] = df.loc[k, c] * rng.lognormal(0, 2.0, int(k.sum()))
        return df

    m2 = {}
    for name, df in merged.items():
        df = jig(df, ["close", "quote_volume"])
        df.loc[after(df), "half_day"] = rng.random(int(after(df).sum())) < 0.3
        m2[name] = df
    df = m2["C01USDT"].copy()
    df.loc[after(df), "source_symbol"] = "BTCUPUSDT"                  # T sonrası kaynak değişimi
    m2["C01USDT"] = df
    m2["LATEUSDT"] = asset(t_day + pd.Timedelta(days=1), "2020-12-31", qv=900 * M, symbol="LATEUSDT")
    o2 = {k: jig(v, ["quote_volume"]) for k, v in other.items()}
    o2["LATEBUSD"] = pair(t_day + pd.Timedelta(days=1), "2020-12-31", 900 * M)
    s2 = {k: jig(v, ["close"]) for k, v in stables.items()}
    pr = promos.copy()
    span = (pr["start"] <= t_day) & (pr["end"] > t_day)
    pr.loc[span, "end"] = t_day + pd.Timedelta(days=int(rng.integers(1, 200)))
    pr = pd.concat([pr, promos_df([(p, t_day + pd.Timedelta(days=int(rng.integers(1, 30))), None, "x")
                                   for p in other])], ignore_index=True)
    names = list(merged)
    new = [flag(names[rng.integers(len(names))], "2018-01-01", t_day + pd.Timedelta(days=100),
                t_day + pd.Timedelta(days=int(rng.integers(0, 50))), "exclude") for _ in range(40)]
    late = fl["known_from"] >= t_day
    f2 = fl.copy()
    f2.loc[late, "period_start"] = pd.Timestamp("2018-01-01")
    f2.loc[late, "severity"] = "exclude"
    return m2, o2, s2, pr, pd.concat([f2, flags_df(new)], ignore_index=True)


def _all_variants(world, month):
    merged, other, stables, promos, fl = world
    data = U.prepare_data(merged, other, stables, promos, cfg=CFG)
    return U.build_universes(data, months=[month], cfg=CFG, flags=fl, sizes=[10, 20, 30, 50]).tables


@pytest.mark.parametrize("month", ["2019-04", "2019-08", "2019-12", "2020-01", "2020-02", "2020-07"])
def test_lookahead_data_after_T_does_not_change_universe(month):
    world = _world()
    t_day = U.decision_time(month)
    ref = _all_variants(world, month)
    assert len(ref["main"][month]) >= 5
    for alt in (_truncate(world, t_day), _perturb(world, t_day, seed=1), _perturb(world, t_day, seed=2)):
        got = _all_variants(alt, month)
        for variant in ref:
            pd.testing.assert_frame_equal(got[variant][month], ref[variant][month], check_exact=True)


# --- dosya G/Ç, adaptörler, rapor ----------------------------------------------------------------------------------

def test_disk_adapters_roundtrip_and_report(tmp_path):
    merged, other, stables, promos, fl = _world()
    mdir, cdir, meta = tmp_path / "data/merged/1d", tmp_path / "data/clean/1d", tmp_path / "meta"
    for d in (mdir, cdir, meta):
        d.mkdir(parents=True)
    for k, v in merged.items():          # CONTRACTS §3/§4 şemasına yakın: ek kolonlar okunmamalı
        v.assign(open=v["close"], high=v["close"], low=v["close"], volume=1.0, number_of_trades=10).to_parquet(
            mdir / f"{k}.parquet")
    for k, v in {**other, **stables}.items():
        v.to_parquet(cdir / f"{k}.parquet")
    pd.DataFrame({"open_time": pd.date_range("2018-01-01", periods=3), "quote_volume": 1e12}).to_parquet(
        cdir / "C03BTC.parquet")         # BTC quote: likiditeye girmez
    promos.to_csv(meta / "fee_promotions.csv", index=False)
    fl.to_parquet(tmp_path / "quality_flags.parquet")
    months = ["2019-06", "2019-07", "2019-08", "2020-01"]
    b = U.build_from_disk(CFG, merged_dir=mdir, clean_dir=cdir, flags_path=tmp_path / "quality_flags.parquet",
                          promotions_path=meta / "fee_promotions.csv", out_dir=tmp_path / "universe",
                          report_path=tmp_path / "G6_universe.md", months=months)
    mem = _all_variants((merged, other, stables, promos, fl), "2019-08")
    pd.testing.assert_frame_equal(b.tables["main"]["2019-08"], mem["main"]["2019-08"])
    for m in months:
        f = tmp_path / "universe" / f"{m}.csv"
        assert f.exists() and (tmp_path / "universe/usdt_only" / f"{m}.csv").exists()
        assert (tmp_path / "universe/size_50" / f"{m}.csv").exists()
        assert list(pd.read_csv(f).columns) == U.COLUMNS
        pd.testing.assert_frame_equal(U.load_universe(m, tmp_path / "universe"), b.tables["main"][m])
    got = U.universe_for_decision_day("2019-07-31", tmp_path / "universe")   # karar günü T → 2019-08 evreni
    pd.testing.assert_frame_equal(got, b.tables["main"]["2019-08"])
    got = U.universe_for_decision_day("2019-07-30", tmp_path / "universe", variant="usdt_only")
    pd.testing.assert_frame_equal(got, b.tables["usdt_only"]["2019-07"])
    with pytest.raises(FileNotFoundError):
        U.universe_for_decision_day("2021-06-30", tmp_path / "universe")
    txt = (tmp_path / "G6_universe.md").read_text(encoding="utf-8")
    assert "## Aylık" in txt and "| 2019-08 | 2019-07-31 |" in txt and "V11" in txt
    diag = pd.read_csv(tmp_path / "universe/diagnostics.csv")
    assert list(diag["month"]) == months and (diag["n_main"] <= 20).all()


def test_empty_month_writes_header_only(tmp_path):
    merged = {"BTCUSDT": asset("2018-01-01", "2018-03-31", symbol="BTCUSDT")}
    data = U.prepare_data(merged, cfg=CFG)
    b = U.build_universes(data, cfg=CFG)
    assert list(b.tables["main"]) == ["2018-02", "2018-03", "2018-04"]
    U.write_universes(b, tmp_path, CFG)
    assert (tmp_path / "2018-02.csv").read_text().strip() == ",".join(U.COLUMNS)
    assert U.load_universe("2018-02", tmp_path).empty


# --- performans ----------------------------------------------------------------------------------------------------

def test_performance_100_months_600_assets():
    rng = np.random.default_rng(0)
    days = pd.date_range("2017-08-17", "2026-10-31", freq="D")
    n = len(days)
    merged = {}
    for i in range(600):
        k0 = int(rng.integers(0, n - 60))
        k1 = n if rng.random() < 0.8 else int(rng.integers(k0 + 30, n))
        d = days[k0:k1]
        merged[f"A{i:03d}USDT"] = pd.DataFrame({
            "open_time": d, "close": 10 * np.exp(np.cumsum(rng.normal(0, 0.04, len(d)))),
            "quote_volume": np.exp(rng.normal(np.log(5 * M), 1.5)) * rng.lognormal(0, 0.5, len(d)),
            "half_day": np.r_[True, np.zeros(len(d) - 2, bool), True], "source_symbol": f"A{i:03d}USDT"})
    other = {f"A{i:03d}{q}": pd.DataFrame({"open_time": days, "quote_volume": rng.lognormal(np.log(3 * M), 1.0, n)})
             for i in range(0, 600, 2) for q in ("BUSD",)}
    stables = {"BUSDUSDT": pd.DataFrame({"open_time": days, "close": 1.0})}
    fl = flags_df([flag(f"A{rng.integers(600):03d}USDT", days[k], days[min(k + 5, n - 1)],
                        days[min(k + 10, n - 1)], "exclude") for k in rng.integers(0, n, 3000)])
    t0 = time.perf_counter()
    data = U.prepare_data(merged, other, stables, cfg=CFG)
    b = U.build_universes(data, cfg=CFG, flags=fl, sizes=[10, 20, 30, 50])
    elapsed = time.perf_counter() - t0
    print(f"\nperformans: {len(b.tables['main'])} ay × {len(merged)} varlık: {elapsed:.1f} s")
    assert len(b.tables["main"]) >= 100
    assert elapsed < 120
