"""Bağımsız denetim: botun `labels` tablosundaki etiketleri Binance'ten SIFIRDAN yeniden hesaplar (bot.py içe aktarılmaz).

    /root/binanced/.venv/bin/python /root/binanced/v9live/audit/label_check.py [db] [ts_ms]
    db: live.db (varsayılan) ya da dry_run.db; ts_ms: dakika (varsayılan: tablodaki son dakika)

Tanımlar (KURALLAR.md "Etiket ve giriş engeli"):
  (06.11 12:45'ten beri kayan pencere: t her dakika; "son saat" = son 60 dk, 1 dk mumlardan)
  r_t          = vadeli kapanış_t / kapanış_{t-60dk} - 1
  OI_1         = açık pozisyon adedi, botun kullandığı 5 dk noktası (scores.feats.OI_TS) / tam 1 sa öncesi - 1
  SPOT_SHARE_1 = spot $ hacmi / vadeli $ hacmi (son 60 dk)
  SPOT_REL_1   = SPOT_SHARE_1 / önceki 168 tam saatin saatlik oran ortancası (t'nin saat başına göre; en az 120 saat)
  engel        = r_t > 0 ve OI_1 < 0 ve SPOT_REL_1 < 1
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import requests

H = 3_600_000
F, S = "https://fapi.binance.com", "https://api.binance.com"
ses = requests.Session()


def get(url, **p):
    r = ses.get(url, params=p, timeout=20)
    return r.json() if r.status_code == 200 else None


def spot_symbol(sym):
    for c in [sym] + ([sym[4:]] if sym.startswith("1000") else []):
        i = get(f"{S}/api/v3/exchangeInfo", symbol=c)
        if i and i.get("symbols") and i["symbols"][0]["status"] == "TRADING":
            return c
    return None


def recompute(sym, t, oi_ts):
    """06.11 12:45'ten beri kayan pencere: t herhangi bir dakika; son 60 dk = 1 dk mumlar [t−60 dk, t)."""
    M = 60_000
    m = get(f"{F}/fapi/v1/klines", symbol=sym, interval="1m", startTime=t - H - M, endTime=t - 1, limit=61)
    m = {int(x[0]): x for x in m}
    out = {"r_t": float(m[t - M][4]) / float(m[t - H - M][4]) - 1}
    fut_qv = sum(float(m[t - j * M][7]) for j in range(1, 61))
    if oi_ts:
        oi = get(f"{F}/futures/data/openInterestHist", symbol=sym, period="5m", startTime=oi_ts - H, endTime=oi_ts)
        v = {int(x["timestamp"]): float(x["sumOpenInterest"]) for x in oi or []}
        if oi_ts in v and oi_ts - H in v:
            out["oi_1"] = v[oi_ts] / v[oi_ts - H] - 1
    sp = spot_symbol(sym)
    if sp:
        sm = get(f"{S}/api/v3/klines", symbol=sp, interval="1m", startTime=t - H, endTime=t - 1, limit=60) or []
        if len(sm) == 60 and fut_qv > 0:
            sq = sum(float(x[7]) for x in sm)
            out["spot_share_1"] = sq / fut_qv
            out["spot_taker_1"] = sum(float(x[10]) for x in sm) / sq if sq > 0 else np.nan
            # taban: t'nin saat başı T için önceki 168 tam saat (açılış o − i sa, o = T − 1 sa), saatlik oran ortancası
            T = t // H * H
            fk = {int(x[0]): x for x in get(f"{F}/fapi/v1/klines", symbol=sym, interval="1h", endTime=T - 1, limit=200)}
            sk = {int(x[0]): x for x in get(f"{S}/api/v3/klines", symbol=sp, interval="1h", endTime=T - 1, limit=200)}
            o = T - H
            hist = [float(sk[a][7]) / float(fk[a][7]) for a in (o - i * H for i in range(1, 169))
                    if a in sk and a in fk and float(fk[a][7]) > 0]
            if len(hist) >= 120 and np.median(hist) > 0:
                out["spot_rel_1"] = out["spot_share_1"] / float(np.median(hist))
    r, oi1, rel = out.get("r_t"), out.get("oi_1"), out.get("spot_rel_1")
    if not r > 0:
        lab = "yukselis_yok"
    else:
        who = "oi_yok" if oi1 is None else ("short_kapatma" if oi1 < 0 else "yeni_alici")
        spot = "spot_olcum_yok" if rel is None or not np.isfinite(rel) else ("spotsuz" if rel < 1 else "spotlu")
        lab = f"{who}+{spot}"
    out["label"] = lab
    out["block"] = int(lab == "short_kapatma+spotsuz")
    return out


def main():
    dbp = Path("/root/binanced/v9live") / (sys.argv[1] if len(sys.argv) > 1 else "live.db")
    db = sqlite3.connect(dbp)
    t = int(sys.argv[2]) if len(sys.argv) > 2 else db.execute("select max(ts) from labels").fetchone()[0]
    cols = [r[1] for r in db.execute("pragma table_info(labels)")]
    rows = [dict(zip(cols, r)) for r in db.execute("select * from labels where ts=?", (t,))]
    feats = {s: json.loads(f) for s, f in db.execute("select sym, feats from scores where ts=?", (t,))}
    bad = 0
    for row in rows:
        oi_ts = feats.get(row["sym"], {}).get("OI_TS")
        me = recompute(row["sym"], t, int(oi_ts) if oi_ts else None)
        diffs = []
        for k in ("r_t", "oi_1", "spot_share_1", "spot_rel_1", "spot_taker_1"):
            a, b = row.get(k), me.get(k)
            a = np.nan if a is None else a
            b = np.nan if b is None else b
            if not ((np.isnan(a) and np.isnan(b)) or np.isclose(a, b, rtol=1e-9, atol=1e-12)):
                diffs.append(f"{k} bot {a:.6g} / denetim {b:.6g}")
        for k in ("label", "block"):
            if row[k] != me[k]:
                diffs.append(f"{k} bot {row[k]} / denetim {me[k]}")
        bad += bool(diffs)
        print(("FARK " if diffs else "OK   ") + f"{row['sym']:13s} {row['label']:28s} engel {row['block']} "
              f"atlandı {row['blocked']} seçildi {row['chosen']}" + ("  | " + "; ".join(diffs) if diffs else ""))
    print(f"{dbp.name} saat {t} ({np.datetime64(t, 'ms')}): {len(rows)} coin, farklı {bad}")


if __name__ == "__main__":
    main()
