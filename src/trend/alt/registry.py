"""Araştırma v2 aile kayıt defteri ve ayarları (`research_v2.yaml`).

`make_alt(aile, parametreler, lag)` runner'ın `alt:<AİLE>` çalıştırma türü için karar vericiyi kurar; ailenin `common`
ayarları aileyi tanımlayan ayar dosyasından okunur (research_v2.yaml, research_v3.yaml). `HOLD` ailesi kıyas içindir:
sabit karışım (ör. %50 BTC + %50 ETH), aylık dengelenir.
"""

from __future__ import annotations

import numpy as np
import yaml

from trend.alt.base import AltStrategy
from trend.config import ROOT

V2_FILE = ROOT / "research_v2.yaml"
CONFIG_FILES = (V2_FILE, ROOT / "research_v3.yaml")


def load_v2(path=None) -> dict:
    with open(path or V2_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


class HoldMix(AltStrategy):
    """Kıyas: sabit ağırlıklı karışım, ay sonunda hedefe dengelenir."""

    def __init__(self, params: dict, common: dict | None = None, lag: int = 0):
        self.mix = {str(a): float(w) for a, w in dict(params["mix"]).items()}
        super().__init__(every="monthly", band=0.0, lag=lag, assets=tuple(self.mix))

    def compute(self, data) -> None:
        pass

    def target(self, j, v) -> np.ndarray:
        out = np.zeros(len(self.data.assets))
        for a, w in self.mix.items():
            out[self.col[a]] = w
        return out


def families() -> dict:
    from trend.alt import single, tsmom, xsec
    return {**xsec.FAMILIES, **single.FAMILIES, **tsmom.FAMILIES, "HOLD": HoldMix}


def common_for(family: str) -> dict:
    """Aileyi tanımlayan ilk ayar dosyasının `common` bölümü (yoksa research_v2.yaml)."""
    for p in CONFIG_FILES:
        if p.exists():
            c = load_v2(p)
            if family in c.get("families", {}):
                return c["common"]
    return load_v2()["common"]


def make_alt(family: str, params: dict, lag: int = 0, v2: dict | None = None) -> AltStrategy:
    cls = families()[family]
    return cls(dict(params), v2["common"] if v2 else common_for(family), lag)
