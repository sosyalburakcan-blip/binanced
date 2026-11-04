"""Telefon bildirimi (trend.live.notify) ve kâğıt çalıştırıcıya bağlanışı: anahtar dosyası, kanallar, gönderim
(sahte HTTP, ağ yok), yeniden deneme yalnızca ağ/429/5xx, anahtar maskeleme, birleştirme, kısıtlama, giriş/çıkış
mesajları, veri kesintisi uyarısı ve günlük özet.
"""

import json
import urllib.parse

import pytest

from tests._live_common import H_MS, T0_MS
from tests.test_live_paper import _books, _runner
from trend.live.notify import (TELEGRAM, WHATSAPP, Notifier, channels, find_chat_id, http_request, load_creds, pack,
                               save_chat_id, send_one)
from trend.live.paper import Position, trade_text
from trend.live.stream import FUT, SPOT, AggTrade, Depth

TOKEN = "123456:ABCdefSECRET"
KEY = "998877"
PHONE = "+905551112233"
ALL = {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "42", "WHATSAPP_PHONE": PHONE, "CALLMEBOT_APIKEY": KEY}


class FakeHttp:
    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.calls: list[tuple] = []

    def __call__(self, url, data=None, timeout=20.0):
        self.calls.append((url, data))
        r = self.replies.pop(0) if self.replies else None
        if isinstance(r, Exception):
            raise r
        if r is not None:
            return r
        if "telegram" in url:
            return 200, json.dumps({"ok": True})
        return 200, "Message queued. You will receive it in a few seconds."


def _write(path, creds):
    path.write_text("# yorum\n" + "".join(f"{k}={v}\n" for k, v in creds.items()), encoding="utf-8")
    return path


# --- anahtar dosyası ve kanallar ---

def test_load_creds_parses_comments_quotes_and_ignores_unknown(tmp_path):
    p = tmp_path / ".env.bildirim"
    p.write_text('﻿# baş\nTELEGRAM_BOT_TOKEN="abc:def"  # yorum\nTELEGRAM_CHAT_ID=\nBINANCE_API_KEY=xyz\n'
                 "WHATSAPP_PHONE = +90555\nCALLMEBOT_APIKEY='77'\nbozuk satır\n", encoding="utf-8")
    c = load_creds(p)
    assert c == {"TELEGRAM_BOT_TOKEN": "abc:def", "WHATSAPP_PHONE": "+90555", "CALLMEBOT_APIKEY": "77"}
    assert channels(c) == [WHATSAPP]
    assert channels({**c, "TELEGRAM_CHAT_ID": "1"}) == [TELEGRAM, WHATSAPP]
    assert load_creds(tmp_path / "yok") == {} and channels({}) == []


def test_http_request_only_allowed_hosts():
    for url in ("https://api.binance.com/api/v3/order", "http://api.telegram.org/x", "https://evil.com/?h=api.telegram.org"):
        with pytest.raises(ValueError):
            http_request(url)


# --- tek gönderim ---

def test_send_one_telegram_and_whatsapp_requests():
    http = FakeHttp()
    assert send_one(TELEGRAM, ALL, "merhaba", http)[0]
    url, data = http.calls[0]
    assert url == f"https://api.telegram.org/bot{TOKEN}/sendMessage" and data["chat_id"] == "42"
    assert data["text"] == "merhaba"
    assert send_one(WHATSAPP, ALL, "kâr +5$ & çıkış", http)[0]
    url, data = http.calls[1]
    u = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qs(u.query)
    assert u.hostname == "api.callmebot.com" and data is None
    assert q == {"phone": [PHONE], "text": ["kâr +5$ & çıkış"], "apikey": [KEY]}
    assert "%2B90" in url                                                          # + kodlanır


def test_send_one_failure_and_retry_flags():
    http = FakeHttp([(200, json.dumps({"ok": False})), (429, "{}"), (502, "x"), (400, "{}"),
                     (200, "APIKey is invalid"), (200, "Account is Paused")])
    assert send_one(TELEGRAM, ALL, "a", http)[:2] == (False, False)
    assert send_one(TELEGRAM, ALL, "a", http)[:2] == (False, True)
    assert send_one(TELEGRAM, ALL, "a", http)[:2] == (False, True)
    assert send_one(TELEGRAM, ALL, "a", http)[:2] == (False, False)
    assert send_one(WHATSAPP, ALL, "a", http)[:2] == (False, False)
    assert send_one(WHATSAPP, ALL, "a", http)[:2] == (False, False)


def test_pack_joins_splits_and_truncates():
    assert pack(["a", "b"], 100) == ["a\n\nb"]
    assert pack(["x" * 6, "y" * 6], 10) == ["x" * 6, "y" * 6]
    assert pack(["z" * 20], 10) == ["z" * 9 + "…"]
    assert pack([], 10) == []


# --- gönderici ---

def _notifier(tmp_path, creds=ALL, http=None, **kw):
    sleeps = []
    n = Notifier(_write(tmp_path / ".env.bildirim", creds), http=http or FakeHttp(), sleep=sleeps.append,
                 start=False, **kw)
    return n, sleeps


