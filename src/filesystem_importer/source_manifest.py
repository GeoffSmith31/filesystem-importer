
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

"""Create a reproducible fingerprint of a scanned source directory."""

import hashlib
import json
from typing import Any

from filesystem_importer.file_discovery import ScanResult


FINGERPRINT_ALGORITHM = "sha256"


def build_source_manifest(scan_result: ScanResult) -> dict[str, Any]:
    """Build a manifest of candidate files and relevant directories.

    File paths are relative to the source directory. Candidate files
    include their size and nanosecond modification timestamp.
    """

    source_directory = scan_result.source_directory

    if scan_result.scan_errors:
        raise ValueError(
            "Cannot fingerprint a source directory with scan errors."
        )

    candidate_files = []

    for file_path in scan_result.candidate_files:
        try:
            relative_path = file_path.relative_to(source_directory)
            stat = file_path.stat()

            if not file_path.is_file():
                raise ValueError(
                    f"Candidate path is no longer a file: {file_path}"
                )
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"Cannot inspect candidate file: {file_path}"
            ) from exc

        candidate_files.append({
            "path": relative_path.as_posix(),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        })

    candidate_files.sort(
        key=lambda entry: (
            entry["path"].casefold(),
            entry["path"],
        )
    )

    relevant_directories = sorted(
        (path.as_posix() for path in scan_result.relevant_directories),
        key=lambda path: (path.casefold(), path),
    )

    manifest = {
        "algorithm": FINGERPRINT_ALGORITHM,
        "candidate_count": len(candidate_files),
        "candidate_files": candidate_files,
        "relevant_directories": relevant_directories,
    }

    canonical_manifest = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    manifest["fingerprint"] = hashlib.sha256(
        canonical_manifest
    ).hexdigest()

    return manifest
