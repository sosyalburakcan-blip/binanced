"""Bağımsız denetim (bot.py içe aktarılmaz): 5 dk kararlarının ŞART, PUAN, SEÇİM adımları, KURALLAR.md tanımıyla sıfırdan.
Girdi: botun kendi kaydı live.db (scores.feats = karar anındaki ölçümler; ölçümlerin doğruluğu ayrıca verify.py features ile).
  1. Karar düzeni: her 5 dk sınırında bir kayıt, listedeki 30 coin (uni24 ile aynı coinler).
  2. Puan: 6 bileşenin (LC, SMOOTH_4, TAKER_1, IMB1_1, BIDSHARE_1, OI_1) hepsi ölçülen coinler içinde her bileşenin yüzdelik sırası
     (eşitlerde ortalama sıra / n), 6'sının ortalaması.
  3. Şart (Değişiklik 26): puanı var + PİYASA son 30 dk > 0 + LC ≥ 2. Piyasa = o kararın listesindeki coinlerin R30'larının
     (ham son 30 dk) ortalaması, burada coinlerin kaydından yeniden hesaplanır ve botun yazdığı MKT_30 ile karşılaştırılır.
     (Eski şartların — son 4 sa > 0, yükseliş sinyali, Değ. 17–23 — kodu silindi; Değ. 26 öncesi kararlar denetlenmez.)
     Değişiklik 27'den beri (D27_FROM_MS): PİYASA son 30 dk ≥ +%0,10 + R30 > 0 coin sayısı ≥ 20 (ikisi burada coinlerin R30'undan
     yeniden) + son 5 dk (MKT_5) > 0 + tepeden uzaklık (MKT_PEAK) ≥ −%0,10 (bu ikisi botun kaydından; 1 dk yoldan sıfırdan
     hesabı verify.py features yapar) + LC ≥ 2. Değişiklik 28'den beri (D28_FROM_MS) ek olarak son 2 dk (MKT_JUMP, botun kaydından)
     ≤ 0,5 × son 30 dk ortalaması (sıçrama değil).
     Değişiklik 30'dan beri (D30_FROM_MS): YÖN — yukarıdaki şart LONG; aynası (son 30 dk ≤ −%0,10, R30 < 0 coin ≥ 20 [burada
     yeniden], son 5 dk < 0, 30 dk dibine uzaklık MKT_TROUGH ≤ %0,10, son 2 dk ≥ 0,5 × son 30 dk) SHORT; botun scores.side'ı ile
     aynı mı. Şart: LONG'da LC ≥ 2, SHORT'ta LC_DN ≥ 2. Short puanı: LC_DN, −SMOOTH_4, −TAKER_1, −IMB1_1, −BIDSHARE_1, OI_1
     sıra yüzdeleri ortalaması (scores.score_s ile). Seçimde ayrıca coin sıçraması atlanır: long r_t_raw > 0 ve COIN_J_UP >
     0,5 × r_t_raw; short r_t_raw < 0 ve COIN_J_DN < 0,5 × r_t_raw; ölçülemeyen (değerler botun kaydından, verify.py features
     denetler). Engel (labels.block) yalnız long'da.
  4. Seçim: karar başına en çok 1 giriş; yuva = 4 − açık/bekleyen; şartı sağlayanlar puana göre; açık olan, bu turda satılan,
     engelli (labels.block = 1, "short kapatma + spotsuz") atlanır; ilk uygun coin seçilmeli.
     Değişiklik 25'ten beri fiyat adımı / son kapanış (TICK_REL) > %0,1 ya da ölçülemeyen coin de atlanır.
     Borsanın reddettiği giriş (events enter_error, karar anından 60 sn içinde; ör. METUSDT "Leverage 10 is not valid") atlanır.
     Açık/bekleyen: trades (decision < t, exit bu turdan sonra) + dolmadan vazgeçilen girişler (events entry_unfilled)
     + şu an state.json; bu turda satılan = exit [t, t + 60 sn).
    /root/binanced/.venv/bin/python /root/binanced/v9live/audit/decide_check.py [başlangıç_ms bitiş_ms ...]
Varsayılan pencere: Değişiklik 26 yeniden başlatmasından (D26_FROM_MS) şimdiye."""
import json, sqlite3, sys
from datetime import datetime, timezone

