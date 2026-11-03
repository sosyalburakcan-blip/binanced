"""G5 — Meta tablolar ve birleştirilmiş seriler (SPEC "Sembol eşleştirme tablosu", CONTRACTS §4).

- `meta/symbol_map.csv`, `meta/fee_promotions.csv`, `meta/delist_announcements.csv` yüklenir ve doğrulanır.
- `build_merged` sembol tablosunu temiz serilere uygular → `data/merged/{interval}/{ASSET_ID}.parquet` +
  `meta/asset_segments.csv`.
- `find_candidates` kalite bölünme kontrolünden ve "biri biterken diğeri başlayan" USDT çiftlerinden aday üretir.

Varsayımlar (raporda da listelenir):
- `build_merged` varsayılan olarak yalnızca `verified=yes` satırları uygular; `candidate` satırlar kullanıcı onayı
  olmadan veriyi değiştirmez (`include_candidates=True` ile denenebilir). Tablo onayı ayrı bir kapıdır (SPEC).
- Zaman alanları UTC, "YYYY-MM-DD HH:MM" veya yalnız tarih "YYYY-MM-DD". Mum ataması: eski parça
  open_time ≤ old_last_trade (yalnız tarihte: o günün sonuna kadar), yeni parça open_time ≥ floor(new_first_trade)
  (yalnız tarihte: o günün başından). Aynı sembolde (BNX bölünmesi, LUNA) iki sınır arasında kalan mum atanamaz ve
  uyarıyla düşürülür.
- Farklı sembollü RENAME/REDENOM'da sınır verinin kendisidir: eski çiftin tüm mumları alınır, yalnızca yeni çiftin
  ilk mumuyla çakışanlar düşer; tablo zamanlarıyla uyuşmazlık uyarı olarak raporlanır.
- Zincirler (ör. BNX ×100 → BNX → FORM) birleştirilir; her parçanın oranı zincir boyunca oranların çarpımıdır.
  Fiyat / oran, taban hacim ve taker_buy_base × oran; quote hacim, taker_buy_quote ve işlem sayısı değişmez.
- MERGE_INTO_EXISTING ve DELIST seriyi değiştirmez (ayrı seri olarak biter; delist kuralı motorda).
- `meta/asset_segments.csv` 1d çalıştırmasından yazılır; 1h için `meta/asset_segments_1h.csv` (CONTRACTS tek dosya
  der, aralık ayrımı varsayımdır).
- Yalnızca USDT çiftleri birleştirilir (sembol tablosu USDT çift adlarıyla yazılır); diğer kotasyonlar temiz veriden okunur.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import numpy as np
import pandas as pd

from trend.config import ROOT, load_settings
from trend.config import path as cfg_path
from trend.quality import INTERVAL_FREQ, INTERVAL_STEP, quote_of

SYMBOL_MAP_COLUMNS = ["old_symbol", "new_symbol", "type", "ratio", "old_last_trade_utc", "new_first_trade_utc", "source", "verified"]
TYPES = ("RENAME", "REDENOM", "ASSET_CHANGE", "MERGE_INTO_EXISTING", "DELIST")
VERIFIED = ("yes", "candidate")
FEE_COLUMNS = ["symbol", "start", "end", "source"]
DELIST_COLUMNS = ["symbol", "announced_utc", "delist_utc", "kind", "source"]
DELIST_KINDS = ("delist", "monitoring_tag")
SEGMENT_COLUMNS = ["asset_id", "source_symbol", "start", "end", "ratio"]
CANDIDATE_COLUMNS = SYMBOL_MAP_COLUMNS + ["method", "detail"]
PRICE_COLS = ("open", "high", "low", "close")
BASE_VOLUME_COLS = ("volume", "taker_buy_base")

# Birleştirilmiş seriler dizini (CONTRACTS §4).
MERGED_DIR = load_settings()["paths"]["merged"]
# Aday arama penceresi (gün) ve çift eşleştirmede "yuvarlak oran" toleransı (fiyat boşlukta oynar;
# bölünme kontrolünün 0,02'sinden gevşek tutuldu, adaylar zaten kullanıcı incelemesine gider).
PAIR_MATCH_MAX_GAP_DAYS = int(load_settings()["meta"]["pair_match_max_gap_days"])
PAIR_MATCH_MIN_GAP_DAYS = int(load_settings()["meta"]["pair_match_min_gap_days"])
PAIR_MATCH_LOG10_TOL = float(load_settings()["meta"]["pair_match_log10_tol"])

_SYMBOL_RE = re.compile(r"^[A-Z0-9]+$")


# --------------------------------------------------------------------------------------------------------------------
# Zaman ve CSV yardımcıları
# --------------------------------------------------------------------------------------------------------------------


def parse_utc(value) -> tuple[pd.Timestamp | None, bool]:
    """'YYYY-MM-DD[ HH:MM[:SS]]' → (Timestamp, yalnız_tarih_mi). Boş → (None, False). Hatalıysa ValueError."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None, False
    s = str(value).strip()
    if not s:
        return None, False
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?", s):
        raise ValueError(f"zaman biçimi geçersiz: {s!r} (beklenen 'YYYY-MM-DD' veya 'YYYY-MM-DD HH:MM')")
    return pd.Timestamp(s).as_unit("ns"), len(s) == 10


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, dtype=str, keep_default_na=False, comment=None)
    return df


def _ts_series(values) -> pd.Series:
    """Metin zaman alanlarını tek tek `parse_utc` ile çevirir (karışık 'tarih' / 'tarih saat' biçimi)."""
    ts = [parse_utc(v)[0] for v in values]
    return pd.Series([pd.NaT if t is None else t for t in ts], dtype="datetime64[ns]")


def _check_columns(df: pd.DataFrame, columns: list[str], name: str) -> list[str]:
    errs = []
    missing = [c for c in columns if c not in df.columns]
    extra = [c for c in df.columns if c not in columns]
    if missing:
        errs.append(f"{name}: eksik kolon {missing}")
    if extra:
        errs.append(f"{name}: fazla kolon {extra}")
    return errs


