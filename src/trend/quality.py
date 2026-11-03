"""G4 — Veri kalitesi denetimi (SPEC "Veri kalitesi ve meta tablolar", CONTRACTS §5).

İşaretler **tarihe bağlıdır**. Her satırın `known_from` alanı, işaretin yalnızca gün etiketi ≤ known_from olan
mumlardan üretilebildiği en erken gün etiketidir. Değişmez kural (G4 kabul testi): veri T'de kesilip işaretler
yeniden hesaplandığında known_from ≤ T olan satırlar, tam veriden hesaplananların known_from ≤ T olanlarıyla
**birebir** aynıdır. Bunu sağlamak için her satırın tüm alanları (dönem, ayrıntı) yalnızca gün etiketi ≤ known_from
olan mumlardan hesaplanır; geleceğe bağlı alan (ör. bir sıfır hacim dizisinin toplam uzunluğu) yazılmaz.

Satır tasarımı (varsayımlar):
- Satır-yerel kontroller (OHLC, zaman damgası, iğne, aşırı getiri, tekrar): etkilenen gün başına bir satır,
  known_from = o günün etiketi.
- Eksik gün: boşluk başına bir satır, known_from = seri yeniden başladığı gün. Seri hiç dönmezse boşluk değil
  sondur (delist kuralı motorda); T anında "biten" seriyle "boşluktaki" seri ayırt edilemediği için boşluk ancak
  dönüşte bilinir.
- Bölünme adayı: boşluk (veya ardışık iki mum) öncesi son kapanış / sonrası ilk açılış; known_from = sonraki mum günü.
- Sıfır hacim: etkilenen gün başına bir satır; dizinin ilk iki günü, dizinin 3. gününde bilinir
  (known_from = max(gün, dizi başı + 2 mum)). Ayrıntıda yalnızca dizi başlangıcı yazılır.
- Yarım gün: ilk mum (known_from = ilk gün); son mum temiz verinin `half_day` kolonundan okunur ve
  known_from = son gün + 1 (sonraki mumun gelmediği ilk gün). Son mumu veri sonu (data_end) olan, hâlâ işlem gören
  çift işaretlenmez.

Önem (severity): error = veri hatası, exclude = dönem dışlanır, flag = bilgi/ikinci kaynakla kontrol.
"Temiz/kullanılabilir gün" = mumu olan ve kararda bilinen error/exclude/yarım gün işaretiyle örtüşmeyen gün
(aşırı getiri, iğne, bölünme adayı, eksik gün işaretleri günü kirletmez: gerçek fiyat hareketleri silinmez).
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from trend.config import load_settings
from trend.config import path as cfg_path

FLAG_COLUMNS = ["symbol", "check", "period_start", "period_end", "known_from", "severity", "detail"]
DAY = pd.Timedelta(days=1)
INTERVAL_STEP = {"1d": pd.Timedelta(days=1), "1h": pd.Timedelta(hours=1)}
INTERVAL_FREQ = {"1d": "D", "1h": "h"}

SEVERITY = {
    "duplicate_open_time": "error",
    "ohlc_inconsistent": "error",
    "timestamp": "error",
    "missing_days": "flag",
    "missing_hours": "flag",
    "split_candidate": "flag",
    "zero_volume": "exclude",
    "extreme_return": "flag",
    "extreme_wick": "flag",
    "half_day": "flag",
}
# Kullanılabilir gün sayımında günü "kirli" yapan kontroller (varsayım; yukarıdaki modül açıklaması).
UNUSABLE_CHECKS = frozenset({"duplicate_open_time", "ohlc_inconsistent", "timestamp", "zero_volume", "half_day"})

# Binance spot 2017-07-14'te açıldı; daha eski zaman damgası birim (ms/µs/ns) hatasıdır. Üst sınır sabit tutulur
# (now() kullanılmaz ki sonuç tekrarlanabilir olsun).
MIN_PLAUSIBLE_TIME = pd.Timestamp("2017-07-01")
MAX_PLAUSIBLE_TIME = pd.Timestamp("2100-01-01")
QUOTE_SUFFIXES = ("FDUSD", "USDT", "BUSD", "USDC", "TUSD")  # uzun sonek önce denenir

# REST çapraz kontrol örneklemi tohumu, göreli tolerans ve çıktı dosyası (rapor dizinine yazılır).
REST_CROSSCHECK_SEED = int(load_settings()["quality"]["rest_crosscheck_seed"])
REST_RTOL = float(load_settings()["quality"]["rest_rtol"])
REST_CROSSCHECK_FILE = Path(load_settings()["paths"]["rest_crosscheck"]).name
# Temizleyicinin (trend.data.clean) tekrar kaydı dosya adı.
CLEANER_DUPLICATES = "_duplicates.csv"
# 10 Ekim 2025 bilinen iğneleri (SPEC); rapor bulunup bulunmadığını yazar.
KNOWN_WICKS_2025_10_10 = {"WBETHUSDT": 430.0, "BNSOLUSDT": 34.90, "USDEUSDT": 0.65}


# --------------------------------------------------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------------------------------------------------


def _fmt(**kv) -> str:
    """Ayrıntı alanı: 'k=v;k=v' (float'lar 10 anlamlı basamak; deterministik)."""
    out = []
    for k, v in kv.items():
        if isinstance(v, (float, np.floating)):
            v = f"{float(v):.10g}"
        elif isinstance(v, pd.Timestamp):
            v = v.strftime("%Y-%m-%d") if v == v.normalize() else v.strftime("%Y-%m-%d %H:%M")
        out.append(f"{k}={v}")
    return ";".join(out)


def empty_flags() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="str") for c in FLAG_COLUMNS})
    for c in ("period_start", "period_end", "known_from"):
        df[c] = pd.Series(dtype="datetime64[ns]")
    return df


def _frame(symbol: str, check: str, ps, pe, kf, details) -> pd.DataFrame:
    n = len(details)
    if n == 0:
        return empty_flags()
    return pd.DataFrame(
        {
            "symbol": [symbol] * n,
            "check": [check] * n,
            "period_start": pd.to_datetime(np.asarray(ps)).astype("datetime64[ns]"),
            "period_end": pd.to_datetime(np.asarray(pe)).astype("datetime64[ns]"),
            "known_from": pd.to_datetime(np.asarray(kf)).astype("datetime64[ns]"),
            "severity": [SEVERITY[check]] * n,
            "detail": list(details),
        }
    )


