"""Negatif ve pozitif kontroller, sıfır hipotezi girdileri (SPEC "Değerlendirme").

Motorla çalışan kontroller (sinyal gecikmesi, ters sinyal, karıştırılmış ve GARCH panelleri) runner üzerinden
yürür; bu modül panelleri kurar. Ağırlık yoluyla çalışan kontroller (başka coinin getirisi, en iyi 5 döngü) ve sıfır
hipotezleri, nulls.py'deki basitleştirilmiş getiri hesabını (`portfolio_returns`) kullanır; gözlenen değer de aynı
hesapla üretilir.

Varsayımlar (SPEC'in açık bıraktığı yerler):
- Basitleştirilmiş getiri: coin getirisi = kapanış / son geçerli kapanış − 1 (boşluk dönüşündeki sıçrama dahil);
  maliyet oranı = komisyon + %0,10 kayma (ciro başına), gözlenen ve sıfır yollarında aynı.
- Tarih karıştırma kontrolü: günlük log getiri vektörleri (tüm coinler birlikte) veri başından dönem sonuna kadar
  aynı permütasyonla karıştırılır; coinin orijinalde verisi olan ama karışık satırda verisi olmayan günlerde getiri 0
  alınır. Fiyat her coinin ilk geçerli kapanışından yeniden kurulur; veri olmayan günler NaN kalır.
- GARCH kontrolü: her coine sıfır ortalamalı GARCH(1,1) yarı-ML ile uydurulur, standartlaştırılmış artıklar iid
  yeniden örneklenerek aynı uzunlukta seri üretilir (oynaklık eşleşir, trend yoktur; coinler arası bağımlılık yoktur).
- Kontrol panellerinde açılış = önceki kapanış ve dolum `open_t1`'dir; kıyas gerçek veride aynı dolumla (T3) yapılır.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.signal import lfilter

from trend.evaluation.common import sharpe
from trend.evaluation.nulls import portfolio_returns, start_of_day_weights

SIMPLE_SLIPPAGE = 0.0010


def simple_cost_rate(cfg: dict) -> float:
    return float(cfg["backtest"]["commission"]) + SIMPLE_SLIPPAGE


def asset_returns(close: pd.DataFrame) -> pd.DataFrame:
    """Coin günlük basit getirisi; boşluk sonrası ilk gün son geçerli kapanışa göre, veri olmayan gün NaN."""
    c = close.astype(float)
    prev = c.ffill().shift(1)
    return (c / prev - 1.0).where(c.notna())


def membership(universe, days: pd.DatetimeIndex, assets: list[str]) -> pd.DataFrame:
    """(gün × varlık) bool: t karar günündeki evren (ay(t+1)) üyeliği."""
    cols = {a: j for j, a in enumerate(assets)}
    arr = np.zeros((len(days), len(assets)), dtype=bool)
    cache: dict = {}
    for i, t in enumerate(days):
        k = universe.key(t)
        if k not in cache:
            df = universe(t)
            cache[k] = [cols[s] for s in df["symbol"].astype(str) if s in cols] if len(df) else []
        arr[i, cache[k]] = True
    return pd.DataFrame(arr, index=days, columns=assets)


def hold_weights(weights_end: pd.DataFrame, rets: pd.DataFrame) -> pd.DataFrame:
    return start_of_day_weights(weights_end.fillna(0.0), rets)


def simple_stats(w_hold: pd.DataFrame, rets: pd.DataFrame, cost_rate: float, rf: pd.Series | None,
                 ppy: int = 365) -> np.ndarray:
    """(Sharpe (rf üstü), en büyük düşüş) — basitleştirilmiş getiriyle."""
    r = portfolio_returns(w_hold, rets, cost_rate)
    ex = r - (rf.reindex(r.index).fillna(0.0) if rf is not None else 0.0)
    nav = (1.0 + r).cumprod()
    mdd = float((nav / nav.cummax() - 1.0).min())
    return np.array([sharpe(ex, ppy), mdd])


# ---------------------------------------------------------------------------------------------------------------
# Kontrol panelleri


def _rebuild(close: pd.DataFrame, lr: np.ndarray) -> dict[str, pd.DataFrame]:
    c = close.to_numpy(dtype=float)
    avail = np.isfinite(c)
    first = np.where(avail.any(axis=0), avail.argmax(axis=0), c.shape[0])
    lr = np.where(np.isfinite(lr), lr, 0.0)
    lr[~avail] = 0.0
    rows = np.arange(c.shape[0])[:, None]
    lr[rows <= first[None, :]] = 0.0
    p0 = np.log(np.where(first < c.shape[0], c[np.minimum(first, c.shape[0] - 1), np.arange(c.shape[1])], 1.0))
    logp = p0[None, :] + np.cumsum(lr, axis=0)
    new = np.where(avail, np.exp(logp), np.nan)
    cl = pd.DataFrame(new, index=close.index, columns=close.columns)
    op = cl.ffill().shift(1).where(cl.notna())
    return {"close": cl, "open": op}


def shuffled_panel(close: pd.DataFrame, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    """Negatif kontrol: günlük log getiri satırları (tüm coinler birlikte) karıştırılıp fiyat yeniden kurulur."""
    c = close.to_numpy(dtype=float)
    lr = np.full(c.shape, np.nan)
    prev = pd.DataFrame(c).ffill().shift(1).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        lr[1:] = np.log(c[1:] / prev[1:])
    perm = 1 + rng.permutation(c.shape[0] - 1)
    lr_p = lr.copy()
    lr_p[1:] = lr[perm]
    return _rebuild(close, lr_p)


def _garch_var(omega: float, alpha: float, beta: float, x: np.ndarray, v0: float) -> np.ndarray:
    """h_t = ω + α·x_{t−1}² + β·h_{t−1}, h_0 = v0 (doğrusal süzgeçle)."""
    u = np.empty_like(x)
    u[0] = v0
    u[1:] = omega + alpha * x[:-1] ** 2
    return lfilter([1.0], [1.0, -beta], u)


def _garch_nll(params: np.ndarray, x: np.ndarray, v0: float) -> float:
    omega, alpha, beta = params
    if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 0.999:
        return 1e12
    h = _garch_var(omega, alpha, beta, x, v0)
    return float(0.5 * np.sum(np.log(h) + x**2 / h))


def fit_garch(x: np.ndarray) -> tuple[float, float, float, np.ndarray]:
    """Sıfır ortalamalı GARCH(1,1) yarı-ML. Dönüş: (omega, alpha, beta, standartlaştırılmış artıklar)."""
    v0 = float(np.var(x))
    start = np.array([v0 * 0.05, 0.08, 0.90])
    res = minimize(_garch_nll, start, args=(x, v0), method="Nelder-Mead",
                   options={"maxiter": 2000, "xatol": 1e-8, "fatol": 1e-6})
    omega, alpha, beta = res.x if res.fun < 1e11 else start
    z = x / np.sqrt(_garch_var(omega, alpha, beta, x, v0))
    return float(omega), float(alpha), float(beta), (z - z.mean()) / z.std()


def garch_panel(close: pd.DataFrame, rng: np.random.Generator, fits: dict | None = None) -> dict[str, pd.DataFrame]:
    """Negatif kontrol: her coin için oynaklığı eşleştirilmiş, trendsiz GARCH(1,1) serisi."""
    c = close.to_numpy(dtype=float)
    prev = pd.DataFrame(c).ffill().shift(1).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        lr = np.log(c / prev)
    out = np.full(c.shape, np.nan)
    fits = fits if fits is not None else garch_fits(close)
    for j, a in enumerate(close.columns):
        f = fits.get(a)
        ok = np.isfinite(lr[:, j])
        if f is None or ok.sum() < 30:
            continue
        omega, alpha, beta, z = f
        n = int(ok.sum())
        e = rng.choice(z, size=n, replace=True)
        x = np.empty(n)
        h = omega / max(1.0 - alpha - beta, 1e-3)
        prev_x = 0.0
        for t in range(n):
            if t:
                h = omega + alpha * prev_x**2 + beta * h
            prev_x = np.sqrt(h) * e[t]
            x[t] = prev_x
        out[np.flatnonzero(ok), j] = x
    return _rebuild(close, out)


def garch_fits(close: pd.DataFrame) -> dict:
    c = close.to_numpy(dtype=float)
    prev = pd.DataFrame(c).ffill().shift(1).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        lr = np.log(c / prev)
    fits = {}
    for j, a in enumerate(close.columns):
        x = lr[:, j]
        x = x[np.isfinite(x)]
        if len(x) >= 30:
            fits[a] = fit_garch(x)
    return fits


# ---------------------------------------------------------------------------------------------------------------
# Ağırlık yolu kontrolleri


def other_coin_control(w_hold: pd.DataFrame, rets: pd.DataFrame, cost_rate: float, rf: pd.Series | None,
                       rng: np.random.Generator, n_runs: int = 200) -> np.ndarray:
    """Her coinin ağırlık yolu rastgele başka bir coinin getirisine uygulanır (karışık eşleme, sabit nokta yok)."""
    cols = [c for c in w_hold.columns if (w_hold[c] != 0).any()]
    pool = [c for c in rets.columns]
    out = []
    for _ in range(n_runs):
        tgt = list(rng.permutation(pool))[: len(cols)]
        # sabit noktaları kaldır: kendi getirisine düşen coini havuzdan başka bir coinle değiştir
        for k, c in enumerate(cols):
            if tgt[k] == c:
                alt = [p for p in pool if p not in tgt]
                tgt[k] = alt[int(rng.integers(len(alt)))] if alt else tgt[(k + 1) % len(tgt)]
        r2 = pd.DataFrame({c: rets[t].to_numpy() for c, t in zip(cols, tgt)}, index=rets.index)
        out.append(simple_stats(w_hold[cols], r2, cost_rate, rf))
    return np.vstack(out)


def remove_top_cycles(w_hold: pd.DataFrame, cycles: pd.DataFrame, k: int = 5) -> pd.DataFrame:
    """En kârlı k döngünün ağırlık yolu sıfırlanır (o döngüler hiç açılmamış gibi; nakitte kalınır)."""
    w = w_hold.copy()
    top = cycles.sort_values("profit", ascending=False).head(k)
    for a, od, cd in zip(top["asset"], top["open_date"], top["close_date"]):
        end = w.index[-1] if pd.isna(cd) else pd.Timestamp(cd)
        w.loc[pd.Timestamp(od):end, a] = 0.0
    return w


def drop_year_sharpes(r: pd.Series, rf: pd.Series | None, ppy: int = 365) -> pd.DataFrame:
    """Her yıl için: o yılın günlük getirileri silinip kalanlar zincirlenir → Sharpe ve yıllık getiri."""
    ex = r - (rf.reindex(r.index).fillna(0.0) if rf is not None else 0.0)
    rows = []
    for y in sorted(set(r.index.year)):
        keep = r.index.year != y
        rr, ee = r[keep], ex[keep]
        ann = float((1.0 + rr).prod() ** (ppy / max(len(rr), 1)) - 1.0)
        rows.append({"dropped_year": y, "n_days": int(keep.sum()), "sharpe": sharpe(ee, ppy), "annual_return": ann})
    return pd.DataFrame(rows).set_index("dropped_year")