def _ratio(v: str) -> float | None:
    v = str(v).strip()
    if not v:
        return None
    return float(v)


# --------------------------------------------------------------------------------------------------------------------
# Doğrulama ve yükleme
# --------------------------------------------------------------------------------------------------------------------


def validate_symbol_map(df: pd.DataFrame) -> list[str]:
    """Şema, tipler, izinli `type`/`verified`, oran > 0 ve türlere özgü kurallar. Hata listesi döner."""
    errs = _check_columns(df, SYMBOL_MAP_COLUMNS, "symbol_map")
    if errs:
        return errs
    seen = set()
    for i, r in df.iterrows():
        tag = f"satır {i + 2} ({r['old_symbol']}→{r['new_symbol']})"
        old, new, typ = r["old_symbol"].strip(), r["new_symbol"].strip(), r["type"].strip()
        if not _SYMBOL_RE.match(old):
            errs.append(f"{tag}: old_symbol geçersiz")
        if new and not _SYMBOL_RE.match(new):
            errs.append(f"{tag}: new_symbol geçersiz")
        if typ not in TYPES:
            errs.append(f"{tag}: type {typ!r} izinli değil {TYPES}")
        if r["verified"].strip() not in VERIFIED:
            errs.append(f"{tag}: verified {r['verified']!r} izinli değil {VERIFIED}")
        if not r["source"].strip():
            errs.append(f"{tag}: kaynak boş (SPEC: her satırın kaynağı var)")
        try:
            ratio = _ratio(r["ratio"])
            if ratio is not None and not (math.isfinite(ratio) and ratio > 0):
                errs.append(f"{tag}: oran > 0 olmalı")
        except ValueError:
            errs.append(f"{tag}: oran sayı değil: {r['ratio']!r}")
            ratio = None
        try:
            t_old, _ = parse_utc(r["old_last_trade_utc"])
            t_new, _ = parse_utc(r["new_first_trade_utc"])
        except ValueError as e:
            errs.append(f"{tag}: {e}")
            continue
        if typ == "RENAME":
            if ratio != 1.0:
                errs.append(f"{tag}: RENAME oranı 1 olmalı")
            if not new or new == old:
                errs.append(f"{tag}: RENAME için farklı new_symbol gerekli")
        elif typ == "REDENOM":
            if ratio is None or ratio == 1.0:
                errs.append(f"{tag}: REDENOM oranı gerekli ve ≠ 1")
            if not new:
                errs.append(f"{tag}: REDENOM için new_symbol gerekli")
            if new == old and (t_old is None or t_new is None):
                errs.append(f"{tag}: aynı sembolde REDENOM için iki zaman da gerekli")
        elif typ == "ASSET_CHANGE":
            if new != old:
                errs.append(f"{tag}: ASSET_CHANGE aynı sembolde olur (old == new)")
            if ratio is not None:
                errs.append(f"{tag}: ASSET_CHANGE oranı boş olmalı (yeni varlık)")
            if t_old is None or t_new is None:
                errs.append(f"{tag}: ASSET_CHANGE için iki zaman da gerekli")
        elif typ == "MERGE_INTO_EXISTING":
            if ratio is None:
                errs.append(f"{tag}: MERGE_INTO_EXISTING oranı gerekli")
            if not new or new == old:
                errs.append(f"{tag}: MERGE_INTO_EXISTING için farklı new_symbol gerekli")
        elif typ == "DELIST":
            if new:
                errs.append(f"{tag}: DELIST'te new_symbol boş olmalı")
            if ratio is not None:
                errs.append(f"{tag}: DELIST'te oran boş olmalı")
        if t_old is not None and t_new is not None and t_old >= t_new:
            errs.append(f"{tag}: old_last_trade_utc < new_first_trade_utc olmalı")
        key = (old, new, typ, r["old_last_trade_utc"].strip())
        if key in seen:
            errs.append(f"{tag}: tekrar eden satır")
        seen.add(key)
    return errs


def _finalize_map(df: pd.DataFrame) -> pd.DataFrame:
    df = df[SYMBOL_MAP_COLUMNS].copy()
    for c in SYMBOL_MAP_COLUMNS:
        df[c] = df[c].astype("str").str.strip()
    df["ratio"] = pd.to_numeric(df["ratio"].replace("", np.nan), errors="coerce").astype("float64")
    return df


def load_symbol_map(path: Path | None = None, cfg: dict | None = None, validate: bool = True) -> pd.DataFrame:
    """symbol_map.csv → DataFrame (oran float, diğerleri str; zaman alanları ham metin)."""
    path = path or cfg_path(cfg or load_settings(), "meta") / "symbol_map.csv"
    df = _read_csv(path, SYMBOL_MAP_COLUMNS)
    if validate:
        errs = validate_symbol_map(df)
        if errs:
            raise ValueError("symbol_map doğrulanamadı:\n  " + "\n  ".join(errs))
    return _finalize_map(df)


def validate_fee_promotions(df: pd.DataFrame) -> list[str]:
    errs = _check_columns(df, FEE_COLUMNS, "fee_promotions")
    if errs:
        return errs
    for i, r in df.iterrows():
        tag = f"satır {i + 2} ({r['symbol']})"
        if not _SYMBOL_RE.match(r["symbol"].strip()):
            errs.append(f"{tag}: symbol geçersiz")
        if not r["source"].strip():
            errs.append(f"{tag}: kaynak boş")
        try:
            s, _ = parse_utc(r["start"])
            e, e_date = parse_utc(r["end"])
        except ValueError as ex:
            errs.append(f"{tag}: {ex}")
            continue
        if s is None:
            errs.append(f"{tag}: start gerekli")
        elif e is not None and (e + (pd.Timedelta(days=1) if e_date else pd.Timedelta(0))) <= s:
            errs.append(f"{tag}: end > start olmalı")
    return errs


