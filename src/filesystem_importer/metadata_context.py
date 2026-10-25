
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

"""Gather source information for one photo's metadata resolution."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import piexif
from piexif import helper

from filesystem_importer.app_logging import get_logger

logger = get_logger(__name__)


@dataclass
class PhotoMetadataContext:
    """Source information and derived-value containers for one photo."""

    # Original and staged files.
    source_path: Path
    staged_path: Path

    # Source filesystem information.
    filesystem_timestamp: datetime | None
    source_directory: Path
    relative_directory: Path

    # Saved configuration used when resolving inherited values.
    directory_classifications: dict[str, str]
    workspace_event: str

    # Original EXIF values read from the staged photo.
    user_comment: str | None = None
    user_comment_raw: bytes | None = None
    date_time_original: str | None = None
    gps_latitude: Any = None
    gps_latitude_ref: str | None = None
    gps_longitude: Any = None
    gps_longitude_ref: str | None = None

    # Derived values. None means unavailable, invalid or not yet resolved.
    event_ancestor: str | None = None
    year_ancestor: str | None = None
    location_ancestor: str | None = None
    info_ancestor: str | None = None

    event_comment: str | None = None
    year_comment: str | None = None
    location_comment: str | None = None
    info_comment: str | None = None

    geo_location: str | None = None

    # Parsed components are populated by the later UserComment parser.
    comment_components: list[str] | None = None


def _decode_user_comment(raw_comment: bytes | None) -> str | None:
    """Decode UserComment without changing the stored EXIF value."""
    if not isinstance(raw_comment, bytes) or not raw_comment:
        return None

    try:
        comment = helper.UserComment.load(raw_comment)
    except (ValueError, TypeError, UnicodeError) as exc:
        logger.debug("Could not decode EXIF UserComment: %s", exc)
        return None

    if not isinstance(comment, str) or not comment.strip():
        return None

    return comment


def _read_exif_values(
    staged_path: Path,
) -> dict[str, Any]:
    """Read the required raw EXIF values without modifying the photo."""
    try:
        exif = piexif.load(str(staged_path))
    except (OSError, ValueError, piexif.InvalidImageDataError) as exc:
        logger.warning("Could not read EXIF metadata from %s: %s",
                       staged_path, exc)
        return {}

    exif_ifd = exif.get("Exif", {})
    gps_ifd = exif.get("GPS", {})

    raw_comment = exif_ifd.get(piexif.ExifIFD.UserComment)
    raw_date = exif_ifd.get(piexif.ExifIFD.DateTimeOriginal)

    date_time_original = None
    if isinstance(raw_date, bytes):
        try:
            date_time_original = raw_date.decode("ascii").strip("\x00 ")
        except UnicodeDecodeError:
            logger.debug(
                "EXIF DateTimeOriginal is not valid ASCII: %s",
                staged_path,
            )

    raw_latitude_ref = gps_ifd.get(piexif.GPSIFD.GPSLatitudeRef)
    raw_longitude_ref = gps_ifd.get(piexif.GPSIFD.GPSLongitudeRef)

    return {
        "user_comment_raw": (
            raw_comment if isinstance(raw_comment, bytes) else None
        ),
        "user_comment": _decode_user_comment(raw_comment),
        "date_time_original": date_time_original,
        "gps_latitude": gps_ifd.get(piexif.GPSIFD.GPSLatitude),
        "gps_latitude_ref": _decode_gps_ref(raw_latitude_ref),
        "gps_longitude": gps_ifd.get(piexif.GPSIFD.GPSLongitude),
        "gps_longitude_ref": _decode_gps_ref(raw_longitude_ref),
    }


def _decode_gps_ref(value: Any) -> str | None:
    """Convert an EXIF GPS reference to a string when possible."""
    if isinstance(value, bytes):
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError:
            return None

    if isinstance(value, str):
        value = value.strip("\x00 ").upper()
        return value or None

    return None


def gather_photo_metadata_context(
    source_path: Path,
    staged_path: Path,
    source_directory: Path,
    directory_classifications: dict[str, str],
    workspace_event: str,
) -> PhotoMetadataContext:
    """Gather initial source information for one staged photo.

    The source photo is used for its filesystem timestamp and directory
    position. EXIF metadata is read from the staged copy.

    This function does not parse UserComment into fields, resolve
    inheritance, geocode GPS coordinates or build a photo record.
    """
    source_path = Path(source_path).expanduser().resolve()
    staged_path = Path(staged_path).expanduser().resolve()
    source_directory = Path(source_directory).expanduser().resolve()

    if not source_path.is_file():
        raise ValueError(f"Source photo does not exist: {source_path}")

    if not staged_path.is_file():
        raise ValueError(f"Staged photo does not exist: {staged_path}")

    try:
        relative_directory = source_path.parent.relative_to(
            source_directory
        )
    except ValueError as exc:
        raise ValueError(
            f"Source photo is outside the source directory: {source_path}"
        ) from exc

    try:
        filesystem_timestamp = datetime.fromtimestamp(
            source_path.stat().st_mtime
        )
    except OSError as exc:
        logger.warning(
            "Could not read source filesystem timestamp for %s: %s",
            source_path,
            exc,
        )
        filesystem_timestamp = None

    exif_values = _read_exif_values(staged_path)

    logger.debug(
        "Gathered metadata inputs for source=%s staged=%s",
        source_path,
        staged_path,
    )

    return PhotoMetadataContext(
        source_path=source_path,
        staged_path=staged_path,
        filesystem_timestamp=filesystem_timestamp,
        source_directory=source_directory,
        relative_directory=relative_directory,
        directory_classifications=dict(directory_classifications),
        workspace_event=workspace_event,
        **exif_values,
    )

