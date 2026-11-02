"""G6 — Coin evreni (SPEC "Coin evreni"; CONTRACTS §1, §4, §5, §6).

Ay M'nin evreni, karar anı T = M−1 ayının son günü (gün etiketi) kapanışıyla kurulur: yalnızca gün etiketi ≤ T olan
mumlar ve known_from ≤ T−1 olan kalite işaretleri kullanılır. t günündeki karar (t + 1 gün)'ün ayının evrenini kullanır
(`universe_for_decision_day`).

Girdiler (CONTRACTS biçimleri; adaptörler `load_*`):
  - birleşik USDT günlük serileri, asset_id başına: data/merged/1d/{ASSET_ID}.parquet (§4)
  - diğer stablecoin çiftleri (BUSD/FDUSD/USDC/TUSD quote) ve {Q}USDT çiftleri: data/clean/1d/{SYM}.parquet (§3)
  - data/quality_flags.parquet (§5), meta/fee_promotions.csv (§4), isteğe bağlı meta/asset_segments.csv (§4),
    isteğe bağlı meta/symbols_raw.csv (§2; diğer quote çiftlerinin base/quote ayrımı için)
Çıktılar: universe/{YYYY-MM}.csv (§6), universe/usdt_only/ (T7), universe/size_{N}/ (komşu büyüklükler),
universe/diagnostics.csv; rapor reports/G6_universe.md.

Orkestratör girişi: `build_from_disk()` veya `python -m trend.universe build`.
Tüm varsayımlar ASSUMPTIONS listesindedir (rapora da yazılır).
"""

from __future__ import annotations

import argparse
import re
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from trend.config import ROOT, load_settings
from trend.config import path as settings_path

# --- settings.yaml'da olmayan parametreler -------------------------------------------------------------------------
_S = load_settings()
# CONTRACTS §4 birleşik seriler data/merged/{interval}/{ASSET_ID}.parquet
MERGED_DIR_DEFAULT = _S["paths"]["merged"]
# günü "temiz değil" yapan kalite işareti şiddetleri (V1)
BAD_SEVERITIES = tuple(_S["quality"]["excluding_severities"])
# stablecoin yedek kontrolü için en az getiri gözlemi (V9)
STABLE_FALLBACK_MIN_OBS = int(_S["universe"]["stable_vol_fallback"]["min_obs"])
# {Q}USDT kapanışı eksikse en fazla kaç gün geriye taşınır (V4)
CONVERSION_FFILL_DAYS = int(_S["universe"]["conversion_ffill_days"])

QUOTE = "USDT"
COLUMNS = ["symbol", "rank", "median_liquidity", "tier", "cap", "slippage"]
DIAG_COLUMNS = [
    "month", "decision_time", "size_main", "n_trading", "n_name_excluded", "n_stable_fallback", "n_clean_ok",
    "n_liquid", "n_liquid_usdt_only", "n_main", "n_usdt_only", "stable_fallback_symbols",
]
_UNTIL_RE = re.compile(r"_until_\d{8}$", re.IGNORECASE)
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_DAY = np.timedelta64(1, "D")

ASSUMPTIONS = [
    "V1 Temiz gün (d ≤ T): birleşik USDT serisinde d etiketli mum var; mum half_day değil; d'yi kapsayan, severity ∈ "
    "{error, exclude} ve known_from ≤ T−1 olan kalite işareti yok (işaretin symbol'ü o satırın source_symbol'ü ya da "
    "asset_id). severity=flag (sıçrama, iğne) günü kirletmez. T günündeki mumun half_day işareti yok sayılır: 'son mum' "
    "işareti T sonrası veriye bağlıdır (veri T'de kesilince T'nin mumu son mum olur). Sayım birikimlidir: varlığın "
    "birleşik geçmişindeki tüm temiz günler, ardışık olmaları gerekmez; koşul ≥ min_clean_days (365).",
    "V2 'T'de işlem gören' = birleşik USDT serisinde gün etiketi T olan mum var (hacim veya işaret şartı yok).",
    "V3 L_d = max(USDT çifti quote hacmi, kampanyasız diğer stablecoin çiftlerinin USDT'ye çevrilmiş quote "
    "hacimlerinin en büyüğü); toplama yok. USDT çifti kampanyada olsa da her zaman sayılır. Mumu olmayan gün USDT "
    "hacmi 0, hiçbir çift yoksa L_d = 0. Pencere = gün etiketleri T−29..T (30 takvim günü), np.median.",
    "V4 Çevrim: diğer quote hacmi × o günün {Q}USDT kapanışı; o gün kapanış yoksa en fazla 7 gün öncekine kadar son "
    "kapanış (yalnız geriye), o da yoksa o çiftin o günkü hacmi sayılmaz.",
    "V5 Kampanya: fee_promotions satırının [start, end] günleri (gün etiketine yuvarlanır, uçlar dahil, boş end = "
    "açık uçlu) boyunca o çift L_d'ye girmez; kampanya dışındaki günlerde girer.",
    "V6 Diğer quote çifti → varlık: her kaynak segmentinde (source_symbol'ün ardışık koşusu; ya da asset_segments.csv) "
    "taban = source_symbol − 'USDT'; {taban}{Q} hacmi yalnızca o segmentin [ilk, son] günlerinde o varlığa yazılır "
    "(ör. RNDRBUSD → RENDERUSDT, eski LUNA çiftleri → LUNAUSDT_until_20220513). Quote hacmi oranla değişmez.",
    "V7 Kalite işaretleri likiditeyi değiştirmez; yalnızca temiz gün sayımını etkiler.",
    "V8 İsim dışlaması: settings universe.exclude alt listelerinin birleşimi, büyük harf tam eşleşme (sonek kalıbı yok: "
    "JUP kalır, BTCUP çıkar). Taban = asset_id − '_until_YYYYMMDD' − 'USDT'; ayrıca T'deki source_symbol'ün tabanı da "
    "kontrol edilir (biri listedeyse dışlanır).",
    "V9 Stablecoin yedeği: T−90..T kapanışlarından günlük basit getiriler, ≥ 20 gözlem varsa std (ddof=1) < 0,01 → "
    "dışla. A kademesi (BTC, ETH) bu yedek kontrolden muaftır (sakin dönemde BTC'nin yanlışlıkla elenmemesi için).",
    "V10 Sıralama: medyan likidite azalan, eşitlikte asset_id alfabetik; rank 1..N, BTC dahil sayılır.",
    "V11 Kademe: A = taban ∈ tiers.A.symbols (sırası ne olursa olsun). Diğerleri ham evren sırasıyla: sıra ≤ 20 → B "
    "(BTC/ETH ilk iki sırada değilse 1–2. sıradaki coin de B olur), 21–50 → C. Kademe N'den bağımsızdır; küçük N "
    "evreni büyük N evreninin ilk satırlarıdır. N > 50 desteklenmez (hata).",
    "V12 Kayma: A sabit 0,0005; B/C 30 günlük medyan likiditeyle ≥100M → 0,0005, ≥20M → 0,0010, diğer → 0,0020 "
    "(alt sınırlar dahil). Kademe, tavan ve kayma ay boyunca sabittir.",
    "V13 Sermaye → N: max_capital yarı açık üst sınırdır (<3000 → 10, <15000 → 20, diğer → 30). SPEC'e göre tam "
    "15000 USDT → 20 olurdu; yalnız bu sınır değeri farklıdır.",
    "V14 Aylar: karar günü T veri aralığında olan her ay yazılır; uygun coin yoksa başlıklı boş dosya.",
]


