"""settings.yaml yükleyici. Tüm parametreler tek yerden okunur (SPEC: "her parametre tek yerde")."""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = ROOT / "settings.yaml"


@lru_cache(maxsize=1)
def _load_raw(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_settings(overrides: dict[str, Any] | None = None, path: Path | None = None) -> dict[str, Any]:
    """Ayarları döndürür. `overrides` iç içe sözlükle varyant/komşu ayarlarını uygular (kopya üzerinde)."""
    cfg = copy.deepcopy(_load_raw(str(path or SETTINGS_PATH)))
    if overrides:
        _deep_update(cfg, overrides)
    return cfg


def _deep_update(base: dict, upd: dict) -> None:
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


def path(cfg: dict[str, Any], key: str) -> Path:
    """`paths` altındaki göreli yolu proje köküne göre mutlak yola çevirir."""
    p = Path(cfg["paths"][key])
    return p if p.is_absolute() else ROOT / p
