
"""Tests for extracting probable metadata from UserComment."""

import pytest

from filesystem_importer import metadata_extraction
from filesystem_importer.metadata_extraction import (
    extract_usercomment_metadata,
)


@pytest.fixture
def successful_validation(monkeypatch):
    """Mock successful Year and Location validation."""
    monkeypatch.setattr(
        metadata_extraction, "year_validate", lambda value: value
    )
    monkeypatch.setattr(
        metadata_extraction, "location_validate", lambda value: True
    )


@pytest.fixture
def photo_record():
    """Provide a photo record with its normal default metadata values."""
    return {
        "event": "Default Event",
        "year": "",
        "location": "",
        "info": "",
    }


def test_extracts_four_fields_using_pipe_delimiters(
    successful_validation, photo_record
):
    comment = "Holiday | 2024 | Paris | Family trip"

    extract_usercomment_metadata(comment, photo_record)

    assert photo_record["event"] == "Holiday"
    assert photo_record["year"] == "2024"
    assert photo_record["location"] == "Paris"
    assert photo_record["info"] == "Family trip"


def test_pipe_delimiter_takes_precedence_over_colons_and_hyphens(
    successful_validation, photo_record
):
    comment = "Holiday | 2024:2025 | Paris-North | Family: trip"

    extract_usercomment_metadata(comment, photo_record)

    assert photo_record["event"] == "Holiday"
    assert photo_record["year"] == "2024:2025"
    assert photo_record["location"] == "Paris-North"
    assert photo_record["info"] == "Family: trip"


def test_splits_on_colons_and_hyphens_when_no_pipe_exists(
    successful_validation, photo_record
):
    comment = "Holiday:2024-Paris:Family trip"

    extract_usercomment_metadata(comment, photo_record)

    assert photo_record["event"] == "Holiday"
    assert photo_record["year"] == "2024"
    assert photo_record["location"] == "Paris"
    assert photo_record["info"] == "Family trip"


@pytest.mark.parametrize(
    "comment",
    [
        "Holiday:2024:Paris",
        "Holiday:2024:Paris:Family:Extra",
        "An ordinary comment with no delimiters",
    ],
)
def test_non_four_field_comment_is_preserved_as_info(
    comment, photo_record
):
    extract_usercomment_metadata(comment, photo_record)

    assert photo_record["event"] == "Default Event"
    assert photo_record["year"] == ""
    assert photo_record["location"] == ""
    assert photo_record["info"] == comment


def test_missing_comment_leaves_record_unchanged(photo_record):
    original_record = photo_record.copy()

    extract_usercomment_metadata(None, photo_record)

    assert photo_record == original_record


def test_whitespace_is_stripped_from_extracted_fields(
    successful_validation, photo_record
):
    comment = " Holiday | 2024 | Paris | Family trip "

    extract_usercomment_metadata(comment, photo_record)

    assert photo_record["event"] == "Holiday"
    assert photo_record["year"] == "2024"
    assert photo_record["location"] == "Paris"
    assert photo_record["info"] == "Family trip"


def test_year_validation_failure_preserves_entire_comment(
    monkeypatch, photo_record
):
    comment = "Holiday | 50 year reunion | Paris | Family trip"

    monkeypatch.setattr(
        metadata_extraction, "year_validate", lambda value: None
    )
    monkeypatch.setattr(
        metadata_extraction, "location_validate", lambda value: True
    )

    extract_usercomment_metadata(comment, photo_record)

    assert photo_record["event"] == "Default Event"
    assert photo_record["year"] == ""
    assert photo_record["location"] == ""
    assert photo_record["info"] == comment


@pytest.mark.parametrize("location_result", [False, None])
def test_location_validation_failure_preserves_entire_comment(
    monkeypatch, location_result, photo_record
):
    comment = "Holiday | 2024 | Paris | Family trip"

    monkeypatch.setattr(
        metadata_extraction, "year_validate", lambda value: value
    )
    monkeypatch.setattr(
        metadata_extraction,
        "location_validate",
        lambda value: location_result,
    )

    extract_usercomment_metadata(comment, photo_record)

    assert photo_record["event"] == "Default Event"
    assert photo_record["year"] == ""
    assert photo_record["location"] == ""
    assert photo_record["info"] == comment


def test_successful_validation_uses_normalised_year_and_original_location(
    monkeypatch, photo_record
):
    comment = "Holiday | 25/10/2024 | Paris | Family trip"

    monkeypatch.setattr(
        metadata_extraction,
        "year_validate",
        lambda value: "25-Oct-2024",
    )
    monkeypatch.setattr(
        metadata_extraction, "location_validate", lambda value: True
    )

    extract_usercomment_metadata(comment, photo_record)

    assert photo_record["event"] == "Holiday"
    assert photo_record["year"] == "25-Oct-2024"
    assert photo_record["location"] == "Paris"
    assert photo_record["info"] == "Family trip"