# --- yardımcılar ---------------------------------------------------------------------------------------------------

def base_asset(symbol: str, quote: str = QUOTE) -> str:
    """asset_id / USDT çifti → taban varlık (ör. LUNAUSDT_until_20220513 → LUNA, RENDERUSDT → RENDER)."""
    s = _UNTIL_RE.sub("", str(symbol).upper())
    return s[: -len(quote)] if s.endswith(quote) and len(s) > len(quote) else s


def is_usdt_asset(asset_id: str) -> bool:
    s = _UNTIL_RE.sub("", str(asset_id).upper())
    return s.endswith(QUOTE) and len(s) > len(QUOTE)


def split_other_quote(symbol: str, quotes) -> tuple[str, str] | None:
    """USDT dışı stablecoin çifti → (taban, quote); USDT çifti veya listede olmayan quote ise None.
    Varsayım: symbols_raw.csv yoksa en uzun quote soneki eşleşir (FDUSD, BUSD, USDC, TUSD)."""
    s = str(symbol).upper()
    if s.endswith(QUOTE):
        return None
    for q in sorted((str(q).upper() for q in quotes), key=len, reverse=True):
        if s.endswith(q) and len(s) > len(q):
            return s[: -len(q)], q
    return None


def _to_days(values) -> np.ndarray:
    """Tarih benzeri değerler → datetime64[D] (UTC; tz-aware gelirse UTC'ye çevrilip tz atılır)."""
    s = pd.to_datetime(pd.Series(values), utc=True)
    return s.dt.tz_localize(None).to_numpy().astype("datetime64[D]")


def decision_time(month: str) -> pd.Timestamp:
    """Ay M ('YYYY-MM') için karar günü T = M−1 ayının son günü (CONTRACTS §1)."""
    return pd.Period(month, "M").start_time.normalize() - pd.Timedelta(days=1)


def universe_month_for_decision_day(t) -> str:
    """t günündeki karar (t + 1 gün)'ün ayının evrenini kullanır (CONTRACTS §1)."""
    return (pd.Timestamp(t).normalize() + pd.Timedelta(days=1)).strftime("%Y-%m")


def exclusion_set(cfg: Mapping[str, Any]) -> frozenset[str]:
    ex = cfg["universe"]["exclude"]
    lists = ex.values() if isinstance(ex, Mapping) else [ex]
    return frozenset(str(s).upper() for lst in lists for s in lst)


def _tier_a_bases(cfg) -> frozenset[str]:
    out = set()
    for t in cfg["universe"]["tiers"].values():
        out.update(str(s).upper() for s in t.get("symbols", []))
    return frozenset(out)


def _max_rank(cfg) -> int:
    return max(int(t["ranks"][1]) for t in cfg["universe"]["tiers"].values() if "ranks" in t)


def size_for_capital(capital: float, cfg: Mapping[str, Any] | None = None) -> int:
    """Alt-coin sistemine ayrılan sermaye → evren büyüklüğü (saf fonksiyon; sonuçlardan önce seçilir). V13."""
    cfg = cfg if cfg is not None else load_settings()
    rows = sorted(cfg["universe"]["size_by_capital"],
                  key=lambda r: (r["max_capital"] is None, r["max_capital"] or 0))
    for r in rows:
        m = r["max_capital"]
        if m is None or capital < m or (r.get("inclusive", False) and capital == m):
            return int(r["size"])
    raise ValueError(f"size_by_capital {capital} için bir satır içermiyor")


def default_sizes(cfg: Mapping[str, Any]) -> list[int]:
    """Yazılacak büyüklükler: temel + sermaye tablosu + ızgara komşuları (settings'ten türetilir: 10/20/30/50)."""
    u = cfg["universe"]
    sizes = {int(u["size"])} | {int(r["size"]) for r in u["size_by_capital"]}
    sizes |= {int(n) for n in cfg.get("evaluation", {}).get("grid", {}).get("universe_size", [])}
    return sorted(sizes)


def assign_tiers(bases, ranks, median_liquidity, cfg: Mapping[str, Any]):
    """(taban, sıra, medyan likidite) → (kademe, tavan, kayma) listeleri. V11, V12."""
    u = cfg["universe"]
    sym_tiers = [(n, {str(s).upper() for s in t["symbols"]}, float(t["cap"]))
                 for n, t in u["tiers"].items() if "symbols" in t]
    rank_tiers = sorted((int(t["ranks"][0]), int(t["ranks"][1]), n, float(t["cap"]))
                        for n, t in u["tiers"].items() if "ranks" in t)
    slip = u["slippage"]
    by_liq = sorted(slip["by_liquidity"], key=lambda r: -r["min_liquidity"])
    tiers, caps, slips = [], [], []
    for b, r, m in zip(bases, ranks, median_liquidity):
        name = cap = None
        for n, syms, c in sym_tiers:
            if str(b).upper() in syms:
                name, cap = n, c
                break
        if name is None:
            for _lo, hi, n, c in rank_tiers:  # V11: alt sınırın altındaki sıralar ilk sıra kademesine düşer
                if r <= hi:
                    name, cap = n, c
                    break
        if name is None:
            raise ValueError(f"sıra {r} hiçbir kademeye düşmüyor (en fazla {_max_rank(cfg)})")
        if name in slip and not isinstance(slip[name], (list, dict)):
            s = float(slip[name])
        else:
            s = next(float(row["slippage"]) for row in by_liq if m >= row["min_liquidity"])
        tiers.append(name)
        caps.append(cap)
        slips.append(s)
    return tiers, caps, slips


