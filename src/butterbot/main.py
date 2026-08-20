"""Application process entry point."""

from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

from butterbot.config import ConfigurationError, Settings
from butterbot.discord_app.bot import ButterBot
from butterbot.logging_config import configure_logging

logger = logging.getLogger(__name__)


async def run_application(settings: Settings) -> None:
    """Start ButterBot and close its resources when the process exits."""
    bot = ButterBot(settings)
    try:
        await bot.start(settings.discord_token)
    finally:
        await bot.close()


def main() -> None:
    """Load local configuration and run the application."""
    load_dotenv()
    try:
        settings = Settings.from_environment()
        configure_logging(settings.log_level)
    except (ConfigurationError, ValueError) as error:
        raise SystemExit(f"Configuration error: {error}") from error

    logger.info("Starting ButterBot.")
    asyncio.run(run_application(settings))
