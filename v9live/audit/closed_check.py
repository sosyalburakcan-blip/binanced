"""Bağımsız denetim (bot.py içe aktarılmaz): KAPANMIŞ işlemlerin ve dolmadan vazgeçilen girişlerin emir adımları, borsa geçmişinden.
Kurallar (KURALLAR.md, Değ. 14/15/18): VOL60 = son 1.500 gerçek 1 dk kapanışla 60 dk getirilerin popülasyon std'si (karar anının 5 dk sınırı);
  hedef adet = aşağı adım(min(1.500 $, 12 $ / VOL60) / ilk emir fiyatı); giriş BUY LIMIT GTX (post-only), fiyat yükselince ≥ 30 sn arayla
  yukarı taşınır, 15 dk'da dolmazsa vazgeçilir; kâr al = yukarı tick(ort. giriş × (1 + VOL60)) SELL LIMIT reduceOnly, adet = dolan;
  zarar stopu = yukarı tick(ort. giriş × (1 − VOL60)) STOP_MARKET closePosition MARK_PRICE, stopta fiyat kaybı ≤ 12 $, ≥ giriş × 0,94;
  60 dk kontrolü: dolumdan 60 dk sonraki ilk 5 dk sınırından itibaren 5 dk'da bir, (a) r_t (uçlar 5 dk ort.) ≥ −%0,2 ve
  (b) demo alış ≥ giriş × 1,0014; biri yoksa piyasa satışı (reduceOnly); kâr = satış − alış − komisyon + fonlama (userTrades, income).
    /root/binanced/.venv/bin/python /root/binanced/v9live/audit/closed_check.py [başlangıç_ms bitiş_ms ...]
Varsayılan: Değişiklik 18 kodunun çalıştığı aralıklar. Sınır: o anki DEMO en iyi alış geçmişe dönük alınamaz (Binance vermez) →
  ilk emir fiyatının "demo en iyi alış" olduğu ve kontroldeki demo alış botun kaydından alınır, yeniden ölçülemez."""
import json, math, sqlite3, sys
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

import requests

sys.path.insert(0, "/root/binanced/v9live/audit")
from demo_sign import g  # noqa: E402  (yalnız imzalı GET, kendi Ed25519 imzası)

REAL, M, H, M5 = "https://fapi.binance.com", 60_000, 3_600_000, 300_000
NOTIONAL, RISK, BAND, PROTECT, TIMEOUT, REPRICE = 1500.0, 12.0, 0.002, 1.0014, 15 * 60_000, 30_000
DB = "/root/binanced/v9live/live.db"
DEG23_MS = int(__import__("os").environ.get("V9_DEG23_MS", "1794067891000"))   # Değ. 23: kâr al net +5 $, zarar stopu yok
MAKER = 0.0002


def ms(s):
    return int(datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000) + \
        (int(s[20:23]) if len(s) > 20 else 0)


