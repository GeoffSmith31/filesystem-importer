
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

"""Discover the Photo Manager workspace from its user settings."""

import json
import os
import tempfile
from pathlib import Path

from platformdirs import user_config_dir

from filesystem_importer.app_logging import get_logger

logger = get_logger(__name__)

SETTINGS_FILENAME = "settings.json"
WORKSPACE_SETTING = "workspace_directory"


class WorkspaceDiscoveryError(Exception):
    """Raised when the Photo Manager workspace cannot be discovered."""


def discover_workspace() -> Path:
    """Return the configured, accessible Photo Manager workspace.

    Raises:
        WorkspaceDiscoveryError: If settings are invalid or the workspace
            cannot be inspected and tested for writing.
    """

    config_directory = Path(user_config_dir("photo_manager"))
    settings_file = config_directory / SETTINGS_FILENAME

    logger.debug("Photo Manager configuration directory: %s", config_directory)
    logger.debug("Photo Manager settings file: %s", settings_file)

    try:
        with settings_file.open("r", encoding="utf-8") as file:
            settings = json.load(file)
    except FileNotFoundError as exc:
        logger.error("Photo Manager settings file not found: %s", settings_file)
        raise WorkspaceDiscoveryError(
            f"Photo Manager settings file was not found: {settings_file}"
        ) from exc
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in Photo Manager settings: %s", settings_file)
        raise WorkspaceDiscoveryError(
            "Photo Manager settings.json contains invalid JSON."
        ) from exc
    except OSError as exc:
        logger.exception("Could not read settings file: %s", settings_file)
        raise WorkspaceDiscoveryError(
            f"Could not read Photo Manager settings: {exc}"
        ) from exc

    if not isinstance(settings, dict):
        raise WorkspaceDiscoveryError(
            "Photo Manager settings.json must contain a JSON object."
        )

    workspace_value = settings.get(WORKSPACE_SETTING)

    if not isinstance(workspace_value, str) or not workspace_value.strip():
        raise WorkspaceDiscoveryError(
            f"Photo Manager settings must define a non-empty "
            f"'{WORKSPACE_SETTING}' value."
        )

    workspace = Path(workspace_value).expanduser()

    if not workspace.is_absolute():
        raise WorkspaceDiscoveryError(
            "The configured Photo Manager workspace path must be absolute."
        )

    try:
        if not workspace.exists():
            raise WorkspaceDiscoveryError(
                f"The configured workspace does not exist: {workspace}"
            )

        if not workspace.is_dir():
            raise WorkspaceDiscoveryError(
                f"The configured workspace is not a directory: {workspace}"
            )

        # Confirm that the workspace can be inspected.
        with os.scandir(workspace):
            pass

        # Test writing using a unique temporary filename.
        test_file_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".filesystem-importer-test-",
                dir=workspace,
                delete=False,
            ) as test_file:
                test_file_path = Path(test_file.name)
                test_file.write("Filesystem Importer workspace write test\n")
                test_file.flush()
                os.fsync(test_file.fileno())

        finally:
            if test_file_path is not None:
                try:
                    test_file_path.unlink(missing_ok=True)
                except OSError:
                    logger.exception(
                        "Could not remove workspace write-test file: %s",
                        test_file_path,
                    )
                    raise

    except WorkspaceDiscoveryError:
        logger.error("Configured workspace is invalid: %s", workspace)
        raise
    except OSError as exc:
        logger.exception(
            "Cannot inspect or write to configured workspace: %s",
            workspace,
        )
        raise WorkspaceDiscoveryError(
            f"Cannot access or write to the configured workspace: {exc}"
        ) from exc

    logger.info("Photo Manager workspace discovered: %s", workspace)
    return workspace
