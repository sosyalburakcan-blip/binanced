"""G2 — arşiv indirici: checksum doğrulama, defter, yeniden deneme, kaldığı yerden devam.

Kurallar (SPEC "Veri katmanı"):
- Yayımlanmış aylar için aylık dosya, diğer günler için günlük dosya. Hangi dosyaların gerektiği S3
  envanterinden gelir (`trend.data.s3.build_inventory`): günlük URL'ler tahmin edilmez, yalnız aylık dosyanın
  kapsamadığı ve S3'te gerçekten bulunan günlük dosyalar indirilir → delist edilmiş çiftlerde 404 fırtınası olmaz.
- Her zip `.CHECKSUM` (SHA-256, `<hash>  <dosya>`) ile doğrulanır; tutmazsa bir kez daha indirilir, yine
  tutmazsa `checksum_mismatch`.
- Defter `data/ledger.csv` (CONTRACTS §2). Çalışırken satırlar sona eklenir (kesintiye dayanıklı); yüklemede ve
  bitişte `rel_path` başına son satır kalacak şekilde sıkıştırılır. `rel_path` = `paths.raw`'a göreli yol.
- Tekrar çalıştırma yalnız eksik/başarısız dosyaları indirir: defterde `ok` olan, yerelde aynı boyutta duran ve
  S3 boyutu değişmemiş dosyalar atlanır. Yerelde duran ama defterde olmayan dosya (kesinti) yeniden indirilmez,
  CHECKSUM ile doğrulanıp deftere yazılır.
- `--reverify`: aylık yeniden kontrol; `ok` dosyaların CHECKSUM'ları yeniden çekilir, değişenler yeniden indirilir
  (arşiv düzeltmeleri, ör. 2022-08-08).

CLI örnekleri:
    python -m uv run python -m trend.data.download --all
    python -m uv run python -m trend.data.download --symbols BTCUSDT,ETHUSDT --intervals 1d,1h --since 2024-01
    python -m uv run python -m trend.data.download --all --reverify
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import pandas as pd
import requests

from trend.config import load_settings, path
from trend.data import _http, s3

LEDGER_COLS = ["rel_path", "url", "sha256_expected", "sha256_actual", "size_bytes", "downloaded_at_utc", "status"]
STATUSES = ("ok", "checksum_mismatch", "missing_remote", "error")
PROGRESS_EVERY_S = float(load_settings()["data"]["progress_every_s"])


def now_utc() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------------------------------- defter
def read_ledger(p: Path) -> pd.DataFrame:
    """Defteri okur; `rel_path` başına son satırı tutar. Kesintiyle yarım kalmış satırlar atlanır."""
    if not p.exists():
        return pd.DataFrame(columns=LEDGER_COLS)
    rows: dict[str, list[str]] = {}
    with open(p, encoding="utf-8", newline="") as f:
        rd = csv.reader(f)
        header = next(rd, None)
        if header != LEDGER_COLS:
            raise ValueError(f"{p}: beklenmeyen başlık {header}")
        for r in rd:
            if len(r) == len(LEDGER_COLS) and r[6] in STATUSES:
                rows[r[0]] = r
    df = pd.DataFrame(list(rows.values()), columns=LEDGER_COLS)
    df["size_bytes"] = pd.to_numeric(df["size_bytes"], errors="coerce").fillna(-1).astype("int64")
    return df.sort_values("rel_path", ignore_index=True)


class Ledger:
    """İş parçacığı güvenli defter: bellek içi sözlük + diske ekleme (journal)."""

    def __init__(self, p: Path):
        self.path = p
        self.lock = threading.Lock()
        df = read_ledger(p)
        self.rows: dict[str, dict] = {r["rel_path"]: r for r in df.to_dict("records")}
        self.compact()
        self._fh = open(p, "a", encoding="utf-8", newline="")
        self._w = csv.writer(self._fh, lineterminator="\n")

    def get(self, rel: str) -> dict | None:
        return self.rows.get(rel)

    def put(self, row: dict) -> None:
        with self.lock:
            self.rows[row["rel_path"]] = row
            self._w.writerow([row[c] for c in LEDGER_COLS])
            self._fh.flush()

    def compact(self) -> None:
        """Defteri `rel_path` başına tek satır, sıralı olarak atomik yeniden yazar."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(sorted(self.rows.values(), key=lambda r: r["rel_path"]), columns=LEDGER_COLS)
        s3.write_atomic_csv(df, self.path)

    def close(self) -> None:
        with self.lock:
            self._fh.close()
            self.compact()


