
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

"""Tests for staging and EXIF capability testing."""

from pathlib import Path

import piexif
import pytest
from PIL import Image
from piexif import helper
from filesystem_importer.exif_capability import ExifCapabilityResult
from filesystem_importer import photo_staging
from filesystem_importer.photo_staging import (
    StagingFatalError,
    stage_and_test_photo,
)


def make_jpeg(path: Path, comment: str | None = None) -> Path:
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


def test_success_keeps_staged_copy_and_leaves_source_unchanged(tmp_path):
    source = make_jpeg(tmp_path / "source.jpg", "Original")
    original_bytes = source.read_bytes()
    photos = tmp_path / "photos"
    photos.mkdir()

    result = stage_and_test_photo(source, photos)

    assert result.success is True
    assert result.staged_filename
    assert (photos / result.staged_filename).is_file()
    assert source.read_bytes() == original_bytes


def test_failed_capability_test_deletes_staged_copy(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    source.write_bytes(b"test content")
    photos = tmp_path / "photos"
    photos.mkdir()

    monkeypatch.setattr(
        photo_staging,
        "check_usercomment_capability",
        lambda path: ExifCapabilityResult(
            supported=False,
            reason="Unsupported format",
        ),
    )

    result = stage_and_test_photo(source, photos)

    assert result.success is False
    assert result.staged_filename == ""
    assert list(photos.iterdir()) == []


def test_failed_cleanup_raises_fatal_error(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    source.write_bytes(b"test content")
    photos = tmp_path / "photos"
    photos.mkdir()

    monkeypatch.setattr(
        photo_staging,
        "check_usercomment_capability",
        lambda path: ExifCapabilityResult(
            supported=False,
            reason="Unsupported format",
        ),
    )

    def fail_unlink(self, *args, **kwargs):
        raise PermissionError("Deletion denied")

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    with pytest.raises(StagingFatalError, match="could not be deleted"):
        stage_and_test_photo(source, photos)


def test_missing_source_is_rejected(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()

    with pytest.raises(ValueError, match="Source photo does not exist"):
        stage_and_test_photo(tmp_path / "missing.jpg", photos)


def test_missing_photos_directory_is_rejected(tmp_path):
    source = tmp_path / "source.jpg"
    make_jpeg(source)

    with pytest.raises(ValueError, match="Staging photos directory"):
        stage_and_test_photo(source, tmp_path / "missing")

def test_original_filename_is_preserved_when_available(tmp_path):
    source = make_jpeg(tmp_path / "IMG_1234.jpg", "Original")
    photos = tmp_path / "photos"
    photos.mkdir()

    result = stage_and_test_photo(source, photos)

    assert result.success is True
    assert result.staged_filename == "IMG_1234.jpg"
    assert (photos / "IMG_1234.jpg").is_file()


def test_filename_collision_uses_numbered_suffix(tmp_path):
    source = make_jpeg(tmp_path / "IMG_1234.jpg", "Original")
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "IMG_1234.jpg").write_bytes(b"existing staged file")

    result = stage_and_test_photo(source, photos)

    assert result.success is True
    assert result.staged_filename == "IMG_1234_2.jpg"
    assert (photos / "IMG_1234.jpg").read_bytes() == b"existing staged file"
    assert (photos / "IMG_1234_2.jpg").is_file()

