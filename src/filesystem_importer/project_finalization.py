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

"""Publish a prepared Filesystem Importer project."""

import json
import re
from pathlib import Path, PureWindowsPath
from typing import Any

from filesystem_importer.app_logging import get_logger
from filesystem_importer.constants import (
    CHECKPOINT_FILENAME,
    PREPARED_FILENAME,
)
from filesystem_importer.workspace_discovery import (
    WorkspaceDiscoveryError,
    discover_workspace,
)

logger = get_logger(__name__)

PROJECT_FILENAME = "project.json"


class ProjectFinalizationError(Exception):
    """Raised when a prepared project cannot be published."""


def _sanitise_directory_name(name: str) -> str:
    """Return a safe, cross-platform project directory name."""

    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip().rstrip(" .")

    if not name or name in {".", ".."}:
        name = "Filesystem Import"

    reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }

    if name.split(".", 1)[0].upper() in reserved_names:
        name = f"_{name}"

    name = name[:100].rstrip(" .")

    return name or "Filesystem Import"


def _is_safe_filename(filename: Any) -> bool:
    """Return whether a value is a simple filename on Windows and POSIX."""

    if (
        not isinstance(filename, str)
        or not filename
        or filename in {".", ".."}
        or Path(filename).name != filename
        or PureWindowsPath(filename).name != filename
        or any(ord(character) < 32 for character in filename)
    ):
        return False

    return True


def _validate_prepared_project(
    data: dict[str, Any],
    staging_directory: Path,
) -> tuple[dict[str, Any], str, Path]:
    """Validate the prepared project and all referenced staged photos."""

    if set(data) != {"workspace", "metadata_policies", "photos"}:
        raise ProjectFinalizationError(
            "Prepared project must contain exactly workspace, "
            "metadata_policies and photos."
        )

    workspace = data.get("workspace")
    metadata_policies = data.get("metadata_policies")
    photos = data.get("photos")

    if not isinstance(workspace, dict):
        raise ProjectFinalizationError(
            "Prepared project has no valid workspace object."
        )

    if not isinstance(metadata_policies, dict):
        raise ProjectFinalizationError(
            "Prepared project has no valid metadata_policies object."
        )

    if not isinstance(photos, list) or not photos:
        raise ProjectFinalizationError(
            "Cannot publish a project with no photos."
        )

    if workspace.get("registration_status") != "COMPLETE":
        raise ProjectFinalizationError(
            "Photo registration is not marked as complete."
        )

    if workspace.get("download_status") != "COMPLETE":
        raise ProjectFinalizationError(
            "Photo downloads are not marked as complete."
        )

    event_name = workspace.get("event")

    if not isinstance(event_name, str) or not event_name.strip():
        raise ProjectFinalizationError(
            "The prepared project has no valid Event name."
        )

    image_folder = workspace.get("image_folder")

    if (
        not _is_safe_filename(image_folder)
        or image_folder in {".", ".."}
    ):
        raise ProjectFinalizationError(
            "The prepared project has an invalid image folder name."
        )

    photos_directory = staging_directory / image_folder

    if not photos_directory.is_dir() or photos_directory.is_symlink():
        raise ProjectFinalizationError(
            f"Photo directory not found or is not a regular directory: "
            f"{photos_directory}"
        )

    # Check every successful photo record before moving anything.
    for index, photo in enumerate(photos):

        if not isinstance(photo, dict):
            raise ProjectFinalizationError(
                f"Photo record {index} is not a JSON object."
            )

        guid = photo.get("guid")

        if photo.get("downloaded") is not True:
            raise ProjectFinalizationError(
                f"Photo {guid!r} is not marked as downloaded."
            )

        filename = photo.get("file")

        if not _is_safe_filename(filename):
            raise ProjectFinalizationError(
                f"Photo {guid!r} has an invalid filename."
            )

        photo_path = photos_directory / filename

        if not photo_path.is_file() or photo_path.is_symlink():
            raise ProjectFinalizationError(
                f"Expected photo file is missing or is not a regular file: "
                f"{photo_path}"
            )

    # Deliberately do not require geo_location to be populated.
    return workspace, event_name.strip(), photos_directory


