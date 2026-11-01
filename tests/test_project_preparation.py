import json

import pytest

from filesystem_importer.constants import (
    CHECKPOINT_FILENAME,
    PREPARED_FILENAME,
)
from filesystem_importer.project_preparation import (
    build_prepared_project,
    prepare_project_json,
)


def make_photo(guid, downloaded):
    return {
        "guid": guid,
        "moment_id": "Test Folder",
        "lat": None,
        "lng": None,
        "file": f"{guid}.jpg" if downloaded else "",
        "downloaded": downloaded,
        "retry_count": 0,
        "status": "pending",
        "exif_written": False,
        "last_updated": "2026-10-31T00:00:00.000Z",
        "location_key": None,
        "geo_location": None,
        "event": "Test Event",
        "year": "2024",
        "location": "",
        "info": "",
    }


def make_checkpoint(photos, candidate_count=None):
    if candidate_count is None:
        candidate_count = len(photos)

    return {
        "workspace": {
            "event": "Test Event",
            "registration_status": "NOT_STARTED",
            "download_status": "NOT_STARTED",
        },
        "metadata_policies": {
            "event": {},
            "year": {},
            "location": {},
            "info": {},
        },
        "photos": photos,
        "filesystem_importer": {
            "source_manifest": {
                "candidate_count": candidate_count,
            },
            "directory_classifications": {},
        },
    }


def test_preparation_removes_failed_records_and_importer_data(
    tmp_path,
):
    checkpoint = make_checkpoint([
        make_photo("photo-1", True),
        make_photo("photo-2", False),
        make_photo("photo-3", True),
    ])

    checkpoint_path = tmp_path / CHECKPOINT_FILENAME
    original_text = json.dumps(checkpoint, indent=4)
    checkpoint_path.write_text(original_text, encoding="utf-8")

    prepared_path = prepare_project_json(checkpoint_path)

    assert prepared_path == tmp_path / PREPARED_FILENAME
    assert prepared_path.is_file()

    prepared = json.loads(
        prepared_path.read_text(encoding="utf-8")
    )

    assert set(prepared) == {
        "workspace",
        "metadata_policies",
        "photos",
    }

    # The prepared project must mark both import phases complete.
    assert prepared["workspace"]["registration_status"] == "COMPLETE"
    assert prepared["workspace"]["download_status"] == "COMPLETE"

    assert len(prepared["photos"]) == 2

    assert [
        photo["guid"] for photo in prepared["photos"]
    ] == ["photo-1", "photo-3"]

    assert all(
        photo["downloaded"] is True
        for photo in prepared["photos"]
    )

    # The original recovery checkpoint must remain unchanged.
    assert checkpoint_path.read_text(encoding="utf-8") == original_text

    # The original checkpoint must retain its original status values.
    original = json.loads(
        checkpoint_path.read_text(encoding="utf-8")
    )

    assert original["workspace"]["registration_status"] == "NOT_STARTED"
    assert original["workspace"]["download_status"] == "NOT_STARTED"

    # The temporary write file must not remain.
    assert not (tmp_path / ".prepared.json.tmp").exists()


def test_preparation_rejects_incomplete_import():
    checkpoint = make_checkpoint(
        photos=[
            make_photo("photo-1", True),
        ],
        candidate_count=2,
    )

    with pytest.raises(ValueError, match="incomplete"):
        build_prepared_project(checkpoint)


def test_preparation_rejects_invalid_downloaded_value():
    checkpoint = make_checkpoint([
        make_photo("photo-1", True),
        {
            **make_photo("photo-2", False),
            "downloaded": "false",
        },
    ])

    with pytest.raises(ValueError, match="downloaded"):
        build_prepared_project(checkpoint)


def test_preparation_rejects_project_with_no_successful_photos():
    checkpoint = make_checkpoint([
        make_photo("photo-1", False),
        make_photo("photo-2", False),
    ])

    with pytest.raises(ValueError, match="No photos"):
        build_prepared_project(checkpoint)


def test_preparation_overwrites_previous_prepared_file(tmp_path):
    checkpoint = make_checkpoint([
        make_photo("photo-1", True),
    ])

    checkpoint_path = tmp_path / CHECKPOINT_FILENAME
    checkpoint_path.write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )

    prepared_path = tmp_path / PREPARED_FILENAME
    prepared_path.write_text("old contents", encoding="utf-8")

    prepare_project_json(checkpoint_path)

    prepared = json.loads(
        prepared_path.read_text(encoding="utf-8")
    )

    assert len(prepared["photos"]) == 1
    assert prepared["photos"][0]["guid"] == "photo-1"