def normalize_flags(flags: pd.DataFrame) -> pd.DataFrame:
    """Kolon sırası, tipler ve deterministik sıralama."""
    if flags.empty:
        return empty_flags()
    f = flags[FLAG_COLUMNS].copy()
    for c in ("period_start", "period_end", "known_from"):
        f[c] = pd.to_datetime(f[c]).astype("datetime64[ns]")
    for c in ("symbol", "check", "severity", "detail"):
        f[c] = f[c].astype("str")
    f = f.sort_values(["symbol", "check", "period_start", "known_from", "detail"], kind="mergesort")
    return f.reset_index(drop=True)


def quote_of(symbol: str) -> str:
    for q in QUOTE_SUFFIXES:
        if symbol.endswith(q) and len(symbol) > len(q):
            return q
    return ""


# --------------------------------------------------------------------------------------------------------------------
# Kontroller
# --------------------------------------------------------------------------------------------------------------------


def compute_flags(
    df: pd.DataFrame,
    symbol: str,
    cfg: dict | None = None,
    interval: str = "1d",
    data_end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Tek bir çiftin temiz serisi (CONTRACTS §3) için kalite işaretleri.

    `data_end`: veri setinin son gün etiketi (tüm çiftlerin en büyüğü). Son mumu data_end olan çift hâlâ işlem
    görüyor kabul edilir ve son mumu yarım gün sayılmaz. 1h için yalnızca yapısal kontroller (tekrar, OHLC, zaman
    damgası, eksik saat) çalışır; SPEC'teki gün bazlı kontroller 1d içindir.
    """
    cfg = cfg or load_settings()
    q = cfg["quality"]
    step = INTERVAL_STEP[interval]
    freq = INTERVAL_FREQ[interval]
    parts: list[pd.DataFrame] = []
    if df is None or len(df) == 0:
        return empty_flags()

    d = df.sort_values("open_time", kind="mergesort").reset_index(drop=True)
    ot = pd.to_datetime(d["open_time"]).astype("datetime64[ns]")
    label = ot.dt.floor(freq)
    day = ot.dt.floor("D")

    # 1) Tekrarlanan open_time (temiz veride olmamalı; olursa hata).
    dup_mask = ot.duplicated(keep=False)
    if dup_mask.any():
        g = ot[dup_mask].value_counts().sort_index()
        dd = g.index.floor("D")
        parts.append(_frame(symbol, "duplicate_open_time", dd, dd, dd, [_fmt(open_time=t, n_rows=int(n)) for t, n in g.items()]))

    # 2) OHLC tutarlılığı ve fiyat > 0.
    o, h, lo, c = (d[k].to_numpy(dtype="float64") for k in ("open", "high", "low", "close"))
    with np.errstate(invalid="ignore"):
        issues = {
            "nan": np.isnan(o) | np.isnan(h) | np.isnan(lo) | np.isnan(c),
            "nonpositive": (o <= 0) | (h <= 0) | (lo <= 0) | (c <= 0),
            "high_lt_max_oc": h < np.maximum(o, c),
            "low_gt_min_oc": lo > np.minimum(o, c),
            "high_lt_low": h < lo,
        }
        for vcol in ("volume", "quote_volume"):
            if vcol in d:
                issues[f"negative_{vcol}"] = d[vcol].to_numpy(dtype="float64") < 0
    bad = np.zeros(len(d), dtype=bool)
    for m in issues.values():
        bad |= m
    if bad.any():
        idx = np.flatnonzero(bad)
        det = [_fmt(issues=",".join(k for k, m in issues.items() if m[i]), open=o[i], high=h[i], low=lo[i], close=c[i]) for i in idx]
        parts.append(_frame(symbol, "ohlc_inconsistent", day.iloc[idx], day.iloc[idx], day.iloc[idx], det))

    # 3) Zaman damgası: hiza, makul aralık (birim hatası), 0 < close_time − open_time < aralık.
    # Varsayım: arşivde delist/askı mumunun close_time'ı kesiktir (ör. MATICUSDT 2024-09-10 02:59:59.999, eski LUNA
    # 2022-05-13 00:39:59.999; bkz. trend.data.clean). Kesik close_time hata değil, yarım gün belirtisidir.
    ts_issue = {
        "misaligned": (ot != label).to_numpy(),
        "out_of_range": ((ot < MIN_PLAUSIBLE_TIME) | (ot > MAX_PLAUSIBLE_TIME)).to_numpy(),
    }
    if "close_time" in d:
        dur = pd.to_datetime(d["close_time"]).astype("datetime64[ns]") - ot
        ts_issue["close_time"] = (dur.isna() | (dur <= pd.Timedelta(0)) | (dur >= step)).to_numpy()
    tbad = np.zeros(len(d), dtype=bool)
    for m in ts_issue.values():
        tbad |= m
    if tbad.any():
        idx = np.flatnonzero(tbad)
        det = [_fmt(issues=",".join(k for k, m in ts_issue.items() if m[i]), open_time=ot.iloc[i]) for i in idx]
        parts.append(_frame(symbol, "timestamp", day.iloc[idx], day.iloc[idx], day.iloc[idx], det))

    # Sıralı kontroller tekrarsız seri üzerinde (aynı etikette ilk satır tutulur; yalnızca geçmişe bağlı).
    u = d.loc[~label.duplicated(keep="first")].reset_index(drop=True)
    ul = label[~label.duplicated(keep="first")].reset_index(drop=True)
    uday = ul.dt.floor("D")
    n = len(u)

    # 4) Eksik gün/saat: boşluk başına bir satır, seri döndüğünde bilinir.
    if n >= 2:
        nsteps = ((ul.iloc[1:].to_numpy() - ul.iloc[:-1].to_numpy()) // step.to_timedelta64()).astype("int64")
        gi = np.flatnonzero(nsteps > 1)
        if gi.size:
            chk = "missing_days" if interval == "1d" else "missing_hours"
            ps = ul.iloc[gi].to_numpy() + step.to_timedelta64()
            pe = ul.iloc[gi + 1].to_numpy() - step.to_timedelta64()
            kf = uday.iloc[gi + 1].to_numpy()
            det = [_fmt(n_missing=int(nsteps[i] - 1)) for i in gi]
            if interval != "1d":
                ps, pe = pd.DatetimeIndex(ps).floor("D"), pd.DatetimeIndex(pe).floor("D")
            parts.append(_frame(symbol, chk, ps, pe, kf, det))

    if interval != "1d":
        return normalize_flags(pd.concat(parts, ignore_index=True)) if parts else empty_flags()

    uo = u["open"].to_numpy(dtype="float64")
    uc = u["close"].to_numpy(dtype="float64")

    if n >= 2:
        prev_c = uc[:-1]
        gap_days = ((ul.iloc[1:].to_numpy() - ul.iloc[:-1].to_numpy()) // DAY.to_timedelta64()).astype("int64") - 1
        with np.errstate(divide="ignore", invalid="ignore"):
            # 5) Sembol değişmeden bölünme: önceki kapanış / sonraki açılış ≈ 10^k, k ≠ 0.
            r = np.log10(prev_c / uo[1:])
            k = np.rint(r)
            okp = (prev_c > 0) & (uo[1:] > 0) & np.isfinite(r)
            split = okp & (k != 0) & (np.abs(r - k) < q["split_log10_tolerance"])
            # 7) Aşırı kapanış sıçraması: |ln(C_t / C_{t-1})| > eşik (ardışık mumlar; boşluk varsa gap_days yazılır).
            lr = np.log(uc[1:] / prev_c)
            okr = (prev_c > 0) & (uc[1:] > 0) & np.isfinite(lr)
            jump = okr & (np.abs(lr) > q["max_abs_log_return"])
        si = np.flatnonzero(split)
        if si.size:
            det = [_fmt(prev_close=prev_c[i], next_open=uo[i + 1], log10_ratio=r[i], k=int(k[i]),
                        suggested_ratio=float(10.0 ** k[i]), gap_days=int(gap_days[i])) for i in si]
            parts.append(_frame(symbol, "split_candidate", uday.iloc[si], uday.iloc[si + 1], uday.iloc[si + 1], det))
        ji = np.flatnonzero(jump)
        if ji.size:
            det = [_fmt(log_return=lr[i], prev_close=prev_c[i], close=uc[i + 1], gap_days=int(gap_days[i])) for i in ji]
            parts.append(_frame(symbol, "extreme_return", uday.iloc[ji + 1], uday.iloc[ji + 1], uday.iloc[ji + 1], det))

    # 6) Sıfır hacim: volume = 0 veya number_of_trades = 0, art arda N+ mum (ardışık satırlar; boşluk diziyi bölmez).
    nrun = int(q["zero_volume_run_days"])
    vol = u["volume"].to_numpy(dtype="float64")
    trades = u["number_of_trades"].to_numpy(dtype="float64") if "number_of_trades" in u else np.full(n, np.nan)
    z = (vol == 0) | (trades == 0)
    if z.any():
        run_id = np.cumsum(np.r_[True, z[1:] != z[:-1]])
        start_of = pd.Series(np.arange(n)).groupby(run_id).transform("min").to_numpy()
        size_of = pd.Series(np.arange(n)).groupby(run_id).transform("size").to_numpy()
        zi = np.flatnonzero(z & (size_of >= nrun))
        if zi.size:
            kpos = np.maximum(zi, start_of[zi] + nrun - 1)
            det = [_fmt(run_start=uday.iloc[start_of[i]], volume=vol[i], trades=trades[i]) for i in zi]
            parts.append(_frame(symbol, "zero_volume", uday.iloc[zi], uday.iloc[zi], uday.iloc[kpos], det))

    # 8) Aşırı iğne: low < frac × close veya high > mult × close (satır yerel; tüm satırlar).
    with np.errstate(invalid="ignore"):
        lw = (c > 0) & (lo < q["wick_low_frac"] * c)
        hw = (c > 0) & (h > q["wick_high_mult"] * c)
    wi = np.flatnonzero(lw | hw)
    if wi.size:
        det = [_fmt(side="both" if lw[i] and hw[i] else ("low" if lw[i] else "high"), low=lo[i], high=h[i], close=c[i]) for i in wi]
        parts.append(_frame(symbol, "extreme_wick", day.iloc[wi], day.iloc[wi], day.iloc[wi], det))

    # 9) Yarım gün: ilk mum (konumdan) + kolonda işaretli diğer mumlar, known_from = gün + 1. Temizleyici kolonu
    # ilk mum, kesik close_time'lı mum, kesik mumdan sonra boşlukla gelen yeniden açılış mumu ve sona ermiş çiftin
    # son mumu için True yapar (trend.data.clean); son kural geleceği bildiğinden known_from bir gün geciktirilir.
    hd_ps, hd_kf, hd_det = [uday.iloc[0]], [uday.iloc[0]], [_fmt(position="first")]
    if "half_day" in u:
        hdm = u["half_day"].fillna(False).to_numpy(dtype=bool, copy=True)
        hdm[0] = False
        cand = np.flatnonzero(hdm)
    else:  # Varsayım: kolon yoksa son mum (CONTRACTS §3 kolonu zorunlu kılar; bu yedek kesme testini garanti etmez)
        cand = np.array([n - 1]) if n >= 2 else np.array([], dtype=int)
    for i in cand:
        if data_end is not None and uday.iloc[i] >= pd.Timestamp(data_end).normalize():
            continue  # hâlâ işlem görüyor
        hd_ps.append(uday.iloc[i])
        hd_kf.append(uday.iloc[i] + DAY)
        trunc = bool("close_time" in u and pd.Timestamp(u["close_time"].iloc[i]) - ul.iloc[i] < step - pd.Timedelta(milliseconds=1))
        hd_det.append(_fmt(position="half_day_column" if "half_day" in u else "last", truncated_close=trunc))
    parts.append(_frame(symbol, "half_day", hd_ps, hd_ps, hd_kf, hd_det))

    return normalize_flags(pd.concat(parts, ignore_index=True))


# --------------------------------------------------------------------------------------------------------------------
# İğne fiyatını hesaplardan çıkarma
# --------------------------------------------------------------------------------------------------------------------


def wick_mask(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """Satır başına `low_wick`, `high_wick` maskesi (SPEC aşırı iğne kuralı)."""
    q = (cfg or load_settings())["quality"]
    c = df["close"].astype("float64")
    return pd.DataFrame(
        {"low_wick": (c > 0) & (df["low"] < q["wick_low_frac"] * c), "high_wick": (c > 0) & (df["high"] > q["wick_high_mult"] * c)},
        index=df.index,
    )


def clean_low_high(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """İğne fiyatı hiçbir hesapta kullanılmaz: iğneli günde low → min(open, close), high → max(open, close).

    Varsayım: gövde (open/close) gerçek işlem fiyatıdır ve korunur; yalnızca uç değer gövdeye kırpılır.
    Hem tek seri (kolonlar open/high/low/close) hem de aynı biçimli panel parçaları için kullanılabilir.
    """
    m = wick_mask(df, cfg)
    body_lo = np.minimum(df["open"], df["close"])
    body_hi = np.maximum(df["open"], df["close"])
    return pd.DataFrame(
        {"low": df["low"].where(~m["low_wick"], body_lo), "high": df["high"].where(~m["high_wick"], body_hi)},
        index=df.index,
    )


# --------------------------------------------------------------------------------------------------------------------
# Karar tarihinde bilinen işaretler ve kullanılabilir günler
# --------------------------------------------------------------------------------------------------------------------


def flags_known_at(flags: pd.DataFrame, T) -> pd.DataFrame:
    """T günündeki karar için kullanılabilir işaretler: known_from ≤ T − 1 gün (CONTRACTS §5)."""
    T = pd.Timestamp(T).normalize()
    return flags.loc[flags["known_from"] <= T - DAY]


def expand_flag_days(flags: pd.DataFrame) -> pd.DataFrame:
    """Her işaret satırını kapsadığı günlere açar → (symbol, day, check, known_from)."""
    if flags.empty:
        return pd.DataFrame({"symbol": pd.Series(dtype="str"), "day": pd.Series(dtype="datetime64[ns]"),
                             "check": pd.Series(dtype="str"), "known_from": pd.Series(dtype="datetime64[ns]")})
    ps = pd.to_datetime(flags["period_start"]).dt.floor("D").to_numpy()
    pe = pd.to_datetime(flags["period_end"]).dt.floor("D").to_numpy()
    nday = ((pe - ps) // DAY.to_timedelta64()).astype("int64") + 1
    nday = np.maximum(nday, 1)
    rep = np.repeat(np.arange(len(flags)), nday)
    offs = np.arange(rep.size) - np.repeat(np.cumsum(nday) - nday, nday)
    days = ps[rep] + offs * DAY.to_timedelta64()
    return pd.DataFrame(
        {"symbol": flags["symbol"].to_numpy()[rep], "day": days, "check": flags["check"].to_numpy()[rep],
         "known_from": pd.to_datetime(flags["known_from"]).to_numpy()[rep]}
    )


def usable_days(close: pd.DataFrame, flags: pd.DataFrame, asof, unusable_checks: Iterable[str] = UNUSABLE_CHECKS) -> pd.DataFrame:
    """Panel (index = gün etiketi, kolon = sembol/asset_id) için, `asof` günündeki kararda bilinen bilgiyle
    gün başına "temiz/kullanılabilir" maskesi. Yalnızca index ≤ asof satırları döner.

    Gün kullanılabilir ⇔ mumu var (close notna) ve known_from ≤ asof − 1 olan bir UNUSABLE işaretiyle örtüşmüyor.
    `flags.symbol` panel kolonlarıyla aynı uzayda olmalı (merged panel için önce `flags_to_assets`).
    """
    asof = pd.Timestamp(asof).normalize()
    sub = close.loc[close.index <= asof]
    mask = sub.notna().to_numpy(copy=True)
    known = flags_known_at(flags, asof)
    known = known.loc[known["check"].isin(list(unusable_checks)) & known["symbol"].isin(sub.columns)]
    if not known.empty:
        ex = expand_flag_days(known)
        ri = sub.index.get_indexer(pd.DatetimeIndex(ex["day"]))
        ci = sub.columns.get_indexer(ex["symbol"])
        ok = (ri >= 0) & (ci >= 0)
        mask[ri[ok], ci[ok]] = False
    return pd.DataFrame(mask, index=sub.index, columns=sub.columns)


def clean_day_counts(close: pd.DataFrame, flags: pd.DataFrame, asof, unusable_checks: Iterable[str] = UNUSABLE_CHECKS) -> pd.Series:
    """`asof` kararında sembol başına temiz gün sayısı (evrenin 365 temiz gün kuralı için)."""
    return usable_days(close, flags, asof, unusable_checks).sum(axis=0).astype("int64")


def flags_to_assets(flags: pd.DataFrame, segments: pd.DataFrame) -> pd.DataFrame:
    """Çift sembolündeki işaretleri `meta/asset_segments.csv` ile asset_id uzayına taşır.

    Her işaret, aynı source_symbol'ün başlangıcı ≤ period_start olan en geç segmentine atanır (as-of eşleme;
    ASSET_CHANGE ile bölünen sembolde boşluk/bölünme satırı eski parçaya düşer). Segmenti olmayan çift aynen kalır.
    """
    if flags.empty or segments is None or segments.empty:
        return flags.copy()
    seg = segments[["asset_id", "source_symbol", "start"]].copy()
    seg["seg_start"] = pd.to_datetime(seg["start"]).dt.floor("D").astype("datetime64[ns]")
    seg = seg.drop(columns="start").sort_values("seg_start")
    f = flags.copy()
    f["_ord"] = np.arange(len(f))
    f["_ps"] = pd.to_datetime(f["period_start"]).dt.floor("D").astype("datetime64[ns]")
    m = pd.merge_asof(f.sort_values("_ps"), seg, left_on="_ps", right_on="seg_start", left_by="symbol",
                      right_by="source_symbol", direction="backward")
    # period_start ilk segmentten önceyse (olmamalı) ilk segmente ata.
    first_seg = seg.drop_duplicates("source_symbol", keep="first").set_index("source_symbol")["asset_id"]
    miss = m["asset_id"].isna()
    m.loc[miss, "asset_id"] = m.loc[miss, "symbol"].map(first_seg)
    m["symbol"] = m["asset_id"].fillna(m["symbol"]).astype("str")
    return normalize_flags(m.sort_values("_ord"))


# --------------------------------------------------------------------------------------------------------------------
# Toplu çalıştırma (gerçek veri)
# --------------------------------------------------------------------------------------------------------------------


def clean_dir(interval: str, cfg: dict | None = None) -> Path:
    return cfg_path(cfg or load_settings(), "clean") / interval


def list_clean_symbols(interval: str = "1d", cfg: dict | None = None) -> list[str]:
    d = clean_dir(interval, cfg)
    return sorted(p.stem for p in d.glob("*.parquet") if not p.stem.startswith("_")) if d.exists() else []


def read_clean(symbol: str, interval: str = "1d", cfg: dict | None = None, columns: list[str] | None = None) -> pd.DataFrame:
    return pd.read_parquet(clean_dir(interval, cfg) / f"{symbol}.parquet", columns=columns)


def global_data_end(interval: str = "1d", cfg: dict | None = None) -> pd.Timestamp | None:
    """Tüm temiz dosyaların en büyük gün etiketi (hâlâ işlem gören çiftlerin son mumu)."""
    ends = []
    for s in list_clean_symbols(interval, cfg):
        t = read_clean(s, interval, cfg, columns=["open_time"])["open_time"]
        if len(t):
            ends.append(pd.Timestamp(t.max()))
    return max(ends).normalize() if ends else None


def read_cleaner_duplicates(interval: str = "1d", cfg: dict | None = None) -> pd.DataFrame:
    """Temizleyicinin tekrar kaydı `{clean}/{interval}/_duplicates.csv` (symbol, interval, open_time, kind, n, sources).

    Temiz veri tekrarsızdır: temizleyici aynı open_time'da ilk satırı (aylık > günlük) tutar ve tekrarı buraya yazar.
    """
    p = clean_dir(interval, cfg) / CLEANER_DUPLICATES
    if not p.exists():
        return pd.DataFrame(columns=["symbol", "interval", "open_time", "kind", "n", "sources"])
    d = pd.read_csv(p)
    d["open_time"] = pd.to_datetime(d["open_time"]).astype("datetime64[ns]")
    return d


def duplicate_flags_from_cleaner(interval: str = "1d", cfg: dict | None = None, symbols: list[str] | None = None) -> pd.DataFrame:
    """Değerleri farklı tekrarlar (`kind=conflict`) → `duplicate_open_time` hata satırları (known_from = o gün).
    Birebir aynı tekrarlar (`exact`) zararsız düzeltilmiştir; yalnız raporda sayılır."""
    d = read_cleaner_duplicates(interval, cfg)
    d = d.loc[d["kind"] == "conflict"]
    if symbols is not None:
        d = d.loc[d["symbol"].isin(symbols)]
    parts = []
    for sym, g in d.groupby("symbol", sort=True):
        days = g["open_time"].dt.floor("D")
        det = [_fmt(open_time=t, n_rows=int(n), source="cleaner_conflict", kept="first") for t, n in zip(g["open_time"], g["n"])]
        parts.append(_frame(str(sym), "duplicate_open_time", days, days, days, det))
    return pd.concat(parts, ignore_index=True) if parts else empty_flags()


def flags_hash(flags: pd.DataFrame) -> str:
    """İşaret tablosunun içerik özeti (tekrarlanabilirlik: aynı veri → aynı hash)."""
    f = normalize_flags(flags)
    return hashlib.sha256(f.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%S").encode("utf-8")).hexdigest()


def run_flags(cfg: dict | None = None, interval: str = "1d", symbols: list[str] | None = None, out: Path | None = None) -> pd.DataFrame:
    """Tüm temiz çiftler için işaretleri hesaplar ve `data/quality_flags.parquet`'e yazar (1d)."""
    cfg = cfg or load_settings()
    symbols = symbols or list_clean_symbols(interval, cfg)
    if not symbols:
        raise FileNotFoundError(f"temiz veri yok: {clean_dir(interval, cfg)}")
    data_end = global_data_end(interval, cfg)
    parts = []
    for i, s in enumerate(symbols, 1):
        parts.append(compute_flags(read_clean(s, interval, cfg), s, cfg, interval, data_end))
        if i % 200 == 0:
            print(f"  {i}/{len(symbols)} sembol", file=sys.stderr)
    parts.append(duplicate_flags_from_cleaner(interval, cfg, symbols))
    flags = normalize_flags(pd.concat(parts, ignore_index=True)) if parts else empty_flags()
    out = out or cfg_path(cfg, "quality_flags")
    out.parent.mkdir(parents=True, exist_ok=True)
    flags.to_parquet(out, index=False)
    print(f"{len(flags)} işaret, {flags['symbol'].nunique()} sembol, data_end={data_end:%Y-%m-%d} → {out}")
    print(f"sha256={flags_hash(flags)}")
    return flags


