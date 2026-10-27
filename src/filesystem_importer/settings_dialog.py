
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

"""Dialog for entering and editing application settings."""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from filesystem_importer.app_logging import get_logger
from filesystem_importer.constants import APP_NAME
from filesystem_importer.settings import AppSettings, save_settings

logger = get_logger(__name__)


class SettingsDialog(QDialog):
    """Collect, validate and save application settings."""

    def __init__(
        self,
        settings: AppSettings,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.settings = settings

        self.setWindowTitle(f"{APP_NAME} - Application Settings")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)

        introduction = QLabel(
            "Configure the settings required by the application. "

        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        form = QFormLayout()

        self.request_interval_spin = QDoubleSpinBox()
        self.request_interval_spin.setRange(1.0, 3600.0)
        self.request_interval_spin.setDecimals(1)
        self.request_interval_spin.setSingleStep(0.5)
        self.request_interval_spin.setSuffix(" seconds")
        self.request_interval_spin.setValue(
            settings.minimum_request_interval_seconds
        )
        form.addRow(
            "Minimum request interval:",
            self.request_interval_spin,
        )

        layout.addLayout(form)

        note = QLabel(
            "The minimum interval must be at least one second when "
            "using the public Nominatim service."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._save_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _save_and_accept(self) -> None:
        """Validate and save settings before accepting the dialog."""

        proposed_settings = AppSettings(
            minimum_request_interval_seconds=(
                self.request_interval_spin.value()
            ),
        )

        try:
            proposed_settings.validate()
            save_settings(proposed_settings)
        except (OSError, TypeError, ValueError) as exc:
            logger.exception("Could not save application settings.")
            QMessageBox.warning(
                self,
                "Settings could not be saved",
                "The settings could not be saved.\n\n"
                f"{exc}\n\n"
                "Correct the problem or cancel to stop startup.",
            )
            return

        self.settings = proposed_settings
        logger.info("Application settings configured and saved.")
        self.accept()