def _empty_table() -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": pd.Series([], dtype="str"), "rank": pd.Series([], dtype="int64"),
        "median_liquidity": pd.Series([], dtype="float64"), "tier": pd.Series([], dtype="str"),
        "cap": pd.Series([], dtype="float64"), "slippage": pd.Series([], dtype="float64"),
    })


# --- bellek içi veri -----------------------------------------------------------------------------------------------

@dataclass
class UniverseData:
    """Gün × varlık geniş diziler (index 0 = dates[0], ardışık günler)."""

    dates: np.ndarray            # datetime64[D]
    assets: np.ndarray           # object: asset_id (sıralı)
    bases: np.ndarray            # object: base_asset(asset_id)
    close: np.ndarray            # float, NaN = mum yok
    usdt_qv: np.ndarray          # float, mum yoksa 0
    other_qv: np.ndarray         # float, kampanyasız çevrilmiş diğer quote hacimlerinin max'ı; NaN = yok
    bar: np.ndarray              # bool
    half: np.ndarray             # bool (half_day)
    seg_asset: np.ndarray        # int: segment → varlık indeksi
    seg_symbol: np.ndarray       # object: segmentin source_symbol'ü
    seg_base: np.ndarray         # object: base_asset(seg_symbol)
    seg_i0: np.ndarray           # int, dahil
    seg_i1: np.ndarray           # int, dahil
    _pos: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._pos = {a: j for j, a in enumerate(self.assets)}

    def day_index(self, day) -> int | None:
        d = np.datetime64(pd.Timestamp(day).strftime("%Y-%m-%d"), "D")
        i = int((d - self.dates[0]) / _DAY)
        return i if 0 <= i < len(self.dates) else None

    def asset_index(self, asset_id: str) -> int:
        return self._pos[asset_id]


def _dense(df: pd.DataFrame, col: str, d0: np.datetime64, n: int) -> np.ndarray:
    """Uzun seri → [d0, d0+n) günlük yoğun dizi (NaN = yok)."""
    out = np.full(n, np.nan)
    if df is None or len(df) == 0:
        return out
    idx = ((_to_days(df["open_time"]) - d0) / _DAY).astype(np.int64)
    ok = (idx >= 0) & (idx < n)
    out[idx[ok]] = pd.to_numeric(df[col], errors="coerce").to_numpy(float)[ok]
    return out


def prepare_data(
    merged: Mapping[str, pd.DataFrame],
    other_quote: Mapping[str, pd.DataFrame] | None = None,
    stable_closes: Mapping[str, pd.DataFrame] | None = None,
    promotions: pd.DataFrame | None = None,
    segments: pd.DataFrame | None = None,
    cfg: Mapping[str, Any] | None = None,
    pair_info: Mapping[str, tuple[str, str]] | None = None,
) -> UniverseData:
    """Adaptör çıktılarından geniş dizileri kurar.

    merged: asset_id → DataFrame (open_time, close, quote_volume, [half_day], [source_symbol]) — CONTRACTS §4.
    other_quote: çift sembolü (ör. ETHBUSD) → DataFrame (open_time, quote_volume) — CONTRACTS §3.
    stable_closes: '{Q}USDT' → DataFrame (open_time, close); yoksa `merged` içinden alınır.
    promotions: fee_promotions (symbol, start, end). segments: asset_segments (asset_id, source_symbol, start, end);
    verilmezse source_symbol koşularından türetilir. pair_info: çift → (taban, quote), ör. symbols_raw'dan.
    """
    cfg = cfg if cfg is not None else load_settings()
    quotes = [str(q).upper() for q in cfg["data"]["other_quotes"]]
    stable_pairs = {str(p).upper() for p in cfg["data"]["stable_usdt_pairs"]}

    usdt = {str(a): df for a, df in merged.items() if is_usdt_asset(a) and df is not None and len(df)}
    if not usdt:
        raise ValueError("birleşik USDT serisi yok")
    assets = sorted(usdt)
    days_by = {a: _to_days(usdt[a]["open_time"]) for a in assets}
    d0 = min(d.min() for d in days_by.values())
    d1 = max(d.max() for d in days_by.values())
    n, m = int((d1 - d0) / _DAY) + 1, len(assets)

    close = np.full((n, m), np.nan)
    usdt_qv = np.zeros((n, m))
    bar = np.zeros((n, m), bool)
    half = np.zeros((n, m), bool)
    segs: list[tuple[int, str, int, int]] = []
    for j, a in enumerate(assets):
        df = usdt[a]
        days = days_by[a]
        order = np.argsort(days, kind="stable")
        idx = ((days[order] - d0) / _DAY).astype(np.int64)
        close[idx, j] = pd.to_numeric(df["close"], errors="coerce").to_numpy(float)[order]
        qv = pd.to_numeric(df["quote_volume"], errors="coerce").to_numpy(float)[order]
        usdt_qv[idx, j] = np.nan_to_num(qv, nan=0.0)
        bar[idx, j] = True
        if "half_day" in df.columns:
            half[idx, j] = df["half_day"].fillna(False).to_numpy(bool)[order]
        if "source_symbol" in df.columns:
            src = df["source_symbol"].astype(object).where(df["source_symbol"].notna(), a).to_numpy(object)[order]
        else:
            src = np.full(len(idx), a, dtype=object)
        brk = np.flatnonzero(src[1:] != src[:-1]) + 1
        for s, e in zip(np.r_[0, brk], np.r_[brk - 1, len(idx) - 1]):
            segs.append((j, str(src[s]).upper(), int(idx[s]), int(idx[e])))

    if segments is not None and len(segments):
        pos = {a: j for j, a in enumerate(assets)}
        st, en = _to_days(segments["start"]), _to_days(segments["end"])
        segs = []
        for a, sym, s, e in zip(segments["asset_id"], segments["source_symbol"], st, en):
            if str(a) not in pos:
                continue
            i0 = 0 if np.isnat(s) else int((s - d0) / _DAY)
            i1 = n - 1 if np.isnat(e) else int((e - d0) / _DAY)
            i0, i1 = max(i0, 0), min(i1, n - 1)
            if i0 <= i1:
                segs.append((pos[str(a)], str(sym).upper(), i0, i1))

    # diğer quote çiftlerinin (taban, quote) bilgisi
    pairs: dict[str, tuple[str, str]] = {}
    for pair in other_quote or {}:
        p = str(pair).upper()
        info = (pair_info or {}).get(p) or split_other_quote(p, quotes)
        if info is not None and str(info[1]).upper() in quotes:
            pairs[p] = (str(info[0]).upper(), str(info[1]).upper())

    # V4: {Q}USDT kapanışıyla çevrim (yalnız geriye taşıma)
    conv: dict[str, np.ndarray] = {}
    for q in sorted({q for _, q in pairs.values()}):
        pair = f"{q}{QUOTE}"
        src_df = None
        if pair in stable_pairs:
            src_df = (stable_closes or {}).get(pair)
            if src_df is None:
                src_df = usdt.get(pair)
        if src_df is None:
            warnings.warn(f"{pair} kapanışı yok; {q} çiftleri likiditeye girmez", stacklevel=2)
            continue
        conv[q] = pd.Series(_dense(src_df, "close", d0, n)).ffill(limit=CONVERSION_FFILL_DAYS).to_numpy()

    # V5: kampanya pencereleri (çift → gün aralıkları)
    promo: dict[str, list[tuple[int, int]]] = defaultdict(list)
    if promotions is not None and len(promotions):
        st, en = _to_days(promotions["start"]), _to_days(promotions["end"])
        for sym, s, e in zip(promotions["symbol"], st, en):
            i0 = 0 if np.isnat(s) else int((s - d0) / _DAY)
            i1 = n - 1 if np.isnat(e) else int((e - d0) / _DAY)
            i0, i1 = max(i0, 0), min(i1, n - 1)
            if i0 <= i1:
                promo[str(sym).upper()].append((i0, i1))

    # V6: diğer quote çiftleri → taban → segment günleri
    by_base: dict[str, list[np.ndarray]] = defaultdict(list)
    for pair, df in (other_quote or {}).items():
        p = str(pair).upper()
        if p not in pairs or pairs[p][1] not in conv:
            continue
        vals = _dense(df, "quote_volume", d0, n) * conv[pairs[p][1]]
        for i0, i1 in promo.get(p, []):
            vals[i0 : i1 + 1] = np.nan
        by_base[pairs[p][0]].append(vals)

    other = np.full((n, m), np.nan)
    seg_base = [base_asset(s) for _, s, _, _ in segs]
    for (j, _sym, i0, i1), b in zip(segs, seg_base):
        for vals in by_base.get(b, []):
            other[i0 : i1 + 1, j] = np.fmax(other[i0 : i1 + 1, j], vals[i0 : i1 + 1])

    return UniverseData(
        dates=np.arange(d0, d1 + _DAY, _DAY),
        assets=np.array(assets, dtype=object),
        bases=np.array([base_asset(a) for a in assets], dtype=object),
        close=close, usdt_qv=usdt_qv, other_qv=other, bar=bar, half=half,
        seg_asset=np.array([s[0] for s in segs], dtype=np.int64),
        seg_symbol=np.array([s[1] for s in segs], dtype=object),
        seg_base=np.array(seg_base, dtype=object),
        seg_i0=np.array([s[2] for s in segs], dtype=np.int64),
        seg_i1=np.array([s[3] for s in segs], dtype=np.int64),
    )


