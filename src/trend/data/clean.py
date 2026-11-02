"""G3 — temizleme: ham zip'ler → `data/clean/{interval}/{SYMBOL}.parquet` (CONTRACTS §3).

- Zaman damgası: değer > `data.timestamp_us_threshold` (1e14) ise mikrosaniyedir, 1000'e (tam sayı) bölünür
  (arşiv 2025-01-01'den itibaren µs). Kural satır bazında uygulanır; sonuç tz-naive UTC `datetime64[ns]`.
- Başlık satırı: ilk karakter rakam değilse ilk satır başlık sayılır ve atlanır.
- Kaynak önceliği: bir ay için aylık dosya varsa o ayın günlük dosyaları kullanılmaz (aylık dosya yayımlanınca
  daha önce inmiş günlük dosyalar diskte kalır).
- Tekrarlanan open_time: öncelik sırasıyla ilk satır tutulur (aylık > günlük, sonra dosya adı). Birebir aynı
  satırlar `exact`, değerleri farklı olanlar `conflict` olarak `{clean}/{interval}/_duplicates.csv`'ye yazılır
  (kalite modülü G4 raporlar).
- half_day (CONTRACTS §3, SPEC "Yarım gün": "çiftin ilk ve son mumu"). Varsayım — kural her işlem dilimi için
  uygulanır (aynı sembolün delist/askı sonrası yeniden açılması, ör. LUNAUSDT 2022-05-13 → 2022-05-31,
  FTTUSDT 2022-11-15 → 2023-09-22):
  1. çiftin ilk mumu;
  2. kesik mum: close_time + 1 ms < open_time + aralık (arşivde delist/askı mumunun close_time'ı kesilir,
     ör. MATICUSDT 2024-09-10 02:59:59.999, eski LUNA 2022-05-13 00:39:59.999);
  3. kesik mumdan sonra boşlukla gelen ilk mum (yeniden açılış);
  4. son mum, yalnız çift sona ermişse: son mumun kapanışı aynı aralıktaki tüm defterin kapsadığı en son andan
     (global son) önceyse. Böylece hâlâ işlem gören çiftin en yeni (tam) mumu yarım gün sayılmaz.
- Belirlenimcilik: içerik hash'i `pandas.util.hash_pandas_object` üzerinden (dosya baytı değil);
  `_manifest.json` her sembolün hash'ini ve imzasını tutar. İmza = defterdeki ok dosyaların (yol, sha256)
  listesi + global sona ulaşıp ulaşmadığı. İmza değişmeyen semboller yeniden kurulmaz (artımlı).

CLI: `python -m uv run python -m trend.data.clean [--symbols BTCUSDT] [--intervals 1d,1h] [--force] [--workers 8]`
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from trend.config import load_settings, path
from trend.data import _http
from trend.data.download import now_utc, read_ledger

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
              "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"]
FLOAT_COLS = ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_base", "taker_buy_quote"]
CLEAN_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
              "number_of_trades", "taker_buy_base", "taker_buy_quote", "half_day"]
CLEAN_DTYPES = {"open_time": "datetime64[ns]", "close_time": "datetime64[ns]", "number_of_trades": "int64",
                "half_day": "bool", **{c: "float64" for c in FLOAT_COLS}}
DUP_COLS = ["symbol", "interval", "open_time", "kind", "n", "sources"]
MANIFEST = "_manifest.json"
DUPLICATES = "_duplicates.csv"
_READ_DTYPES = {"open_time": "int64", "close_time": "int64", "number_of_trades": "int64",
                **{c: "float64" for c in FLOAT_COLS}}


# ------------------------------------------------------------------------------------------ zaman damgası
def ts_to_datetime(values, threshold: int) -> np.ndarray:
    """ms/µs tam sayı zaman damgası → tz-naive UTC datetime64[ns]. Değer > threshold ise µs (÷1000, tabana yuvarla)."""
    v = np.asarray(values, dtype="int64")
    ms = np.where(v > threshold, v // 1000, v)
    return ms.astype("datetime64[ms]").astype("datetime64[ns]")


def normalize(raw: pd.DataFrame, threshold: int) -> pd.DataFrame:
    """Ham 11/12 kolonlu kline tablosu (sayısal) → temiz şema (half_day=False). REST istemcisi de bunu kullanır."""
    out = pd.DataFrame({
        "open_time": ts_to_datetime(raw["open_time"], threshold),
        **{c: raw[c].astype("float64").to_numpy() for c in ["open", "high", "low", "close", "volume"]},
        "close_time": ts_to_datetime(raw["close_time"], threshold),
        **{c: raw[c].astype("float64").to_numpy() for c in ["quote_volume"]},
        "number_of_trades": raw["number_of_trades"].astype("int64").to_numpy(),
        **{c: raw[c].astype("float64").to_numpy() for c in ["taker_buy_base", "taker_buy_quote"]},
        "half_day": np.zeros(len(raw), dtype=bool),
    })
    return out[CLEAN_COLS]


# ---------------------------------------------------------------------------------------------- okuma
def read_kline_csv(data: bytes) -> pd.DataFrame:
    """Arşiv CSV baytları → ham sayısal tablo (ignore kolonu atılır). Başlık satırı varsa atlanır."""
    data = data.removeprefix(b"\xef\xbb\xbf")
    if not data.strip():
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in _READ_DTYPES.items()})[KLINE_COLS[:11]]
    header = not data[:1].isdigit()
    return pd.read_csv(io.BytesIO(data), header=None, names=KLINE_COLS, usecols=range(11),
                       skiprows=1 if header else 0, dtype=_READ_DTYPES)


def read_zip(p: Path) -> pd.DataFrame:
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"{p}: zip içinde tek CSV beklenirdi, bulunan {z.namelist()}")
        return read_kline_csv(z.read(names[0]))


def content_hash(df: pd.DataFrame) -> str:
    """Satır sırası dahil içerik hash'i (dosya baytlarından bağımsız; yeniden kurulumda aynı olmalı)."""
    h = pd.util.hash_pandas_object(df, index=False).to_numpy()
    cols = ",".join(f"{c}:{t}" for c, t in df.dtypes.astype(str).items())
    return hashlib.sha256(cols.encode() + h.tobytes()).hexdigest()


