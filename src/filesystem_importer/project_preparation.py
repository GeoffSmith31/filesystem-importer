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

"""Prepare a Photo Manager project JSON from an import checkpoint."""

import json
from pathlib import Path
from typing import Any

from filesystem_importer.app_logging import get_logger
from filesystem_importer.constants import (
    CHECKPOINT_FILENAME,
    PREPARED_FILENAME,
)

logger = get_logger(__name__)


def build_prepared_project(
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    """Build cleaned Photo Manager project data from a checkpoint."""

    if not isinstance(checkpoint, dict):
        raise ValueError("The checkpoint root must be a JSON object.")

    workspace = checkpoint.get("workspace")
    metadata_policies = checkpoint.get("metadata_policies")
    photos = checkpoint.get("photos")
    importer_data = checkpoint.get("filesystem_importer")

    if not isinstance(workspace, dict):
        raise ValueError("The checkpoint has no valid workspace object.")

    if not isinstance(metadata_policies, dict):
        raise ValueError("The checkpoint has no valid metadata_policies object.")

    if not isinstance(photos, list):
        raise ValueError("The checkpoint photos value must be a list.")

    if not isinstance(importer_data, dict):
        raise ValueError("The checkpoint has no valid filesystem_importer data.")

    manifest = importer_data.get("source_manifest")

    if not isinstance(manifest, dict):
        raise ValueError("The checkpoint has no valid source manifest.")

    candidate_count = manifest.get("candidate_count")

    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or candidate_count < 0
    ):
        raise ValueError("The checkpoint has an invalid candidate count.")

    # Every source candidate must have a corresponding photo record.
    if len(photos) != candidate_count:
        logger.error(
            "Cannot prepare project: %d of %d candidate records have "
            "been processed.",
            len(photos),
            candidate_count,
        )
        raise ValueError(
            "The import is incomplete. Not all source candidates "
            "have been processed."
        )

    successful_photos = []
    failed_count = 0

    for index, photo in enumerate(photos):

        if not isinstance(photo, dict):
            raise ValueError(
                f"Photo record {index} must be a JSON object."
            )

        downloaded = photo.get("downloaded")

        if not isinstance(downloaded, bool):
            raise ValueError(
                f"Photo record {index} has an invalid downloaded value."
            )

        if downloaded:
            successful_photos.append(photo)
        else:
            failed_count += 1

    if not successful_photos:
        logger.error(
            "Cannot prepare project: no photos were successfully staged."
        )
        raise ValueError(
            "No photos were successfully staged. "
            "There is nothing to publish."
        )

    # Prepare a copy of the workspace data and mark both import phases
    # as complete. The original recovery checkpoint remains unchanged.
    prepared_workspace = dict(workspace)
    prepared_workspace["registration_status"] = "COMPLETE"
    prepared_workspace["download_status"] = "COMPLETE"

    # Construct the Photo Manager project structure.
    # The Filesystem Importer extension is deliberately excluded.
    prepared_project = {
        "workspace": prepared_workspace,
        "metadata_policies": metadata_policies,
        "photos": successful_photos,
    }

    logger.info(
        "Project data prepared: candidates=%d, successful=%d, failed=%d.",
        candidate_count,
        len(successful_photos),
        failed_count,
    )

    return prepared_project


def prepare_project_json(
    checkpoint_path: Path,
) -> Path:
    """Create an atomic, cleaned copy of importing.json."""

    checkpoint_path = Path(checkpoint_path)

    if checkpoint_path.name != CHECKPOINT_FILENAME:
        raise ValueError(
            f"The input file must be named {CHECKPOINT_FILENAME}."
        )

    logger.info("Preparing Photo Manager project JSON: %s", checkpoint_path)

    try:
        with checkpoint_path.open("r", encoding="utf-8") as file:
            checkpoint = json.load(file)

    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        logger.exception(
            "Could not read import checkpoint: %s",
            checkpoint_path,
        )
        raise ValueError(
            f"The import checkpoint could not be read: {exc}"
        ) from exc

    # Build and validate everything before writing the output file.
    prepared_project = build_prepared_project(checkpoint)

    prepared_path = checkpoint_path.with_name(PREPARED_FILENAME)
    temporary_path = prepared_path.with_name(
        f".{prepared_path.name}.tmp"
    )

    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(
                prepared_project,
                file,
                indent=4,
                ensure_ascii=False,
            )
            file.write("\n")
            file.flush()

        temporary_path.replace(prepared_path)

    except Exception:
        logger.exception(
            "Could not write prepared project: %s",
            prepared_path,
        )
        raise

    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            logger.exception(
                "Could not remove temporary prepared file: %s",
                temporary_path,
            )

    logger.info("Prepared project JSON created: %s", prepared_path)

    return prepared_path