@dataclass
class FlagCells:
    """Temizliği bozan işaretlerin (varlık, gün aralığı, known_from) hücreleri."""

    asset: np.ndarray
    i0: np.ndarray
    i1: np.ndarray
    known: np.ndarray  # datetime64[D]


def prepare_flags(data: UniverseData, flags: pd.DataFrame | None) -> FlagCells:
    """quality_flags (CONTRACTS §5) → hücreler. İşaret symbol'ü bir segmentin source_symbol'ü (o segmentin günleri)
    veya bir asset_id (varlığın tüm günleri) ile eşleşir. Boş period_start/end açık uç; boş known_from → period_end."""
    empty = FlagCells(np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64),
                      np.zeros(0, "datetime64[D]"))
    if flags is None or len(flags) == 0:
        return empty
    f = flags[flags["severity"].astype(str).str.lower().isin(BAD_SEVERITIES)]
    if len(f) == 0:
        return empty
    n, d0 = len(data.dates), data.dates[0]
    ps, pe, kf = _to_days(f["period_start"]), _to_days(f["period_end"]), _to_days(f["known_from"])
    kf = np.where(np.isnat(kf), pe, kf)
    by_sym: dict[str, list[int]] = defaultdict(list)
    for k, s in enumerate(data.seg_symbol):
        by_sym[s].append(k)
    out_a, out_0, out_1, out_k = [], [], [], []
    for sym, s, e, k in zip(f["symbol"].astype(str).str.upper(), ps, pe, kf):
        if np.isnat(k):
            continue
        lo = 0 if np.isnat(s) else int((s - d0) / _DAY)
        hi = n - 1 if np.isnat(e) else int((e - d0) / _DAY)
        cand = [(data.seg_asset[g], data.seg_i0[g], data.seg_i1[g]) for g in by_sym.get(sym, [])]
        if sym in data._pos:
            cand.append((data._pos[sym], 0, n - 1))
        for a, g0, g1 in cand:
            a0, a1 = max(lo, g0, 0), min(hi, g1, n - 1)
            if a0 <= a1:
                out_a.append(a)
                out_0.append(a0)
                out_1.append(a1)
                out_k.append(k)
    if not out_a:
        return empty
    return FlagCells(np.array(out_a, np.int64), np.array(out_0, np.int64), np.array(out_1, np.int64),
                     np.array(out_k, dtype="datetime64[D]"))


def _unclean_cover(fc: FlagCells, cols: np.ndarray, n_assets: int, i_t: int, known_cut: np.datetime64) -> np.ndarray:
    """(i_t+1, len(cols)) bool: known_from ≤ known_cut olan işaretlerin kapsadığı hücreler (fark dizisi + cumsum)."""
    colpos = np.full(n_assets, -1, np.int64)
    colpos[cols] = np.arange(len(cols))
    sel = (fc.known <= known_cut) & (fc.i0 <= i_t)
    if len(fc.asset):
        sel &= colpos[fc.asset] >= 0
    diff = np.zeros((i_t + 2, len(cols)), np.int32)
    if sel.any():
        c = colpos[fc.asset[sel]]
        np.add.at(diff, (fc.i0[sel], c), 1)
        np.add.at(diff, (np.minimum(fc.i1[sel], i_t) + 1, c), -1)
    return np.cumsum(diff[:-1], axis=0) > 0


