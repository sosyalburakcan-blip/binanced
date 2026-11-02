"""Motor ↔ karar verici (strateji veya kıyas) arayüzü.

Karar verici şu yöntemleri sağlar:
- `required_assets() -> list[str]`: evren dışında da gereken varlıklar (ör. rejim filtresi için BTC).
- `prepare(data: EngineData)`: nedensel ön hesap (gösterge dizileri). Satır t yalnızca ≤ t verisinden üretilmeli.
- `observe(i)`: her takvim günü (ısınma dahil) karar öncesi çağrılır (ör. EWMA korelasyonu güncellemesi).
- `decide(view: DayView) -> Decision`: t kapanışındaki karar.

Motor, kararı t'de kesilmiş veriyle verir: `DayView` yalnızca t'ye kadarki durumdan kurulur; karar verici ön hesap
dizilerinde yalnızca `view.i` satırını okur (CONTRACTS §8; nedensellik zorunlu test 1 ile doğrulanır).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class EngineData:
    days: pd.DatetimeIndex          # kesintisiz takvim günleri (gün etiketi, tz-naive UTC)
    assets: list[str]               # motorun izlediği varlıklar (sütun sırası)
    close: pd.DataFrame             # gün × varlık kapanış (NaN = veri yok)
    cfg: dict                       # load_settings() çıktısı (varyant geçersiz kılmaları uygulanmış)
    btc_idx: int | None             # BTC sütunu (yoksa None)
    quality_flags: pd.DataFrame | None = None
    start_idx: int = 0
    extra: dict = field(default_factory=dict)


@dataclass
class DayView:
    i: int                          # gün satırı
    t: pd.Timestamp                 # karar günü etiketi
    first: bool                     # backtestin ilk karar günü mü
    base: float                     # büyüklük tabanı: bileşik = NAV(t), sabit tutar = başlangıç sermayesi
    nav: float
    qty: np.ndarray                 # adet
    w: np.ndarray                   # kaymış mevcut ağırlık = adet·fiyat/base
    held: np.ndarray                # adet > 0
    frozen: np.ndarray              # t'de kapanış yok (boşluk) → işlem yok, sinyal/ağırlık dondurulur
    univ: np.ndarray                # t kararının evreni (ay(t+1)) üyeliği
    cap: np.ndarray                 # tavan (evren satırı; üye değilse son bilinen)
    force_zero: np.ndarray          # delist duyurusu bilinen veya delist edilmiş varlıklar → hedef 0
    s3_last: np.ndarray             # son işlemdeki etkin S3 (pozisyon yoksa −1)
    mintrade: float                 # MINTRADE (ağırlık cinsinden)


@dataclass
class Decision:
    delta: np.ndarray               # Δw (base cinsinden); çıkışlarda −w
    w_tgt: np.ndarray               # hedef ağırlık w*
    s3: np.ndarray                  # etkin S3 (kıyaslarda −1)
    reason: np.ndarray              # rebalance neden kodu (strategy.rebalance)
    s3_raw: np.ndarray | None = None  # kapılardan (T1/T9) önceki ham sinyal; karar defterine yazılır