# ------------------------------------------------------------------------------------------------- indirme
def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_checksum(text: str) -> str:
    """`<sha256>  <dosya adı>` → küçük harf hash. Biçim dışıysa ValueError."""
    h = text.strip().split()[0].lower() if text.strip() else ""
    if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
        raise ValueError(f"geçersiz CHECKSUM: {text[:100]!r}")
    return h


def fetch_checksum(url: str, d: dict) -> str | None:
    """Uzak CHECKSUM; yoksa None."""
    r = _http.get(url + ".CHECKSUM", max_retries=d["max_retries"], backoff_base_s=d["backoff_base_s"])
    if r.status_code in _http.NOT_FOUND:
        return None
    r.raise_for_status()
    return parse_checksum(r.text)


_ck_pool: ThreadPoolExecutor | None = None
_ck_lock = threading.Lock()


def _checksum_pool() -> ThreadPoolExecutor:
    """CHECKSUM'ları zip ile paralel çekmek için yardımcı havuz (eşzamanlı görev sayısı ≤ data.concurrency)."""
    global _ck_pool
    with _ck_lock:
        if _ck_pool is None:
            _ck_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="checksum")
    return _ck_pool


def fetch_one(rel: str, url: str, raw_dir: Path, d: dict, verify_local: bool = True) -> dict:
    """Tek dosya: (yerel dosya CHECKSUM ile doğrulanırsa indirme yok) → indir, hash'le, tutmazsa bir kez daha.
    Hiçbir istisnayı dışarı sızdırmaz; sonucu defter satırı olarak döndürür.

    Hız: arşiv istekleri CloudFront önbellek ıskası (~0,35–0,85 sn ilk bayt) → indirme gecikme sınırlı. Yerel dosya
    yoksa 88 baytlık CHECKSUM zip ile **paralel** çekilir; `data.concurrency` eşzamanlı dosya indirmesi sınırı
    korunur, açık HTTP bağlantısı en fazla 2 × concurrency olur (varsayım: SPEC'in 4–8 sınırı dosya başınadır)."""
    dest = raw_dir / rel
    row = {"rel_path": rel, "url": url, "sha256_expected": "", "sha256_actual": "", "size_bytes": -1,
           "downloaded_at_utc": now_utc(), "status": "error"}
    try:
        ck = None
        expected = None
        if verify_local and dest.exists():
            expected = fetch_checksum(url, d)
            row["sha256_expected"] = expected or ""
            if expected and sha256_file(dest) == expected:
                row.update(sha256_actual=expected, size_bytes=dest.stat().st_size, status="ok")
                return row
        else:
            ck = _checksum_pool().submit(fetch_checksum, url, d)
        dest.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):  # SPEC: tutmazsa bir kez daha indir
            r = _http.get(url, max_retries=d["max_retries"], backoff_base_s=d["backoff_base_s"])
            if r.status_code in _http.NOT_FOUND:
                row["status"] = "missing_remote"
                return row
            r.raise_for_status()
            body = r.content
            actual = hashlib.sha256(body).hexdigest()
            tmp = dest.with_name(dest.name + ".part")
            tmp.write_bytes(body)
            tmp.replace(dest)
            row.update(sha256_actual=actual, size_bytes=len(body), downloaded_at_utc=now_utc())
            if ck is not None:
                expected, ck = ck.result(), None
                row["sha256_expected"] = expected or ""
            if expected is None:
                # Varsayım: CHECKSUM yayımlanmamışsa dosya doğrulanamaz → `error` (temizleme kullanmaz, tekrar denenir).
                row["status"] = "error"
                return row
            if actual == expected:
                row["status"] = "ok"
                return row
        row["status"] = "checksum_mismatch"
    except (requests.RequestException, OSError, ValueError) as e:
        row["status"] = "error"
        print(f"[dl] HATA {rel}: {type(e).__name__}: {e}", flush=True)
    return row


