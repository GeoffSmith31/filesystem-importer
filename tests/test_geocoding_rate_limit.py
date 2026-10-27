
from concurrent.futures import ThreadPoolExecutor

import pytest

from filesystem_importer.geocoding_rate_limit import (
    GeocodingRateLimiter,
    geocoding_rate_limiter,
)


class FakeClock:
    """Monotonic clock that advances when sleep is called."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleep_calls: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.now += seconds


def make_limiter(
    clock: FakeClock,
    interval: float = 1.0,
) -> GeocodingRateLimiter:
    """Create a limiter driven by a fake clock."""
    return GeocodingRateLimiter(
        min_interval_seconds=interval,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )


def test_first_request_does_not_wait() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock)

    slot = limiter.wait_for_slot()

    assert slot == 0.0
    assert clock.sleep_calls == []


def test_second_request_waits_one_second() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock)

    first_slot = limiter.wait_for_slot()
    second_slot = limiter.wait_for_slot()

    assert first_slot == 0.0
    assert second_slot == 1.0
    assert clock.sleep_calls == [1.0]


def test_request_waits_only_for_remaining_interval() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock)

    first_slot = limiter.wait_for_slot()
    clock.now += 0.4
    second_slot = limiter.wait_for_slot()

    assert first_slot == 0.0
    assert second_slot == 1.0
    assert clock.sleep_calls == pytest.approx([0.6])


def test_wait_repeats_if_interval_has_not_elapsed() -> None:
    clock = FakeClock()

    def partial_sleep(seconds: float) -> None:
        clock.sleep_calls.append(seconds)
        clock.now += min(seconds, 0.25)

    limiter = GeocodingRateLimiter(
        min_interval_seconds=1.0,
        clock=clock.monotonic,
        sleep=partial_sleep,
    )

    limiter.wait_for_slot()
    second_slot = limiter.wait_for_slot()

    assert second_slot == pytest.approx(1.0)
    assert len(clock.sleep_calls) > 1


def test_multiple_sequential_requests_respect_interval() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock)

    slots = [
        limiter.wait_for_slot()
        for _ in range(5)
    ]

    assert slots == pytest.approx(
        [0.0, 1.0, 2.0, 3.0, 4.0]
    )


def test_concurrent_callers_receive_separate_slots() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(limiter.wait_for_slot)
            for _ in range(5)
        ]
        slots = sorted(future.result() for future in futures)

    assert slots == pytest.approx(
        [0.0, 1.0, 2.0, 3.0, 4.0]
    )

    for earlier, later in zip(slots, slots[1:]):
        assert later - earlier >= 1.0


def test_zero_interval_does_not_wait() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock, interval=0.0)

    first_slot = limiter.wait_for_slot()
    second_slot = limiter.wait_for_slot()

    assert first_slot == 0.0
    assert second_slot == 0.0
    assert clock.sleep_calls == []


def test_negative_interval_is_rejected() -> None:
    clock = FakeClock()

    with pytest.raises(
        ValueError,
        match="Minimum interval cannot be negative",
    ):
        make_limiter(clock, interval=-1.0)


def test_shared_limiter_is_a_single_instance() -> None:
    from filesystem_importer import geocoding_rate_limit

    assert (
        geocoding_rate_limit.geocoding_rate_limiter
        is geocoding_rate_limiter
    )

