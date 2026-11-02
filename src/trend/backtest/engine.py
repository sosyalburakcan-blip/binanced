"""Olay sıralı günlük backtest motoru (SPEC "Backtest motoru", CONTRACTS §1).

Günlük döngü (t günü):
  1. t−1 kararının emirlerini t gününün dolum penceresi fiyatından gerçekleştir (önce satışlar; nakit yetmezse
     alımlar orantılı küçültülür; nakit asla negatif olmaz)
  2. Delist kuralı (son mum günü → o günün VWAP'ı × (1 − ceza)); boşluk kuralı (son fiyat taşınır, işlem yok)
  3. t kapanışında değerleme: nakit (+ nakit getirisi) + Σ adet × son kapanış
  4. Evren: t kararı ay(t+1) evrenini kullanır (sağlayıcı)
  5. Karar: yalnızca ≤ t verisiyle hedef ve emirler; adet = Δw · base(t) / C(t)

Portföy için vektörel kısayol yoktur; göstergeler nedensel olarak önceden hesaplanır (bkz. interface.py).

Varsayımlar (SPEC'in açık bıraktığı yerler):
- Komisyon nakit (USDT) olarak, gerçekleşen işlem tutarı (kayma dahil fiyat × adet) üzerinden alınır.
- `cost_multiplier` (T6) komisyon, kayma ve delist cezasını çarpar ("tüm maliyetler").
- Delist kapanışı: fiyat = son günün dolum penceresi VWAP'ı; yoksa o günün günlük VWAP'ı (quote_volume/volume); o da
  yoksa son kapanış ("son fiyattan"). × (1 − ceza), üstüne komisyon; kayma ayrıca uygulanmaz.
- Dolum fiyatı yoksa (pencerede ve mum sonuna kadar hacim yok, veya boşluk) emir o gün gerçekleşmez ve düşer;
  ertesi günün kararı yeniden üretir.
- Küsürat: tam çıkışın tutarı minimum emrin (10 USDT) altındaysa satılamaz ve değeri sıfırlanır (kötümser,
  `dust_zero`). Çıkış dışı emirler: karar anında |Δw|·base < 10 USDT ise atlanır; orantılı küçültme sonrası 10 USDT
  altına düşen alımlar atlanır.
- Nakit getirisi her takvim günü (ilk gün hariç) dolumlardan sonraki nakit üzerinden yıllık oran/365 ile işler.
- −%35 sert sınır (varsayılan açık; kıyaslarda kapalı): durdurulmuşken pozisyonu artıran tüm emirler atlanır.
- Sabit tutarlı büyüklükte base = başlangıç sermayesi (kâr yeniden yatırılmaz; zarar halinde alımları nakit sınırlar).
- Orantılı küçültme dolum anında, gerçek dolum fiyatlarıyla yapılır (satış gelirleri eklendikten sonra).
- Dolum defterindeki `post_weight` = dolum gününün kapanışındaki ağırlık.
- Evrendeki üye listesi tüm koşu için önceden okunur, yalnızca izlenecek sütunları (varlık kümesi) seçmek içindir;
  t kararı yalnızca ay(t+1) tablosunu kullanır. Varlık kümesinin değişmesi t'ye kadarki kararları değiştirmez
  (zorunlu test 1 hem sabit hem otomatik kümeyle bayt düzeyinde doğrular).
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from trend.backtest.fills import fill_prices_from_settings
from trend.backtest.interface import DayView, EngineData
from trend.backtest.ledger import DECISION_COLUMNS, FILL_COLUMNS, build_cycles
from trend.backtest.providers import daily_cash_rate, default_slippage, universe_arrays
from trend.backtest.rules import HardStop
from trend.config import _deep_update, load_settings
from trend.strategy.rebalance import EXIT, REASON_NAMES, SKIP_HARDSTOP, SKIP_MINORDER, mintrade
from trend.strategy.system import BTC_ASSET, TrendStrategy

# TODO(settings): backtest.tbill_haircut — "hazine bonosu − 1,5 puan" duyarlılığındaki indirim.
TBILL_HAIRCUT = 0.015


@dataclass
class BacktestResult:
    daily: pd.DataFrame
    weights: pd.DataFrame | None
    fills: pd.DataFrame
    cycles: pd.DataFrame
    decisions: pd.DataFrame
    cfg: dict
    meta: dict = field(default_factory=dict)

    @property
    def nav(self) -> pd.Series:
        return self.daily["nav"]

    def returns(self) -> pd.Series:
        """Günlük basit getiri; ilk gün başlangıç sermayesine göre (daily['ret'])."""
        return self.daily["ret"]


def resolve_settings(settings: dict | None = None, overrides: dict | None = None) -> dict:
    """settings (yüklenmiş) + overrides (iç içe) → yeni sözlük; ikisi de yoksa load_settings()."""
    cfg = copy.deepcopy(settings) if settings is not None else load_settings()
    if overrides:
        _deep_update(cfg, copy.deepcopy(overrides))
    return cfg


def _ns(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame.copy()
    f.index = pd.DatetimeIndex(f.index).as_unit("ns")
    f.columns = [str(c) for c in f.columns]
    return f.sort_index()


def run_backtest(
    panel_1d: dict[str, pd.DataFrame],
    *,
    universe,
    strategy=None,
    panel_1h: dict[str, pd.DataFrame] | None = None,
    fill_px: pd.DataFrame | None = None,
    delist: pd.DataFrame | None = None,
    cash_rate: pd.Series | None = None,
    quality_flags: pd.DataFrame | None = None,
    settings: dict | None = None,
    overrides: dict | None = None,
    start=None,
    end=None,
    sizing: str = "compound",
    hard_stop: bool = True,
    exchange_loss: list[tuple] | None = None,
    initial_capital: float | None = None,
    btc: str = BTC_ASSET,
    fill_offset_hours: int = 0,
    assets: list[str] | None = None,
    record_weights: bool = True,
) -> BacktestResult:
    """Tek backtest çalıştırır.

    panel_1d      CONTRACTS §7 günlük panel (en az `close`; T3 için `open`; delist yedeği için `quote_volume`, `volume`)
    universe      sağlayıcı: universe(t) → DataFrame(symbol, tier, cap, slippage, ...) (providers.MonthlyUniverse)
    strategy      karar verici (varsayılan TrendStrategy(); kıyaslar: strategy.benchmarks.TargetWeightStrategy)
    panel_1h      dolum VWAP'ı için saatlik panel (`quote_volume`, `volume`) — veya hazır `fill_px` (dolum günü indeksli)
    delist        DataFrame(asset, last_day, announced_day) — rules.delist_info_from_panel
    cash_rate     yıllık hazine bonosu faizi serisi (cash_yield ≠ zero ise)
    quality_flags CONTRACTS §5 (symbol = asset_id); yalnızca temiz bar sayımını etkiler
    settings/overrides  ayarlar ve varyant/ızgara geçersiz kılmaları
    sizing        "compound" (base = NAV) | "fixed" (base = başlangıç sermayesi)
    exchange_loss T6: [(tarih, oran), ...] — o gün borsadaki tüm varlık (nakit + coin) oranı kadar kaybedilir
    """
    t0 = time.perf_counter()
    cfg = resolve_settings(settings, overrides)
    bt = cfg["backtest"]
    strategy = strategy if strategy is not None else TrendStrategy(btc=btc)
    if sizing not in ("compound", "fixed"):
        raise ValueError(sizing)

    close_all = _ns(panel_1d["close"])
    days = pd.date_range(close_all.index.min(), close_all.index.max(), freq="D").as_unit("ns")
    close_all = close_all.reindex(days)
    s_idx = 0 if start is None else int(days.searchsorted(pd.Timestamp(start), side="left"))
    e_idx = len(days) - 1 if end is None else int(days.searchsorted(pd.Timestamp(end), side="right")) - 1
    if s_idx > e_idx:
        raise ValueError("boş backtest aralığı")

    # --- evren: karar günü → anahtar → tablo (ay başına bir kez) ---
    keyf = getattr(universe, "key", None)
    day_key: list = []
    key_df: dict = {}
    for i in range(s_idx, e_idx + 1):
        t = days[i]
        k = keyf(t) if keyf is not None else i
        day_key.append(k)
        if k not in key_df:
            key_df[k] = universe(t)
    if assets is None:
        need = set(strategy.required_assets())
        for df in key_df.values():
            if df is not None and len(df):
                need.update(df["symbol"].astype(str))
        assets = [c for c in close_all.columns if c in need]
    else:
        assets = [c for c in assets if c in close_all.columns]
    n = len(assets)
    col = {a: j for j, a in enumerate(assets)}
    close = close_all[assets]
    C = close.to_numpy(dtype=float)
    btc_idx = col.get(btc)
    univ_arr = {k: universe_arrays(df, col, n, cfg) for k, df in key_df.items()}

    # --- dolum fiyatları (dolum günü indeksli) ---
    if fill_px is None:
        p1d = {k: _ns(v)[[a for a in assets if a in v.columns]] for k, v in panel_1d.items()}
        p1h = None
        if panel_1h is not None:
            p1h = {k: v[[a for a in assets if a in v.columns]] for k, v in panel_1h.items()
                   if k in ("quote_volume", "volume")}
        fill_px = fill_prices_from_settings(cfg, p1d, p1h, offset_hours=fill_offset_hours)
    FP = _ns(fill_px).reindex(index=days, columns=assets).to_numpy(dtype=float)
    if "quote_volume" in panel_1d and "volume" in panel_1d:
        qv = _ns(panel_1d["quote_volume"]).reindex(index=days, columns=assets).to_numpy(dtype=float)
        vo = _ns(panel_1d["volume"]).reindex(index=days, columns=assets).to_numpy(dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            DV = np.where(vo > 0, qv / vo, np.nan)
    else:
        DV = np.full_like(C, np.nan)

    # --- delist ---
    last_idx = np.full(n, -1, dtype=np.int64)
    ann_idx = np.full(n, np.iinfo(np.int64).max, dtype=np.int64)
    if delist is not None and len(delist):
        for a, ld, ad in zip(delist["asset"].astype(str), delist["last_day"], delist["announced_day"]):
            j = col.get(a)
            if j is None:
                continue
            if pd.notna(ld):
                ld = pd.Timestamp(ld).floor("D")  # son mumun gün etiketi
                p = int(days.searchsorted(ld, side="left"))
                if p < len(days) and days[p] == ld:
                    last_idx[j] = p
            if pd.notna(ad):
                ann_idx[j] = int(days.searchsorted(pd.Timestamp(ad).floor("D"), side="left"))

    rate = daily_cash_rate(cash_rate, days, bt["cash_yield"], TBILL_HAIRCUT)
    loss = {}
    for d, f in exchange_loss or []:
        loss[int(days.searchsorted(pd.Timestamp(d), side="left"))] = float(f)

    data = EngineData(days=days, assets=assets, close=close, cfg=cfg, btc_idx=btc_idx,
                      quality_flags=quality_flags, start_idx=s_idx)
    strategy.prepare(data)
    for i in range(0, s_idx):
        strategy.observe(i)

    # --- durum ---
    init = float(initial_capital if initial_capital is not None else bt["initial_capital"])
    m = float(bt["cost_multiplier"])
    comm = float(bt["commission"]) * m
    pen = float(bt["delist_penalty"]) * m
    min_order = float(bt["min_order_usdt"])
    dust_zero = bool(bt["dust_zero"])
    rb = cfg["strategy"]["rebalance"]
    mt_mult, mt_min = float(rb["mintrade_notional_mult"]), float(rb["mintrade_min_frac"])
    hs_cfg = cfg["strategy"]["drawdown_hard_stop"]
    hs = HardStop(float(hs_cfg["stop_at"]), float(hs_cfg["resume_at"]), enabled=hard_stop)

    cash = init
    qty = np.zeros(n)
    last_px = np.full(n, np.nan)
    s3_last = np.full(n, -1, dtype=np.int64)
    last_cap = np.full(n, np.nan)
    last_slip = np.array([default_slippage(a, cfg) for a in assets])
    dead = np.zeros(n, dtype=bool)
    pending = None

    n_run = e_idx - s_idx + 1
    rec = {k: np.zeros(n_run) for k in ("nav", "cash", "gross_exposure", "n_pos", "turnover", "commission", "slippage_cost",
                                        "penalty_cost", "cash_yield", "hard_stop", "exchange_loss")}
    W = np.zeros((n_run, n)) if record_weights else None
    F = {c: [] for c in FILL_COLUMNS}
    D = {c: [] for c in DECISION_COLUMNS}
    nav_prev = init
    assets_arr = np.array(assets, dtype=object)
    day_ts = list(days)  # pandas indeks erişimi döngüde yavaş

    def log_fills(i, di, j, side, kind, q, vwap, price, slip, slip_cost, com, pcost, notional, cf):
        k = len(j)
        F["date"].extend([day_ts[i]] * k)
        F["decision_date"].extend([day_ts[di] if di is not None else pd.NaT] * k)
        F["asset"].extend(assets_arr[j].tolist())
        F["side"].extend([side] * k)
        F["kind"].extend(list(kind) if not isinstance(kind, str) else [kind] * k)
        for c, v in (("qty", q), ("vwap", vwap), ("price", price), ("slippage", slip), ("slippage_cost", slip_cost),
                     ("commission", com), ("penalty_cost", pcost), ("notional", notional), ("cash_flow", cf)):
            F[c].extend(np.broadcast_to(np.asarray(v, dtype=float), (k,)).tolist())
        F["qty_after"].extend(qty[j].tolist())
        F["post_weight"].extend([np.nan] * k)

    for r, i in enumerate(range(s_idx, e_idx + 1)):
        strategy.observe(i)
        ci = C[i]
        okc = np.isfinite(ci)
        last_px = np.where(okc, ci, last_px)
        d_comm = d_slip = d_pen = d_traded = 0.0
        n_fill_rows_before = len(F["date"])

        # 1. dolumlar (t−1 kararı)
        if pending is not None:
            di, oj, oq, oex, osl, os3, orsn = pending
            px = FP[i, oj]
            ok = np.isfinite(px)
            # satışlar
            sm = ok & (oq < 0)
            if sm.any():
                j = oj[sm]
                q = np.where(oex[sm], qty[j], np.minimum(-oq[sm], qty[j]))
                p = px[sm]
                sl = osl[sm] * m
                ep = p * (1.0 - sl)
                notional = q * ep
                is_ex = oex[sm]
                dust = (q > 0) & is_ex & (notional < min_order) & dust_zero
                sell = (q > 0) & ~dust & (is_ex | (notional >= min_order))
                if dust.any():
                    jd = j[dust]
                    qd = q[dust]
                    qty[jd] = 0.0
                    log_fills(i, di, jd, "sell", "dust", qd, p[dust], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                if sell.any():
                    js, qs, ps, eps, sls = j[sell], q[sell], p[sell], ep[sell], sl[sell]
                    proceeds = qs * eps
                    com = proceeds * comm
                    cash += float(proceeds.sum() - com.sum())
                    qty[js] = qty[js] - qs
                    qty[js] = np.where(qty[js] < 0, 0.0, qty[js])
                    sc = qs * ps * sls
                    d_comm += float(com.sum())
                    d_slip += float(sc.sum())
                    d_traded += float((qs * ps).sum())
                    kinds = [REASON_NAMES[int(x)] for x in orsn[sm][sell]]
                    log_fills(i, di, js, "sell", kinds, qs, ps, eps, sls, sc, com, 0.0, proceeds, proceeds - com)
                    s3_last[js] = np.where(qty[js] > 0, os3[sm][sell], -1)
            # alımlar
            bm = ok & (oq > 0)
            if bm.any():
                j, q, p = oj[bm], oq[bm].copy(), px[bm]
                sl = osl[bm] * m
                ep = p * (1.0 + sl)
                cost = q * ep * (1.0 + comm)
                tot = float(cost.sum())
                if tot > cash:
                    f = max(cash, 0.0) / tot
                    q = q * f
                    cost = cost * f
                keep = q * ep >= min_order
                if keep.any():
                    jk, qk, pk, epk, slk = j[keep], q[keep], p[keep], ep[keep], sl[keep]
                    notional = qk * epk
                    com = notional * comm
                    cash = max(cash - float(cost[keep].sum()), 0.0)
                    qty[jk] = qty[jk] + qk
                    last_px[jk] = np.where(np.isfinite(last_px[jk]), last_px[jk], pk)
                    sc = qk * pk * slk
                    d_comm += float(com.sum())
                    d_slip += float(sc.sum())
                    d_traded += float((qk * pk).sum())
                    kinds = [REASON_NAMES[int(x)] for x in orsn[bm][keep]]
                    log_fills(i, di, jk, "buy", kinds, qk, pk, epk, slk, sc, com, 0.0, notional, -(notional + com))
                    s3_last[jk] = os3[bm][keep]
            pending = None

        # 2. delist kuralı (son mum günü)
        dl = np.nonzero(last_idx == i)[0]
        if dl.size:
            dead[dl] = True
            hj = dl[qty[dl] > 0]
            if hj.size:
                p = FP[i, hj]
                p = np.where(np.isfinite(p), p, DV[i, hj])
                p = np.where(np.isfinite(p), p, last_px[hj])
                q = qty[hj].copy()
                ep = p * (1.0 - pen)
                proceeds = q * ep
                dust = (proceeds < min_order) & dust_zero
                com = np.where(dust, 0.0, proceeds * comm)
                cf = np.where(dust, 0.0, proceeds - com)
                cash += float(cf.sum())
                qty[hj] = 0.0
                pc = np.where(dust, 0.0, q * p * pen)
                d_comm += float(com.sum())
                d_pen += float(pc.sum())
                kinds = np.where(dust, "dust", "delist")
                log_fills(i, None, hj, "sell", kinds, q, p, np.where(dust, 0.0, ep), 0.0, 0.0, com, pc,
                          np.where(dust, 0.0, proceeds), cf)
                s3_last[hj] = -1

        # T6 borsa kaybı
        if i in loss:
            f = loss[i]
            cash *= 1.0 - f
            qty *= 1.0 - f
            rec["exchange_loss"][r] = f

        # 3. nakit getirisi ve değerleme
        if r > 0 and rate[i] != 0.0:
            y = cash * rate[i] / 365.0
            cash += y
            rec["cash_yield"][r] = y
        held = qty > 0
        mv = np.where(held, qty * np.where(np.isfinite(last_px), last_px, 0.0), 0.0)
        nav = cash + float(mv.sum())
        stopped = hs.update(nav)
        rec["nav"][r], rec["cash"][r] = nav, cash
        rec["gross_exposure"][r] = float(mv.sum()) / nav if nav > 0 else 0.0
        rec["n_pos"][r] = float(held.sum())
        rec["turnover"][r] = d_traded / nav_prev if nav_prev > 0 else 0.0
        rec["commission"][r], rec["slippage_cost"][r], rec["penalty_cost"][r] = d_comm, d_slip, d_pen
        rec["hard_stop"][r] = float(stopped)
        if W is not None and nav > 0:
            W[r] = mv / nav
        if len(F["date"]) > n_fill_rows_before:  # işlem sonrası ağırlık (t kapanışı)
            for k in range(n_fill_rows_before, len(F["date"])):
                F["post_weight"][k] = float(mv[col[F["asset"][k]]] / nav) if nav > 0 else np.nan
        nav_prev = nav

        # 4–5. evren ve karar
        u_mask, u_cap, u_slip = univ_arr[day_key[r]]
        last_cap = np.where(u_mask, u_cap, last_cap)
        last_slip = np.where(u_mask & np.isfinite(u_slip), u_slip, last_slip)
        base = nav if sizing == "compound" else init
        w = mv / base if base > 0 else np.zeros(n)
        frozen = ~okc
        force_zero = dead | (ann_idx <= i)
        mtf = mintrade(base, min_order, mt_mult, mt_min)
        view = DayView(i=i, t=day_ts[i], first=(r == 0), base=base, nav=nav, qty=qty.copy(), w=w, held=held,
                       frozen=frozen, univ=u_mask, cap=last_cap.copy(), force_zero=force_zero,
                       s3_last=s3_last.copy(), mintrade=mtf)
        dec = strategy.decide(view)
        delta = np.where(frozen, 0.0, dec.delta)
        reason = dec.reason.copy()
        is_exit = (reason == EXIT) & held & (delta < 0)
        small = (delta != 0) & ~is_exit & (np.abs(delta) * base < min_order)
        delta[small] = 0.0
        reason[small] = SKIP_MINORDER
        if stopped:
            inc = delta > 0
            delta[inc] = 0.0
            reason[inc] = SKIP_HARDSTOP
        oj = np.nonzero(delta != 0)[0]
        oq = np.zeros(n)
        if oj.size:
            oq[oj] = np.where(is_exit[oj], -qty[oj], delta[oj] * base / ci[oj])
            pending = (i, oj, oq[oj], is_exit[oj], last_slip[oj].copy(), dec.s3[oj].astype(np.int64),
                       reason[oj].copy())
        s3_raw = dec.s3_raw if dec.s3_raw is not None else np.full(n, -1)
        logm = u_mask | held | (dec.w_tgt > 0) | (delta != 0) | (reason != 0)
        lj = np.nonzero(logm)[0]
        if lj.size:
            D["date"].extend([day_ts[i]] * lj.size)
            D["asset"].extend(assets_arr[lj].tolist())
            D["s3_raw"].extend(s3_raw[lj].astype(int).tolist())
            D["s3"].extend(dec.s3[lj].astype(int).tolist())
            D["w"].extend(w[lj].tolist())
            D["w_tgt"].extend(dec.w_tgt[lj].tolist())
            D["delta"].extend(delta[lj].tolist())
            D["qty"].extend(oq[lj].tolist())
            D["reason"].extend([REASON_NAMES[int(x)] for x in reason[lj]])

    idx = pd.DatetimeIndex(days[s_idx:e_idx + 1], name="date")
    daily = pd.DataFrame(rec, index=idx)
    daily["cost"] = daily["commission"] + daily["slippage_cost"] + daily["penalty_cost"]
    prev = daily["nav"].shift(1)
    prev.iloc[0] = init
    daily["ret"] = daily["nav"] / prev - 1.0
    peak = daily["nav"].cummax()
    daily["drawdown"] = daily["nav"] / peak - 1.0
    weights = pd.DataFrame(W, index=idx, columns=assets) if W is not None else None
    fills = pd.DataFrame(F, columns=FILL_COLUMNS)
    decisions = pd.DataFrame(D, columns=DECISION_COLUMNS)
    end_qty = {a: float(qty[j]) for j, a in enumerate(assets) if qty[j] > 0}
    end_px = {a: float(last_px[j]) for j, a in enumerate(assets)}
    cycles = build_cycles(fills, end_qty, end_px, days[e_idx])
    meta = {"initial_capital": init, "assets": assets, "start": days[s_idx], "end": days[e_idx],
            "sizing": sizing, "hard_stop": hard_stop, "runtime_s": time.perf_counter() - t0,
            "strategy": type(strategy).__name__}
    return BacktestResult(daily=daily, weights=weights, fills=fills, cycles=cycles, decisions=decisions,
                          cfg=cfg, meta=meta)
