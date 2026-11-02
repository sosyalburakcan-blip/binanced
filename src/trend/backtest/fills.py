"""Dolum fiyatları (SPEC "Dolum fiyatı", CONTRACTS §1) ve T8 için kaydırılmış günlük mumlar.

Dolum fiyatı çerçevesi **dolum günü** indekslidir: satır d = d gününün penceresindeki fiyat; t kararının emirleri
satır t+1 ile dolar (CONTRACTS: [t+1 00:00, t+1 02:00) VWAP'ı). Delist kapanışı son işlem günü L'nin satırını kullanır.

- VWAP = Σ quote_volume / Σ volume (tipik fiyat × hacim kullanılmaz). Pencerede hacim sıfırsa bir sonraki saat
  eklenir; mum (blok) sonuna kadar hacim bulunamazsa NaN (o gün dolum yok — emir atlanır; varsayım).
- T3: t+1 açılışı = günlük `open` (satır d = d mumunun açılışı).
- T8: blok d = [d H:00, d+1 H:00); günlük mum ve dolum pencereleri aynı kaydırmayla kurulur.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


def _hour_blocks(frame: pd.DataFrame, offset_hours: int) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """Saatlik çerçeveyi (gün, 24, varlık) bloklarına böler; blok d = [d + offset, d + 1 gün + offset)."""
    idx = pd.DatetimeIndex(frame.index).as_unit("ns")
    off = pd.Timedelta(hours=offset_hours)
    d0 = (idx.min() - off).floor("D")
    d1 = (idx.max() - off).floor("D")
    days = pd.date_range(d0, d1, freq="D").as_unit("ns")
    grid = pd.date_range(d0 + off, periods=len(days) * 24, freq="h").as_unit("ns")
    f = frame.copy()
    f.index = idx
    arr = f.reindex(grid).to_numpy(dtype=float).reshape(len(days), 24, frame.shape[1])
    return days, arr


def vwap_fill_prices(
    panel_1h: dict[str, pd.DataFrame],
    start_hour: int,
    end_hour: int,
    offset_hours: int = 0,
) -> pd.DataFrame:
    """Dolum günü indeksli VWAP: blok içinde [start_hour, end_hour) saatleri, hacim sıfırsa sonraki saat eklenir."""
    qv_f, v_f = panel_1h["quote_volume"], panel_1h["volume"]
    days, Q = _hour_blocks(qv_f, offset_hours)
    _, V = _hour_blocks(v_f[qv_f.columns], offset_hours)
    Q = np.nan_to_num(Q[:, start_hour:, :], nan=0.0)
    V = np.nan_to_num(V[:, start_hour:, :], nan=0.0)
    cq = np.cumsum(Q, axis=1)
    cv = np.cumsum(V, axis=1)
    base = end_hour - start_hour - 1
    ok = cv[:, base:, :] > 0
    has = ok.any(axis=1)
    k = base + ok.argmax(axis=1)
    num = np.take_along_axis(cq, k[:, None, :], axis=1)[:, 0, :]
    den = np.take_along_axis(cv, k[:, None, :], axis=1)[:, 0, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        px = np.where(has, num / den, np.nan)
    px[~(px > 0)] = np.nan
    return pd.DataFrame(px, index=days, columns=qv_f.columns)


def open_fill_prices(panel_1d: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """T3: dolum = günlük mumun açılışı (satır d = d mumunun açılışı)."""
    o = panel_1d["open"].copy()
    o.index = pd.DatetimeIndex(o.index).as_unit("ns")
    return o.where(o > 0)


def daily_from_hourly(panel_1h: dict[str, pd.DataFrame], close_hour: int = 0) -> dict[str, pd.DataFrame]:
    """T8: blok d = [d H:00, d+1 H:00) saatlerinden günlük mum (etiket d). H = 0 standart UTC günüdür.

    open = bloktaki ilk geçerli saatin açılışı, close = son geçerli saatin kapanışı; hacimler toplam.
    Bloğun hiç verisi yoksa NaN (boşluk).
    """
    out: dict[str, pd.DataFrame] = {}
    days, O = _hour_blocks(panel_1h["open"], close_hour)
    cols = panel_1h["open"].columns
    valid = np.isfinite(O)
    has = valid.any(axis=1)
    first = valid.argmax(axis=1)
    out["open"] = np.where(has, np.take_along_axis(O, first[:, None, :], axis=1)[:, 0, :], np.nan)
    _, C = _hour_blocks(panel_1h["close"][cols], close_hour)
    vc = np.isfinite(C)
    last = 23 - vc[:, ::-1, :].argmax(axis=1)
    out["close"] = np.where(vc.any(axis=1), np.take_along_axis(C, last[:, None, :], axis=1)[:, 0, :], np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # tümü NaN bloklar (boşluk) → NaN
        if "high" in panel_1h:
            out["high"] = np.nanmax(_hour_blocks(panel_1h["high"][cols], close_hour)[1], axis=1)
        if "low" in panel_1h:
            out["low"] = np.nanmin(_hour_blocks(panel_1h["low"][cols], close_hour)[1], axis=1)
    for k in ("volume", "quote_volume", "trades"):
        if k in panel_1h:
            a = _hour_blocks(panel_1h[k][cols], close_hour)[1]
            s = np.nansum(a, axis=1)
            out[k] = np.where(np.isfinite(a).any(axis=1), s, np.nan)
    return {k: pd.DataFrame(v, index=days, columns=cols) for k, v in out.items()}


def fill_prices_from_settings(
    cfg: dict,
    panel_1d: dict[str, pd.DataFrame],
    panel_1h: dict[str, pd.DataFrame] | None,
    offset_hours: int = 0,
) -> pd.DataFrame:
    """settings.backtest.fill'e göre dolum fiyatı çerçevesi (vwap_00_02 | open_t1 | vwap_06_07 | vwap_14_15)."""
    mode = cfg["backtest"]["fill"]
    if mode == "open_t1":
        return open_fill_prices(panel_1d)
    if panel_1h is None:
        raise ValueError(f"fill={mode!r} için 1h panel (veya hazır fill_px) gerekli")
    h0, h1 = cfg["backtest"]["fill_windows"][mode]
    return vwap_fill_prices(panel_1h, int(h0), int(h1), offset_hours=offset_hours)
