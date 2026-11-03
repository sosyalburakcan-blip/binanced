"""Günlük rapor (trend.live.report): sentetik bir canlı gün (sahte REST) → hesaplar, kayma, açık pozisyonlar, olaylar
ve tutarlılık kontrolü (kayıtlı sinyal = REST'ten backtest koduyla yeniden hesap; bozulan satırlar listelenir).
"""

import json

import pandas as pd
import pytest

from tests._live_common import BAR_MS, H_MS, T0_MS, FakeRest, S1, make_cfg, synth_market
from trend.live import report
from trend.live.paper import LiveRunner
from trend.live.recorder import Recorder
from trend.live.stream import FUT, SPOT, AggTrade, Depth, Sym, SymbolTable

ASSETS = ["AAA", "BBB"]
SYMS = SymbolTable([Sym("AAA", SPOT, "AAAUSDT"), Sym("BBB", SPOT, "BBBUSDT"), Sym("AAA", FUT, "1000AAAUSDT", 1000.0),
                    Sym("BBB", FUT, "BBBUSDT")])
DAY = "2026-01-12"                       # saat 264..287
K0, K1 = 264, 288


@pytest.fixture(scope="module")
def live_day(tmp_path_factory):
    d = tmp_path_factory.mktemp("live")
    mkt = synth_market(K1 + 2, ASSETS, seed=5, drift=[0.0008, -0.0002])
    rest = FakeRest({SPOT: mkt, FUT: mkt}, SYMS)
    now = [T0_MS + K0 * H_MS]
    rr = LiveRunner(make_cfg(strategies=[S1], leverage=[1, 3]), assets=ASSETS, slip={"AAA": 0.0005, "BBB": 0.001},
                    month="2026-01", symbols=SYMS, rest=rest, rec=Recorder(d / "live.db"), now_fn=lambda: now[0],
                    verbose=False)
    rr.broker.restore(now[0])
    rr.rec.add("config", ts_ms=now[0], json=rr.snapshot_json())
    for i in range(4 * K0):
        for venue in (SPOT, FUT):
            for j, a in enumerate(ASSETS):
                rr.on_bar(venue, a, T0_MS + i * BAR_MS, mkt.o[i, j], mkt.h[i, j], mkt.l[i, j], mkt.c[i, j], now[0])
    rr.last_hour = {SPOT: T0_MS + (K0 - 1) * H_MS, FUT: T0_MS + (K0 - 1) * H_MS}
    rr.rec.event(now[0] + 1000, "disconnect", FUT, {"reason": "stale"})
    rr.rec.event(now[0] + 2000, "gap", FUT, {"down_s": 1.5})
    for k in range(K0, K1):
        for i in range(4 * k, 4 * k + 4):
            now[0] = T0_MS + i * BAR_MS + 60_000
            for venue in (SPOT, FUT):
                for j, a in enumerate(ASSETS):
                    for px in (mkt.h[i, j], mkt.l[i, j]):
                        rr.on_event(AggTrade(venue, a, i, float(px), 1.0, 0, False, 0))
                    _depth(rr, venue, a, float(mkt.c[i, j]), i)
                    rr.on_bar(venue, a, T0_MS + i * BAR_MS, mkt.o[i, j], mkt.h[i, j], mkt.l[i, j], mkt.c[i, j], now[0])
            rr.tick(now[0])
        now[0] = T0_MS + (k + 1) * H_MS + 1500
        for venue in (SPOT, FUT):
            for j, a in enumerate(ASSETS):
                _depth(rr, venue, a, float(mkt.c[4 * k + 3, j]), 4 * k + 4)
        rr.tick(now[0])
    rr.rec.flush()
    return d, rr, rest, mkt


def _depth(rr, venue, a, c, uid):
    rr.on_event(Depth(venue, a, uid, ((c * 0.9995, 50.0), (c * 0.999, 1e9)), ((c * 1.0005, 2.0), (c * 1.001, 1e9)), 0))