def hm(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%H:%M:%S")


def q(x, step, mode):
    return float((Decimal(str(x)) / Decimal(str(step))).to_integral_value(rounding=mode) * Decimal(str(step)))


def closes(sym, a, b):
    out, s = {}, a
    while s < b:
        k = requests.get(REAL + "/fapi/v1/klines", params=dict(symbol=sym, interval="1m", startTime=s, endTime=b - 1,
                                                               limit=1500), timeout=15).json()
        if not k:
            break
        out.update({int(x[0]): float(x[4]) for x in k})
        s = int(k[-1][0]) + M
    return out


def vol60(sym, t):
    t5 = t // M5 * M5
    c = closes(sym, t5 - 1500 * M, t5)
    r = [c[o + H] / c[o] - 1 for o in range(t5 - 1500 * M, t5 - H, M) if o in c and o + H in c]
    mu = sum(r) / len(r)
    return math.sqrt(sum((x - mu) ** 2 for x in r) / len(r))


def r_t(sym, t):
    c = closes(sym, t - 70 * M, t)
    end = [c.get(t - j * M) for j in range(5, 0, -1)]
    beg = [c.get(t - H - j * M) for j in range(5, 0, -1)]
    return sum(end) / 5 / (sum(beg) / 5) - 1 if None not in end + beg else float("nan")


argv = [int(x) for x in sys.argv[1:]]
wins = list(zip(argv[::2], argv[1::2])) if argv else [(ms("2026-11-07 09:15:45"), ms("2026-11-07 11:11:38")),
                                                      (ms("2026-11-07 12:52:05"), 10**13)]
inw = lambda t: any(a < t < b for a, b in wins)  # noqa: E731
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
info = requests.get("https://demo-fapi.binance.com/fapi/v1/exchangeInfo", timeout=15).json()["symbols"]
filt = {s["symbol"]: {f["filterType"]: f for f in s["filters"]} for s in info}
jobs = [("işlem", r[0], ms(r[1]), r) for r in c.execute("select sym, decision, fill, exit, entry, exit_px, qty, cost, value, fees, "
                                                        "funding, pnl, reason, rowid from trades") if inw(ms(r[1]))]
jobs += [("dolmadı", json.loads(d)["sym"], json.loads(d)["decision"], ts) for ts, d in
         c.execute("select ts, data from events where kind = 'entry_unfilled'") if inw(json.loads(d)["decision"])]
bad = 0


def chk(name, ok, detail):
    global bad
    bad += not ok
    print(f"   {'✓' if ok else '✗'} {name}: {detail}")


for kind, sym, dec, row in sorted(jobs, key=lambda j: j[2]):
    fs = filt[sym]
    tick, step = float(fs["PRICE_FILTER"]["tickSize"]), float(fs["LOT_SIZE"]["stepSize"])
    end = ms(row[3]) + 120_000 if kind == "işlem" else row + 60_000
    od = sorted(g("/fapi/v1/allOrders", symbol=sym, startTime=dec - 60_000, endTime=end, limit=500), key=lambda o: o["time"])
    od = [o for o in od if o["time"] >= dec]
    en = [o for o in od if o["clientOrderId"].startswith("v9d-en-")]
    v = vol60(sym, dec)
    print(f"\n{sym} {kind}: karar {hm(dec)} UTC, VOL60 (bağımsız) %{v * 100:.4f}")
    chk("giriş emirleri post-only alış", bool(en) and all(o["side"] == "BUY" and o["type"] == "LIMIT" and o["timeInForce"] == "GTX"
                                                         for o in en), f"{len(en)} emir")
    chk("ilk emir karar anından ≤ 60 sn", bool(en) and en[0]["time"] - dec <= 60_000, f"+{(en[0]['time'] - dec) / 1000:.1f} sn")
    p0 = float(en[0]["price"])
    tq = q(min(NOTIONAL, RISK / v) / p0, step, ROUND_FLOOR)
    chk("hedef adet = min(1.500, 12/VOL60) / fiyat", all(abs(float(o["origQty"]) - tq) < step / 10 for o in en[:1]),
        f"emir {en[0]['origQty']} / bağımsız {tq:g} (≈ {tq * p0:.1f} $)")
    ups = [(float(b["price"]) >= float(a["price"]), (b["time"] - a["time"]) / 1000) for a, b in zip(en, en[1:])]
    chk("takip: fiyat yalnız yukarı, ≥ 30 sn arayla", all(u and dt >= REPRICE / 1000 - 1 for u, dt in ups),
        " → ".join(o["price"] for o in en) + (f" (ara en kısa {min(d for _, d in ups):.0f} sn)" if ups else ""))
    last = max(o["updateTime"] for o in en)
    chk("giriş en geç karar + 15 dk'da biter", last - dec <= TIMEOUT + 30_000, f"son giriş emri {hm(last)} (+{(last - dec) / 60000:.1f} dk)")
    filled = sum(float(o["executedQty"]) for o in en)
    if kind == "dolmadı":
        chk("dolmadı: hiç dolum yok, kâr al/stop konmadı", filled == 0 and not [o for o in od if not o["clientOrderId"].startswith("v9d-en-")],
            f"dolan {filled:g}, diğer emir {len(od) - len(en)}")
        continue
    _, _, fill_s, exit_s, entry, exit_px, qty, cost, value, fees, funding, pnl, reason, rid = row
    fill_ms, exit_ms = ms(fill_s), ms(exit_s)
    ut = g("/fapi/v1/userTrades", symbol=sym, startTime=dec - 60_000, endTime=exit_ms + 60_000, limit=1000)
    eo = {o["orderId"] for o in en}
    buys = [x for x in ut if x["side"] == "BUY" and x["orderId"] in eo]
    sells = [x for x in ut if x["side"] == "SELL" and x["time"] >= fill_ms - 1000]
    bq = sum(float(x["qty"]) for x in buys)
    avg = sum(float(x["quoteQty"]) for x in buys) / bq
    chk("dolan adet = işlem adedi", abs(bq - qty) < step / 10 and abs(filled - bq) < step / 10, f"borsa {bq:g} / bot {qty:g}")
    chk("ortalama giriş", abs(avg - entry) < 1e-9 * avg, f"borsa {avg:.6g} / bot {entry:.6g}")
    tp = [o for o in od if o["clientOrderId"].startswith("v9d-tp-")]
    d23 = fill_ms >= DEG23_MS
    tpw = q((5.0 / bq + avg * (1 + MAKER)) / (1 - MAKER) if d23 else avg * (1 + v), tick, ROUND_CEILING)
    chk("kâr al = yukarı tick(net +5 $: (5/adet + giriş × 1,0002) / 0,9998)" if d23 else "kâr al = yukarı tick(giriş × (1 + VOL60)), azaltmalı, adet = dolan",
        len(tp) == 1 and abs(float(tp[0]["price"]) - tpw) < tick / 10 and tp[0]["reduceOnly"] and abs(float(tp[0]["origQty"]) - bq) < step / 10,
        f"borsa {tp[0]['price'] if tp else None} / bağımsız {tpw:g} (≈ +{(tpw - avg) * bq:.2f} $ fiyat)")
    al = [a for a in g("/fapi/v1/allAlgoOrders", symbol=sym, startTime=dec - 60_000, endTime=exit_ms + 60_000)
          if a["createTime"] >= dec and a["clientAlgoId"].startswith("v9d-")]
    slw = q(avg * (1 - v), tick, ROUND_CEILING)
    zs = [a for a in al if a["clientAlgoId"].startswith(("v9d-zs-", "v9d-es-"))]
    lastz = max(zs, key=lambda a: a["createTime"]) if zs else None   # en son konan (taşınan) stop
    if d23:
        chk("Değ. 23: zarar stopu emri YOK", not zs, f"{len(zs)} stop emri")
    else:
      chk("zarar stopu = yukarı tick(giriş × (1 − VOL60)), STOP_MARKET closePosition MARK_PRICE",
        lastz is not None and abs(float(lastz["triggerPrice"]) - slw) < tick / 10 and lastz["closePosition"]
        and lastz["workingType"] == "MARK_PRICE" and lastz["orderType"] == "STOP_MARKET" and lastz["side"] == "SELL",
        f"borsa {lastz['triggerPrice'] if lastz else None} / bağımsız {slw:g} ({len(zs)} stop emri: "
        + ", ".join(f"{a['clientAlgoId'].split('-')[1]} {a['triggerPrice']} {a['algoStatus']}" for a in zs) + ")")
      chk("stopta fiyat kaybı ≤ 12 $ ve ≥ −%6 tabanı", (avg - slw) * bq <= RISK + 1e-6 and slw >= avg * 0.94,
        f"{(avg - slw) * bq:.2f} $, giriş × {slw / avg:.4f}")
    rows = c.execute("select ts, r_t, bid, rise_ok, pnl_ok, sold from checks where sym = ? and fill_ms = ? order by ts",
                     (sym, fill_ms)).fetchall()
    t1 = -(-(fill_ms + H) // M5) * M5
    if exit_ms < t1:                                   # 60 dk dolmadan kâr al / stop ile çıktı → kontrol olmamalı
        chk("60 dk dolmadan çıktı: kontrol yok", not rows, f"dolum {hm(fill_ms)}, çıkış {hm(exit_ms)}, kontrol {len(rows)}")
    else:
        want = list(range(t1, (rows[-1][0] if rows else t1) + 1, M5))
        last_ok = bool(rows) and (rows[-1][5] == 1 or exit_ms < rows[-1][0] + M5 + 60_000)
        chk("60 dk kontrolü zamanları (dolum + 60 dk sonrası ilk 5 dk sınırı, sonra 5 dk'da bir, satışa ya da çıkışa kadar)",
            bool(rows) and [r[0] for r in rows] == want and last_ok and all(r[5] == 0 for r in rows[:-1]),
            f"dolum {hm(fill_ms)} → kontroller {[hm(r[0])[:5] for r in rows]}, çıkış {hm(exit_ms)}")
    for ts, rt_bot, bid, rise, pok, sold in rows:
        rt = r_t(sym, ts)
        rise_w, pnl_w = rt >= -BAND, bid >= avg * PROTECT
        chk(f"kontrol {hm(ts)[:5]}", abs(rt - rt_bot) < 1e-12 and rise == rise_w and pok == pnl_w and sold == (not (rise_w and pnl_w)),
            f"son 60 dk bağımsız {rt:+.4%} / bot {rt_bot:+.4%} → (a) {'✓' if rise_w else '✗'}; demo alış {bid} vs eşik "
            f"{avg * PROTECT:.6g} → (b) {'✓' if pnl_w else '✗'}; sat {'evet' if sold else 'hayır'}")
    mx = [o for o in od if o["clientOrderId"].startswith("v9d-mx-")]
    if reason in ("kayan_kontrol", "saatlik_kontrol"):
        chk("kontrolde satış: piyasa SELL reduceOnly, kontrolden ≤ 60 sn", len(mx) >= 1 and all(o["type"] == "MARKET" and o["reduceOnly"]
                                                                                      and o["side"] == "SELL" for o in mx)
            and rows and rows[-1][5] == 1 and 0 <= mx[0]["time"] - rows[-1][0] <= 60_000,
            f"{len(mx)} piyasa emri, {hm(mx[0]['time']) if mx else None}")
    sq = sum(float(x["qty"]) for x in sells)
    tp_oid = {int(o["orderId"]) for o in tp}
    if reason == "kâr_al":
        ok_x = all(o["status"] == "FILLED" for o in tp) and all(x["orderId"] in tp_oid and x["maker"] for x in sells)
        why = "kâr al emri doldu (maker), satışların hepsi kâr al emrinden"
    elif reason in ("zarar_stop", "acil_stop"):
        trig = [a for a in zs if a["algoStatus"] not in ("EXPIRED", "CANCELED", "NEW")]
        ok_x = bool(trig) and all(o["status"] in ("CANCELED", "EXPIRED") for o in tp) and min(float(x["price"]) for x in sells) <= \
            float(trig[-1]["triggerPrice"]) * 1.01
        why = f"stop tetiklendi ({trig[-1]['algoStatus'] if trig else '-'}), kâr al iptal"
    else:
        ok_x = all(o["status"] in ("CANCELED", "EXPIRED") for o in tp) and all(a["algoStatus"] in ("EXPIRED", "CANCELED") for a in zs)
        why = "kâr al iptal, stop düştü"
    chk(f"çıkış ({reason}): tüm adet satıldı, {why}", abs(sq - bq) < step / 10 and ok_x,
        f"satılan {sq:g}, kâr al {[o['status'] for o in tp]}, stop {[a['algoStatus'] for a in zs]}")
    inc = g("/fapi/v1/income", symbol=sym, incomeType="FUNDING_FEE", startTime=fill_ms, endTime=exit_ms + 60_000, limit=100)
    fee = sum(float(x["commission"]) for x in buys + sells)
    fund = sum(float(x["income"]) for x in inc)
    pw = sum(float(x["quoteQty"]) for x in sells) - sum(float(x["quoteQty"]) for x in buys) - fee + fund
    chk("net kâr = satış − alış − komisyon + fonlama (borsadan)", abs(pw - pnl) < 1e-6,
        f"borsa {pw:+.4f} $ / bot {pnl:+.4f} $ (komisyon {fee:.4f}, fonlama {fund:+.4f}), sebep {reason}")
print(f"\nuyuşmayan: {bad}")
