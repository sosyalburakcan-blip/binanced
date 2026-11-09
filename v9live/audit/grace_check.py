"""Bağımsız denetim (bot.py içe aktarılmaz): Değişiklik 29 — 60 dk kontrolünün EK SÜRESİ, KURALLAR.md tanımıyla sıfırdan.
Girdi: live.db events kind 'ek_kontrol' (botun her ek-süre kontrolünde yazdığı girdiler + karar), trades (çıkış sebebi),
gerçek fapi 1 dk mumları (son 5 dk REST'ten yeniden).
  1. Girdiler: (b) kâr = demo alış ≥ giriş × 1,0014; (a) yükseliş = son 60 dk (botun r_t'si; r_t'nin kendisini verify.py features
     denetler) ≥ −%0,2; son 5 dk = t'de biten 1 dk kapanış / t − 5 dk'da biten − 1, burada REST'ten sıfırdan, botun r5'iyle aynı mı.
  2. Karar: ek süre dışında (önceki 0): (a)+(b) → tut; (a) + son 5 dk > 0 → tut, ek 1; yoksa sat (kayan_kontrol).
     Ek sürede (önceki k ≥ 1): (b) → sat ek_kontrol_kâr; (a) yok ya da son 5 dk ≤ 0 → sat ek_kontrol_düştü; k ≥ 3 → sat
     ek_kontrol_süre; yoksa tut, ek k + 1.
     Değişiklik 30: SHORT'ta aynası — (b) demo satış (px) ≤ giriş × (2 − 1,0014), (a) son 60 dk ≤ +%0,2, son 5 dk < 0
     (olaydaki side; yoksa long).
  3. Sıra: aynı pozisyonun ek-süre kontrolleri 5 dk arayla, sayaç ardışık; satış kararından sonra o pozisyon için kontrol yok;
     satış kararı verilen pozisyonun trades çıkış sebebi aynı (kâr al / stop önce dolduysa o sebep kabul edilir).
    /root/binanced/.venv/bin/python /root/binanced/v9live/audit/grace_check.py"""
import json, sqlite3, time
from datetime import datetime, timezone
import requests

DB = "/root/binanced/v9live/live.db"
PROTECT, BAND, GRACE_N = 1.0014, 0.002, 3
S = requests.Session()


def close_at(sym, t):
    r = S.get("https://fapi.binance.com/fapi/v1/klines", params=dict(symbol=sym, interval="1m", startTime=t - 6 * 60_000,
                                                                      endTime=t - 1, limit=10), timeout=15).json()
    time.sleep(0.2)
    return {int(k[0]) + 60_000: float(k[4]) for k in r}


def ms(s):
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f" if "." in s else "%Y-%m-%d %H:%M:%S")
               .replace(tzinfo=timezone.utc).timestamp() * 1000)


c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
ev = [json.loads(d) for _, d in c.execute("select ts, data from events where kind = 'ek_kontrol' order by ts")]
trades = {(r[0], ms(r[1])): r[2] for r in c.execute("select sym, fill, reason from trades")}
bad, notes, last = 0, [], {}
for e in ev:
    sym, t = e["sym"], e["t"]
    k = close_at(sym, t)
    r5 = k[t] / k[t - 5 * 60_000] - 1 if t in k and t - 5 * 60_000 in k else None
    d = -1 if e.get("side") == "SHORT" else 1
    px = e.get("px", e["bid"])
    pnl_ok = px >= e["entry"] * PROTECT if d > 0 else 0 < px <= e["entry"] * (2 - PROTECT)
    rise_ok = e["r_t"] is not None and d * e["r_t"] >= -BAND
    up5 = r5 is not None and d * r5 > 0
    g = e["grace_before"]
    if g == 0:
        want = (False, "", 0) if rise_ok and pnl_ok else (False, "", 1) if rise_ok and up5 else (True, "kayan_kontrol", 0)
    else:
        want = ((True, "ek_kontrol_kâr", g) if pnl_ok else (True, "ek_kontrol_düştü", g) if not (rise_ok and up5)
                else (True, "ek_kontrol_süre", g) if g >= GRACE_N else (False, "", g + 1))
    got = (e["sell"], e["why"], e["grace_after"])
    ok_in = (e["pnl_ok"] == pnl_ok and e["rise_ok"] == rise_ok and r5 is not None and e["r5"] is not None
             and abs(e["r5"] - r5) < 1e-12)
    key = (sym, e["fill_ms"])
    prev = last.get(key)
    ok_seq = (prev is None and g == 1 or prev is None and g == 0) or (prev is not None and not prev["sell"]
                                                                       and t - prev["t"] == 300_000 and g == prev["grace_after"])
    last[key] = e
    if got != want or not ok_in or not ok_seq:
        bad += 1
    notes.append(f"{datetime.fromtimestamp(t / 1000, timezone.utc):%H:%M} {e.get('side', 'LONG')} {sym} ek {g}→{e['grace_after']} kâr {'✓' if pnl_ok else '✗'} "
                 f"son60 {'✓' if rise_ok else '✗'} son5 {('%+.3f%%' % (r5 * 100)) if r5 is not None else '-'} (bot "
                 f"{('%+.3f%%' % (e['r5'] * 100)) if e['r5'] is not None else '-'}) → bot {'SAT ' + e['why'] if e['sell'] else 'tut'}"
                 f" / bağımsız {'SAT ' + want[1] if want[0] else 'tut'}{'' if ok_in else ' GİRDİ FARKI'}{'' if ok_seq else ' SIRA HATASI'}")
for (sym, f), e in last.items():
    if e["sell"]:
        tr = [r for (s_, fm), r in trades.items() if s_ == sym and abs(fm - f) < 1000]
        if tr and tr[0] not in (e["why"], "kâr_al", "zarar_stop"):
            bad += 1
            notes.append(f"{sym} çıkış sebebi trades {tr[0]} / karar {e['why']}")
print(f"ek-süre kontrolü {len(ev)}, pozisyon {len(last)}")
for x in notes[-40:]:
    print("  " + x)
print("uyuşmayan:", bad)
