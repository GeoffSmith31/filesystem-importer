
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

"""Dialog for confirming the Event Name."""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from filesystem_importer.app_logging import get_logger
from filesystem_importer.constants import APP_NAME

logger = get_logger(__name__)


class EventNameDialog(QDialog):
    """Ask the user to confirm or enter an Event Name."""

    def __init__(self, suggested_name="", parent=None):
        super().__init__(parent)

        self.setWindowTitle("Confirm Event Name")
        self.resize(500, 170)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)

        instructions = QLabel(
            "Confirm the Event Name for this import. "
            "You can edit the suggested name or enter a new one."
        )
        instructions.setWordWrap(True)
        instructions.setMinimumHeight(
            instructions.sizeHint().height()
        )
        layout.addWidget(instructions)

        self.event_name_edit = QLineEdit()
        self.event_name_edit.setObjectName("eventNameEdit")
        self.event_name_edit.setText(suggested_name)
        self.event_name_edit.setPlaceholderText("Enter Event Name")
        self.event_name_edit.setClearButtonEnabled(True)
        layout.addWidget(self.event_name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Confirm")

        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        logger.info(
            "Event Name dialog prepared; suggestion provided: %s",
            bool(suggested_name),
        )

    @property
    def event_name(self):
        """Return the confirmed Event Name, trimmed of outer whitespace."""
        return self.event_name_edit.text().strip()

    def _confirm(self):
        """Validate the Event Name before accepting the dialog."""

        event_name = self.event_name

        if not event_name:
            logger.warning("Event Name confirmation rejected: name is empty.")

            QMessageBox.warning(
                self,
                APP_NAME,
                "Please enter an Event Name before continuing.",
            )
            self.event_name_edit.setFocus()
            return

        logger.info("Event Name confirmed: %s", event_name)
        self.accept()
