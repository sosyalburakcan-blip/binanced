"""Raporlanacak metrikler (SPEC "Değerlendirme → Raporlanacak metrikler"), her alt dönem için ayrı hesaplanabilir.

Girdi biçimleri (motor çıktısı; CONTRACTS.md: index tz-naive UTC günlük `DatetimeIndex`, gün etiketi t = t mumunun
kapanışı; her takvim günü bir satır):

daily : pd.DataFrame
    nav             float  t kapanışında portföy değeri (USDT; o günkü tüm dolum ve maliyetler sonrası)
    cash            float  t kapanışında nakit (USDT)
    gross_exposure  float  Σ_i w_i, t kapanışında (NAV oranı) — yoksa `weights`'ten hesaplanır
    turnover        float  t günü dolumlarının Σ|işlem tutarı| / NAV(t−1)  (alım + satım, tek yön değil)
    cost            float  t günü toplam maliyet, USDT (komisyon + kayma + delist cezası)
    ret             float  (isteğe bağlı) t günü basit getiri; yoksa nav.pct_change()
weights : pd.DataFrame  index = daily.index, kolonlar = asset_id, t kapanışındaki ağırlık (NAV oranı)
cycles : pd.DataFrame  döngü defteri (SPEC "Muhasebe")
    asset       str       asset_id
    open_date   datetime  ağırlığı 0'dan pozitife taşıyan ilk dolumun günü
    close_date  datetime  tekrar 0'a indiren dolumun günü; açık döngüde NaT
    profit      float     tüm dolumlar ve maliyetler dahil net kâr (USDT); açık döngü piyasa değerinden
    is_open     bool      dönem sonunda açık mı

Kurallar: getiriler tam seriden hesaplanır, sonra döneme kesilir (dönemin ilk günü de bir getiri taşır).
Düşüşler (drawdown) her yerde ≤ 0 kesirdir (−0,35 = −%35). Bir döngü, açılış günü dönem içindeyse o döneme aittir.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from trend.config import load_settings
from trend.evaluation.common import excess_returns, periods_per_year, settings, sharpe

DAILY_COLUMNS = ("nav", "cash", "gross_exposure", "turnover", "cost")
CYCLE_COLUMNS = ("asset", "open_date", "close_date", "profit", "is_open")
ROLLING_WINDOW_DAYS = 365  # "kayan 12 aylık Sharpe"
TOP_CYCLE_FRAC = 0.10  # "kârın en iyi %10 döngüden gelen payı"
WORST_LOSS_WINDOWS = (1, 3)  # "en kötü 1 ve 3 günlük kayıp"
# Bundan küçük gün içi maruziyette ölçekleme yapılmaz.
WORST_LOSS_MIN_EXPOSURE = float(load_settings()["evaluation"]["worst_loss_min_exposure"])
WORST_LOSS_TOP = 5


# ---------------------------------------------------------------------------------------------------------------
# Dönemler


def periods_from_settings(
    cfg: dict[str, Any] | None = None, stage: str = "development", lock_date: str | pd.Timestamp | None = None
) -> dict[str, tuple[pd.Timestamp, pd.Timestamp | None]]:
    """Rapor dönemleri. stage="development": geliştirme + iki rejimin geliştirme içindeki kısmı (G10–G11).

    stage="full" (G12, kilitten sonra; `lock_date` zorunlu): geliştirme, doğrulama, tam dönem (2019-07 – kilit),
    iki rejim (ikincisi kilide kadar). Doğrulama dönemi kilitten önce yanlışlıkla raporlanmasın diye ayrıdır.
    """
    p = settings(cfg)["periods"]
    ts = pd.Timestamp
    dev_s, dev_e = ts(p["development"][0]), ts(p["development"][1])
    (r1s, r1e), (r2s, r2e) = p["regimes"]
    if stage == "development":
        end = dev_e
    elif stage == "full":
        if lock_date is None:
            raise ValueError("stage='full' için kilit tarihi gerekir")
        end = ts(lock_date)
    else:
        raise ValueError(f"bilinmeyen stage: {stage!r}")

    def clip(e):
        return end if e is None else min(ts(e), end)

    out = {"development": (dev_s, dev_e)}
    if stage == "full":
        out["validation"] = (ts(p["validation_start"]), end)
        out["full"] = (dev_s, end)
    out[f"regime_{r1s[:7]}_{(r1e or 'end')[:7]}"] = (ts(r1s), clip(r1e))
    out[f"regime_{r2s[:7]}_{(r2e or 'end')[:7]}"] = (ts(r2s), clip(r2e))
    return out


def _slice(obj, start=None, end=None):
    return obj.loc[start:end]


# ---------------------------------------------------------------------------------------------------------------
# Getiri bazlı metrikler


def daily_returns(daily: pd.DataFrame) -> pd.Series:
    """Günlük basit getiri: `ret` kolonu varsa o, yoksa nav.pct_change() (ilk gün atılır)."""
    if "ret" in daily.columns:
        r = daily["ret"].astype(float).dropna()
    else:
        r = daily["nav"].astype(float).pct_change().iloc[1:]
    if r.isna().any():
        raise ValueError("getiri serisinde NaN var")
    r.name = "ret"
    return r


def annual_return(r: pd.Series, ppy: int = 365) -> float:
    """Bileşik yıllık getiri (CAGR) = (Π(1+r))^(ppy/n) − 1."""
    if len(r) == 0:
        return float("nan")
    return float(np.prod(1.0 + r.to_numpy()) ** (ppy / len(r)) - 1.0)


def annual_volatility(r: pd.Series, ppy: int = 365) -> float:
    """Gerçekleşen yıllık oynaklık = std(r, ddof=1)·√ppy."""
    return float(r.std(ddof=1) * np.sqrt(ppy))


def sharpe_ratio(r: pd.Series, rf: pd.Series | float | None = None, ppy: int = 365) -> float:
    """Risksiz faiz üzerindeki yıllık Sharpe: ort(r − rf)/std(r − rf)·√ppy (Sharpe 1994)."""
    return sharpe(excess_returns(r, rf), ppy)


def sortino_ratio(r: pd.Series, rf: pd.Series | float | None = None, ppy: int = 365) -> float:
    """Sortino = ort(r − rf) / √ort(min(r − rf, 0)²) · √ppy; hedef getiri = rf (Sortino ve Price 1994)."""
    ex = excess_returns(r, rf).to_numpy()
    dd = np.sqrt(np.mean(np.minimum(ex, 0.0) ** 2))
    return float(ex.mean() / dd * np.sqrt(ppy)) if dd > 0 else float("nan")


def drawdown(r: pd.Series) -> pd.Series:
    """Düşüş serisi W/max(W) − 1, W = Π(1+r), dönem başı değeri 1 zirve sayılır."""
    w = np.cumprod(1.0 + r.to_numpy())
    peak = np.maximum.accumulate(np.maximum(w, 1.0))
    return pd.Series(w / peak - 1.0, index=r.index, name="drawdown")


def _underwater_runs(dd: pd.Series) -> pd.DataFrame:
    """Ardışık sudan uzak (dd < 0) dönemler: start, end, days, recovered, trough_dd."""
    uw = (dd < 0).to_numpy()
    if not uw.any():
        return pd.DataFrame(columns=["start", "end", "days", "recovered", "trough_dd"])
    edges = np.diff(np.concatenate([[0], uw.astype(int), [0]]))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1) - 1
    vals = dd.to_numpy()
    rows = [
        (dd.index[s], dd.index[e], e - s + 1, e < len(uw) - 1, vals[s : e + 1].min())
        for s, e in zip(starts, ends)
    ]
    return pd.DataFrame(rows, columns=["start", "end", "days", "recovered", "trough_dd"])


def max_drawdown_info(r: pd.Series) -> dict[str, Any]:
    """En büyük düşüş, zirve/dip/toparlanma tarihleri ve süresi (dip içeren sudan uzak dönemin gün sayısı)."""
    dd = drawdown(r)
    mdd = float(dd.min()) if len(dd) else float("nan")
    out = {"max_drawdown": mdd, "mdd_peak": pd.NaT, "mdd_trough": pd.NaT, "mdd_recovery": pd.NaT,
           "mdd_duration_days": 0}
    if not len(dd) or mdd >= 0:
        return out
    pos = int(np.argmin(dd.to_numpy()))
    vals = dd.to_numpy()
    zeros_before = np.flatnonzero(vals[:pos] >= 0)
    peak = dd.index[zeros_before[-1]] if zeros_before.size else dd.index[0] - pd.Timedelta(days=1)
    zeros_after = np.flatnonzero(vals[pos:] >= 0)
    rec = dd.index[pos + zeros_after[0]] if zeros_after.size else pd.NaT
    end_pos = pos + zeros_after[0] - 1 if zeros_after.size else len(vals) - 1
    start_pos = zeros_before[-1] + 1 if zeros_before.size else 0
    out.update(mdd_peak=peak, mdd_trough=dd.index[pos], mdd_recovery=rec, mdd_duration_days=int(end_pos - start_pos + 1))
    return out


def underwater_info(r: pd.Series) -> dict[str, Any]:
    """Sudan uzak kalınan süre: zaman payı, en uzun kesintisiz dönem (gün), dönem sonunda süren dönem (gün)."""
    dd = drawdown(r)
    runs = _underwater_runs(dd)
    cur = 0
    if len(runs) and not runs["recovered"].iloc[-1]:
        cur = int(runs["days"].iloc[-1])
    return {
        "time_under_water_frac": float((dd < 0).mean()) if len(dd) else float("nan"),
        "longest_underwater_days": int(runs["days"].max()) if len(runs) else 0,
        "current_underwater_days": cur,
    }


def calmar_ratio(r: pd.Series, ppy: int = 365) -> float:
    """Calmar = CAGR / |en büyük düşüş| (Young 1991; burada tüm dönem üzerinden)."""
    mdd = drawdown(r).min()
    return float(annual_return(r, ppy) / abs(mdd)) if mdd < 0 else float("nan")


def skewness(r: pd.Series) -> float:
    """Örneklem çarpıklığı (düzeltilmiş Fisher–Pearson, bias=False)."""
    return float(stats.skew(r.to_numpy(), bias=False))


def kurtosis(r: pd.Series) -> float:
    """Basıklık, Pearson tanımı (normal = 3), bias=False. DSR/MinTRL γ4 girdisi."""
    return float(stats.kurtosis(r.to_numpy(), fisher=False, bias=False))


def rolling_sharpe(
    r: pd.Series, rf: pd.Series | float | None = None, window: int = ROLLING_WINDOW_DAYS, ppy: int = 365
) -> pd.Series:
    """Kayan `window` günlük Sharpe (fazla getiri, √ppy); tam pencere dolmadan NaN."""
    ex = excess_returns(r, rf)
    roll = ex.rolling(window, min_periods=window)
    out = roll.mean() / roll.std(ddof=1) * np.sqrt(ppy)
    out.name = "rolling_sharpe_12m"
    return out


def yearly_returns(r: pd.Series) -> pd.DataFrame:
    """Takvim yılı bazında bileşik getiri ve gün sayısı (kısmi yıllar gün sayısıyla görünür)."""
    g = (1.0 + r).groupby(r.index.year)
    return pd.DataFrame({"return": g.prod() - 1.0, "n_days": g.size()}).rename_axis("year")


# ---------------------------------------------------------------------------------------------------------------
# Maruziyet, ciro, maliyet, nakit


def gross_exposure(daily: pd.DataFrame, weights: pd.DataFrame | None = None) -> pd.Series:
    if "gross_exposure" in daily.columns:
        return daily["gross_exposure"].astype(float)
    if weights is None:
        raise ValueError("gross_exposure kolonu yok ve weights verilmedi")
    return weights.reindex(daily.index).fillna(0.0).sum(axis=1).rename("gross_exposure")


def cost_fraction(daily: pd.DataFrame) -> pd.Series:
    """Günlük maliyet / NAV(t−1). İlk gün için NAV(t−1) ≈ nav + cost."""
    nav = daily["nav"].astype(float)
    cost = daily["cost"].astype(float)
    prev = nav.shift(1)
    prev.iloc[0] = nav.iloc[0] + cost.iloc[0]
    return (cost / prev).rename("cost_frac")


def turnover_cost_by_year(daily: pd.DataFrame, cost_frac: pd.Series) -> pd.DataFrame:
    """Yıl bazında toplam ciro (NAV oranı, alım + satım) ve toplam maliyet (NAV oranı)."""
    yr = daily.index.year
    return pd.DataFrame(
        {"turnover": daily["turnover"].astype(float).groupby(yr).sum(), "cost": cost_frac.groupby(yr).sum()}
    ).rename_axis("year")


def cash_drag(cash_share: pd.Series, tbill_daily: pd.Series, ppy: int = 365) -> float:
    """Nakit kaybı (yıllık) = ort_t(nakit payı_t × hazine bonosu günlük oranı_t) × ppy (SPEC "Ön kayıt")."""
    tb = tbill_daily.reindex(cash_share.index)
    if tb.isna().any():
        raise ValueError("hazine bonosu serisi nakit payı tarihlerini kapsamıyor")
    return float((cash_share * tb).mean() * ppy)


def intraday_exposure(daily: pd.DataFrame, r: pd.Series) -> pd.Series:
    """t günü dolumdan sonra taşınan maruziyet G0_t = 1 − (cash_t/nav_t)·(1 + r_t).

    Gün sonu ağırlık o günün getirisiyle kaymıştır; nakit gün içinde sabit kabul edilerek gün başı maruziyete
    geri çevrilir (nakit getirisi ve maliyetin etkisi ≤ birkaç baz puan, ihmal edilir).
    """
    share = (daily["cash"].astype(float) / daily["nav"].astype(float)).reindex(r.index)
    return (1.0 - share * (1.0 + r)).clip(lower=0.0).rename("exposure_intraday")


def worst_losses_at_max_exposure(
    daily: pd.DataFrame,
    r: pd.Series,
    windows: tuple[int, ...] = WORST_LOSS_WINDOWS,
    max_exposure: float = 1.0,
    top: int = WORST_LOSS_TOP,
    min_exposure: float = WORST_LOSS_MIN_EXPOSURE,
) -> pd.DataFrame:
    """Maksimum maruziyette en kötü 1 ve 3 günlük kayıp tablosu.

    Riskli kısmın getirisi r_t / G0_t (G0: `intraday_exposure`) maksimum maruziyete ölçeklenir:
    r_max_t = max_exposure · r_t / G0_t (G0_t < min_exposure günleri tanımsız). w günlük pencere: Π(1+r_max) − 1.
    Çakışmayan en kötü `top` pencere; gerçekleşen getiri ve ortalama maruziyet yanında verilir.
    """
    g0 = intraday_exposure(daily, r)
    scaled = (max_exposure * r / g0).where(g0 >= min_exposure).clip(lower=-1.0)
    log_s = np.log1p(scaled.clip(lower=-1 + 1e-12))
    log_r = np.log1p(r)
    rows = []
    for w in windows:
        comp = np.expm1(log_s.rolling(w, min_periods=w).sum())
        actual = np.expm1(log_r.rolling(w, min_periods=w).sum())
        avg_g = g0.rolling(w, min_periods=w).mean()
        order = comp.dropna().sort_values()
        taken: list[int] = []
        for end in order.index:
            pos = r.index.get_loc(end)
            if any(abs(pos - p) < w for p in taken):
                continue
            taken.append(pos)
            rows.append({"window_days": w, "rank": len(taken), "start": r.index[pos - w + 1], "end": end,
                         "loss_at_max_exposure": float(comp[end]), "actual_return": float(actual[end]),
                         "avg_exposure": float(avg_g[end])})
            if len(taken) >= top:
                break
    return pd.DataFrame(rows, columns=["window_days", "rank", "start", "end", "loss_at_max_exposure",
                                       "actual_return", "avg_exposure"])


def worst_actual_loss(r: pd.Series, w: int) -> float:
    """Gerçekleşen en kötü w günlük bileşik getiri."""
    if len(r) < w:
        return float("nan")
    return float(np.expm1(np.log1p(r).rolling(w, min_periods=w).sum()).min())


# ---------------------------------------------------------------------------------------------------------------
# Döngü metrikleri


def cycles_in_period(cycles: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    od = pd.to_datetime(cycles["open_date"])
    m = pd.Series(True, index=cycles.index)
    if start is not None:
        m &= od >= pd.Timestamp(start)
    if end is not None:
        m &= od <= pd.Timestamp(end)
    return cycles.loc[m]


def holding_days(cycles: pd.DataFrame) -> pd.Series:
    """Tutma süresi = son dolum − ilk dolum (gün); açık döngüler sansürlü olduğu için NaN."""
    d = (pd.to_datetime(cycles["close_date"]) - pd.to_datetime(cycles["open_date"])).dt.days.astype(float)
    return d.where(~cycles["is_open"].astype(bool))


def holding_time_table(cycles: pd.DataFrame) -> pd.DataFrame:
    """Kapanmış döngülerde tutma süresi medyanı ile %10/%90 dilimleri; kazanan / kaybeden / tümü ayrı."""
    hd = holding_days(cycles)
    win = cycles["profit"].astype(float) > 0
    rows = {}
    for name, mask in (("winners", win), ("losers", ~win), ("all", pd.Series(True, index=cycles.index))):
        x = hd[mask].dropna()
        rows[name] = {"n": int(x.size),
                      "p10": float(x.quantile(0.10)) if x.size else np.nan,
                      "median": float(x.median()) if x.size else np.nan,
                      "p90": float(x.quantile(0.90)) if x.size else np.nan}
    return pd.DataFrame(rows).T


def cycle_stats(cycles: pd.DataFrame, top_frac: float = TOP_CYCLE_FRAC) -> dict[str, Any]:
    """Döngü sayısı, kazanma oranı (kâr > 0), ortalama kazanç/zarar (USDT), en iyi %10 döngünün kâr payı,
    kârlı coin sayısı. Açık döngüler piyasa değerinden dahildir (SPEC "Muhasebe")."""
    p = cycles["profit"].astype(float)
    n = int(len(p))
    win = p > 0
    out: dict[str, Any] = {"n_cycles": n, "n_open_cycles": int(cycles["is_open"].astype(bool).sum())}
    out["win_rate"] = float(win.mean()) if n else np.nan
    out["avg_win"] = float(p[win].mean()) if win.any() else np.nan
    out["avg_loss"] = float(p[~win].mean()) if (~win).any() else np.nan
    out["payoff_ratio"] = (abs(out["avg_win"] / out["avg_loss"])
                           if win.any() and (~win).any() and out["avg_loss"] != 0 else np.nan)
    total = float(p.sum())
    k = int(np.ceil(top_frac * n)) if n else 0
    out["total_cycle_profit"] = total
    # kâr payı: en iyi ⌈%10·n⌉ döngünün kârı / toplam net kâr (toplam ≤ 0 ise tanımsız; > 1 olabilir)
    out["top10pct_profit_share"] = float(p.nlargest(k).sum() / total) if n and total > 0 else np.nan
    by_coin = p.groupby(cycles["asset"]).sum()
    out["n_coins_traded"] = int(by_coin.size)
    out["n_profitable_coins"] = int((by_coin > 0).sum())
    hd = holding_time_table(cycles) if n else None
    for grp in ("winners", "losers", "all"):
        for q in ("p10", "median", "p90"):
            out[f"hold_{q}_{grp}"] = float(hd.loc[grp, q]) if hd is not None else np.nan
    return out


# ---------------------------------------------------------------------------------------------------------------
# Toplu hesap


def compute_metrics(
    daily: pd.DataFrame,
    cycles: pd.DataFrame | None = None,
    rf_daily: pd.Series | float | None = None,
    tbill_daily: pd.Series | None = None,
    start=None,
    end=None,
    weights: pd.DataFrame | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bir dönem için tüm metrikler. Dönüş: {"scalars": dict, "tables": dict}.

    rf_daily: Sharpe/Sortino için günlük risksiz oran (rates.rf_daily); tbill_daily: nakit kaybı için hazine bonosu
    günlük oranı (çoğunlukla rf_daily ile aynı). Verilmezse ilgili metrikler rf = 0 / NaN olur.
    """
    cfg = settings(cfg)
    ppy = periods_per_year(cfg)
    target_vol = float(cfg["strategy"]["target_vol"])
    gmax = float(cfg["strategy"]["gross_max"])

    r_full = daily_returns(daily)
    cf_full = cost_fraction(daily) if "cost" in daily.columns else None
    r = _slice(r_full, start, end)
    d = _slice(daily, start, end).loc[r.index[0] : r.index[-1]] if len(r) else _slice(daily, start, end)
    if len(r) < 2:
        raise ValueError("dönemde yeterli getiri yok")

    sc: dict[str, Any] = {"start": r.index[0], "end": r.index[-1], "n_days": int(len(r))}
    sc["annual_return"] = annual_return(r, ppy)
    sc["annual_return_simple"] = float(r.mean() * ppy)  # sabit tutarlı (bileşiksiz) karşılık, SPEC "Muhasebe"
    sc["annual_vol"] = annual_volatility(r, ppy)
    sc["target_vol"] = target_vol
    sc["vol_minus_target"] = sc["annual_vol"] - target_vol
    ge = gross_exposure(d, weights)
    cash_share = (d["cash"].astype(float) / d["nav"].astype(float)).rename("cash_share")
    sc["avg_gross_exposure"] = float(ge.mean())
    sc["max_gross_exposure"] = float(ge.max())
    sc["avg_cash_share"] = float(cash_share.mean())
    sc["sharpe"] = sharpe_ratio(r, rf_daily, ppy)
    sc["sortino"] = sortino_ratio(r, rf_daily, ppy)
    sc["calmar"] = calmar_ratio(r, ppy)
    sc.update(max_drawdown_info(r))
    sc.update(underwater_info(r))
    sc["skewness"] = skewness(r)
    sc["kurtosis"] = kurtosis(r)

    tables: dict[str, Any] = {}
    yearly = yearly_returns(r)
    if cf_full is not None and "turnover" in d.columns:
        cf = cf_full.reindex(d.index)
        yearly = yearly.join(turnover_cost_by_year(d, cf))
        sc["turnover_annual"] = float(d["turnover"].sum() * ppy / len(d))
        sc["cost_annual"] = float(cf.sum() * ppy / len(d))
    sc["cash_drag_annual"] = cash_drag(cash_share, tbill_daily, ppy) if tbill_daily is not None else np.nan

    worst = worst_losses_at_max_exposure(d, r, max_exposure=gmax)
    for w in WORST_LOSS_WINDOWS:
        sc[f"worst_{w}d_actual"] = worst_actual_loss(r, w)
        sub = worst[worst["window_days"] == w]
        sc[f"worst_{w}d_at_max_exposure"] = float(sub["loss_at_max_exposure"].min()) if len(sub) else np.nan

    if cycles is not None:
        cyc = cycles_in_period(cycles, start, end)
        sc.update(cycle_stats(cyc))
        tables["holding_times"] = holding_time_table(cyc) if len(cyc) else None

    tables["yearly"] = yearly
    tables["rolling_sharpe_12m"] = rolling_sharpe(r, rf_daily, ROLLING_WINDOW_DAYS, ppy)
    tables["exposure_monthly"] = pd.DataFrame({"gross_exposure": ge, "cash_share": cash_share}).resample("ME").mean()
    tables["drawdown"] = drawdown(r)
    tables["worst_losses"] = worst
    return {"scalars": sc, "tables": tables}


def evaluate_periods(
    daily: pd.DataFrame,
    periods: dict[str, tuple],
    cycles: pd.DataFrame | None = None,
    rf_daily: pd.Series | float | None = None,
    tbill_daily: pd.Series | None = None,
    weights: pd.DataFrame | None = None,
    cfg: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """Her dönem için `compute_metrics`. Dönüş: (metrik × dönem skaler tablo, dönem → tablolar)."""
    scal, tabs = {}, {}
    for name, (s, e) in periods.items():
        res = compute_metrics(daily, cycles, rf_daily, tbill_daily, s, e, weights, cfg)
        scal[name], tabs[name] = res["scalars"], res["tables"]
    return pd.DataFrame(scal), tabs
