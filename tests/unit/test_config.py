from __future__ import annotations

import pytest

from butterbot.config import ConfigurationError, Settings


def test_settings_reads_required_and_optional_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_ID", "123")
    monkeypatch.setenv("DATABASE_PATH", "var/butterbot.sqlite3")
    monkeypatch.setenv("DEV_GUILD_ID", "456")

    settings = Settings.from_environment()

    assert settings.discord_token == "test-token"
    assert settings.owner_id == 123
    assert settings.database_path.as_posix() == "var/butterbot.sqlite3"
    assert settings.enable_dev_commands is False
    assert settings.dev_guild_id == 456


def test_settings_requires_discord_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("OWNER_ID", "123")

    with pytest.raises(ConfigurationError, match="DISCORD_TOKEN"):
        Settings.from_environment()


def test_settings_keeps_development_guild_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_ID", "123")
    monkeypatch.delenv("DEV_GUILD_ID", raising=False)

    settings = Settings.from_environment()

    assert settings.dev_guild_id is None
    assert settings.enable_dev_commands is False


def test_settings_enables_development_commands_with_guild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_ID", "123")
    monkeypatch.setenv("ENABLE_DEV_COMMANDS", "TrUe")
    monkeypatch.setenv("DEV_GUILD_ID", "456")

    settings = Settings.from_environment()

    assert settings.enable_dev_commands is True
    assert settings.dev_guild_id == 456


def test_settings_requires_development_guild_when_commands_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_ID", "123")
    monkeypatch.setenv("ENABLE_DEV_COMMANDS", "true")
    monkeypatch.delenv("DEV_GUILD_ID", raising=False)

    with pytest.raises(ConfigurationError, match=r"DEV_GUILD_ID.*ENABLE_DEV_COMMANDS"):
        Settings.from_environment()


@pytest.mark.parametrize("value", ["1", "yes", "on", "development"])
def test_settings_rejects_non_boolean_development_command_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_ID", "123")
    monkeypatch.setenv("ENABLE_DEV_COMMANDS", value)

    with pytest.raises(ConfigurationError, match="ENABLE_DEV_COMMANDS"):
        Settings.from_environment()


def test_settings_rejects_invalid_owner_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_ID", "invalid")

    with pytest.raises(ConfigurationError, match="OWNER_ID"):
        Settings.from_environment()


def test_settings_rejects_invalid_development_guild_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_ID", "123")
    monkeypatch.setenv("DEV_GUILD_ID", "invalid")

    with pytest.raises(ConfigurationError, match="DEV_GUILD_ID"):
        Settings.from_environment()