def test_deliver_all_channels_with_header(tmp_path):
    http = FakeHttp()
    n, _ = _notifier(tmp_path, http=http, header="📄 kâğıt")
    assert n.deliver(["bir", "iki"]) == 2
    tg = http.calls[0][1]["text"]
    wa = urllib.parse.parse_qs(urllib.parse.urlsplit(http.calls[1][0]).query)["text"][0]
    assert tg == wa == "📄 kâğıt\nbir\n\niki"
    assert n.stats["sent_telegram"] == 1 and n.stats["sent_whatsapp"] == 1


def test_retry_only_transient_and_errors_are_scrubbed(tmp_path):
    http = FakeHttp([OSError(f"bağlantı koptu {TOKEN}"), (503, "x"), (200, json.dumps({"ok": True})),
                     (400, f"bad apikey={KEY} phone={urllib.parse.quote_plus(PHONE)}")])
    n, sleeps = _notifier(tmp_path, http=http)
    assert n.deliver(["m"]) == 1
    assert sleeps == [5.0, 30.0] and len(http.calls) == 4                          # TG 3 deneme, WA 400 → tek
    errs = n.drain_errors()
    assert len(errs) == 1 and errs[0]["channel"] == WHATSAPP and errs[0]["attempts"] == 1
    assert KEY not in errs[0]["info"] and "905551112233" not in errs[0]["info"] and "***" in errs[0]["info"]
    http2 = FakeHttp([OSError(f"x {TOKEN}")] * 3)
    n2, _ = _notifier(tmp_path, creds={k: ALL[k] for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}, http=http2)
    assert n2.deliver(["m"]) == 0
    assert TOKEN not in n2.drain_errors()[0]["info"]


def test_no_channel_sends_nothing_and_reloads_file(tmp_path):
    http = FakeHttp()
    clock = [0.0]
    p = tmp_path / ".env.bildirim"
    p.write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")
    n = Notifier(p, http=http, start=False, clock=lambda: clock[0], reload_s=60.0)
    assert n.deliver(["a"]) == 0 and http.calls == [] and n.stats["no_channel"] == 1
    _write(p, {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "42"})
    clock[0] = 30.0
    assert n.deliver(["b"]) == 0                                                  # henüz yeniden okunmadı
    clock[0] = 61.0
    assert n.deliver(["c"]) == 1 and len(http.calls) == 1


def test_send_throttle_by_key(tmp_path):
    clock = [0.0]
    n = Notifier(tmp_path / "yok", start=False, clock=lambda: clock[0])
    assert n.send("e1", key="err", every_s=1800)
    clock[0] = 100.0
    assert not n.send("e2", key="err", every_s=1800) and n.send("diğer")
    clock[0] = 1801.0
    assert n.send("e3", key="err", every_s=1800)
    assert n.stats["throttled"] == 1 and n._q.qsize() == 3


def test_worker_batches_and_close_flushes(tmp_path):
    http = FakeHttp()
    n = Notifier(_write(tmp_path / ".env.bildirim", {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "42"}),
                 http=http, batch_s=0.3)
    for t in ("bir", "iki", "üç"):
        n.send(t)
    n.close(timeout=5)
    assert len(http.calls) == 1 and http.calls[0][1]["text"] == "bir\n\niki\n\nüç"
    assert not n._thread.is_alive()


