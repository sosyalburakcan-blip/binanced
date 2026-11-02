"""G7 karar verici: SPEC "Strateji" sözde kodunun (temel ayar + T1/T9 bayrakları) günlük uygulaması.

her gün t (≤ t verisi):
  E = evren(t) ∩ {≥200 temiz bar} ; H = tutulan ∖ E ; boşluktaki (dondurulmuş) coinler hiç ele alınmaz
  S = tamponlu sinyal ; [T1] rejim KAPALI → S = 0 (BTC hariç) ; [T9] S ← S·g ; delist duyurusu → S = 0
  σ, R (EWMA, küçültülmüş) ; A = {S > 0} ; k* bisection ; w* = S·min(k*·v, CAP) ; i ∈ H: w* = min(w*, w)
  yeniden dengeleme kuralları (+ haftalık giriş)

Varsayımlar:
- "Temiz bar" = geçerli kapanış; tarihe bağlı kalite işaretleri (CONTRACTS §5) verilirse, severity ∈
  `EXCLUDING_SEVERITIES` olan işaretin kapsadığı barlar, işaretin `known_from + 1` karar gününden itibaren sayılmaz.
  Durum makinesinin başlangıcı (ilk uygun gün) işaretlerden bağımsız olarak 200. geçerli bardır.
- Boşluktaki tutulan coin k hesabına girmez; ağırlığı aynen kalır (nakit kısıtı kaldıraçsızlığı garanti eder).
- `sizing="equal"` yalnızca kıyas 6 içindir: w_full = 1/|E| (tavan ve oynaklık hedefi yok), diğer kurallar aynı.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trend.backtest.interface import DayView, Decision, EngineData
from trend.strategy.filters import RelativeStrengthGate, regime_state, relative_strength
from trend.strategy.rebalance import FROZEN, rebalance_orders
from trend.strategy.risk import EwmaCorrelation, annualized_vol, covariance, shrink_to_constant
from trend.strategy.signal import log_returns, trend_signal
from trend.strategy.sizing import solve_k

# TODO(settings): quality.excluding_severities — temiz bar sayımından düşen işaret türleri (CONTRACTS §5).
EXCLUDING_SEVERITIES = ("error", "exclude")
# TODO(settings): universe.btc_asset — BTC'nin asset_id'si (rejim filtresi, T9, BTC-200).
BTC_ASSET = "BTCUSDT"


def min_obs_for(table: dict, window: int) -> int:
    """settings.strategy.vol_min_obs anahtarı int veya str olabilir (YAML / geçersiz kılma)."""
    return int(table[window] if window in table else table[str(window)])


def clean_bar_count(close: pd.DataFrame, flags: pd.DataFrame | None) -> np.ndarray:
    """Karar günü T için temiz bar sayısı: geçerli barlar − (T'de bilinen dışlayıcı işaretlerin kapsadığı barlar)."""
    valid = np.isfinite(close.to_numpy(dtype=float))
    n_days, n = valid.shape
    if flags is None or len(flags) == 0:
        return np.cumsum(valid, axis=0)
    days = pd.DatetimeIndex(close.index)
    col = {str(c): j for j, c in enumerate(close.columns)}
    excl = np.full((n_days, n), n_days, dtype=np.int64)  # bar b'nin sayımdan düştüğü ilk karar günü
    f = flags[flags["severity"].isin(EXCLUDING_SEVERITIES)]
    for sym, ps, pe, kf in zip(f["symbol"].astype(str), f["period_start"], f["period_end"], f["known_from"]):
        j = col.get(sym)
        if j is None:
            continue
        a = int(days.searchsorted(pd.Timestamp(ps), side="left"))
        b = int(days.searchsorted(pd.Timestamp(pe), side="right"))
        k = int(days.searchsorted(pd.Timestamp(kf).floor("D"), side="left")) + 1  # known_from ≤ T−1
        if a < b:
            excl[a:b, j] = np.minimum(excl[a:b, j], max(k, 0))
    inc = np.zeros((n_days + 1, n), dtype=np.int64)
    inc[:n_days] += valid
    rb, cb = np.nonzero(valid & (excl < n_days))
    rem = np.maximum(excl[rb, cb], rb)
    np.add.at(inc, (rem, cb), -1)
    return np.cumsum(inc[:n_days], axis=0)


class TrendStrategy:
    """Tamponlu trend + oynaklık hedefli büyüklük + yeniden dengeleme (G7)."""

    def __init__(self, sizing: str = "vol", btc: str = BTC_ASSET, leak_days: int = 0):
        if sizing not in ("vol", "equal"):
            raise ValueError(sizing)
        self.sizing, self.btc, self.leak_days = sizing, btc, leak_days

    def required_assets(self) -> list[str]:
        return [self.btc]

    def prepare(self, data: EngineData) -> None:
        s = data.cfg["strategy"]
        self.s = s
        close = data.close
        sig = trend_signal(close, s["spans"], float(s["buffer_h"]), int(s["min_signal_bars"]),
                           int(s["sigma_d_window"]), min_obs_for(s["vol_min_obs"], int(s["sigma_d_window"])),
                           leak_days=self.leak_days)
        self.S3 = sig["S3"]
        self.clean_ok = clean_bar_count(close, data.quality_flags) >= int(s["min_signal_bars"])
        self.sigma = annualized_vol(close, s["vol_windows"], s["vol_min_obs"], float(s["vol_floor"]),
                                    int(s["annualization_days"]))
        self.ret = log_returns(close).to_numpy()
        self.corr = EwmaCorrelation(len(data.assets), float(s["corr_halflife_days"]))
        self.btc_idx = data.btc_idx
        n = len(data.assets)
        self.nonbtc = np.ones(n, dtype=bool)
        if self.btc_idx is not None:
            self.nonbtc[self.btc_idx] = False
        rf = s["regime_filter"]
        self.regime = None
        if rf["enabled"]:
            if self.btc_idx is None:
                raise ValueError("rejim filtresi için BTC verisi gerekli")
            self.regime = regime_state(close.iloc[:, self.btc_idx], int(rf["sma"]), float(rf["off_below"]),
                                       float(rf["on_above"]))
        rs = s["relative_strength"]
        self.rel = None
        if rs["enabled"]:
            if self.btc_idx is None:
                raise ValueError("T9 için BTC verisi gerekli")
            self.rel = relative_strength(close, data.assets[self.btc_idx], int(rs["lookback"]))
            self.gate = RelativeStrengthGate(n, float(rs["upper_q"]), float(rs["lower_q"]), float(rs["exit_rel"]))
        we = s["weekly_entry"]
        self.weekly, self.entry_wd = bool(we["enabled"]), int(we["entry_weekday"])
        rb = s["rebalance"]
        self.drift_rel, self.drift_min = float(rb["drift_rel"]), float(rb["drift_min"])
        self.tgt, self.gmax, self.tol = float(s["target_vol"]), float(s["gross_max"]), float(s["bisection_tol"])
        self.alpha = float(s["corr_shrinkage"])
        self.min_cap = min(float(t["cap"]) for t in data.cfg["universe"]["tiers"].values())
        self.last_k = np.nan

    def observe(self, i: int) -> None:
        self.corr.update(self.ret[i])

    def decide(self, v: DayView) -> Decision:
        i = v.i
        n = v.w.shape[0]
        E = v.univ & self.clean_ok[i]
        H = v.held & ~E
        cand = (E | H) & ~v.frozen
        s3 = np.where(cand, np.maximum(self.S3[i], 0), 0).astype(np.int64)
        s3_raw = np.where(cand, self.S3[i], -1).astype(np.int64)
        if self.regime is not None and not (self.regime[i] == 1.0):
            s3[self.nonbtc] = 0
        if self.rel is not None:
            g = self.gate.step(self.rel[i], E & ~v.frozen, cand, self.btc_idx)
            s3 = s3 * g
        s3[v.force_zero] = 0
        sig = self.sigma[i]
        A = cand & (s3 > 0) & np.isfinite(sig)
        idx = np.nonzero(A)[0]
        w_full = np.zeros(n)
        if idx.size:
            if self.sizing == "vol":
                vv = 1.0 / sig[idx]
                cap = np.where(np.isfinite(v.cap[idx]), v.cap[idx], self.min_cap)  # tavanı bilinmeyen: en küçük
                R = shrink_to_constant(self.corr.corr(idx), self.alpha)
                k, wf = solve_k(vv, cap, covariance(sig[idx], R), self.tgt, self.gmax, self.tol)
                self.last_k = k
            else:
                wf = np.full(idx.size, 1.0 / max(int(E.sum()), 1))
            w_full[idx] = wf
        w_tgt = s3 / 3.0 * w_full
        w_tgt[H] = np.minimum(w_tgt[H], v.w[H])
        allow_inc = (not self.weekly) or (v.t.weekday() == self.entry_wd)
        delta, reason = rebalance_orders(v.held & cand, v.w, w_tgt, s3, v.s3_last, v.mintrade, allow_inc,
                                         self.drift_rel, self.drift_min)
        delta[~cand] = 0.0
        reason[~cand] = 0
        reason[v.frozen & v.held] = FROZEN
        w_tgt[~cand & v.held] = v.w[~cand & v.held]  # dondurulmuş: hedef = mevcut
        return Decision(delta=delta, w_tgt=w_tgt, s3=s3, reason=reason, s3_raw=s3_raw)
