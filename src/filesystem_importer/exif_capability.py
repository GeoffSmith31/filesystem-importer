
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

"""Test whether a staged JPEG supports EXIF UserComment writing."""

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import piexif
from piexif import helper

from filesystem_importer.app_logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ExifCapabilityResult:
    """Outcome of the staged-photo EXIF capability test."""

    supported: bool
    reason: str = ""


def check_usercomment_capability(image_path: Path) -> ExifCapabilityResult:
    """Test UserComment writing on a staged JPEG.

    The caller must pass a staged copy, never the source photo.

    The original UserComment is restored and verified when the test
    succeeds. On failure, the caller should delete the staged copy.
    """
    image_path = Path(image_path)

    logger.info("Starting EXIF UserComment capability test: %s", image_path)

    if image_path.suffix.lower() not in {".jpg", ".jpeg"}:
        logger.info(
            "EXIF capability test skipped: unsupported file extension %s",
            image_path.suffix,
        )
        return ExifCapabilityResult(
            supported=False,
            reason="EXIF capability testing is currently limited to JPEG.",
        )

    try:
        original_exif = piexif.load(str(image_path))
        original_comment = original_exif["Exif"].get(
            piexif.ExifIFD.UserComment
        )

        logger.debug(
            "Original UserComment present: %s",
            original_comment is not None,
        )

        test_value = f"FilesystemImporterTest-{uuid4().hex}"
        test_comment = helper.UserComment.dump(test_value)

        test_exif = {
            ifd_name: dict(ifd_data)
            for ifd_name, ifd_data in original_exif.items()
            if isinstance(ifd_data, dict)
        }
        test_exif["Exif"][piexif.ExifIFD.UserComment] = test_comment

        logger.debug("Writing temporary UserComment test value.")
        piexif.insert(piexif.dump(test_exif), str(image_path))

        written_exif = piexif.load(str(image_path))
        written_comment = written_exif["Exif"].get(
            piexif.ExifIFD.UserComment
        )
        if written_comment != test_comment:
            raise ValueError("Temporary UserComment could not be verified.")

        logger.debug("Temporary UserComment verified; restoring original value.")

        if original_comment is None:
            written_exif["Exif"].pop(piexif.ExifIFD.UserComment, None)
        else:
            written_exif["Exif"][piexif.ExifIFD.UserComment] = original_comment

        piexif.insert(piexif.dump(written_exif), str(image_path))

        restored_exif = piexif.load(str(image_path))
        restored_comment = restored_exif["Exif"].get(
            piexif.ExifIFD.UserComment
        )
        if restored_comment != original_comment:
            raise ValueError("Original UserComment could not be verified.")

        logger.info(
            "Original UserComment restored and verified: %s",
            image_path,
        )
        logger.info(
            "EXIF UserComment capability test succeeded: %s",
            image_path,
        )
        return ExifCapabilityResult(supported=True)

    except Exception as exc:
        logger.warning(
            "EXIF UserComment capability test failed for %s: %s",
            image_path,
            exc,
        )
        return ExifCapabilityResult(
            supported=False,
            reason=str(exc) or type(exc).__name__,
        )