# ------------------------------------------------------------------------------------------------- planlama
def filter_inventory(inv: pd.DataFrame, symbols: list[str] | None = None, intervals: list[str] | None = None,
                     since: str | None = None, until: str | None = None) -> pd.DataFrame:
    m = pd.Series(True, index=inv.index)
    if symbols:
        m &= inv["symbol"].isin(symbols)
    if intervals:
        m &= inv["interval"].isin(intervals)
    month = inv["period"].str[:7]
    if since:
        m &= month >= since
    if until:
        m &= month <= until
    return inv[m]


def plan(inv: pd.DataFrame, ledger: Ledger, raw_dir: Path) -> pd.DataFrame:
    """İndirilmesi gereken envanter satırları: defterde ok değil, yerelde yok/boyutu farklı ya da S3 boyutu değişmiş."""
    need = []
    for rel, size in zip(inv["rel_path"], inv["size_bytes"]):
        led = ledger.get(rel)
        if led and led["status"] == "ok" and int(led["size_bytes"]) == int(size):
            f = raw_dir / rel
            if f.exists() and f.stat().st_size == int(size):
                need.append(False)
                continue
        need.append(True)
    return inv[need]


def _fmt_eta(s: float) -> str:
    s = int(s)
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def bounded_map(fn, items, workers: int, on_result, on_tick=None) -> bool:
    """`fn`'i iş parçacığı havuzunda çalıştırır; aynı anda en fazla 4 × workers görev kuyrukta tutulur
    (100 bin görevi baştan göndermek `wait`'i yavaşlatır). Ctrl+C: yeni görev gönderilmez, uçuştakiler biter.
    Dönüş: kesildi mi."""
    it = iter(items)
    inflight: set = set()
    stop = False
    interrupted = False
    with ThreadPoolExecutor(max_workers=workers) as ex:
        while True:
            try:
                while not stop and len(inflight) < 4 * workers:
                    x = next(it, _END)
                    if x is _END:
                        stop = True
                        break
                    inflight.add(ex.submit(fn, x))
                if not inflight:
                    break
                # Kısa zaman aşımı: Windows'ta Ctrl+C ana iş parçacığına ancak bekleme dönünce ulaşır.
                done, inflight = wait(inflight, timeout=1.0, return_when=FIRST_COMPLETED)
                for f in done:
                    on_result(f.result())
                if on_tick:
                    on_tick()
            except KeyboardInterrupt:
                if interrupted:  # ikinci Ctrl+C: beklemeden çık
                    raise
                interrupted = stop = True
                print("[dl] kesildi; uçuştaki dosyalar bitiyor, defter kaydediliyor...", flush=True)
    return interrupted


_END = object()


