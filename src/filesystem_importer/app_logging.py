
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

"""
Filesystem Importer Logging Service

Purpose
-------
Provides the application logging service used by all Filesystem Importer
components.

Responsibilities
----------------
- Configure application logging.
- Create named loggers.
- Apply the configured logging level.
- Write log messages to the rotating log file.
- Optionally write log messages to the console during development.

Notes
-----
The logging service is configured during application startup.
Application components obtain named loggers through get_logger().

The logging service determines the log filename, rotation limits,
formatting, and log directory.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

APPLICATION_ID = "filesystem-importer"

_LOG_FILE_NAME = f"{APPLICATION_ID}.log"
_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 5

_LOG_FORMAT = (
    "%(asctime)s "
    "[%(levelname)-7s] "
    "%(name)-24s "
    "%(message)s"
)
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

__all__ = ["configure_logging", "get_logger", "get_log_directory"]


def get_log_directory() -> Path:
    """Return the application log directory."""
    return (
        Path.home()
        / ".local"
        / "share"
        / APPLICATION_ID
        / "logs"
    )


def configure_logging(
    level: int = logging.INFO,
    log_directory: Path | None = None,
    console_logging: bool = False,
) -> None:
    """Configure rotating file logging and optional console logging."""
    root_logger = logging.getLogger()

    # Remove existing handlers so configuration is repeatable.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    root_logger.setLevel(level)

    formatter = logging.Formatter(
        _LOG_FORMAT,
        datefmt=_LOG_DATE_FORMAT,
    )

    if console_logging:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if log_directory is None:
        log_directory = get_log_directory()

    log_directory.mkdir(parents=True, exist_ok=True)

    log_file = log_directory / _LOG_FILE_NAME

    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    logger = get_logger("Logging Service")
    logger.info("Logging service initialised.")
    logger.info("Logging level: %s", logging.getLevelName(level))
    logger.info("Log file: %s", log_file.resolve())


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for an application component."""
    return logging.getLogger(name)
