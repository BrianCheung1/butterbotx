"""Typed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(ValueError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated configuration required by the application foundation."""

    discord_token: str
    owner_id: int
    database_path: Path
    log_level: str
    enable_dev_commands: bool = False
    dev_guild_id: int | None = None
    valorant_api_key: str | None = None

    def __post_init__(self) -> None:
        if self.enable_dev_commands and self.dev_guild_id is None:
            raise ConfigurationError(
                "DEV_GUILD_ID is required when ENABLE_DEV_COMMANDS is true."
            )

    @classmethod
    def from_environment(cls) -> Settings:
        """Read and validate configuration from the process environment."""
        return cls(
            discord_token=_required_value("DISCORD_TOKEN"),
            owner_id=_required_positive_int("OWNER_ID"),
            database_path=Path(
                os.environ.get("DATABASE_PATH", "data/butterbot.sqlite3")
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            enable_dev_commands=_boolean("ENABLE_DEV_COMMANDS", default=False),
            dev_guild_id=_optional_positive_int("DEV_GUILD_ID"),
            valorant_api_key=_optional_value("VAL_KEY"),
        )


def _required_value(name: str) -> str:
    value = _optional_value(name)
    if value is None:
        raise ConfigurationError(f"Required configuration {name} is missing.")
    return value


def _optional_value(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _required_positive_int(name: str) -> int:
    value = _optional_positive_int(name)
    if value is None:
        raise ConfigurationError(f"Required configuration {name} is missing.")
    return value


def _optional_positive_int(name: str) -> int | None:
    value = _optional_value(name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError as error:
        raise ConfigurationError(f"Configuration {name} must be an integer.") from error
    if parsed <= 0:
        raise ConfigurationError(f"Configuration {name} must be positive.")
    return parsed


def _boolean(name: str, *, default: bool) -> bool:
    value = _optional_value(name)
    if value is None:
        return default
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ConfigurationError(f"Configuration {name} must be true or false.")