def run(tasks: list[tuple[str, str, int]], ledger: Ledger, raw_dir: Path, cfg: dict,
        label: str = "dl", verify_local: bool = True) -> dict:
    """`(rel_path, url, beklenen_boyut)` görevlerini çalıştırır; ilerlemeyi yazdırır. Ctrl+C güvenlidir:
    uçuştaki dosyalar biter ve deftere yazılır, tekrar çalıştırma kalan dosyalarla devam eder."""
    d = cfg["data"]
    total = len(tasks)
    total_bytes = sum(int(t[2]) for t in tasks)
    stats = {s: 0 for s in STATUSES}
    stats.update(done=0, bytes=0)
    t0 = time.time()
    last = [t0]

    def work(t):
        row = fetch_one(t[0], t[1], raw_dir, d, verify_local=verify_local)
        ledger.put(row)
        return row

    def progress(final=False):
        el = max(time.time() - t0, 1e-9)
        rate = stats["done"] / el
        eta = (total - stats["done"]) / rate if rate > 0 else float("nan")
        print(f"[{label}] {'BİTTİ ' if final else ''}{stats['done']}/{total} dosya "
              f"({100 * stats['done'] / max(total, 1):.1f}%), {stats['bytes'] / 1e6:.1f}/{total_bytes / 1e6:.1f} MB, "
              f"ok {stats['ok']}, eksik {stats['missing_remote']}, checksum {stats['checksum_mismatch']}, "
              f"hata {stats['error']}, {rate:.1f} dosya/s, {stats['bytes'] / el / 1e6:.2f} MB/s"
              + ("" if final or rate == 0 else f", kalan ~{_fmt_eta(eta)}"), flush=True)

    def on_result(row):
        stats["done"] += 1
        stats[row["status"]] += 1
        stats["bytes"] += max(int(row["size_bytes"]), 0)
        if row["status"] != "ok":
            print(f"[{label}] {row['status']}: {row['rel_path']}", flush=True)

    def on_tick():
        if time.time() - last[0] >= PROGRESS_EVERY_S:
            last[0] = time.time()
            progress()

    interrupted = bounded_map(work, tasks, d["concurrency"], on_result, on_tick)
    progress(final=True)
    stats.update(interrupted=interrupted, seconds=round(time.time() - t0, 1), total=total)
    return stats


# --------------------------------------------------------------------------------------------------- CLI
def load_or_build_inventory(cfg: dict, symbols: list[str] | None, refresh: bool) -> pd.DataFrame:
    """Envanter bugün (UTC) oluşturulmuşsa okunur; değilse S3 yeniden listelenir.
    Sembol alt kümesinde ve envanter eskiyse yalnız o semboller listelenir (tam envanter dosyası değişmez)."""
    p = s3.inventory_path(cfg)
    fresh = p.exists() and dt.datetime.fromtimestamp(p.stat().st_mtime, dt.UTC).date() == dt.datetime.now(dt.UTC).date()
    if fresh and not refresh:
        return s3.read_inventory(cfg)
    if symbols:
        inv, _, _ = s3.build_inventory(cfg, symbols, progress=False)
        return inv
    inv, raw, _ = s3.build_inventory(cfg)
    s3.write_atomic_csv(inv, p)
    s3.write_atomic_csv(raw, path(cfg, "meta") / "symbols_raw.csv")
    return inv


