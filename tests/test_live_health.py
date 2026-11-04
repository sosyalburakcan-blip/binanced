"""Sağlık kontrolü (trend.live.health): canlılık, eksik/geç kararlar, hatalar ve atlamalar, işlem neden yok
(eşik altı, takip süresi dolmadı, aday var giriş yok), backtest beklemesi ve salt okunur komut satırı (ağ yok).
"""

import pandas as pd

from tests._live_common import H_MS, T0_MS
from trend.live import health
from trend.live.health import BAD, OK, WARN, diagnose, expectations, format_text
from trend.live.recorder import Recorder

S = {"name": "s1", "lookback_h": 6, "z_entry": 2.0, "confirm_h": 3, "tp": 0.04, "sl": 0.04, "max_hold_h": 72}
START = T0_MS + 5 * H_MS + 600_000               # 05:10
NOW = T0_MS + 12 * H_MS + 1_200_000              # 12:20 → 15 dk payla sınırı geçmiş saatler k = 5..11 (B = 06..12)


def _db(tmp_path, zs=None, last_seen=NOW - 3000, skip_hours=(), phase="live", events=(), positions=()):
    """k = 4..11 saatleri × spot/vadeli × AAA/BBB sinyalleri; zs: {(saat, varlık): z} (varsayılan 0.5)."""
    rec = Recorder(tmp_path / "h.db")
    for acc, venue, lev in (("s1/spot", "spot", 1.0), ("s1/fut2x", "futures", 2.0), ("btc_200/spot", "spot", 1.0)):
        rec.add("accounts", account=acc, strategy=acc.split("/")[0], venue=venue, leverage=lev, capital=1000.0,
                params={"strategy": S if acc.startswith("s1") else "btc_200", "venue": venue}, created_ms=START)
    rec.event(START, "start", None, {})
    rec.set_state("last_seen_ms", last_seen)
    for h in range(4, 12):
        if h in skip_hours:
            continue
        for venue in ("spot", "futures"):
            for a in ("AAA", "BBB"):
                z = (zs or {}).get((h, a), 0.5)
                rec.add("signals", hour_ms=T0_MS + h * H_MS, hour=str(h), venue=venue, strategy="s1", asset=a,
                        close=1.0, z=z, ok=bool(z >= 2.0 and (zs or {}).get(("ok", h, a))), top=True, eligible=True,
                        phase=phase, ts_ms=T0_MS + (h + 1) * H_MS)
    for ts, kind, d in events:
        rec.event(ts, kind, "spot", d)
    for i, (entry_ms, status) in enumerate(positions):
        rec.add("positions", pos_id=f"p{i}", account="s1/spot", strategy="s1", venue="spot", leverage=1.0,
                asset="AAA", hour_ms=entry_ms, entry_ms=entry_ms, p_in=1.0, qty=1.0, margin=1.0, notional=1.0,
                fee_in=0.0, status=status, updated_ms=entry_ms)
    rec.flush()
    return rec


def _texts(d):
    return [t for _, t in d["findings"]]


def test_healthy_below_threshold(tmp_path):
    rec = _db(tmp_path, zs={(8, "BBB"): 1.4})
    d = diagnose(rec.rows, NOW, 24)
    assert d["level"] == OK and d["last_seen"] == NOW - 3000
    t = format_text(d)
    assert "TAMAM" in t and "bot çalışıyor, son kayıt 3 sn önce" in t
    assert "spot: son 7 saatin kararları alındı" in t and "vadeli: son 7 saatin kararları alındı" in t
    assert "momentum eşiğe ulaşmadı: en yüksek z 1.40 (BBB" in t and "eşik 2, 3 saat" in t and "hata yok" in t
    assert d["per_strategy"]["s1"]["entries"] == 0 and "btc_200" not in d["per_strategy"]


def test_threshold_crossed_but_not_confirmed(tmp_path):
    rec = _db(tmp_path, zs={(7, "AAA"): 2.5, (8, "AAA"): 2.1, (9, "AAA"): 1.0, (10, "BBB"): 2.2})
    d = diagnose(rec.rows, NOW, 24)
    assert d["level"] == OK and d["per_strategy"]["s1"]["run"] == 2
    assert any("aşıldı ama 3 saat sürmedi: en uzun 2 sa (AAA)" in t for t in _texts(d))


