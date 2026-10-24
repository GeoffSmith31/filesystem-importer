
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

"""Inspect the staging area when the application starts."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from filesystem_importer.app_logging import get_logger

logger = get_logger(__name__)

CLEAN = "clean"
PARTIAL_IMPORT = "partial_import"
ORPHANED_DATA = "orphaned_data"
INSPECTION_ERROR = "inspection_error"


@dataclass
class StartupResult:
    """Result of inspecting the staging area."""

    state: str
    importing_file: Path | None = None
    project_name: str | None = None
    modified_date: str | None = None
    details: str | None = None


def inspect_staging_directory(staging_directory: Path) -> StartupResult:
    """Classify the staging area without changing its contents."""

    try:
        if not staging_directory.exists():
            logger.info(
                "Staging directory does not exist: %s",
                staging_directory,
            )
            return StartupResult(state=CLEAN)

        if not staging_directory.is_dir():
            logger.error(
                "Staging path is not a directory: %s",
                staging_directory,
            )
            return StartupResult(
                state=INSPECTION_ERROR,
                details="The staging path is not a directory.",
            )

        # Force a directory read so permission errors are detected.
        list(staging_directory.iterdir())

        importing_file = staging_directory / "importing.json"

        if importing_file.is_file():
            importing_files = [importing_file]
        else:
            importing_files = []

        if importing_files:
            if len(importing_files) > 1:
                logger.error(
                    "Multiple importing.json files found in %s: %s",
                    staging_directory,
                    importing_files,
                )
                return StartupResult(
                    state=INSPECTION_ERROR,
                    details=(
                        "Multiple partial-import checkpoints were found. "
                        "No import has been selected."
                    ),
                )

            importing_file = importing_files[0]
            modified_date = datetime.fromtimestamp(
                importing_file.stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M")

            logger.info(
                "Partial import checkpoint found: %s",
                importing_file,
            )

            # Do not validate or parse the checkpoint at startup.
            # The project name can be read later when Resume is selected.
            return StartupResult(
                state=PARTIAL_IMPORT,
                importing_file=importing_file,
                modified_date=modified_date,
            )

        # No checkpoint exists. Any contents indicate orphaned data.
        contents = list(staging_directory.iterdir())

        if contents:
            logger.warning(
                "Staging data found without importing.json in %s. "
                "Entries: %s",
                staging_directory,
                [str(path) for path in contents],
            )
            return StartupResult(
                state=ORPHANED_DATA,
                details=(
                    "Files from an incomplete import were found, "
                    "but importing.json is missing."
                ),
            )

        logger.info("Staging directory is empty: %s", staging_directory)
        return StartupResult(state=CLEAN)

    except OSError as exc:
        logger.exception(
            "Could not inspect staging directory %s",
            staging_directory,
        )
        return StartupResult(
            state=INSPECTION_ERROR,
            details=str(exc),
        )
