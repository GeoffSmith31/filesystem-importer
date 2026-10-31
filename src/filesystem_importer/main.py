
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

"""Application entry point for Filesystem Importer."""

import argparse
import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from filesystem_importer.app_logging import (
    configure_logging,
    get_logger,
)
from filesystem_importer.constants import APP_NAME
from filesystem_importer.geocoding import configure_geocoding
from filesystem_importer.geocoding_rate_limit import geocoding_rate_limiter
from filesystem_importer.gui import FilesystemImporterWindow
from filesystem_importer.settings import get_settings_path, load_settings
from filesystem_importer.settings_dialog import SettingsDialog
from filesystem_importer.startup_check import (
    CLEAN,
    INSPECTION_ERROR,
    ORPHANED_DATA,
    PARTIAL_IMPORT,
    inspect_staging_directory,
)
from filesystem_importer.workspace_discovery import (
    WorkspaceDiscoveryError,
    discover_workspace,
)

logger = get_logger(__name__)


def obtain_settings(parent=None):
    """Load settings or request them from the user on first run."""

    settings_path = get_settings_path()
    settings = load_settings(settings_path)

    # Request configuration on first run.
    if settings_path.exists():
        logger.info("Existing application settings are available.")
        return settings

    logger.info("Application settings require user configuration.")

    dialog = SettingsDialog(settings, parent)

    if dialog.exec() != dialog.DialogCode.Accepted:
        logger.warning("Application settings configuration was cancelled.")
        QMessageBox.critical(
            parent,
            APP_NAME,
            "The application is unable to proceed without valid settings.\n\n"
            "No importing session has been started.",
        )
        return None

    return dialog.settings


def initialise_window(window: FilesystemImporterWindow) -> None:
    """Discover the workspace and determine the initial GUI state."""

    logger.info("Checking Photo Manager workspace and staging area.")

    try:
        workspace = discover_workspace()
    except WorkspaceDiscoveryError as exc:
        logger.error("Workspace discovery failed: %s", exc)
        window.show_error_state(str(exc))
        return

    staging_directory = workspace / "Importers" / "Filesystem"
    window.staging_directory = staging_directory

    logger.info(
        "Filesystem Importer staging directory: %s",
        staging_directory,
    )

    result = inspect_staging_directory(staging_directory)

    if result.state == CLEAN:
        window.show_normal_state()
        return

    if result.state == PARTIAL_IMPORT:
        window.show_resume_state(
            project_name=result.project_name,
            modified_date=result.modified_date,
            importing_file=result.importing_file,
        )
        return

    if result.state == ORPHANED_DATA:
        window.show_orphaned_state(result.details)
        return

    if result.state == INSPECTION_ERROR:
        window.show_error_state(
            result.details or "The staging directory could not be inspected."
        )
        return

    logger.error("Unexpected startup state returned: %r", result.state)
    window.show_error_state(
        "The importer received an unrecognised startup state."
    )


def main() -> None:
    """Start Filesystem Importer."""

    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Enable development logging to the console.",
    )
    args = parser.parse_args()

    configure_logging(
        level=logging.DEBUG if args.dev else logging.INFO,
        console_logging=args.dev,
    )

    logger.info("%s starting.", APP_NAME)

    if args.dev:
        logger.debug("Development mode enabled.")

    app = QApplication(sys.argv[:1])

    settings = obtain_settings()

    if settings is None:
        logger.info(
            "%s startup cancelled because settings were not configured.",
            APP_NAME,
        )
        return

    configure_geocoding(settings)
    geocoding_rate_limiter.set_min_interval_seconds(
        settings.minimum_request_interval_seconds
    )

    logger.info(
        "Geocoding configured with a minimum request interval of %.1f seconds.",
        settings.minimum_request_interval_seconds,
    )

    window = FilesystemImporterWindow()
    initialise_window(window)
    window.show()

    try:
        exit_code = app.exec()
    except Exception:
        logger.exception("Unhandled exception in the GUI application.")
        raise
    finally:
        logger.info("%s stopped.", APP_NAME)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

