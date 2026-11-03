"""Günlük canlı kâğıt takip raporu: `reports/live/YYYY-MM-DD.md` (kaynak `data/live/live.db`).

    python -m uv run python -m trend.live.report --date 2026-11-04 [--db data/live/live.db] [--no-rest] [--days 7]

İçerik (gün = UTC takvim günü [00:00, 24:00); `--days N` ile N günlük dönem, ör. haftalık gözden geçirme):
- Hesap başına (strateji × spot/vadeli kaldıraç): gün içinde kapanan işlemler (neden dağılımı, kazanan), net PnL,
  ücretler (o günün dolumları), fonlama (fonlama zamanı o gün); gün başı/sonu özsermaye (15 dk anlık görüntüleri) ve
  başlangıçtan beri getiri.
- Kayma: alıcı (taker) dolumlarda gerçekleşen kayma (VWAP'ın orta fiyata göre bps'i) vs backtest varsayımı (evren
  dosyasının kayma kademesi) ve farkı; SL dolumlarında stop fiyatına göre kayma (backtest SL·(1 − kayma) varsayar).
- Gün sonunda açık pozisyonlar; olay sayıları (bağlantı, kopma, bayatlık, kesinti, mum boşluğu, hata) ve hatalar.
- Tutarlılık: o günün kayıtlı saatlik kapanışları ve sinyalleri (z, ok, top), herkese açık REST 15 dk mumlarından
  backtest koduyla (`sim.hourly_close` + `sim.hourly_signals`, aynı kayan pencere ve sütunlar) yeniden hesaplananla
  karşılaştırılır; farklar listelenir ve özet `events` tablosuna `consistency` olarak yazılır.
  Toleranslar: kapanış göreli 1e-9, z mutlak 1e-6 (ikisi de NaN = eşit); ok ve top tam eşitlik.

Varsayımlar:
- Yeniden hesap için günün son yapılandırma anlık görüntüsü (`config` tablosu: varlıklar, semboller, çarpanlar,
  strateji parametreleri, keep_h) kullanılır.
- REST erişilemezse (veya --no-rest) tutarlılık bölümü "atlandı" yazar; rapor yine üretilir.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from trend.config import ROOT
from trend.intraday.sim import Market, Params, hourly_close, hourly_signals
from trend.live.recorder import DB_PATH, Recorder
from trend.live.stream import PublicRest, SymbolTable, rest_bars

H_MS = 3_600_000
BAR_MS = 900_000
DAY_MS = 86_400_000
OUT_DIR = ROOT / "reports" / "live"
CLOSE_RTOL = 1e-9
Z_ATOL = 1e-6
MAX_LIST = 60
ERROR_KINDS = ("error", "handler_error", "connect_error", "backfill_error", "rest_error", "clock_error")


def day_bounds(date) -> tuple[int, int]:
    t0 = int(pd.Timestamp(date).normalize().value // 1_000_000)
    return t0, t0 + DAY_MS


def _utc(ms) -> str:
    return "—" if ms is None or (isinstance(ms, float) and not math.isfinite(ms)) else \
        pd.Timestamp(int(ms), unit="ms").strftime("%Y-%m-%d %H:%M")


def _n(x, fmt="{:.2f}") -> str:
    if x is None:
        return "—"
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return str(x)
    return fmt.format(xf) if math.isfinite(xf) else "—"


def _table(headers: list[str], rows: list[list]) -> list[str]:
    if not rows:
        return ["(yok)"]
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def _df(rec: Recorder, sql: str, params=()) -> pd.DataFrame:
    d = pd.DataFrame(rec.rows(sql, params))
    for c in d.columns:                    # tamamı NULL olan sayısal kolonlar object kalmasın
        if d[c].dtype == object and d[c].map(lambda v: v is None or isinstance(v, (int, float))).all():
            d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


# ---------------------------------------------------------------------------------------------------------------
# Tutarlılık


def recompute(sig: pd.DataFrame, snap: dict, fetch, now_ms: int | None = None) -> pd.DataFrame:
    """Kayıtlı sinyal satırlarının saatleri için REST 15 dk mumlarından backtest koduyla yeniden hesap."""
    cfg = snap["config"]
    assets = list(snap["assets"])
    keep_h = int(snap["keep_h"])
    syms = SymbolTable.from_json(snap["symbols"])
    params = {s["name"]: Params(lookback_h=int(s["lookback_h"]), z_entry=float(s["z_entry"]),
                                confirm_h=int(s["confirm_h"]), tp=float(s["tp"]), sl=float(s["sl"]),
                                max_hold_h=int(s["max_hold_h"]), vol_window_h=int(cfg["vol_window_h"]),
                                n_top=int(cfg["n_top"]), slots=int(cfg["slots"])) for s in cfg["strategies"]}
    out = []
    for venue, g in sig.groupby("venue"):
        hours = sorted(int(h) for h in g["hour_ms"].unique())
        h0 = hours[0] - (keep_h - 1) * H_MS
        T = (hours[-1] - h0) // BAR_MS + 4
        t15 = pd.date_range(pd.Timestamp(h0, unit="ms"), periods=T, freq="15min")
        arr = {k: np.full((T, len(assets)), np.nan) for k in "ohlc"}
        for j, a in enumerate(assets):
            s = syms.get(venue, a)
            if s is None:
                continue
            for t, o, h, l, c in rest_bars(fetch(venue, s.symbol, "15m", h0, h0 + T * BAR_MS - 1), s.mult, now_ms):  # noqa: E741
                i = (t - h0) // BAR_MS
                if 0 <= i < T:
                    arr["o"][i, j], arr["h"][i, j], arr["l"][i, j], arr["c"][i, j] = o, h, l, c
        C = hourly_close(Market(assets=assets, t15=t15, o=arr["o"], h=arr["h"], l=arr["l"], c=arr["c"]))
        elig = np.ones(C.shape, dtype=bool)
        for name, p in params.items():
            if name not in set(g["strategy"]):
                continue
            z, ok, top = hourly_signals(C, elig, p)
            for hm in hours:
                i = (hm - h0) // H_MS
                for j, a in enumerate(assets):
                    out.append({"hour_ms": hm, "venue": venue, "strategy": name, "asset": a, "close": C[i, j],
                                "z": z[i, j], "ok": int(ok[i, j]), "top": int(top[i, j])})
    return pd.DataFrame(out, columns=["hour_ms", "venue", "strategy", "asset", "close", "z", "ok", "top"])


def compare(live: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Farklı satırlar: (saat, piyasa, strateji, varlık, alan, canlı, REST)."""
    key = ["hour_ms", "venue", "strategy", "asset"]
    m = live.merge(ref, on=key, how="left", suffixes=("_live", "_rest"), indicator=True)
    rows = []
    for d in m.to_dict("records"):
        if d["_merge"] != "both":
            rows.append({**{k: d[k] for k in key}, "field": "missing_rest", "live": None, "rest": None})
            continue
        cl, cr = d["close_live"], d["close_rest"]
        if _neq(cl, cr, rel=CLOSE_RTOL):
            rows.append({**{k: d[k] for k in key}, "field": "close", "live": cl, "rest": cr})
        if _neq(d["z_live"], d["z_rest"], abs_=Z_ATOL):
            rows.append({**{k: d[k] for k in key}, "field": "z", "live": d["z_live"], "rest": d["z_rest"]})
        for f in ("ok", "top"):
            if int(d[f"{f}_live"] or 0) != int(d[f"{f}_rest"] or 0):
                rows.append({**{k: d[k] for k in key}, "field": f, "live": d[f"{f}_live"], "rest": d[f"{f}_rest"]})
    return pd.DataFrame(rows, columns=key + ["field", "live", "rest"])


