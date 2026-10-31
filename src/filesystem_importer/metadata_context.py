
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

import calendar
import piexif
import re
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Any
from piexif import helper

from filesystem_importer.app_logging import get_logger

logger = get_logger(__name__)


@dataclass
class PhotoMetadataContext:
    """Source information required for one photo's metadata resolution."""

    # Original and staged files.
    source_path: Path
    staged_path: Path

    # Source filesystem information.
    filesystem_timestamp: datetime | None
    source_directory: Path
    relative_directory: Path

    # Directory classifications and workspace configuration.
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


def _read_exif_values(staged_path: Path) -> dict[str, Any]:
    """Read the required raw EXIF values without modifying the photo."""
    try:
        exif = piexif.load(str(staged_path))
    except (OSError, ValueError, piexif.InvalidImageDataError) as exc:
        logger.warning(
            "Could not read EXIF metadata from %s: %s",
            staged_path,
            exc,
        )
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


def _normalise_inherited_year(folder_name: str) -> str | None:
    """Validate and normalise a directory name used as an inherited Year."""
    value = folder_name.strip()

    logger.debug(
        "Validating inherited Year folder name: %r",
        folder_name,
    )

    if not value:
        logger.debug("Rejected inherited Year: folder name is empty.")
        return None

    # A four-digit calendar year.
    if re.fullmatch(r"\d{4}", value):
        year = int(value)

        if 1 <= year <= 9999:
            logger.debug(
                "Accepted inherited Year %r, normalised to %r.",
                folder_name,
                value,
            )
            return value

        logger.debug(
            "Rejected inherited Year %r: year is outside the valid range.",
            folder_name,
        )
        return None

    # A date in day-month-year form, normalised to DD-Mmm-YYYY.
    date_match = re.fullmatch(
        r"(\d{1,2})-([A-Za-z]+)-(\d{4})",
        value,
    )

    if date_match:
        day_text, month_text, year_text = date_match.groups()

        month_numbers = {
            name.casefold(): number
            for number, name in enumerate(calendar.month_name)
            if name
        }
        month_numbers.update({
            name.casefold(): number
            for number, name in enumerate(calendar.month_abbr)
            if name
        })
        month_numbers["sept"] = 9

        month = month_numbers.get(month_text.casefold())

        if month is None:
            logger.debug(
                "Rejected inherited Year %r: unrecognised month %r.",
                folder_name,
                month_text,
            )
            return None

        try:
            parsed_date = date(
                int(year_text),
                month,
                int(day_text),
            )
        except ValueError:
            logger.debug(
                "Rejected inherited Year %r: invalid calendar date.",
                folder_name,
            )
            return None

        normalised = (
            f"{parsed_date.day:02d}-"
            f"{calendar.month_abbr[parsed_date.month]}-"
            f"{parsed_date.year:04d}"
        )

        logger.debug(
            "Accepted inherited Year %r, normalised to %r.",
            folder_name,
            normalised,
        )
        return normalised

    # Full month names and recognised abbreviations.
    month_names = {
        name.casefold(): name
        for name in calendar.month_name
        if name
    }
    month_names.update({
        name.casefold(): calendar.month_name[number]
        for number, name in enumerate(calendar.month_abbr)
        if name
    })
    month_names["sept"] = "September"

    month = month_names.get(value.casefold())

    if month is not None:
        logger.debug(
            "Accepted inherited Year %r, normalised to %r.",
            folder_name,
            month,
        )
        return month

    # Full weekday names and recognised abbreviations.
    day_names = {
        name.casefold(): name
        for name in calendar.day_name
    }
    day_names.update({
        name.casefold(): calendar.day_name[number]
        for number, name in enumerate(calendar.day_abbr)
    })

    day = day_names.get(value.casefold())

    if day is not None:
        logger.debug(
            "Accepted inherited Year %r, normalised to %r.",
            folder_name,
            day,
        )
        return day

    # Seasons and agreed temporal descriptors.
    accepted_descriptors = {
        "autumn": "Autumn",
        "spring": "Spring",
        "summer": "Summer",
        "winter": "Winter",
        "morning": "Morning",
        "afternoon": "Afternoon",
        "night": "Night",
        "early": "Early",
        "late": "Late",
        "day": "Day",
    }

    normalised = accepted_descriptors.get(value.casefold())

    if normalised is not None:
        logger.debug(
            "Accepted inherited Year %r, normalised to %r.",
            folder_name,
            normalised,
        )
        return normalised

    logger.debug(
        "Rejected inherited Year %r: unsupported format.",
        folder_name,
    )
    return None


