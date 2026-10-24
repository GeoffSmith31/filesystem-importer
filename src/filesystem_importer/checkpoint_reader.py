
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

"""Read and validate an existing importing.json checkpoint."""

import json
from pathlib import Path
from typing import Any

from filesystem_importer.app_logging import get_logger
from filesystem_importer.classification_dialog import (
    CATEGORIES,
    MAX_CLASSIFICATION_LEVELS,
)
from filesystem_importer.constants import (
    CHECKPOINT_FILENAME,
    IMPORTER_ID,
    SCHEMA_VERSION,
)
from filesystem_importer.file_discovery import (
    ScanResult,
    scan_source_directory,
)
from filesystem_importer.source_manifest import (
    FINGERPRINT_ALGORITHM,
    build_source_manifest,
)

logger = get_logger(__name__)


def read_checkpoint(
    checkpoint_path: Path,
) -> tuple[dict[str, Any], ScanResult]:
    """Read and validate a checkpoint and its source directory."""

    checkpoint_path = Path(checkpoint_path)

    try:
        with checkpoint_path.open("r", encoding="utf-8") as file:
            checkpoint = json.load(file)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"The checkpoint could not be read as valid JSON: {exc}"
        ) from exc

    if not isinstance(checkpoint, dict):
        raise ValueError("The checkpoint root must be a JSON object.")

    workspace = checkpoint.get("workspace")
    if not isinstance(workspace, dict):
        raise ValueError("The checkpoint has no valid workspace object.")

    importer = workspace.get("importer")
    if not isinstance(importer, str):
        raise ValueError("The checkpoint has no valid importer identity.")

    importer_parts = importer.split("/", 1)

    if importer_parts[0] != IMPORTER_ID:
        raise ValueError(
            "This checkpoint does not belong to the Filesystem Importer."
        )

    if len(importer_parts) != 2 or not importer_parts[1].strip():
        raise ValueError("The checkpoint has no valid importer version.")

    if workspace.get("schema") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported checkpoint schema. "
            f"Expected schema {SCHEMA_VERSION}."
        )

    source_id = workspace.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("The checkpoint has no valid source_id.")

    source_directory = Path(source_id)

    if not source_directory.is_dir():
        raise ValueError(
            f"The source directory does not exist or is not a directory:\n"
            f"{source_id}"
        )

    try:
        scan_result = scan_source_directory(source_directory)
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"The source directory could not be scanned: {exc}"
        ) from exc

    if scan_result.scan_errors:
        raise ValueError(
            "The source directory could not be fully inspected. "
            "Check directory permissions and try again."
        )

    extension = checkpoint.get("filesystem_importer")
    if not isinstance(extension, dict):
        raise ValueError(
            "The checkpoint has no valid Filesystem Importer data."
        )

    saved_manifest = extension.get("source_manifest")
    if not isinstance(saved_manifest, dict):
        raise ValueError(
            "The checkpoint has no source fingerprint. "
            "Resume is not possible; delete the partial import "
            "and start again."
        )

    if saved_manifest.get("algorithm") != FINGERPRINT_ALGORITHM:
        raise ValueError(
            "The checkpoint uses an unsupported source fingerprint algorithm."
        )

    current_manifest = build_source_manifest(scan_result)

    if (
        saved_manifest.get("fingerprint")
        != current_manifest["fingerprint"]
        or saved_manifest.get("candidate_count")
        != current_manifest["candidate_count"]
    ):
        raise ValueError(
            "The source directory has changed since this checkpoint "
            "was created. Resume is not possible; delete the partial "
            "import and start again."
        )

    if extension.get("classification_limit") != MAX_CLASSIFICATION_LEVELS:
        raise ValueError(
            "The checkpoint uses an unsupported classification limit."
        )

    classifications = extension.get("directory_classifications")
    if not isinstance(classifications, dict) or not classifications:
        raise ValueError(
            "The checkpoint has no directory classifications."
        )

    normalised: dict[str, str] = {}

    for level, category in classifications.items():
        try:
            level_number = int(level)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid classification level: {level!r}"
            ) from exc

        if not 1 <= level_number <= MAX_CLASSIFICATION_LEVELS:
            raise ValueError(
                f"Classification level is outside the supported range: "
                f"{level!r}"
            )

        if category not in CATEGORIES:
            raise ValueError(
                f"Invalid category for level {level_number}: {category!r}"
            )

        normalised[str(level_number)] = category

    classified_levels = {int(level) for level in normalised}
    deepest_level = max(
        (
            len(relative_path.parts) + 1
            for relative_path in scan_result.relevant_directories
        ),
        default=1,
    )

    expected_levels = set(range(1, deepest_level + 1))

    if classified_levels != expected_levels:
        raise ValueError(
            "The directory structure has changed since this checkpoint "
            "was created. "
            f"The checkpoint classifies {len(classified_levels)} levels, "
            f"but the source currently has {deepest_level} relevant levels. "
            "Resume is not possible; delete the partial import and start again."
        )

    event_name = workspace.get("event")
    if not isinstance(event_name, str) or not event_name.strip():
        raise ValueError("The checkpoint has no valid Event Name.")

    logger.info(
        "Checkpoint validated: %s; source depth %d.",
        checkpoint_path,
        deepest_level,
    )

    # Return the saved checkpoint unchanged and the fresh scan result.
    # Do not rewrite importing.json during validation.
    return checkpoint, scan_result
