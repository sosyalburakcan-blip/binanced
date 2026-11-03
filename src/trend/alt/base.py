"""Araştırma v2 aday stratejileri için ortak karar verici (PREREGISTRATION_v2 §4 "Yürütme").

Bir aday yalnızca iki şey tanımlar:
- `compute(data)`: `prepare` içinde çağrılır; nedensel ön hesap dizileri (satır i yalnızca ≤ i verisinden).
- `target(j, v) -> np.ndarray`: j satırının bilgisiyle hedef ağırlıklar (≥ 0, motor varlık sırası). Normalde j = i;
  kontrollerde j = i − lag (lag > 0 gecikme, lag < 0 pozitif kontrol: geleceğin satırı). j aralık dışıysa hedef 0.

Ortak yürütme (tüm adaylar için aynı):
- Hedeften sonra sırayla: delist/duyuru (`force_zero`) → 0; `use_universe` ise evren dışı → 0; `apply_cap` ise
  evren kademe tavanı; brüt > 1 ise orantılı küçültme.
- Yeniden dengeleme günü: ilk karar günü ve sonra her `every` günde bir (`every="monthly"`: ayın son günü, dolum
  ayın 1'i). Yeniden dengeleme gününde hedefe işlem yapılır; |w − w*| ≤ max(band·w*, MINTRADE) ise yapılmaz.
- Ara günlerde: hedefi 0 olan tutulan pozisyon her gün tamamen satılır (`exit_daily`, varsayılan açık); dolumu
  yapılamamış girişler (hedef > 0, pozisyon yok, son yeniden dengelemede istenmiş) her gün yeniden denenir.
- `hold_targets` (kesitsel adaylar): hedef yalnızca yeniden dengeleme gününde `target`'tan hesaplanır ve sonraki
  yeniden dengelemeye kadar tutulur; delist (`force_zero`) ve evren dışı maskesi yine her gün uygulanır. Böylece
  seçilen sepet E gün tutulur (her gün yeniden sıralanıp toparlanan coin hafta ortasında satılmaz).
- Boşluk gününde (`frozen`) işlem yok. Çıkış her zaman tam; çıkış dışı işlemde |Δ| < MINTRADE ise yapılmaz.
- Sert sınır yok (motor `hard_stop=False` ile çağrılır; runner'da `alt:` türleri STOP_KINDS'de değil).

Oynaklık hedefli boyutlandırma (`vol_target_weights`): ham ağırlıklar (ör. 1/σ_i) seçili sepetin son `window` günlük
basit getirilerinden kurulan kovaryansla ölçeklenir: k = σ* / √(wᵀΣw·365); ortak gözlem < `min_obs` ise sepetteki
tüm korelasyonlar 1 kabul edilir (kötümser). Sonra kademe tavanı ve brüt ≤ 1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trend.backtest.interface import DayView, Decision, EngineData
from trend.strategy.rebalance import ENTRY, EXIT, SKIP_MINTRADE, TIER

ANN = 365.0


def log_returns(C: np.ndarray) -> np.ndarray:
    """Ardışık geçerli kapanışlar arası log getiri; boşluktan sonraki ilk getiri NaN (boşluğu aşan getiri yok)."""
    r = np.full_like(C, np.nan)
    r[1:] = np.log(C[1:] / C[:-1])
    return r


def rolling_vol(C: np.ndarray, window: int, min_obs: int) -> np.ndarray:
    """Yıllıklandırılmış gerçekleşen oynaklık: son `window` takvim günündeki log getirilerin std'si (ddof=1),
    en az `min_obs` gözlem; satır i yalnızca ≤ i verisinden."""
    r = pd.DataFrame(log_returns(C))
    return (r.rolling(window, min_periods=min_obs).std(ddof=1) * np.sqrt(ANN)).to_numpy()


def vol_target_weights(raw: np.ndarray, sel: np.ndarray, R: np.ndarray, i: int, sigma_target: float,
                       window: int, min_obs: int, cap: np.ndarray | None = None) -> np.ndarray:
    """Seçili varlıkların ham ağırlıklarını portföy oynaklığı σ*'a ölçekler (bkz. modül notu). R: basit getiri."""
    w = np.zeros(raw.shape[0])
    idx = np.flatnonzero(sel & np.isfinite(raw) & (raw > 0))
    if idx.size == 0:
        return w
    w_raw = raw[idx] / raw[idx].sum()
    lo = max(0, i - window + 1)
    sub = R[lo: i + 1][:, idx]
    full = np.all(np.isfinite(sub), axis=1)
    if full.sum() >= min_obs:
        cov = np.cov(sub[full], rowvar=False, ddof=1)
        cov = np.atleast_2d(cov)
        var = float(w_raw @ cov @ w_raw)
    else:
        sd = np.array([np.nanstd(sub[:, k], ddof=1) if np.isfinite(sub[:, k]).sum() >= 2 else np.nan
                       for k in range(idx.size)])
        if not np.isfinite(sd).all():
            return w
        var = float((w_raw * sd).sum() ** 2)          # tüm korelasyonlar 1
    if not np.isfinite(var) or var <= 0:
        return w
    k = sigma_target / np.sqrt(var * ANN)
    w[idx] = w_raw * k
    if cap is not None:
        c = np.where(np.isfinite(cap), cap, np.inf)
        w = np.minimum(w, c)
    g = w.sum()
    if g > 1.0:
        w /= g
    return w


