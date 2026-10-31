
"""Extract probable metadata fields from a decoded EXIF UserComment."""

import logging
import re
from typing import Any

from filesystem_importer.geocoding import location_validate
from filesystem_importer.metadata_validation import year_validate


logger = logging.getLogger(__name__)


def extract_usercomment_metadata(
    user_comment: str | None,
    photo_record: dict[str, Any],
) -> None:
    """Extract and validate UserComment fields into the photo record.

    A confidently extracted four-field comment is interpreted as:
    Event, Year, Location and Info.

    Pipe delimiters take precedence. If no pipe is present, colons
    and hyphens are used as delimiters.

    If the comment cannot be confidently extracted, preserve the
    entire comment in the Info field.
    """
    if user_comment is None or not user_comment.strip():
        logger.debug("No usable UserComment found.")
        return

    comment = user_comment

    if "|" in comment:
        fields = comment.split("|")
    else:
        fields = re.split(r"[:-]", comment)

    if len(fields) != 4:
        photo_record["info"] = comment

        logger.info(
            "UserComment retained in Info: expected four fields, "
            "found %d.",
            len(fields),
        )
        return

    event = fields[0].strip()
    year = fields[1].strip()
    location = fields[2].strip()
    info = fields[3].strip()

    validated_year = year_validate(year)
    validated_location = location_validate(location)

    if validated_year is None or validated_location is not True:
        photo_record["info"] = comment

        logger.info(
            "UserComment validation failed; entire comment "
            "retained in Info."
        )
        return

    photo_record["event"] = event
    photo_record["year"] = validated_year
    photo_record["location"] = location
    photo_record["info"] = info

    logger.info(
        "UserComment metadata extracted: event=%s, year=%s, "
        "location=%s, info_present=%s.",
        event,
        validated_year,
        location,
        bool(info),
    )

