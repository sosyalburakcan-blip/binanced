"""G0 kabul testleri: ayarlar yüklenir, her parametre tek yerde tanımlı, Binance erişimi (ağ testleri)."""

import pytest
import requests
import yaml

from trend.config import SETTINGS_PATH, load_settings


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader, node, deep=False):
    keys = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise ValueError(f"settings.yaml içinde tekrar eden anahtar: {key!r} (satır {key_node.start_mark.line + 1})")
        keys.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def test_settings_have_no_duplicate_keys():
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        yaml.load(f, Loader=_UniqueKeyLoader)


def test_settings_core_values_match_spec():
    c = load_settings()
    s = c["strategy"]
    assert s["spans"] == [20, 50, 100]
    assert s["buffer_h"] == 0.5
    assert s["vol_floor"] == 0.30
    assert s["target_vol"] == 0.35
    assert s["gross_max"] == 1.0
    assert s["rebalance"]["drift_rel"] == 0.25 and s["rebalance"]["drift_min"] == 0.005
    assert c["universe"]["size"] == 20 and c["universe"]["min_clean_days"] == 365
    assert c["universe"]["tiers"]["A"]["cap"] == 0.10
    assert c["backtest"]["commission"] == 0.0010 and c["backtest"]["delist_penalty"] == 0.05
    assert c["evaluation"]["dsr_n_min"] == 100


def test_overrides_do_not_mutate_base():
    a = load_settings({"strategy": {"buffer_h": 0.0}})
    b = load_settings()
    assert a["strategy"]["buffer_h"] == 0.0 and b["strategy"]["buffer_h"] == 0.5


@pytest.mark.network
def test_binance_ping_unsigned():
    c = load_settings()
    r = requests.get(c["data"]["rest_base"] + "/api/v3/ping", timeout=15)
    assert r.status_code == 200


@pytest.mark.network
def test_archive_single_file():
    c = load_settings()
    url = c["data"]["archive_base"] + "/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2024-01.zip"
    r = requests.head(url, timeout=15)
    assert r.status_code == 200
