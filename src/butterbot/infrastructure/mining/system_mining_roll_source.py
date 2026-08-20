"""Production mining rolls backed by the operating system random source."""

from __future__ import annotations

import random

from butterbot.domain.mining import MINING_ROLL_RANGE, MiningRoll


class SystemMiningRollSource:
    """Create complete mining rolls from system-provided randomness."""

    def __init__(self) -> None:
        self._random = random.SystemRandom()

    def create_roll(self) -> MiningRoll:
        """Create all random inputs consumed by one mining action."""
        return MiningRoll(
            rarity_roll=self._random.randrange(MINING_ROLL_RANGE),
            resource_roll=self._random.randrange(MINING_ROLL_RANGE),
            value_roll=self._random.randrange(MINING_ROLL_RANGE),
            xp_roll=self._random.randrange(MINING_ROLL_RANGE),
        )
