
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

"""Graphical user interface for Filesystem Importer."""

import shutil
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from pathlib import Path

from filesystem_importer.file_discovery import scan_source_directory
from filesystem_importer.app_logging import get_logger
from filesystem_importer.constants import APP_NAME, HELP_URL
from filesystem_importer.classification_dialog import ClassificationDialog
from filesystem_importer.event_name_dialog import EventNameDialog
from filesystem_importer.checkpoint_writer import write_initial_checkpoint
from filesystem_importer.checkpoint_reader import read_checkpoint
from filesystem_importer.staging_audit import audit_staging_directory
from filesystem_importer.import_loop import initialise_progress

logger = get_logger(__name__)


class FilesystemImporterWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle(APP_NAME)
        self.resize(700, 420)

        # Set when a resumable partial import has been detected.
        # Startup detection will be implemented separately.
        self.partial_import = None
        self.startup_state = "clean"
        self.scan_result = None
        self.classifications = None
        self.event_name = None
        self.staging_directory: Path | None = None
        self.checkpoint_path: Path | None = None
        self._build_ui()
        self.show_normal_state()

        logger.info("Main window initialised.")

    def _build_ui(self):
        """Create the initial screen and its controls."""

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(40, 35, 40, 25)
        layout.setSpacing(18)

        title = QLabel(APP_NAME)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 24px; font-weight: bold; padding: 10px;"
        )
        layout.addWidget(title)

        self.status_heading = QLabel()
        self.status_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_heading.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding-top: 10px;"
        )
        layout.addWidget(self.status_heading)

        self.status_detail = QLabel()
        self.status_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_detail.setWordWrap(True)
        layout.addWidget(self.status_detail)

        layout.addSpacing(12)

        self.primary_button = QPushButton("Select Source Directory")
        self.primary_button.setMinimumHeight(42)
        self.primary_button.clicked.connect(self._on_primary_clicked)
        layout.addWidget(self.primary_button)

        self.secondary_button = QPushButton()
        self.secondary_button.setMinimumHeight(42)
        self.secondary_button.clicked.connect(
            self._on_secondary_clicked
        )
        layout.addWidget(self.secondary_button)

        layout.addStretch()

        help_layout = QHBoxLayout()
        help_layout.addStretch()

        self.help_button = QPushButton("Help")
        self.help_button.setMinimumWidth(110)
        self.help_button.clicked.connect(self._on_help_clicked)
        help_layout.addWidget(self.help_button)

        layout.addLayout(help_layout)


    def show_normal_state(self):
        """Display the screen when no partial import is available."""

        self.partial_import = None
        self.startup_state = "clean"

        self.status_heading.setText("No partial imports detected")
        self.status_detail.setText(
            "Select a source directory to begin a new import."
        )

        self.primary_button.setText("Select Source Directory")
        self.primary_button.show()
        self.primary_button.setEnabled(True)
        self.secondary_button.hide()

        logger.info("Initial screen set to normal state.")

    def show_resume_state(
        self,
        project_name=None,
        modified_date=None,
        importing_file=None,
    ):
        """Display the screen when a partial import is available."""

        self.startup_state = "partial_import"
        self.partial_import = {
            "project_name": project_name,
            "modified_date": modified_date,
            "importing_file": importing_file,
        }

        self.status_heading.setText("Partial import detected")

        details = []

        if project_name:
            details.append(f"Project: {project_name}")

        if modified_date:
            details.append(f"Last modified: {modified_date}")

        details.append(
            "The project will be verified when you select Resume."
        )

        self.status_detail.setText("\n".join(details))

        self.primary_button.setText("Resume")
        self.primary_button.show()
        self.primary_button.setEnabled(True)

        self.secondary_button.setText("Delete Partial Import")
        self.secondary_button.show()

        logger.info(
            "Resume screen displayed for checkpoint: %s",
            importing_file,
        )

    def show_orphaned_state(self, details=None):
        """Display staging data that has no importing.json checkpoint."""

        self.partial_import = None
        self.startup_state = "orphaned_data"

        self.status_heading.setText("Incomplete import data detected")
        self.status_detail.setText(
            (details or "Staging data exists without importing.json.")
            + "\n\nA new import cannot start until this data is dealt with."
        )

        self.primary_button.hide()
        self.secondary_button.setText("Delete Partial Import")
        self.secondary_button.show()

        logger.warning("Orphaned staging data detected.")

    def show_error_state(self, details):
        """Display a startup error that prevents a new import."""

        self.partial_import = None
        self.startup_state = "inspection_error"

        self.status_heading.setText("Workspace inspection failed")
        self.status_detail.setText(
            f"{details}\n\n"
            "No import can be started until this problem is resolved."
        )

        self.primary_button.hide()
        self.secondary_button.hide()

        logger.error("Startup inspection failed: %s", details)


    def _open_classification_dialog(self):
        """Open the directory-level classification screen."""

        if self.scan_result is None:
            return

        dialog = ClassificationDialog(
            self.scan_result,
            existing_classifications=self.classifications,
            parent=self,
        )

        if dialog.exec() != dialog.DialogCode.Accepted:
            logger.info("Directory classification cancelled.")
            self.primary_button.setText("Classify Directory Levels")
            return

        self.classifications = dialog.classifications

        logger.info(
            "Directory classification completed: %s",
            self.classifications,
        )

        self._open_event_name_dialog()

    def _suggest_event_name(self):
        """Suggest a name from the first directory at the highest Event level."""

        event_levels = [
            int(level)
            for level, category in self.classifications.items()
            if category == "Event"
        ]

        if not event_levels:
            return ""

        event_level = min(event_levels)

        if event_level == 1:
            return (
                self.scan_result.source_directory.name
                or str(self.scan_result.source_directory)
            )

        directory_names = sorted(
            {
                relative_path.name
                for relative_path in self.scan_result.relevant_directories
                if len(relative_path.parts) + 1 == event_level
            },
            key=str.casefold,
        )

        if not directory_names:
            return ""

        return directory_names[0]


    def _open_event_name_dialog(self):
        """Ask the user to confirm or enter the Event Name."""

        if self.scan_result is None or self.classifications is None:
            return

        dialog = EventNameDialog(
            suggested_name=self._suggest_event_name(),
            parent=self,
        )

        if dialog.exec() != dialog.DialogCode.Accepted:
            logger.info("Event Name confirmation cancelled.")
            self.status_heading.setText(
                "Directory classification complete"
            )
            self.status_detail.setText(
                "Your directory classifications have been retained.\n\n"
                "Confirm the Event Name to continue."
            )
            self.primary_button.setText("Confirm Event Name")
            self.primary_button.setEnabled(True)
            return

        self.event_name = dialog.event_name

        logger.info("Event Name confirmed: %s", self.event_name)

        self._create_checkpoint()

    def _create_checkpoint(self):
        """Create the initial importing.json checkpoint."""

        if (
            self.scan_result is None
            or self.classifications is None
            or self.event_name is None
        ):
            logger.error("Cannot create checkpoint: import details are missing.")
            return

        if self.staging_directory is None:
            message = (
                "The Photo Manager staging directory has not been configured."
            )
            logger.error(message)
            QMessageBox.warning(self, APP_NAME, message)
            return

        try:
            checkpoint_path = write_initial_checkpoint(
                staging_directory=self.staging_directory,
                source_directory=self.scan_result.source_directory,
                event_name=self.event_name,
                classifications=self.classifications,
            )
        except (OSError, ValueError) as exc:
            logger.exception("Initial checkpoint creation failed.")

            self.status_heading.setText("Checkpoint creation failed")
            self.status_detail.setText(
                f"The initial checkpoint could not be created:\n\n{exc}\n\n"
                "Your directory classifications and Event Name have been "
                "retained. Correct the problem and retry."
            )
            self.primary_button.setText("Retry Checkpoint Creation")
            self.primary_button.setEnabled(True)

            QMessageBox.warning(
                self,
                APP_NAME,
                f"The initial checkpoint could not be created:\n\n{exc}\n\n"
                "Your selections have been retained so you can retry.",
            )
            return


        self.checkpoint_path = checkpoint_path

        try:
            checkpoint, scan_result = read_checkpoint(checkpoint_path)
        except (OSError, ValueError) as exc:
            logger.exception(
                "Could not reload the newly created checkpoint."
            )
            self.status_heading.setText("Checkpoint created")
            self.status_detail.setText(
                f"The initial checkpoint was created at:\n"
                f"{checkpoint_path}\n\n"
                "However, it could not be reloaded for progress "
                f"initialisation:\n\n{exc}"
            )
            self.primary_button.setText("Checkpoint Created")
            self.primary_button.setEnabled(False)
            return

        self.scan_result = scan_result
        self.start_import(checkpoint)



    def start_import(self, checkpoint):
        """Enter the import workflow and display its current progress."""
        progress = initialise_progress(checkpoint)

        self.status_heading.setText("Import progress")
        self.status_detail.setText(
            f"Event: {self.event_name}\n"
            f"Source: {self.scan_result.source_directory}\n\n"
            f"Total candidates: {progress.total}\n"
            f"Processed: {progress.processed}\n"
            f"Successful: {progress.successful}\n"
            f"Failed: {progress.failed}\n"
            f"Remaining: {progress.remaining}"
        )

        self.primary_button.setText("Import Ready")
        self.primary_button.setEnabled(False)
        self.secondary_button.hide()

        logger.info(
            "Import progress initialised: total=%d, processed=%d, "
            "successful=%d, failed=%d, remaining=%d",
            progress.total,
            progress.processed,
            progress.successful,
            progress.failed,
            progress.remaining,
        )


    def _on_primary_clicked(self):
        """Handle the primary action."""

        if self.checkpoint_path is not None:
            return

        if self.scan_result is not None and self.classifications is None:
            self._open_classification_dialog()
            return

        if self.scan_result is not None and self.classifications is not None:
            if self.event_name is None:
                self._open_event_name_dialog()
            else:
                self._create_checkpoint()
            return

        if self.partial_import is not None:
            logger.info("Resume requested by user.")

            if self.staging_directory is None:
                QMessageBox.warning(
                    self,
                    APP_NAME,
                    "The staging directory is not configured. "
                    "The partial import cannot be resumed.",
                )
                return

            checkpoint_path = (
                self.staging_directory / "importing.json"
            )

            try:
                checkpoint, scan_result = read_checkpoint(
                    checkpoint_path
                )
            except (OSError, ValueError) as exc:
                logger.warning(
                    "Checkpoint validation failed: %s", exc
                )
                QMessageBox.warning(
                    self,
                    APP_NAME,
                    "The partial import cannot be resumed.\n\n"
                    f"{exc}\n\n"
                    "The existing checkpoint has not been changed.",
                )
                return

            try:
                audit_result = audit_staging_directory(
                    self.staging_directory / "photos",
                    checkpoint.get("photos"),
                )
            except (OSError, ValueError) as exc:
                logger.warning(
                    "Staging audit failed: %s", exc
                )
                QMessageBox.warning(
                    self,
                    APP_NAME,
                    "The partial import cannot be resumed because "
                    "the staging directory failed its audit.\n\n"
                    f"{exc}\n\n"
                    "No further import processing has started.",
                )
                return

            if audit_result.orphan_files_deleted:
                logger.info(
                    "Staging audit removed %d orphan files.",
                    len(audit_result.orphan_files_deleted),
                )

            workspace_data = checkpoint["workspace"]
            importer_data = checkpoint["filesystem_importer"]

            self.scan_result = scan_result
            self.classifications = importer_data[
                "directory_classifications"
            ]
            self.event_name = workspace_data["event"]
            self.checkpoint_path = checkpoint_path

            logger.info(
                "Checkpoint validated. Event: %s; source: %s",
                self.event_name,
                scan_result.source_directory,
            )

            self.start_import(checkpoint)
            return


        logger.info("Source directory selection requested.")

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Source Directory",
        )

        # Cancelling the picker leaves the current screen unchanged.
        if not directory:
            logger.info("Source directory selection cancelled.")
            return

        logger.info("Source directory selected: %s", directory)

        try:
            result = scan_source_directory(Path(directory))
        except (OSError, ValueError) as exc:
            logger.exception("Could not scan source directory.")
            QMessageBox.warning(
                self,
                APP_NAME,
                f"The source directory could not be scanned:\n\n{exc}",
            )
            return

        self.scan_result = result

        file_count = len(result.candidate_files)
        directory_count = len(result.directories_with_candidates)
        relevant_count = len(result.relevant_directories)
        error_count = len(result.scan_errors)

        if file_count == 0:
            heading = "No candidate images found"
        elif error_count:
            heading = "Scan completed with warnings"
        else:
            heading = "Source directory scanned"

        # Calculate the deepest relevant directory level.
        # The selected source directory is Level 1.
        deepest_level = max(
            (
                len(path.parts) + 1
                for path in result.relevant_directories
            ),
            default=1,
        )

        details = [
            f"Source: {result.source_directory}",
            "",
            f"Candidate image files: {file_count}",
            f"Directories containing candidate files: {directory_count}",
            f"Deepest directory level: {deepest_level}",
        ]

        if error_count:
            details.extend([
                "",
                f"Warning: {error_count} path(s) could not be scanned.",
                "The results may be incomplete.",
            ])

        self.status_heading.setText(heading)
        self.status_detail.setText("\n".join(details))
        self.primary_button.setText("Classify Directory Levels")
        self.primary_button.show()
        self.primary_button.setEnabled(True)
        self.secondary_button.hide()

        logger.info(
            "Scan results displayed: %d files, %d directories "
            "containing candidates, depth %d, %d errors.",
            file_count,
            directory_count,
            deepest_level,
            error_count,
        )

        # Automatically proceed to directory classification.
        self._open_classification_dialog()


    def _on_secondary_clicked(self):
        """Handle deletion requests for partial or orphaned staging data."""

        if self.startup_state not in {"partial_import", "orphaned_data"}:
            return

        if self.staging_directory is None:
            QMessageBox.warning(
                self,
                APP_NAME,
                "The staging directory is not configured. "
                "Nothing has been deleted.",
            )
            return

        if self.startup_state == "orphaned_data":
            description = (
                "The staging directory contains files but no importing.json "
                "checkpoint. These files cannot be resumed."
            )
        else:
            description = (
                "An unfinished import was found in the staging directory."
            )

        answer = QMessageBox.question(
            self,
            "Delete Partial Import",
            f"{description}\n\n"
            "All contents of the Filesystem Importer staging directory "
            "will be deleted. This action cannot be undone.\n\n"
            "Do you want to continue?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            logger.info("Partial import deletion cancelled.")
            return

        staging_directory = self.staging_directory

        # Safety check: only delete the expected Filesystem staging folder.
        if (
            staging_directory.name != "Filesystem"
            or staging_directory.parent.name != "Importers"
        ):
            logger.error(
                "Refusing to delete unexpected staging directory: %s",
                staging_directory,
            )
            QMessageBox.warning(
                self,
                APP_NAME,
                "The staging directory path did not pass the safety check. "
                "Nothing has been deleted.",
            )
            return

        try:
            for entry in staging_directory.iterdir():
                if entry.is_symlink() or not entry.is_dir():
                    entry.unlink()
                else:
                    shutil.rmtree(entry)

        except OSError as exc:
            logger.exception(
                "Could not completely delete staging contents: %s",
                staging_directory,
            )
            QMessageBox.warning(
                self,
                APP_NAME,
                "The staging contents could not be completely deleted.\n\n"
                f"{exc}\n\n"
                "Inspect the staging directory before starting another import.",
            )

            # Reinspect the directory to reflect whatever remains.
            from filesystem_importer.startup_check import (
                inspect_staging_directory,
                CLEAN,
                PARTIAL_IMPORT,
                ORPHANED_DATA,
                INSPECTION_ERROR,
            )

            result = inspect_staging_directory(staging_directory)

            if result.state == CLEAN:
                self.show_normal_state()
            elif result.state == PARTIAL_IMPORT:
                self.show_resume_state(
                    project_name=result.project_name,
                    modified_date=result.modified_date,
                    importing_file=result.importing_file,
                )
            elif result.state == ORPHANED_DATA:
                self.show_orphaned_state(result.details)
            else:
                self.show_error_state(
                    result.details or "Could not inspect remaining staging data."
                )
            return

        logger.info(
            "Deleted partial-import staging contents from %s",
            staging_directory,
        )
        self.show_normal_state()

    def _on_help_clicked(self):
        """Open the help documentation in the web browser."""

        logger.info("Help requested by user.")

        if not HELP_URL:
            QMessageBox.information(
                self,
                "Help",
                "The help documentation is not available yet.",
            )
            return

        opened = QDesktopServices.openUrl(QUrl(HELP_URL))

        if not opened:
            logger.error("Could not open help URL: %s", HELP_URL)

            QMessageBox.warning(
                self,
                "Help",
                "The help page could not be opened in your web browser.",
            )