# ------------------------------------------------------------------------------------------ dosya seçimi
def parse_rel(rel: str) -> dict:
    """`{monthly|daily}/klines/SYM/INT/SYM-INT-YYYY-MM[-DD].zip` → alanlar ve dönemin [başlangıç, bitiş) aralığı."""
    kind, _, sym, iv, fn = rel.split("/")
    parts = fn.removesuffix(".zip").split("-")
    if kind == "monthly":
        period = "-".join(parts[-2:])
        start = pd.Timestamp(period + "-01")
        end = start + pd.offsets.MonthBegin(1)
    else:
        period = "-".join(parts[-3:])
        start = pd.Timestamp(period)
        end = start + pd.Timedelta(days=1)
    return {"rel_path": rel, "kind": kind, "symbol": sym, "interval": iv, "period": period, "month": period[:7],
            "start": start, "end": end}


def ledger_files(cfg: dict) -> pd.DataFrame:
    """Defterdeki ok dosyalar, ayrıştırılmış alanlarla."""
    led = read_ledger(path(cfg, "ledger"))
    led = led[led["status"] == "ok"]
    if led.empty:
        return pd.DataFrame(columns=["rel_path", "kind", "symbol", "interval", "period", "month", "start", "end",
                                     "sha256_actual"])
    meta = pd.DataFrame([parse_rel(r) for r in led["rel_path"]])
    return meta.assign(sha256_actual=led["sha256_actual"].to_numpy())


def select_files(files: pd.DataFrame) -> pd.DataFrame:
    """Aylık dosyası olan ayların günlük dosyalarını atar; öncelik sırasına dizer (aylık önce, sonra yol)."""
    months = set(files.loc[files["kind"] == "monthly", "month"])
    keep = (files["kind"] == "monthly") | ~files["month"].isin(months)
    out = files[keep].copy()
    out["rank"] = (out["kind"] != "monthly").astype(int)
    return out.sort_values(["rank", "rel_path"], ignore_index=True)


def signature(files: pd.DataFrame, global_end: pd.Timestamp) -> str:
    reaches = bool(len(files)) and files["end"].max() >= global_end
    txt = "\n".join(f"{r}:{h}" for r, h in sorted(zip(files["rel_path"], files["sha256_actual"])))
    return hashlib.sha256(f"{txt}\nreaches_end={reaches}".encode()).hexdigest()