def load_fee_promotions(path: Path | None = None, cfg: dict | None = None, validate: bool = True) -> pd.DataFrame:
    """fee_promotions.csv → DataFrame; `start_ts` (dahil) ve `end_ts` (hariç; boşsa NaT = sürüyor) eklenir.

    Varsayım: yalnız tarih olan `end` o günü kapsar (end_ts = gün + 1); saatli `end` kampanyanın bittiği andır.
    """
    path = path or cfg_path(cfg or load_settings(), "meta") / "fee_promotions.csv"
    df = _read_csv(path, FEE_COLUMNS)
    if validate:
        errs = validate_fee_promotions(df)
        if errs:
            raise ValueError("fee_promotions doğrulanamadı:\n  " + "\n  ".join(errs))
    df = df[FEE_COLUMNS].copy()
    st, en = [], []
    for s, e in zip(df["start"], df["end"]):
        ts, _ = parse_utc(s)
        te, te_date = parse_utc(e)
        st.append(ts)
        en.append(pd.NaT if te is None else te + (pd.Timedelta(days=1) if te_date else pd.Timedelta(0)))
    df["start_ts"] = pd.to_datetime(pd.Series(st, dtype="object")).astype("datetime64[ns]")
    df["end_ts"] = pd.to_datetime(pd.Series(en, dtype="object")).astype("datetime64[ns]")
    return df


def promo_mask(promos: pd.DataFrame, symbols: list[str], days: pd.DatetimeIndex) -> pd.DataFrame:
    """Gün etiketi d, [d, d+1) kampanya aralığıyla örtüşüyorsa True (gün kısmen kampanyalıysa da dışarıda tutulur)."""
    days = pd.DatetimeIndex(days)
    out = pd.DataFrame(False, index=days, columns=list(symbols))
    for r in promos.itertuples(index=False):
        if r.symbol not in out.columns:
            continue
        end = r.end_ts if pd.notna(r.end_ts) else pd.Timestamp.max
        hit = (days + pd.Timedelta(days=1) > r.start_ts) & (days < end)
        out.loc[hit, r.symbol] = True
    return out


def validate_delist_announcements(df: pd.DataFrame) -> list[str]:
    errs = _check_columns(df, DELIST_COLUMNS, "delist_announcements")
    if errs:
        return errs
    for i, r in df.iterrows():
        tag = f"satır {i + 2} ({r['symbol']})"
        if not _SYMBOL_RE.match(r["symbol"].strip()):
            errs.append(f"{tag}: symbol geçersiz")
        if r["kind"].strip() not in DELIST_KINDS:
            errs.append(f"{tag}: kind {r['kind']!r} izinli değil {DELIST_KINDS}")
        if not r["source"].strip():
            errs.append(f"{tag}: kaynak boş")
        try:
            a, _ = parse_utc(r["announced_utc"])
            d, _ = parse_utc(r["delist_utc"])
        except ValueError as ex:
            errs.append(f"{tag}: {ex}")
            continue
        if a is None:
            errs.append(f"{tag}: announced_utc gerekli")
        elif d is not None and d < a:
            errs.append(f"{tag}: delist_utc ≥ announced_utc olmalı")
    return errs


def load_delist_announcements(path: Path | None = None, cfg: dict | None = None, validate: bool = True) -> pd.DataFrame:
    path = path or cfg_path(cfg or load_settings(), "meta") / "delist_announcements.csv"
    df = _read_csv(path, DELIST_COLUMNS)
    if validate:
        errs = validate_delist_announcements(df)
        if errs:
            raise ValueError("delist_announcements doğrulanamadı:\n  " + "\n  ".join(errs))
    df = df[DELIST_COLUMNS].copy()
    df["announced_ts"] = _ts_series(df["announced_utc"])
    df["delist_ts"] = _ts_series(df["delist_utc"])
    return df


def announcements_known_at(ann: pd.DataFrame, decision_day) -> pd.DataFrame:
    """Gün etiketi D'deki kararda (D kapanışı = D+1 00:00) bilinen duyurular: announced_ts < D + 1 gün.

    SPEC: duyuru t−1 kapanışından önceyse t günü satılır → t−1 kararında bilinmesi yeterli.
    """
    D = pd.Timestamp(decision_day).normalize()
    return ann.loc[ann["announced_ts"] < D + pd.Timedelta(days=1)]


def validate_all(cfg: dict | None = None) -> dict[str, list[str]]:
    """Üç tabloyu doğrular (var olanları). Sonuç: dosya → hata listesi."""
    cfg = cfg or load_settings()
    m = cfg_path(cfg, "meta")
    out = {}
    for name, cols, fn in (("symbol_map.csv", SYMBOL_MAP_COLUMNS, validate_symbol_map),
                           ("fee_promotions.csv", FEE_COLUMNS, validate_fee_promotions),
                           ("delist_announcements.csv", DELIST_COLUMNS, validate_delist_announcements)):
        p = m / name
        out[name] = fn(_read_csv(p, cols)) if p.exists() else ["dosya yok"]
    return out


# --------------------------------------------------------------------------------------------------------------------
# Birleştirme planı
# --------------------------------------------------------------------------------------------------------------------


@dataclass
class Piece:
    """Bir çiftin zaman aralığı: open_time ∈ [lo, hi). ASSET_CHANGE eski parçasıysa `until` = son işlem günü."""

    symbol: str
    lo: pd.Timestamp | None = None
    hi: pd.Timestamp | None = None
    until: pd.Timestamp | None = None
    succ: int | None = None
    ratio_to_succ: float = 1.0
    pred: int | None = None
    old_cut: pd.Timestamp | None = None  # farklı sembollü geçişte tablo zamanı (yalnız uyarı için)
    new_cut: pd.Timestamp | None = None

    def contains(self, t: pd.Timestamp) -> bool:
        return (self.lo is None or t >= self.lo) and (self.hi is None or t < self.hi)


def _old_end_excl(v: str, step: pd.Timedelta) -> pd.Timestamp | None:
    t, date_only = parse_utc(v)
    if t is None:
        return None
    return t + pd.Timedelta(days=1) if date_only else t.floor(step) + step


