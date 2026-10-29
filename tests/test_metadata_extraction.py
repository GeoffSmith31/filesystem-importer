
"""Tests for extracting probable metadata from UserComment."""

import pytest
from piexif import helper

from filesystem_importer.metadata_extraction import (
    extract_usercomment_metadata,
)


def encode_comment(comment: str) -> bytes:
    """Encode a comment using piexif's standard UserComment encoding."""
    return helper.UserComment.dump(comment)


def test_extracts_four_fields_using_pipe_delimiters():
    comment = encode_comment("Holiday | 2024 | Paris | Family trip")

    result = extract_usercomment_metadata(comment)

    assert result.exif_event == "Holiday"
    assert result.exif_year == "2024"
    assert result.exif_location == "Paris"
    assert result.exif_info == "Family trip"


def test_pipe_delimiter_takes_precedence_over_colons_and_hyphens():
    comment = encode_comment("Holiday | 2024:2025 | Paris-North | Family: trip")

    result = extract_usercomment_metadata(comment)

    assert result.exif_event == "Holiday"
    assert result.exif_year == "2024:2025"
    assert result.exif_location == "Paris-North"
    assert result.exif_info == "Family: trip"


def test_splits_on_colons_and_hyphens_when_no_pipe_exists():
    comment = encode_comment("Holiday:2024-Paris:Family trip")

    result = extract_usercomment_metadata(comment)

    assert result.exif_event == "Holiday"
    assert result.exif_year == "2024"
    assert result.exif_location == "Paris"
    assert result.exif_info == "Family trip"


@pytest.mark.parametrize(
    "comment",
    [
        "Holiday:2024:Paris",
        "Holiday:2024:Paris:Family:Extra",
        "An ordinary comment with no delimiters",
    ],
)
def test_non_four_field_comment_is_preserved_as_info(comment):
    result = extract_usercomment_metadata(encode_comment(comment))

    assert result.exif_event is None
    assert result.exif_year is None
    assert result.exif_location is None
    assert result.exif_info == comment


def test_missing_comment_returns_empty_metadata():
    result = extract_usercomment_metadata(None)

    assert result.exif_event is None
    assert result.exif_year is None
    assert result.exif_location is None
    assert result.exif_info is None


def test_whitespace_is_stripped_from_extracted_fields():
    comment = encode_comment(" Holiday | 2024 | Paris | Family trip ")

    result = extract_usercomment_metadata(comment)

    assert result.exif_event == "Holiday"
    assert result.exif_year == "2024"
    assert result.exif_location == "Paris"
    assert result.exif_info == "Family trip"

