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

"""Audit the staging photo directory against saved photo records."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from filesystem_importer.app_logging import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class StagingAuditResult:
    """Summary of a staging directory audit."""

    files_checked: int
    orphan_files_deleted: tuple[str, ...]


def audit_staging_directory(
    photos_directory: Path,
    photo_records: list[dict[str, Any]],
) -> StagingAuditResult:
    """Delete staged files that have no matching photo record.

    Records without a corresponding staged file are allowed. Records with an
    empty file value are also allowed; these represent failed EXIF tests.
    No files are deleted if the records are malformed or ambiguous.
    """

    photos_directory = Path(photos_directory)

    if not photos_directory.is_dir():
        logger.error(
            "Staging photos directory does not exist: %s",
            photos_directory,
        )
        raise ValueError(
            f"The staging photos directory does not exist: {photos_directory}"
        )

    if not isinstance(photo_records, list):
        logger.error("Checkpoint photos value is not a list.")
        raise ValueError("The checkpoint photos value must be a list.")

    recorded_filenames: set[str] = set()

    # Validate all records before touching the filesystem.
    for index, record in enumerate(photo_records):
        if not isinstance(record, dict):
            logger.error("Photo record %d is not a JSON object.", index)
            raise ValueError(
                f"Photo record {index} must be a JSON object."
            )

        filename = record.get("file")

        if not isinstance(filename, str):
            logger.error(
                "Photo record %d has a missing or invalid file value.",
                index,
            )
            raise ValueError(
                f"Photo record {index} has a missing or invalid file value."
            )

        if filename == "":
            continue

        if Path(filename).name != filename or filename in {".", ".."}:
            logger.error(
                "Photo record %d has an invalid staging filename: %r",
                index,
                filename,
            )
            raise ValueError(
                f"Photo record {index} has an invalid staging filename: "
                f"{filename!r}"
            )

        if filename in recorded_filenames:
            logger.error(
                "Multiple photo records refer to the same filename: %r",
                filename,
            )
            raise ValueError(
                f"Multiple photo records refer to the same filename: "
                f"{filename!r}"
            )

        recorded_filenames.add(filename)

    try:
        entries = sorted(
            photos_directory.iterdir(),
            key=lambda path: (path.name.casefold(), path.name),
        )
    except OSError as exc:
        logger.error(
            "Could not inspect staging photos directory %s: %s",
            photos_directory,
            exc,
        )
        raise ValueError(
            f"The staging photos directory could not be inspected: {exc}"
        ) from exc

    orphan_files: list[Path] = []

    # Do not delete unexpected directories or symlinks automatically.
    # Only ordinary files can be safely classified as orphaned photos.
    for entry in entries:
        if entry.is_symlink():
            logger.error(
                "Unexpected symbolic link in staging photos directory: %s",
                entry,
            )
            raise ValueError(
                f"Unexpected symbolic link in staging photos directory: "
                f"{entry.name}"
            )

        if entry.is_dir():
            logger.error(
                "Unexpected subdirectory in staging photos directory: %s",
                entry,
            )
            raise ValueError(
                f"Unexpected subdirectory in staging photos directory: "
                f"{entry.name}"
            )

        if not entry.is_file():
            logger.error(
                "Unexpected filesystem entry in staging photos directory: %s",
                entry,
            )
            raise ValueError(
                f"Unexpected filesystem entry in staging photos directory: "
                f"{entry.name}"
            )

        if entry.name not in recorded_filenames:
            orphan_files.append(entry)

    # All entries and records have been checked before deletion begins.
    deleted: list[str] = []

    for orphan in orphan_files:
        try:
            orphan.unlink()
        except OSError as exc:
            logger.error(
                "Could not delete orphaned staged file %s: %s",
                orphan,
                exc,
            )
            raise ValueError(
                f"Could not delete orphaned staged file {orphan.name}: {exc}"
            ) from exc

        deleted.append(orphan.name)
        logger.warning("Deleted orphaned staged file: %s", orphan)

    result = StagingAuditResult(
        files_checked=len(entries),
        orphan_files_deleted=tuple(deleted),
    )

    logger.info(
        "Staging audit complete: %d files checked, %d orphan files deleted.",
        result.files_checked,
        len(result.orphan_files_deleted),
    )

    return result
