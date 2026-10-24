
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

"""Discover potentially suitable image files in a source directory."""

import os
from dataclasses import dataclass
from pathlib import Path

from filesystem_importer.app_logging import get_logger

logger = get_logger(__name__)


# Candidate formats only. Actual metadata-writing support is tested
# later, during import.
CANDIDATE_EXTENSIONS = frozenset({
    # Standard and modern image formats
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
    ".png",
    ".webp",
    ".avif",

    # Older image formats
    ".bmp",
    ".gif",

    # Camera RAW formats
    ".cr2",
    ".cr3",
    ".nef",
    ".nrw",
    ".arw",
    ".srf",
    ".sr2",
    ".dng",
    ".orf",
    ".rw2",
    ".raf",
    ".pef",
    ".srw",
})


@dataclass(frozen=True)
class ScanResult:
    """Results from a read-only source-directory scan."""

    source_directory: Path
    candidate_files: tuple[Path, ...]
    directories_with_candidates: tuple[Path, ...]
    relevant_directories: tuple[Path, ...]
    scan_errors: tuple[str, ...]


def scan_source_directory(source_directory: Path) -> ScanResult:
    """Recursively find candidate image files without modifying them.

    Paths in candidate_files are absolute. Directory paths are relative
    to the selected source directory.

    relevant_directories includes directories containing candidates
    and their parent directories below the selected source root.
    Empty branches are excluded.

    Scan errors are recorded so that an incomplete scan is not
    mistaken for a complete one.
    """

    source_directory = Path(source_directory).expanduser().resolve()

    if not source_directory.exists():
        raise ValueError(
            f"The source directory does not exist: {source_directory}"
        )

    if not source_directory.is_dir():
        raise ValueError(
            f"The selected source path is not a directory: "
            f"{source_directory}"
        )

    candidate_files = []
    directories_with_candidates = set()
    relevant_directories = set()
    scan_errors = []

    def record_error(error):
        message = f"{error.filename or source_directory}: {error}"
        scan_errors.append(message)
        logger.warning("Directory scan could not access a path: %s", message)

    logger.info("Starting source scan: %s", source_directory)

    for current_root, _, filenames in os.walk(
        source_directory,
        topdown=True,
        followlinks=False,
        onerror=record_error,
    ):
        current_directory = Path(current_root)

        for filename in filenames:
            file_path = current_directory / filename

            if file_path.suffix.lower() not in CANDIDATE_EXTENSIONS:
                continue

            candidate_files.append(file_path)

            relative_directory = current_directory.relative_to(
                source_directory
            )

            if relative_directory != Path("."):
                directories_with_candidates.add(relative_directory)

            # Retain the directory and its ancestors within the source
            # tree so that the hierarchy can be classified later.
            ancestor = relative_directory
            while ancestor != Path("."):
                relevant_directories.add(ancestor)
                ancestor = ancestor.parent

    candidate_files.sort(
        key=lambda path: (
            str(path).casefold(),
            str(path),
        )
    )
    sorted_directories = lambda paths: tuple(
        sorted(
            paths,
            key=lambda path: (
                path.as_posix().casefold(),
                path.as_posix(),
            ),
        )
    )

    result = ScanResult(
        source_directory=source_directory,
        candidate_files=tuple(candidate_files),
        directories_with_candidates=sorted_directories(
            directories_with_candidates
        ),
        relevant_directories=sorted_directories(relevant_directories),
        scan_errors=tuple(scan_errors),
    )

    logger.info(
        "Source scan finished: %d candidate files, "
        "%d directories containing candidates, "
        "%d relevant directories, %d scan errors.",
        len(result.candidate_files),
        len(result.directories_with_candidates),
        len(result.relevant_directories),
        len(result.scan_errors),
    )

    return result
