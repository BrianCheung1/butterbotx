from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from butterbot.domain.daily_reward import (
    DailyAlreadyClaimed,
    DailyClaimState,
    InvalidDailyClaimState,
    calculate_daily_reward,
)


def test_first_daily_claim_awards_base_and_starts_streak() -> None:
    reward = calculate_daily_reward(DailyClaimState(0, None), date(2026, 8, 19))

    assert (reward.base, reward.bonus, reward.total, reward.streak) == (
        500,
        0,
        500,
        1,
    )


@pytest.mark.parametrize(
    ("previous_streak", "bonus", "total", "new_streak"),
    [
        (1, 50, 550, 2),
        (5, 250, 750, 6),
        (6, 800, 1_300, 7),
        (9, 450, 950, 10),
        (10, 500, 1_000, 11),
        (13, 1_000, 1_500, 14),
        (20, 1_000, 1_500, 21),
        (27, 1_000, 1_500, 28),
        (1_000_000, 500, 1_000, 1_000_001),
    ],
)
def test_daily_linear_bonus_cap_and_weekly_milestones(
    previous_streak: int, bonus: int, total: int, new_streak: int
) -> None:
    reward = calculate_daily_reward(
        DailyClaimState(previous_streak, date(2026, 8, 18)),
        date(2026, 8, 19),
    )

    assert (reward.bonus, reward.total, reward.streak) == (
        bonus,
        total,
        new_streak,
    )


def test_same_utc_day_is_rejected_until_next_midnight() -> None:
    with pytest.raises(DailyAlreadyClaimed) as raised:
        calculate_daily_reward(DailyClaimState(5, date(2026, 8, 19)), date(2026, 8, 19))

    assert raised.value.next_claim_at == datetime(2026, 8, 20, tzinfo=UTC)


def test_exactly_one_elapsed_day_preserves_streak() -> None:
    reward = calculate_daily_reward(
        DailyClaimState(5, date(2026, 8, 19)),
        date(2026, 8, 20),
    )

    assert (reward.streak, reward.bonus, reward.total) == (6, 250, 750)


@pytest.mark.parametrize("gap_days", [2, 13, 14])
def test_missing_two_or_more_utc_days_resets_streak(gap_days: int) -> None:
    reward = calculate_daily_reward(
        DailyClaimState(5, date(2026, 8, 19)),
        date(2026, 8, 19) + timedelta(days=gap_days),
    )

    assert (reward.streak, reward.bonus, reward.total) == (1, 0, 500)


def test_first_week_and_first_thirty_days_match_economy_targets() -> None:
    state = DailyClaimState(0, None)
    start = date(2026, 8, 1)
    rewards = []

    for offset in range(30):
        claim_date = start + timedelta(days=offset)
        reward = calculate_daily_reward(state, claim_date)
        rewards.append(reward.total)
        state = DailyClaimState(reward.streak, claim_date)

    assert sum(rewards[:7]) == 5_050
    assert sum(rewards) == 29_250
    assert max(rewards) == 1_500


def test_future_last_claim_date_is_invalid() -> None:
    with pytest.raises(InvalidDailyClaimState, match="future"):
        calculate_daily_reward(DailyClaimState(1, date(2026, 8, 20)), date(2026, 8, 19))


def test_daily_state_rejects_invalid_values() -> None:
    with pytest.raises(InvalidDailyClaimState):
        DailyClaimState(-1, None)
    with pytest.raises(InvalidDailyClaimState):
        DailyClaimState(1, None)