DB = "/root/binanced/v9live/live.db"
M5 = 300_000
COMP = ("LC", "SMOOTH_4", "TAKER_1", "IMB1_1", "BIDSHARE_1", "OI_1")
SLOTS, PER_TICK = 4, 1
D26_FROM_MS = 1794105790000   # 08.11 Değişiklik 26 yeniden başlatması 02:43:10 UTC = 05:43 TR
D25_FROM_MS = 1794075199000   # 07.11 Değişiklik 25: fiyat adımı / son kapanış (scores.feats TICK_REL; verify.py features denetler) > %0,1 → girilmez
TICK_MAX_REL = 0.001
D27_FROM_MS = 1794111396000   # 08.11 Değişiklik 27 yeniden başlatması 04:16:36 UTC = 07:16 TR
MKT_MIN, MKT_UP_MIN, MKT_PEAK_MAX = 0.001, 20, 0.001
D28_FROM_MS = 1794112590000   # 08.11 Değişiklik 28 yeniden başlatması 04:36:30 UTC = 07:36 TR
MKT_JUMP_SHARE = 0.5
D30_FROM_MS = int(__import__("os").environ.get("V9_D30_FROM_MS", "1794121293000"))   # 08.11 Değişiklik 30 yeniden başlatması 07:01:33 UTC = 10:01 TR
COMP_S = {"LC_DN": 1, "SMOOTH_4": -1, "TAKER_1": -1, "IMB1_1": -1, "BIDSHARE_1": -1, "OI_1": 1}
COIN_JUMP_SHARE = 0.5


def ms(s):
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f" if "." in s else "%Y-%m-%d %H:%M:%S")
               .replace(tzinfo=timezone.utc).timestamp() * 1000)