# --- aylık hesap ---------------------------------------------------------------------------------------------------

@dataclass
class _MonthEval:
    month: str
    i_t: int
    cols: np.ndarray                 # 365 gün kuralını geçen varlık indeksleri
    med: dict[str, np.ndarray]       # "max" / "usdt" → medyan likidite
    diag: dict[str, Any]


def _evaluate_month(data: UniverseData, month: str, cfg, fc: FlagCells) -> _MonthEval:
    u = cfg["universe"]
    t_day = decision_time(month)
    i_t = data.day_index(t_day)
    if i_t is None:
        raise ValueError(f"{month}: karar günü {t_day.date()} veri aralığı dışında")
    excl, a_bases = exclusion_set(cfg), _tier_a_bases(cfg)

    # 1) T'de işlem gören (V2)
    cols = np.flatnonzero(data.bar[i_t])
    # 2) isim listesi (V8)
    on_t = (data.seg_i0 <= i_t) & (data.seg_i1 >= i_t)
    src_base = dict(zip(data.seg_asset[on_t].tolist(), data.seg_base[on_t].tolist()))
    name_ex = np.array([data.bases[j] in excl or src_base.get(j, data.bases[j]) in excl for j in cols], bool)
    cols1 = cols[~name_ex]
    # 2b) stablecoin yedeği (V9)
    fb = u["stable_vol_fallback"]
    lo = max(i_t - int(fb["window_days"]), 0)
    c = data.close[lo : i_t + 1][:, cols1]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = c[1:] / c[:-1] - 1.0
        n_obs = np.isfinite(r).sum(axis=0)
        mean = np.nansum(r, axis=0) / n_obs
        std = np.sqrt(np.nansum((r - mean) ** 2, axis=0) / (n_obs - 1))
    is_a = np.array([data.bases[j] in a_bases for j in cols1], bool)
    stable_ex = (n_obs >= STABLE_FALLBACK_MIN_OBS) & (std < float(fb["max_std"])) & ~is_a
    cols2 = cols1[~stable_ex]
    # 3) temiz gün sayısı (V1)
    bar = data.bar[: i_t + 1][:, cols2]
    half = data.half[: i_t + 1][:, cols2]
    half[-1] = False  # T'nin half_day işareti yok sayılır
    known_cut = np.datetime64(t_day.strftime("%Y-%m-%d"), "D") - _DAY
    cover = _unclean_cover(fc, cols2, len(data.assets), i_t, known_cut)
    n_clean = (bar & ~half & ~cover).sum(axis=0)
    cols3 = cols2[n_clean >= int(u["min_clean_days"])]
    # 4–5) likidite ve 30 günlük medyan (V3)
    w = int(u["liquidity_window_days"])
    lo = i_t - w + 1
    uq = data.usdt_qv[max(lo, 0) : i_t + 1][:, cols3]
    oq = data.other_qv[max(lo, 0) : i_t + 1][:, cols3]
    if lo < 0:  # veri başlangıcından önceki günler: likidite 0
        uq = np.vstack([np.zeros((-lo, len(cols3))), uq])
        oq = np.vstack([np.full((-lo, len(cols3)), np.nan), oq])
    lmax = np.fmax(uq, oq)
    med = {"max": np.median(lmax, axis=0), "usdt": np.median(uq, axis=0)}
    thr = float(u["min_median_liquidity_usdt"])
    diag = {
        "month": month, "decision_time": t_day.strftime("%Y-%m-%d"),
        "n_trading": int(len(cols)), "n_name_excluded": int(name_ex.sum()),
        "n_stable_fallback": int(stable_ex.sum()), "n_clean_ok": int(len(cols3)),
        "n_liquid": int((med["max"] >= thr).sum()), "n_liquid_usdt_only": int((med["usdt"] >= thr).sum()),
        "stable_fallback_symbols": ";".join(str(data.assets[j]) for j in cols1[stable_ex]),
    }
    return _MonthEval(month, i_t, cols3, med, diag)


def _select(data: UniverseData, ev: _MonthEval, liquidity: str, size: int, cfg) -> pd.DataFrame:
    """Eşik (≥ 5M) → sırala (V10) → ilk N → kademe/tavan/kayma (V11, V12)."""
    med = ev.med[liquidity]
    keep = med >= float(cfg["universe"]["min_median_liquidity_usdt"])
    idx, mv = ev.cols[keep], med[keep]
    order = sorted(range(len(idx)), key=lambda k: (-mv[k], data.assets[idx[k]]))[: int(size)]
    if not order:
        return _empty_table()
    syms = [str(data.assets[idx[k]]) for k in order]
    meds = [float(mv[k]) for k in order]
    ranks = list(range(1, len(order) + 1))
    tiers, caps, slips = assign_tiers([data.bases[idx[k]] for k in order], ranks, meds, cfg)
    return pd.DataFrame({
        "symbol": pd.Series(syms, dtype="str"), "rank": pd.Series(ranks, dtype="int64"),
        "median_liquidity": pd.Series(meds, dtype="float64"), "tier": pd.Series(tiers, dtype="str"),
        "cap": pd.Series(caps, dtype="float64"), "slippage": pd.Series(slips, dtype="float64"),
    })


def available_months(data: UniverseData) -> list[str]:
    """Karar günü T (ay sonu) veri aralığında olan aylar."""
    first, last = pd.Timestamp(data.dates[0]), pd.Timestamp(data.dates[-1])
    out = []
    for p in pd.period_range(first, last, freq="M"):
        t_day = p.end_time.normalize()
        if first <= t_day <= last:
            out.append((p + 1).strftime("%Y-%m"))
    return out


@dataclass
class UniverseBuild:
    tables: dict[str, dict[str, pd.DataFrame]]   # varyant ("main", "usdt_only", "size_N") → ay → tablo
    diagnostics: pd.DataFrame
    size: int


