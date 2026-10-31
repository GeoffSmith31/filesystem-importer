
"""Tests for forward geocoding and location verification."""

from types import SimpleNamespace

import pytest

from filesystem_importer import geocoding


class FakeCache:
    """In-memory cache for geocoding tests."""

    def __init__(self):
        self.entries = {}
        self.stored = []

    def lookup(self, name):
        return self.entries.get(name)

    def store(self, name, *, valid):
        self.entries[name] = valid
        self.stored.append((name, valid))


class FakeRateLimiter:
    """Records rate-limiter calls."""

    def __init__(self, events=None):
        self.calls = 0
        self.events = events

    def wait_for_slot(self):
        self.calls += 1
        if self.events is not None:
            self.events.append("rate_limiter")


@pytest.fixture
def configured_geocoding(monkeypatch):
    """Configure a test User-Agent without changing global settings."""
    monkeypatch.setattr(
        geocoding,
        "_settings",
        SimpleNamespace(user_agent="FilesystemImporter/test (contact: developer@example.com)"),
    )


def test_implausible_location_is_rejected_without_request(
    configured_geocoding, monkeypatch
):
    cache = FakeCache()
    limiter = FakeRateLimiter()

    def unexpected_request(*args, **kwargs):
        pytest.fail("Nominatim should not be called for an implausible location")

    monkeypatch.setattr(geocoding, "_query_nominatim", unexpected_request)

    result = geocoding.check_location(
        "12345---",
        cache=cache,
        rate_limiter=limiter,
    )

    assert result is False
    assert limiter.calls == 0
    assert cache.stored == []


def test_empty_location_is_rejected_without_request(
    configured_geocoding, monkeypatch
):
    cache = FakeCache()
    limiter = FakeRateLimiter()

    def unexpected_request(*args, **kwargs):
        pytest.fail("Nominatim should not be called for an empty location")

    monkeypatch.setattr(geocoding, "_query_nominatim", unexpected_request)

    result = geocoding.check_location(
        "",
        cache=cache,
        rate_limiter=limiter,
    )

    assert result is False
    assert limiter.calls == 0


def test_missing_settings_returns_unknown_without_request(monkeypatch):
    monkeypatch.setattr(geocoding, "_settings", None)

    cache = FakeCache()
    limiter = FakeRateLimiter()

    def unexpected_request(*args, **kwargs):
        pytest.fail("Nominatim should not be called without settings")

    monkeypatch.setattr(geocoding, "_query_nominatim", unexpected_request)

    result = geocoding.check_location(
        "Brisbane",
        cache=cache,
        rate_limiter=limiter,
    )

    assert result is None
    assert limiter.calls == 0
    assert cache.stored == []


def test_missing_user_agent_returns_unknown_without_request(monkeypatch):
    monkeypatch.setattr(
        geocoding,
        "_settings",
        SimpleNamespace(user_agent=""),
    )

    cache = FakeCache()
    limiter = FakeRateLimiter()

    def unexpected_request(*args, **kwargs):
        pytest.fail("Nominatim should not be called without a User-Agent")

    monkeypatch.setattr(geocoding, "_query_nominatim", unexpected_request)

    result = geocoding.check_location(
        "Brisbane",
        cache=cache,
        rate_limiter=limiter,
    )

    assert result is None
    assert limiter.calls == 0
    assert cache.stored == []


@pytest.mark.parametrize("cached_result", [True, False])
def test_cache_hit_bypasses_rate_limiter_and_request(
    configured_geocoding, monkeypatch, cached_result
):
    cache = FakeCache()
    cache.entries["Brisbane"] = cached_result
    limiter = FakeRateLimiter()

    def unexpected_request(*args, **kwargs):
        pytest.fail("Nominatim should not be called for a cached location")

    monkeypatch.setattr(geocoding, "_query_nominatim", unexpected_request)

    result = geocoding.check_location(
        "Brisbane",
        cache=cache,
        rate_limiter=limiter,
    )

    assert result is cached_result
    assert limiter.calls == 0
    assert cache.stored == []


@pytest.mark.parametrize("query_result", [True, False])
def test_cache_miss_queries_nominatim_and_caches_definitive_result(
    configured_geocoding, monkeypatch, query_result
):
    events = []
    cache = FakeCache()
    limiter = FakeRateLimiter(events)

    def fake_query(location_name, *, timeout, user_agent):
        events.append("nominatim")
        assert location_name == "Brisbane"
        assert timeout == geocoding.REQUEST_TIMEOUT_SECONDS
        assert user_agent == geocoding._settings.user_agent
        return query_result

    monkeypatch.setattr(geocoding, "_query_nominatim", fake_query)

    result = geocoding.check_location(
        "Brisbane",
        cache=cache,
        rate_limiter=limiter,
    )

    assert result is query_result
    assert events == ["rate_limiter", "nominatim"]
    assert limiter.calls == 1
    assert cache.stored == [("Brisbane", query_result)]
    assert cache.entries["Brisbane"] is query_result


def test_service_failure_returns_unknown_and_is_not_cached(
    configured_geocoding, monkeypatch
):
    cache = FakeCache()
    limiter = FakeRateLimiter()

    monkeypatch.setattr(
        geocoding,
        "_query_nominatim",
        lambda *args, **kwargs: None,
    )

    result = geocoding.check_location(
        "Brisbane",
        cache=cache,
        rate_limiter=limiter,
    )

    assert result is None
    assert limiter.calls == 1
    assert cache.stored == []
    assert cache.entries == {}


def test_injected_cache_is_used(
    configured_geocoding, monkeypatch
):
    cache = FakeCache()
    limiter = FakeRateLimiter()

    monkeypatch.setattr(
        geocoding,
        "_query_nominatim",
        lambda *args, **kwargs: True,
    )

    result = geocoding.check_location(
        "Toowoomba",
        cache=cache,
        rate_limiter=limiter,
    )

    assert result is True
    assert cache.entries["Toowoomba"] is True
    assert cache.stored == [("Toowoomba", True)]

@pytest.mark.parametrize("result", [True, False, None])
def test_location_validate_preserves_check_location_result(
    monkeypatch, result
):
    def fake_check_location(location_name):
        assert location_name == "Brisbane"
        return result

    monkeypatch.setattr(
        geocoding, "check_location", fake_check_location
    )

    assert geocoding.location_validate("Brisbane") is result

