"""Önceden kaydedilmiş varyantlar T0–T10 (SPEC "Ön kayıt") → ayar geçersiz kılmaları ve motor seçenekleri.

Her alt çalıştırma bir `VariantRun`: `overrides` (run_backtest(overrides=...)) ve özel girdi ihtiyacı `params`:
- `exchange_loss_frac` (T6): orkestratör bir tarih seçip `exchange_loss=[(tarih, frac)]` geçer;
- `usdt_only` (T7): evren sağlayıcısı `universe/usdt_only/` dizininden kurulur;
- `close_hour` (T8): `shifted_inputs()` ile kaydırılmış günlük panel + dolum fiyatları, delist tablosu bu panelden.
Stres ve varyant değerleri settings.yaml'dan (`backtest.stress`, `backtest.t8_close_hours`,
`evaluation.core_satellite_core_weights`) okunur.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from trend.backtest.fills import daily_from_hourly, fill_prices_from_settings
from trend.config import load_settings

_S = load_settings()
T5_DELIST_PENALTIES = tuple(_S["backtest"]["stress"]["delist_penalties"])
T6_COST_MULTIPLIER = float(_S["backtest"]["stress"]["cost_multiplier"])
T6_EXCHANGE_LOSSES = tuple(_S["backtest"]["stress"]["exchange_losses"])
T8_CLOSE_HOURS = tuple(_S["backtest"]["t8_close_hours"])
T10_CORE_WEIGHTS = tuple(_S["evaluation"]["core_satellite_core_weights"])


@dataclass
class VariantRun:
    code: str
    overrides: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    note: str = ""


def variant_runs() -> list[VariantRun]:
    """T0–T9 alt çalıştırmalarının listesi (T10 iki NAV yolunun karışımıdır: benchmarks.core_satellite)."""
    runs = [
        VariantRun("T0", note="temel ayar"),
        VariantRun("T1", {"strategy": {"regime_filter": {"enabled": True}}}),
        VariantRun("T3", {"backtest": {"fill": "open_t1"}}),
        VariantRun("T4_0607", {"backtest": {"fill": "vwap_06_07"}}),
        VariantRun("T4_1415", {"backtest": {"fill": "vwap_14_15"}}),
    ]
    runs += [VariantRun(f"T5_{int(p * 100)}", {"backtest": {"delist_penalty": p}}) for p in T5_DELIST_PENALTIES]
    runs.append(VariantRun("T6_cost2", {"backtest": {"cost_multiplier": T6_COST_MULTIPLIER}}))
    runs += [VariantRun(f"T6_loss{int(f * 100)}", params={"exchange_loss_frac": f}) for f in T6_EXCHANGE_LOSSES]
    runs.append(VariantRun("T7", params={"usdt_only": True}))
    runs += [VariantRun(f"T8_h{h:02d}", params={"close_hour": h}) for h in T8_CLOSE_HOURS]
    runs += [VariantRun(f"T8_wd{d}", {"strategy": {"weekly_entry": {"entry_weekday": d}}}) for d in range(6)]
    runs.append(VariantRun("T9", {"strategy": {"relative_strength": {"enabled": True}}}))
    return runs


def shifted_inputs(cfg: dict, panel_1h: dict[str, pd.DataFrame], close_hour: int) -> tuple[dict, pd.DataFrame]:
    """T8: H saatinde kapanan günlük panel ve aynı kaydırmayla dolum fiyatları (dolum günü indeksli)."""
    p1d = daily_from_hourly(panel_1h, close_hour)
    fp = fill_prices_from_settings(cfg, p1d, panel_1h, offset_hours=close_hour)
    return p1d, fp
