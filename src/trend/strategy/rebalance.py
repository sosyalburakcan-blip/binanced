"""Yeniden dengeleme kuralları (SPEC "Strateji" §4 ve "Haftalık giriş, günlük çıkış").

Sıra (her coin için, w = kaymış mevcut ağırlık, w* = hedef):
1. w* = 0 < w            → tamamını sat (minimum işlem eşiğinin altında olsa bile)
2. w = 0 < w*            → hedefe al (giriş)
   w > 0, S ≠ S_son_işlem → hedefe işlem (kademe değişikliği)
3. diğer (w > 0, w* > 0)  → |w − w*| > max(REL·w*, MINB) ise yalnızca bant kenarına
4. çıkış dışı |Δ| < MINTRADE → yapma
5. haftalık: giriş günü değilse Δ > 0 olan (pozisyonu artıran) tüm işlemler atlanır; azaltanlar her gün.

"Pozisyonu artıran/azaltan" Δ'nın işaretiyle belirlenir (varsayım: kademe değişikliği de olsa Δ < 0 ise azaltır).
S karşılaştırması tamsayı S3 = 3·S ile yapılır (kayan nokta eşitliği sorunu olmasın diye).
"""

from __future__ import annotations

import numpy as np

NONE, ENTRY, EXIT, TIER, BAND = 0, 1, 2, 3, 4
SKIP_MINTRADE, SKIP_WEEKLY, SKIP_HARDSTOP, SKIP_MINORDER, FROZEN = -1, -2, -3, -4, -5
REASON_NAMES = {
    NONE: "none", ENTRY: "entry", EXIT: "exit", TIER: "tier", BAND: "band",
    SKIP_MINTRADE: "skip_mintrade", SKIP_WEEKLY: "skip_weekly", SKIP_HARDSTOP: "skip_hardstop",
    SKIP_MINORDER: "skip_minorder", FROZEN: "frozen",
}


def mintrade(nav: float, min_notional: float, mult: float, min_frac: float) -> float:
    """MINTRADE = max(mult × minNotional / NAV, min_frac)."""
    return max(mult * min_notional / nav, min_frac) if nav > 0 else np.inf


def rebalance_orders(
    held: np.ndarray,
    w: np.ndarray,
    w_tgt: np.ndarray,
    s3_now: np.ndarray,
    s3_last: np.ndarray,
    mintrade_frac: float,
    allow_increase: bool,
    drift_rel: float,
    drift_min: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Ağırlık değişimi Δw ve neden kodu döndürür. `held` = adet > 0 (w = 0 ⇔ pozisyon yok)."""
    n = w.shape[0]
    delta = np.zeros(n)
    reason = np.zeros(n, dtype=np.int8)
    pos_t = w_tgt > 0
    exit_ = held & ~pos_t
    entry = ~held & pos_t
    tier = held & pos_t & (s3_now != s3_last)
    other = held & pos_t & ~tier

    delta[exit_] = -w[exit_]
    reason[exit_] = EXIT
    delta[entry] = w_tgt[entry]
    reason[entry] = ENTRY
    delta[tier] = w_tgt[tier] - w[tier]
    reason[tier] = TIER

    band = np.maximum(drift_rel * w_tgt, drift_min)
    dev = w - w_tgt
    over = other & (dev > band)
    under = other & (dev < -band)
    delta[over] = (w_tgt[over] + band[over]) - w[over]
    delta[under] = (w_tgt[under] - band[under]) - w[under]
    reason[over | under] = BAND

    small = (reason > 0) & (reason != EXIT) & (np.abs(delta) < mintrade_frac)
    delta[small] = 0.0
    reason[small] = SKIP_MINTRADE

    if not allow_increase:
        inc = delta > 0
        delta[inc] = 0.0
        reason[inc] = SKIP_WEEKLY
    return delta, reason
