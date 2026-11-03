"""Zorunlu test 6: bağımsız kontrol betiği (`independent/check.py`, motoru görmemiş ayrı bir oturumda yalnızca
SPEC'ten yazıldı) ile motorun karşılaştırması (G10).

Karşılaştırılanlar, coin başına: EMA 20/50/100, tamponlu durum (S3 = 3·S), σ, tutma bayrağı ve tek coinlik net
getiri. Tek coinlik portföy bağımsız betikteki tanımla kurulur: sinyal > 0 iken %100 coin, aksi halde nakit; haftalık
giriş, günlük çıkış, VWAP 00–02 dolum, komisyon ve kademe kayması; oynaklık hedefi, tavan ve sert sınır yok.

    python -m trend.research.independent_compare      # independent/out/*.csv gerekir
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trend.backtest.engine import run_backtest
from trend.backtest.fills import vwap_fill_prices
from trend.backtest.interface import DayView, Decision
from trend.backtest.providers import MonthlyUniverse, tier_slippage
from trend.config import ROOT, load_settings, path as cfg_path
from trend.research.inputs import hourly_end_time, load_fields, map_announcements
from trend.backtest.rules import delist_info_from_panel
from trend.quality import flags_to_assets, load_flags
from trend.strategy.rebalance import FROZEN, rebalance_orders
from trend.strategy.risk import annualized_vol
from trend.strategy.signal import ema_on_valid
from trend.strategy.system import TrendStrategy

ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "KAIAUSDT", "LUNAUSDT_until_20220513", "FTTUSDT"]
OUT_DIR = ROOT / "independent" / "out"
END = pd.Timestamp("2023-12-31")


FINDINGS = """## Bulgular (2026-11-03, portföy sonucu görülmeden)

İlk karşılaştırma iki uygulama hatası buldu; ikisi de düzeltildi, regresyon testi eklendi ve experiments.md satır
11'e yazıldı:

1. **Yarım gün temiz bar sayılıyordu.** Motorun 200 temiz bar şartı (`strategy.system.clean_bar_count`) yalnızca
   `error`/`exclude` işaretlerini düşüyordu; PREREGISTRATION §10'a göre yarım gün de temiz gün değildir. Sonuç:
   BTC, ETH ve KAIA ilk uygun günlerinde bir gün erken uygun sayılıyor ve bir fazla giriş yapıyordu. Ana portföyde
   etkisi pratikte yoktur (evren zaten 365 temiz gün ister) ama tanım artık ön kayıtla aynıdır.
2. **Delist duyurusu kalıcı yasak gibi uygulanıyordu.** FTTUSDT 2022-11-14 duyurusundan sonra seri 2023-09-22'de
   yeniden başlıyor; motor coini kalıcı olarak hedef 0'da tutuyordu. Onaylı meta tablodaki not ("delist kuralı ilk
   kapanışa uygulanır") gereği duyuru artık seri `delist_stale_days`'ten uzun bir boşluktan dönene kadar geçerlidir.

Kalan tek fark beklenen ve belgelenmiş bir yorum farkıdır: FTT'nin 310 günlük boşluğundan sonra σ penceresi dolana
kadar bağımsız betik σ'yı tanımsız bırakır, motor son geçerli değeri taşır (PREREGISTRATION §10 "son geçerli değer
taşınır"). Bu, tek coinlik portföyü etkilemez (σ kullanılmaz).

Karşılaştırma portföyünde kademe geçişleri (1/3 ↔ 2/3 ↔ 1) işlem doğurmayacak şekilde sabitlenmiştir (bağımsız
README karar 3); bu yapılmadan önce motorun pazartesi günleri ağırlığı %100'e tamamlaması günlük getirilerde en fazla
%0,37 fark yaratıyordu. Birincil getiri karşılaştırması bağımsız betiğin SPEC adet kuralıyla (Adet = Δw·NAV/kapanış)
hesapladığı seriyle (`ret_net_adet`) yapılır; "tüm nakitle alım" serisiyle fark yalnızca bu kuraldan gelir.

