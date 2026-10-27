
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

"""Persistent application settings."""

import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from filesystem_importer.app_logging import get_logger
from filesystem_importer.constants import (
    APP_NAME,
    APP_VERSION,
    DEVELOPER_EMAIL,
)

logger = get_logger(__name__)

SETTINGS_FILENAME = "settings.json"
SETTINGS_VERSION = 1
DEFAULT_MINIMUM_REQUEST_INTERVAL_SECONDS = 1.0


def get_settings_path() -> Path:
    """Return the platform-specific persistent settings path."""
    return Path(user_data_dir("filesystem-importer")) / SETTINGS_FILENAME


@dataclass
class AppSettings:
    """Application settings that can be persisted between runs."""

    minimum_request_interval_seconds: float = (
        DEFAULT_MINIMUM_REQUEST_INTERVAL_SECONDS
    )

    @property
    def user_agent(self) -> str:
        """Build the User-Agent from application identity and developer contact."""
        return f"{APP_NAME}/{APP_VERSION} (contact: {DEVELOPER_EMAIL})"

    def validate(self) -> None:
        """Validate settings before they are saved or used."""
        interval = self.minimum_request_interval_seconds

        if isinstance(interval, bool) or not isinstance(interval, (int, float)):
            raise TypeError("Request interval must be a number.")

        if not math.isfinite(interval):
            raise ValueError("Request interval must be finite.")

        if interval < 1.0:
            raise ValueError(
                "Request interval cannot be less than 1 second."
            )


def load_settings(settings_path: Path | None = None) -> AppSettings:
    """Load settings, returning defaults when no usable file exists."""
    path = Path(settings_path) if settings_path is not None else get_settings_path()

    if not path.exists():
        logger.info("Settings file does not exist yet: %s.", path)
        return AppSettings()

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read settings file %s: %s", path, exc)
        return AppSettings()

    if not isinstance(data, dict) or data.get("version") != SETTINGS_VERSION:
        logger.warning(
            "Settings file has an invalid structure or version: %s",
            path,
        )
        return AppSettings()

    geocoding = data.get("geocoding")
    if not isinstance(geocoding, dict):
        logger.warning(
            "Settings file has no valid geocoding section: %s",
            path,
        )
        return AppSettings()

    contact_email = geocoding.get("contact_email", "")
    interval = geocoding.get(
        "minimum_request_interval_seconds",
        DEFAULT_MINIMUM_REQUEST_INTERVAL_SECONDS,
    )

    try:
        settings = AppSettings(
            minimum_request_interval_seconds=interval,
        )
        settings.validate()
    except (TypeError, ValueError) as exc:
        logger.warning("Invalid settings in %s: %s", path, exc)
        return AppSettings()

    logger.info("Loaded application settings from %s.", path)
    return settings


def save_settings(
    settings: AppSettings,
    settings_path: Path | None = None,
) -> None:
    """Validate and atomically save application settings."""
    settings.validate()

    path = Path(settings_path) if settings_path is not None else get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {
        "version": SETTINGS_VERSION,
        "geocoding": {
            "minimum_request_interval_seconds": (
                settings.minimum_request_interval_seconds
            ),
        },
    }

    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        temporary_path.replace(path)
        temporary_path = None

    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    "Could not remove temporary settings file %s.",
                    temporary_path,
                )

    logger.info("Saved application settings to %s.", path)