def test_stale_missing_and_late_decisions(tmp_path):
    rec = _db(tmp_path, last_seen=NOW - 10 * 60_000, skip_hours=(7,), phase="late")
    d = diagnose(rec.rows, NOW, 24)
    t = _texts(d)
    assert d["level"] == BAD
    assert any(x.startswith("bot kayıt yazmıyor: son kayıt 10 dk önce") for x in t)
    assert any(x.startswith("spot: 1 saatlik karar eksik") for x in t)
    assert any("karar geç kaldı" in x for x in t)


def test_errors_skips_and_outage(tmp_path):
    ev = [(NOW - H_MS, "connect_error", {"error": "timeout"}), (NOW - 600_000, "gap", {"down_s": 700.0}),
          (NOW - 500_000, "entry_skip", {"why": "no_book"}), (NOW - 400_000, "disconnect", {})]
    d = diagnose(_db(tmp_path, events=ev).rows, NOW, 24)
    t = _texts(d)
    assert d["level"] == WARN
    assert any(x.startswith("bağlantı: 1 kopma, toplam veri kesintisi 11.7 dk") for x in t)
    assert any("connect_error" in x and "timeout" in x for x in t) and any("no_book" in x for x in t)
    d2 = diagnose(_db(tmp_path / "b", events=[(NOW - 60_000, "error", {"error": "ZeroDivisionError"})]).rows, NOW)
    assert d2["level"] == BAD and any("ZeroDivisionError" in x for x in _texts(d2))


def test_candidates_without_entry_and_entries(tmp_path):
    zs = {(9, "AAA"): 2.5, ("ok", 9, "AAA"): True}
    d = diagnose(_db(tmp_path, zs=zs).rows, NOW, 24)
    assert d["level"] == WARN and any("1 aday saat vardı ama giriş yok — incelenmeli" in x for x in _texts(d))
    d2 = diagnose(_db(tmp_path / "b", zs=zs, positions=[(T0_MS + 10 * H_MS, "open")]).rows, NOW, 24)
    assert d2["level"] == OK and any(x.startswith("s1: 1 giriş") for x in _texts(d2))


def test_unfilled_maker_entries_explain_missing_entry(tmp_path):
    zs = {(9, "AAA"): 2.5, ("ok", 9, "AAA"): True}
    ev = [(NOW - 2 * H_MS, "entry_skip", {"account": "s1/spot", "asset": "AAA", "why": "unfilled", "z": 2.5})]
    d = diagnose(_db(tmp_path, zs=zs, events=ev).rows, NOW, 24)
    t = _texts(d)
    assert d["level"] == OK and any("atlanan girişler: {'unfilled': 1}" in x for x in t)
    assert any(x.startswith("s1: 1 aday saat vardı; 1 maker alış emri süresinde dolmadı") for x in t)


def test_expectations_and_idle_beyond_backtest(tmp_path):
    days = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-04", "2025-01-08"])
    pd.DataFrame({"entry_time": days}).to_parquet(tmp_path / "s1.parquet")
    ex = expectations(["s1", "yok"], tmp_path)
    assert list(ex) == ["s1"] and ex["s1"]["gap_max_d"] == 4.0 and ex["s1"]["gap_med_d"] == 2.0
    assert ex["s1"]["per_week"] == 4.0 and ex["s1"]["last_entry"] == "2025-01-08 00:00"
    d = diagnose(_db(tmp_path).rows, START + 5 * 86_400_000, 24, ex)
    s = next(x for x in _texts(d) if x.startswith("s1:"))
    assert "Backtest: haftada 4.0 giriş" in s and "en uzun 4 gün" in s and "backtestteki en uzun beklemeyi aştı" in s


def test_cli_read_only(tmp_path, capsys, monkeypatch):
    rec = _db(tmp_path)
    rec.close()
    monkeypatch.setattr(health.time, "time", lambda: NOW / 1000)
    code = health.main(["--db", str(tmp_path / "h.db")])
    out = capsys.readouterr().out
    assert code == OK and out.startswith("🩺 Sağlık kontrolü") and "momentum eşiğe ulaşmadı" in out
