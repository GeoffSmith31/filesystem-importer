
"""Extract probable metadata fields from an EXIF UserComment."""

import re
from dataclasses import dataclass
from piexif import helper
from filesystem_importer.geocoding import location_validate
from filesystem_importer.metadata_validation import year_validate

@dataclass(frozen=True)
class ExifMetadata:
    """Probable metadata values extracted from UserComment."""

    exif_event: str | None = None
    exif_year: str | None = None
    exif_location: str | None = None
    exif_info: str | None = None


def extract_usercomment_metadata(
    original_comment: bytes | None,
) -> ExifMetadata:
    """Extract and validate probable metadata fields from an EXIF UserComment.

    If the comment splits into exactly four fields, assign them in order:
    Event, Year, Location and Info.

    Accept the extracted fields only when Year and Location validation
    both succeed. Otherwise, preserve the entire original comment as Info.

    Comments that do not split into exactly four fields are also preserved
    in their entirety as Info.
    """
    if original_comment is None:
        return ExifMetadata()

    comment = helper.UserComment.load(original_comment)

    if "|" in comment:
        fields = comment.split("|")
    else:
        fields = re.split(r"[:-]", comment)

    if len(fields) != 4:
        return ExifMetadata(exif_info=comment)

    event = fields[0].strip()
    year = fields[1].strip()
    location = fields[2].strip()
    info = fields[3].strip()

    validated_year = year_validate(year)
    validated_location = location_validate(location)

    if validated_year is None or validated_location is not True:
        return ExifMetadata(exif_info=comment)

    return ExifMetadata(
        exif_event=event,
        exif_year=validated_year,
        exif_location=location,
        exif_info=info,
    )