def _new_start(v: str, step: pd.Timedelta) -> pd.Timestamp | None:
    t, date_only = parse_utc(v)
    if t is None:
        return None
    return t if date_only else t.floor(step)


def active_rows(symbol_map: pd.DataFrame, include_candidates: bool = False) -> pd.DataFrame:
    return symbol_map if include_candidates else symbol_map.loc[symbol_map["verified"] == "yes"]


def build_plan(symbol_map: pd.DataFrame, symbols: list[str], interval: str = "1d", include_candidates: bool = False,
               warnings: list[str] | None = None) -> list[tuple[str, list[tuple[Piece, float]]]]:
    """Varlık başına zincir: [(asset_id, [(parça, kümülatif_oran), ...])] — parçalar zaman sırasında."""
    warnings = warnings if warnings is not None else []
    step = INTERVAL_STEP[interval]
    rows = active_rows(symbol_map, include_candidates)
    avail = set(symbols)
    pieces: list[Piece] = []
    by_symbol: dict[str, list[int]] = {}

    # 1) Aynı sembolde kesimler (REDENOM aynı sembol, ASSET_CHANGE).
    same = rows.loc[(rows["old_symbol"] == rows["new_symbol"]) & rows["type"].isin(["REDENOM", "ASSET_CHANGE"])]
    cuts: dict[str, list] = {}
    for r in same.itertuples(index=False):
        e, s = _old_end_excl(r.old_last_trade_utc, step), _new_start(r.new_first_trade_utc, step)
        if e > s:
            raise ValueError(f"{r.old_symbol}: aynı sembolde eski ve yeni sınır çakışıyor ({interval})")
        t_old, _ = parse_utc(r.old_last_trade_utc)
        cuts.setdefault(r.old_symbol, []).append((e, s, r.type, r.ratio, t_old.normalize()))
    for sym in sorted(avail):
        ids = []
        lo = None
        for e, s, typ, ratio, until in sorted(cuts.get(sym, []), key=lambda x: x[0]):
            if lo is not None and e <= lo:
                raise ValueError(f"{sym}: kesimler sıralı değil")
            pieces.append(Piece(sym, lo, e, until=until if typ == "ASSET_CHANGE" else None))
            ids.append(len(pieces) - 1)
            if typ == "REDENOM":
                pieces[-1].ratio_to_succ = float(ratio)
                pieces[-1].succ = len(pieces)  # bir sonraki parça
            lo = s
        pieces.append(Piece(sym, lo, None))
        ids.append(len(pieces) - 1)
        for a, b in zip(ids[:-1], ids[1:]):
            if pieces[a].succ == b:
                pieces[b].pred = a
        by_symbol[sym] = ids
    for sym in set(cuts) - avail:
        warnings.append(f"{sym}: tabloda aynı sembol kesimi var ama temiz veri yok ({interval})")

    # 2) Farklı sembollü RENAME/REDENOM kenarları.
    diff = rows.loc[(rows["old_symbol"] != rows["new_symbol"]) & rows["type"].isin(["RENAME", "REDENOM"])]
    for r in diff.itertuples(index=False):
        if r.old_symbol not in avail or r.new_symbol not in avail:
            warnings.append(f"{r.old_symbol}→{r.new_symbol}: temiz veride eksik çift, atlandı ({interval})")
            continue
        t_old, _ = parse_utc(r.old_last_trade_utc)
        t_new, _ = parse_utc(r.new_first_trade_utc)
        src_ids, dst_ids = by_symbol[r.old_symbol], by_symbol[r.new_symbol]
        src = next((i for i in src_ids if t_old is not None and pieces[i].contains(t_old)), src_ids[-1])
        dst = next((i for i in dst_ids if t_new is not None and pieces[i].contains(t_new)), dst_ids[0])
        if pieces[src].succ is not None or pieces[dst].pred is not None:
            raise ValueError(f"{r.old_symbol}→{r.new_symbol}: parçanın birden fazla ardılı/öncülü var")
        pieces[src].succ, pieces[src].ratio_to_succ, pieces[dst].pred = dst, float(r.ratio), src
        pieces[src].old_cut = _old_end_excl(r.old_last_trade_utc, step)
        pieces[dst].new_cut = _new_start(r.new_first_trade_utc, step)

    # 3) Zincirler: her uç parçadan geriye yürü.
    chains = []
    covered = set()
    for i, p in enumerate(pieces):
        if p.succ is not None:
            continue
        chain, cum, j = [], 1.0, i
        while j is not None:
            if j in covered:
                raise ValueError(f"{pieces[j].symbol}: döngü")
            covered.add(j)
            chain.append((pieces[j], cum))
            k = pieces[j].pred
            if k is not None:
                cum *= pieces[k].ratio_to_succ
            j = k
        chain.reverse()
        aid = f"{p.symbol}_until_{p.until:%Y%m%d}" if p.until is not None else p.symbol
        chains.append((aid, chain))
    if len(covered) != len(pieces):
        raise ValueError("sembol tablosunda döngü var")
    ids = [a for a, _ in chains]
    if len(ids) != len(set(ids)):
        raise ValueError(f"tekrar eden asset_id: {sorted({a for a in ids if ids.count(a) > 1})}")
    return sorted(chains, key=lambda x: x[0])


def _adjust(df: pd.DataFrame, ratio: float, symbol: str) -> pd.DataFrame:
    out = df.copy()
    if ratio != 1.0:
        for c in PRICE_COLS:
            out[c] = out[c] / ratio
        for c in BASE_VOLUME_COLS:
            if c in out:
                out[c] = out[c] * ratio
    out["source_symbol"] = symbol
    return out


