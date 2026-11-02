"""Kıyaslar (SPEC "Ön kayıt" BTC-200, "Değerlendirme → Kıyaslar") ve T10 çekirdek–uydu karışımı.

Her kıyas bir **hedef ağırlık çerçevesi** (karar günü × varlık) üretir ve AYNI motorda `TargetWeightStrategy` ile
çalışır: aynı dolum, aynı maliyet, aynı nakit faizi, aynı delist/boşluk kuralları.

Yürütme politikası (varsayım; SPEC kıyaslar için bant/haftalık kural tanımlamaz):
- Bir varlığın hedefi son ele alındığı karara göre değiştiğinde, pozisyon durumu hedefle çeliştiğinde (hedef > 0 ama pozisyon
  yok veya tersi; ör. dolum yapılamamışsa) ya da yeniden dengeleme gününde hedefe işlem yapılır.
- Yeniden dengeleme günü: ilk karar günü ve `rebalance="monthly"` ise ayın son günündeki karar (dolum ayın 1'i).
- Çıkış her zaman tamdır; çıkış dışı işlemlerde MINTRADE ve 10 USDT minimum emir uygulanır. Haftalık giriş kuralı
  ve −%35 sert sınır kıyaslarda uygulanmaz (motor `hard_stop=False` ile çağrılmalı).
- %100 hedefli tek coin (BTC-200, al-tut) için alım tutarı nakit kısıtıyla orantılı küçültülür, yani tüm nakit
  yatırılır.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trend.backtest.interface import DayView, Decision, EngineData
from trend.strategy.rebalance import ENTRY, EXIT, SKIP_MINTRADE, TIER
from trend.strategy.signal import sma_on_valid
from trend.strategy.system import BTC_ASSET, TrendStrategy

# TODO(settings): universe.eth_asset — ETH'nin asset_id'si (BTC/ETH kıyası).
ETH_ASSET = "ETHUSDT"
# TODO(settings): evaluation.benchmark_sma — kıyaslardaki 200 günlük basit ortalama penceresi
# (strategy.regime_filter.sma ile aynı değer; BTC-200 tanımı rejim filtresinden bağımsız olduğu için ayrı tutulmalı).
BENCH_SMA = 200


class TargetWeightStrategy:
    """Hazır hedef ağırlıkları motorda yürütür (kıyaslar için)."""

    def __init__(self, weights: pd.DataFrame, rebalance: str = "on_change", name: str = "target"):
        if rebalance not in ("on_change", "monthly"):
            raise ValueError(rebalance)
        self.weights, self.rebalance, self.name = weights, rebalance, name

    def required_assets(self) -> list[str]:
        return [str(c) for c in self.weights.columns]

    def prepare(self, data: EngineData) -> None:
        w = self.weights.copy()
        w.index = pd.DatetimeIndex(w.index).as_unit("ns")
        w.columns = [str(c) for c in w.columns]
        self.W = w.reindex(index=data.days, columns=data.assets).fillna(0.0).to_numpy(dtype=float)
        self.last = np.full(len(data.assets), np.nan)  # varlığın son ele alındığı (boşlukta olmayan) gündeki hedef

    def observe(self, i: int) -> None:
        pass

    def decide(self, v: DayView) -> Decision:
        i, n = v.i, v.w.shape[0]
        wt = self.W[i].copy()
        month_end = (v.t + pd.Timedelta(days=1)).day == 1
        reb = v.first or (self.rebalance == "monthly" and month_end)
        wt[v.force_zero] = 0.0
        changed = ~(wt == self.last)  # boşlukta kaçırılan hedef değişikliği seri dönünce uygulanır
        mismatch = (wt > 0) != v.held
        trade = (reb | changed | mismatch) & ~v.frozen
        self.last = np.where(v.frozen, self.last, wt)
        delta = np.zeros(n)
        reason = np.zeros(n, dtype=np.int8)
        ex = trade & v.held & (wt <= 0)
        delta[ex] = -v.w[ex]
        reason[ex] = EXIT
        oth = trade & (wt > 0)
        delta[oth] = wt[oth] - v.w[oth]
        reason[oth] = np.where(v.held[oth], TIER, ENTRY)
        small = oth & (np.abs(delta) < v.mintrade)
        delta[small] = 0.0
        reason[small] = SKIP_MINTRADE
        return Decision(delta=delta, w_tgt=wt, s3=np.full(n, -1, dtype=np.int64), reason=reason)


def _days(close: pd.DataFrame) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(close.index).as_unit("ns")
    return pd.date_range(idx.min(), idx.max(), freq="D").as_unit("ns")


def _sma_signal(close: pd.DataFrame, asset: str, window: int) -> pd.Series:
    """C > SMA(window) → 1, aksi halde 0 (SMA tanımsızsa 0). Histerezis yok. Boşluk gününde önceki değer."""
    c = close[asset].copy()
    c.index = pd.DatetimeIndex(c.index).as_unit("ns")
    c = c.reindex(_days(close))
    sma = sma_on_valid(c, window)
    sig = pd.Series(np.where(c > sma, 1.0, np.where(c.notna() & sma.notna(), 0.0, np.nan)), index=c.index)
    first = sma.first_valid_index()
    sig = sig.ffill()
    if first is not None:
        sig[sig.index < first] = 0.0
    return sig.fillna(0.0)


def btc_200(close: pd.DataFrame, btc: str = BTC_ASSET, window: int = BENCH_SMA) -> TargetWeightStrategy:
    """Birincil kıyas: BTC kapanışı > SMA200 → %100 BTC, aksi halde %100 nakit (histerezis yok).

    Aylık yeniden dengeleme yalnızca adet formülünün (Δw·NAV(t)/C(t)) dolum < kapanış olduğunda bıraktığı artık nakdi
    MINTRADE'i aşarsa tamamlar; böylece AÇIK dönemde maruziyet ~%100 kalır (varsayım)."""
    w = _sma_signal(close, btc, window).to_frame(btc)
    return TargetWeightStrategy(w, rebalance="monthly", name="btc_200")


