"""Deterministic mining progression and reward rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

MAX_MINING_LEVEL = 25
MINING_COOLDOWN_SECONDS = 30
MINING_ROLL_RANGE = 1_000_000
XP_CURVE_FACTOR = 12
LEVEL_VALUE_BONUS_PERCENT = 2


class MiningCooldownActive(Exception):
    """Raised when a user attempts to mine before their cooldown expires."""

    def __init__(self, next_mine_at: datetime) -> None:
        super().__init__("Mining cooldown is active.")
        self.next_mine_at = next_mine_at


class MiningRewardExceedsWalletLimit(Exception):
    """Raised when a wallet cannot hold a mining reward."""


class InvalidMiningState(Exception):
    """Raised when persisted mining state violates domain expectations."""


@dataclass(frozen=True, slots=True)
class MiningTier:
    """One configured rarity tier and its possible outcomes."""

    name: str
    rank: int
    unlock_level: int
    weight: int
    resources: tuple[str, ...]
    minimum_value: int
    maximum_value: int
    minimum_xp: int
    maximum_xp: int


@dataclass(frozen=True, slots=True)
class MiningCatalog:
    """The complete, validated mining balance catalog."""

    tiers: tuple[MiningTier, ...]

    def __post_init__(self) -> None:
        if not self.tiers:
            raise ValueError("Mining catalog must contain at least one tier.")
        ranks = [tier.rank for tier in self.tiers]
        if len(ranks) != len(set(ranks)):
            raise ValueError("Mining tier ranks must be unique.")
        for tier in self.tiers:
            if tier.weight <= 0:
                raise ValueError("Mining tier weights must be positive.")
            if not 1 <= tier.unlock_level <= MAX_MINING_LEVEL:
                raise ValueError("Mining unlock levels must be within the level cap.")
            if not tier.resources:
                raise ValueError("Mining tiers must contain resources.")
            if tier.minimum_value <= 0 or tier.maximum_value < tier.minimum_value:
                raise ValueError("Mining value ranges must be positive and ordered.")
            if tier.minimum_xp <= 0 or tier.maximum_xp < tier.minimum_xp:
                raise ValueError("Mining XP ranges must be positive and ordered.")
        if sum(tier.weight for tier in self.tiers) > MINING_ROLL_RANGE:
            raise ValueError("Mining tier weights exceed the supported roll range.")
        if min(tier.unlock_level for tier in self.tiers) != 1:
            raise ValueError("At least one mining tier must unlock at level 1.")

    def eligible_tiers(self, level: int) -> tuple[MiningTier, ...]:
        """Return tiers unlocked at a level in deterministic rank order."""
        return tuple(
            sorted(
                (tier for tier in self.tiers if tier.unlock_level <= level),
                key=lambda tier: tier.rank,
            )
        )


@dataclass(frozen=True, slots=True)
class MiningRoll:
    """All random inputs for one deterministic mining action."""

    rarity_roll: int
    resource_roll: int
    value_roll: int
    xp_roll: int

    def __post_init__(self) -> None:
        for value in (
            self.rarity_roll,
            self.resource_roll,
            self.value_roll,
            self.xp_roll,
        ):
            if not 0 <= value < MINING_ROLL_RANGE:
                raise ValueError("Mining roll values must be within the roll range.")


@dataclass(frozen=True, slots=True)
class MiningOutcome:
    """Resolved reward for one mining action."""

    resource: str
    rarity: str
    base_value: int
    level_bonus: int
    total_value: int
    xp_gained: int


@dataclass(frozen=True, slots=True)
class MiningResult:
    """Committed mining outcome and updated progression state."""

    outcome: MiningOutcome
    previous_level: int
    level: int
    xp: int
    xp_for_next_level: int | None
    total_actions: int
    total_earned: int
    balance: int
    next_mine_at: datetime

    @property
    def leveled_up(self) -> bool:
        return self.level > self.previous_level


def cumulative_xp_for_level(level: int) -> int:
    """Return cumulative XP required to have the given mining level."""
    if not 1 <= level <= MAX_MINING_LEVEL:
        raise ValueError("Mining level must be between 1 and 25.")
    return XP_CURVE_FACTOR * (level - 1) ** 2


def level_for_xp(xp: int) -> int:
    """Derive a capped mining level from nonnegative cumulative XP."""
    if xp < 0:
        raise ValueError("Mining XP cannot be negative.")
    level = 1
    while level < MAX_MINING_LEVEL and xp >= cumulative_xp_for_level(level + 1):
        level += 1
    return level


def resolve_mining(
    catalog: MiningCatalog, level: int, roll: MiningRoll
) -> MiningOutcome:
    """Resolve one roll using only tiers eligible at the supplied level."""
    if not 1 <= level <= MAX_MINING_LEVEL:
        raise ValueError("Mining level must be between 1 and 25.")
    eligible = catalog.eligible_tiers(level)
    total_weight = sum(tier.weight for tier in eligible)
    weighted_roll = roll.rarity_roll * total_weight // MINING_ROLL_RANGE
    cumulative_weight = 0
    selected = eligible[-1]
    for tier in eligible:
        cumulative_weight += tier.weight
        if weighted_roll < cumulative_weight:
            selected = tier
            break

    resource = selected.resources[
        roll.resource_roll * len(selected.resources) // MINING_ROLL_RANGE
    ]
    base_value = _roll_inclusive(
        selected.minimum_value, selected.maximum_value, roll.value_roll
    )
    xp_gained = _roll_inclusive(selected.minimum_xp, selected.maximum_xp, roll.xp_roll)
    bonus_percent = LEVEL_VALUE_BONUS_PERCENT * (level - 1)
    level_bonus = base_value * bonus_percent // 100
    return MiningOutcome(
        resource=resource,
        rarity=selected.name,
        base_value=base_value,
        level_bonus=level_bonus,
        total_value=base_value + level_bonus,
        xp_gained=xp_gained,
    )


def _roll_inclusive(minimum: int, maximum: int, roll: int) -> int:
    size = maximum - minimum + 1
    return minimum + roll * size // MINING_ROLL_RANGE


MINING_CATALOG = MiningCatalog(
    tiers=(
        MiningTier(
            "Common",
            1,
            1,
            60,
            (
                "dirt",
                "sand",
                "cobblestone",
                "wood",
                "gravel",
                "andesite",
                "granite",
                "diorite",
            ),
            50,
            100,
            5,
            10,
        ),
        MiningTier(
            "Uncommon",
            2,
            3,
            25,
            (
                "coal",
                "redstone",
                "lapis lazuli",
                "copper",
                "tin",
                "flint",
                "charcoal",
                "clay",
            ),
            100,
            150,
            5,
            10,
        ),
        MiningTier(
            "Rare",
            3,
            7,
            10,
            (
                "iron",
                "gold",
                "nether quartz",
                "platinum",
                "golden apple",
                "amethyst",
                "glowstone",
                "honeycomb",
                "quartz block",
            ),
            150,
            250,
            5,
            10,
        ),
        MiningTier(
            "Epic",
            4,
            15,
            4,
            (
                "diamond",
                "emerald",
                "mythril",
                "sponge",
                "heart of the sea",
                "totem of undying",
                "prismarine shard",
                "enchanted golden apple",
            ),
            250,
            500,
            5,
            10,
        ),
        MiningTier(
            "Legendary",
            5,
            25,
            1,
            (
                "ancient debris",
                "netherite scrap",
                "nether star",
                "dragon egg",
                "elytra",
                "beacon",
                "enchanted book",
                "dragon head",
            ),
            1_500,
            2_000,
            5,
            10,
        ),
    )
)
