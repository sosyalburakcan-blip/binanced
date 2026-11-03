"""SPEC zorunlu test 5 — altın kayıt: kilitten sonra kaydedilen T0 ve BTC-200 karar geçmişi her kod veya kütüphane
değişikliğinden sonra birebir yeniden üretilmeli. Gerçek veri ve `golden/manifest.json` gerekir (yoksa atlanır)."""

import pytest

from trend.config import load_settings, path as cfg_path
from trend.research import g12

pytestmark = pytest.mark.data


def test_golden_master_reproduces_locked_decisions():
    cfg = load_settings()
    if not (g12.golden_dir(cfg) / "manifest.json").exists() or not (cfg_path(cfg, "merged") / "1d").exists():
        pytest.skip("altın kayıt veya birleştirilmiş veri yok")
    r = g12.golden_check(cfg, record=False)
    bad = {k: (v["bad_columns"], v["why"]) for k, v in r["tables"].items() if not v["ok"]}
    assert r["ok"], bad
