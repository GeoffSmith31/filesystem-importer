
import json
from pathlib import Path

import pytest

from filesystem_importer.location_cache import (
    CACHE_VERSION,
    LocationCache,
    get_location_cache_path,
)


def test_missing_cache_starts_empty(tmp_path: Path) -> None:
    cache_path = tmp_path / "tested-locations.json"

    cache = LocationCache(cache_path)

    assert cache.lookup("Brisbane") is None
    assert not cache_path.exists()


def test_stores_valid_result(tmp_path: Path) -> None:
    cache_path = tmp_path / "tested-locations.json"
    cache = LocationCache(cache_path)

    cache.store("Brisbane", True)

    assert cache.lookup("Brisbane") is True
    assert cache_path.exists()


def test_stores_invalid_result(tmp_path: Path) -> None:
    cache = LocationCache(tmp_path / "tested-locations.json")

    cache.store("Not a real place", False)

    assert cache.lookup("Not a real place") is False


def test_lookup_ignores_case_and_extra_whitespace(
    tmp_path: Path,
) -> None:
    cache = LocationCache(tmp_path / "tested-locations.json")

    cache.store("  New   Zealand  ", True)

    assert cache.lookup("new zealand") is True
    assert cache.lookup("NEW ZEALAND") is True
    assert cache.lookup(" New Zealand ") is True


def test_results_persist_between_instances(tmp_path: Path) -> None:
    cache_path = tmp_path / "tested-locations.json"

    first_cache = LocationCache(cache_path)
    first_cache.store("Brisbane", True)
    first_cache.store("Imaginary Place", False)

    second_cache = LocationCache(cache_path)

    assert second_cache.lookup("Brisbane") is True
    assert second_cache.lookup("Imaginary Place") is False
    assert second_cache.lookup("Unknown Place") is None


def test_cache_contains_only_definitive_statuses(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "tested-locations.json"
    cache = LocationCache(cache_path)

    cache.store("Brisbane", True)
    cache.store("Imaginary Place", False)

    data = json.loads(cache_path.read_text(encoding="utf-8"))

    assert data["version"] == CACHE_VERSION
    assert {
        entry["status"]
        for entry in data["locations"].values()
    } == {"valid", "invalid"}


def test_rejects_non_boolean_result(tmp_path: Path) -> None:
    cache = LocationCache(tmp_path / "tested-locations.json")

    with pytest.raises(TypeError, match="must be a Boolean"):
        cache.store("Brisbane", 1)  # type: ignore[arg-type]


def test_rejects_empty_location_name(tmp_path: Path) -> None:
    cache = LocationCache(tmp_path / "tested-locations.json")

    with pytest.raises(ValueError, match="cannot be empty"):
        cache.store("   ", True)


def test_does_not_store_service_failure_automatically(
    tmp_path: Path,
) -> None:
    """Only explicit definitive results can be written to the cache."""
    cache = LocationCache(tmp_path / "tested-locations.json")

    # A service failure is represented by not calling store().
    assert cache.lookup("Brisbane") is None
    assert not cache.cache_path.exists()


def test_corrupt_cache_file_starts_empty(tmp_path: Path) -> None:
    cache_path = tmp_path / "tested-locations.json"
    cache_path.write_text("{ invalid json", encoding="utf-8")

    cache = LocationCache(cache_path)

    assert cache.lookup("Brisbane") is None


def test_ignores_entries_with_invalid_status(tmp_path: Path) -> None:
    cache_path = tmp_path / "tested-locations.json"
    cache_path.write_text(
        json.dumps({
            "version": CACHE_VERSION,
            "locations": {
                "brisbane": {
                    "name": "Brisbane",
                    "status": "unverified",
                    "checked_at": "2026-10-26T00:00:00+00:00",
                }
            },
        }),
        encoding="utf-8",
    )

    cache = LocationCache(cache_path)

    assert cache.lookup("Brisbane") is None


def test_default_path_uses_platform_data_directory() -> None:
    path = get_location_cache_path()

    assert path.name == "tested-locations.json"
    assert path.parent.name == "filesystem-importer"