def reverify(ledger: Ledger, raw_dir: Path, cfg: dict, rels: list[str] | None = None) -> pd.DataFrame:
    """Aylık yeniden kontrol: ok dosyaların CHECKSUM'ını yeniden çeker ve yerel dosyayı yeniden hash'ler;
    uzak hash defterdekinden farklıysa (arşiv düzeltmesi) ya da yerel dosya bozuk/eksikse yeniden indirir.
    Dönüş: değişen dosyalar (rel_path, eski, yeni hash, yeni durum)."""
    d = cfg["data"]
    rows = [r for r in ledger.rows.values() if r["status"] == "ok" and (rels is None or r["rel_path"] in rels)]
    changed: list[dict] = []
    t0, n = time.time(), 0

    def check(r):
        try:
            exp = fetch_checksum(r["url"], d)
        except (requests.RequestException, ValueError) as e:
            return {"rel_path": r["rel_path"], "old": r["sha256_actual"], "new": "", "status": f"error:{e}"}
        f = raw_dir / r["rel_path"]
        if exp == r["sha256_actual"] and f.exists() and sha256_file(f) == exp:
            return None
        new = fetch_one(r["rel_path"], r["url"], raw_dir, d, verify_local=False) if exp else \
            {**r, "status": "missing_remote", "downloaded_at_utc": now_utc()}
        ledger.put(new)
        return {"rel_path": r["rel_path"], "old": r["sha256_actual"], "new": new["sha256_actual"],
                "status": new["status"]}

    def on_result(res):
        nonlocal n
        n += 1
        if res:
            changed.append(res)
            print(f"[reverify] değişti: {res}", flush=True)
        if n % 2000 == 0:
            print(f"[reverify] {n}/{len(rows)} kontrol, {len(changed)} değişen, {time.time() - t0:.0f}s", flush=True)

    bounded_map(check, rows, d["concurrency"], on_result)
    print(f"[reverify] BİTTİ {n} dosya, {len(changed)} değişen, {time.time() - t0:.0f}s", flush=True)
    return pd.DataFrame(changed, columns=["rel_path", "old", "new", "status"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="G2: data.binance.vision indirici (checksum + defter)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="envanterdeki tüm gerekli dosyalar")
    g.add_argument("--symbols", help="virgülle ayrılmış semboller, ör. BTCUSDT,ETHUSDT")
    ap.add_argument("--intervals", help="ör. 1d,1h")
    ap.add_argument("--since", help="YYYY-MM (dahil)")
    ap.add_argument("--until", help="YYYY-MM (dahil)")
    ap.add_argument("--refresh-inventory", action="store_true", help="S3'ü bugün listelenmiş olsa da yeniden listele")
    ap.add_argument("--reverify", action="store_true", help="aylık yeniden kontrol (CHECKSUM'ları yeniden çek)")
    ap.add_argument("--dry-run", action="store_true", help="yalnız planı yazdır")
    ap.add_argument("--max-files", type=int, help="en fazla N dosya (deneme için)")
    a = ap.parse_args(argv)
    _http.utf8_stdout()

    cfg = load_settings()
    raw_dir = path(cfg, "raw")
    syms = a.symbols.split(",") if a.symbols else None
    ivs = a.intervals.split(",") if a.intervals else None
    ledger = Ledger(path(cfg, "ledger"))
    try:
        if a.reverify:
            led = read_ledger(ledger.path)
            parts = led.rel_path.str.split("/")
            led = led.assign(symbol=parts.str[2], interval=parts.str[3], period=_period_from_rel(led.rel_path))
            rels = filter_inventory(led, syms, ivs, a.since, a.until)["rel_path"]
            ch = reverify(ledger, raw_dir, cfg, set(rels))
            out = raw_dir / f"_reverify_{dt.datetime.now(dt.UTC):%Y%m%d}.csv"
            s3.write_atomic_csv(ch, out)
            print(f"[reverify] değişen dosya listesi: {out}")
            return 0
        inv = load_or_build_inventory(cfg, syms, a.refresh_inventory)
        inv = filter_inventory(inv, syms, ivs, a.since, a.until)
        todo = plan(inv, ledger, raw_dir)
        if a.max_files:
            todo = todo.head(a.max_files)
        print(f"[dl] envanter {len(inv)} dosya ({inv.size_bytes.sum() / 1e6:.1f} MB); indirilecek {len(todo)} "
              f"({todo.size_bytes.sum() / 1e6:.1f} MB); eşzamanlılık {cfg['data']['concurrency']}", flush=True)
        if a.dry_run or todo.empty:
            return 0
        st = run(list(zip(todo.rel_path, todo.url, todo.size_bytes)), ledger, raw_dir, cfg)
        return 130 if st["interrupted"] else (1 if st["checksum_mismatch"] or st["error"] else 0)
    finally:
        ledger.close()


def _period_from_rel(rel: pd.Series) -> pd.Series:
    """`.../SYM-INT-YYYY-MM.zip` → `YYYY-MM`; `.../SYM-INT-YYYY-MM-DD.zip` → `YYYY-MM-DD`."""
    stem = rel.str.rsplit("/", n=1).str[-1].str.removesuffix(".zip")
    daily = rel.str.startswith("daily/")
    parts = stem.str.split("-")
    return parts.str[-3:].str.join("-").where(daily, parts.str[-2:].str.join("-"))


if __name__ == "__main__":
    sys.exit(main())