def load_flags(cfg: dict | None = None) -> pd.DataFrame:
    return normalize_flags(pd.read_parquet(cfg_path(cfg or load_settings(), "quality_flags")))


# --------------------------------------------------------------------------------------------------------------------
# REST çapraz kontrolü (bağımsız kaynak; ağ gerekir)
# --------------------------------------------------------------------------------------------------------------------

REST_FIELDS = ["open", "high", "low", "close", "volume", "quote_volume", "number_of_trades", "taker_buy_base", "taker_buy_quote"]


def parse_rest_klines(rows: list[list]) -> pd.DataFrame:
    """REST /api/v3/klines yanıtını temiz şemaya çevirir (REST varsayılanı milisaniye; timeZone gönderilmez)."""
    if not rows:
        return pd.DataFrame(columns=["open_time", *REST_FIELDS])
    a = pd.DataFrame(rows).iloc[:, :11]
    a.columns = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
                 "number_of_trades", "taker_buy_base", "taker_buy_quote"]
    ot = a["open_time"].astype("int64")
    ot = ot.where(ot <= 10**14, ot // 1000)  # güvenlik: µs gelirse
    out = pd.DataFrame({"open_time": pd.to_datetime(ot, unit="ms").astype("datetime64[ns]")})
    for f in REST_FIELDS:
        out[f] = a[f].astype("int64" if f == "number_of_trades" else "float64")
    return out


def compare_with_rest(symbol: str, clean: pd.DataFrame, rest: pd.DataFrame, rtol: float = REST_RTOL) -> pd.DataFrame:
    """Aynı open_time'lı satırları alan alan karşılaştırır → (symbol, open_time, field, archive, rest, match)."""
    a = clean[["open_time", *REST_FIELDS]].assign(open_time=pd.to_datetime(clean["open_time"]).astype("datetime64[ns]"))
    b = rest[["open_time", *REST_FIELDS]].assign(open_time=pd.to_datetime(rest["open_time"]).astype("datetime64[ns]"))
    m = a.merge(b, on="open_time", how="outer", suffixes=("_archive", "_rest"), indicator=True)
    recs = []
    for _, r in m.iterrows():
        if r["_merge"] != "both":
            recs.append({"symbol": symbol, "open_time": r["open_time"], "field": "row",
                         "archive": float(r["_merge"] != "right_only"), "rest": float(r["_merge"] != "left_only"), "match": False})
            continue
        for f in REST_FIELDS:
            a, b = float(r[f + "_archive"]), float(r[f + "_rest"])
            ok = bool(np.isclose(a, b, rtol=rtol, atol=1e-12))
            recs.append({"symbol": symbol, "open_time": r["open_time"], "field": f, "archive": a, "rest": b, "match": ok})
    return pd.DataFrame(recs, columns=["symbol", "open_time", "field", "archive", "rest", "match"])


class _RestClient:
    """Küçük, ağırlık izleyen REST istemcisi (veri ajanının rest.py'si hazır değilse diye bağımsız)."""

    def __init__(self, cfg: dict):
        import requests

        self.s = requests.Session()
        self.base = cfg["data"]["rest_base"]
        self.limit = int(cfg["data"]["rest_weight_limit_default"])
        self.pause_frac = float(cfg["data"]["rest_weight_pause_frac"])
        self.max_retries = int(cfg["data"]["max_retries"])
        self.backoff = float(cfg["data"]["backoff_base_s"])

    def get(self, endpoint: str, params: dict) -> object:
        assert "timeZone" not in params  # SPEC: timeZone asla gönderilmez
        for attempt in range(self.max_retries):
            r = self.s.get(self.base + endpoint, params=params, timeout=20)
            used = int(r.headers.get("X-MBX-USED-WEIGHT-1M", "0") or 0)
            if used >= self.pause_frac * self.limit:
                time.sleep(61 - time.gmtime().tm_sec)
            if r.status_code in (429, 418):
                time.sleep(float(r.headers.get("Retry-After", self.backoff * 2**attempt)))
                continue
            if r.status_code >= 500:
                time.sleep(self.backoff * 2**attempt)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"REST başarısız: {endpoint} {params}")


