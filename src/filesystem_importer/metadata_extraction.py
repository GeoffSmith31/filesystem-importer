
"""Extract probable metadata fields from an EXIF UserComment."""

import re
from dataclasses import dataclass
from piexif import helper

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
    """Extract four probable metadata fields from an original UserComment.

    If the comment splits into exactly four fields, assign them in order:
    Event, Year, Location and Info.

    If it does not split into exactly four fields, preserve the entire
    comment as Info and leave the other fields undetermined.

    This function extracts fields only; it does not validate their values.
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

    return ExifMetadata(
        exif_event=fields[0].strip(),
        exif_year=fields[1].strip(),
        exif_location=fields[2].strip(),
        exif_info=fields[3].strip(),
    )