**Sonuç:** EMA'lar, tamponlu durum, tutma bayrakları, giriş/çıkış sayıları ve günlük net getiriler 7 coinin
tamamında makine hassasiyetinde eşleşiyor (`ret_days_diff_gt_1e-6` = 0).
"""


class SingleCoinStrategy(TrendStrategy):
    """Tek coin, sinyal > 0 iken hedef %100 (tamponlu sinyal ve haftalık giriş/günlük çıkış motorunkiyle aynı)."""

    def decide(self, v: DayView) -> Decision:
        i = v.i
        E = v.univ & self.clean_ok[i]
        H = v.held & ~E
        cand = (E | H) & ~v.frozen
        s3 = np.where(cand, np.maximum(self.S3[i], 0), 0).astype(np.int64)
        s3[v.force_zero] = 0
        # Bağımsız portföyde 1/3 ↔ 2/3 ↔ 1 geçişleri işlem doğurmaz (README karar 3): kademe sabit tutulur
        s3_raw = np.where(cand, self.S3[i], -1)
        s3 = np.where(s3 > 0, 3, 0).astype(np.int64)
        w_tgt = np.where(s3 > 0, 1.0, 0.0)
        w_tgt[H] = np.minimum(w_tgt[H], v.w[H])
        allow_inc = v.t.weekday() == self.entry_wd
        delta, reason = rebalance_orders(v.held & cand, v.w, w_tgt, s3, v.s3_last, v.mintrade, allow_inc,
                                         self.drift_rel, self.drift_min)
        delta[~cand] = 0.0
        reason[~cand] = 0
        reason[v.frozen & v.held] = FROZEN
        w_tgt[~cand & v.held] = v.w[~cand & v.held]
        return Decision(delta=delta, w_tgt=w_tgt, s3=s3, reason=reason, s3_raw=s3_raw)


def single_coin_universe(asset: str, qv: pd.Series, cfg: dict) -> MonthlyUniverse:
    """Ay sonu T'de 30 günlük medyan USDT hacmi (barı olmayan gün 0) → kademe kayması; tavan 1."""
    a_syms = {str(b) + "USDT" for b in cfg["universe"]["tiers"]["A"]["symbols"]}
    tier = "A" if asset in a_syms else "B"
    q = qv.fillna(0.0)
    med = q.rolling(30, min_periods=1).median()
    tables = {}
    for T in q.index[(q.index + pd.Timedelta(days=1)).day == 1]:
        ml = float(med.loc[T])
        tables[(T + pd.Timedelta(days=1)).strftime("%Y-%m")] = pd.DataFrame(
            [(asset, 1, ml, tier, 1.0, tier_slippage(tier, ml, cfg))],
            columns=["symbol", "rank", "median_liquidity", "tier", "cap", "slippage"])
    return MonthlyUniverse(tables)


def engine_side(asset: str, cfg: dict, flags: pd.DataFrame, delist: pd.DataFrame) -> pd.DataFrame:
    p = load_fields("1d", [asset], {"close": "close", "quote_volume": "quote_volume", "volume": "volume"},
                    END + pd.Timedelta(hours=23), cfg)
    days = pd.date_range(p["close"].index.min(), END, freq="D").as_unit("ns")
    p = {k: v.reindex(days) for k, v in p.items()}
    h = load_fields("1h", [asset], ("quote_volume", "volume"), hourly_end_time(END), cfg)
    w0, w1 = cfg["backtest"]["fill_windows"]["vwap_00_02"]
    fp = vwap_fill_prices(h, int(w0), int(w1))
    uni = single_coin_universe(asset, p["quote_volume"][asset], cfg)
    res = run_backtest(p, universe=uni, strategy=SingleCoinStrategy(), fill_px=fp,
                       delist=delist[delist["asset"] == asset], quality_flags=flags[flags["symbol"] == asset],
                       settings=cfg, hard_stop=False, end=END)
    c = p["close"]
    s = cfg["strategy"]
    out = pd.DataFrame(index=days)
    for n in s["spans"]:
        out[f"ema{n}"] = ema_on_valid(c, int(n))[:, 0]
    st = res.decisions
    sig = annualized_vol(c, s["vol_windows"], s["vol_min_obs"], float(s["vol_floor"]), int(s["annualization_days"]))
    out["sigma"] = np.asarray(sig)[:, 0]
    strat = SingleCoinStrategy()
    from trend.backtest.interface import EngineData
    strat.prepare(EngineData(days=days, assets=[asset], close=c, cfg=cfg, btc_idx=None, quality_flags=None,
                             start_idx=0))
    out["S3"] = strat.S3[:, 0].astype(float)
    out.loc[out["S3"] < 0, "S3"] = np.nan
    out["held"] = (res.weights[asset] > 0).astype(int) if res.weights is not None else 0
    out["ret"] = res.daily["ret"]
    out["nav"] = res.daily["nav"]
    out["trades"] = 0
    if len(res.fills):
        f = res.fills[res.fills["asset"] == asset]
        out.loc[pd.DatetimeIndex(f["date"]), "trades"] = 1
    del st
    return out