def utc(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%H:%M")


def pct_rank(vals: dict) -> dict:
    """eşitlerde ortalama sıra; sıra 1..n, yüzde = sıra / n"""
    xs = sorted(vals.items(), key=lambda kv: kv[1])
    n, out, i = len(xs), {}, 0
    while i < n:
        j = i
        while j + 1 < n and xs[j + 1][1] == xs[i][1]:
            j += 1
        r = (i + 1 + j + 1) / 2
        for k in range(i, j + 1):
            out[xs[k][0]] = r / n
        i = j + 1
    return out


def ok(v, f):
    return v is not None and f(v)


argv = [int(x) for x in sys.argv[1:]]
wins = list(zip(argv[::2], argv[1::2])) if argv else [(D26_FROM_MS, 10**13)]
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
trades = [(r[0], ms(r[1]), ms(r[2]), r[3]) for r in c.execute("select sym, decision, exit, reason from trades")]
# 08.11: botun karar turunda kendisinin sattığı (60 dk kontrolü / ek kontrol; Değ. 30 ters sıçrama karardan hemen önce) = "bu turda
# satılan" (yuva boşalır, coine o tur girilmez). Borsadaki kâr al / stop ise karardan (t + 12 sn) ÖNCE dolduysa yuva boş, SONRA
# dolduysa karar anında hâlâ açıktı (04:10 PEPE kâr al 04:10:31 → eski sürüm yanlışlıkla "boşaldı" sayıyordu).
BOT_EXITS = {"kayan_kontrol", "saatlik_kontrol", "ek_kontrol_kâr", "ek_kontrol_düştü", "ek_kontrol_süre", "ters_sıçrama"}
DECIDE_LAG = 12_000
# dolmadan vazgeçilen girişler (trades'e yazılmaz): karar anından vazgeçme anına kadar yuvayı tutar
unfilled = [(json.loads(d)["sym"], json.loads(d)["decision"], ts) for ts, d in
            c.execute("select ts, data from events where kind = 'entry_unfilled'")]
state = json.load(open("/root/binanced/v9live/state.json"))
rejected = [(ts, json.loads(d)["sym"]) for ts, d in c.execute("select ts, data from events where kind = 'enter_error'")]
bad, n_dec, n_gated, n_chosen, notes = 0, 0, 0, 0, []
for a, b in wins:
    ts = [r[0] for r in c.execute("select distinct ts from scores where ts > ? and ts < ? order by ts", (a, b))]
    if not ts:
        continue
    grid = list(range((a // M5 + 1) * M5, min(b, ts[-1] + 1), M5))
    miss = sorted(set(grid) - set(ts))
    extra = sorted(set(ts) - set(grid))
    print(f"pencere {utc(a)}–{utc(min(b, ts[-1]))} UTC: {len(ts)} karar, 5 dk düzeninde eksik {len(miss)}, düzen dışı {len(extra)}")
    bad += len(miss) + len(extra)
    for t in ts:
        n_dec += 1
        rows = {s: (json.loads(f), g, sc, ch) for s, f, g, sc, ch in
                c.execute("select sym, feats, gated, score, chosen from scores where ts = ?", (t,))}
        d30 = bool(D30_FROM_MS and t >= D30_FROM_MS)
        side_bot = {s: (sd_, ss_) for s, sd_, ss_ in c.execute("select sym, side, score_s from scores where ts = ?", (t,))} if d30 else {}
        uni = {r[0] for r in c.execute("select sym from uni24 where ts = ?", (t,))}
        if uni and set(rows) != uni:
            bad += 1
            notes.append(f"{utc(t)} scores coinleri ≠ liste ({len(rows)} / {len(uni)})")
        full = [s for s, (f, *_r) in rows.items() if all(f.get(k) is not None for k in COMP)]
        ranks = {k: pct_rank({s: rows[s][0][k] for s in full}) for k in COMP}
        score = {s: sum(ranks[k][s] for k in COMP) / len(COMP) for s in full}
        if d30:
            full_s = [s for s in full if rows[s][0].get("LC_DN") is not None]
            ranks_s = {k: pct_rank({s: sg * rows[s][0][k] for s in full_s}) for k, sg in COMP_S.items()}
            score_s = {s: sum(ranks_s[k][s] for k in COMP_S) / len(COMP_S) for s in full_s}
            for s in rows:
                ss_ = side_bot.get(s, (None, None))[1]
                if (s in score_s) != (ss_ is not None) or (s in score_s and abs(score_s[s] - ss_) > 1e-9):
                    bad += 1
                    notes.append(f"{utc(t)} {s} short puanı bot {ss_} / bağımsız {score_s.get(s)}")
        r30 = [f["R30"] for f, *_r in rows.values() if f.get("R30") is not None]
        mkt = sum(r30) / len(r30) if r30 else None
        for s, (f, *_r) in rows.items():
            bm = f.get("MKT_30")
            if (bm is None) != (mkt is None) or (mkt is not None and abs(bm - mkt) > 1e-12) or f.get("MKT_N") != len(r30):
                bad += 1
                notes.append(f"{utc(t)} {s} piyasa bot {bm} ({f.get('MKT_N')} coin) / bağımsız {mkt} ({len(r30)} coin)")
                break
        if D27_FROM_MS and t >= D27_FROM_MS:
            f0 = next(iter(rows.values()))[0]
            up_n = sum(1 for v in r30 if v > 0)
            m5, pk, jp = f0.get("MKT_5"), f0.get("MKT_PEAK"), f0.get("MKT_JUMP")
            for s, (f, *_r) in rows.items():
                if f.get("MKT_UP") != up_n or f.get("MKT_5") != m5 or f.get("MKT_PEAK") != pk or f.get("MKT_JUMP") != jp:
                    bad += 1
                    notes.append(f"{utc(t)} {s} piyasa kaydı coinler arasında farklı / genişlik bot {f.get('MKT_UP')} bağımsız {up_n}")
                    break
            mkt_ok = (mkt is not None and mkt >= MKT_MIN and up_n >= MKT_UP_MIN and m5 is not None and m5 > 0
                      and pk is not None and pk >= -MKT_PEAK_MAX)
            if D28_FROM_MS and t >= D28_FROM_MS:
                mkt_ok = mkt_ok and jp is not None and jp <= MKT_JUMP_SHARE * mkt
        else:
            mkt_ok = mkt is not None and mkt > 0
        side = "LONG" if mkt_ok else None
        if d30 and not mkt_ok:
            dn_n = sum(1 for v in r30 if v < 0)
            trg = f0.get("MKT_TROUGH")
            for s, (f, *_r) in rows.items():
                if f.get("MKT_DN") != dn_n or f.get("MKT_TROUGH") != trg:
                    bad += 1
                    notes.append(f"{utc(t)} {s} short piyasa kaydı farklı / ekside bot {f.get('MKT_DN')} bağımsız {dn_n}")
                    break
            if (mkt is not None and mkt <= -MKT_MIN and dn_n >= MKT_UP_MIN and m5 is not None and m5 < 0 and trg is not None
                    and trg <= MKT_PEAK_MAX and jp is not None and jp >= MKT_JUMP_SHARE * mkt):
                side = "SHORT"
        if d30:
            bs = {v[0] for v in side_bot.values()}
            if bs != {side}:
                bad += 1
                notes.append(f"{utc(t)} yön bot {bs} / bağımsız {side}")
        lck = "LC_DN" if side == "SHORT" else "LC"
        gate = {s for s in full if side and ok(rows[s][0].get(lck), lambda v: v >= 2)}
        sc_use = score_s if side == "SHORT" else score
        n_gated += len(gate)
        for s, (f, g, sc, ch) in rows.items():
            if (s in gate) != bool(g):
                bad += 1
                notes.append(f"{utc(t)} {s} şart bot {g} / bağımsız {int(s in gate)}")
            if (s in score) != (sc is not None) or (s in score and abs(score[s] - sc) > 1e-9):   # long puanı (score sütunu) her zaman
                bad += 1
                notes.append(f"{utc(t)} {s} puan bot {sc} / bağımsız {score.get(s)}")
        sold = {s for s, d, e, r in trades if d < t and t <= e < t + 60_000 and r in BOT_EXITS}   # bu turda satılan (yuvası boşalır)
        held = ({s for s, d, e, r in trades if d < t and (e >= t + 60_000 or (r not in BOT_EXITS and e >= t + DECIDE_LAG))}
                | {s for s, d, e in unfilled if d < t < e}
                | {p["sym"] for p in state if p.get("decision_ms", 0) < t})
        blk = {r[0] for r in c.execute("select sym from labels where ts = ? and block = 1", (t,))} if side != "SHORT" else set()
        free = min(max(SLOTS - len(held), 0), PER_TICK)
        pool = gate
        coarse = {s for s in pool if t >= D25_FROM_MS and not ((rows[s][0].get('TICK_REL') or float('nan')) <= TICK_MAX_REL)}
        rej = {s for ts_, s in rejected if t <= ts_ < t + 60_000}

        def spiky(s):                                   # Değ. 30: son 60 dk tek 2 dk sıçramasından (ya da ölçülemedi)
            f = rows[s][0]
            r, ju, jd = f.get("r_t_raw"), f.get("COIN_J_UP"), f.get("COIN_J_DN")
            if r is None or ju is None or jd is None:
                return True
            return (r > 0 and ju > COIN_JUMP_SHARE * r) if side == "LONG" else (r < 0 and jd < COIN_JUMP_SHARE * r)
        spk = {s for s in pool if d30 and spiky(s)}
        cand = [s for s in sorted(pool, key=lambda s: -sc_use[s])
                if s not in held and s not in sold and s not in blk and s not in coarse and s not in rej and s not in spk]
        want = cand[:free]
        got = [s for s, (_f, _g, _sc, ch) in rows.items() if ch == 1]
        n_chosen += len(got)
        if sorted(got) != sorted(want):
            bad += 1
            notes.append(f"{utc(t)} seçim bot {got} / bağımsız {want} (şartlı {sorted(gate)}, açık {sorted(held)}, engelli {sorted(blk & gate)})")
        elif got:
            notes.append(f"{utc(t)} seçim ✓ {side} {got} (piyasa {mkt:+.3%}, şartlı {len(gate)}, puan {sc_use[got[0]]:.3f}, "
                         f"sıçramalı atlanan {sorted(spk & set(sorted(pool, key=lambda s: -sc_use[s])[:5]))}, "
                         f"açık {sorted(held)})")
print(f"karar {n_dec}, şartı sağlayan coin-karar {n_gated}, girilen {n_chosen}")
for x in notes[:40]:
    print("  " + x)
print("uyuşmayan:", bad)