def build_universes(
    data: UniverseData,
    months: list[str] | None = None,
    cfg: Mapping[str, Any] | None = None,
    flags: pd.DataFrame | FlagCells | None = None,
    size: int | None = None,
    sizes: list[int] | None = None,
) -> UniverseBuild:
    """Tüm aylar: ana evren (N = size, max likidite), T7 (sadece USDT, N = size) ve diğer büyüklükler."""
    cfg = cfg if cfg is not None else load_settings()
    size = int(size if size is not None else cfg["universe"]["size"])
    sizes = default_sizes(cfg) if sizes is None else [int(s) for s in sizes]
    if max([size, *sizes]) > _max_rank(cfg):
        raise ValueError(f"N > {_max_rank(cfg)} desteklenmez (V11)")
    fc = flags if isinstance(flags, FlagCells) else prepare_flags(data, flags)
    months = available_months(data) if months is None else list(months)
    tables: dict[str, dict[str, pd.DataFrame]] = {"main": {}, "usdt_only": {}}
    extra = [s for s in sizes if s != size]
    for s in extra:
        tables[f"size_{s}"] = {}
    diags = []
    for month in months:
        ev = _evaluate_month(data, month, cfg, fc)
        tables["main"][month] = _select(data, ev, "max", size, cfg)
        tables["usdt_only"][month] = _select(data, ev, "usdt", size, cfg)
        for s in extra:
            tables[f"size_{s}"][month] = _select(data, ev, "max", s, cfg)
        diags.append({**ev.diag, "size_main": size, "n_main": len(tables["main"][month]),
                      "n_usdt_only": len(tables["usdt_only"][month])})
    diag = pd.DataFrame(diags, columns=DIAG_COLUMNS) if diags else pd.DataFrame(columns=DIAG_COLUMNS)
    return UniverseBuild(tables, diag, size)


def build_universe_month(
    data: UniverseData,
    month: str,
    cfg: Mapping[str, Any] | None = None,
    flags: pd.DataFrame | FlagCells | None = None,
    size: int | None = None,
    liquidity: str = "max",
) -> pd.DataFrame:
    """Tek ay için evren tablosu. liquidity: 'max' (ana) veya 'usdt' (T7)."""
    cfg = cfg if cfg is not None else load_settings()
    size = int(size if size is not None else cfg["universe"]["size"])
    if size > _max_rank(cfg):
        raise ValueError(f"N > {_max_rank(cfg)} desteklenmez (V11)")
    fc = flags if isinstance(flags, FlagCells) else prepare_flags(data, flags)
    return _select(data, _evaluate_month(data, month, cfg, fc), liquidity, size, cfg)


# --- dosya G/Ç -----------------------------------------------------------------------------------------------------

def _variant_dir(universe_dir: Path, variant: str) -> Path:
    return universe_dir if variant == "main" else universe_dir / variant


def write_universes(build: UniverseBuild, out_dir: Path | str | None = None, cfg=None) -> Path:
    cfg = cfg if cfg is not None else load_settings()
    out = Path(out_dir) if out_dir is not None else settings_path(cfg, "universe")
    for variant, tabs in build.tables.items():
        d = _variant_dir(out, variant)
        d.mkdir(parents=True, exist_ok=True)
        for month, df in tabs.items():
            df.to_csv(d / f"{month}.csv", index=False, lineterminator="\n")
    out.mkdir(parents=True, exist_ok=True)
    build.diagnostics.to_csv(out / "diagnostics.csv", index=False, lineterminator="\n")
    return out


@lru_cache(maxsize=4096)
def _read_universe_csv(path: str, mtime_ns: int, size: int) -> pd.DataFrame:
    """Önbellekli okuma; anahtar (yol, mtime_ns, boyut) dosya yeniden yazılınca değişir."""
    df = pd.read_csv(path, dtype={"symbol": "str", "tier": "str"})
    if len(df) == 0:
        return _empty_table()
    return df.astype({"rank": "int64", "median_liquidity": "float64", "cap": "float64", "slippage": "float64"})


def load_universe(month: str, universe_dir: Path | str | None = None, variant: str = "main", cfg=None) -> pd.DataFrame:
    """universe/{variant}/{YYYY-MM}.csv → DataFrame (CONTRACTS §6). Dosya yoksa FileNotFoundError."""
    if universe_dir is None:
        universe_dir = settings_path(cfg if cfg is not None else load_settings(), "universe")
    p = _variant_dir(Path(universe_dir), variant) / f"{month}.csv"
    if not p.exists():
        raise FileNotFoundError(p)
    return _read_universe_csv(str(p), p.stat().st_mtime_ns, p.stat().st_size).copy()


def universe_for_decision_day(t, universe_dir: Path | str | None = None, variant: str = "main", cfg=None) -> pd.DataFrame:
    """t günündeki kararın evreni = (t + 1 gün)'ün ayının evreni (CONTRACTS §1)."""
    return load_universe(universe_month_for_decision_day(t), universe_dir, variant, cfg)


def _read_cols(p: Path, wanted: list[str]) -> pd.DataFrame:
    import pyarrow.parquet as pq

    names = set(pq.read_schema(p).names)
    return pd.read_parquet(p, columns=[c for c in wanted if c in names])


def load_merged_daily(merged_dir: Path | str | None = None) -> dict[str, pd.DataFrame]:
    """data/merged/1d/{ASSET_ID}.parquet → {asset_id: DataFrame}; yalnızca USDT varlıkları."""
    d = Path(merged_dir) if merged_dir is not None else ROOT / MERGED_DIR_DEFAULT / "1d"
    cols = ["open_time", "close", "quote_volume", "half_day", "source_symbol"]
    return {p.stem: _read_cols(p, cols) for p in sorted(d.glob("*.parquet")) if is_usdt_asset(p.stem)}


def pair_info_from_symbols_raw(symbols_raw: pd.DataFrame | Path | str | None, quotes) -> dict[str, tuple[str, str]]:
    """meta/symbols_raw.csv (symbol, quote, base, ...) → {çift: (taban, quote)} (yalnızca diğer stablecoin quote'ları)."""
    if symbols_raw is None:
        return {}
    df = symbols_raw if isinstance(symbols_raw, pd.DataFrame) else pd.read_csv(symbols_raw, dtype=str)
    qs = {str(q).upper() for q in quotes}
    df = df[df["quote"].astype(str).str.upper().isin(qs)].drop_duplicates("symbol")
    return {str(s).upper(): (str(b).upper(), str(q).upper()) for s, b, q in zip(df["symbol"], df["base"], df["quote"])}


def load_other_quote_daily(clean_dir: Path | str, quotes, pair_info: Mapping[str, tuple[str, str]] | None = None
                           ) -> tuple[dict[str, pd.DataFrame], dict[str, tuple[str, str]]]:
    """data/clean/1d/ içindeki diğer stablecoin quote çiftleri → ({çift: (open_time, quote_volume)}, {çift: (taban, quote)})."""
    out, info = {}, {}
    for p in sorted(Path(clean_dir).glob("*.parquet")):
        sym = p.stem.upper()
        bq = pair_info.get(sym) if pair_info else split_other_quote(sym, quotes)
        if bq is None:
            continue
        out[sym] = _read_cols(p, ["open_time", "quote_volume"])
        info[sym] = bq
    return out, info


