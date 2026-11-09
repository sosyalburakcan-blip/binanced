"""Bağımsız denetim (bot.py içe aktarılmaz): Değişiklik 30 (3) — açık pozisyonda TERS SIÇRAMA kontrolü, KURALLAR.md tanımıyla.
Girdi: live.db spike_checks (botun her dakika açık pozisyon başına yazdığı ölçüm + karar), trades, events spike_error,
gerçek fapi 1 dk mumları (REST'ten sıfırdan).
  1. Ölçüm: hareket = t'de biten 1 dk kapanış / t − 2 dk'da biten kapanış − 1 (gerçek piyasa); botun c_now, c_2, move'u ile aynı mı.
  2. Karar: long hareket ≤ −%0,20, short hareket ≥ +%0,20 → kapat (sold = 1); değilse tut.
  3. Pencere: t − 2 dk ≥ dolum (pencere dolumdan önce başlamamalı).
  4. Kapsam: kapanmış her pozisyon için dolum + 2 dk'dan çıkışa kadar her dakika bir satır olmalı (spike_error olan dakika hariç);
     sold = 1 olan satırdan sonra o pozisyon için satır olmamalı; o işlemin trades sebebi ters_sıçrama olmalı
     (borsadaki kâr al / stop aynı anda dolduysa o sebep kabul edilir).
    /root/binanced/.venv/bin/python /root/binanced/v9live/audit/spike_check.py"""
import json, sqlite3, time
from collections import defaultdict
from datetime import datetime, timezone
import requests

DB = "/root/binanced/v9live/live.db"
M, SPIKE_MS, SPIKE_MAX = 60_000, 120_000, 0.002
S = requests.Session()


def ms(s):
    return int(datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000) + \
        (int(s[20:23]) if len(s) > 20 else 0)


def hm(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%H:%M")


def closes(sym, a, b):
    out, s = {}, a
    while s < b:
        k = S.get("https://fapi.binance.com/fapi/v1/klines", params=dict(symbol=sym, interval="1m", startTime=s, endTime=b - 1,
                                                                          limit=1500), timeout=15).json()
        time.sleep(0.2)
        if not k:
            break
        out.update({int(x[0]) + M: float(x[4]) for x in k})       # anahtar = mumun bittiği an
        s = int(k[-1][0]) + M
    return out


c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
if not c.execute("select 1 from sqlite_master where name = 'spike_checks'").fetchone():
    raise SystemExit("spike_checks tablosu yok (Değ. 30 öncesi)")
rows = c.execute("select ts, sym, side, fill_ms, c_now, c_2, move, sold from spike_checks order by ts").fetchall()
errs = {(json.loads(d).get("sym"), json.loads(d).get("t")) for (d,) in c.execute("select data from events where kind = 'spike_error'")}
tcols = [r[1] for r in c.execute("pragma table_info(trades)")]
trades = {}
if "side" in tcols:
    for sym, fill, ex, reason, side in c.execute("select sym, fill, exit, reason, side from trades where side is not null"):
        trades[(sym, ms(fill))] = (ms(ex), reason, side)
by_pos = defaultdict(list)
for r in rows:
    by_pos[(r[1], r[3])].append(r)
bad, notes, n_sold = 0, [], 0
for (sym, fill), rs in by_pos.items():
    k = closes(sym, rs[0][0] - 4 * M, rs[-1][0] + M)
    sold_at = None
    for ts, _, side, _, cn, c2, mv, sold in rs:
        d = -1 if side == "SHORT" else 1
        a, b = k.get(ts), k.get(ts - SPIKE_MS)
        me = a / b - 1 if a and b else None
        want = me is not None and d * me <= -SPIKE_MAX
        if me is None or abs(me - mv) > 1e-12 or abs(a - cn) > 1e-12 or abs(b - c2) > 1e-12 or bool(sold) != want:
            bad += 1
            notes.append(f"{hm(ts)} {side} {sym} hareket bot {mv:+.4%} / bağımsız {me if me is None else f'{me:+.4%}'} "
                         f"karar bot {sold} / bağımsız {int(want)}")
        if ts - SPIKE_MS < fill:
            bad += 1
            notes.append(f"{hm(ts)} {sym} pencere dolumdan önce başlıyor")
        if sold_at is not None:
            bad += 1
            notes.append(f"{hm(ts)} {sym} kapatma kararından sonra yine ölçüm")
        if sold:
            sold_at, n_sold = ts, n_sold + 1
            notes.append(f"{hm(ts)} {side} {sym} TERS SIÇRAMA {mv:+.3%} → kapat (bağımsız {me:+.3%})")
    tr = next((v for (s_, f_), v in trades.items() if s_ == sym and abs(f_ - fill) < 1000), None)
    if tr:                                                      # kapanmış pozisyon: her dakika bir satır var mı
        ex, reason, side = tr
        first = (fill + SPIKE_MS + M - 1) // M * M
        want_ts = {x for x in range(first, ex // M * M + 1, M) if x <= (sold_at or ex)}
        have = {r[0] for r in rs}
        miss = sorted(x for x in want_ts - have if (sym, x) not in errs and x + 12_000 < ex)
        if miss:
            bad += 1
            notes.append(f"{sym} {hm(fill)} eksik ölçüm dakikaları: {[hm(x) for x in miss[:10]]} ({len(miss)})")
        if sold_at and reason not in ("ters_sıçrama", "kâr_al", "zarar_stop"):
            bad += 1
            notes.append(f"{sym} çıkış sebebi trades {reason} / karar ters_sıçrama")
print(f"ölçüm {len(rows)}, pozisyon {len(by_pos)}, ters sıçramada kapatılan {n_sold}")
for x in notes[-40:]:
    print("  " + x)
print("uyuşmayan:", bad)
