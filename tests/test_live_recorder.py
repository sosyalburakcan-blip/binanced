"""Canlı kayıt (trend.live.recorder): WAL kipi, toplu yazım, tablo gidiş-dönüşü, son durum yazımı, NaN → NULL."""

import json
import math
import sqlite3

import pytest

from trend.live.recorder import SCHEMA, Recorder


def test_round_trip_all_tables(tmp_path):
    db = tmp_path / "sub" / "live.db"
    rec = Recorder(db, batch=10_000)
    assert db.exists() and rec.con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    rec.event(1, "connect", "spot", {"attempt": 0}, None)
    rec.event(2, "error", None, {"where": "tick"}, "Traceback ...\nValueError: x")
    rec.add("signals", hour_ms=0, hour="2026-01-01 00:00:00", venue="spot", strategy="s1", asset="AAA", close=1.5,
            z=math.nan, ok=True, top=False, eligible=True, phase="live", ts_ms=3)
    rec.add("paper_orders", order_id="o1", ts_ms=4, account="s1/spot", strategy="s1", venue="spot", leverage=1.0,
            asset="AAA", side="sell", type="limit", qty=2.0, notional=None, price=10.2, reason="tp", status="open",
            pos_id="p1", updated_ms=4, detail=None)
    rec.add("fills", fill_id="f1", order_id="o0", pos_id="p1", ts_ms=5, account="s1/spot", vwap=10.01, mid=10.0,
            slippage_bps=10.0, levels_used=2, assumed_slip_bps=5.0, slip_diff_bps=5.0, book_json={"asks": [[10, 1]]})
    rec.add("positions", pos_id="p1", account="s1/spot", status="open", tp_px=math.inf, sl_px=9.9, qty=2.0)
    rec.add("equity", ts_ms=900_000, account="s1/spot", cash=1.0, pos_value=2.0, equity=3.0, n_open=1)
    rec.add("funding", funding_ms=8, pos_id="p1", ts_ms=9, account="s1/fut1x", asset="AAA", qty=2.0, mark=10.0,
            rate=1e-4, amount=0.002, estimated=False)
    rec.add("accounts", account="s1/spot", strategy="s1", venue="spot", leverage=1.0, capital=1000.0,
            params={"a": 1}, created_ms=0)
    rec.add("config", ts_ms=0, json={"assets": ["AAA"]})
    rec.set_state("last_seen_ms", 123)
    assert rec.rows("SELECT COUNT(*) AS n FROM events")[0]["n"] == 2          # rows() önce yazar
    assert rec.n_buf == 0
    s = rec.rows("SELECT * FROM signals")[0]
    assert s["z"] is None and s["ok"] == 1 and s["top"] == 0 and s["close"] == 1.5
    f = rec.rows("SELECT * FROM fills")[0]
    assert json.loads(f["book_json"]) == {"asks": [[10, 1]]} and f["levels_used"] == 2
    p = rec.rows("SELECT * FROM positions")[0]
    assert p["tp_px"] is None and p["sl_px"] == 9.9                          # ±inf → NULL
    assert json.loads(rec.rows("SELECT params FROM accounts")[0]["params"]) == {"a": 1}
    assert rec.get_state("last_seen_ms") == 123 and rec.get_state("yok", 7) == 7
    ev = rec.rows("SELECT * FROM events ORDER BY id")
    assert [e["kind"] for e in ev] == ["connect", "error"] and ev[1]["traceback"].endswith("ValueError: x")
    rec.close()
    rec.close()                                                               # iki kez kapatma güvenli
    con = sqlite3.connect(db)
    assert {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")} >= set(SCHEMA)
    con.close()


def test_upsert_keeps_latest_state_and_events_append(tmp_path):
    rec = Recorder(tmp_path / "live.db")
    rec.add("positions", pos_id="p1", status="open", funding=0.0)
    rec.add("positions", pos_id="p1", status="closed", funding=0.5, pnl=-1.0)
    rec.event(1, "gap")
    rec.event(1, "gap")
    rec.flush()
    rows = rec.rows("SELECT * FROM positions")
    assert len(rows) == 1 and rows[0]["status"] == "closed" and rows[0]["pnl"] == -1.0
    assert len(rec.rows("SELECT * FROM events")) == 2
    rec.close()


def test_batched_writes_flush_at_threshold(tmp_path):
    rec = Recorder(tmp_path / "live.db", batch=3)
    other = sqlite3.connect(tmp_path / "live.db")
    rec.event(1, "a")
    rec.event(2, "b")
    assert other.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0    # henüz bellekte
    rec.event(3, "c")                                                           # eşik → tek işlemde yazım
    assert other.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3 and rec.n_buf == 0
    other.close()
    with pytest.raises(KeyError):
        rec.add("fills", nonexistent=1)
    rec.close()