def load_stable_closes(clean_dir: Path | str, cfg) -> dict[str, pd.DataFrame]:
    out = {}
    for pair in cfg["data"]["stable_usdt_pairs"]:
        p = Path(clean_dir) / f"{pair}.parquet"
        if p.exists():
            out[str(pair).upper()] = _read_cols(p, ["open_time", "close"])
    return out


def load_quality_flags(path: Path | str | None = None, cfg=None) -> pd.DataFrame | None:
    p = Path(path) if path is not None else settings_path(cfg if cfg is not None else load_settings(), "quality_flags")
    if not p.exists():
        warnings.warn(f"{p} yok; kalite işareti kullanılmadan kuruluyor", stacklevel=2)
        return None
    return pd.read_parquet(p)


def load_fee_promotions(path: Path | str | None = None, cfg=None) -> pd.DataFrame | None:
    if path is None:
        path = settings_path(cfg if cfg is not None else load_settings(), "meta") / "fee_promotions.csv"
    p = Path(path)
    if not p.exists():
        warnings.warn(f"{p} yok; kampanya dışlaması yapılmadan kuruluyor", stacklevel=2)
        return None
    return pd.read_csv(p, dtype=str)


def load_asset_segments(path: Path | str) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"asset_id": str, "source_symbol": str})


def build_from_disk(
    cfg: Mapping[str, Any] | None = None,
    *,
    merged_dir=None, clean_dir=None, flags_path=None, promotions_path=None, segments_path=None,
    symbols_raw_path=None, out_dir=None, report_path=None,
    months: list[str] | None = None, size: int | None = None, capital: float | None = None,
    sizes: list[int] | None = None, report: bool = True,
) -> UniverseBuild:
    """Orkestratör girişi: girdileri varsayılan yollardan okur, tüm ayları kurar, universe/ ve raporu yazar."""
    cfg = cfg if cfg is not None else load_settings()
    if size is None and capital is not None:
        size = size_for_capital(capital, cfg)
    quotes = cfg["data"]["other_quotes"]
    clean = Path(clean_dir) if clean_dir is not None else settings_path(cfg, "clean") / "1d"
    if symbols_raw_path is None:
        cand = settings_path(cfg, "meta") / "symbols_raw.csv"
        symbols_raw_path = cand if cand.exists() else None
    pinfo = pair_info_from_symbols_raw(symbols_raw_path, quotes)
    other, pinfo = load_other_quote_daily(clean, quotes, pinfo or None)
    data = prepare_data(
        load_merged_daily(merged_dir), other_quote=other, stable_closes=load_stable_closes(clean, cfg),
        promotions=load_fee_promotions(promotions_path, cfg),
        segments=load_asset_segments(segments_path) if segments_path else None, cfg=cfg, pair_info=pinfo,
    )
    build = build_universes(data, months=months, cfg=cfg, flags=load_quality_flags(flags_path, cfg),
                            size=size, sizes=sizes)
    out = write_universes(build, out_dir, cfg)
    if report:
        write_report(out, report_path, cfg)
    return build


# --- rapor ---------------------------------------------------------------------------------------------------------

