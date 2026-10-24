
# =============================================================================
#
# Filesystem Importer
#
# Copyright (c) 2026 Geoff <dev.photomanager@gmail.com>
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# =============================================================================

"""Tests for staged JPEG EXIF UserComment capability."""

from pathlib import Path

import piexif
import pytest
from PIL import Image
from piexif import helper

from filesystem_importer.exif_capability import check_usercomment_capability


def make_jpeg(path: Path, comment: str | None = None) -> Path:
    """Create a small JPEG fixture with an optional UserComment."""
    Image.new("RGB", (8, 8), (120, 140, 160)).save(path, format="JPEG")

    if comment is not None:
        exif_data = {
            "0th": {},
            "Exif": {
                piexif.ExifIFD.UserComment: helper.UserComment.dump(comment),
            },
            "GPS": {},
            "1st": {},
            "thumbnail": None,
        }
        piexif.insert(piexif.dump(exif_data), str(path))

    return path


def read_comment(path: Path) -> bytes | None:
    exif_data = piexif.load(str(path))
    return exif_data["Exif"].get(piexif.ExifIFD.UserComment)


def test_capability_succeeds_and_restores_existing_comment(tmp_path):
    image_path = make_jpeg(tmp_path / "existing.jpg", "Original comment")
    original_comment = read_comment(image_path)

    result = check_usercomment_capability(image_path)

    assert result.supported is True
    assert read_comment(image_path) == original_comment


def test_capability_succeeds_and_removes_comment_when_originally_absent(tmp_path):
    image_path = make_jpeg(tmp_path / "absent.jpg")

    assert read_comment(image_path) is None

    result = check_usercomment_capability(image_path)

    assert result.supported is True
    assert read_comment(image_path) is None


def test_non_jpeg_is_reported_as_unsupported(tmp_path):
    image_path = tmp_path / "photo.webp"
    image_path.write_bytes(b"not a real WebP file")

    result = check_usercomment_capability(image_path)

    assert result.supported is False
    assert "limited to JPEG" in result.reason


def test_invalid_jpeg_is_reported_as_unsupported(tmp_path):
    image_path = tmp_path / "broken.jpg"
    image_path.write_bytes(b"not a valid JPEG")

    result = check_usercomment_capability(image_path)

    assert result.supported is False
    assert result.reason


@pytest.mark.parametrize("comment", ["", "Short comment", "A comment with Unicode: café"])
def test_existing_comment_is_preserved_exactly(tmp_path, comment):
    image_path = make_jpeg(tmp_path / "preserve.jpg", comment)
    original_comment = read_comment(image_path)

    result = check_usercomment_capability(image_path)

    assert result.supported is True
    assert read_comment(image_path) == original_comment

def test_capability_preserves_unrelated_exif_tags(tmp_path):
    image_path = make_jpeg(tmp_path / "metadata.jpg", "Original comment")

    exif_data = piexif.load(str(image_path))
    exif_data["0th"][piexif.ImageIFD.Make] = b"Test Camera"
    exif_data["0th"][piexif.ImageIFD.Model] = b"Test Model"
    exif_data["Exif"][piexif.ExifIFD.DateTimeOriginal] = (
        b"2024:05:06 12:34:56"
    )
    piexif.insert(piexif.dump(exif_data), str(image_path))

    original_exif = piexif.load(str(image_path))

    result = check_usercomment_capability(image_path)

    assert result.supported is True

    restored_exif = piexif.load(str(image_path))
    assert restored_exif["0th"][piexif.ImageIFD.Make] == (
        original_exif["0th"][piexif.ImageIFD.Make]
    )
    assert restored_exif["0th"][piexif.ImageIFD.Model] == (
        original_exif["0th"][piexif.ImageIFD.Model]
    )
    assert restored_exif["Exif"][piexif.ExifIFD.DateTimeOriginal] == (
        original_exif["Exif"][piexif.ExifIFD.DateTimeOriginal]
    )
    assert read_comment(image_path) == read_comment_from_exif(original_exif)


def read_comment_from_exif(exif_data):
    return exif_data["Exif"].get(piexif.ExifIFD.UserComment)