def test_find_and_save_chat_id(tmp_path):
    upd = {"ok": True, "result": [{"update_id": 1, "message": {"chat": {"id": 111}}},
                                  {"update_id": 2, "message": {"chat": {"id": 222}, "text": "/start"}}]}
    http = FakeHttp([(200, json.dumps(upd)), (200, json.dumps({"ok": True, "result": []}))])
    assert find_chat_id(TOKEN, http) == "222" and "getUpdates" in http.calls[0][0]
    assert find_chat_id(TOKEN, http) is None
    p = tmp_path / ".env.bildirim"
    p.write_text("TELEGRAM_BOT_TOKEN=x\nTELEGRAM_CHAT_ID=\nWHATSAPP_PHONE=\n", encoding="utf-8")
    save_chat_id(p, "222")
    assert load_creds(p) == {"TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "222"}
    q = tmp_path / "b.env"
    q.write_text("TELEGRAM_BOT_TOKEN=x", encoding="utf-8")
    save_chat_id(q, "7")
    assert load_creds(q)["TELEGRAM_CHAT_ID"] == "7"


# --- çalıştırıcıya bağlanış ---

class SpyNotifier:
    def __init__(self):
        self.sent: list[str] = []
        self.errors = [{"channel": "telegram", "info": "500 x"}]

    def send(self, text, key=None, every_s=0.0):
        self.sent.append(text)
        return True

    def drain_errors(self):
        out, self.errors = self.errors, []
        return out


def test_trade_text_entry_exit_and_baseline():
    class A:
        acc_id, venue, lev = "s1/fut2x", FUT, 2.0
    p = Position("p1", "s1/fut2x", "s1", FUT, 2.0, "SOLUSDT", 0, 0, 100.0, 6.0, 300.0, 600.0, 0.3, tp_px=104.0,
                 sl_px=96.0, liq_px=51.0, deadline_ms=72 * H_MS)
    s = trade_text("entry", A, p, slip_bps=1.23)
    assert s.startswith("🟢 GİRİŞ s1/fut2x SOLUSDT @ 100") and "600$ 2×" in s and "kayma 1.2bps" in s
    assert "kâr al 104" in s and "zarar kes 96" in s and "likidasyon 51" in s and "en geç 04.01 03:00" in s
    p.status, p.exit_ms, p.p_out, p.reason, p.fee_out, p.pnl, p.funding = "closed", 5 * H_MS, 104.0, "tp", 0.12, 23.58, 0.0
    s = trade_text("exit", A, p)
    assert s.startswith("✅ ÇIKIŞ s1/fut2x SOLUSDT kâr al @ 104") and "+23.58$ (+7.9%)" in s and "5.0 sa" in s
    p.pnl, p.reason, p.flags = -12.0, "sl", "offline"
    assert trade_text("exit", A, p).startswith("🔴 ÇIKIŞ s1/fut2x SOLUSDT zarar kes") and "kapalıyken" in trade_text("exit", A, p)

    class Bsp:
        acc_id, venue, lev = "btc_200/spot", SPOT, 1.0
    b = Position("p2", "btc_200/spot", "btc_200", SPOT, 1.0, "BTCUSDT", 0, 0, 77822.7, 0.0128, 999.0, 999.0, 1.0)
    s = trade_text("entry", Bsp, b, slip_bps=0.0)
    assert "BTCUSDT @ 77822.7" in s and "×" not in s and "kâr al" not in s


def test_runner_sends_entry_exit_feed_and_summary(tmp_path):
    k = 250
    rr, mkt, now = _runner(tmp_path, k)
    spy = SpyNotifier()
    rr.notifier = spy
    _books(rr, mkt, 4 * k + 3)
    rr.tick(now[0])
    entries = [m for m in spy.sent if m.startswith("🟢 GİRİŞ")]
    assert entries and any("s1/spot AAA" in m for m in entries) and any("s1/fut2x AAA" in m for m in entries)
    assert rr.rec.rows("SELECT * FROM events WHERE kind = 'notify_error'")[0]["venue"] is None
    ps = rr.broker.accounts["s1/spot"].positions["AAA"]
    rr.on_event(AggTrade(SPOT, "AAA", 1, ps.tp_px * 1.0001, 1.0, 0, False, 0))
    assert spy.sent[-1].startswith("✅ ÇIKIŞ s1/spot AAA kâr al")
    # veri kesintisi: 5 dk mesaj yok → bir uyarı; tekrar yok; mesaj gelince bir bilgi
    t0 = rr.last_msg[SPOT]
    n0 = len(spy.sent)
    rr.check_feeds(t0 + 301_000)
    rr.check_feeds(t0 + 400_000)
    new = spy.sent[n0:]
    assert len(new) == 2 and new[0].startswith("⚠️ spot verisi 5 dk") and new[1].startswith("⚠️ vadeli verisi 5 dk")
    now[0] = t0 + 420_000
    c = float(mkt.c[4 * k + 3, 1])
    rr.on_event(Depth(SPOT, "BBB", 2, ((c * 0.9999, 1e9),), ((c * 1.0001, 1e9),), 0))
    rr.check_feeds(now[0])
    assert any(m.startswith("✅ spot verisi geri geldi (7 dk") for m in spy.sent)
    # günlük özet: hesap başına özsermaye, son özetten beri sayılar
    rr.n_disconnect = 3
    s = rr.summary_text(now[0])
    assert s.startswith("📊 Günlük özet") and "s1: spot" in s and "2× " in s
    assert f"{rr.broker.stats['entries']} giriş, 1 çıkış, 3 bağlantı kopması" in s
    assert "0 giriş, 0 çıkış, 0 bağlantı kopması" in rr.summary_text(now[0])
    # saatlik işler: yapılandırılan UTC saatinde özet gönderilir
    rr._next_hourly = None
    day = (now[0] // (24 * H_MS) + 1) * 24 * H_MS
    rr.hourly_chores(day + 5 * H_MS)
    rr.hourly_chores(day + 6 * H_MS + 1000)
    assert spy.sent[-2].startswith("📊 Günlük özet") and spy.sent[-1].startswith("🩺 Sağlık kontrolü")
    # saatlik karar gecikmesi: bir uyarı, saatte en fazla bir
    n1 = len(spy.sent)
    late = max(rr.last_hour.values()) + 2 * H_MS + 20 * 60_000
    rr.last_msg = {}
    rr.check_feeds(late)
    assert any("saatlik kararı 20 dk gecikti" in m for m in spy.sent[n1:])


def test_runner_without_notifier_is_silent(tmp_path):
    rr, mkt, now = _runner(tmp_path, 250)
    assert rr.notifier is None
    _books(rr, mkt, 4 * 250 + 3)
    rr.tick(now[0])
    rr.check_feeds(now[0] + 10 * H_MS)
    assert rr.broker.stats["entries"] > 0 and T0_MS < now[0]