def iter_merged(symbols: list[str], loader: Callable[[str], pd.DataFrame], symbol_map: pd.DataFrame, interval: str = "1d",
                include_candidates: bool = False, warnings: list[str] | None = None) -> Iterator[tuple[str, pd.DataFrame, list[dict]]]:
    """Her varlık için (asset_id, birleşik seri, segment satırları) üretir. `loader(symbol)` temiz seriyi verir."""
    warnings = warnings if warnings is not None else []
    for aid, chain in build_plan(symbol_map, symbols, interval, include_candidates, warnings):
        frames = []
        for piece, cum in chain:
            df = loader(piece.symbol)
            ot = pd.to_datetime(df["open_time"]).astype("datetime64[ns]")
            sel = np.ones(len(df), dtype=bool)
            if piece.lo is not None:
                sel &= (ot >= piece.lo).to_numpy()
            if piece.hi is not None:
                sel &= (ot < piece.hi).to_numpy()
            part = df.loc[sel].assign(open_time=ot[sel]).sort_values("open_time", kind="mergesort")
            if piece.old_cut is not None and len(part) and part["open_time"].max() >= piece.old_cut:
                # Varsayım: tablodaki son işlemden sonra hacmi sıfır olan mumlar işlem görmemiş bayat kayıtlardır
                # (ör. KLAYUSDT 1d 2024-10-29/30) ve atılır; hacmi olan mumlar kalır (sınırı veri belirler).
                stale = (part["open_time"] >= piece.old_cut) & (part["volume"] <= 0)
                if stale.any():
                    warnings.append(f"{piece.symbol}: old_last_trade sonrasındaki {int(stale.sum())} sıfır hacimli mum atıldı ({interval})")
                    part = part.loc[~stale]
            if piece.old_cut is not None and len(part) and part["open_time"].max() >= piece.old_cut:
                warnings.append(f"{piece.symbol}: tablodaki old_last_trade sonrasında {int((part['open_time'] >= piece.old_cut).sum())} mum var ({interval})")
            if piece.new_cut is not None and len(part) and part["open_time"].min() < piece.new_cut:
                warnings.append(f"{piece.symbol}: tablodaki new_first_trade öncesinde {int((part['open_time'] < piece.new_cut).sum())} mum var ({interval})")
            frames.append((piece, cum, part))
        out, segs = [], []
        for k, (piece, cum, part) in enumerate(frames):
            nxt = next((p for _, _, p in frames[k + 1:] if len(p)), None)
            if nxt is not None and len(part):
                over = part["open_time"] >= nxt["open_time"].iloc[0]
                if over.any():
                    warnings.append(f"{aid}: {piece.symbol} ile ardılı çakışıyor, {int(over.sum())} eski mum düşürüldü ({interval})")
                    part = part.loc[~over]
            if len(part) == 0:
                continue
            out.append(_adjust(part, cum, piece.symbol))
            segs.append({"asset_id": aid, "source_symbol": piece.symbol, "start": part["open_time"].iloc[0],
                         "end": part["open_time"].iloc[-1], "ratio": cum})
        if not out:
            continue
        merged = pd.concat(out, ignore_index=True)
        merged["open_time"] = merged["open_time"].astype("datetime64[ns]")
        if "close_time" in merged:
            merged["close_time"] = pd.to_datetime(merged["close_time"]).astype("datetime64[ns]")
        if merged["open_time"].duplicated().any():
            raise ValueError(f"{aid}: birleşik seride tekrar eden open_time")
        yield aid, merged.reset_index(drop=True), segs


def dropped_between_cuts(symbol_map: pd.DataFrame, frames_or_loader, symbols: list[str], interval: str = "1d",
                         include_candidates: bool = False) -> dict[str, int]:
    """Aynı sembolde eski/yeni sınırları arasında kalıp hiçbir parçaya atanmayan mum sayısı (uyarı için)."""
    step = INTERVAL_STEP[interval]
    rows = active_rows(symbol_map, include_candidates)
    same = rows.loc[(rows["old_symbol"] == rows["new_symbol"]) & rows["type"].isin(["REDENOM", "ASSET_CHANGE"])]
    out = {}
    get = frames_or_loader if callable(frames_or_loader) else frames_or_loader.__getitem__
    for r in same.itertuples(index=False):
        if r.old_symbol not in symbols:
            continue
        e, s = _old_end_excl(r.old_last_trade_utc, step), _new_start(r.new_first_trade_utc, step)
        ot = pd.to_datetime(get(r.old_symbol)["open_time"])
        n = int(((ot >= e) & (ot < s)).sum())
        if n:
            out[f"{r.old_symbol}@{r.old_last_trade_utc}"] = n
    return out


def merge_frames(frames: dict[str, pd.DataFrame], symbol_map: pd.DataFrame, interval: str = "1d",
                 include_candidates: bool = False) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, list[str]]:
    """Bellek içi birleştirme (testler ve küçük kullanım): (asset_id → seri, segmentler, uyarılar)."""
    warnings: list[str] = []
    out, segs = {}, []
    for aid, df, s in iter_merged(sorted(frames), frames.__getitem__, symbol_map, interval, include_candidates, warnings):
        out[aid] = df
        segs += s
    for k, n in dropped_between_cuts(symbol_map, frames, list(frames), interval, include_candidates).items():
        warnings.append(f"{k}: sınırlar arasında {n} mum atanamadı ve düşürüldü ({interval})")
    return out, _segments_frame(segs), warnings