def _find_directory_ancestor(
    relative_directory: Path,
    source_directory: Path,
    directory_classifications: dict[str, str],
    category: str,
) -> tuple[str, str] | None:
    """Find the nearest usable directory value for a metadata category.

    Return (normalised_value, original_folder_name), or None if no
    usable classified directory is found.

    Classifications are keyed by directory level. The source root is
    level 1, and its immediate child directories are level 2.
    """
    current_directory = relative_directory

    logger.debug(
        "Searching for inherited %s from relative directory %s.",
        category,
        relative_directory,
    )

    while True:
        level = len(current_directory.parts) + 1
        classification = directory_classifications.get(str(level))

        logger.debug(
            "Checking directory %s at level %d: classification=%r, "
            "requested category=%r.",
            current_directory,
            level,
            classification,
            category,
        )

        if classification == category:
            if current_directory == Path("."):
                folder_name = source_directory.name
            else:
                folder_name = current_directory.name

            logger.debug(
                "Found %s classification at level %d: folder=%r.",
                category,
                level,
                folder_name,
            )

            if category == "Year":
                normalised_value = _normalise_inherited_year(folder_name)

                if normalised_value is not None:
                    logger.info(
                        "Inherited Year resolved to %r from folder %r.",
                        normalised_value,
                        folder_name,
                    )
                    return normalised_value, folder_name

                logger.debug(
                    "Continuing Year search because folder %r "
                    "contains an invalid Year value.",
                    folder_name,
                )

            elif folder_name.strip():
                logger.info(
                    "Inherited %s resolved to %r from folder %r.",
                    category,
                    folder_name,
                    folder_name,
                )
                return folder_name, folder_name

            else:
                logger.debug(
                    "Skipping %s folder with an empty name.",
                    category,
                )

        if current_directory == Path("."):
            break

        current_directory = current_directory.parent

        logger.debug(
            "Moving up to parent directory: %s.",
            current_directory,
        )

    logger.info(
        "No usable inherited %s value found from %s.",
        category,
        relative_directory,
    )
    return None


def _find_directory_ancestors(
    relative_directory: Path,
    source_directory: Path,
    directory_classifications: dict[str, str],
    category: str,
) -> list[tuple[str, str]]:
    """Find all non-empty classified directory ancestors.

    Return a list of (value, original_folder_name) pairs, ordered
    nearest to farthest.

    Unlike _find_directory_ancestor(), this function does not validate
    or normalise the folder names. The caller is responsible for
    deciding whether each candidate is usable.
    """
    current_directory = relative_directory
    ancestors: list[tuple[str, str]] = []

    logger.debug(
        "Searching for all %s ancestors from relative directory %s.",
        category,
        relative_directory,
    )

    while True:
        level = len(current_directory.parts) + 1
        classification = directory_classifications.get(str(level))

        logger.debug(
            "Checking directory %s at level %d: classification=%r, "
            "requested category=%r.",
            current_directory,
            level,
            classification,
            category,
        )

        if classification == category:
            if current_directory == Path("."):
                folder_name = source_directory.name
            else:
                folder_name = current_directory.name

            if folder_name.strip():
                ancestors.append((folder_name, folder_name))

                logger.debug(
                    "Added %s ancestor candidate at level %d: %r.",
                    category,
                    level,
                    folder_name,
                )

        if current_directory == Path("."):
            break

        current_directory = current_directory.parent

    logger.info(
        "Found %d %s ancestor candidate(s) from %s.",
        len(ancestors),
        category,
        relative_directory,
    )

    return ancestors