class AltStrategy:
    """Ortak yürütme; alt sınıflar `compute` ve `target`'ı tanımlar (bkz. modül notu)."""

    name = "alt"
    use_universe = False          # True: yalnızca t kararının evren üyeleri (ay(t+1))
    apply_cap = False             # True: evren kademe tavanı
    exit_daily = True
    hold_targets = False          # True: hedef yalnızca yeniden dengeleme gününde hesaplanır ve tutulur

    def __init__(self, every: int | str = 1, band: float = 0.0, lag: int = 0, assets: tuple[str, ...] = ()):
        if not (every == "monthly" or (isinstance(every, int) and every >= 1)):
            raise ValueError(f"every: {every!r}")
        self.every, self.band, self.lag, self.assets_fixed = every, float(band), int(lag), tuple(assets)

    # --- motor arayüzü ---
    def required_assets(self) -> list[str]:
        return list(self.assets_fixed)

    def prepare(self, data: EngineData) -> None:
        self.data = data
        self.col = {a: j for j, a in enumerate(data.assets)}
        self.C = data.close.to_numpy(dtype=float)
        self.R = np.full_like(self.C, np.nan)
        self.R[1:] = self.C[1:] / self.C[:-1] - 1.0
        self.n_days = self.C.shape[0]
        self.i0 = None
        self.pending = np.zeros(len(data.assets), dtype=bool)
        self.held_wt = None
        self.compute(data)

    def observe(self, i: int) -> None:
        pass

    # --- alt sınıf kancaları ---
    def compute(self, data: EngineData) -> None:
        raise NotImplementedError

    def target(self, j: int, v: DayView) -> np.ndarray:
        raise NotImplementedError

    # --- ortak ---
    def is_rebalance(self, v: DayView) -> bool:
        if v.first or self.i0 is None:
            self.i0 = v.i
            return True
        if self.every == "monthly":
            return (v.t + pd.Timedelta(days=1)).day == 1
        return (v.i - self.i0) % int(self.every) == 0

    def decide(self, v: DayView) -> Decision:
        n = v.w.shape[0]
        j = v.i - self.lag
        reb = self.is_rebalance(v)
        if self.hold_targets and not reb and self.held_wt is not None:
            wt = self.held_wt.copy()
        else:
            wt = np.zeros(n)
            if 0 <= j < self.n_days:
                wt = np.nan_to_num(np.asarray(self.target(j, v), dtype=float), nan=0.0)
                wt = np.maximum(wt, 0.0)
            if self.hold_targets:
                self.held_wt = wt.copy()
        wt[v.force_zero] = 0.0
        if self.use_universe:
            wt[~v.univ] = 0.0
        if self.apply_cap:
            wt = np.minimum(wt, np.where(np.isfinite(v.cap), v.cap, np.inf))
        g = wt.sum()
        if g > 1.0:
            wt = wt / g
        live = ~v.frozen
        delta = np.zeros(n)
        reason = np.zeros(n, dtype=np.int8)
        ex = live & v.held & (wt <= 0) & (reb | self.exit_daily)
        delta[ex] = -v.w[ex]
        reason[ex] = EXIT
        if reb:
            self.pending = (wt > 0) & ~v.held
            act = live & (wt > 0)
        else:
            self.pending &= (wt > 0) & ~v.held
            act = live & self.pending
        new = act & ~v.held
        delta[new] = wt[new]
        reason[new] = ENTRY
        adj = act & v.held
        dif = wt - v.w
        thr = np.maximum(self.band * wt, v.mintrade)
        do = adj & (np.abs(dif) > thr)
        delta[do] = dif[do]
        reason[do] = TIER
        small = (new | do) & (np.abs(delta) < v.mintrade)
        delta[small] = 0.0
        reason[small] = SKIP_MINTRADE
        return Decision(delta=delta, w_tgt=wt, s3=np.full(n, -1, dtype=np.int64), reason=reason)
