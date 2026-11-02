"""Uydu payı kuralı (SPEC "Ön kayıt → Uydu payı kuralı"; birincil hipotez reddedilirse uygulanır).

    0,5 · SR_T0^net > ρ · SR_BTC200^net  →  alt-coin sistemi payı %20, aksi halde %0

SR'ler tam dönem net Sharpe (hazine bonosu üzerinde, √365), ρ iki stratejinin günlük getiri korelasyonu (Pearson).
0,5 çarpanı ve %20 pay settings `evaluation.satellite` (haircut, weight). Takdire dayalı artırım yok. Koşul, uyduyu
eklemenin portföy Sharpe'ını artırması için gereken SR_uydu > ρ·SR_çekirdek eşiğinin indirimli hâlidir.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from trend.evaluation.common import periods_per_year, settings
from trend.evaluation.metrics import sharpe_ratio


def satellite_weight(
    sr_t0: float, sr_btc200: float, rho: float, haircut: float | None = None, weight: float | None = None,
    cfg: dict[str, Any] | None = None,
) -> float:
    s = settings(cfg)["evaluation"]["satellite"]
    haircut = float(s["haircut"] if haircut is None else haircut)
    weight = float(s["weight"] if weight is None else weight)
    return weight if haircut * sr_t0 > rho * sr_btc200 else 0.0


def satellite_from_returns(
    t0: pd.Series, btc200: pd.Series, rf: pd.Series | float | None = None, cfg: dict[str, Any] | None = None
) -> dict[str, float]:
    """Net günlük getirilerden (ortak günler) SR'ler, ρ ve kural sonucu."""
    cfg = settings(cfg)
    ppy = periods_per_year(cfg)
    df = pd.concat([t0.rename("t0"), btc200.rename("b")], axis=1, join="inner").dropna()
    sr_t0, sr_b = sharpe_ratio(df["t0"], rf, ppy), sharpe_ratio(df["b"], rf, ppy)
    rho = float(df["t0"].corr(df["b"]))
    h = float(cfg["evaluation"]["satellite"]["haircut"])
    return {"sr_t0": sr_t0, "sr_btc200": sr_b, "rho": rho, "lhs": h * sr_t0, "rhs": rho * sr_b,
            "weight": satellite_weight(sr_t0, sr_b, rho, cfg=cfg), "n_obs": int(len(df))}
