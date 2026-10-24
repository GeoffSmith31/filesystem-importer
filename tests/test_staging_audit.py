
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

"""Tests for auditing the staging photos directory."""

from pathlib import Path

import pytest

from filesystem_importer.staging_audit import audit_staging_directory


def make_photos_directory(tmp_path: Path) -> Path:
    """Create an empty staging photos directory."""
    directory = tmp_path / "photos"
    directory.mkdir()
    return directory


def test_matching_staged_file_is_kept(tmp_path: Path) -> None:
    photos_directory = make_photos_directory(tmp_path)
    (photos_directory / "photo.jpg").write_bytes(b"photo")

    result = audit_staging_directory(
        photos_directory,
        [{"file": "photo.jpg"}],
    )

    assert (photos_directory / "photo.jpg").exists()
    assert result.files_checked == 1
    assert result.orphan_files_deleted == ()


def test_unrecorded_staged_file_is_deleted(tmp_path: Path) -> None:
    photos_directory = make_photos_directory(tmp_path)
    (photos_directory / "orphan.jpg").write_bytes(b"orphan")

    result = audit_staging_directory(photos_directory, [])

    assert not (photos_directory / "orphan.jpg").exists()
    assert result.files_checked == 1
    assert result.orphan_files_deleted == ("orphan.jpg",)


def test_empty_file_record_does_not_match_any_staged_file(
    tmp_path: Path,
) -> None:
    photos_directory = make_photos_directory(tmp_path)
    (photos_directory / "orphan.jpg").write_bytes(b"orphan")

    result = audit_staging_directory(
        photos_directory,
        [{"file": ""}],
    )

    assert not (photos_directory / "orphan.jpg").exists()
    assert result.orphan_files_deleted == ("orphan.jpg",)


def test_record_without_staged_file_is_allowed(
    tmp_path: Path,
) -> None:
    photos_directory = make_photos_directory(tmp_path)

    result = audit_staging_directory(
        photos_directory,
        [{"file": "missing.jpg"}],
    )

    assert result.files_checked == 0
    assert result.orphan_files_deleted == ()


def test_multiple_records_and_files(tmp_path: Path) -> None:
    photos_directory = make_photos_directory(tmp_path)
    (photos_directory / "photo-a.jpg").write_bytes(b"a")
    (photos_directory / "photo-b.jpg").write_bytes(b"b")
    (photos_directory / "orphan.jpg").write_bytes(b"orphan")

    result = audit_staging_directory(
        photos_directory,
        [
            {"file": "photo-a.jpg"},
            {"file": "photo-b.jpg"},
            {"file": ""},
        ],
    )

    assert (photos_directory / "photo-a.jpg").exists()
    assert (photos_directory / "photo-b.jpg").exists()
    assert not (photos_directory / "orphan.jpg").exists()
    assert result.orphan_files_deleted == ("orphan.jpg",)


@pytest.mark.parametrize(
    "photo_records",
    [
        None,
        {},
        "not a list",
        [None],
        ["not a record"],
        [{}],
        [{"file": None}],
        [{"file": 123}],
        [{"file": "../outside.jpg"}],
        [{"file": "nested/photo.jpg"}],
        [{"file": "photo.jpg"}, {"file": "photo.jpg"}],
    ],
)
def test_malformed_or_ambiguous_records_are_rejected_without_deletion(
    tmp_path: Path,
    photo_records: object,
) -> None:
    photos_directory = make_photos_directory(tmp_path)
    staged_file = photos_directory / "orphan.jpg"
    staged_file.write_bytes(b"orphan")

    with pytest.raises(ValueError):
        audit_staging_directory(photos_directory, photo_records)  # type: ignore[arg-type]

    assert staged_file.exists()


def test_unexpected_subdirectory_is_rejected_without_deletion(
    tmp_path: Path,
) -> None:
    photos_directory = make_photos_directory(tmp_path)
    (photos_directory / "orphan.jpg").write_bytes(b"orphan")
    (photos_directory / "unexpected").mkdir()

    with pytest.raises(ValueError, match="subdirectory"):
        audit_staging_directory(photos_directory, [])

    assert (photos_directory / "orphan.jpg").exists()


def test_symlink_is_rejected_without_deletion(
    tmp_path: Path,
) -> None:
    photos_directory = make_photos_directory(tmp_path)
    outside_file = tmp_path / "outside.jpg"
    outside_file.write_bytes(b"outside")
    (photos_directory / "link.jpg").symlink_to(outside_file)

    with pytest.raises(ValueError, match="symbolic link"):
        audit_staging_directory(photos_directory, [])

    assert outside_file.exists()
    assert (photos_directory / "link.jpg").is_symlink()


def test_missing_photos_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        audit_staging_directory(tmp_path / "missing", [])