def finalize_project(prepared_json_path: Path) -> Path:
    """Move a prepared project into the Photo Manager workspace.

    The final project.json rename is the publication commit point.
    The original importing.json recovery checkpoint is deleted only
    after that rename succeeds.
    """

    prepared_json_path = Path(prepared_json_path)

    if prepared_json_path.name != PREPARED_FILENAME:
        raise ProjectFinalizationError(
            f"Expected {PREPARED_FILENAME}: {prepared_json_path}"
        )

    staging_directory = prepared_json_path.parent
    importing_json_path = staging_directory / CHECKPOINT_FILENAME

    if not prepared_json_path.is_file() or prepared_json_path.is_symlink():
        raise ProjectFinalizationError(
            f"Prepared project file not found: {prepared_json_path}"
        )

    if not importing_json_path.is_file() or importing_json_path.is_symlink():
        raise ProjectFinalizationError(
            f"Recovery checkpoint not found: {importing_json_path}"
        )

    try:
        with prepared_json_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectFinalizationError(
            f"Cannot read prepared project: {prepared_json_path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ProjectFinalizationError(
            "Prepared project root must be a JSON object."
        )

    workspace_data, event_name, photos_directory = (
        _validate_prepared_project(data, staging_directory)
    )

    try:
        workspace_root = discover_workspace().resolve()
    except WorkspaceDiscoveryError as exc:
        raise ProjectFinalizationError(
            f"Cannot discover Photo Manager workspace: {exc}"
        ) from exc

    staging_directory = staging_directory.resolve()

    try:
        staging_directory.relative_to(workspace_root)
    except ValueError as exc:
        raise ProjectFinalizationError(
            "The staging directory is outside the Photo Manager workspace."
        ) from exc

    base_name = _sanitise_directory_name(event_name)
    existing_names = {
        entry.name.casefold()
        for entry in workspace_root.iterdir()
    }

    destination = None

    # Reserve a unique project directory without overwriting anything.
    for number in range(1, 10000):

        if number == 1:
            candidate_name = base_name
        else:
            suffix = f" ({number})"
            candidate_name = (
                base_name[:100 - len(suffix)].rstrip(" .") + suffix
            )

        if candidate_name.casefold() in existing_names:
            continue

        candidate = workspace_root / candidate_name

        try:
            candidate.mkdir()
        except FileExistsError:
            # Another process may have created this name since the check.
            continue
        except OSError as exc:
            raise ProjectFinalizationError(
                f"Cannot create project directory {candidate}: {exc}"
            ) from exc

        destination = candidate
        break

    if destination is None:
        raise ProjectFinalizationError(
            "Could not find an available project directory name."
        )

    logger.info("Publishing Filesystem project into: %s", destination)

    destination_photos = destination / workspace_data["image_folder"]
    destination_prepared = destination / PREPARED_FILENAME
    project_path = destination / PROJECT_FILENAME

    moved_photos = False
    moved_prepared = False

    try:
        # Move the staged photographs first.
        photos_directory.rename(destination_photos)
        moved_photos = True

        # Move the prepared project JSON.
        prepared_json_path.rename(destination_prepared)
        moved_prepared = True

        # Final commit: Photo Manager can now discover the project.
        destination_prepared.rename(project_path)

    except OSError as exc:
        logger.exception("Filesystem project publication failed.")

        rollback_errors = []

        if moved_prepared and destination_prepared.exists():
            try:
                destination_prepared.rename(prepared_json_path)
            except OSError as rollback_exc:
                rollback_errors.append(
                    f"Could not restore prepared.json: {rollback_exc}"
                )

        if moved_photos and destination_photos.exists():
            try:
                destination_photos.rename(photos_directory)
            except OSError as rollback_exc:
                rollback_errors.append(
                    f"Could not restore photos directory: {rollback_exc}"
                )

        try:
            destination.rmdir()
        except OSError:
            pass

        details = " ".join(rollback_errors)

        raise ProjectFinalizationError(
            f"Project publication failed: {exc}. {details}".strip()
        ) from exc

    logger.info("Filesystem project published: %s", project_path)

    # The project is now published. Remove the original recovery checkpoint.
    try:
        importing_json_path.unlink()
    except OSError:
        # Do not report publication as failed after project.json exists.
        logger.exception(
            "Project was published, but the recovery checkpoint "
            "could not be removed: %s",
            importing_json_path,
        )

    return project_path
