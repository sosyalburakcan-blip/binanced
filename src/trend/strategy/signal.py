"""Tamponlu üç vadeli trend sinyali (SPEC "Strateji" §1).

Tüm fonksiyonlar nedenseldir (causal): t satırı yalnızca ≤ t satırlarından hesaplanır. Motor bunları bir kez
hesaplar ve döngüde yalnızca t satırını okur; nedensellik zorunlu test 1 (geleceği görme) ile doğrulanır.

Girdi biçimi: `close` = gün × varlık geniş DataFrame (CONTRACTS §7), eksik değer NaN (taşınmaz).

Varsayımlar (SPEC'in açık bıraktığı yerler):
- EMA, coinin **geçerli (NaN olmayan) kapanışları** üzerinde `ewm(span=n, adjust=False)` ile hesaplanır; boşluk
  günleri atlanır (boşluk kuralı: sinyal dondurulur), seri devam edince EMA son değerden sürer.
- σ_d = takvim günlük log getirilerinin (r_t = ln C_t − ln C_{t−1}; iki uçtan biri eksikse NaN) 30 günlük örneklem
  std'si (ddof=1), en az `vol_min_obs[30]` gözlem; yetersizse son geçerli σ_d taşınır (nedensel ffill).
- Durum makinesi coinin **ilk uygun gününde** (200. geçerli bar) tamponsuz kuralla (C > EMA → 1) başlar ve evren
  üyeliğinden bağımsız olarak sürekli işletilir. Boşluk günlerinde durum değişmez.
- C tam olarak tampon sınırına eşitse durum korunur (SPEC: "aksi halde önceki değer").
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def log_returns(close: pd.DataFrame) -> pd.DataFrame:
    """Takvim günlük log getirisi; t veya t−1 kapanışı eksikse NaN (boşluğu aşan getiri dahil edilmez)."""
    lc = np.log(close.to_numpy(dtype=float))
    r = np.full_like(lc, np.nan)
    r[1:] = lc[1:] - lc[:-1]
    return pd.DataFrame(r, index=close.index, columns=close.columns)


def valid_bar_count(close: pd.DataFrame) -> pd.DataFrame:
    """t gününe kadarki (t dahil) geçerli kapanış sayısı."""
    v = np.isfinite(close.to_numpy(dtype=float))
    return pd.DataFrame(np.cumsum(v, axis=0), index=close.index, columns=close.columns)


def ema_on_valid(close: pd.DataFrame | np.ndarray, span: int) -> np.ndarray:
    """Geçerli kapanışlar üzerinde `ewm(span, adjust=False)`; NaN günlerde NaN döner (değer dondurulur).

    `pd.Series.dropna().ewm(span=span, adjust=False).mean()` ile birebir aynıdır (testte doğrulanır).
    """
    x = close.to_numpy(dtype=float) if isinstance(close, pd.DataFrame) else np.asarray(close, dtype=float)
    alpha = 2.0 / (span + 1.0)
    out = np.full_like(x, np.nan)
    prev = np.full(x.shape[1], np.nan)
    for t in range(x.shape[0]):
        xt = x[t]
        ok = np.isfinite(xt)
        init = ok & ~np.isfinite(prev)
        upd = ok & ~init
        prev = np.where(init, xt, prev)
        prev = np.where(upd, (1.0 - alpha) * prev + alpha * xt, prev)
        out[t] = np.where(ok, prev, np.nan)
    return out


def sma_on_valid(close: pd.Series, window: int) -> pd.Series:
    """Geçerli kapanışlar üzerinde basit ortalama (en az `window` geçerli bar); boşluk günleri NaN."""
    s = close.dropna()
    m = s.rolling(window, min_periods=window).mean()
    return m.reindex(close.index)


def rolling_std(r: pd.DataFrame, window: int, min_obs: int, ffill: bool = True) -> pd.DataFrame:
    """Takvim penceresinde örneklem std (ddof=1), en az `min_obs` gözlem; istenirse son geçerli değer taşınır."""
    sd = r.rolling(window, min_periods=min_obs).std()
    return sd.ffill() if ffill else sd


def buffered_states(
    close: np.ndarray,
    ema: np.ndarray,
    sigma_d: np.ndarray,
    h: float,
    first_eligible: np.ndarray,
) -> np.ndarray:
    """Tek vade için durum s ∈ {0, 1}; uygun olmayan günlerde NaN.

    s(t) = 1 if C > EMA(1 + hσ); 0 if C < EMA(1 − hσ); aksi halde s(t−1). İlk uygun gün f_i'de s = [C > EMA].
    Döngüyle birebir eşdeğer vektörel uygulama: tetik değerleri yazılır, aralar ileri doldurulur.
    """
    n_days, n = close.shape
    with np.errstate(invalid="ignore"):
        up = close > ema * (1.0 + h * sigma_d)
        dn = close < ema * (1.0 - h * sigma_d)
        plain = close > ema
    trig = np.full((n_days, n), np.nan)
    trig[up] = 1.0
    trig[dn] = 0.0
    # boşluk günleri: tetik yok → durum korunur (ffill ile dondurulur)
    trig[~np.isfinite(close)] = np.nan
    rows = np.arange(n_days)[:, None]
    trig[rows < first_eligible[None, :]] = np.nan
    cols = np.nonzero(first_eligible < n_days)[0]
    r0 = first_eligible[cols]
    trig[r0, cols] = plain[r0, cols].astype(float)  # başlangıç: tamponsuz kural
    return pd.DataFrame(trig).ffill().to_numpy()


def first_eligible_index(close: pd.DataFrame, min_bars: int) -> np.ndarray:
    """Her varlık için geçerli kapanış sayısının `min_bars`'a ulaştığı ilk satır (yoksa len(index))."""
    cnt = valid_bar_count(close).to_numpy()
    reached = cnt >= min_bars
    first = np.where(reached.any(axis=0), reached.argmax(axis=0), len(close.index))
    return first.astype(np.int64)


def trend_signal(
    close: pd.DataFrame,
    spans: list[int] | tuple[int, ...],
    h: float,
    min_bars: int,
    sigma_window: int,
    sigma_min_obs: int,
    leak_days: int = 0,
) -> dict[str, np.ndarray]:
    """Tamponlu sinyal: S3 = açık durum sayısı (0..3, S = S3/3), uygun olmayan günlerde −1.

    `leak_days` > 0 YALNIZCA pozitif kontrol testi içindir (zorunlu test 2): sinyal kasıtlı olarak
    `leak_days` gün sonraki kapanışla hesaplanır ve geleceği görme testinin bunu yakalaması beklenir.
    """
    c_df = close.shift(-leak_days) if leak_days else close
    c = c_df.to_numpy(dtype=float)
    first = first_eligible_index(close, min_bars)
    sig_d = rolling_std(log_returns(c_df), sigma_window, sigma_min_obs, ffill=True).to_numpy()
    total = np.zeros(c.shape)
    states = {}
    for n in spans:
        ema = ema_on_valid(c, int(n))
        s = buffered_states(c, ema, sig_d, h, first)
        states[int(n)] = s
        total = total + s
    s3 = np.where(np.isfinite(total), total, -1.0)
    return {"S3": np.rint(s3).astype(np.int8), "first_eligible": first, "sigma_d": sig_d, "states": states}
