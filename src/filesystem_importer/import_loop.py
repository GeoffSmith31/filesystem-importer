
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

"""Control the filesystem photo-import loop."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from filesystem_importer.photo_staging import (
    PhotoStagingResult,
    StagingFatalError,
    stage_and_test_photo,
)
from filesystem_importer.app_logging import get_logger
from filesystem_importer.checkpoint_writer import (
    write_recovery_checkpoint,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class ImportProgress:
    """Progress counts for one import run."""

    total: int
    processed: int
    successful: int
    failed: int
    remaining: int


def initialise_progress(checkpoint: dict[str, Any]) -> ImportProgress:
    """Calculate progress from the saved checkpoint records."""
    logger.debug("Calculating import progress from checkpoint.")

    try:
        total = checkpoint["filesystem_importer"]["source_manifest"][
            "candidate_count"
        ]
        photos = checkpoint["photos"]
    except (KeyError, TypeError) as exc:
        logger.error("Checkpoint is missing required progress data: %s", exc)
        raise ValueError("Checkpoint is missing required progress data.") from exc

    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        logger.error("Invalid checkpoint candidate_count: %r", total)
        raise ValueError("Checkpoint candidate_count must be a non-negative integer.")

    if not isinstance(photos, list):
        logger.error("Checkpoint photos value is not a list.")
        raise ValueError("Checkpoint photos must be a list.")

    processed = len(photos)

    if processed > total:
        logger.error(
            "Checkpoint has %d photo records but only %d source candidates.",
            processed,
            total,
        )
        raise ValueError("Checkpoint has more photo records than source candidates.")

    successful = 0
    failed = 0

    for index, photo in enumerate(photos):
        if not isinstance(photo, Mapping):
            logger.error("Photo record %d is not an object.", index)
            raise ValueError(f"Photo record {index} must be an object.")

        downloaded = photo.get("downloaded")

        if not isinstance(downloaded, bool):
            logger.error(
                "Photo record %d has a non-Boolean downloaded value.",
                index,
            )
            raise ValueError(
                f"Photo record {index} must have a Boolean downloaded value."
            )

        if downloaded:
            successful += 1
        else:
            failed += 1

    progress = ImportProgress(
        total=total,
        processed=processed,
        successful=successful,
        failed=failed,
        remaining=total - processed,
    )

    logger.debug(
        "Import progress: total=%d, processed=%d, successful=%d, "
        "failed=%d, remaining=%d.",
        progress.total,
        progress.processed,
        progress.successful,
        progress.failed,
        progress.remaining,
    )

    return progress


def stage_candidate(
    source_path: Path,
    photos_directory: Path,
) -> PhotoStagingResult:
    """Stage a candidate and test EXIF capability.

    Return the complete staging result, including the staged filename
    on success or the failure reason on failure.

    Fatal staging errors propagate to stop processing.
    """
    logger.info("Staging candidate: %s", source_path)

    result = stage_and_test_photo(source_path, photos_directory)

    if not result.success:
        logger.info(
            "Candidate failed the staging/EXIF test: %s (%s)",
            source_path,
            result.reason,
        )
    else:
        logger.info(
            "Candidate passed the staging/EXIF test: %s -> %s",
            source_path,
            result.staged_filename,
        )

    return result


def build_failed_photo_record(
    source_path: Path,
    event_name: str,
) -> dict[str, Any]:
    """Build a photo record for a candidate that failed staging."""
    logger.debug("Building failed photo record for: %s", source_path)

    return build_photo_record(
        source_path=source_path,
        downloaded=False,
        file="",
        event=event_name,
    )


def process_candidate(
    source_path: Path,
    photos_directory: Path,
    event_name: str,
) -> dict[str, Any] | None:
    """Process one candidate."""

    logger.debug("Processing candidate: %s", source_path)

    result = stage_candidate(source_path, photos_directory)

    if not result.success:
        logger.info(
            "Building failure record for candidate: %s",
            source_path,
        )
        return build_failed_photo_record(source_path, event_name)

    logger.info(
        "Candidate staged successfully; metadata resolution is pending: %s",
        source_path,
    )
    return None


def update_progress_display(progress: ImportProgress) -> None:
    """Update the GUI with the latest progress."""
    raise NotImplementedError


def save_recovery_checkpoint(
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
) -> None:
    """Save the current checkpoint for recovery."""
    logger.info("Saving recovery checkpoint: %s", checkpoint_path)

    write_recovery_checkpoint(
        checkpoint_path=checkpoint_path,
        checkpoint=checkpoint,
    )

    logger.info("Recovery checkpoint saved: %s", checkpoint_path)


def run_import_loop(
    checkpoint: dict[str, Any],
    candidate_paths: list[Path],
    photos_directory: Path,
    checkpoint_path: Path,
) -> ImportProgress:
    """Process failed candidates until a successful candidate needs metadata.

    Failed candidates receive complete records and are appended to the
    checkpoint. Successful candidates stop processing until metadata
    resolution has been implemented.
    """
    logger.info(
        "Starting import loop: %d candidate paths; checkpoint %s.",
        len(candidate_paths),
        checkpoint_path,
    )

    progress = initialise_progress(checkpoint)
    update_progress_display(progress)

    if len(candidate_paths) != progress.total:
        logger.error(
            "Candidate path count (%d) does not match checkpoint manifest "
            "count (%d).",
            len(candidate_paths),
            progress.total,
        )
        raise ValueError(
            "Candidate path count does not match the checkpoint manifest."
        )

    event_name = checkpoint["workspace"]["event"]

    logger.info(
        "Import loop resuming at candidate %d of %d.",
        progress.processed + 1 if progress.remaining else progress.total,
        progress.total,
    )

    for source_path in candidate_paths[progress.processed:]:
        logger.info(
            "Processing import candidate %d of %d: %s",
            progress.processed + 1,
            progress.total,
            source_path,
        )

        record = process_candidate(
            source_path=source_path,
            photos_directory=photos_directory,
            event_name=event_name,
        )

        if record is None:
            logger.warning(
                "Candidate staged successfully but cannot yet be recorded "
                "because metadata resolution is not implemented: %s",
                source_path,
            )
            raise NotImplementedError(
                "Metadata resolution is not implemented; "
                "the successful candidate has been staged but not recorded."
            )

        checkpoint["photos"].append(record)
        progress = initialise_progress(checkpoint)
        update_progress_display(progress)

        logger.info(
            "Failed candidate recorded: %s (%d of %d processed)",
            source_path,
            progress.processed,
            progress.total,
        )

        save_recovery_checkpoint(
            checkpoint=checkpoint,
            checkpoint_path=checkpoint_path,
        )

    logger.info(
        "Import loop finished: %d processed, %d successful, %d failed, "
        "%d remaining.",
        progress.processed,
        progress.successful,
        progress.failed,
        progress.remaining,
    )

    return progress


def build_photo_record(
    source_path: Path,
    *,
    downloaded: bool,
    file: str,
    event: str,
    moment_id: str = "",
    lat: float | None = None,
    lng: float | None = None,
    retry_count: int = 0,
    status: str = "pending",
    exif_written: bool = False,
    location_key: str | None = None,
    geo_location: str | None = None,
    year: str = "",
    location: str = "",
    info: str = "",
) -> dict[str, Any]:
    """Build a photo record using the standard Project JSON structure."""
    last_updated = (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

    record = {
        "guid": str(Path(source_path).resolve()),
        "moment_id": moment_id,
        "lat": lat,
        "lng": lng,
        "file": file,
        "downloaded": downloaded,
        "retry_count": retry_count,
        "status": status,
        "exif_written": exif_written,
        "last_updated": last_updated,
        "location_key": location_key,
        "geo_location": geo_location,
        "event": event,
        "year": year,
        "location": location,
        "info": info,
    }

    logger.debug(
        "Photo record built: source=%s, downloaded=%s, status=%s, "
        "exif_written=%s.",
        record["guid"],
        record["downloaded"],
        record["status"],
        record["exif_written"],
    )

    return record

