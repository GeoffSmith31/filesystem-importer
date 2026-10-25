
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

"""Directory-level classification dialog."""

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from filesystem_importer.app_logging import get_logger

logger = get_logger(__name__)

MAX_CLASSIFICATION_LEVELS = 10

CATEGORIES = (
    "Event",
    "Location",
    "Year",
    "Info",
    "Ignore",
)


class ClassificationDialog(QDialog):
    """Assign one metadata category to each directory level."""

    def __init__(self, scan_result, existing_classifications=None, parent=None):
        super().__init__(parent)

        self.scan_result = scan_result
        self.classifications = dict(existing_classifications or {})
        self.level_names = self._build_level_names()

        self.setWindowTitle("Classify Directory Levels")
        self.resize(950, 600)
        self.setMinimumSize(750, 450)

        self._build_ui()

        logger.info(
            "Classification dialog prepared: %d levels displayed.",
            len(self.level_names),
        )

    def _build_level_names(self):
        """Group relevant directory names by level."""

        source_name = (
            self.scan_result.source_directory.name
            or str(self.scan_result.source_directory)
        )

        names_by_level = {1: {source_name}}

        self.deepest_level = 1

        for relative_path in self.scan_result.relevant_directories:
            level = len(relative_path.parts) + 1
            self.deepest_level = max(self.deepest_level, level)

            if level <= MAX_CLASSIFICATION_LEVELS:
                names_by_level.setdefault(level, set()).add(
                    relative_path.name
                )

        displayed_depth = min(
            self.deepest_level,
            MAX_CLASSIFICATION_LEVELS,
        )

        level_names = {
            level: sorted(
                names_by_level.get(level, set()),
                key=str.casefold,
            )
            for level in range(1, displayed_depth + 1)
        }

        logger.debug(
            "Directory levels built: deepest level %d, "
            "%d levels displayed.",
            self.deepest_level,
            len(level_names),
        )

        return level_names

    def _build_ui(self):
        """Create the classification table and dialog controls."""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        source_label = QLabel(
            f"Source directory: {self.scan_result.source_directory}"
        )
        source_label.setWordWrap(True)
        layout.addWidget(source_label)

        deepest_level = self.deepest_level
        file_count = len(self.scan_result.candidate_files)

        summary = QLabel(
            f"{file_count} candidate image files found. "
            f"Deepest relevant directory level: {deepest_level}."
        )
        layout.addWidget(summary)

        if deepest_level > MAX_CLASSIFICATION_LEVELS:
            logger.warning(
                "Source hierarchy reaches level %d, exceeding the "
                "classification limit of %d.",
                deepest_level,
                MAX_CLASSIFICATION_LEVELS,
            )

            warning = QLabel(
                f"Warning: the directory hierarchy extends beyond "
                f"Level {MAX_CLASSIFICATION_LEVELS}. Only the first "
                f"{MAX_CLASSIFICATION_LEVELS} levels can be classified. "
                "Files found deeper in the hierarchy will still be "
                "included in discovery and will inherit applicable "
                "metadata values. Consider restructuring the source "
                "directories to simplify future imports."
            )
            warning.setWordWrap(True)
            warning.setStyleSheet(
                "QLabel { padding: 8px; border: 1px solid #c58b24; }"
            )
            layout.addWidget(warning)

        instructions = QLabel(
            "Choose the meaning of each directory level. "
            "All directory names at the same level use the same category. "
            "Names that cannot be interpreted for the selected category "
            "will produce a null value."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.table = QTableWidget(len(self.level_names), 3, self)
        self.table.setHorizontalHeaderLabels(
            ["Directory Level", "Directory Names", "Category"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )

        self.category_combos = {}

        for row, (level, names) in enumerate(self.level_names.items()):
            level_item = QTableWidgetItem(f"Level {level}")
            level_item.setData(
                256, level
            )
            self.table.setItem(row, 0, level_item)

            names_item = QTableWidgetItem(", ".join(names))
            names_item.setToolTip("\n".join(names))
            self.table.setItem(row, 1, names_item)

            combo = QComboBox(self.table)
            combo.addItem("Select category", "")
            combo.addItems(CATEGORIES)

            saved_category = self.classifications.get(str(level), "")
            if saved_category in CATEGORIES:
                combo.setCurrentText(saved_category)

            combo.currentIndexChanged.connect(
                self._update_continue_button
            )

            self.category_combos[level] = combo
            self.table.setCellWidget(row, 2, combo)

        layout.addWidget(self.table, 1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        self.continue_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Ok
        )
        self.continue_button.setText("Continue")
        self.continue_button.setEnabled(False)

        self.button_box.accepted.connect(self._accept_classifications)
        self.button_box.rejected.connect(self.reject)

        layout.addWidget(self.button_box)

        self._update_continue_button()

    def _update_continue_button(self, *_args):
        """Enable Continue only when all displayed levels are classified."""

        complete = all(
            combo.currentText() in CATEGORIES
            for combo in self.category_combos.values()
        )

        self.continue_button.setEnabled(complete)

    def _accept_classifications(self):
        """Validate and return the selected level-to-category mapping."""

        classifications = {
            str(level): combo.currentText()
            for level, combo in self.category_combos.items()
        }

        if len(classifications) != len(self.category_combos):
            logger.warning(
                "Classification submission rejected: not all displayed "
                "levels have a category."
            )

            QMessageBox.warning(
                self,
                "Incomplete Classification",
                "Please select a category for every displayed level.",
            )
            return

        self.classifications = classifications

        logger.info(
            "Directory classifications accepted: %s",
            classifications,
        )

        self.accept()