def _neq(a, b, rel: float | None = None, abs_: float | None = None) -> bool:
    fa = a is not None and not (isinstance(a, float) and math.isnan(a))
    fb = b is not None and not (isinstance(b, float) and math.isnan(b))
    if not fa and not fb:
        return False
    if fa != fb:
        return True
    a, b = float(a), float(b)
    if rel is not None:
        return abs(a - b) > rel * max(abs(a), abs(b), 1e-300)
    return abs(a - b) > abs_


# ---------------------------------------------------------------------------------------------------------------
# Rapor


def build(date, db: Path | str = DB_PATH, out_dir: Path | str = OUT_DIR, fetch=None, use_rest: bool = True,
          now_ms: int | None = None, days: int = 1) -> Path:
    """`days` > 1: haftalık vb. dönem raporu [date, date + days) → `YYYY-MM-DD_{days}g.md`."""
    t0, _ = day_bounds(date)
    t1 = t0 + int(days) * DAY_MS
    day = pd.Timestamp(date).strftime("%Y-%m-%d")
    label = day if int(days) == 1 else f"{day} + {int(days)} gün"
    rec = Recorder(db)
    try:
        lines = _build(rec, label, t0, t1, fetch, use_rest, now_ms)
    finally:
        rec.close()
    out = Path(out_dir) / (f"{day}.md" if int(days) == 1 else f"{day}_{int(days)}g.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return out


def _build(rec: Recorder, day: str, t0: int, t1: int, fetch, use_rest: bool, now_ms) -> list[str]:
    acc = _df(rec, "SELECT * FROM accounts ORDER BY account")
    pos = _df(rec, "SELECT * FROM positions")
    fills = _df(rec, "SELECT * FROM fills WHERE ts_ms >= ? AND ts_ms < ?", (t0, t1))
    fund = _df(rec, "SELECT * FROM funding WHERE funding_ms >= ? AND funding_ms < ?", (t0, t1))
    eq = _df(rec, "SELECT * FROM equity WHERE ts_ms < ? ORDER BY ts_ms", (t1,))
    ev = _df(rec, "SELECT * FROM events WHERE ts_ms >= ? AND ts_ms < ? ORDER BY ts_ms", (t0, t1))
    sig = _df(rec, "SELECT * FROM signals WHERE hour_ms >= ? AND hour_ms < ?", (t0, t1))
    snap_row = rec.rows("SELECT json FROM config WHERE ts_ms < ? ORDER BY ts_ms DESC LIMIT 1", (t1,))
    snap = json.loads(snap_row[0]["json"]) if snap_row else None

    L = [f"# Canlı kâğıt takip — {day} (UTC)", "",
         "Gölge mod: gerçek emir yok; dolumlar canlı emir defterinde yürünerek, çıkışlar canlı işlemlerle "
         "(TP yalnızca TP'nin kesin üstündeki işlemle). Kaynak `data/live/live.db`.", ""]
    if snap:
        c = snap["config"]
        L += [f"Evren {snap.get('universe_month')}: {', '.join(snap['assets'])}. Sermaye {c['capital_usdt']:g} USDT, "
              f"kaldıraç {c['leverage']}, yuva {c['slots']}, n_top {c['n_top']}, vol_window_h {c['vol_window_h']}.", ""]
        L += _table(["strateji", "lookback_h", "z_entry", "confirm_h", "tp", "sl", "max_hold_h"],
                    [[s["name"], s["lookback_h"], s["z_entry"], s["confirm_h"], s["tp"], s["sl"], s["max_hold_h"]]
                     for s in c["strategies"]]) + [""]

    # --- hesaplar ---
    L += ["## Hesaplar", ""]
    rows = []
    for a in acc.to_dict("records") if len(acc) else []:
        aid = a["account"]
        p = pos[pos["account"] == aid] if len(pos) else pos
        closed = p[(p["status"] == "closed") & (p["exit_ms"] >= t0) & (p["exit_ms"] < t1)] if len(p) else p
        reasons = closed["reason"].value_counts().to_dict() if len(closed) else {}
        f = fills[fills["account"] == aid] if len(fills) else fills
        fu = fund[fund["account"] == aid] if len(fund) else fund
        e = eq[eq["account"] == aid] if len(eq) else eq
        e_before = e[e["ts_ms"] <= t0] if len(e) else e
        e_day = e[e["ts_ms"] > t0] if len(e) else e
        start = float(e_before["equity"].iloc[-1]) if len(e_before) else (float(e_day["equity"].iloc[0]) if len(e_day) else math.nan)
        end = float(e_day["equity"].iloc[-1]) if len(e_day) else (float(e_before["equity"].iloc[-1]) if len(e_before) else math.nan)
        cap = float(a["capital"])
        rows.append([aid, len(closed), ", ".join(f"{k} {v}" for k, v in sorted(reasons.items())) or "—",
                     int((closed["pnl"] > 0).sum()) if len(closed) else 0,
                     _n(closed["pnl"].sum() if len(closed) else 0.0), _n(f["fee"].sum() if len(f) else 0.0),
                     _n(fu["amount"].sum() if len(fu) else 0.0), _n(start), _n(end),
                     _n((end / start - 1) * 100 if start and math.isfinite(start) else math.nan, "{:+.2f}%"),
                     _n((end / cap - 1) * 100 if cap else math.nan, "{:+.2f}%")])
    L += _table(["hesap", "kapanan", "nedenler", "kazanan", "net PnL", "ücret", "fonlama", "özs. başı", "özs. sonu",
                 "gün", "başlangıçtan"], rows)
    L += ["", "Net PnL = gün içinde kapanan işlemlerin ücret ve fonlama sonrası sonucu; ücret = o günün dolum "
          "ücretleri; fonlama pozitifse ödendi.", ""]

    # --- kayma ---
    L += ["## Kayma: gerçekleşen vs backtest varsayımı (alıcı dolumları, bps)", ""]
    rows = []
    if len(fills):
        tk = fills[fills["liquidity"] == "taker"]
        for (venue, reason), g in tk.groupby(["venue", "reason"]):
            vt = g["slip_vs_trigger_bps"].dropna()
            rows.append([venue, reason, len(g), _n(g["slippage_bps"].mean()), _n(g["slippage_bps"].max()),
                         _n(g["assumed_slip_bps"].mean()), _n(g["slip_diff_bps"].mean(), "{:+.2f}"),
                         _n(vt.mean()) if len(vt) else "—", _n(g["levels_used"].mean(), "{:.1f}"),
                         int((g["shortfall_qty"].fillna(0) > 0).sum())])
    L += _table(["piyasa", "neden", "dolum", "ort. kayma", "en kötü", "varsayım", "fark", "SL stopa göre",
                 "kademe", "eksik dolum"], rows)
    L += ["", "Kayma = VWAP'ın dolum anındaki orta fiyata göre maliyeti (pozitif = kötü). Fark > 0: backtest "
          "kaymayı olduğundan düşük varsaymış.", ""]
    if len(fills):
        fl = [f for x in fills["flags"].fillna("") for f in str(x).split(",") if f]
        if fl:
            L += ["İşaretli dolumlar: " + ", ".join(f"{k} {v}" for k, v in sorted(pd.Series(fl).value_counts()
                                                                                    .items())) + ".", ""]

    # --- açık pozisyonlar ---
    L += ["## Gün sonunda açık pozisyonlar", ""]
    rows = []
    if len(pos):
        op = pos[(pos["entry_ms"] < t1) & (pos["exit_ms"].isna() | (pos["exit_ms"] >= t1))]
        for r in op.sort_values(["account", "entry_ms"]).to_dict("records"):
            rows.append([r["account"], r["asset"], _utc(r["entry_ms"]), _n(r["p_in"], "{:.6g}"),
                         _n(r["margin"]), _n(r["tp_px"], "{:.6g}"), _n(r["sl_px"], "{:.6g}"),
                         _n(r["liq_px"], "{:.6g}"), _utc(r["deadline_ms"]), _n(r["funding"], "{:.4f}")])
    L += _table(["hesap", "varlık", "giriş", "p_in", "margin", "TP", "SL", "likidasyon", "süre sonu", "fonlama"], rows)
    L += [""]

    # --- olaylar ---
    L += ["## Bağlantı ve hatalar", ""]
    rows = []
    if len(ev):
        for (kind, venue), g in ev.fillna({"venue": "—"}).groupby(["kind", "venue"]):
            extra = ""
            if kind == "gap":
                extra = f"toplam kesinti {sum(json.loads(d).get('down_s', 0) for d in g['detail']):.1f} sn"
            rows.append([kind, venue, len(g), extra])
    L += _table(["olay", "piyasa", "sayı", "not"], rows)
    errs = ev[ev["kind"].isin(ERROR_KINDS)] if len(ev) else ev
    if len(errs):
        L += ["", f"Hatalar (ilk {MAX_LIST}):", ""]
        for r in errs.head(MAX_LIST).to_dict("records"):
            last = (r.get("traceback") or "").strip().splitlines()[-1:] or [""]
            L.append(f"- {_utc(r['ts_ms'])} {r['kind']} {r.get('venue') or ''}: {(r.get('detail') or '')[:160]} "
                     f"{('— ' + last[0][:160]) if last[0] else ''}")
    L += [""]

    # --- tutarlılık ---
    L += ["## Tutarlılık: canlı saatlik kapanış/sinyal vs REST'ten backtest koduyla yeniden hesap", ""]
    if not len(sig):
        L += ["O gün kayıtlı sinyal yok."]
    elif not use_rest or snap is None:
        L += ["Atlandı (REST kapalı veya yapılandırma anlık görüntüsü yok)."]
    else:
        try:
            fetch = fetch or PublicRest().klines
            ref = recompute(sig, snap, fetch, now_ms=now_ms)
            diff = compare(sig[["hour_ms", "venue", "strategy", "asset", "close", "z", "ok", "top"]], ref)
            n_hours = sig.groupby("venue")["hour_ms"].nunique().to_dict()
            L += [f"Karşılaştırılan: {len(sig)} satır ({', '.join(f'{v} {n} saat' for v, n in n_hours.items())}); "
                  f"fark: **{len(diff)}**.", ""]
            if len(diff):
                L += _table(["saat", "piyasa", "strateji", "varlık", "alan", "canlı", "REST"],
                            [[_utc(r["hour_ms"]), r["venue"], r["strategy"], r["asset"], r["field"],
                              _n(r["live"], "{:.10g}"), _n(r["rest"], "{:.10g}")]
                             for r in diff.head(MAX_LIST).to_dict("records")])
                if len(diff) > MAX_LIST:
                    L.append(f"... ve {len(diff) - MAX_LIST} fark daha")
            rec.event(t1, "consistency", None, {"date": day, "n_checked": int(len(sig)), "n_diff": int(len(diff)),
                                                "diffs": diff.head(50).to_dict("records")})
        except Exception as e:  # noqa: BLE001
            L += [f"Atlandı: REST hatası {e!r}"[:300]]
    return L


def main(argv: list[str] | None = None) -> int:
    from trend.data._http import utf8_stdout
    ap = argparse.ArgumentParser(prog="python -m trend.live.report")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (UTC); varsayılan dün")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--no-rest", action="store_true", help="tutarlılık kontrolünü atla (ağ yok)")
    ap.add_argument("--days", type=int, default=1, help="dönem uzunluğu (ör. 7 = haftalık rapor)")
    a = ap.parse_args(argv)
    utf8_stdout()
    date = a.date or (pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    if not Path(a.db).exists():
        raise SystemExit(f"veritabanı yok: {a.db}")
    print("rapor →", build(date, a.db, a.out, use_rest=not a.no_rest,
                           now_ms=int(pd.Timestamp.now(tz="UTC").value // 1_000_000), days=a.days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