def compare_asset(asset: str, eng: pd.DataFrame) -> dict:
    ind = pd.read_csv(OUT_DIR / f"{asset}.csv", parse_dates=["date"]).set_index("date")
    ind.index = pd.DatetimeIndex(ind.index).as_unit("ns")
    e = eng.reindex(ind.index)
    out: dict = {"asset": asset, "days": int(len(ind))}
    for n in (20, 50, 100):
        a, b = ind[f"ema{n}"], e[f"ema{n}"]
        ok = a.notna() & b.notna()
        out[f"ema{n}_max_rel"] = float(((a[ok] - b[ok]).abs() / a[ok].abs()).max())
    si = (ind["state"] * 3).round()
    ok = si.notna() & e["S3"].notna()
    agree = si[ok] == e["S3"][ok]
    out["state_days"] = int(ok.sum())
    out["state_agree"] = float(agree.mean()) if ok.any() else np.nan
    out["state_first_diff"] = str(agree.index[~agree.to_numpy()][0].date()) if (~agree).any() else ""
    ok = ind["sigma"].notna() & e["sigma"].notna()
    out["sigma_max_abs"] = float((ind["sigma"][ok] - e["sigma"][ok]).abs().max()) if ok.any() else np.nan
    h_ok = (ind["held"] == e["held"])
    out["held_agree"] = float(h_ok.mean())
    out["held_first_diff"] = str(h_ok.index[~h_ok.to_numpy()][0].date()) if (~h_ok).any() else ""
    out["entries_ind"] = int((ind["trade"] == 1).sum())
    out["exits_ind"] = int((ind["trade"] < 0).sum())
    dh = e["held"].diff().fillna(e["held"])
    out["entries_eng"] = int((dh > 0).sum())
    out["exits_eng"] = int((dh < 0).sum())
    first = ind.index[0]
    r_e = e["ret"].copy()
    r_e.iloc[0] = 0.0
    # Birincil: bağımsız betiğin SPEC adet kuralıyla (Adet = Δw·NAV/kapanış) hesapladığı seri; motor aynı kuralı
    # kullanır. "Tüm nakitle alım" serisi (ret_net) ayrıca gösterilir.
    for tag, col_r, col_n in (("adet", "ret_net_adet", "nav_adet"), ("allcash", "ret_net", "nav")):
        r_i = ind[col_r]
        diff = (r_i - r_e).abs()
        out[f"ret_max_abs_diff_{tag}"] = float(diff.max())
        out[f"ret_diff_day_{tag}"] = str(diff.idxmax().date()) if diff.max() > 0 else ""
        out[f"nav_ind_{tag}"] = float(ind[col_n].iloc[-1])
    out["ret_days_diff_gt_1e-6"] = int(((ind["ret_net_adet"] - r_e).abs() > 1e-6).sum())
    out["nav_eng"] = float((1.0 + r_e).cumprod().iloc[-1])
    out["nav_ratio_adet"] = out["nav_eng"] / out["nav_ind_adet"]
    out["start"] = str(first.date())
    return out


def run_compare(cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or load_settings()
    segments = pd.read_csv(cfg_path(cfg, "meta") / "asset_segments.csv")
    flags = flags_to_assets(load_flags(cfg), segments)
    full = load_fields("1d", ASSETS, {"close": "close"}, None, cfg)["close"]
    ann = map_announcements(pd.read_csv(cfg_path(cfg, "meta") / "delist_announcements.csv"), segments)
    delist = delist_info_from_panel(full, int(cfg["backtest"]["delist_stale_days"]), ann)
    rows, engs = [], {}
    for a in ASSETS:
        eng = engine_side(a, cfg, flags, delist)
        engs[a] = eng
        rows.append(compare_asset(a, eng))
    df = pd.DataFrame(rows).set_index("asset")
    return df, engs


def write_report(df: pd.DataFrame, cfg: dict | None = None) -> str:
    cfg = cfg or load_settings()
    from trend.evaluation.report import to_markdown
    L = ["# G10 — Bağımsız kontrol betiği karşılaştırması (zorunlu test 6)", "",
         "Bağımsız betik (`independent/check.py`) motor kodunu görmemiş ayrı bir ajan oturumunda yalnızca SPEC'ten "
         "yazıldı; yorum kararları `independent/README.md`'de. Tek coinlik portföy: sinyal > 0 iken %100, haftalık giriş "
         "(pazar kararı, pazartesi dolum), günlük çıkış, VWAP 00–02, komisyon %0,10 + kademe kayması, 2017-08 – 2023-12.", "",
         to_markdown(df.T, 6, set()), "", FINDINGS]
    p = cfg_path(cfg, "reports") / "G10_independent_check.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    return str(p)


if __name__ == "__main__":
    d, _ = run_compare()
    pd.set_option("display.width", 250)
    print(d.T)
    print("rapor:", write_report(d))
