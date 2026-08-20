from __future__ import annotations

from dataclasses import replace

import pytest

from butterbot.domain.mining import (
    MAX_MINING_LEVEL,
    MINING_CATALOG,
    MINING_ROLL_RANGE,
    MiningCatalog,
    MiningRoll,
    cumulative_xp_for_level,
    level_for_xp,
    resolve_mining,
)


@pytest.mark.parametrize(
    ("level", "expected_xp"),
    [(1, 0), (3, 48), (7, 432), (15, 2_352), (25, 6_912)],
)
def test_approved_cumulative_xp_curve(level: int, expected_xp: int) -> None:
    assert cumulative_xp_for_level(level) == expected_xp


def test_level_is_derived_from_cumulative_xp_and_capped() -> None:
    assert level_for_xp(47) == 2
    assert level_for_xp(48) == 3
    assert level_for_xp(6_911) == 24
    assert level_for_xp(6_912) == MAX_MINING_LEVEL
    assert level_for_xp(1_000_000) == MAX_MINING_LEVEL


def test_level_one_roll_can_only_select_common_and_has_no_bonus() -> None:
    outcome = resolve_mining(
        MINING_CATALOG,
        1,
        MiningRoll(
            rarity_roll=MINING_ROLL_RANGE - 1,
            resource_roll=MINING_ROLL_RANGE - 1,
            value_roll=MINING_ROLL_RANGE - 1,
            xp_roll=MINING_ROLL_RANGE - 1,
        ),
    )

    assert outcome.rarity == "Common"
    assert outcome.resource == "diorite"
    assert outcome.base_value == 100
    assert outcome.level_bonus == 0
    assert outcome.total_value == 100
    assert outcome.xp_gained == 10


def test_level_25_can_select_legendary_and_floors_level_bonus() -> None:
    outcome = resolve_mining(
        MINING_CATALOG,
        25,
        MiningRoll(999_999, 0, 0, 0),
    )

    assert outcome.rarity == "Legendary"
    assert outcome.resource == "ancient debris"
    assert outcome.base_value == 1_500
    assert outcome.level_bonus == 720
    assert outcome.total_value == 2_220
    assert outcome.xp_gained == 5


@pytest.mark.parametrize(
    ("tier_change", "message"),
    [
        ({"rank": 2}, "ranks"),
        ({"weight": 0}, "weights"),
        ({"minimum_value": 0}, "value ranges"),
        ({"maximum_xp": 4}, "XP ranges"),
        ({"unlock_level": 26}, "unlock levels"),
        ({"resources": ()}, "resources"),
    ],
)
def test_catalog_rejects_invalid_tiers(
    tier_change: dict[str, object], message: str
) -> None:
    tiers = list(MINING_CATALOG.tiers)
    tiers[0] = replace(tiers[0], **tier_change)

    with pytest.raises(ValueError, match=message):
        MiningCatalog(tuple(tiers))


def test_catalog_rejects_total_weight_above_roll_range() -> None:
    tier = replace(MINING_CATALOG.tiers[0], weight=MINING_ROLL_RANGE + 1)

    with pytest.raises(ValueError, match="supported roll range"):
        MiningCatalog((tier,))


def test_roll_rejects_values_outside_supported_range() -> None:
    with pytest.raises(ValueError, match="roll range"):
        MiningRoll(MINING_ROLL_RANGE, 0, 0, 0)
