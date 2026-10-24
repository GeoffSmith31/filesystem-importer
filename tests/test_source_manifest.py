
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

"""Tests for source manifest creation."""

import os
from pathlib import Path

import pytest

from filesystem_importer.file_discovery import scan_source_directory
from filesystem_importer.source_manifest import build_source_manifest


@pytest.fixture
def source_directory(tmp_path: Path) -> Path:
    """Create a small source tree with two candidate photos."""

    source = tmp_path / "Test Event"
    location = source / "London"
    location.mkdir(parents=True)

    (location / "photo1.jpg").write_bytes(b"photo one")
    (location / "photo2.jpg").write_bytes(b"photo two")

    (source / "notes.txt").write_text(
        "Not a candidate image",
        encoding="utf-8",
    )

    return source


def fingerprint(source: Path) -> dict:
    """Scan a source and build its manifest."""

    return build_source_manifest(scan_source_directory(source))


def test_repeated_calculation_is_stable(
    source_directory: Path,
) -> None:
    first = fingerprint(source_directory)
    second = fingerprint(source_directory)

    assert first["fingerprint"] == second["fingerprint"]
    assert first["candidate_count"] == 2
    assert first["algorithm"] == "sha256"


def test_adding_candidate_changes_fingerprint(
    source_directory: Path,
) -> None:
    before = fingerprint(source_directory)

    (source_directory / "new.jpg").write_bytes(b"new photo")

    after = fingerprint(source_directory)

    assert after["candidate_count"] == 3
    assert after["fingerprint"] != before["fingerprint"]


def test_removing_candidate_changes_fingerprint(
    source_directory: Path,
) -> None:
    before = fingerprint(source_directory)

    (source_directory / "London" / "photo2.jpg").unlink()

    after = fingerprint(source_directory)

    assert after["candidate_count"] == 1
    assert after["fingerprint"] != before["fingerprint"]


def test_renaming_candidate_changes_fingerprint(
    source_directory: Path,
) -> None:
    before = fingerprint(source_directory)

    (source_directory / "London" / "photo1.jpg").rename(
        source_directory / "London" / "renamed.jpg"
    )

    after = fingerprint(source_directory)

    assert after["fingerprint"] != before["fingerprint"]


def test_renaming_relevant_directory_changes_fingerprint(
    source_directory: Path,
) -> None:
    before = fingerprint(source_directory)

    (source_directory / "London").rename(
        source_directory / "Paris"
    )

    after = fingerprint(source_directory)

    assert after["fingerprint"] != before["fingerprint"]


def test_changing_file_size_changes_fingerprint(
    source_directory: Path,
) -> None:
    photo = source_directory / "London" / "photo1.jpg"
    before = fingerprint(source_directory)

    photo.write_bytes(b"a different size")

    after = fingerprint(source_directory)

    assert after["fingerprint"] != before["fingerprint"]


def test_changing_modification_time_changes_fingerprint(
    source_directory: Path,
) -> None:
    photo = source_directory / "London" / "photo1.jpg"
    before = fingerprint(source_directory)

    stat = photo.stat()
    os.utime(
        photo,
        ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000),
    )

    after = fingerprint(source_directory)

    assert after["fingerprint"] != before["fingerprint"]


def test_scan_errors_prevent_fingerprinting(
    source_directory: Path,
) -> None:
    scan_result = scan_source_directory(source_directory)

    scan_result_with_error = type(scan_result)(
        source_directory=scan_result.source_directory,
        candidate_files=scan_result.candidate_files,
        directories_with_candidates=scan_result.directories_with_candidates,
        relevant_directories=scan_result.relevant_directories,
        scan_errors=("simulated scan error",),
    )

    with pytest.raises(ValueError, match="scan errors"):
        build_source_manifest(scan_result_with_error)


def test_case_only_filename_differences_have_deterministic_order(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Case-Test"
    source.mkdir()

    for name in ("Photo.jpg", "photo.jpg", "PHOTO.jpg"):
        (source / name).write_bytes(b"image")

    first_scan = scan_source_directory(source)
    second_scan = scan_source_directory(source)

    first_names = [path.name for path in first_scan.candidate_files]
    second_names = [path.name for path in second_scan.candidate_files]

    assert first_names == second_names
    assert first_names == ["PHOTO.jpg", "Photo.jpg", "photo.jpg"]

    first_manifest = build_source_manifest(first_scan)
    second_manifest = build_source_manifest(second_scan)

    assert first_manifest["fingerprint"] == second_manifest["fingerprint"]
