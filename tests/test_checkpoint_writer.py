
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

"""Tests for initial checkpoint creation."""

import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from filesystem_importer.checkpoint_writer import (
    build_initial_checkpoint,
    write_initial_checkpoint,
)
from filesystem_importer.constants import (
    APP_VERSION,
    CHECKPOINT_FILENAME,
    IMAGE_FOLDER_NAME,
    IMPORTER_ID,
    SCHEMA_VERSION,
    SOURCE_NAME,
)
from filesystem_importer.classification_dialog import MAX_CLASSIFICATION_LEVELS


@pytest.fixture
def source_directory(tmp_path: Path) -> Path:
    """Provide a temporary source directory."""
    source = tmp_path / "Filesystem-Test"
    source.mkdir()
    return source


@pytest.fixture
def classifications() -> dict[str, str]:
    """Provide representative directory classifications."""
    return {
        "1": "Event",
        "2": "Location",
        "3": "Year",
        "4": "Info",
    }


def test_initial_checkpoint_has_required_structure(
    source_directory: Path,
    classifications: dict[str, str],
) -> None:
    checkpoint = build_initial_checkpoint(
        source_directory,
        "Test Event",
        classifications,
    )

    assert set(checkpoint) == {
        "workspace",
        "metadata_policies",
        "photos",
        "filesystem_importer",
    }

    workspace = checkpoint["workspace"]
    assert set(workspace) == {
        "schema",
        "importer",
        "source",
        "source_id",
        "source_title",
        "registration_status",
        "download_status",
        "event",
        "image_folder",
        "created_at",
    }

    assert workspace["schema"] == SCHEMA_VERSION
    assert workspace["importer"] == f"{IMPORTER_ID}/{APP_VERSION}"
    assert workspace["source"] == SOURCE_NAME
    assert workspace["source_id"] == str(source_directory.resolve())
    assert workspace["source_title"] == source_directory.name
    assert workspace["registration_status"] == "NOT_STARTED"
    assert workspace["download_status"] == "NOT_STARTED"
    assert workspace["event"] == "Test Event"
    assert workspace["image_folder"] == IMAGE_FOLDER_NAME

    assert set(checkpoint["metadata_policies"]) == {
        "event",
        "year",
        "location",
        "info",
    }

    for policy in checkpoint["metadata_policies"].values():
        assert set(policy) == {"propagate", "priority", "default"}
        assert policy["propagate"] in {"event", "group", "location", "none"}
        assert isinstance(policy["priority"], list)
        assert isinstance(policy["default"], str)

    assert checkpoint["photos"] == []

    importer_data = checkpoint["filesystem_importer"]

    assert importer_data["classification_limit"] == MAX_CLASSIFICATION_LEVELS
    assert importer_data["directory_classifications"] == classifications

    manifest = importer_data["source_manifest"]
    assert manifest["algorithm"] == "sha256"
    assert len(manifest["fingerprint"]) == 64
    assert all(
        character in "0123456789abcdef"
        for character in manifest["fingerprint"]
    )
    assert manifest["candidate_count"] == 0


def test_created_at_is_utc_timestamp(
    source_directory: Path,
    classifications: dict[str, str],
) -> None:
    checkpoint = build_initial_checkpoint(
        source_directory,
        "Test Event",
        classifications,
    )

    timestamp = checkpoint["workspace"]["created_at"]

    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z",
        timestamp,
    )

    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed.utcoffset().total_seconds() == 0


def test_event_name_is_trimmed(
    source_directory: Path,
    classifications: dict[str, str],
) -> None:
    checkpoint = build_initial_checkpoint(
        source_directory,
        "  Test Event  ",
        classifications,
    )

    assert checkpoint["workspace"]["event"] == "Test Event"
    assert checkpoint["workspace"]["source_title"] == source_directory.name


@pytest.mark.parametrize("event_name", ["", " ", "   \t  "])
def test_empty_event_name_is_rejected(
    source_directory: Path,
    classifications: dict[str, str],
    event_name: str,
) -> None:
    with pytest.raises(ValueError, match="Event name"):
        build_initial_checkpoint(
            source_directory,
            event_name,
            classifications,
        )


def test_invalid_classification_level_is_rejected(
    source_directory: Path,
) -> None:
    with pytest.raises(ValueError, match="(?i)classification level"):
        build_initial_checkpoint(
            source_directory,
            "Test Event",
            {"0": "Event"},
        )

def test_missing_classification_level_is_rejected(
    source_directory: Path,
) -> None:
    with pytest.raises(ValueError, match="missing levels"):
        build_initial_checkpoint(
            source_directory,
            "Test Event",
            {
                "1": "Event",
                "3": "Year",
            },
        )

def test_classification_above_limit_is_rejected(
    source_directory: Path,
) -> None:
    too_deep = str(MAX_CLASSIFICATION_LEVELS + 1)

    with pytest.raises(ValueError, match="(?i)classification level"):
        build_initial_checkpoint(
            source_directory,
            "Test Event",
            {too_deep: "Event"},
        )


def test_invalid_classification_category_is_rejected(
    source_directory: Path,
) -> None:
    with pytest.raises(ValueError, match="classification category"):
        build_initial_checkpoint(
            source_directory,
            "Test Event",
            {"1": "Unknown"},
        )


def test_missing_source_directory_is_rejected(
    tmp_path: Path,
    classifications: dict[str, str],
) -> None:
    missing_source = tmp_path / "does-not-exist"

    with pytest.raises(ValueError, match="source directory"):
        build_initial_checkpoint(
            missing_source,
            "Test Event",
            classifications,
        )


def test_checkpoint_and_image_folder_are_created(
    tmp_path: Path,
    source_directory: Path,
    classifications: dict[str, str],
) -> None:
    staging = tmp_path / "staging"

    checkpoint_path = write_initial_checkpoint(
        staging,
        source_directory,
        "Test Event",
        classifications,
    )

    assert checkpoint_path == staging / CHECKPOINT_FILENAME
    assert checkpoint_path.is_file()
    assert (staging / IMAGE_FOLDER_NAME).is_dir()

    with checkpoint_path.open(encoding="utf-8") as file:
        checkpoint = json.load(file)

    assert checkpoint["workspace"]["source_id"] == str(
        source_directory.resolve()
    )
    assert checkpoint["photos"] == []


def test_existing_checkpoint_is_not_overwritten(
    tmp_path: Path,
    source_directory: Path,
    classifications: dict[str, str],
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()

    checkpoint_path = staging / CHECKPOINT_FILENAME
    original_content = '{"preserve": true}\n'
    checkpoint_path.write_text(original_content, encoding="utf-8")

    with pytest.raises(FileExistsError, match="checkpoint already exists"):
        write_initial_checkpoint(
            staging,
            source_directory,
            "Test Event",
            classifications,
        )

    assert checkpoint_path.read_text(encoding="utf-8") == original_content
