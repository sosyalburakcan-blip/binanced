"""T1 BTC rejim filtresi ve T9 Bitcoin'e göre güç kapısı (SPEC "Strateji" §5 ve "Bitcoin'e göre güç filtresi").

Varsayımlar:
- SMA200, BTC'nin geçerli kapanışları üzerinde (en az 200 bar). Rejim durumu SMA ilk tanımlandığı gün
  C > SMA ise AÇIK ile başlar; öncesinde tanımsızdır ve KAPALI sayılır (kötümser). BTC boşluk gününde durum korunur.
- T9: rel_i(t) takvim t−30 kapanışıyla hesaplanır; C_i(t), C_i(t−30), BTC(t), BTC(t−30) ve ≥ 30 geçerli bar şart.
  Tanımsızsa g = 0 ve durum sıfırlanır (sonraki tanımlı günde başlangıç kuralı uygulanır).
- Yüzdelik sıra q = ortalama-sıra / n, evren (E) içindeki BTC dışı, rel'i tanımlı coinler arasında (pandas
  `rank(pct=True)` ile aynı). Evrenden çıkmış ama tutulan (H) coin için q, E'ye eklenmiş gibi hesaplanır
  (E'nin sıralamasını değiştirmez).
- Kapı durumu, coin E ∪ H dışına çıktığında sıfırlanır; T9 durumu backtest başlangıcında başlar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trend.strategy.signal import sma_on_valid, valid_bar_count


def regime_state(btc_close: pd.Series, sma_window: int, off_below: float, on_above: float) -> np.ndarray:
    """1 = AÇIK, 0 = KAPALI, NaN = tanımsız (SMA yok). Histerezisli durum makinesi (ileri doldurma ile)."""
    c = btc_close.to_numpy(dtype=float)
    sma = sma_on_valid(btc_close, sma_window).to_numpy()
    n = c.shape[0]
    trig = np.full(n, np.nan)
    with np.errstate(invalid="ignore"):
        trig[c < off_below * sma] = 0.0
        trig[c > on_above * sma] = 1.0
    ok = np.isfinite(sma) & np.isfinite(c)
    if ok.any():
        f = int(np.argmax(ok))
        trig[:f] = np.nan
        trig[f] = 1.0 if c[f] > sma[f] else 0.0
    return pd.Series(trig).ffill().to_numpy()


def relative_strength(close: pd.DataFrame, btc_col: str, lookback: int) -> np.ndarray:
    """rel_i(t) = ln(C_i(t)/C_i(t−L)) − ln(BTC(t)/BTC(t−L)); tanımsızsa NaN. BTC sütunu NaN."""
    c = close.to_numpy(dtype=float)
    lc = np.log(c)
    past = np.full_like(lc, np.nan)
    past[lookback:] = lc[:-lookback]
    own = lc - past
    j = close.columns.get_loc(btc_col) if btc_col in close.columns else None
    if j is None:
        return np.full_like(lc, np.nan)
    rel = own - own[:, [j]]
    cnt = valid_bar_count(close).to_numpy()
    rel[cnt < lookback] = np.nan
    rel[:, j] = np.nan
    return rel


def _avg_rank_pct(x: np.ndarray) -> np.ndarray:
    """Ortalama-sıra / n (pandas rank(pct=True, method='average'))."""
    return pd.Series(x).rank(method="average", pct=True).to_numpy()


def _inserted_pct(ref: np.ndarray, x: float) -> float:
    """x, ref kümesine eklenmiş olsaydı ortalama-sıra / (n+1)."""
    less = float(np.sum(ref < x))
    ties = float(np.sum(ref == x))
    return (less + (ties + 2.0) / 2.0) / (ref.size + 1.0)


class RelativeStrengthGate:
    """Durum makinesi: q ≥ upper ve rel > 0 → 1; q < lower veya rel < exit_rel → 0; arada önceki değer."""

    def __init__(self, n_assets: int, upper_q: float, lower_q: float, exit_rel: float):
        self.upper, self.lower, self.exit_rel = upper_q, lower_q, exit_rel
        self.state = np.full(n_assets, -1, dtype=np.int8)  # −1 = başlatılmamış

    def step(self, rel: np.ndarray, in_universe: np.ndarray, cand: np.ndarray, btc_idx: int | None) -> np.ndarray:
        """Bugünün kapısı g (0/1) — `cand` (E ∪ H) dışı ve BTC için anlamsız; BTC için 1 döner."""
        n = rel.shape[0]
        g = np.zeros(n, dtype=np.int8)
        nonbtc = np.ones(n, dtype=bool)
        if btc_idx is not None:
            nonbtc[btc_idx] = False
        valid = np.isfinite(rel)
        ref_mask = in_universe & nonbtc & valid
        ref_idx = np.nonzero(ref_mask)[0]
        q = np.full(n, np.nan)
        if ref_idx.size:
            q[ref_idx] = _avg_rank_pct(rel[ref_idx])
            ref_vals = rel[ref_idx]
            for i in np.nonzero(cand & nonbtc & valid & ~in_universe)[0]:
                q[i] = _inserted_pct(ref_vals, rel[i])
        upd = cand & nonbtc & valid & np.isfinite(q)
        on = upd & (q >= self.upper) & (rel > 0)
        off = upd & ((q < self.lower) | (rel < self.exit_rel))
        prev = self.state
        new = np.where(on, 1, np.where(off, 0, prev)).astype(np.int8)
        init = upd & (prev < 0)
        new[init] = np.where(on[init], 1, 0)
        new[~upd] = -1  # tanımsız veya aday değil → sıfırla
        self.state = new
        g[upd] = (new[upd] == 1).astype(np.int8)
        if btc_idx is not None:
            g[btc_idx] = 1
        return g
