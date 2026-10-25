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

    logger.info("Reading checkpoint: %s", checkpoint_path)

    try:
        with checkpoint_path.open("r", encoding="utf-8") as file:
            checkpoint = json.load(file)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        logger.exception("Failed to read checkpoint: %s", checkpoint_path)
        raise ValueError(
            f"The checkpoint could not be read as valid JSON: {exc}"
        ) from exc

    logger.debug("Checkpoint JSON loaded successfully: %s", checkpoint_path)

    if not isinstance(checkpoint, dict):
        logger.error("Checkpoint root is not a JSON object: %s", checkpoint_path)
        raise ValueError("The checkpoint root must be a JSON object.")

    workspace = checkpoint.get("workspace")
    if not isinstance(workspace, dict):
        logger.error("Checkpoint has no valid workspace object: %s", checkpoint_path)
        raise ValueError("The checkpoint has no valid workspace object.")

    importer = workspace.get("importer")
    if not isinstance(importer, str):
        logger.error("Checkpoint has no valid importer identity: %s", checkpoint_path)
        raise ValueError("The checkpoint has no valid importer identity.")

    importer_parts = importer.split("/", 1)

    if importer_parts[0] != IMPORTER_ID:
        logger.error(
            "Checkpoint belongs to a different importer: %s (importer=%r)",
            checkpoint_path,
            importer,
        )
        raise ValueError(
            "This checkpoint does not belong to the Filesystem Importer."
        )

    if len(importer_parts) != 2 or not importer_parts[1].strip():
        logger.error("Checkpoint has no valid importer version: %s", checkpoint_path)
        raise ValueError("The checkpoint has no valid importer version.")

    if workspace.get("schema") != SCHEMA_VERSION:
        logger.error(
            "Unsupported checkpoint schema: %s (found=%r, expected=%r)",
            checkpoint_path,
            workspace.get("schema"),
            SCHEMA_VERSION,
        )
        raise ValueError(
            f"Unsupported checkpoint schema. "
            f"Expected schema {SCHEMA_VERSION}."
        )

    source_id = workspace.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        logger.error("Checkpoint has no valid source_id: %s", checkpoint_path)
        raise ValueError("The checkpoint has no valid source_id.")

    source_directory = Path(source_id)

    if not source_directory.is_dir():
        logger.error(
            "Checkpoint source directory does not exist or is not a directory: %s",
            source_id,
        )
        raise ValueError(
            f"The source directory does not exist or is not a directory:\n"
            f"{source_id}"
        )

    logger.info("Scanning checkpoint source directory: %s", source_directory)

    try:
        scan_result = scan_source_directory(source_directory)
    except (OSError, ValueError) as exc:
        logger.exception(
            "Failed to scan checkpoint source directory: %s",
            source_directory,
        )
        raise ValueError(
            f"The source directory could not be scanned: {exc}"
        ) from exc

    if scan_result.scan_errors:
        logger.error(
            "Source directory scan reported %d error(s): %s",
            len(scan_result.scan_errors),
            source_directory,
        )
        raise ValueError(
            "The source directory could not be fully inspected. "
            "Check directory permissions and try again."
        )

    logger.debug(
        "Source scan completed: %s; candidates=%d, relevant directories=%d",
        source_directory,
        len(scan_result.candidate_files),
        len(scan_result.relevant_directories),
    )

    extension = checkpoint.get("filesystem_importer")
    if not isinstance(extension, dict):
        logger.error(
            "Checkpoint has no valid Filesystem Importer data: %s",
            checkpoint_path,
        )
        raise ValueError(
            "The checkpoint has no valid Filesystem Importer data."
        )

    saved_manifest = extension.get("source_manifest")
    if not isinstance(saved_manifest, dict):
        logger.error("Checkpoint has no source fingerprint: %s", checkpoint_path)
        raise ValueError(
            "The checkpoint has no source fingerprint. "
            "Resume is not possible; delete the partial import "
            "and start again."
        )

    if saved_manifest.get("algorithm") != FINGERPRINT_ALGORITHM:
        logger.error(
            "Unsupported source fingerprint algorithm: %s (found=%r, expected=%r)",
            checkpoint_path,
            saved_manifest.get("algorithm"),
            FINGERPRINT_ALGORITHM,
        )
        raise ValueError(
            "The checkpoint uses an unsupported source fingerprint algorithm."
        )

    logger.debug(
        "Building current source manifest using algorithm %s: %s",
        FINGERPRINT_ALGORITHM,
        source_directory,
    )
    current_manifest = build_source_manifest(scan_result)

    logger.debug(
        "Comparing source manifests: saved fingerprint=%r, current fingerprint=%r, "
        "saved candidate count=%r, current candidate count=%r",
        saved_manifest.get("fingerprint"),
        current_manifest["fingerprint"],
        saved_manifest.get("candidate_count"),
        current_manifest["candidate_count"],
    )

    if (
        saved_manifest.get("fingerprint")
        != current_manifest["fingerprint"]
        or saved_manifest.get("candidate_count")
        != current_manifest["candidate_count"]
    ):
        logger.error(
            "Source directory fingerprint or candidate count has changed: %s",
            source_directory,
        )
        raise ValueError(
            "The source directory has changed since this checkpoint "
            "was created. Resume is not possible; delete the partial "
            "import and start again."
        )

    if extension.get("classification_limit") != MAX_CLASSIFICATION_LEVELS:
        logger.error(
            "Unsupported classification limit: %s (found=%r, expected=%r)",
            checkpoint_path,
            extension.get("classification_limit"),
            MAX_CLASSIFICATION_LEVELS,
        )
        raise ValueError(
            "The checkpoint uses an unsupported classification limit."
        )

    classifications = extension.get("directory_classifications")
    if not isinstance(classifications, dict) or not classifications:
        logger.error(
            "Checkpoint has no directory classifications: %s",
            checkpoint_path,
        )
        raise ValueError(
            "The checkpoint has no directory classifications."
        )

    logger.debug(
        "Validating %d saved directory classification(s): %s",
        len(classifications),
        checkpoint_path,
    )

    normalised: dict[str, str] = {}

    for level, category in classifications.items():
        try:
            level_number = int(level)
        except (TypeError, ValueError) as exc:
            logger.exception(
                "Invalid classification level in checkpoint %s: %r",
                checkpoint_path,
                level,
            )
            raise ValueError(
                f"Invalid classification level: {level!r}"
            ) from exc

        if not 1 <= level_number <= MAX_CLASSIFICATION_LEVELS:
            logger.error(
                "Classification level outside supported range in %s: %r",
                checkpoint_path,
                level,
            )
            raise ValueError(
                f"Classification level is outside the supported range: "
                f"{level!r}"
            )

        if category not in CATEGORIES:
            logger.error(
                "Invalid classification category in %s: level=%r, category=%r",
                checkpoint_path,
                level_number,
                category,
            )
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

    logger.debug(
        "Comparing classified directory levels: saved=%s, expected=%s",
        sorted(classified_levels),
        sorted(expected_levels),
    )

    if classified_levels != expected_levels:
        logger.error(
            "Directory classification depth has changed: %s "
            "(classified levels=%d, current source depth=%d)",
            checkpoint_path,
            len(classified_levels),
            deepest_level,
        )
        raise ValueError(
            "The directory structure has changed since this checkpoint "
            "was created. "
            f"The checkpoint classifies {len(classified_levels)} levels, "
            f"but the source currently has {deepest_level} relevant levels. "
            "Resume is not possible; delete the partial import and start again."
        )

    event_name = workspace.get("event")
    if not isinstance(event_name, str) or not event_name.strip():
        logger.error("Checkpoint has no valid Event Name: %s", checkpoint_path)
        raise ValueError("The checkpoint has no valid Event Name.")

    logger.info(
        "Checkpoint validated: %s; source depth %d.",
        checkpoint_path,
        deepest_level,
    )

    # Return the saved checkpoint unchanged and the fresh scan result.
    # Do not rewrite importing.json during validation.
    return checkpoint, scan_result
