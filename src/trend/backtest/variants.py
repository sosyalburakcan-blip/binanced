"""Önceden kaydedilmiş varyantlar T0–T10 (SPEC "Ön kayıt") → ayar geçersiz kılmaları ve motor seçenekleri.

Her alt çalıştırma bir `VariantRun`: `overrides` (run_backtest(overrides=...)) ve özel girdi ihtiyacı `params`:
- `exchange_loss_frac` (T6): orkestratör bir tarih seçip `exchange_loss=[(tarih, frac)]` geçer;
- `usdt_only` (T7): evren sağlayıcısı `universe/usdt_only/` dizininden kurulur;
- `close_hour` (T8): `shifted_inputs()` ile kaydırılmış günlük panel + dolum fiyatları, delist tablosu bu panelden.
Stres değerleri settings.yaml'da olmadığı için burada sabittir (TODO(settings)).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from trend.backtest.fills import daily_from_hourly, fill_prices_from_settings

# TODO(settings): backtest.stress.delist_penalties — T5 zorunlu stres değerleri.
T5_DELIST_PENALTIES = (0.20, 0.50)
# TODO(settings): backtest.stress.cost_multiplier — T6 maliyet çarpanı.
T6_COST_MULTIPLIER = 2.0
# TODO(settings): backtest.stress.exchange_losses — T6 borsadaki varlığın tek seferlik kaybı.
T6_EXCHANGE_LOSSES = (0.20, 0.50)
# TODO(settings): backtest.t8_close_hours — T8 günlük mum kapanış saatleri (UTC).
T8_CLOSE_HOURS = (4, 8, 12, 16, 20)
# TODO(settings): evaluation.core_satellite_weights — T10 çekirdek (BTC-200) payları.
T10_CORE_WEIGHTS = (0.80, 0.50)


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
