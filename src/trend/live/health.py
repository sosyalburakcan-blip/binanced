"""Canlı kâğıt takip sağlık kontrolü: bot kayıt yazıyor mu, saatlik kararlar alınıyor mu, hata var mı, işlem neden
yok (momentum eşiğe ne kadar yakın) ve bu bekleme backtestle uyumlu mu. Kaynak `data/live/live.db` (salt okunur).

    python -m uv run python -m trend.live.health [--hours 24] [--send | --send-if-problem] [--restart]

Durum ve çıkış kodu: TAMAM 0, UYARI 1, SORUN 2.
- --send: özeti telefona gönderir (trend.live.notify, `.env.bildirim`); --send-if-problem yalnızca UYARI/SORUN'da.
- --restart: bot süreci yoksa başlatır; süreç var ama `HUNG_S`'dir kayıt yazmıyorsa öldürüp başlatır. Süreç sağlıklıyken
  ikinci kopya asla başlatılmaz (aynı veritabanına tek yazar). Eski günlük `paper_YYYYmmdd_HHMM.log` olarak saklanır.

Kurallar:
- Canlılık: `state.last_seen_ms` (bot 5 sn'de bir yazar) `STALE_S`'den eskiyse SORUN.
- Kararlar: pencere içinde sınırı (k + 1 sa) geçmiş her saat × piyasa için `signals` satırı beklenir (faz fark etmez;
  yeniden başlatmada son saat `warmup` olarak yazılır). Eksik saat SORUN, `late` faz UYARI.
- Hatalar: error / handler_error SORUN; diğer hata türleri, bildirim hataları, giriş atlamaları ve 10 dk'yı aşan veri
  kesintisi UYARI.
- İşlem yok açıklaması (strateji başına, pencere içindeki sinyaller): giriş varsa sayısı; aday (top ∧ ok) var ama
  giriş yoksa UYARI; z eşiği aştı ama takip süresi dolmadıysa en uzun seri; hiç aşmadıysa en yüksek z. Backtest
  (`backtests/v4/spot_ctl/trades`, tam dönem) haftalık giriş sayısı ve girişler arası bekleme (medyan, %90, en uzun)
  verilir; canlıda girişsiz geçen süre backtestteki en uzun beklemeyi aşarsa UYARI.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

from trend.config import ROOT
from trend.live.recorder import DB_PATH

H_MS = 3_600_000
DAY_MS = 86_400_000
STALE_S = 120.0
HUNG_S = 600.0
DOWN_WARN_S = 600.0
DECISION_SLACK_MS = 15 * 60_000
TRADES_DIR = ROOT / "backtests" / "v4" / "spot_ctl" / "trades"
LIVE_DIR = ROOT / "data" / "live"
OK, WARN, BAD, INFO = 0, 1, 2, -1
LEVEL_TR = {OK: "TAMAM", WARN: "UYARI", BAD: "SORUN"}
ICON = {OK: "✅", WARN: "⚠️", BAD: "❌", INFO: "•"}
ERROR_BAD = ("error", "handler_error")
ERROR_WARN = ("connect_error", "backfill_error", "rest_error", "clock_error", "notify_error", "decision_late")
VENUE_TR = {"spot": "spot", "futures": "vadeli"}


def _tr(ms) -> str:
    """Türkiye saati (UTC+3, yaz saati yok)."""
    return pd.Timestamp(int(ms) + 3 * H_MS, unit="ms").strftime("%d.%m %H:%M")


def _ago(ms_delta: float) -> str:
    s = ms_delta / 1000
    if s < 120:
        return f"{s:.0f} sn"
    if s < 2 * 3600:
        return f"{s / 60:.0f} dk"
    if s < 2 * 86400:
        return f"{s / 3600:.1f} sa"
    return f"{s / 86400:.1f} gün"


def _detail(d) -> dict:
    try:
        return json.loads(d) if isinstance(d, str) else (d or {})
    except ValueError:
        return {"text": str(d)}


def expectations(names, trades_dir: Path = TRADES_DIR) -> dict:
    """Strateji → backtest giriş istatistikleri (dosya yoksa atlanır): haftalık giriş, bekleme günleri, son giriş."""
    out = {}
    for n in names:
        f = Path(trades_dir) / f"{n}.parquet"
        if not f.exists():
            continue
        e = pd.read_parquet(f, columns=["entry_time"])["entry_time"].sort_values()
        if len(e) < 2:
            continue
        gaps = e.diff().dropna().dt.total_seconds() / 86400
        span = (e.iloc[-1] - e.iloc[0]).total_seconds() / 86400
        out[n] = {"per_week": len(e) / span * 7 if span > 0 else math.nan, "gap_med_d": float(gaps.median()),
                  "gap_p90_d": float(gaps.quantile(0.9)), "gap_max_d": float(gaps.max()),
                  "last_entry": str(e.iloc[-1])[:16], "n": int(len(e))}
    return out


def _runs(rows: list[dict], z_entry: float) -> tuple[int, str | None]:
    """En uzun ardışık z ≥ eşik serisi (saat) ve varlığı."""
    by = defaultdict(list)
    for r in rows:
        by[r["asset"]].append((int(r["hour_ms"]), r["z"]))
    best, who = 0, None
    for a, xs in by.items():
        run, prev = 0, None
        for h, z in sorted(xs):
            hit = z is not None and math.isfinite(z) and z >= z_entry
            run = (run + 1 if prev is not None and h - prev == H_MS else 1) if hit else 0
            prev = h if hit else None
            if run > best:
                best, who = run, a
    return best, who


def diagnose(rows, now_ms: int, hours: float = 24.0, expect: dict | None = None) -> dict:
    """`rows(sql, params)` → dict listesi (Recorder.rows). Sonuç: {"level", "findings": [(seviye, metin)], ...}."""
    F: list[tuple[int, str]] = []
    w0 = int(now_ms - hours * H_MS)
    starts = rows("SELECT MIN(ts_ms) AS t FROM events WHERE kind = 'start'")
    first_start = starts[0]["t"] if starts and starts[0]["t"] is not None else None
    w0 = max(w0, int(first_start)) if first_start is not None else w0

    # canlılık
    st = rows("SELECT value FROM state WHERE key = 'last_seen_ms'")
    last_seen = int(json.loads(st[0]["value"])) if st else None
    if last_seen is None:
        F.append((BAD, "bot hiç kayıt yazmamış (last_seen yok)"))
        age = math.inf
    else:
        age = now_ms - last_seen
        F.append((BAD, f"bot kayıt yazmıyor: son kayıt {_ago(age)} önce ({_tr(last_seen)})") if age > STALE_S * 1000
                 else (OK, f"bot çalışıyor, son kayıt {_ago(age)} önce"))

    # bağlantı
    ev = rows("SELECT ts_ms, venue, kind, detail FROM events WHERE ts_ms >= ? ORDER BY ts_ms", (w0,))
    disc = [e for e in ev if e["kind"] == "disconnect"]
    down = sum(float(_detail(e["detail"]).get("down_s") or 0) for e in ev if e["kind"] == "gap")
    msg = f"bağlantı: {len(disc)} kopma, toplam veri kesintisi {down / 60:.1f} dk"
    F.append((WARN if down > DOWN_WARN_S else INFO, msg))

    # saatlik kararlar
    sig = rows("SELECT DISTINCT venue, hour_ms, phase FROM signals WHERE hour_ms >= ?", (w0 - 2 * H_MS,))
    venues = sorted({r["venue"] for r in rows("SELECT DISTINCT venue FROM signals")})
    for v in venues:
        have = {int(r["hour_ms"]) for r in sig if r["venue"] == v}
        late = {int(r["hour_ms"]) for r in sig if r["venue"] == v and r["phase"] == "late"}
        k0 = (w0 // H_MS) * H_MS
        need = [k for k in range(k0, int(now_ms), H_MS) if w0 <= k + H_MS <= now_ms - DECISION_SLACK_MS]
        miss = [k for k in need if k not in have]
        name = VENUE_TR.get(v, v)
        if miss:
            F.append((BAD, f"{name}: {len(miss)} saatlik karar eksik (ilk {_tr(miss[0] + H_MS)}, son "
                           f"{_tr(miss[-1] + H_MS)})"))
        elif need:
            F.append((OK, f"{name}: son {len(need)} saatin kararları alındı"))
        if late:
            F.append((WARN, f"{name}: {len(late)} karar geç kaldı (giriş yapılmadı)"))

    # hatalar ve atlamalar
    bad = [e for e in ev if e["kind"] in ERROR_BAD]
    warn = [e for e in ev if e["kind"] in ERROR_WARN]
    for lvl, xs in ((BAD, bad), (WARN, warn)):
        if xs:
            kinds = defaultdict(int)
            for e in xs:
                kinds[e["kind"]] += 1
            last = xs[-1]
            d = _detail(last["detail"])
            F.append((lvl, f"hata: {dict(kinds)}; son: {_tr(last['ts_ms'])} {last['kind']} "
                           f"{str(d.get('error') or d.get('info') or d)[:160]}"))
    if not bad and not warn:
        F.append((OK, "hata yok"))
    skips = defaultdict(int)
    unfilled = defaultdict(int)                     # strateji → dolmayan maker giriş emri
    for e in ev:
        if e["kind"] == "entry_skip":
            d = _detail(e["detail"])
            skips[d.get("why")] += 1
            if d.get("why") == "unfilled":
                unfilled[str(d.get("account", "")).split("/")[0]] += 1
    if skips:
        F.append((WARN if set(skips) - {"no_slot", "unfilled"} else INFO, f"atlanan girişler: {dict(skips)}"))

    # strateji başına: neden işlem yok
    acc = rows("SELECT account, strategy, params FROM accounts")
    strat = {}
    for a in acc:
        p = _detail(a["params"]).get("strategy")
        if isinstance(p, dict):
            strat[a["strategy"]] = p
    expect = expect or {}
    per = {}
    for name, p in strat.items():
        z_entry, confirm = float(p["z_entry"]), int(p["confirm_h"])
        sr = rows("SELECT hour_ms, asset, z, ok, top FROM signals WHERE strategy = ? AND venue = 'spot' AND hour_ms >= ?",
                  (name, w0 - (confirm + 1) * H_MS))
        sr_w = [r for r in sr if int(r["hour_ms"]) + H_MS >= w0]
        ents = rows("SELECT entry_ms, asset FROM positions WHERE strategy = ? ORDER BY entry_ms", (name,))
        n_win = len({(r["asset"], int(r["entry_ms"]) // H_MS) for r in ents if r["entry_ms"] >= w0})
        cand = [r for r in sr_w if r["ok"] and r["top"]]
        zs = [r for r in sr_w if r["z"] is not None and math.isfinite(r["z"])]
        top = max(zs, key=lambda r: r["z"]) if zs else None
        run, who = _runs(sr, z_entry)
        if n_win:
            lvl, why = OK, f"{n_win} giriş"
        elif cand and unfilled.get(name):
            lvl, why = INFO, (f"{len(cand)} aday saat vardı; {unfilled[name]} maker alış emri süresinde dolmadı "
                              "(fiyat emirden kaçtı)")
        elif cand:
            open_n = rows("SELECT COUNT(*) AS n FROM positions WHERE strategy = ? AND status = 'open'", (name,))[0]["n"]
            lvl = INFO if open_n else WARN
            why = (f"{len(cand)} aday saat vardı ama giriş yok"
                   + (f" ({open_n} açık pozisyon, yuva/elde olabilir)" if open_n else " — incelenmeli"))
        elif top is not None and top["z"] >= z_entry:
            lvl, why = OK, (f"z eşiği ({z_entry:g}) aşıldı ama {confirm} saat sürmedi: en uzun {run} sa ({who})")
        elif top is not None:
            lvl, why = OK, (f"momentum eşiğe ulaşmadı: en yüksek z {top['z']:.2f} ({top['asset']}, "
                            f"{_tr(int(top['hour_ms']) + H_MS)}); eşik {z_entry:g}, {confirm} saat üst üste sürmeli")
        else:
            lvl, why = WARN, "pencerede sinyal kaydı yok"
        last_e = max((int(r["entry_ms"]) for r in ents), default=None)
        since0 = last_e if last_e is not None else first_start
        idle_d = (now_ms - since0) / DAY_MS if since0 is not None else math.nan
        ex = expect.get(name)
        if ex:
            why += (f". Backtest: haftada {ex['per_week']:.1f} giriş, bekleme medyan {ex['gap_med_d']:.1f} gün, "
                    f"%90 ≤ {ex['gap_p90_d']:.0f} gün, en uzun {ex['gap_max_d']:.0f} gün (son backtest girişi "
                    f"{ex['last_entry'][:10]})")
            if math.isfinite(idle_d) and idle_d > ex["gap_max_d"]:
                lvl = max(lvl, WARN)
                why += f". Canlıda {idle_d:.1f} gündür giriş yok — backtestteki en uzun beklemeyi aştı"
        if math.isfinite(idle_d) and not n_win:
            why += f". Canlıda girişsiz: {idle_d:.1f} gün"
        per[name] = {"entries": n_win, "candidates": len(cand), "max_z": top["z"] if top else None, "run": run}
        F.append((lvl, f"{name}: {why}"))

    level = max([lv for lv, _ in F if lv >= 0], default=OK)
    return {"level": level, "findings": F, "per_strategy": per, "window_start": w0, "now": now_ms,
            "last_seen": last_seen}


def format_text(d: dict) -> str:
    lines = [f"🩺 Sağlık kontrolü {_tr(d['now'])} · {LEVEL_TR[d['level']]}"]
    lines += [f"{ICON[lv]} {t}" for lv, t in d["findings"]]
    return "\n".join(lines)


# --- süreç ---

def paper_pids() -> list[int]:
    """Çalışan `trend.live.paper` süreçleri (Windows; python/uv). Başka sistemde pgrep."""
    if os.name == "nt":
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='uv.exe'\" | "
              "Where-Object { $_.CommandLine -like '*trend.live.paper*' } | ForEach-Object { $_.ProcessId }")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=60)
    else:
        out = subprocess.run(["pgrep", "-f", "trend.live.paper"], stdin=subprocess.DEVNULL, capture_output=True,
                             text=True, timeout=60)
    return [int(x) for x in out.stdout.split() if x.strip().isdigit()]


def kill(pids: list[int]) -> None:
    for pid in pids:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=60)
        else:
            os.kill(pid, 9)


def start_paper(config: str = "live_v4.yaml") -> int:
    """Gizli, bağımsız süreç olarak başlatır (Start-Process; aracı kapansa da sürer). Eski günlük yeniden adlandırılır."""
    log, err = LIVE_DIR / "paper.log", LIVE_DIR / "paper.err"
    stamp = time.strftime("%Y%m%d_%H%M")
    for f in (log, err):
        if f.exists() and f.stat().st_size:
            f.rename(f.with_name(f"{f.stem}_{stamp}{f.suffix}"))
    if os.name != "nt":
        p = subprocess.Popen([sys.executable, "-m", "trend.live.paper", "--config", config], cwd=ROOT,
                             stdin=subprocess.DEVNULL, stdout=open(log, "wb"), stderr=open(err, "wb"),
                             start_new_session=True)
        pid = p.pid
        (LIVE_DIR / "paper.pid").write_text(str(pid), encoding="utf-8")
        return pid
    # Boru yok: başlatılan süreç tutamaçları miras alır; yakalanan bir boruyu miras alırsa bu komut hiç bitmez.
    pid_file = LIVE_DIR / "paper.pid"
    args = ",".join(f"'{a}'" for a in ("-m", "trend.live.paper", "--config", config))
    ps = (f"$env:PYTHONIOENCODING='utf-8'; (Start-Process -FilePath '{sys.executable}' -ArgumentList {args} "
          f"-WorkingDirectory '{ROOT}' -WindowStyle Hidden -RedirectStandardOutput '{log}' "
          f"-RedirectStandardError '{err}' -PassThru).Id | Set-Content -Encoding ascii '{pid_file}'")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=60, check=True)
    return int(pid_file.read_text(encoding="ascii").strip())


def main(argv: list[str] | None = None) -> int:
    from trend.data._http import utf8_stdout
    ap = argparse.ArgumentParser(prog="python -m trend.live.health", description="Kâğıt takip sağlık kontrolü")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--hours", type=float, default=24.0, help="bakılan pencere (saat)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--send", action="store_true", help="özeti telefona gönder")
    g.add_argument("--send-if-problem", action="store_true", help="yalnızca UYARI/SORUN'da gönder")
    ap.add_argument("--restart", action="store_true", help="bot ölü ya da takılıysa yeniden başlat")
    ap.add_argument("--config", default="live_v4.yaml")
    a = ap.parse_args(argv)
    utf8_stdout()
    con = sqlite3.connect(f"{Path(a.db).resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    try:
        def rows(sql, params=()):
            cur = con.execute(sql, params)
            names = [c[0] for c in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]
        strategies = [r["strategy"] for r in rows("SELECT DISTINCT strategy FROM accounts")]
        d = diagnose(rows, int(time.time() * 1000), a.hours, expectations(strategies))
    finally:
        con.close()
    restarted = None
    if a.restart:
        pids = paper_pids()
        age_s = (d["now"] - d["last_seen"]) / 1000 if d["last_seen"] else math.inf
        if not pids:
            restarted = ("süreç yoktu", start_paper(a.config))
        elif age_s > HUNG_S:
            kill(pids)
            time.sleep(3)
            restarted = (f"süreç {age_s / 60:.0f} dk'dır kayıt yazmıyordu, öldürüldü", start_paper(a.config))
        else:
            d["findings"].insert(1, (INFO, f"süreç: {len(pids)} (python/uv)"))
        if restarted:
            d["findings"].insert(0, (BAD, f"bot yeniden başlatıldı: {restarted[0]} (yeni PID {restarted[1]})"))
            d["level"] = BAD
    text = format_text(d)
    print(text)
    if a.send or (a.send_if_problem and d["level"] >= WARN):
        from trend.live.notify import ENV_PATH, Notifier
        n = Notifier(ENV_PATH, start=False, retry_s=(5.0,))
        sent = n.deliver([text])
        print(f"bildirim: {'gönderildi' if sent else 'gönderilemedi (kanal yok ya da hata)'}")
    return d["level"]


if __name__ == "__main__":
    raise SystemExit(main())
