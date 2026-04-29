from __future__ import annotations

from pathlib import Path

import yaml
from platformdirs import user_cache_dir, user_config_dir, user_data_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "azure-investigator"


def default_config_path() -> Path:
    return Path(user_config_dir(APP_NAME)) / "config.yaml"


def default_snapshot_root() -> Path:
    return Path(user_data_dir(APP_NAME)) / "snapshots"


def default_price_cache_root() -> Path:
    return Path(user_cache_dir(APP_NAME)) / "prices"


class Config(BaseSettings):
    """Configuration for azure-investigator. Read from YAML, overridable via env."""

    model_config = SettingsConfigDict(
        env_prefix="AZINV_",
        extra="ignore",
        case_sensitive=False,
    )

    currency: str = "GBP"
    snapshot_root: Path = Field(default_factory=default_snapshot_root)
    price_cache_root: Path = Field(default_factory=default_price_cache_root)
    price_cache_ttl_days: int = 7
    default_subscriptions: list[str] | None = None
    excluded_subscriptions: list[str] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        cfg_path = path or default_config_path()
        if cfg_path.exists():
            with cfg_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            return cls(**data)
        return cls()

    def write(self, path: Path | None = None) -> Path:
        cfg_path = path or default_config_path()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump(mode="json")
        with cfg_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, sort_keys=True)
        return cfg_path