# ---------------------------------------------------------------------------------------------- kurulum
def interval_td(interval: str) -> pd.Timedelta:
    """'1h' → 1 saat, '1d' → 1 gün (Binance aralık yazımı)."""
    units = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
    return pd.Timedelta(**{units[interval[-1]]: int(interval[:-1])})


def half_day_flags(open_time: pd.Series, close_time: pd.Series, step: pd.Timedelta,
                   global_end: pd.Timestamp) -> np.ndarray:
    """Yarım gün işareti (kurallar modül belgesinde). Girdi open_time'a göre sıralı ve benzersiz olmalı."""
    ot = open_time.to_numpy()
    ct = close_time.to_numpy()
    n = len(ot)
    one_ms = np.timedelta64(1, "ms")
    trunc = ct + one_ms < ot + step.to_timedelta64()
    hd = trunc.copy()
    if n > 1:
        gap = ot[1:] > ot[:-1] + step.to_timedelta64()
        hd[1:] |= trunc[:-1] & gap
    if n:
        hd[0] = True
        if ct[-1] + one_ms < global_end.to_datetime64():
            hd[-1] = True
    return hd


def build_frame(files: pd.DataFrame, raw_dir: Path, threshold: int, global_end: pd.Timestamp,
                symbol: str = "", interval: str = "") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Seçilmiş dosyalardan temiz tablo + tekrar kaydı üretir (diske yazmaz)."""
    sel = select_files(files)
    parts = []
    for i, rel in enumerate(sel["rel_path"]):
        raw = read_zip(raw_dir / rel)
        df = normalize(raw, threshold)
        df["_ord"] = i
        df["_row"] = np.arange(len(df))
        parts.append(df)
    if not parts:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in CLEAN_DTYPES.items()})[CLEAN_COLS], \
            pd.DataFrame(columns=DUP_COLS)
    df = pd.concat(parts, ignore_index=True)
    df = df.sort_values(["open_time", "_ord", "_row"], kind="mergesort", ignore_index=True)

    dup_rows = []
    dmask = df["open_time"].duplicated(keep=False)
    if dmask.any():
        data_cols = [c for c in CLEAN_COLS if c != "half_day"]
        for t, g in df[dmask].groupby("open_time", sort=True):
            exact = len(g[data_cols].drop_duplicates()) == 1
            srcs = ";".join(sel["rel_path"].iloc[o].rsplit("/", 1)[-1] for o in g["_ord"])
            dup_rows.append({"symbol": symbol, "interval": interval, "open_time": t,
                             "kind": "exact" if exact else "conflict", "n": len(g), "sources": srcs})
        df = df[~df["open_time"].duplicated(keep="first")]
    df = df[CLEAN_COLS].reset_index(drop=True)
    if df.empty:
        return df.astype(CLEAN_DTYPES), pd.DataFrame(dup_rows, columns=DUP_COLS)

    df["half_day"] = half_day_flags(df["open_time"], df["close_time"], interval_td(interval), global_end)
    df = df.astype(CLEAN_DTYPES)
    return df, pd.DataFrame(dup_rows, columns=DUP_COLS)


def _build_one(symbol: str, interval: str, files: pd.DataFrame, raw_dir: str, out_dir: str, threshold: int,
               global_end: pd.Timestamp, sig: str) -> tuple[str, dict, pd.DataFrame]:
    """İşçi süreç: bir sembolü kurar, parquet'i atomik yazar, manifest girdisini döndürür."""
    df, dups = build_frame(files, Path(raw_dir), threshold, global_end, symbol, interval)
    out = Path(out_dir) / f"{symbol}.parquet"
    tmp = out.with_name(out.name + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, out)
    entry = {"sig": sig, "content_hash": content_hash(df), "rows": len(df),
             "first": str(df["open_time"].iloc[0]) if len(df) else "",
             "last": str(df["open_time"].iloc[-1]) if len(df) else "",
             "n_files": int(len(files)), "dup_exact": int((dups["kind"] == "exact").sum()),
             "dup_conflict": int((dups["kind"] == "conflict").sum()), "built_at_utc": now_utc()}
    return symbol, entry, dups


