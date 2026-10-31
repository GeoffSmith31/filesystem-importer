
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

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
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
from filesystem_importer.metadata_context import (
    PhotoMetadataContext,
    gather_photo_metadata_context,
    _find_directory_ancestor,
    _find_directory_ancestors,
)
from filesystem_importer.geocoding import (
    check_location,
    reverse_geocode,
)
from filesystem_importer.metadata_extraction import (
    extract_usercomment_metadata,
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
    directory_classifications: Mapping[str, str] | None = None,
    source_directory: Path | None = None,
    existing_photo_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Stage one candidate and populate its proposed metadata."""

    logger.info("Processing candidate: %s", source_path)

    # Create the shared photo record once.
    photo_record = build_photo_record(
        source_path=source_path,
        downloaded=False,
        file="",
        event="",
    )

    result = stage_candidate(source_path, photos_directory)

    if not result.success:
        logger.info(
            "Candidate staging failed; returning failure record: "
            "source=%s, reason=%s",
            source_path,
            result.reason,
        )
        return photo_record

    photo_record["downloaded"] = True
    photo_record["file"] = result.staged_filename

    if source_directory is None:
        raise ValueError(
            "Source directory is required for metadata processing."
        )

    # Step 1: Gather context and extract UserComment metadata.
    context = gather_photo_metadata_context(
        source_path=source_path,
        staged_path=photos_directory / result.staged_filename,
        source_directory=source_directory,
        directory_classifications=dict(directory_classifications or {}),
        workspace_event=event_name,
    )

    extract_usercomment_metadata(
        context.user_comment,
        photo_record,
    )

    logger.info(
        "UserComment processing complete: event=%s, year=%s, "
        "location=%s, info=%s",
        bool(photo_record["event"]),
        bool(photo_record["year"]),
        bool(photo_record["location"]),
        bool(photo_record["info"]),
    )

    # Step 2: Populate GPS and propagation fields.
    # GPS coordinates take precedence when calculating location_key.
    # geo_location is deliberately not populated at this stage.
    populate_gps_fields(photo_record, context)

    # Every photo belongs to its containing directory.
    photo_record["moment_id"] = source_path.parent.name

    # Step 3: Resolve any metadata fields not supplied by UserComment.
    if not photo_record["event"]:
        resolve_event(photo_record, context)

    if not photo_record["year"]:
        resolve_year(photo_record, context)

    if not photo_record["location"]:
        resolve_location(
            photo_record,
            context,
            existing_photo_records=existing_photo_records,
        )

    if not photo_record["info"]:
        resolve_info(photo_record, context)

    logger.info(
        "Photo metadata processing complete: guid=%s, event=%s, "
        "year=%s, location=%s, info_present=%s, lat=%s, lng=%s, "
        "location_key=%s, moment_id=%s",
        photo_record["guid"],
        photo_record["event"],
        photo_record["year"],
        photo_record["location"],
        bool(photo_record["info"]),
        photo_record["lat"],
        photo_record["lng"],
        photo_record["location_key"],
        photo_record["moment_id"],
    )

    return photo_record

def _gps_dms_to_decimal(
    coordinate: Any,
    reference: str | None,
    maximum: float,
    coordinate_name: str,
) -> float | None:
    """Convert an EXIF GPS DMS coordinate to decimal degrees."""

    import math

    def rational_to_float(value: Any) -> float | None:
        if (
            isinstance(value, (tuple, list))
            and len(value) == 2
        ):
            numerator, denominator = value

            if (
                isinstance(numerator, bool)
                or isinstance(denominator, bool)
                or not isinstance(numerator, (int, float))
                or not isinstance(denominator, (int, float))
                or denominator == 0
            ):
                return None

            result = numerator / denominator

        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            result = float(value)

        else:
            return None

        return result if math.isfinite(result) else None

    # GPS data is optional. Missing coordinates and references
    # are normal for photos that have no GPS metadata.
    if coordinate is None and reference is None:
        return None

    if reference not in ("N", "S", "E", "W"):
        logger.warning(
            "Invalid GPS %s reference: %r.",
            coordinate_name,
            reference,
        )
        return None

    if not isinstance(coordinate, (tuple, list)) or len(coordinate) != 3:
        logger.warning(
            "Invalid GPS %s coordinate: %r.",
            coordinate_name,
            coordinate,
        )
        return None

    degrees, minutes, seconds = (
        rational_to_float(value) for value in coordinate
    )

    if degrees is None or minutes is None or seconds is None:
        logger.warning(
            "Invalid GPS %s DMS values: %r.",
            coordinate_name,
            coordinate,
        )
        return None

    if (
        degrees < 0
        or degrees > maximum
        or not 0 <= minutes < 60
        or not 0 <= seconds < 60
        or (degrees == maximum and (minutes != 0 or seconds != 0))
    ):
        logger.warning(
            "GPS %s coordinate is outside its valid range: %r.",
            coordinate_name,
            coordinate,
        )
        return None

    decimal = degrees + minutes / 60 + seconds / 3600

    if reference in ("S", "W"):
        decimal = -decimal

    return decimal


def populate_gps_fields(
    photo_record: dict[str, Any],
    context: PhotoMetadataContext,
) -> None:
    """Populate latitude, longitude and GPS-derived location_key.

    geo_location is populated later by reverse geocoding during
    Location resolution.
    """
    latitude = _gps_dms_to_decimal(
        context.gps_latitude,
        context.gps_latitude_ref,
        90,
        "latitude",
    )

    longitude = _gps_dms_to_decimal(
        context.gps_longitude,
        context.gps_longitude_ref,
        180,
        "longitude",
    )

    if latitude is None or longitude is None:
        logger.debug(
            "No complete valid GPS position: source=%s.",
            context.source_path,
        )
        return

    photo_record["lat"] = latitude
    photo_record["lng"] = longitude
    photo_record["location_key"] = f"{latitude:.2f},{longitude:.2f}"

    logger.info(
        "GPS coordinates populated: source=%s, "
        "latitude=%s, longitude=%s, location_key=%s.",
        context.source_path,
        latitude,
        longitude,
        photo_record["location_key"],
    )


def resolve_event(
    photo_record: dict[str, Any],
    context: PhotoMetadataContext,
) -> None:
    """Resolve Event from directory inheritance or workspace context."""

    inheritance = _find_directory_ancestor(
        context.relative_directory,
        context.source_directory,
        context.directory_classifications,
        "Event",
    )

    if inheritance is not None:
        event, folder_name = inheritance
        photo_record["event"] = event

        logger.info(
            "Event inherited from directory: source=%s, "
            "folder=%s, event=%s.",
            context.source_path,
            folder_name,
            event,
        )
        return

    if context.workspace_event:
        photo_record["event"] = context.workspace_event
        logger.info(
            "Event inherited from workspace: source=%s, event=%s.",
            context.source_path,
            photo_record["event"],
        )
        return

    logger.debug("No Event value available: source=%s.", context.source_path)


def resolve_year(
    photo_record: dict[str, Any],
    context: PhotoMetadataContext,
) -> None:
    """Propose Year from EXIF date, filesystem timestamp or inheritance."""

    # Preserve a Year already extracted from UserComment.
    if photo_record.get("year"):
        return

    # Priority 1: EXIF DateTimeOriginal.
    date_text = context.date_time_original

    if date_text:
        # Require the exact standard EXIF date/time format.
        if re.fullmatch(r"[0-9]{4}:[0-9]{2}:[0-9]{2} "
                        r"[0-9]{2}:[0-9]{2}:[0-9]{2}", date_text):
            try:
                original_date = datetime.strptime(
                    date_text,
                    "%Y:%m:%d %H:%M:%S",
                )
            except ValueError:
                logger.debug(
                    "Invalid EXIF DateTimeOriginal: source=%s, value=%r.",
                    context.source_path,
                    date_text,
                )
            else:
                photo_record["year"] = str(original_date.year)
                logger.info(
                    "Year resolved from EXIF DateTimeOriginal: "
                    "source=%s, year=%s.",
                    context.source_path,
                    photo_record["year"],
                )
                return
        else:
            logger.debug(
                "EXIF DateTimeOriginal has unsupported format: "
                "source=%s, value=%r.",
                context.source_path,
                date_text,
            )

    # Priority 2: Filesystem timestamp.
    if context.filesystem_timestamp is not None:
        photo_record["year"] = str(
            context.filesystem_timestamp.year
        )
        logger.info(
            "Year resolved from filesystem timestamp: "
            "source=%s, year=%s.",
            context.source_path,
            photo_record["year"],
        )
        return

    # Priority 3: Inherited Year directory.
    inheritance = _find_directory_ancestor(
        context.relative_directory,
        context.source_directory,
        context.directory_classifications,
        "Year",
    )

    if inheritance is not None:
        year, folder_name = inheritance
        photo_record["year"] = year

        logger.info(
            "Year inherited from directory: source=%s, "
            "folder=%s, year=%s.",
            context.source_path,
            folder_name,
            year,
        )
        return

    # No usable source was available.
    logger.debug(
        "No Year value available: source=%s.",
        context.source_path,
    )


def resolve_location(
    photo_record: dict[str, Any],
    context: PhotoMetadataContext,
    existing_photo_records: list[dict[str, Any]] | None = None,
) -> None:
    """Resolve Location from GPS reverse geocoding or directory inheritance."""

    # GPS coordinates take priority over directory inheritance.
    if photo_record["lat"] is not None and photo_record["lng"] is not None:
        location_key = photo_record["location_key"]

        # Reuse a previously resolved location for the same GPS key.
        for existing_record in existing_photo_records or []:
            if (
                existing_record.get("location_key") == location_key
                and existing_record.get("geo_location")
            ):
                resolved_location = existing_record["geo_location"]
                photo_record["location"] = resolved_location
                photo_record["geo_location"] = resolved_location

                logger.info(
                    "Location reused from previous photo: source=%s, "
                    "location_key=%s, location=%s.",
                    context.source_path,
                    location_key,
                    resolved_location,
                )
                return

        # No previous result: ask Nominatim to resolve the coordinates.
        resolved_location = reverse_geocode(
            photo_record["lat"],
            photo_record["lng"],
        )

        if resolved_location:
            photo_record["location"] = resolved_location
            photo_record["geo_location"] = resolved_location

            logger.info(
                "Location resolved from GPS: source=%s, "
                "location=%s, location_key=%s.",
                context.source_path,
                resolved_location,
                location_key,
            )
            return

        logger.info(
            "GPS reverse geocoding did not resolve a location; "
            "trying directory inheritance: source=%s.",
            context.source_path,
        )

    # No GPS, or GPS reverse geocoding did not produce a result.
    # Try Location-classified folders, nearest first.
    ancestors = _find_directory_ancestors(
        context.relative_directory,
        context.source_directory,
        context.directory_classifications,
        "Location",
    )

    for folder_name, _ in ancestors:
        result = check_location(folder_name)

        if result is None:
            logger.warning(
                "Location validation unavailable; stopping directory "
                "search: source=%s, folder=%s.",
                context.source_path,
                folder_name,
            )
            return

        if result:
            photo_record["location"] = folder_name

            # Only set location_key from the folder when GPS did not
            # already provide a coordinate-based key.
            if photo_record["location_key"] is None:
                photo_record["location_key"] = folder_name

            logger.info(
                "Location inherited from validated directory: "
                "source=%s, folder=%s, location_key=%s.",
                context.source_path,
                folder_name,
                photo_record["location_key"],
            )
            return

        logger.info(
            "Location folder was not recognised; trying next ancestor: "
            "source=%s, folder=%s.",
            context.source_path,
            folder_name,
        )

    logger.debug(
        "No usable Location value found: source=%s.",
        context.source_path,
    )


def resolve_info(
    photo_record: dict[str, Any],
    context: PhotoMetadataContext,
) -> None:
    """Propose Info from directory inheritance or filename."""

    inheritance = _find_directory_ancestor(
        context.relative_directory,
        context.source_directory,
        context.directory_classifications,
        "Info",
    )

    if inheritance is not None:
        info, folder_name = inheritance
        photo_record["info"] = info

        logger.info(
            "Info inherited from directory: source=%s, "
            "folder=%s, info=%s.",
            context.source_path,
            folder_name,
            info,
        )
        return

    # Priority 2: Filename.
    filename = context.source_path.stem

    # Normalise separators and whitespace.
    proposed_info = re.sub(r"[_-]+", " ", filename)
    proposed_info = " ".join(proposed_info.split())

    # Reject empty or numeric-only names.
    if not proposed_info or re.fullmatch(r"[0-9 ]+", proposed_info):
        logger.debug(
            "Filename rejected as Info (numeric or empty): source=%s.",
            context.source_path,
        )
        return

    # Reject recognisable camera-generated filenames.
    if re.fullmatch(
        r"(?:IMG|DSC|DSCF|DSCN|PXL|VID|MOV)\s*\d+(?:\s+\d+)*",
        proposed_info,
        re.IGNORECASE,
    ):
        logger.debug(
            "Filename rejected as Info (camera-generated): source=%s.",
            context.source_path,
        )
        return

    # Reject UUID-like and long hexadecimal identifiers.
    if re.fullmatch(
        r"[0-9a-f]{8}(?:\s+[0-9a-f]{4}){3}\s+[0-9a-f]{12}",
        proposed_info,
        re.IGNORECASE,
    ) or re.fullmatch(r"[0-9a-f]{16,}", proposed_info, re.IGNORECASE):
        logger.debug(
            "Filename rejected as Info (identifier): source=%s.",
            context.source_path,
        )
        return

    photo_record["info"] = proposed_info

    logger.info(
        "Info proposed from filename: source=%s, info=%s.",
        context.source_path,
        photo_record["info"],
    )


def update_progress_display(progress: ImportProgress) -> None:
    """Log the current import progress.

    Live GUI updates will be connected when the import loop is integrated
    with the main window.
    """
    logger.info(
        "Import progress: total=%d, processed=%d, successful=%d, "
        "failed=%d, remaining=%d.",
        progress.total,
        progress.processed,
        progress.successful,
        progress.failed,
        progress.remaining,
    )



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
    source_directory: Path | None = None,
    progress_callback: Callable[[ImportProgress], None] | None = None,
) -> ImportProgress:
    """Process candidates, record each outcome, and save recovery progress."""
    logger.info(
        "Starting import loop: %d candidate paths; checkpoint %s.",
        len(candidate_paths),
        checkpoint_path,
    )

    progress = initialise_progress(checkpoint)

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
    importer_data = checkpoint["filesystem_importer"]
    directory_classifications = importer_data.get(
        "directory_classifications", {}
    )

    logger.info(
        "Import loop resuming at candidate %d of %d.",
        progress.processed + 1 if progress.remaining else progress.total,
        progress.total,
    )

    for index, source_path in enumerate(
        candidate_paths[progress.processed:],
        start=progress.processed + 1,
    ):

        # Progress is updated only at the start of each iteration.
        # Never update progress after processing or saving a candidate.
        update_progress_display(progress)

        if progress_callback is not None:
            progress_callback(progress)

        logger.info(
            "Processing import candidate %d of %d: %s",
            index,
            progress.total,
            source_path,
        )

        record = process_candidate(
            source_path=source_path,
            photos_directory=photos_directory,
            event_name=event_name,
            directory_classifications=directory_classifications,
            source_directory=source_directory,
            existing_photo_records=checkpoint["photos"],
        )

        checkpoint["photos"].append(record)

        logger.info(
            "Photo record appended: candidate=%d, guid=%s, "
            "downloaded=%s, file=%s.",
            index,
            record["guid"],
            record["downloaded"],
            record["file"],
        )

        save_recovery_checkpoint(
            checkpoint=checkpoint,
            checkpoint_path=checkpoint_path,
        )

        progress = initialise_progress(checkpoint)

        logger.info(
            "Candidate %d of %d recorded and checkpoint saved.",
            index,
            progress.total,
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

