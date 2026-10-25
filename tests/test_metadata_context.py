
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

"""Tests for gathering per-photo metadata context."""

from datetime import datetime
from pathlib import Path

import piexif
import pytest
from PIL import Image
from piexif import helper

from filesystem_importer import metadata_context
from filesystem_importer.metadata_context import (
    gather_photo_metadata_context,
)


@pytest.fixture
def photo_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create source and staged JPEGs in a source directory hierarchy."""
    source_directory = tmp_path / "source"
    source_folder = source_directory / "Event" / "Location"
    source_folder.mkdir(parents=True)

    staged_directory = tmp_path / "staging"
    staged_directory.mkdir()

    source_path = source_folder / "original.jpg"
    staged_path = staged_directory / "staged_2.jpg"

    Image.new("RGB", (20, 20)).save(source_path, format="JPEG")
    Image.new("RGB", (20, 20)).save(staged_path, format="JPEG")

    return source_directory, source_path, staged_path


def write_exif(
    image_path: Path,
    *,
    user_comment: str | None = None,
    date_time_original: str | None = None,
    gps: bool = False,
) -> bytes | None:
    """Write selected test EXIF values and return the raw comment."""
    exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    raw_comment = None
    if user_comment is not None:
        raw_comment = helper.UserComment.dump(user_comment)
        exif["Exif"][piexif.ExifIFD.UserComment] = raw_comment

    if date_time_original is not None:
        exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = (
            date_time_original.encode("ascii")
        )

    if gps:
        exif["GPS"] = {
            piexif.GPSIFD.GPSLatitudeRef: b"S",
            piexif.GPSIFD.GPSLatitude: ((27, 1), (28, 1), (30, 1)),
            piexif.GPSIFD.GPSLongitudeRef: b"E",
            piexif.GPSIFD.GPSLongitude: ((153, 1), (1, 1), (15, 1)),
        }

    piexif.insert(piexif.dump(exif), str(image_path))
    return raw_comment


def gather(
    source_directory: Path,
    source_path: Path,
    staged_path: Path,
):
    """Gather context with representative saved configuration."""
    return gather_photo_metadata_context(
        source_path=source_path,
        staged_path=staged_path,
        source_directory=source_directory,
        directory_classifications={
            "1": "Event",
            "2": "Location",
        },
        workspace_event="Workspace Event",
    )


def test_gathers_paths_and_relative_directory(
    photo_paths: tuple[Path, Path, Path],
) -> None:
    source_directory, source_path, staged_path = photo_paths

    context = gather(source_directory, source_path, staged_path)

    assert context.source_path == source_path.resolve()
    assert context.staged_path == staged_path.resolve()
    assert context.source_directory == source_directory.resolve()
    assert context.relative_directory == Path("Event") / "Location"
    assert context.directory_classifications == {
        "1": "Event",
        "2": "Location",
    }
    assert context.workspace_event == "Workspace Event"


def test_reads_and_preserves_user_comment(
    photo_paths: tuple[Path, Path, Path],
) -> None:
    source_directory, source_path, staged_path = photo_paths
    comment = "UNTAC 1992/93-Battambang-UN Sector 8 HQ in early 1993"
    raw_comment = write_exif(staged_path, user_comment=comment)

    context = gather(source_directory, source_path, staged_path)

    assert context.user_comment == comment
    assert context.user_comment_raw == raw_comment


def test_reads_date_time_original_and_gps(
    photo_paths: tuple[Path, Path, Path],
) -> None:
    source_directory, source_path, staged_path = photo_paths
    write_exif(
        staged_path,
        date_time_original="1993:02:14 10:30:00",
        gps=True,
    )

    context = gather(source_directory, source_path, staged_path)

    assert context.date_time_original == "1993:02:14 10:30:00"
    assert context.gps_latitude == ((27, 1), (28, 1), (30, 1))
    assert context.gps_latitude_ref == "S"
    assert context.gps_longitude == ((153, 1), (1, 1), (15, 1))
    assert context.gps_longitude_ref == "E"


def test_missing_exif_values_are_none(
    photo_paths: tuple[Path, Path, Path],
) -> None:
    source_directory, source_path, staged_path = photo_paths

    context = gather(source_directory, source_path, staged_path)

    assert context.user_comment is None
    assert context.user_comment_raw is None
    assert context.date_time_original is None
    assert context.gps_latitude is None
    assert context.gps_latitude_ref is None
    assert context.gps_longitude is None
    assert context.gps_longitude_ref is None


def test_derived_fields_start_as_none(
    photo_paths: tuple[Path, Path, Path],
) -> None:
    source_directory, source_path, staged_path = photo_paths

    context = gather(source_directory, source_path, staged_path)

    for field in (
        "event_ancestor",
        "year_ancestor",
        "location_ancestor",
        "info_ancestor",
        "event_comment",
        "year_comment",
        "location_comment",
        "info_comment",
        "geo_location",
        "comment_components",
    ):
        assert getattr(context, field) is None


def test_missing_source_file_raises_clear_error(
    photo_paths: tuple[Path, Path, Path],
) -> None:
    source_directory, source_path, staged_path = photo_paths
    source_path.unlink()

    with pytest.raises(ValueError, match="Source photo does not exist"):
        gather(source_directory, source_path, staged_path)


def test_missing_staged_file_raises_clear_error(
    photo_paths: tuple[Path, Path, Path],
) -> None:
    source_directory, source_path, staged_path = photo_paths
    staged_path.unlink()

    with pytest.raises(ValueError, match="Staged photo does not exist"):
        gather(source_directory, source_path, staged_path)


def test_source_outside_source_directory_is_rejected(
    photo_paths: tuple[Path, Path, Path],
) -> None:
    source_directory, source_path, staged_path = photo_paths

    with pytest.raises(ValueError, match="outside the source directory"):
        gather(
            source_directory / "different-root",
            source_path,
            staged_path,
        )

def test_timestamp_failure_does_not_stop_metadata_gathering(
    photo_paths: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_directory, source_path, staged_path = photo_paths
    write_exif(staged_path, user_comment="Test comment")

    class FailingDateTime:
        @staticmethod
        def fromtimestamp(value):
            raise OSError("Simulated timestamp conversion failure")

    monkeypatch.setattr(
        metadata_context,
        "datetime",
        FailingDateTime,
    )

    context = gather(source_directory, source_path, staged_path)

    assert context.filesystem_timestamp is None
    assert context.user_comment == "Test comment"

def test_invalid_exif_file_returns_empty_exif_values(
    photo_paths: tuple[Path, Path, Path],
) -> None:
    source_directory, source_path, staged_path = photo_paths
    staged_path.write_bytes(b"not an image")

    context = gather(source_directory, source_path, staged_path)

    assert context.user_comment is None
    assert context.date_time_original is None
    assert context.gps_latitude is None
    assert context.gps_longitude is None

