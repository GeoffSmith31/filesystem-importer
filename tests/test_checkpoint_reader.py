
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

"""Tests for reading and validating import checkpoints."""

import json
from pathlib import Path

import pytest

from filesystem_importer.checkpoint_reader import read_checkpoint
from filesystem_importer.checkpoint_writer import build_initial_checkpoint
from filesystem_importer.constants import (
    CHECKPOINT_FILENAME,
    IMPORTER_ID,
    SCHEMA_VERSION,
)


@pytest.fixture
def source_directory(tmp_path: Path) -> Path:
    """Create a source tree with four relevant levels."""

    source = tmp_path / "Filesystem-Test"
    photo_directory = source / "Location" / "2024" / "Holiday"
    photo_directory.mkdir(parents=True)

    # Discovery uses file extensions, so these files need not contain
    # valid image data for a directory-depth test.
    (photo_directory / "photo.jpg").write_bytes(b"test")

    return source


@pytest.fixture
def checkpoint_path(
    tmp_path: Path,
    source_directory: Path,
) -> Path:
    """Write a valid checkpoint for the test source tree."""

    checkpoint = build_initial_checkpoint(
        source_directory,
        "Test Event",
        {
            "1": "Event",
            "2": "Location",
            "3": "Year",
            "4": "Info",
        },
    )

    path = tmp_path / CHECKPOINT_FILENAME
    path.write_text(
        json.dumps(checkpoint, indent=4),
        encoding="utf-8",
    )
    return path


def load_json(path: Path) -> dict:
    """Load a checkpoint as a mutable dictionary for test setup."""

    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, checkpoint: dict) -> None:
    """Save modified checkpoint test data."""

    path.write_text(
        json.dumps(checkpoint, indent=4),
        encoding="utf-8",
    )


def test_valid_checkpoint_is_read_without_modification(
    checkpoint_path: Path,
    source_directory: Path,
) -> None:
    original_contents = checkpoint_path.read_bytes()

    checkpoint, scan_result = read_checkpoint(checkpoint_path)

    assert checkpoint["workspace"]["source_id"] == str(
        source_directory.resolve()
    )
    assert checkpoint["workspace"]["event"] == "Test Event"
    assert checkpoint["filesystem_importer"]["directory_classifications"] == {
        "1": "Event",
        "2": "Location",
        "3": "Year",
        "4": "Info",
    }

    manifest = checkpoint["filesystem_importer"]["source_manifest"]
    assert manifest["algorithm"] == "sha256"
    assert len(manifest["fingerprint"]) == 64
    assert manifest["candidate_count"] == 1

    assert scan_result.source_directory == source_directory
    assert checkpoint_path.read_bytes() == original_contents


def test_wrong_importer_is_rejected(checkpoint_path: Path) -> None:
    checkpoint = load_json(checkpoint_path)
    checkpoint["workspace"]["importer"] = "another-importer/1.0.0"
    save_json(checkpoint_path, checkpoint)

    with pytest.raises(ValueError, match="does not belong"):
        read_checkpoint(checkpoint_path)


def test_importer_version_may_be_older(checkpoint_path: Path) -> None:
    checkpoint = load_json(checkpoint_path)
    checkpoint["workspace"]["importer"] = f"{IMPORTER_ID}/0.0.1"
    save_json(checkpoint_path, checkpoint)

    read_checkpoint(checkpoint_path)


def test_missing_importer_version_is_rejected(
    checkpoint_path: Path,
) -> None:
    checkpoint = load_json(checkpoint_path)
    checkpoint["workspace"]["importer"] = IMPORTER_ID
    save_json(checkpoint_path, checkpoint)

    with pytest.raises(ValueError, match="version"):
        read_checkpoint(checkpoint_path)


def test_unsupported_schema_is_rejected(
    checkpoint_path: Path,
) -> None:
    checkpoint = load_json(checkpoint_path)
    checkpoint["workspace"]["schema"] = SCHEMA_VERSION + 1
    save_json(checkpoint_path, checkpoint)

    with pytest.raises(ValueError, match="schema"):
        read_checkpoint(checkpoint_path)


def test_missing_source_directory_is_rejected(
    checkpoint_path: Path,
    tmp_path: Path,
) -> None:
    checkpoint = load_json(checkpoint_path)
    checkpoint["workspace"]["source_id"] = str(
        tmp_path / "missing-source"
    )
    save_json(checkpoint_path, checkpoint)

    with pytest.raises(ValueError, match="source directory"):
        read_checkpoint(checkpoint_path)


def test_missing_classification_level_is_rejected(
    checkpoint_path: Path,
) -> None:
    checkpoint = load_json(checkpoint_path)
    checkpoint["filesystem_importer"]["directory_classifications"] = {
        "1": "Event",
        "2": "Location",
        "4": "Info",
    }
    save_json(checkpoint_path, checkpoint)

    with pytest.raises(ValueError, match="classifications|levels"):
        read_checkpoint(checkpoint_path)


def test_invalid_classification_category_is_rejected(
    checkpoint_path: Path,
) -> None:
    checkpoint = load_json(checkpoint_path)
    checkpoint["filesystem_importer"]["directory_classifications"]["3"] = (
        "Unknown"
    )
    save_json(checkpoint_path, checkpoint)

    with pytest.raises(ValueError, match="Invalid category"):
        read_checkpoint(checkpoint_path)


def test_new_relevant_level_is_rejected(
    checkpoint_path: Path,
    source_directory: Path,
) -> None:
    new_directory = source_directory / "Location" / "2024" / "Holiday" / "Extra"
    new_directory.mkdir()
    (new_directory / "another.jpg").write_bytes(b"test")

    with pytest.raises(ValueError, match="source directory has changed"):
        read_checkpoint(checkpoint_path)


def test_removed_relevant_level_is_rejected(
    checkpoint_path: Path,
    source_directory: Path,
) -> None:
    photo = (
        source_directory / "Location" / "2024" / "Holiday" / "photo.jpg"
    )
    photo.unlink()

    # Leave a candidate at Level 3 instead of Level 4.
    new_photo_directory = source_directory / "Location" / "2024"
    (new_photo_directory / "photo.jpg").write_bytes(b"test")

    with pytest.raises(ValueError, match="source directory has changed"):
        read_checkpoint(checkpoint_path)


def test_malformed_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / CHECKPOINT_FILENAME
    path.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(ValueError, match="valid JSON"):
        read_checkpoint(path)

def test_missing_source_manifest_is_rejected(
    checkpoint_path: Path,
) -> None:
    checkpoint = load_json(checkpoint_path)
    del checkpoint["filesystem_importer"]["source_manifest"]
    save_json(checkpoint_path, checkpoint)

    with pytest.raises(ValueError, match="no source fingerprint"):
        read_checkpoint(checkpoint_path)


def test_changed_fingerprint_is_rejected(
    checkpoint_path: Path,
) -> None:
    checkpoint = load_json(checkpoint_path)
    checkpoint["filesystem_importer"]["source_manifest"]["fingerprint"] = (
        "0" * 64
    )
    save_json(checkpoint_path, checkpoint)

    with pytest.raises(ValueError, match="source directory has changed"):
        read_checkpoint(checkpoint_path)
