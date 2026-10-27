
from pathlib import Path

import pytest

from filesystem_importer.metadata_context import (
    _find_directory_ancestor,
    _normalise_inherited_year,
)


@pytest.mark.parametrize(
    ("folder_name", "expected"),
    [
        ("1982", "1982"),
        ("2025", "2025"),
        ("january", "January"),
        ("DECEMBER", "December"),
        ("mon", "Monday"),
        ("FRIDAY", "Friday"),
        ("summer", "Summer"),
        ("EARLY", "Early"),
        ("afternoon", "Afternoon"),
        ("5-Jan-1982", "05-Jan-1982"),
        ("31-dec-2025", "31-Dec-2025"),
        ("29-Feb-2024", "29-Feb-2024"),
    ],
)
def test_normalise_valid_year_values(
    folder_name: str,
    expected: str,
) -> None:
    assert _normalise_inherited_year(folder_name) == expected


@pytest.mark.parametrize(
    "folder_name",
    [
        "",
        "   ",
        "0000",
        "50 year reunion",
        "Summer holiday",
        "Unknown",
        "31-Feb-2025",
        "29-Feb-2023",
        "2025-12-31",
    ],
)
def test_reject_invalid_year_values(folder_name: str) -> None:
    assert _normalise_inherited_year(folder_name) is None


def test_finds_nearest_valid_year_ancestor() -> None:
    result = _find_directory_ancestor(
        relative_directory=Path("1982/50 year reunion/Beach"),
        source_directory=Path("/photos"),
        directory_classifications={
            "1": "Event",
            "2": "Year",
            "3": "Year",
            "4": "Location",
        },
        category="Year",
    )

    assert result == ("1982", "1982")


def test_returns_original_folder_name_for_event() -> None:
    result = _find_directory_ancestor(
        relative_directory=Path("My Event/Photos"),
        source_directory=Path("/photos"),
        directory_classifications={
            "2": "Event",
        },
        category="Event",
    )

    assert result == ("My Event", "My Event")


def test_returns_none_when_no_valid_year_exists() -> None:
    result = _find_directory_ancestor(
        relative_directory=Path("50 year reunion/Photos"),
        source_directory=Path("/photos"),
        directory_classifications={
            "2": "Year",
            "3": "Info",
        },
        category="Year",
    )

    assert result is None


def test_can_use_source_root_as_ancestor() -> None:
    result = _find_directory_ancestor(
        relative_directory=Path("."),
        source_directory=Path("/photos/January"),
        directory_classifications={
            "1": "Year",
        },
        category="Year",
    )

    assert result == ("January", "January")