def _load_manifest(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save_manifest(p: Path, m: dict) -> None:
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(dict(sorted(m.items())), indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def build(cfg: dict | None = None, intervals: list[str] | None = None, symbols: list[str] | None = None,
          force: bool = False, workers: int | None = None, progress: bool = True) -> dict[str, dict]:
    """Temiz parquet'leri (yeniden) kurar. Dönüş: aralık → {kurulan, atlanan, hatalı} özet."""
    cfg = cfg or load_settings()
    thr = int(cfg["data"]["timestamp_us_threshold"])
    raw_dir = path(cfg, "raw")
    files = ledger_files(cfg)
    intervals = intervals or sorted(files["interval"].unique())
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    summary = {}
    for iv in intervals:
        fiv = files[files["interval"] == iv]
        if fiv.empty:
            continue
        global_end = fiv["end"].max()
        out_dir = path(cfg, "clean") / iv
        out_dir.mkdir(parents=True, exist_ok=True)
        man_p, dup_p = out_dir / MANIFEST, out_dir / DUPLICATES
        manifest = _load_manifest(man_p)
        groups = {s: g for s, g in fiv.groupby("symbol", sort=True) if symbols is None or s in symbols}
        todo = []
        for s, g in groups.items():
            sig = signature(g, global_end)
            if not force and manifest.get(s, {}).get("sig") == sig and (out_dir / f"{s}.parquet").exists():
                continue
            todo.append((s, g, sig))
        t0 = time.time()
        if progress:
            print(f"[clean] {iv}: {len(groups)} sembol, kurulacak {len(todo)}, global son {global_end}", flush=True)
        new_dups, failed = [], {}
        if todo:
            with ProcessPoolExecutor(max_workers=min(workers, len(todo))) as ex:
                futs = {ex.submit(_build_one, s, iv, g, str(raw_dir), str(out_dir), thr, global_end, sig): s
                        for s, g, sig in todo}
                for i, f in enumerate(as_completed(futs), 1):
                    s = futs[f]
                    try:
                        _, entry, dups = f.result()
                    except Exception as e:  # noqa: BLE001 — sembol bazında hata raporlanır, diğerleri sürer
                        failed[s] = f"{type(e).__name__}: {e}"
                        print(f"[clean] HATA {iv}/{s}: {failed[s]}", flush=True)
                        continue
                    manifest[s] = entry
                    if len(dups):
                        new_dups.append(dups)
                    if progress and (i % 100 == 0 or i == len(todo)):
                        print(f"[clean] {iv}: {i}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)
                        _save_manifest(man_p, manifest)
        _save_manifest(man_p, manifest)
        rebuilt = {s for s, _, _ in todo} - set(failed)
        old = pd.read_csv(dup_p) if dup_p.exists() else pd.DataFrame(columns=DUP_COLS)
        old = old[~old["symbol"].isin(rebuilt)] if len(old) else old
        dup_all = pd.concat([d for d in [old, *new_dups] if len(d)], ignore_index=True) \
            if (len(old) or new_dups) else pd.DataFrame(columns=DUP_COLS)
        dup_all.sort_values(["symbol", "open_time"]).to_csv(dup_p, index=False, lineterminator="\n")
        summary[iv] = {"built": len(rebuilt), "skipped": len(groups) - len(todo), "failed": failed,
                       "seconds": round(time.time() - t0, 1)}
        if progress:
            print(f"[clean] {iv}: BİTTİ kurulan {len(rebuilt)}, atlanan {len(groups) - len(todo)}, "
                  f"hatalı {len(failed)}, {time.time() - t0:.0f}s", flush=True)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="G3: ham zip → temiz parquet")
    ap.add_argument("--symbols", help="virgülle ayrılmış (varsayılan: defterdeki hepsi)")
    ap.add_argument("--intervals", help="ör. 1d,1h (varsayılan: defterdeki hepsi)")
    ap.add_argument("--force", action="store_true", help="imza değişmemiş olsa da yeniden kur")
    ap.add_argument("--workers", type=int, help="süreç sayısı (varsayılan: çekirdek − 1)")
    a = ap.parse_args(argv)
    _http.utf8_stdout()
    summ = build(load_settings(), a.intervals.split(",") if a.intervals else None,
                 a.symbols.split(",") if a.symbols else None, a.force, a.workers)
    return 1 if any(v["failed"] for v in summ.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
