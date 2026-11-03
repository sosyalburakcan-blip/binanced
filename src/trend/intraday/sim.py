"""Gün içi işlem simülatörü: saatlik momentum z-skoru girişleri, 15 dk barlarda TP/SL/süre/likidasyon çıkışları.

Veri: `Market` = tek piyasa (spot veya vadeli), kesintisiz 15 dk barlar (UTC, tz-naive, saat başında başlar).
Saat k = 15 dk barlar [4k, 4k+4); saatlik kapanış C_k = 4k+3 barının kapanışı (bar yoksa NaN). Bar yok = o/h/l/c'den
biri NaN (veya fiyat ≤ 0). `eligible` (T1h × A, nokta zamanlı "bilinen coin" listesi) ve `slip` (T1h × A, taraf başı
kayma kesri) çağırandan gelir.

Kurallar:
1. Sinyal (k saat kapanışı; yalnızca ≤ k verisi): r_k = log(C_k / C_{k−1}); vol_k = std(r_{k−W+1..k}, ddof=1), en az
   W // 2 geçerli r (W = vol_window_h); mom_k = log(C_k / C_{k−L}), L = lookback_h; z_k = mom_k / (vol_k·√L).
   Girdilerden biri yoksa NaN.
2. Takip süresi: ok_k = z_j ≥ z_entry, tüm j ∈ k−confirm_h+1..k (hepsi sonlu).
3. Momentum listesi: eligible[k] ve sonlu z_k olanlar arasında en yüksek z'li n_top varlık. Aday = listede ∧ ok_k ∧
   elde değil; azalan z sırasıyla, boş yuva kaldıkça alınır (slots = en fazla eşzamanlı pozisyon; varlık başına bir).
4. Kontroller: lag_h → k kararı k − lag_h'de hesaplanmış z/ok/listeyi kullanır (> 0 gecikme, < 0 sızıntı = pozitif
   kontrol). random_entries = p → sinyal yerine her uygun varlık-saat p olasılıkla aday (rng ile; sıfır hipotezi),
   öncelik rastgele; TP/SL/süre kuralları aynı.
5. Giriş: 4(k+1) barının (sonraki saatin ilk barı) açılışında; bar yoksa atlanır. p_in = açılış·(1 + slip[k, a]).
   margin = özsermaye / slots (özsermaye = nakit + açık pozisyonlar, giriş anındaki son geçerli kapanışla);
   notional = margin·leverage, qty = notional / p_in; giriş ücreti notional·(taker + tax_per_side) nakitten.
6. Çıkış taraması giriş barından başlar (giriş barında açılış sonrası h/l sayılır). TP = p_in(1+tp), SL = p_in(1−sl),
   likidasyon (yalnızca leverage > 1) = p_in(1 − 1/leverage + mmr). Her barda sırayla:
   a. leverage > 1 ve açılış ≤ likidasyon → açılışta likidasyon: tüm margin + liq_fee·notional kaybı (liq).
   b. düşük ≤ SL (veya açılış ≤ SL) → min(açılış, SL)·(1 − slip), stop-market, taker (sl); leverage > 1 ve SL
      likidasyonun altındaysa önce likidasyon (liq).
   c. değilse yüksek ≥ TP → tam TP fiyatından (limit, kaymasız), maker (tp).
   d. Aynı 15 dk barda hem SL hem TP → önce SL (temkinli); diag["same_bar_ambiguous"] sayar.
   e. Süre: girişten 4·max_hold_h bar geçince o barın açılışı·(1 − slip), taker (time).
   f. Çıkış ücreti = çıkış tutarı·(ücret + tax_per_side). Veri sonu veya `end` → son kapanıştan (end).
   Eksik barlar atlanır (tetik yok, çıkış yok) ama süreye sayılır.
7. Fonlama (mkt.funding varsa): girişten sonraki (giriş barı hariç) ve çıkış barına kadar (dahil) her fonlama ≠ 0
   barının açılışında nakit −= qty·açılış·oran (pozitif oranı uzunlar öder).
8. Pozisyon değeri = margin + qty·(fiyat − p_in) (spot, leverage 1: margin = notional). Günlük NAV her günün son
   15 dk kapanışında; başlangıç 1.0.
9. Spot (funding None) yalnızca leverage == 1.

Varsayımlar (brifin açık bıraktığı yerler):
- start/end gün etiketleridir (ikisi de dahil; None = veri başı/sonu). NAV[start] = 1.0: ilk karar start gününün son
  saat kapanışında, ilk giriş ertesi gün 00:00 (günlük motorun "t kararı, t+1 dolumu" düzeni). Pencere sonu = end
  gününün son barı (veya veri sonu); açık pozisyonlar o ana kadarki son geçerli kapanıştan kapanır. Sinyal ısınması
  start öncesi veriyi kullanır.
- Yuva/varlık meşguliyeti: k kararında çıkış barı ≥ 4(k+1) olan pozisyon hâlâ açık sayılır (o barın açılışındaki
  süre veya boşluk çıkışı dahil); karar böylece k sonrası veriye bakmaz. Aynı saatin girişleri tek özsermaye
  ölçümüyle boyutlanır.
- Nakit eksiye düşmez: margin·(1 + leverage·(taker + tax)) ≤ nakit; aşarsa margin küçültülür
  (diag["margin_capped"]). margin ≤ 0 → giriş atlanır.
- Kayma: bar j'deki dolumda slip[j // 4 − 1] (son tamamlanmış saat; girişle aynı düzen). Giriş saatinde slip NaN →
  giriş atlanır; çıkışta NaN → girişteki kayma.
- Likidasyon maliyeti = margin + notional·(liq_fee + tax_per_side) (vergi diğer çıkışlarla tutarlı); p_out bilgi
  amaçlı min(açılış, likidasyon fiyatı).
- Süre barında (veya süre dolduktan sonraki ilk mevcut barda) yalnızca açılışa bakılır: açılış ≤ likidasyon (liq),
  açılış ≤ SL (sl), açılış ≥ TP (tp, tam TP'den), aksi halde time.
- Açılışta tetiklenen SL (boşluk) belirsiz sayılmaz; giriş barında açılışta likidasyon (a) uygulanmaz ve açılış
  boşluk sayılmaz (pozisyon açılışta kurulur).
- end çıkışı kaymasız, taker + tax ücretli.
- Eşit z'de küçük sütun indeksi önce (kararlı sıralama). vol ≤ 1e-10 (düz fiyat) → z NaN.
- Fonlama NaN = 0; fonlama barı yoksa fiyat = son geçerli kapanış.
- exit_time = çıkış barının açılış zamanı. T15 4'ün katı değilse sondaki eksik saat atılır.
- Bar dizileri gelen dtype'ta (ör. float32) kullanılır; seviyeler float64 karşılaştırılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

BAR = np.timedelta64(15, "m")
DAY = pd.Timedelta(days=1)
VOL_EPS = 1e-10                   # sayısal sıfır oynaklık (düz fiyat; kayan std artığı) → z NaN
REASONS = ("tp", "sl", "time", "liq", "end")
TP, SL, TIME, LIQ, END = range(5)
TRADE_COLUMNS = ["asset", "entry_time", "exit_time", "p_in", "p_out", "reason", "margin", "notional", "qty", "fees",
                 "funding", "pnl", "ret_margin"]


@dataclass
class Market:
    """Tek piyasa (spot veya vadeli); diziler (T15, A), NaN = bar yok."""
    assets: list[str]
    t15: pd.DatetimeIndex
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray  # noqa: E741
    c: np.ndarray
    funding: np.ndarray | None = None      # o barın açılışında uygulanan fonlama oranı; spot için None


@dataclass(frozen=True)
class Params:
    lookback_h: int
    z_entry: float
    confirm_h: int
    tp: float
    sl: float
    max_hold_h: int
    vol_window_h: int = 168
    n_top: int = 3
    slots: int = 3
    leverage: float = 1.0


@dataclass(frozen=True)
class Costs:
    taker: float
    maker: float
    tax_per_side: float = 0.0
    mmr: float = 0.005
    liq_fee: float = 0.0


@dataclass
class Result:
    trades: pd.DataFrame
    nav: pd.Series
    diag: dict = field(default_factory=dict)
    daily: pd.DataFrame | None = None      # gün sonu nakit, pozisyon değeri, açık pozisyon sayısı (nav = cash + pos)


def _as_float(x) -> np.ndarray:
    a = np.asarray(x)
    return a if np.issubdtype(a.dtype, np.floating) else a.astype(np.float64)


def _present(o, h, l, c) -> np.ndarray:  # noqa: E741
    with np.errstate(invalid="ignore"):
        return np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c) & (o > 0) & (c > 0)


def _hourly(c: np.ndarray, pres: np.ndarray) -> np.ndarray:
    return np.where(pres[3::4], c[3::4], np.nan).astype(np.float64)


def hourly_close(mkt: Market) -> np.ndarray:
    """(T1h, A) saatlik kapanış: C_k = 4k+3 barının kapanışı, bar yoksa NaN."""
    T = 4 * (len(mkt.t15) // 4)
    o, h, l, c = (_as_float(x)[:T] for x in (mkt.o, mkt.h, mkt.l, mkt.c))  # noqa: E741
    return _hourly(c, _present(o, h, l, c))


def hourly_signals(C: np.ndarray, eligible: np.ndarray, p: Params) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Kural 1–3: (z, ok, top), hepsi (T1h, A); satır k yalnızca ≤ k kapanışlarından."""
    C = np.asarray(C, dtype=np.float64)
    T1, A = C.shape
    with np.errstate(divide="ignore", invalid="ignore"):
        lc = np.log(np.where(C > 0, C, np.nan))
    r = np.full_like(lc, np.nan)
    r[1:] = lc[1:] - lc[:-1]
    W = int(p.vol_window_h)
    vol = pd.DataFrame(r).rolling(W, min_periods=max(1, W // 2)).std(ddof=1).to_numpy()
    L = int(p.lookback_h)
    mom = np.full_like(lc, np.nan)
    if L < T1:
        mom[L:] = lc[L:] - lc[:-L]
    with np.errstate(divide="ignore", invalid="ignore"):
        z = mom / (vol * np.sqrt(L))
    z[~(np.isfinite(z) & (vol > VOL_EPS))] = np.nan
    n = int(p.confirm_h)
    with np.errstate(invalid="ignore"):
        hit = (z >= p.z_entry).astype(np.int64)        # NaN → 0
    cs = np.cumsum(hit, axis=0)
    win = cs.copy()
    win[n:] -= cs[:-n]
    ok = win == n
    ok[: n - 1] = False
    valid = np.asarray(eligible, dtype=bool)[:T1] & np.isfinite(z)
    order = np.argsort(np.where(valid, -z, np.inf), axis=1, kind="stable")
    rank = np.empty_like(order)
    np.put_along_axis(rank, order, np.broadcast_to(np.arange(A), (T1, A)), axis=1)
    top = valid & (rank < int(p.n_top))
    return z, ok, top


def _shift(x: np.ndarray, lag: int, fill) -> np.ndarray:
    """Satır k = x[k − lag] (dışarısı fill)."""
    out = np.full_like(x, fill)
    T1 = x.shape[0]
    if abs(lag) < T1:
        if lag >= 0:
            out[lag:] = x[: T1 - lag]
        else:
            out[: T1 + lag] = x[-lag:]
    return out


def _check(mkt: Market, p: Params, k: Costs) -> None:
    if mkt.funding is None and float(p.leverage) != 1.0:
        raise ValueError("spot piyasada leverage == 1 olmalı")
    if not float(p.leverage) > 0:
        raise ValueError("leverage > 0 olmalı")
    if min(p.lookback_h, p.confirm_h, p.max_hold_h, p.slots, p.n_top, p.vol_window_h) < 1:
        raise ValueError("lookback_h, confirm_h, max_hold_h, slots, n_top, vol_window_h ≥ 1 olmalı")
    if not (p.tp > 0 and 0 < p.sl <= 1):
        raise ValueError("tp > 0 ve 0 < sl ≤ 1 olmalı")
    if min(k.taker, k.maker, k.tax_per_side, k.mmr, k.liq_fee) < 0:
        raise ValueError("maliyetler negatif olamaz")


def simulate(mkt: Market, eligible, slip, p: Params, k: Costs, start=None, end=None, lag_h: int = 0, rng=None,
             random_entries: float | None = None) -> Result:
    """Tek koşu (bkz. modül notu); start/end gün etiketleri (dahil)."""
    _check(mkt, p, k)
    futures = mkt.funding is not None
    lev = float(p.leverage)
    t15 = pd.DatetimeIndex(mkt.t15)
    A = len(mkt.assets)
    T1 = len(t15) // 4
    T = 4 * T1
    if T1 < 2:
        raise ValueError("en az iki saatlik veri gerekli")
    t15 = t15[:T].as_unit("ns")
    if t15.tz is not None or t15[0] != t15[0].floor("h") or (np.diff(t15.values) != BAR).any():
        raise ValueError("t15 kesintisiz, tz-naive ve saat başında başlayan 15 dk dizi olmalı")
    o, h, l, c = (_as_float(x)[:T] for x in (mkt.o, mkt.h, mkt.l, mkt.c))  # noqa: E741
    if any(x.shape != (T, A) for x in (o, h, l, c)):
        raise ValueError("o/h/l/c (T15, A) olmalı")
    eligible = np.asarray(eligible, dtype=bool)[:T1]
    slip = np.asarray(slip, dtype=np.float64)[:T1]
    if eligible.shape != (T1, A) or slip.shape != (T1, A):
        raise ValueError(f"eligible/slip ({T1}, {A}) olmalı")
    pres = _present(o, h, l, c)
    cf = pd.DataFrame(np.where(pres, c, np.nan)).ffill().to_numpy()      # son geçerli kapanış (değerleme)

    # --- adaylar (saatlik, vektörel) ---
    if random_entries is None:
        z, ok, top = hourly_signals(_hourly(c, pres), eligible, p)
        cand0, prio0 = top & ok, -z
    else:
        if not 0 <= float(random_entries) <= 1:
            raise ValueError("random_entries ∈ [0, 1]")
        u = np.random.default_rng(rng).random((T1, A))        # tüm ızgara: pencereden bağımsız çekiliş
        cand0, prio0 = eligible & (u < float(random_entries)), u
    cand = _shift(cand0, int(lag_h), False)
    prio = np.where(cand, _shift(prio0, int(lag_h), np.inf), np.inf)

    # --- pencere ---
    first_day, last_day = t15[0].normalize(), t15[-1].normalize()
    d0 = first_day if start is None else max(pd.Timestamp(start).normalize(), first_day)
    d1 = last_day if end is None else min(pd.Timestamp(end).normalize(), last_day)
    if d1 < d0:
        raise ValueError("end < start")
    days = pd.date_range(d0, d1, freq="D").as_unit("ns")
    dend = np.asarray(t15.searchsorted(days + DAY), dtype=np.int64) - 1   # her günün son barı
    e_min, Lw = int(t15.searchsorted(d0 + DAY)), int(dend[-1])
    k_lo, k_hi = e_min // 4 - 1, Lw // 4 - 1                               # e = 4(k+1) ∈ [e_min, Lw]
    ks = (np.flatnonzero(cand[k_lo: k_hi + 1].any(axis=1)) + k_lo) if k_hi >= k_lo else np.zeros(0, dtype=np.int64)
    order = np.argsort(prio[ks], axis=1, kind="stable").tolist()
    ncand = cand[ks].sum(axis=1).tolist()

    # --- fonlama (varlık başına sıfır olmayan barlar) ---
    if futures:
        fr = np.nan_to_num(np.asarray(mkt.funding, dtype=np.float64)[:T])
        prev = np.vstack([np.full((1, A), np.nan), cf[:-1]])
        mark = np.nan_to_num(np.where(pres, o, prev))
        fidx = [np.flatnonzero(fr[:, a] != 0) for a in range(A)]
        fmk = [mark[fi, a].astype(np.float64) for a, fi in enumerate(fidx)]
        frt = [fr[fi, a] for a, fi in enumerate(fidx)]

    H4 = 4 * int(p.max_hold_h)
    in_rate = k.taker + k.tax_per_side
    diag = dict.fromkeys(("same_bar_ambiguous", "skipped_no_bar", "skipped_no_slip", "skipped_no_slot",
                          "skipped_no_cash", "margin_capped"), 0)

    def bar_slip(j: int, a: int, s_in: float) -> float:
        s = slip[max(j // 4 - 1, 0), a]
        return float(s) if np.isfinite(s) else s_in

    def scan(a: int, e: int, p_in: float, s_in: float):
        """Kural 6: (çıkış barı, p_out, neden, belirsiz mi)."""
        tp_px = np.float64(p_in * (1.0 + p.tp))
        sl_px = np.float64(p_in * (1.0 - p.sl))
        liq_px = np.float64(p_in * (1.0 - 1.0 / lev + k.mmr)) if lev > 1.0 else np.float64(-np.inf)
        adv = max(sl_px, liq_px)                         # ilk dokunulan olumsuz seviye
        j1 = min(e + H4, Lw + 1)
        with np.errstate(invalid="ignore"):
            dn = l[e:j1, a] <= adv
            up = h[e:j1, a] >= tp_px
        ev = (dn | up) & pres[e:j1, a]
        if ev.any():
            i = int(ev.argmax())
            x = e + i
            oi = float(o[x, a])
            if dn[i]:
                gap = i > 0 and oi <= adv
                amb = bool(up[i]) and not gap
                if liq_px > sl_px or (i > 0 and oi <= liq_px):
                    return x, min(oi, float(liq_px)), LIQ, amb
                return x, min(oi, float(sl_px)) * (1.0 - bar_slip(x, a, s_in)), SL, amb
            return x, float(tp_px), TP, False
        tb = e + H4
        if tb <= Lw:
            if not pres[tb, a]:
                w = pres[tb: Lw + 1, a]
                tb = tb + int(w.argmax()) if w.any() else Lw + 1
            if tb <= Lw:
                ob = float(o[tb, a])
                if ob <= liq_px:
                    return tb, ob, LIQ, False
                if ob <= sl_px:
                    return tb, ob * (1.0 - bar_slip(tb, a, s_in)), SL, False
                if ob >= tp_px:
                    return tb, float(tp_px), TP, False
                return tb, ob * (1.0 - bar_slip(tb, a, s_in)), TIME, False
        return Lw, float(cf[Lw, a]), END, False

    # --- portföy döngüsü (yalnızca adaylı saatler) ---
    fl = np.zeros(T)              # tüm nakit akışları (bar indeksli; NAV için)
    fut = np.zeros(T)             # çalışan nakde henüz eklenmemiş akışlar (çıkış, fonlama)
    cash, ptr = 1.0, 0
    book: list[tuple] = []        # açık: (a, x, qty, margin, p_in)
    held = np.zeros(A, dtype=bool)
    R = {n: [] for n in ("a", "e", "x", "p_in", "p_out", "why", "m", "N", "q", "fees", "fund", "pnl")}
    for kk, row, n in zip(ks.tolist(), order, ncand):
        e = 4 * (kk + 1)
        if book:
            keep = []
            for pos in book:
                if pos[1] < e:
                    held[pos[0]] = False
                else:
                    keep.append(pos)
            book = keep
        free = p.slots - len(book)
        eq = None
        for a in row[:n]:
            if held[a]:
                continue
            if free <= 0:
                diag["skipped_no_slot"] += 1
                continue
            if not pres[e, a]:
                diag["skipped_no_bar"] += 1
                continue
            s_in = float(slip[kk, a])
            if not np.isfinite(s_in):
                diag["skipped_no_slip"] += 1
                continue
            if eq is None:
                cash += float(fut[ptr:e].sum())
                ptr = e
                eq = cash + sum(m_ + q_ * (float(cf[e - 1, a_]) - pi_) for a_, _, q_, m_, pi_ in book)
            m = eq / p.slots
            cap = cash / (1.0 + lev * in_rate)
            if m > cap:
                m = cap
                diag["margin_capped"] += 1
            if not m > 0:
                diag["skipped_no_cash"] += 1
                continue
            p_in = float(o[e, a]) * (1.0 + s_in)
            N = m * lev
            q = N / p_in
            fee_in = N * in_rate
            x, p_out, why, amb = scan(a, e, p_in, s_in)
            diag["same_bar_ambiguous"] += int(amb)
            if why == LIQ:
                fee_out = N * (k.liq_fee + k.tax_per_side)
                v = -fee_out                                  # margin tamamen kaybedilir
            else:
                fee_out = q * p_out * ((k.maker if why == TP else k.taker) + k.tax_per_side)
                v = m + q * (p_out - p_in) - fee_out
            fund = 0.0
            if futures:
                fa = fidx[a]
                lo, hi = int(fa.searchsorted(e, "right")), int(fa.searchsorted(x, "right"))
                if hi > lo:
                    js = fa[lo:hi]
                    amt = q * fmk[a][lo:hi] * frt[a][lo:hi]
                    fl[js] -= amt
                    fut[js] -= amt
                    fund = float(amt.sum())
            cash -= m + fee_in
            fl[e] -= m + fee_in
            fl[x] += v
            fut[x] += v
            book.append((a, x, q, m, p_in))
            held[a] = True
            free -= 1
            for key, val in (("a", a), ("e", e), ("x", x), ("p_in", p_in), ("p_out", p_out), ("why", why), ("m", m),
                             ("N", N), ("q", q), ("fees", fee_in + fee_out), ("fund", fund),
                             ("pnl", v - m - fee_in - fund)):
                R[key].append(val)

    # --- günlük NAV: nakit + açık pozisyonlar (gün sonu barı d, giriş ≤ d < çıkış) ---
    cash_d = 1.0 + np.cumsum(fl)[dend]
    pos_d = np.zeros(len(days))
    nop = np.zeros(len(days), dtype=np.int64)
    n_tr = len(R["a"])
    if n_tr:
        aa, E, X = (np.asarray(R[x], dtype=np.int64) for x in ("a", "e", "x"))
        M, Q, P = (np.asarray(R[x], dtype=np.float64) for x in ("m", "q", "p_in"))
        lo, hi = np.searchsorted(dend, E, "left"), np.searchsorted(dend, X, "left")
        cnt = hi - lo
        tot = int(cnt.sum())
        if tot:
            rep = np.repeat(np.arange(n_tr), cnt)
            dd = lo[rep] + np.arange(tot) - np.repeat(np.cumsum(cnt) - cnt, cnt)
            val = M[rep] + Q[rep] * (cf[dend[dd], aa[rep]].astype(np.float64) - P[rep])
            np.add.at(pos_d, dd, val)
            np.add.at(nop, dd, 1)
    nav = pd.Series(cash_d + pos_d, index=days, name="nav")
    daily = pd.DataFrame({"cash": cash_d, "pos_value": pos_d, "n_open": nop}, index=days)
    t_ns = t15.values
    trades = pd.DataFrame({
        "asset": pd.Series([mkt.assets[a] for a in R["a"]], dtype=object),
        "entry_time": pd.DatetimeIndex(t_ns[np.asarray(R["e"], dtype=np.int64)]),
        "exit_time": pd.DatetimeIndex(t_ns[np.asarray(R["x"], dtype=np.int64)]),
        "p_in": np.asarray(R["p_in"], dtype=np.float64), "p_out": np.asarray(R["p_out"], dtype=np.float64),
        "reason": pd.Series([REASONS[w] for w in R["why"]], dtype=object),
        "margin": np.asarray(R["m"], dtype=np.float64), "notional": np.asarray(R["N"], dtype=np.float64),
        "qty": np.asarray(R["q"], dtype=np.float64), "fees": np.asarray(R["fees"], dtype=np.float64),
        "funding": np.asarray(R["fund"], dtype=np.float64), "pnl": np.asarray(R["pnl"], dtype=np.float64),
    }, columns=TRADE_COLUMNS[:-1])
    trades["ret_margin"] = trades["pnl"] / trades["margin"]
    diag["n_trades"] = n_tr
    diag["n_decision_hours"] = int(len(ks))
    return Result(trades=trades, nav=nav, diag=diag, daily=daily)
