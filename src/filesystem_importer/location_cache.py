
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

"""Persistent cache of definitive forward-geocoding results."""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from filesystem_importer.app_logging import get_logger

logger = get_logger(__name__)

CACHE_FILENAME = "tested-locations.json"
CACHE_VERSION = 1


def _normalise_location_name(name: str) -> str:
    """Normalise a location name for cache lookup."""
    return " ".join(name.split()).casefold()


def get_location_cache_path() -> Path:
    """Return the platform-specific persistent cache path."""
    return Path(user_data_dir("filesystem-importer")) / CACHE_FILENAME


class LocationCache:
    """Store definitive valid/invalid location lookup results."""

    def __init__(self, cache_path: Path | None = None) -> None:
        self._cache_path = (
            Path(cache_path) if cache_path is not None
            else get_location_cache_path()
        )
        self._lock = threading.RLock()
        self._entries: dict[str, dict[str, str]] = {}

        self._load()

    @property
    def cache_path(self) -> Path:
        """Return the file used to persist this cache."""
        return self._cache_path

    def lookup(self, location_name: str) -> bool | None:
        """Return True/False for a cached answer, or None for a cache miss."""
        key = _normalise_location_name(location_name)

        if not key:
            return None

        with self._lock:
            entry = self._entries.get(key)

            if entry is None:
                logger.debug(
                    "Location cache miss for %r.",
                    location_name,
                )
                return None

            status = entry["status"]
            logger.debug(
                "Location cache hit for %r: %s.",
                location_name,
                status,
            )
            return status == "valid"

    def store(self, location_name: str, valid: bool) -> None:
        """Store a definitive geocoding answer and persist the cache."""
        if not isinstance(location_name, str):
            raise TypeError("Location name must be a string.")

        if not location_name.strip():
            raise ValueError("Location name cannot be empty.")

        if not isinstance(valid, bool):
            raise TypeError("Cache result must be a Boolean.")

        key = _normalise_location_name(location_name)
        status = "valid" if valid else "invalid"

        with self._lock:
            previous = self._entries.get(key)

            self._entries[key] = {
                "name": location_name.strip(),
                "status": status,
                "checked_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
            }

            try:
                self._save()
            except OSError:
                if previous is None:
                    self._entries.pop(key, None)
                else:
                    self._entries[key] = previous
                raise

            logger.debug(
                "Cached definitive location result for %r: %s.",
                location_name,
                status,
            )

    def _load(self) -> None:
        """Load cached answers from disk if the file exists."""
        with self._lock:
            if not self._cache_path.exists():
                logger.debug(
                    "Location cache does not exist yet: %s.",
                    self._cache_path,
                )
                return

            try:
                with self._cache_path.open("r", encoding="utf-8") as file:
                    data = json.load(file)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "Could not read location cache %s: %s",
                    self._cache_path,
                    exc,
                )
                return

            if not isinstance(data, dict):
                logger.warning(
                    "Location cache has an invalid top-level structure: %s",
                    self._cache_path,
                )
                return

            if data.get("version") != CACHE_VERSION:
                logger.warning(
                    "Unsupported location cache version in %s.",
                    self._cache_path,
                )
                return

            locations = data.get("locations")
            if not isinstance(locations, dict):
                logger.warning(
                    "Location cache has no valid locations mapping: %s",
                    self._cache_path,
                )
                return

            loaded: dict[str, dict[str, str]] = {}

            for key, entry in locations.items():
                if not isinstance(key, str) or not isinstance(entry, dict):
                    continue

                name = entry.get("name")
                status = entry.get("status")
                checked_at = entry.get("checked_at")

                if (
                    not isinstance(name, str)
                    or not name.strip()
                    or status not in ("valid", "invalid")
                    or not isinstance(checked_at, str)
                ):
                    continue

                normalised_key = _normalise_location_name(name)
                if normalised_key != key or not normalised_key:
                    continue

                loaded[key] = {
                    "name": name,
                    "status": status,
                    "checked_at": checked_at,
                }

            self._entries = loaded

            logger.info(
                "Loaded %d tested locations from %s.",
                len(self._entries),
                self._cache_path,
            )

    def _save(self) -> None:
        """Atomically write the cache to disk."""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "version": CACHE_VERSION,
            "locations": self._entries,
        }

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._cache_path.parent,
                prefix=f".{self._cache_path.name}.",
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

            temporary_path.replace(self._cache_path)
            temporary_path = None

        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Could not remove temporary location cache file %s.",
                        temporary_path,
                    )

