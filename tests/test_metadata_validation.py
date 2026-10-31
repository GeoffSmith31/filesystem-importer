
"""Tests for reusable metadata validation functions."""

import pytest

from filesystem_importer.metadata_validation import year_validate


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024", "2024"),
        (" 2024 ", "2024"),
        ("25-10-2024", "25-Oct-2024"),
        ("25/10/2024", "25-Oct-2024"),
        ("2024-10-25", "25-Oct-2024"),
        ("25 October 2024", "25-Oct-2024"),
        ("October 25, 2024", "25-Oct-2024"),
        ("03/04/2024", "2024"),
        ("10/11/2024", "2024"),
        ("13/04/2024", "13-Apr-2024"),
        ("04/13/2024", "13-Apr-2024"),
        ("29/02/2024", "29-Feb-2024"),
        ("October", "October"),
        ("october", "October"),
        ("MONDAY", "Monday"),
        ("Spring", "Spring"),
        ("summer", "Summer"),
        ("Morning", "Morning"),
        ("afternoon", "Afternoon"),
        ("night", "Night"),
        ("early", "Early"),
        ("late", "Late"),
        ("day", "Day"),
    ],
)
def test_year_validate_accepts_valid_values(value, expected):
    assert year_validate(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "50 year reunion",
        "2024-02-30",
        "31/02/2024",
        "29/02/2023",
        "Not a date",
        "123",
        "2024abc",
        "Monday morning",
        "October 2024",
    ],
)
def test_year_validate_rejects_invalid_values(value):
    assert year_validate(value) is None

