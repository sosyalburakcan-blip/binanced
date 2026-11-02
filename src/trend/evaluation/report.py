"""Rapor yardımcıları: tabloyu Markdown'a çevirir (pandas.to_markdown `tabulate` ister; ortamda yok)."""

from __future__ import annotations

import numpy as np
import pandas as pd

PCT_METRICS = {
    "annual_return", "annual_return_simple", "annual_vol", "target_vol", "vol_minus_target",
    "avg_gross_exposure", "max_gross_exposure", "avg_cash_share", "max_drawdown", "time_under_water_frac",
    "turnover_annual", "cost_annual",
    "cash_drag_annual", "win_rate", "top10pct_profit_share", "worst_1d_actual", "worst_1d_at_max_exposure",
    "worst_3d_actual", "worst_3d_at_max_exposure",
}


def _fmt(v, pct: bool, digits: int) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NaT:
        return ""
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, (float, np.floating)):
        return f"{v * 100:.{max(digits - 2, 1)}f}%" if pct else f"{v:.{digits}f}"
    return str(v)


def to_markdown(df: pd.DataFrame, digits: int = 3, pct_rows: set[str] | None = None) -> str:
    """DataFrame → Markdown tablo. `pct_rows` (varsayılan PCT_METRICS) satır adları yüzde biçimlenir."""
    pct_rows = PCT_METRICS if pct_rows is None else pct_rows
    head = "| " + " | ".join([str(df.index.name or "")] + [str(c) for c in df.columns]) + " |"
    sep = "| " + " | ".join(["---"] * (len(df.columns) + 1)) + " |"
    lines = [head, sep]
    for name, row in df.iterrows():
        pct = str(name) in pct_rows
        lines.append("| " + " | ".join([str(name)] + [_fmt(v, pct, digits) for v in row]) + " |")
    return "\n".join(lines)