def _fetch(rest):
    return lambda venue, symbol, interval, s, e: rest.klines(venue, symbol, interval, s, e)


def test_report_sections_and_zero_diffs(live_day):
    d, rr, rest, mkt = live_day
    n_fills = rr.rec.rows("SELECT COUNT(*) AS n FROM fills")[0]["n"]
    assert n_fills > 0
    out = report.build(DAY, d / "live.db", d / "reports", fetch=_fetch(rest), now_ms=2**62)
    md = out.read_text(encoding="utf-8")
    assert out.name == f"{DAY}.md"
    for h in ("## Hesaplar", "## Kayma", "## Gün sonunda açık pozisyonlar", "## Bağlantı ve hatalar", "## Tutarlılık"):
        assert h in md
    for acc in ("s1/spot", "s1/fut1x", "s1/fut3x"):
        assert f"| {acc} |" in md
    assert "fark: **0**" in md and "spot 24 saat" in md and "futures 24 saat" in md
    assert "toplam kesinti 1.5 sn" in md and "| disconnect | futures | 1 |" in md
    assert "| spot | entry |" in md
    ev = rr.rec.rows("SELECT detail FROM events WHERE kind = 'consistency'")
    assert json.loads(ev[-1]["detail"])["n_diff"] == 0


def test_report_lists_differences(live_day, tmp_path):
    d, rr, rest, mkt = live_day
    db = tmp_path / "bad.db"
    src = Recorder(d / "live.db")
    src.con.execute(f"VACUUM INTO '{db.as_posix()}'")
    src.close()
    con = Recorder(db).con
    h = T0_MS + 270 * H_MS
    with con:
        con.execute("UPDATE signals SET close = close * 1.01 WHERE hour_ms = ? AND venue = 'spot' AND asset = 'AAA'",
                    (h,))
        con.execute("UPDATE signals SET ok = 1 - ok WHERE hour_ms = ? AND venue = 'futures' AND asset = 'BBB'", (h,))
    out = report.build(DAY, db, tmp_path / "reports", fetch=_fetch(rest), now_ms=2**62)
    md = out.read_text(encoding="utf-8")
    assert "fark: **2**" in md
    hh = pd.Timestamp(h, unit="ms").strftime("%Y-%m-%d %H:%M")
    assert f"| {hh} | spot | s1 | AAA | close |" in md and f"| {hh} | futures | s1 | BBB | ok |" in md


def test_recompute_matches_live_signals(live_day):
    d, rr, rest, mkt = live_day
    rec = Recorder(d / "live.db")
    sig = pd.DataFrame(rec.rows("SELECT * FROM signals"))
    snap = json.loads(rec.rows("SELECT json FROM config")[0]["json"])
    rec.close()
    ref = report.recompute(sig, snap, _fetch(rest), now_ms=2**62)
    assert len(ref) == len(sig) == 24 * 2 * 2
    assert report.compare(sig[["hour_ms", "venue", "strategy", "asset", "close", "z", "ok", "top"]], ref).empty


def test_report_without_rest(live_day, tmp_path):
    d, *_ = live_day
    out = report.build(DAY, d / "live.db", tmp_path, use_rest=False)
    assert "Atlandı" in out.read_text(encoding="utf-8")
    empty = report.build("2025-01-01", d / "live.db", tmp_path)
    assert "O gün kayıtlı sinyal yok." in empty.read_text(encoding="utf-8")


def test_weekly_period_report(live_day, tmp_path):
    d, rr, rest, mkt = live_day
    out = report.build("2026-01-11", d / "live.db", tmp_path, fetch=_fetch(rest), now_ms=2**62, days=3)
    md = out.read_text(encoding="utf-8")
    assert out.name == "2026-01-11_3g.md" and "2026-01-11 + 3 gün" in md and "fark: **0**" in md
