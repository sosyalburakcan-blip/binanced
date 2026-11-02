"""Defterler: dolum defteri, döngü defteri (SPEC "Muhasebe") ve altın kayıt serileştirmesi (zorunlu test 5).

Döngü: ağırlığı 0'dan pozitife taşıyan ilk dolumdan tekrar 0'a indiren doluma kadar. Döngü kârı (`profit`) = tüm
dolumların nakit akışı (komisyon, kayma, delist cezası dahil); dönem sonunda açık döngü piyasa değeriyle "open"
(`is_open`) işaretlenir. Kazanan = kâr > 0. Süre = son dolum − ilk dolum (gün). Kolon adları evaluation.metrics
sözleşmesiyle uyumludur (asset, open_date, close_date, profit, is_open).
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import numpy as np
import pandas as pd

FILL_COLUMNS = [
    "date", "decision_date", "asset", "side", "kind", "qty", "vwap", "price", "slippage", "slippage_cost",
    "commission", "penalty_cost", "notional", "cash_flow", "qty_after", "post_weight",
]
CYCLE_COLUMNS = [
    "asset", "cycle", "open_date", "close_date", "last_fill", "n_fills", "invested", "proceeds",
    "market_value", "profit", "ret", "win", "is_open", "status", "duration_days",
]
DECISION_COLUMNS = ["date", "asset", "s3_raw", "s3", "w", "w_tgt", "delta", "qty", "reason"]


def build_cycles(fills: pd.DataFrame, end_qty: dict[str, float], end_px: dict[str, float],
                 end_date: pd.Timestamp) -> pd.DataFrame:
    """Dolum defterinden döngü defteri. `end_qty`/`end_px`: dönem sonu adet ve değerleme fiyatı (açık döngüler)."""
    rows = []
    if len(fills):
        for asset, g in fills.groupby("asset", sort=True):
            cyc = None
            n = 0
            for date, qa, cf in zip(g["date"], g["qty_after"], g["cash_flow"]):
                if cyc is None:
                    if qa <= 0:
                        continue  # artık/kapanış dolumu (döngü dışı) — olmamalı
                    n += 1
                    cyc = {"asset": asset, "cycle": n, "open_date": date, "last_fill": date, "n_fills": 0,
                           "invested": 0.0, "proceeds": 0.0}
                cyc["n_fills"] += 1
                cyc["last_fill"] = date
                if cf < 0:
                    cyc["invested"] += -cf
                else:
                    cyc["proceeds"] += cf
                if qa <= 0:
                    cyc.update(close_date=date, market_value=0.0, status="closed")
                    rows.append(cyc)
                    cyc = None
            if cyc is not None:
                mv = float(end_qty.get(asset, 0.0)) * float(end_px.get(asset, np.nan))
                cyc.update(close_date=pd.NaT, market_value=mv, status="open")
                rows.append(cyc)
    derived = ("profit", "ret", "win", "is_open", "duration_days")
    out = pd.DataFrame(rows, columns=[c for c in CYCLE_COLUMNS if c not in derived])
    out["profit"] = out["proceeds"] + out["market_value"] - out["invested"]
    out["ret"] = out["profit"] / out["invested"].where(out["invested"] > 0)
    out["win"] = out["profit"] > 0
    out["is_open"] = out["status"] == "open"
    out["duration_days"] = (pd.to_datetime(out["last_fill"]) - pd.to_datetime(out["open_date"])).dt.days
    return out[CYCLE_COLUMNS]


def _canon_csv(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False, float_format="%.17g", lineterminator="\n", date_format="%Y-%m-%d")
    return buf.getvalue().encode("utf-8")


def golden_bytes(result) -> bytes:
    """Tüm karar geçmişi + dolumlar + günlük NAV'ın kanonik bayt dizisi (bayt bayt karşılaştırma için)."""
    parts = [b"#decisions\n", _canon_csv(result.decisions[DECISION_COLUMNS]),
             b"#fills\n", _canon_csv(result.fills[FILL_COLUMNS]),
             b"#daily\n", _canon_csv(result.daily.reset_index()[["date", "nav", "cash"]])]
    return b"".join(parts)


def golden_digest(result) -> str:
    return hashlib.sha256(golden_bytes(result)).hexdigest()


def save_golden(result, path: str | Path) -> str:
    """Altın kaydı yazar (G12'de kilitte kaydedilecek); sha256 döndürür."""
    b = golden_bytes(result)
    Path(path).write_bytes(b)
    return hashlib.sha256(b).hexdigest()


def compare_golden(result, path: str | Path) -> tuple[bool, str]:
    """Kayıtlı altın kayıtla bayt bayt karşılaştırır; (eşit mi, ilk fark satırının açıklaması)."""
    new = golden_bytes(result)
    old = Path(path).read_bytes()
    if new == old:
        return True, ""
    a, b = old.split(b"\n"), new.split(b"\n")
    for k, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return False, f"satır {k + 1}: kayıt={x[:200]!r} yeni={y[:200]!r}"
    return False, f"uzunluk farkı: kayıt={len(a)} satır, yeni={len(b)} satır"
