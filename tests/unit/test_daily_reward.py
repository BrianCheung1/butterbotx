from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from butterbot.domain.daily_reward import (
    DAILY_BONUS_CAP,
    DailyAlreadyClaimed,
    DailyClaimState,
    InvalidDailyClaimState,
    calculate_daily_reward,
)


def test_first_daily_claim_awards_base_and_starts_streak() -> None:
    reward = calculate_daily_reward(DailyClaimState(0, None), date(2026, 8, 19))

    assert (reward.base, reward.bonus, reward.total, reward.streak) == (
        1_000,
        0,
        1_000,
        1,
    )


@pytest.mark.parametrize(
    ("previous_streak", "bonus", "total", "new_streak"),
    [
        (1, 1_000, 2_000, 2),
        (2, 2_000, 3_000, 3),
        (3, 4_000, 5_000, 4),
        (10, 512_000, 513_000, 11),
        (11, DAILY_BONUS_CAP, 1_001_000, 12),
        (1_000_000, DAILY_BONUS_CAP, 1_001_000, 1_000_001),
    ],
)
def test_daily_bonus_progression_and_cap(
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


@pytest.mark.parametrize("gap_days", [1, 13])
def test_shorter_gaps_preserve_streak(gap_days: int) -> None:
    reward = calculate_daily_reward(
        DailyClaimState(5, date(2026, 8, 19)),
        date(2026, 8, 19) + timedelta(days=gap_days),
    )

    assert reward.streak == 6


@pytest.mark.parametrize("claim_date", [date(2026, 9, 2), date(2026, 10, 1)])
def test_gap_of_fourteen_or_more_days_resets_streak(claim_date: date) -> None:
    reward = calculate_daily_reward(DailyClaimState(5, date(2026, 8, 19)), claim_date)

    assert (reward.streak, reward.bonus, reward.total) == (1, 0, 1_000)


def test_future_last_claim_date_is_invalid() -> None:
    with pytest.raises(InvalidDailyClaimState, match="future"):
        calculate_daily_reward(DailyClaimState(1, date(2026, 8, 20)), date(2026, 8, 19))


def test_daily_state_rejects_invalid_values() -> None:
    with pytest.raises(InvalidDailyClaimState):
        DailyClaimState(-1, None)
    with pytest.raises(InvalidDailyClaimState):
        DailyClaimState(1, None)
