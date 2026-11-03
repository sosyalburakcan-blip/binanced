"""Canlı kâğıt takip kaydı: SQLite (`data/live/live.db`), WAL kipi, toplu yazım.

Tablolar (zamanlar UTC epoch ms; kolonlar `SCHEMA`):
- events: bağlantı/kopma/bayatlık/kesinti/mum boşluğu/hata (traceback ile), başlatma/durdurma, tutarlılık farkları.
- signals: her saat × piyasa × strateji × varlık: kapanış, z, ok, top, uygunluk, faz (warmup/live/late).
- paper_orders: kâğıt emirler (piyasa alış/satış, dinlenen TP limit, SL stop-market); durum güncellemesi = aynı
  order_id ile yeniden yazım.
- fills: dolumlar — vwap, mid, slippage_bps, levels_used, eksik dolum, backtest kayma varsayımı (bps) ve farkı,
  tetik fiyatı, ücret, dolum anındaki defter anlık görüntüsü (JSON).
- positions: pozisyon durumu (açılış, fonlama, kapanış; pos_id ile yeniden yazım).
- equity: hesap başına 15 dk özsermaye anlık görüntüsü. funding: fonlama tahsilatları.
- accounts: hesap tanımları (parametreler JSON). config: başlatmadaki yapılandırma anlık görüntüsü. state: anahtar/değer
  (ör. last_seen_ms — yeniden başlatmada kapalı geçen süre).

Toplu yazım: satırlar bellekte biriktirilir; `batch` satırda veya `flush()` çağrısında tek işlemde yazılır.
Birincil anahtarlı tablolarda INSERT OR REPLACE (son durum kalır); events yalnızca eklenir. NaN/±inf → NULL.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

from trend.config import ROOT

DB_PATH = ROOT / "data" / "live" / "live.db"

SCHEMA: dict[str, tuple[list[str], str]] = {
    "events": (["ts_ms", "venue", "kind", "detail", "traceback"],
               "id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms INTEGER, venue TEXT, kind TEXT, detail TEXT, traceback TEXT"),
    "signals": (["hour_ms", "hour", "venue", "strategy", "asset", "close", "z", "ok", "top", "eligible", "phase", "ts_ms"],
                "hour_ms INTEGER, hour TEXT, venue TEXT, strategy TEXT, asset TEXT, close REAL, z REAL, ok INTEGER, "
                "top INTEGER, eligible INTEGER, phase TEXT, ts_ms INTEGER, PRIMARY KEY (hour_ms, venue, strategy, asset)"),
    "paper_orders": (["order_id", "ts_ms", "account", "strategy", "venue", "leverage", "asset", "side", "type", "qty",
                      "notional", "price", "reason", "status", "pos_id", "updated_ms", "detail"],
                     "order_id TEXT PRIMARY KEY, ts_ms INTEGER, account TEXT, strategy TEXT, venue TEXT, leverage REAL, "
                     "asset TEXT, side TEXT, type TEXT, qty REAL, notional REAL, price REAL, reason TEXT, status TEXT, "
                     "pos_id TEXT, updated_ms INTEGER, detail TEXT"),
    "fills": (["fill_id", "order_id", "pos_id", "ts_ms", "account", "strategy", "venue", "leverage", "asset", "side",
               "reason", "liquidity", "qty", "notional", "vwap", "mid", "slippage_bps", "levels_used", "shortfall_qty",
               "assumed_slip_bps", "slip_diff_bps", "trigger_price", "slip_vs_trigger_bps", "fee", "fee_rate",
               "book_age_ms", "book_json", "flags"],
              "fill_id TEXT PRIMARY KEY, order_id TEXT, pos_id TEXT, ts_ms INTEGER, account TEXT, strategy TEXT, "
              "venue TEXT, leverage REAL, asset TEXT, side TEXT, reason TEXT, liquidity TEXT, qty REAL, notional REAL, "
              "vwap REAL, mid REAL, slippage_bps REAL, levels_used INTEGER, shortfall_qty REAL, assumed_slip_bps REAL, "
              "slip_diff_bps REAL, trigger_price REAL, slip_vs_trigger_bps REAL, fee REAL, fee_rate REAL, "
              "book_age_ms INTEGER, book_json TEXT, flags TEXT"),
    "positions": (["pos_id", "account", "strategy", "venue", "leverage", "asset", "hour_ms", "entry_ms", "p_in", "qty",
                   "margin", "notional", "fee_in", "tp_px", "sl_px", "liq_px", "deadline_ms", "z", "status", "exit_ms",
                   "p_out", "reason", "fee_out", "funding", "exit_flow", "pnl", "flags", "updated_ms"],
                  "pos_id TEXT PRIMARY KEY, account TEXT, strategy TEXT, venue TEXT, leverage REAL, asset TEXT, "
                  "hour_ms INTEGER, entry_ms INTEGER, p_in REAL, qty REAL, margin REAL, notional REAL, fee_in REAL, "
                  "tp_px REAL, sl_px REAL, liq_px REAL, deadline_ms INTEGER, z REAL, status TEXT, exit_ms INTEGER, "
                  "p_out REAL, reason TEXT, fee_out REAL, funding REAL, exit_flow REAL, pnl REAL, flags TEXT, "
                  "updated_ms INTEGER"),
    "equity": (["ts_ms", "account", "strategy", "venue", "leverage", "cash", "pos_value", "equity", "n_open"],
               "ts_ms INTEGER, account TEXT, strategy TEXT, venue TEXT, leverage REAL, cash REAL, pos_value REAL, "
               "equity REAL, n_open INTEGER, PRIMARY KEY (ts_ms, account)"),
    "funding": (["funding_ms", "pos_id", "ts_ms", "account", "asset", "qty", "mark", "rate", "amount", "estimated"],
                "funding_ms INTEGER, pos_id TEXT, ts_ms INTEGER, account TEXT, asset TEXT, qty REAL, mark REAL, "
                "rate REAL, amount REAL, estimated INTEGER, PRIMARY KEY (funding_ms, pos_id)"),
    "accounts": (["account", "strategy", "venue", "leverage", "capital", "params", "created_ms"],
                 "account TEXT PRIMARY KEY, strategy TEXT, venue TEXT, leverage REAL, capital REAL, params TEXT, "
                 "created_ms INTEGER"),
    "config": (["ts_ms", "json"], "ts_ms INTEGER PRIMARY KEY, json TEXT"),
    "state": (["key", "value"], "key TEXT PRIMARY KEY, value TEXT"),
}
APPEND_ONLY = {"events"}
INDEXES = ("CREATE INDEX IF NOT EXISTS ix_events_ts ON events (ts_ms)",
           "CREATE INDEX IF NOT EXISTS ix_fills_ts ON fills (ts_ms)",
           "CREATE INDEX IF NOT EXISTS ix_equity_acc ON equity (account, ts_ms)",
           "CREATE INDEX IF NOT EXISTS ix_positions_acc ON positions (account, status)")


def _clean(v):
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, (dict, list, tuple)):
        return json.dumps(v, default=str, separators=(",", ":"))
    if isinstance(v, bool):
        return int(v)
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):     # numpy skaler
        return _clean(v.item())
    return v


class Recorder:
    def __init__(self, path: Path | str = DB_PATH, batch: int = 2000):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")
        with self.con:
            for t, (_, ddl) in SCHEMA.items():
                self.con.execute(f"CREATE TABLE IF NOT EXISTS {t} ({ddl})")
            for ix in INDEXES:
                self.con.execute(ix)
        self.batch = int(batch)
        self.buf: dict[str, list[tuple]] = defaultdict(list)
        self.n_buf = 0
        self.closed = False

    def add(self, table: str, **row) -> None:
        cols = SCHEMA[table][0]
        unknown = set(row) - set(cols)
        if unknown:
            raise KeyError(f"{table}: bilinmeyen kolon {sorted(unknown)}")
        self.buf[table].append(tuple(_clean(row.get(c)) for c in cols))
        self.n_buf += 1
        if self.n_buf >= self.batch:
            self.flush()

    def event(self, ts_ms: int, kind: str, venue: str | None = None, detail=None, tb: str | None = None) -> None:
        self.add("events", ts_ms=int(ts_ms), venue=venue, kind=kind, detail=detail, traceback=tb)

    def set_state(self, key: str, value) -> None:
        self.add("state", key=key, value=json.dumps(value, default=str))

    def get_state(self, key: str, default=None):
        self.flush()
        r = self.con.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def flush(self) -> None:
        if not self.n_buf or self.closed:
            return
        with self.con:
            for t, rows in self.buf.items():
                if not rows:
                    continue
                cols = SCHEMA[t][0]
                verb = "INSERT" if t in APPEND_ONLY else "INSERT OR REPLACE"
                self.con.executemany(f"{verb} INTO {t} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)
        self.buf.clear()
        self.n_buf = 0

    def rows(self, sql: str, params=()) -> list[dict]:
        self.flush()
        cur = self.con.execute(sql, params)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def close(self) -> None:
        if self.closed:
            return
        self.flush()
        self.con.close()
        self.closed = True