def _segments_frame(segs: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(segs, columns=SEGMENT_COLUMNS)
    if len(df):
        df["start"] = pd.to_datetime(df["start"]).astype("datetime64[ns]")
        df["end"] = pd.to_datetime(df["end"]).astype("datetime64[ns]")
        df = df.sort_values(["asset_id", "start"], kind="mergesort").reset_index(drop=True)
    return df


def merged_dir(interval: str, cfg: dict | None = None) -> Path:
    """data/merged/{interval} (`paths.merged`)."""
    p = Path((cfg or load_settings())["paths"].get("merged", MERGED_DIR))
    return (p if p.is_absolute() else ROOT / p) / interval


def segments_path(cfg: dict, interval: str) -> Path:
    name = "asset_segments.csv" if interval == "1d" else f"asset_segments_{interval}.csv"
    return cfg_path(cfg, "meta") / name


def build_merged(interval: str = "1d", cfg: dict | None = None, include_candidates: bool = False,
                 symbols: list[str] | None = None) -> pd.DataFrame:
    """Temiz USDT serilerine sembol tablosunu uygular → data/merged/{interval}/{ASSET_ID}.parquet + segment tablosu.

    Önceki çalıştırmadan kalan ve artık üretilmeyen birleşik dosyalar silinir (yalnızca bu fonksiyonun çıktıları).
    """
    cfg = cfg or load_settings()
    smap = load_symbol_map(cfg=cfg)
    cdir = cfg_path(cfg, "clean") / interval
    if symbols is None:
        symbols = sorted(p.stem for p in cdir.glob("*.parquet") if quote_of(p.stem) == "USDT")
    if not symbols:
        raise FileNotFoundError(f"temiz USDT verisi yok: {cdir}")
    out_dir = merged_dir(interval, cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache: dict[str, pd.DataFrame] = {}

    def loader(sym: str) -> pd.DataFrame:
        if sym not in cache:
            if len(cache) > 8:
                cache.clear()
            cache[sym] = pd.read_parquet(cdir / f"{sym}.parquet")
        return cache[sym]

    warnings: list[str] = []
    segs, written = [], set()
    for aid, df, s in iter_merged(symbols, loader, smap, interval, include_candidates, warnings):
        df.to_parquet(out_dir / f"{aid}.parquet", index=False)
        written.add(aid)
        segs += s
    for k, n in dropped_between_cuts(smap, loader, symbols, interval, include_candidates).items():
        warnings.append(f"{k}: sınırlar arasında {n} mum atanamadı ve düşürüldü ({interval})")
    for p in out_dir.glob("*.parquet"):
        if p.stem not in written:
            p.unlink()
    seg = _segments_frame(segs)
    sp = segments_path(cfg, interval)
    seg.to_csv(sp, index=False, date_format="%Y-%m-%d %H:%M:%S")
    skipped = smap.loc[smap["verified"] != "yes"] if not include_candidates else smap.iloc[0:0]
    log = cfg_path(cfg, "meta") / f"merge_log_{interval}.txt"
    lines = [f"interval={interval} assets={len(written)} include_candidates={include_candidates}"]
    lines += [f"UYARI {w}" for w in warnings]
    lines += [f"ATLANDI (candidate) {r.old_symbol}->{r.new_symbol} {r.type}" for r in skipped.itertuples(index=False)]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    multi = seg.groupby("asset_id").size()
    print(f"{len(written)} varlık yazıldı → {out_dir}; çok parçalı: {int((multi > 1).sum())}; segmentler → {sp}")
    for w in warnings:
        print("UYARI", w, file=sys.stderr)
    return seg


# --------------------------------------------------------------------------------------------------------------------
# Aday üretimi
# --------------------------------------------------------------------------------------------------------------------


def _pair_summary(symbols: list[str], loader: Callable[[str], pd.DataFrame]) -> pd.DataFrame:
    recs = []
    for s in symbols:
        df = loader(s)
        if len(df) == 0:
            continue
        df = df.sort_values("open_time")
        ot = pd.to_datetime(df["open_time"])
        recs.append({"symbol": s, "first": ot.iloc[0].normalize(), "last": ot.iloc[-1].normalize(),
                     "first_open": float(df["open"].iloc[0]), "last_close": float(df["close"].iloc[-1])})
    return pd.DataFrame(recs, columns=["symbol", "first", "last", "first_open", "last_close"])


def find_candidates_from(summary: pd.DataFrame, flags: pd.DataFrame | None, symbol_map: pd.DataFrame | None,
                         data_end: pd.Timestamp, cfg: dict | None = None) -> pd.DataFrame:
    """Saf aday üretimi: (1) kalite `split_candidate` işaretleri ve boşluklu `extreme_return` ≈ 10^k (gevşek tolerans),
    (2) USDT çifti biterken ~10 gün içinde başlayan başka bir çift ve fiyat oranı ≈ 10^k veya isim benzerliği
    (biri diğerinin öneki). Tabloda zaten açıklanan çiftler/tarihler atlanır."""
    cfg = cfg or load_settings()
    tol_split = float(cfg["quality"]["split_log10_tolerance"])
    stale = pd.Timedelta(days=int(cfg["backtest"]["delist_stale_days"]))
    stables = {s.upper() for s in cfg["universe"]["exclude"]["stable_fiat"]}
    smap = symbol_map if symbol_map is not None else pd.DataFrame(columns=SYMBOL_MAP_COLUMNS)
    explained_old = set(smap["old_symbol"])
    known_pairs = set(zip(smap["old_symbol"], smap["new_symbol"]))
    recs = []

    def near_known_same(symbol: str, day) -> bool:
        """Tabloda bu sembol için ±PAIR_MATCH_MAX_GAP_DAYS içinde aynı sembollü satır (REDENOM/ASSET_CHANGE) var mı?"""
        same_rows = smap.loc[(smap["old_symbol"] == symbol) & (smap["new_symbol"] == symbol)]
        for t in same_rows["old_last_trade_utc"]:
            tt, _ = parse_utc(t)
            if tt is not None and abs((tt.normalize() - pd.Timestamp(day)).days) <= PAIR_MATCH_MAX_GAP_DAYS:
                return True
        return False

    # (1) Bölünme kontrolü.
    if flags is not None and len(flags):
        sp = flags.loc[flags["check"] == "split_candidate"]
        for r in sp.itertuples(index=False):
            if near_known_same(r.symbol, r.period_start):
                continue
            m = re.search(r"suggested_ratio=([0-9.eE+-]+)", r.detail)
            ratio = float(m.group(1)) if m else np.nan
            recs.append({"old_symbol": r.symbol, "new_symbol": r.symbol, "type": "REDENOM", "ratio": ratio,
                         "old_last_trade_utc": f"{pd.Timestamp(r.period_start):%Y-%m-%d}",
                         "new_first_trade_utc": f"{pd.Timestamp(r.period_end):%Y-%m-%d}",
                         "source": "find_candidates: quality split_candidate (duyuru ile doğrulanmalı)", "verified": "candidate",
                         "method": "split_check", "detail": r.detail})
        # Boşlukta fiyat %4,7'den fazla oynadıysa bölünme kontrolü kaçırır; boşluklu aşırı kapanış sıçramasını
        # (C_{t-1}/C_t ≈ 10^k, k ≠ 0) gevşek toleransla aday say (aynı gün bölünme adayı yoksa).
        split_keys = {(x["old_symbol"], x["new_first_trade_utc"]) for x in recs}
        er = flags.loc[flags["check"] == "extreme_return"]
        for r in er.itertuples(index=False):
            m = re.search(r"log_return=([0-9.eE+-]+)", r.detail)
            g = re.search(r"gap_days=(\d+)", r.detail)
            if not m or not g or int(g.group(1)) == 0:
                continue
            lr10 = -float(m.group(1)) / math.log(10.0)
            k = round(lr10)
            day = f"{pd.Timestamp(r.period_start):%Y-%m-%d}"
            if k == 0 or abs(lr10 - k) >= PAIR_MATCH_LOG10_TOL or (r.symbol, day) in split_keys:
                continue
            if near_known_same(r.symbol, r.period_start):
                continue
            recs.append({"old_symbol": r.symbol, "new_symbol": r.symbol, "type": "REDENOM", "ratio": float(10.0**k),
                         "old_last_trade_utc": f"{pd.Timestamp(r.period_start) - pd.Timedelta(days=int(g.group(1)) + 1):%Y-%m-%d}",
                         "new_first_trade_utc": day,
                         "source": "find_candidates: gap + extreme_return ≈ 10^k (duyuru ile doğrulanmalı)", "verified": "candidate",
                         "method": "return_check", "detail": r.detail})

    # (2) Biten/başlayan çift eşleştirme.
    if len(summary):
        s = summary.copy()
        s["base"] = [x[: -len(quote_of(x))] if quote_of(x) else x for x in s["symbol"]]
        ended = s.loc[s["last"] < data_end - stale]
        for a in ended.itertuples(index=False):
            if a.symbol in explained_old:
                continue
            gap = (s["first"] - a.last).dt.days
            cands = s.loc[(gap >= PAIR_MATCH_MIN_GAP_DAYS) & (gap <= PAIR_MATCH_MAX_GAP_DAYS) & (s["symbol"] != a.symbol)]
            for b in cands.itertuples(index=False):
                if (a.symbol, b.symbol) in known_pairs or (a.base in stables and b.base in stables):
                    continue
                if not (a.last_close > 0 and b.first_open > 0):
                    continue
                r = math.log10(a.last_close / b.first_open)
                k = round(r)
                round_match = abs(r - k) < PAIR_MATCH_LOG10_TOL
                name_hint = a.base.startswith(b.base) or b.base.startswith(a.base)
                if not (round_match or name_hint):
                    continue
                if round_match:
                    typ, ratio = ("RENAME", 1.0) if k == 0 else ("REDENOM", float(10.0**k))
                else:
                    typ, ratio = "REDENOM", float(f"{a.last_close / b.first_open:.6g}")
                method = "+".join(m for m, ok in (("pair_round_ratio", round_match), ("pair_name_hint", name_hint)) if ok)
                recs.append({"old_symbol": a.symbol, "new_symbol": b.symbol, "type": typ, "ratio": ratio,
                             "old_last_trade_utc": f"{a.last:%Y-%m-%d}", "new_first_trade_utc": f"{b.first:%Y-%m-%d}",
                             "source": f"find_candidates: {method} (duyuru ile doğrulanmalı)", "verified": "candidate",
                             "method": method,
                             "detail": f"gap_days={int((b.first - a.last).days)};price_old={a.last_close:.10g};"
                                       f"price_new={b.first_open:.10g};log10_ratio={r:.4f};within_split_tol={abs(r - k) < tol_split}"})
    df = pd.DataFrame(recs, columns=CANDIDATE_COLUMNS)
    return df.sort_values(["method", "old_symbol", "new_symbol"], kind="mergesort").reset_index(drop=True)


def find_candidates(cfg: dict | None = None, interval: str = "1d", out: Path | None = None, append: bool = False) -> pd.DataFrame:
    """Gerçek veriden adaylar → meta/symbol_map_candidates.csv (kullanıcı incelemesi). `append=True` ise tabloda
    olmayanlar symbol_map.csv'ye `verified=candidate` olarak eklenir (build_merged bunları varsayılan olarak uygulamaz)."""
    cfg = cfg or load_settings()
    cdir = cfg_path(cfg, "clean") / interval
    symbols = sorted(p.stem for p in cdir.glob("*.parquet") if quote_of(p.stem) == "USDT")
    summ = _pair_summary(symbols, lambda s: pd.read_parquet(cdir / f"{s}.parquet", columns=["open_time", "open", "close"]))
    data_end = summ["last"].max()
    fp = cfg_path(cfg, "quality_flags")
    flags = pd.read_parquet(fp) if fp.exists() else None
    smap = load_symbol_map(cfg=cfg)
    cand = find_candidates_from(summ, flags, smap, data_end, cfg)
    out = out or cfg_path(cfg, "meta") / "symbol_map_candidates.csv"
    cand.to_csv(out, index=False)
    print(f"{len(cand)} aday → {out}" + ("" if flags is not None else " (quality_flags yok: bölünme adayları atlandı)"))
    if append and len(cand):
        raw = _read_csv(cfg_path(cfg, "meta") / "symbol_map.csv", SYMBOL_MAP_COLUMNS)
        have = set(zip(raw["old_symbol"], raw["new_symbol"], raw["type"]))
        add = cand.loc[[(o, n, t) not in have for o, n, t in zip(cand["old_symbol"], cand["new_symbol"], cand["type"])], SYMBOL_MAP_COLUMNS]
        add = add.assign(ratio=[("" if pd.isna(x) else f"{x:.10g}") for x in add["ratio"]])
        pd.concat([raw, add.astype(str)], ignore_index=True).to_csv(cfg_path(cfg, "meta") / "symbol_map.csv", index=False)
        print(f"{len(add)} aday symbol_map.csv'ye eklendi (verified=candidate)")
    return cand


# --------------------------------------------------------------------------------------------------------------------
# G5 raporu (otomatik bölüm)
# --------------------------------------------------------------------------------------------------------------------

AUTO_BEGIN = "<!-- AUTO:BEGIN (python -m trend.meta report ile yeniden üretilir) -->"
AUTO_END = "<!-- AUTO:END -->"


def _md(df: pd.DataFrame) -> str:
    if df is None or len(df) == 0:
        return "_(yok)_\n"
    d = df.astype(str)
    lines = ["| " + " | ".join(d.columns) + " |", "| " + " | ".join("---" for _ in d.columns) + " |"]
    lines += ["| " + " | ".join(v.replace("|", "\\|") for v in row) + " |" for row in d.itertuples(index=False)]
    return "\n".join(lines) + "\n"


SYMBOL_MAP_APPROVED_ROWS = 43


def render_auto_section(cfg: dict | None = None) -> str:
    cfg = cfg or load_settings()
    m = cfg_path(cfg, "meta")
    L = [AUTO_BEGIN, ""]
    val = validate_all(cfg)
    L.append("### Doğrulama\n")
    for k, v in val.items():
        L.append(f"- `meta/{k}`: " + ("geçerli" if not v else "**HATA** — " + "; ".join(v)))
    L.append("")
    sm = _read_csv(m / "symbol_map.csv", SYMBOL_MAP_COLUMNS) if (m / "symbol_map.csv").exists() else None
    if sm is not None:
        t = sm.copy()
        t.insert(0, "#", range(1, len(t) + 1))
        # Kullanıcı 43 satırı 2026-11-03'te onayladı (PREREGISTRATION.md); sonraki satırlar yeniden onay bekler
        t["onay"] = ["Onaylandı 2026-11-03" if i < SYMBOL_MAP_APPROVED_ROWS else "Onay bekliyor" for i in range(len(t))]
        L.append(f"### symbol_map.csv ({len(t)} satır; yes: {int((t['verified'] == 'yes').sum())}, "
                 f"candidate: {int((t['verified'] == 'candidate').sum())})\n")
        L.append(_md(t))
    for name, cols in (("fee_promotions.csv", FEE_COLUMNS), ("delist_announcements.csv", DELIST_COLUMNS)):
        p = m / name
        if p.exists():
            t = _read_csv(p, cols)
            L.append(f"### {name} ({len(t)} satır)\n")
            L.append(_md(t))
    cp = m / "symbol_map_candidates.csv"
    L.append("### Veriden bulunan adaylar (`meta/symbol_map_candidates.csv`)\n")
    if cp.exists():
        c = pd.read_csv(cp, dtype=str, keep_default_na=False)
        L.append(f"{len(c)} aday (yöntem: " + ", ".join(f"{k} {v}" for k, v in c["method"].value_counts().items()) + ").\n")
        L.append(_md(c[["old_symbol", "new_symbol", "type", "ratio", "old_last_trade_utc", "new_first_trade_utc", "method", "detail"]]))
    else:
        L.append("_Henüz üretilmedi (veri gerekli): `python -m uv run python -m trend.meta candidates`._\n")
    sp = segments_path(cfg, "1d")
    L.append("### Birleştirilmiş varlıklar (`meta/asset_segments.csv`)\n")
    if sp.exists():
        seg = pd.read_csv(sp)
        multi = seg.groupby("asset_id").filter(lambda g: len(g) > 1)
        L.append(f"{seg['asset_id'].nunique()} varlık; birden fazla parçalı: {multi['asset_id'].nunique()}.\n")
        L.append(_md(multi))
    else:
        L.append("_Henüz üretilmedi (veri gerekli): `python -m uv run python -m trend.meta merged --interval 1d`._\n")
    L.append(AUTO_END)
    return "\n".join(L)


def write_g5_report(cfg: dict | None = None, path: Path | None = None) -> Path:
    """reports/G5_meta.md içindeki AUTO bölümünü yeniler (elle yazılmış araştırma notları korunur)."""
    cfg = cfg or load_settings()
    path = path or cfg_path(cfg, "reports") / "G5_meta.md"
    auto = render_auto_section(cfg)
    if path.exists():
        txt = path.read_text(encoding="utf-8")
        if AUTO_BEGIN in txt and AUTO_END in txt:
            pre, rest = txt.split(AUTO_BEGIN, 1)
            post = rest.split(AUTO_END, 1)[1]
            txt = pre + auto + post
        else:
            txt = txt.rstrip() + "\n\n" + auto + "\n"
    else:
        txt = "# G5 — Meta tablolar\n\n" + auto + "\n"
    path.write_text(txt, encoding="utf-8")
    print(f"rapor → {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows konsolunda Türkçe karakterler hata vermesin
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="python -m trend.meta", description="G5 meta tablolar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="meta/*.csv doğrula")
    mg = sub.add_parser("merged", help="data/merged/{interval}/ + meta/asset_segments.csv")
    mg.add_argument("--interval", default="1d", choices=sorted(INTERVAL_FREQ))
    mg.add_argument("--include-candidates", action="store_true")
    cd = sub.add_parser("candidates", help="meta/symbol_map_candidates.csv")
    cd.add_argument("--append", action="store_true", help="adayları symbol_map.csv'ye candidate olarak ekle")
    sub.add_parser("report", help="reports/G5_meta.md AUTO bölümü")
    a = ap.parse_args(argv)
    if a.cmd == "validate":
        res = validate_all()
        for k, v in res.items():
            print(f"{k}: " + ("geçerli" if not v else "\n  " + "\n  ".join(v)))
        return 0 if all(not v for v in res.values()) else 1
    if a.cmd == "merged":
        build_merged(a.interval, include_candidates=a.include_candidates)
    elif a.cmd == "candidates":
        find_candidates(append=a.append)
    elif a.cmd == "report":
        write_g5_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