def btc_eth_200(close: pd.DataFrame, btc: str = BTC_ASSET, eth: str = ETH_ASSET,
                window: int = BENCH_SMA) -> TargetWeightStrategy:
    """BTC/ETH eşit ağırlık (%50/%50), her biri kendi SMA200'ü üstündeyse; aylık yeniden dengelenir."""
    w = pd.concat([0.5 * _sma_signal(close, btc, window).rename(btc),
                   0.5 * _sma_signal(close, eth, window).rename(eth)], axis=1)
    return TargetWeightStrategy(w, rebalance="monthly", name="btc_eth_200")


def btc_hold(close: pd.DataFrame, btc: str = BTC_ASSET, weight: float = 1.0,
             rebalance: str | None = None) -> TargetWeightStrategy:
    """BTC al-tut (weight=1). weight<1: %50 BTC + %50 nakit (0.5) veya oynaklığa ölçeklenmiş al-tut (oran dışarıdan).
    Aylık yeniden dengelenir (weight=1'de yalnızca artık nakit MINTRADE'i aşarsa işlem olur)."""
    w = pd.DataFrame({btc: weight}, index=_days(close))
    return TargetWeightStrategy(w, rebalance=rebalance or "monthly", name=f"btc_hold_{weight:g}")


def universe_equal_weight(close: pd.DataFrame, universe) -> TargetWeightStrategy:
    """Evrenin eşit ağırlıklı al-tutu, aylık dengelenir: t kararının evreni ay(t+1), w_i = 1/n."""
    days = _days(close)
    cols = [str(c) for c in close.columns]
    rows = {}
    cache = {}
    keyf = getattr(universe, "key", None)
    for t in days:
        k = keyf(t) if keyf else t
        if k not in cache:
            df = universe(t)
            syms = [s for s in df["symbol"].astype(str) if s in cols] if len(df) else []
            cache[k] = syms
        rows[t] = cache[k]
    W = pd.DataFrame(0.0, index=days, columns=cols)
    arr = W.to_numpy(copy=True)
    pos = {c: j for j, c in enumerate(cols)}
    for r, t in enumerate(days):
        syms = rows[t]
        if syms:
            arr[r, [pos[s] for s in syms]] = 1.0 / len(syms)
    W = pd.DataFrame(arr, index=days, columns=cols)
    W = W.loc[:, (W > 0).any(axis=0)]
    return _MonthlyOnly(W, name="universe_ew")


class _MonthlyOnly(TargetWeightStrategy):
    """Hedef yalnızca yeniden dengeleme günlerinde uygulanır (evren ay içinde değişmez; çıkan coin ay sonunda satılır)."""

    def __init__(self, weights: pd.DataFrame, name: str):
        super().__init__(weights, rebalance="monthly", name=name)

    def decide(self, v: DayView) -> Decision:
        month_end = (v.t + pd.Timedelta(days=1)).day == 1
        if v.first or month_end:
            return super().decide(v)
        n = v.w.shape[0]
        wt = np.where(v.held, v.w, 0.0)
        delta = np.zeros(n)
        reason = np.zeros(n, np.int8)
        ex = v.held & v.force_zero & ~v.frozen  # delist duyurusu: ertesi gün sat (ay sonunu bekleme)
        delta[ex], reason[ex], wt[ex] = -v.w[ex], EXIT, 0.0
        return Decision(delta=delta, w_tgt=wt, s3=np.full(n, -1, dtype=np.int64), reason=reason)


def trend_equal_weight(btc: str = BTC_ASSET) -> TrendStrategy:
    """Kıyas 6: aynı tamponlu trend sinyali ve yeniden dengeleme kuralları, oynaklık ayarsız eşit ağırlık (1/|E|)."""
    return TrendStrategy(sizing="equal", btc=btc)


def core_satellite(nav_core: pd.Series, nav_sat: pd.Series, w_core: float) -> pd.Series:
    """T10: iki motor NAV yolunun aylık yeniden dengelenen karışımı (ay sonu kapanışında w_core / 1 − w_core).

    Varsayım: dilimler arası aktarım maliyetsizdir (alt hesaplar arası transfer); başlangıç değeri 1.
    """
    df = pd.concat([nav_core.rename("c"), nav_sat.rename("s")], axis=1).dropna()
    r = df.pct_change().fillna(0.0).to_numpy()
    idx = df.index
    vc, vs = w_core, 1.0 - w_core
    out = np.empty(len(idx))
    for k in range(len(idx)):
        if k > 0:
            vc *= 1.0 + r[k, 0]
            vs *= 1.0 + r[k, 1]
        out[k] = vc + vs
        if k + 1 < len(idx) and idx[k + 1].month != idx[k].month:
            tot = vc + vs
            vc, vs = w_core * tot, (1.0 - w_core) * tot
    return pd.Series(out, index=idx, name=f"core_sat_{w_core:g}")
