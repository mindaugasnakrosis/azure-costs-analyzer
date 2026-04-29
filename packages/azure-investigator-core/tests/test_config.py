from __future__ import annotations

from pathlib import Path

import yaml
from azure_investigator_core.config import Config


def test_defaults(tmp_path, monkeypatch):
    cfg = Config.load(tmp_path / "missing.yaml")
    assert cfg.currency == "GBP"
    assert cfg.price_cache_ttl_days == 7
    assert isinstance(cfg.snapshot_root, Path)


def test_yaml_overrides(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "currency": "GBP",
                "snapshot_root": str(tmp_path / "snaps"),
                "price_cache_ttl_days": 30,
                "excluded_subscriptions": ["sub-x"],
            }
        ),
        encoding="utf-8",
    )
    cfg = Config.load(p)
    assert cfg.snapshot_root == tmp_path / "snaps"
    assert cfg.price_cache_ttl_days == 30
    assert cfg.excluded_subscriptions == ["sub-x"]


def test_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AZINV_PRICE_CACHE_TTL_DAYS", "14")
    cfg = Config.load(tmp_path / "absent.yaml")
    assert cfg.price_cache_ttl_days == 14


def test_write_roundtrip(tmp_path):
    p = tmp_path / "config.yaml"
    cfg = Config(
        currency="GBP",
        snapshot_root=tmp_path / "snap",
        price_cache_root=tmp_path / "prices",
        price_cache_ttl_days=10,
        excluded_subscriptions=["a", "b"],
    )
    cfg.write(p)
    assert p.exists()
    reloaded = Config.load(p)
    assert reloaded.price_cache_ttl_days == 10
    assert reloaded.excluded_subscriptions == ["a", "b"]


def test_currency_default_is_gbp(tmp_path):
    cfg = Config.load(tmp_path / "absent.yaml")
    assert cfg.currency == "GBP"
