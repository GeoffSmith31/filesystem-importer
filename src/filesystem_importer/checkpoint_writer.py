
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

"""Create the initial importing.json checkpoint."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filesystem_importer.app_logging import get_logger
from filesystem_importer.classification_dialog import MAX_CLASSIFICATION_LEVELS
from filesystem_importer.constants import (
    APP_VERSION,
    CHECKPOINT_FILENAME,
    IMAGE_FOLDER_NAME,
    IMPORTER_ID,
    SCHEMA_VERSION,
    SOURCE_NAME,
)
from filesystem_importer.file_discovery import scan_source_directory
from filesystem_importer.source_manifest import build_source_manifest

logger = get_logger(__name__)


def build_initial_checkpoint(
    source_directory: Path,
    event_name: str,
    classifications: dict[str, str],
) -> dict[str, Any]:
    """Build the initial checkpoint data without writing any files."""

    source_directory = Path(source_directory)
    event_name = event_name.strip()

    if not source_directory.is_dir():
        raise ValueError("The source directory does not exist or is not a directory.")

    if not event_name:
        raise ValueError("The Event name must not be empty.")

    if not classifications:
        raise ValueError("Directory classifications must not be empty.")

    normalised_classifications: dict[str, str] = {}

    for level, category in classifications.items():
        try:
            level_number = int(level)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid classification level: {level!r}") from exc

        if not 1 <= level_number <= MAX_CLASSIFICATION_LEVELS:
            raise ValueError(
                f"Classification level must be between 1 and "
                f"{MAX_CLASSIFICATION_LEVELS}: {level!r}"
            )

        if category not in {"Event", "Location", "Year", "Info", "Ignore"}:
            raise ValueError(f"Invalid classification category: {category!r}")

        normalised_classifications[str(level_number)] = category

    classified_levels = {
        int(level) for level in normalised_classifications
    }
    expected_levels = set(range(1, max(classified_levels) + 1))

    if classified_levels != expected_levels:
        missing_levels = sorted(expected_levels - classified_levels)
        raise ValueError(
            f"Directory classifications have missing levels: {missing_levels}"
        )

    created_at = (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

    scan_result = scan_source_directory(source_directory)
    manifest = build_source_manifest(scan_result)

    source_id = str(source_directory.resolve())

    checkpoint = {
        "workspace": {
            "schema": SCHEMA_VERSION,
            "importer": f"{IMPORTER_ID}/{APP_VERSION}",
            "source": SOURCE_NAME,
            "source_id": source_id,
            "source_title": source_directory.name,
            "registration_status": "NOT_STARTED",
            "download_status": "NOT_STARTED",
            "event": event_name,
            "image_folder": IMAGE_FOLDER_NAME,
            "created_at": created_at,
        },
        "metadata_policies": {
            "event": {
                "propagate": "none",
                "priority": [],
                "default": "",
            },
            "year": {
                "propagate": "none",
                "priority": [],
                "default": "",
            },
            "location": {
                "propagate": "location",
                "priority": [],
                "default": "",
            },
            "info": {
                "propagate": "group",
                "priority": [],
                "default": "",
            },
        },
        "photos": [],
        "filesystem_importer": {
            "classification_limit": MAX_CLASSIFICATION_LEVELS,
            "directory_classifications": normalised_classifications,
            "source_manifest": {
                "algorithm": manifest["algorithm"],
                "fingerprint": manifest["fingerprint"],
                "candidate_count": manifest["candidate_count"],
            },
        },
    }

    return checkpoint


def write_initial_checkpoint(
    staging_directory: Path,
    source_directory: Path,
    event_name: str,
    classifications: dict[str, str],
) -> Path:
    """Create the image folder and write the initial checkpoint."""

    staging_directory = Path(staging_directory)
    checkpoint_path = staging_directory / CHECKPOINT_FILENAME
    image_directory = staging_directory / IMAGE_FOLDER_NAME

    if checkpoint_path.exists():
        raise FileExistsError(
            f"A checkpoint already exists: {checkpoint_path}"
        )

    checkpoint = build_initial_checkpoint(
        source_directory=source_directory,
        event_name=event_name,
        classifications=classifications,
    )

    staging_directory.mkdir(parents=True, exist_ok=True)
    image_directory.mkdir(exist_ok=True)

    try:
        with checkpoint_path.open("x", encoding="utf-8") as checkpoint_file:
            json.dump(
                checkpoint,
                checkpoint_file,
                indent=4,
                ensure_ascii=False,
            )
            checkpoint_file.write("\n")
    except Exception:
        logger.exception("Failed to write checkpoint: %s", checkpoint_path)
        raise

    logger.info("Initial checkpoint created: %s", checkpoint_path)
    logger.info("Initial image directory created: %s", image_directory)

    return checkpoint_path