def _read_variant(d: Path) -> dict[str, pd.DataFrame]:
    if not d.exists():
        return {}
    files = [p for p in sorted(d.glob("*.csv")) if _MONTH_RE.match(p.stem)]
    return {p.stem: _read_universe_csv(str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files}


def _rel(p: Path) -> str:
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def _fmt(x: float, nd: int = 1) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def write_report(universe_dir: Path | str | None = None, report_path: Path | str | None = None, cfg=None) -> Path:
    """reports/G6_universe.md: aylık evren büyüklüğü, devir, kademe sayıları, T7 karşılaştırması, eleme hunisi."""
    cfg = cfg if cfg is not None else load_settings()
    udir = Path(universe_dir) if universe_dir is not None else settings_path(cfg, "universe")
    rpath = Path(report_path) if report_path is not None else settings_path(cfg, "reports") / "G6_universe.md"
    main, usdt = _read_variant(udir), _read_variant(udir / "usdt_only")
    dpath = udir / "diagnostics.csv"
    diag = pd.read_csv(dpath, dtype={"month": str, "stable_fallback_symbols": str}).set_index("month") \
        if dpath.exists() else pd.DataFrame()
    u = cfg["universe"]
    n_target = int(diag["size_main"].iloc[0]) if len(diag) and "size_main" in diag else int(u["size"])

    rows, prev, prev_u = [], None, None
    for month in sorted(main):
        cur = set(main[month]["symbol"])
        cu = set(usdt[month]["symbol"]) if month in usdt else set()
        ins = len(cur - prev) if prev is not None else np.nan
        outs = len(prev - cur) if prev is not None else np.nan
        denom = (len(prev) + len(cur)) if prev is not None else 0
        turn = (ins + outs) / denom if denom else np.nan
        denom_u = (len(prev_u) + len(cu)) if prev_u is not None else 0
        turn_u = (len(cu - prev_u) + len(prev_u - cu)) / denom_u if denom_u else np.nan
        tiers = main[month]["tier"].value_counts()
        d = diag.loc[month] if month in diag.index else None
        rows.append({
            "month": month, "T": decision_time(month).strftime("%Y-%m-%d"), "n": len(cur),
            "A": int(tiers.get("A", 0)), "B": int(tiers.get("B", 0)), "C": int(tiers.get("C", 0)),
            "in": ins, "out": outs, "turn": turn, "n_u": len(cu), "overlap": len(cur & cu), "turn_u": turn_u,
            "funnel": "—" if d is None else
            f"{d['n_trading']} → {d['n_trading'] - d['n_name_excluded'] - d['n_stable_fallback']} → "
            f"{d['n_clean_ok']} → {d['n_liquid']}",
        })
        prev, prev_u = cur, cu
    df = pd.DataFrame(rows)

    lines = [
        "# G6 — Coin evreni raporu", "",
        f"Üretildi: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC · kaynak: `{_rel(udir)}` · "
        f"`trend.universe.write_report`", "",
        f"Kurallar (settings.yaml): N = {n_target}, en az {u['min_clean_days']} temiz gün, "
        f"{u['liquidity_window_days']} günlük medyan likidite ≥ {u['min_median_liquidity_usdt'] / 1e6:g}M USDT, "
        "L_d = max(USDT, kampanyasız en büyük diğer stablecoin çifti). Karar günü T = önceki ayın son günü.", "",
    ]
    if df.empty:
        lines += ["Evren dosyası bulunamadı.", ""]
    else:
        nonempty = df[df["n"] > 0]
        y1920 = df[df["month"].str[:4].isin(["2019", "2020"])]
        lines += ["## Özet", ""]
        lines.append(f"- Ay sayısı: {len(df)} ({df['month'].iloc[0]} – {df['month'].iloc[-1]}); boş evrenli ay: "
                     f"{int((df['n'] == 0).sum())}" + (f"; ilk dolu ay: {nonempty['month'].iloc[0]}"
                                                         if len(nonempty) else ""))
        if len(y1920):
            lines.append(f"- 2019–2020 evren büyüklüğü: min {y1920['n'].min()}, medyan {y1920['n'].median():g}, "
                         f"maks {y1920['n'].max()} (SPEC beklentisi 15–30, 20'nin altında kalabilir); "
                         f"N = {n_target} altında kalan ay: {int((y1920['n'] < n_target).sum())} / {len(y1920)}")
        lines.append(f"- N = {n_target} altında kalan ay (tümü): {int((df['n'] < n_target).sum())}")
        lines.append(f"- Ortalama aylık devir (giren+çıkan)/(önceki+şimdiki): ana {_fmt(df['turn'].mean(), 3)}, "
                     f"sadece USDT (T7) {_fmt(df['turn_u'].mean(), 3)}")
        ov = (df["overlap"] / df["n"].where(df["n"] > 0)).mean()
        lines.append(f"- Ana evrenin sadece-USDT evreniyle ortalama örtüşmesi: {_fmt(ov * 100 if ov == ov else np.nan)}%")
        lines += ["", "## Yıllara göre", "",
                  "| Yıl | Ay | Ort. büyüklük | Min | Maks | N altında ay | Ort. devir | Ort. T7 büyüklük |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for year, g in df.groupby(df["month"].str[:4]):
            lines.append(f"| {year} | {len(g)} | {_fmt(g['n'].mean())} | {g['n'].min()} | {g['n'].max()} | "
                         f"{int((g['n'] < n_target).sum())} | {_fmt(g['turn'].mean(), 3)} | {_fmt(g['n_u'].mean())} |")
        lines += ["", "## Aylık", "",
                  "Huni: T'de işlem gören → isim ve stablecoin yedeği sonrası → 365 temiz gün → likidite ≥ eşik "
                  "(N kesmesinden önce).", "",
                  "| Ay | T | Büyüklük | A | B | C | Giren | Çıkan | Devir | T7 büyüklük | Ortak | T7 devir | Huni |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for r in rows:
            i = "—" if r["in"] != r["in"] else int(r["in"])
            o = "—" if r["out"] != r["out"] else int(r["out"])
            lines.append(f"| {r['month']} | {r['T']} | {r['n']} | {r['A']} | {r['B']} | {r['C']} | {i} | {o} | "
                         f"{_fmt(r['turn'], 2)} | {r['n_u']} | {r['overlap']} | {_fmt(r['turn_u'], 2)} | "
                         f"{r['funnel']} |")
        if len(diag) and "stable_fallback_symbols" in diag:
            fb = diag["stable_fallback_symbols"].dropna()
            fb = fb[fb.astype(str).str.len() > 0]
            lines += ["", "## Stablecoin yedek kontrolüyle (90 gün std < %1) dışlananlar", ""]
            lines += [f"- {m}: {s.replace(';', ', ')}" for m, s in fb.items()] or ["- Yok."]
    lines += ["", "## Varsayımlar", ""] + [f"- {a}" for a in ASSUMPTIONS]
    lines += ["", "## settings.yaml'da olmayan parametreler (modül sabiti, TODO(settings))", "",
              f"- paths.merged = `{MERGED_DIR_DEFAULT}`",
              f"- universe.clean_day_bad_severities = {list(BAD_SEVERITIES)}",
              f"- universe.stable_vol_fallback.min_obs = {STABLE_FALLBACK_MIN_OBS}",
              f"- universe.conversion_ffill_days = {CONVERSION_FFILL_DAYS}", ""]
    rpath.parent.mkdir(parents=True, exist_ok=True)
    rpath.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return rpath


# --- CLI -----------------------------------------------------------------------------------------------------------

def _month_range(start: str, end: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m trend.universe", description="G6 coin evreni")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="evreni kur, universe/ ve raporu yaz")
    g = b.add_mutually_exclusive_group()
    g.add_argument("--size", type=int, help="ana evren büyüklüğü (varsayılan settings universe.size)")
    g.add_argument("--capital", type=float, help="alt-coin sermayesi → size_by_capital ile N")
    b.add_argument("--sizes", type=int, nargs="*", help="ek büyüklükler (varsayılan 10 20 30 50)")
    b.add_argument("--start", help="ilk ay YYYY-MM (varsayılan: veriden)")
    b.add_argument("--end", help="son ay YYYY-MM")
    for opt in ("merged-dir", "clean-dir", "flags", "promotions", "segments", "symbols-raw", "out-dir", "report-path"):
        b.add_argument(f"--{opt}")
    b.add_argument("--no-report", action="store_true")
    r = sub.add_parser("report", help="universe/ dosyalarından raporu yeniden üret")
    r.add_argument("--universe-dir")
    r.add_argument("--report-path")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        months = None
        if a.start or a.end:
            if not (a.start and a.end):
                ap.error("--start ve --end birlikte verilmeli")
            months = _month_range(a.start, a.end)
        build = build_from_disk(
            merged_dir=a.merged_dir, clean_dir=a.clean_dir, flags_path=a.flags, promotions_path=a.promotions,
            segments_path=a.segments, symbols_raw_path=a.symbols_raw, out_dir=a.out_dir, report_path=a.report_path,
            months=months, size=a.size, capital=a.capital, sizes=a.sizes, report=not a.no_report,
        )
        sizes = [len(t) for t in build.tables["main"].values()]
        print(f"{len(sizes)} ay yazıldı (N = {build.size}); büyüklük min {min(sizes, default=0)}, "
              f"maks {max(sizes, default=0)}")
    else:
        print(write_report(a.universe_dir, a.report_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