def rest_crosscheck(
    cfg: dict | None = None,
    n_coins: int | None = None,
    n_days: int | None = None,
    seed: int = REST_CROSSCHECK_SEED,
    extra_flagged: int = 0,
    out: Path | None = None,
) -> pd.DataFrame:
    """Rastgele `n_coins` USDT çifti × `n_days` gün, arşiv (temiz 1d) ile REST klines karşılaştırması.

    Sadece bugün TRADING olan çiftler örneklenir (delist edilen çift REST'te yok). `extra_flagged` > 0 ise
    ek olarak o kadar aşırı getiri/iğne işaretli gün de kontrol edilir (SPEC: "işaret, ikinci kaynakla kontrol").
    Çıktı: reports/G4_rest_crosscheck.csv.
    """
    cfg = cfg or load_settings()
    q = cfg["quality"]
    n_coins = n_coins or int(q["rest_crosscheck_coins"])
    n_days = n_days or int(q["rest_crosscheck_days"])
    cli = _RestClient(cfg)
    info = cli.get("/api/v3/exchangeInfo", {"permissions": "SPOT"})
    trading = {s["symbol"] for s in info["symbols"] if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT"}
    pool = sorted(s for s in list_clean_symbols("1d", cfg) if s in trading)
    rng = random.Random(seed)
    picks = [(s, None) for s in rng.sample(pool, min(n_coins, len(pool)))]
    if extra_flagged > 0:
        try:
            fl = load_flags(cfg)
            fl = fl.loc[fl["check"].isin(["extreme_return", "extreme_wick"]) & fl["symbol"].isin(pool)]
            rows = sorted(zip(fl["symbol"], fl["period_start"]))
            picks += [(s, pd.Timestamp(t)) for s, t in rng.sample(rows, min(extra_flagged, len(rows)))]
        except FileNotFoundError:
            pass
    results = []
    for sym, fixed_day in picks:
        clean = read_clean(sym, "1d", cfg)
        cd = pd.to_datetime(clean["open_time"]).astype("datetime64[ns]")
        if fixed_day is not None:
            days = [fixed_day]
        else:
            cand = sorted(cd.iloc[1:-1])  # ilk/son (yarım) mum hariç
            days = sorted(rng.sample(cand, min(n_days, len(cand))))
        for dd in days:
            ms = int((pd.Timestamp(dd) - pd.Timestamp(0)) // pd.Timedelta(milliseconds=1))
            rows = cli.get("/api/v3/klines", {"symbol": sym, "interval": "1d", "startTime": ms, "limit": 1})
            rest = parse_rest_klines(rows)
            rest = rest.loc[rest["open_time"] == pd.Timestamp(dd)]
            sub = clean.loc[cd == pd.Timestamp(dd)].assign(open_time=pd.Timestamp(dd))
            res = compare_with_rest(sym, sub, rest)
            res["sample"] = "flagged" if fixed_day is not None else "random"
            results.append(res)
    df = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    out = out or cfg_path(cfg, "reports") / REST_CROSSCHECK_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    n_rows = df.groupby(["symbol", "open_time"]).ngroups if len(df) else 0
    print(f"{n_rows} gün karşılaştırıldı; uyuşmayan alan: {int((~df['match']).sum()) if len(df) else 0} → {out}")
    return df


# --------------------------------------------------------------------------------------------------------------------
# Rapor (reports/G4_quality.md)
# --------------------------------------------------------------------------------------------------------------------


def clean_summary(interval: str = "1d", cfg: dict | None = None) -> pd.DataFrame:
    """Sembol başına ilk/son gün, mum sayısı, kotasyon."""
    recs = []
    for s in list_clean_symbols(interval, cfg):
        t = pd.to_datetime(read_clean(s, interval, cfg, columns=["open_time"])["open_time"])
        if len(t):
            recs.append({"symbol": s, "quote": quote_of(s), "first": t.min().normalize(), "last": t.max().normalize(), "n_rows": len(t)})
    return pd.DataFrame(recs, columns=["symbol", "quote", "first", "last", "n_rows"])


def truncation_check(symbols: list[str], dates: list[str], cfg: dict | None = None, interval: str = "1d") -> list[dict]:
    """Gerçek veri örneğinde kesme değişmezini doğrular (rapor için)."""
    cfg = cfg or load_settings()
    data_end = global_data_end(interval, cfg)
    out = []
    for s in symbols:
        df = read_clean(s, interval, cfg)
        full = compute_flags(df, s, cfg, interval, data_end)
        for T in dates:
            T = pd.Timestamp(T)
            trunc = compute_flags(df.loc[pd.to_datetime(df["open_time"]) <= T], s, cfg, interval, min(T, data_end))
            a = normalize_flags(full.loc[full["known_from"] <= T])
            b = normalize_flags(trunc.loc[trunc["known_from"] <= T])
            out.append({"symbol": s, "T": T, "equal": a.equals(b), "n": len(a)})
    return out


def _md_table(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "_(yok)_\n"
    d = df.head(max_rows).copy()
    for c in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[c]):
            d[c] = d[c].dt.strftime("%Y-%m-%d")
    lines = ["| " + " | ".join(map(str, d.columns)) + " |", "| " + " | ".join("---" for _ in d.columns) + " |"]
    for row in d.itertuples(index=False):
        lines.append("| " + " | ".join(str(v).replace("|", "\\|") for v in row) + " |")
    more = f"\n_(+{len(df) - max_rows} satır daha)_\n" if len(df) > max_rows else "\n"
    return "\n".join(lines) + more


def write_report(cfg: dict | None = None, with_1h: bool = False, out: Path | None = None) -> Path:
    """`reports/G4_quality.md`: kontrol sayıları, en çok işaretlenenler, 10 Ekim 2025 iğneleri, veriden öğrenilenler."""
    cfg = cfg or load_settings()
    flags = load_flags(cfg)
    summ = clean_summary("1d", cfg)
    data_end = summ["last"].max() if len(summ) else None
    L: list[str] = ["# G4 — Veri kalitesi raporu", ""]
    L.append(f"_Üretildi: `python -m trend.quality report` · işaret tablosu sha256 `{flags_hash(flags)}`_\n")
    L.append("Kurallar SPEC \"Veri kalitesi ve meta tablolar\" ve CONTRACTS §5'e göredir; satır tasarımı ve varsayımlar "
             "`src/trend/quality.py` başındaki açıklamadadır. T günündeki karar yalnızca `known_from ≤ T − 1` işaretleri kullanır.\n")

    # Kontrol başına sayılar
    L.append("## Kontrol başına sayılar (1d)\n")
    if len(flags):
        g = flags.groupby(["check", "severity"]).agg(rows=("symbol", "size"), symbols=("symbol", "nunique")).reset_index()
        L.append(_md_table(g, 50))
    else:
        L.append("_(işaret yok)_\n")

    dups = read_cleaner_duplicates("1d", cfg)
    if len(dups):
        L.append("Temizleyicinin tekrar kaydı (`_duplicates.csv`, ilk satır tutuldu): "
                 + ", ".join(f"{k} {v}" for k, v in dups["kind"].value_counts().items())
                 + f"; {dups['symbol'].nunique()} sembol. Yalnız `conflict` olanlar `duplicate_open_time` hatası olarak işaretlendi.\n")
    else:
        L.append("Temizleyicinin tekrar kaydı: yok (veya `_duplicates.csv` bulunamadı).\n")

    # En çok işaretlenenler
    L.append("## En çok işaretlenen semboller\n")
    ex = expand_flag_days(flags.loc[flags["check"].isin(list(UNUSABLE_CHECKS))])
    if len(ex):
        top = ex.drop_duplicates(["symbol", "day"]).groupby("symbol").size().rename("unusable_days").sort_values(ascending=False)
        L.append("Kullanılamaz gün (error/exclude/yarım gün) sayısına göre ilk 20:\n")
        L.append(_md_table(top.reset_index(), 20))
    for chk in ("extreme_return", "extreme_wick", "missing_days"):
        sub = flags.loc[flags["check"] == chk]
        if len(sub):
            t = sub.groupby("symbol").size().rename("rows").sort_values(ascending=False).reset_index()
            L.append(f"`{chk}` satır sayısına göre ilk 10:\n")
            L.append(_md_table(t, 10))

    # 10 Ekim 2025
    L.append("## 10 Ekim 2025 bilinen iğneleri\n")
    rows = []
    d0 = pd.Timestamp("2025-10-10")
    for sym, ref in KNOWN_WICKS_2025_10_10.items():
        p = clean_dir("1d", cfg) / f"{sym}.parquet"
        if not p.exists():
            rows.append({"symbol": sym, "spec_low": ref, "data_low": "dosya yok", "close": "", "flagged": ""})
            continue
        df = pd.read_parquet(p)
        r = df.loc[pd.to_datetime(df["open_time"]).dt.normalize() == d0]
        fl = flags.loc[(flags["symbol"] == sym) & (flags["check"] == "extreme_wick") & (flags["period_start"] == d0)]
        if r.empty:
            rows.append({"symbol": sym, "spec_low": ref, "data_low": "mum yok", "close": "", "flagged": bool(len(fl))})
        else:
            rows.append({"symbol": sym, "spec_low": ref, "data_low": float(r["low"].iloc[0]), "close": float(r["close"].iloc[0]),
                         "flagged": bool(len(fl))})
    L.append(_md_table(pd.DataFrame(rows)))
    L.append("Not: kural low < 0,3 × close'dur; USDe'nin ~0,65'lik iğnesi (~%35 düşüş) bu eşiğin altında kalmaz, "
             "dolayısıyla işaretlenmemesi beklenir (USDe zaten stablecoin olarak evren dışıdır). wBETH/BNSOL dışlama listesinde.\n")

    # Veriden ne öğrendik
    L.append("## Veriden ne öğrendik\n")
    if len(summ):
        L.append(f"- Temiz 1d çift sayısı: **{len(summ)}**; kotasyona göre: "
                 + ", ".join(f"{q or '?'} {n}" for q, n in summ.groupby("quote").size().items()) + ".")
        L.append(f"- En erken gün: **{summ['first'].min():%Y-%m-%d}** ({summ.loc[summ['first'].idxmin(), 'symbol']}); "
                 f"en geç gün (data_end): **{data_end:%Y-%m-%d}**.")
        ended = summ.loc[summ["last"] < data_end - pd.Timedelta(days=int(cfg['backtest']['delist_stale_days']))]
        L.append(f"- Veri sonundan {cfg['backtest']['delist_stale_days']}+ gün önce biten (delist/rename) çift: **{len(ended)}**.")
        usdt = summ.loc[summ["quote"] == "USDT"]
        years = range(int(summ["first"].min().year), int(data_end.year) + 1)
        yr = []
        for y in years:
            a, b = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-12-31")
            yr.append({"year": y,
                       "usdt_active": int(((usdt["first"] <= b) & (usdt["last"] >= a)).sum()),
                       "usdt_listed": int((usdt["first"].dt.year == y).sum()),
                       "usdt_ended": int(((usdt["last"].dt.year == y) & (usdt["last"] < data_end - pd.Timedelta(days=7))).sum()),
                       "all_active": int(((summ["first"] <= b) & (summ["last"] >= a)).sum())})
        L.append("\nYıllara göre sembol sayıları (active = yıl içinde en az bir mum):\n")
        L.append(_md_table(pd.DataFrame(yr), 50))
    gaps = flags.loc[flags["check"] == "missing_days"].copy()
    if len(gaps):
        gaps["n_missing"] = gaps["detail"].str.extract(r"n_missing=(\d+)")[0].astype(int)
        L.append(f"- Boşluk: **{len(gaps)}** boşluk, **{gaps['symbol'].nunique()}** sembolde, toplam **{int(gaps['n_missing'].sum())}** eksik gün. En uzun 15:\n")
        L.append(_md_table(gaps.sort_values("n_missing", ascending=False)[["symbol", "period_start", "period_end", "n_missing"]], 15))
    else:
        L.append("- Boşluk: yok.\n")
    sp = flags.loc[flags["check"] == "split_candidate"]
    L.append(f"- Sembol değişmeden bölünme adayı: **{len(sp)}** (tamamı `meta/symbol_map_candidates.csv` üzerinden incelenir):\n")
    L.append(_md_table(sp[["symbol", "period_start", "period_end", "detail"]], 50))
    ud = ex.drop_duplicates(["symbol", "day"]) if len(ex) else ex
    L.append(f"- Kullanılamaz (error/exclude/yarım gün) sembol-gün sayısı: **{len(ud)}**; "
             f"tüm işaretlerin kapsadığı sembol-gün: **{len(expand_flag_days(flags).drop_duplicates(['symbol', 'day']))}**.\n")

    # Kesme değişmezi (gerçek veri örneği)
    L.append("## Tarih kesme değişmezi (gerçek veri örneği)\n")
    if len(summ):
        syms = summ.sort_values("symbol")["symbol"].tolist()
        sample = syms[:: max(1, len(syms) // 25)][:25]
        chk = truncation_check(sample, ["2020-03-12", "2022-05-12", "2024-07-01"], cfg)
        n_ok = sum(c["equal"] for c in chk)
        failed = ", ".join(c["symbol"] + "@" + c["T"].strftime("%Y-%m-%d") for c in chk if not c["equal"])
        verdict = "GEÇTİ" if n_ok == len(chk) else "KALDI: " + failed
        L.append(f"{len(sample)} sembol × 3 kesim tarihi: **{n_ok}/{len(chk)}** eşit ({verdict}).\n")

    # REST çapraz kontrol
    L.append("## REST çapraz kontrolü (bağımsız kaynak)\n")
    rp = cfg_path(cfg, "reports") / REST_CROSSCHECK_FILE
    if rp.exists():
        rc = pd.read_csv(rp)
        nday = rc.groupby(["symbol", "open_time"]).ngroups
        bad = rc.loc[~rc["match"].astype(bool)]
        L.append(f"{rc['symbol'].nunique()} coin, {nday} gün karşılaştırıldı; uyuşmayan alan: **{len(bad)}** "
                 f"(`reports/{REST_CROSSCHECK_FILE}`).\n")
        if len(bad):
            L.append(_md_table(bad, 30))
    else:
        L.append("_Henüz çalıştırılmadı: `python -m uv run python -m trend.quality rest-check`._\n")

    if with_1h:
        L.append("## 1h yapısal kontroller\n")
        recs = []
        for s in list_clean_symbols("1h", cfg):
            f = compute_flags(read_clean(s, "1h", cfg), s, cfg, "1h")
            if len(f):
                recs.append(f.groupby("check").size().rename(s))
        if recs:
            t = pd.concat(recs, axis=1).T.fillna(0).astype(int)
            L.append(f"İşaretli 1h sembol: {len(t)}. Kontrol başına toplam satır: "
                     + ", ".join(f"{k} {int(v)}" for k, v in t.sum().items()) + "\n")
            L.append(_md_table(t.sum(axis=1).sort_values(ascending=False).rename("rows").reset_index(names="symbol"), 15))
        else:
            L.append("_(1h işaret yok)_\n")

    out = out or cfg_path(cfg, "reports") / "G4_quality.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print(f"rapor → {out}")
    return out


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows konsolunda Türkçe karakterler hata vermesin
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="python -m trend.quality", description="G4 kalite denetimi")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("flags", help="data/clean/1d → data/quality_flags.parquet")
    r = sub.add_parser("report", help="reports/G4_quality.md")
    r.add_argument("--with-1h", action="store_true", help="1h yapısal kontrol özetini ekle (yavaş)")
    rc = sub.add_parser("rest-check", help="REST çapraz kontrol (ağ)")
    rc.add_argument("--coins", type=int, default=None)
    rc.add_argument("--days", type=int, default=None)
    rc.add_argument("--seed", type=int, default=REST_CROSSCHECK_SEED)
    rc.add_argument("--flagged", type=int, default=0, help="ek olarak kontrol edilecek işaretli gün sayısı")
    a = ap.parse_args(argv)
    if a.cmd == "flags":
        run_flags()
    elif a.cmd == "report":
        write_report(with_1h=a.with_1h)
    elif a.cmd == "rest-check":
        rest_crosscheck(n_coins=a.coins, n_days=a.days, seed=a.seed, extra_flagged=a.flagged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
