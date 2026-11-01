import json
from pathlib import Path

import pytest

from filesystem_importer.project_finalization import (
    ProjectFinalizationError,
    finalize_project,
)
from filesystem_importer.constants import (
    CHECKPOINT_FILENAME,
    PREPARED_FILENAME,
)


@pytest.fixture
def project_staging(tmp_path, monkeypatch):
    """Create a staged project and a separate Photo Manager workspace."""

    workspace = tmp_path / "PhotoManager"
    staging = workspace / "Importers" / "Filesystem"
    photos = staging / "photos"

    photos.mkdir(parents=True)

    (photos / "photo1.jpg").write_bytes(b"photo one")
    (photos / "photo2.jpg").write_bytes(b"photo two")

    prepared = {
        "workspace": {
            "event": "Test Event",
            "image_folder": "photos",
            "registration_status": "COMPLETE",
            "download_status": "COMPLETE",
        },
        "metadata_policies": {
            "event": {},
            "year": {},
            "location": {},
            "info": {},
        },
        "photos": [
            {
                "guid": "photo-1",
                "file": "photo1.jpg",
                "downloaded": True,
                "geo_location": None,
            },
            {
                "guid": "photo-2",
                "file": "photo2.jpg",
                "downloaded": True,
                "geo_location": "Paris, France",
            },
        ],
    }

    prepared_path = staging / PREPARED_FILENAME
    prepared_path.write_text(
        json.dumps(prepared, indent=4),
        encoding="utf-8",
    )

    importing_path = staging / CHECKPOINT_FILENAME
    importing_path.write_text(
        '{"recovery": true}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "filesystem_importer.project_finalization.discover_workspace",
        lambda: workspace,
    )

    return workspace, staging, prepared_path, importing_path


def test_finalize_project_publishes_project(project_staging):
    workspace, staging, prepared_path, importing_path = project_staging

    project_path = finalize_project(prepared_path)

    assert project_path == workspace / "Test Event" / "project.json"
    assert project_path.is_file()

    project = json.loads(project_path.read_text(encoding="utf-8"))

    assert set(project) == {
        "workspace",
        "metadata_policies",
        "photos",
    }
    assert len(project["photos"]) == 2
    assert project["photos"][0]["geo_location"] is None

    assert (project_path.parent / "photos" / "photo1.jpg").is_file()
    assert (project_path.parent / "photos" / "photo2.jpg").is_file()

    assert not prepared_path.exists()
    assert not importing_path.exists()
    assert not (staging / "photos").exists()


def test_finalize_project_uses_unique_directory_name(project_staging):
    workspace, _, prepared_path, _ = project_staging

    (workspace / "Test Event").mkdir()

    project_path = finalize_project(prepared_path)

    assert project_path.parent.name == "Test Event (2)"
    assert project_path.is_file()


def test_finalize_project_rejects_missing_photo(project_staging):
    _, staging, prepared_path, importing_path = project_staging

    (staging / "photos" / "photo2.jpg").unlink()

    with pytest.raises(ProjectFinalizationError, match="missing"):
        finalize_project(prepared_path)

    assert prepared_path.is_file()
    assert importing_path.is_file()
    assert (staging / "photos" / "photo1.jpg").is_file()


def test_finalize_project_rejects_unsafe_filename(project_staging):
    _, _, prepared_path, importing_path = project_staging

    data = json.loads(prepared_path.read_text(encoding="utf-8"))
    data["photos"][0]["file"] = "../outside.jpg"
    prepared_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ProjectFinalizationError, match="invalid filename"):
        finalize_project(prepared_path)

    assert importing_path.is_file()


def test_finalize_project_rejects_undownloaded_photo(project_staging):
    _, _, prepared_path, importing_path = project_staging

    data = json.loads(prepared_path.read_text(encoding="utf-8"))
    data["photos"][0]["downloaded"] = False
    prepared_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ProjectFinalizationError, match="not marked as downloaded"):
        finalize_project(prepared_path)

    assert importing_path.is_file()


def test_finalize_project_rolls_back_when_final_rename_fails(
    project_staging,
    monkeypatch,
):
    workspace, staging, prepared_path, importing_path = project_staging

    original_rename = Path.rename

    def failing_rename(self, target):
        target = Path(target)

        if self.name == PREPARED_FILENAME and target.name == "project.json":
            raise OSError("Simulated final rename failure")

        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", failing_rename)

    with pytest.raises(ProjectFinalizationError, match="publication failed"):
        finalize_project(prepared_path)

    assert prepared_path.is_file()
    assert importing_path.is_file()
    assert (staging / "photos" / "photo1.jpg").is_file()
    assert (staging / "photos" / "photo2.jpg").is_file()

    # The destination directory created during the failed attempt is removed.
    assert not (workspace / "Test Event").exists()
