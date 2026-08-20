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
    assert settings.dev_guild_id == 456


def test_settings_requires_discord_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("OWNER_ID", "123")

    with pytest.raises(ConfigurationError, match="DISCORD_TOKEN"):
        Settings.from_environment()


def test_settings_rejects_invalid_owner_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("OWNER_ID", "invalid")

    with pytest.raises(ConfigurationError, match="OWNER_ID"):
        Settings.from_environment()
