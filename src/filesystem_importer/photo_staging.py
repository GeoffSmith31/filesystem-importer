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

"""Copy candidate photos into staging and test EXIF capability."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from filesystem_importer.app_logging import get_logger
from filesystem_importer.exif_capability import check_usercomment_capability

logger = get_logger(__name__)


class StagingFatalError(RuntimeError):
    """A staging error that requires import processing to stop."""


@dataclass(frozen=True)
class PhotoStagingResult:
    """Outcome of staging and testing one candidate photo."""

    success: bool
    staged_filename: str = ""
    reason: str = ""
    original_comment: bytes | None = None


def _copy_without_overwriting(source: Path, destination: Path) -> None:
    """Copy a file without overwriting an existing destination."""
    import os
    import shutil

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(destination, flags, 0o666)

    try:
        with os.fdopen(descriptor, "wb") as destination_file:
            with source.open("rb") as source_file:
                shutil.copyfileobj(source_file, destination_file)
    except Exception:
        try:
            destination.unlink(missing_ok=True)
        except OSError as exc:
            logger.exception(
                "Could not remove incomplete staged copy: %s",
                destination,
            )
            raise StagingFatalError(
                f"Could not remove incomplete staged copy: {destination}"
            ) from exc
        raise

def _choose_staged_path(source_path: Path, photos_directory: Path) -> Path:
    """Choose the original filename, adding a number if it is already used."""
    candidate = photos_directory / source_path.name
    if not candidate.exists() and not candidate.is_symlink():
        return candidate

    stem = source_path.stem
    suffix = source_path.suffix
    number = 2

    while True:
        candidate = photos_directory / f"{stem}_{number}{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        number += 1



def stage_and_test_photo(source_path: Path, photos_directory: Path) -> PhotoStagingResult:
    """Copy one candidate and test EXIF capability on the staged copy.

    The original filename is preserved where possible. If it is already
    in use, a numbered suffix is added. A failed capability test results
    in deletion of the staged copy. Failure to delete it is fatal.
    """
    source_path = Path(source_path)
    photos_directory = Path(photos_directory)

    if not source_path.is_file():
        raise ValueError(f"Source photo does not exist: {source_path}")
    if not photos_directory.is_dir():
        raise ValueError(f"Staging photos directory does not exist: {photos_directory}")

    while True:
        staged_path = _choose_staged_path(source_path, photos_directory)
        try:
            _copy_without_overwriting(source_path, staged_path)
            break
        except FileExistsError:
            # Another file appeared after we chose the name. Try again.
            logger.debug("Staging filename collision; retrying: %s", staged_path)
        except OSError:
            logger.exception(
                "Failed to copy photo into staging: %s -> %s",
                source_path,
                staged_path,
            )
            raise

    try:
        capability = check_usercomment_capability(staged_path)
    except Exception as exc:
        capability = None
        reason = f"EXIF capability test raised an error: {exc}"
    else:
        reason = capability.reason if not capability.supported else ""

    if capability is not None and capability.supported:
        logger.info("Photo staged successfully: %s", staged_path)
        return PhotoStagingResult(
            success=True,
            staged_filename=staged_path.name,
            original_comment=capability.original_comment,
        )

    try:
        staged_path.unlink()
    except OSError as exc:
        logger.exception(
            "Failed EXIF test and staged file could not be deleted: %s",
            staged_path,
        )
        raise StagingFatalError(
            "The EXIF capability test failed and the staged copy "
            f"could not be deleted: {staged_path}: {exc}"
        ) from exc

    logger.warning(
        "Photo not staged because EXIF capability testing failed: %s (%s)",
        source_path,
        reason,
    )
    return PhotoStagingResult(success=False, reason=reason)
