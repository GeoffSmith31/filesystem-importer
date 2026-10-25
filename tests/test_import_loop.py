
"""Tests for the filesystem importing loop."""

from pathlib import Path

import pytest
from unittest.mock import patch

from filesystem_importer.photo_staging import (
    PhotoStagingResult,
    StagingFatalError,
)

from filesystem_importer.import_loop import (
    stage_candidate,
    initialise_progress,
    process_candidate,
    run_import_loop,
    save_recovery_checkpoint,
    update_progress_display,
    build_failed_photo_record,
    build_photo_record,
)


def test_build_failed_photo_record_contains_required_fields(tmp_path):
    source_path = tmp_path / "source.jpg"
    record = build_failed_photo_record(source_path, "Test Event")

    assert record["guid"] == str(source_path.resolve())
    assert record["downloaded"] is False
    assert record["file"] == ""
    assert record["status"] == "pending"
    assert record["event"] == "Test Event"
    assert record["year"] == ""
    assert record["location"] == ""
    assert record["info"] == ""
    assert record["last_updated"].endswith("Z")


def test_process_candidate_creates_record_only_on_failure(tmp_path):
    source = tmp_path / "source.jpg"
    photos = tmp_path / "photos"
    source.touch()
    photos.mkdir()

    with patch(
        "filesystem_importer.import_loop.stage_candidate",
        return_value=PhotoStagingResult(
            success=False,
            reason="EXIF test failed",
        ),
    ):
        record = process_candidate(source, photos, "Test Event")

    assert record is not None
    assert record["downloaded"] is False
    assert record["file"] == ""


def test_process_candidate_does_not_create_record_on_success(tmp_path):
    source = tmp_path / "source.jpg"
    photos = tmp_path / "photos"
    source.touch()
    photos.mkdir()

    with patch(
        "filesystem_importer.import_loop.stage_candidate",
        return_value=PhotoStagingResult(
            success=True,
            staged_filename="source.jpg",
        ),
    ):
        record = process_candidate(source, photos, "Test Event")

    assert record is None


def test_process_candidate_propagates_fatal_staging_error(tmp_path):
    source = tmp_path / "source.jpg"
    photos = tmp_path / "photos"
    source.touch()
    photos.mkdir()

    with patch(
        "filesystem_importer.import_loop.stage_candidate",
        side_effect=StagingFatalError("Could not delete staged copy."),
    ):
        with pytest.raises(StagingFatalError):
            process_candidate(source, photos, "Test Event")



def test_stage_candidate_calls_existing_staging_and_exif_test(tmp_path):
    source = tmp_path / "source.jpg"
    photos = tmp_path / "photos"
    source.touch()
    photos.mkdir()

    with patch(
        "filesystem_importer.import_loop.stage_and_test_photo",
        return_value=PhotoStagingResult(
            success=True,
            staged_filename="source.jpg",
        ),
    ) as staging:
        result = stage_candidate(source, photos)

    assert result.success is True
    assert result.staged_filename == "source.jpg"


def test_stage_candidate_returns_false_when_exif_test_fails(tmp_path):
    source = tmp_path / "source.jpg"
    photos = tmp_path / "photos"
    source.touch()
    photos.mkdir()

    with patch(
        "filesystem_importer.import_loop.stage_and_test_photo",
        return_value=PhotoStagingResult(
            success=False,
            reason="EXIF UserComment is not supported.",
        ),
    ) as staging:
        result = stage_candidate(source, photos)

    assert result.success is False
    assert result.reason == "EXIF UserComment is not supported."


def test_stage_candidate_propagates_fatal_staging_error(tmp_path):
    source = tmp_path / "source.jpg"
    photos = tmp_path / "photos"
    source.touch()
    photos.mkdir()

    with patch(
        "filesystem_importer.import_loop.stage_and_test_photo",
        side_effect=StagingFatalError("Could not delete staged copy."),
    ):
        with pytest.raises(StagingFatalError):
            stage_candidate(source, photos)


def test_initialise_progress_with_no_processed_photos():
    checkpoint = {
        "filesystem_importer": {
            "source_manifest": {"candidate_count": 10}
        },
        "photos": [],
    }

    progress = initialise_progress(checkpoint)

    assert progress.total == 10
    assert progress.processed == 0
    assert progress.successful == 0
    assert progress.failed == 0
    assert progress.remaining == 10


def test_initialise_progress_counts_successes_and_failures():
    checkpoint = {
        "filesystem_importer": {
            "source_manifest": {"candidate_count": 5}
        },
        "photos": [
            {"downloaded": True},
            {"downloaded": False},
            {"downloaded": True},
        ],
    }

    progress = initialise_progress(checkpoint)

    assert progress.total == 5
    assert progress.processed == 3
    assert progress.successful == 2
    assert progress.failed == 1
    assert progress.remaining == 2


def test_initialise_progress_when_all_candidates_are_processed():
    checkpoint = {
        "filesystem_importer": {
            "source_manifest": {"candidate_count": 2}
        },
        "photos": [
            {"downloaded": True},
            {"downloaded": False},
        ],
    }

    progress = initialise_progress(checkpoint)

    assert progress.total == 2
    assert progress.processed == 2
    assert progress.successful == 1
    assert progress.failed == 1
    assert progress.remaining == 0


@pytest.mark.parametrize(
    "checkpoint",
    [
        {},
        {
            "filesystem_importer": {
                "source_manifest": {"candidate_count": -1}
            },
            "photos": [],
        },
        {
            "filesystem_importer": {
                "source_manifest": {"candidate_count": 1}
            },
            "photos": [{"downloaded": "false"}],
        },
        {
            "filesystem_importer": {
                "source_manifest": {"candidate_count": 1}
            },
            "photos": [{"downloaded": True}, {"downloaded": False}],
        },
    ],
)
def test_initialise_progress_rejects_invalid_checkpoint(checkpoint):
    with pytest.raises(ValueError):
        initialise_progress(checkpoint)



def test_process_candidate_requires_event_name():
    with pytest.raises(TypeError):
        process_candidate(
            Path("/source/photo.jpg"),
            Path("/staging/photos"),
        )


def test_update_progress_display_is_not_implemented_yet():
    with pytest.raises(NotImplementedError):
        update_progress_display(None)


def test_save_recovery_checkpoint_writes_checkpoint(tmp_path):
    checkpoint_path = tmp_path / "importing.json"
    checkpoint = {"photos": []}

    with patch(
        "filesystem_importer.import_loop.write_recovery_checkpoint"
    ) as mock_writer:
        save_recovery_checkpoint(
            checkpoint=checkpoint,
            checkpoint_path=checkpoint_path,
        )

    mock_writer.assert_called_once_with(
        checkpoint_path=checkpoint_path,
        checkpoint=checkpoint,
    )


def test_run_import_loop_rejects_invalid_checkpoint(tmp_path):
    with pytest.raises(ValueError, match="missing required progress data"):
        run_import_loop(
            checkpoint={},
            candidate_paths=[],
            photos_directory=Path("/staging/photos"),
            checkpoint_path=tmp_path / "importing.json",
        )
def test_run_import_loop_records_failed_candidate_and_saves_checkpoint(
    tmp_path,
):
    checkpoint = {
        "workspace": {"event": "Test Event"},
        "filesystem_importer": {
            "source_manifest": {"candidate_count": 1},
        },
        "photos": [],
    }
    candidate = tmp_path / "failed.jpg"
    photos_directory = tmp_path / "photos"
    photos_directory.mkdir()

    failed_record = {
        "guid": str(candidate.resolve()),
        "downloaded": False,
        "file": "",
    }

    with (
        patch(
            "filesystem_importer.import_loop.process_candidate",
            return_value=failed_record,
        ) as mock_process,
        patch(
            "filesystem_importer.import_loop.update_progress_display",
        ) as mock_display,
        patch(
            "filesystem_importer.import_loop.save_recovery_checkpoint",
        ) as mock_save,
    ):
        progress = run_import_loop(
            checkpoint=checkpoint,
            candidate_paths=[candidate],
            photos_directory=photos_directory,
            checkpoint_path=tmp_path / "importing.json",
        )

    assert checkpoint["photos"] == [failed_record]
    assert progress.total == 1
    assert progress.processed == 1
    assert progress.successful == 0
    assert progress.failed == 1
    assert progress.remaining == 0

    mock_process.assert_called_once_with(
        source_path=candidate,
        photos_directory=photos_directory,
        event_name="Test Event",
    )
    mock_display.assert_called()
    mock_save.assert_called_once_with(
        checkpoint=checkpoint,
        checkpoint_path=tmp_path / "importing.json",
    )
    
def test_run_import_loop_skips_already_processed_candidates(tmp_path):
    candidates = [
        tmp_path / "first.jpg",
        tmp_path / "second.jpg",
        tmp_path / "third.jpg",
    ]

    first_record = {
        "guid": str(candidates[0].resolve()),
        "downloaded": False,
        "file": "",
    }

    checkpoint = {
        "workspace": {"event": "Test Event"},
        "filesystem_importer": {
            "source_manifest": {"candidate_count": 3},
        },
        "photos": [first_record],
    }

    photos_directory = tmp_path / "photos"
    photos_directory.mkdir()

    second_record = {
        "guid": str(candidates[1].resolve()),
        "downloaded": False,
        "file": "",
    }
    third_record = {
        "guid": str(candidates[2].resolve()),
        "downloaded": False,
        "file": "",
    }

    with (
        patch(
            "filesystem_importer.import_loop.process_candidate",
            side_effect=[second_record, third_record],
        ) as mock_process,
        patch(
            "filesystem_importer.import_loop.update_progress_display",
        ),
        patch(
            "filesystem_importer.import_loop.save_recovery_checkpoint",
        ) as mock_save,
    ):
        progress = run_import_loop(
            checkpoint=checkpoint,
            candidate_paths=candidates,
            photos_directory=photos_directory,
            checkpoint_path=tmp_path / "importing.json",
        )

    assert [record["guid"] for record in checkpoint["photos"]] == [
        str(candidate.resolve()) for candidate in candidates
    ]
    assert progress.processed == 3
    assert progress.failed == 3
    assert progress.remaining == 0

    assert mock_process.call_count == 2
    assert mock_process.call_args_list[0].kwargs["source_path"] == candidates[1]
    assert mock_process.call_args_list[1].kwargs["source_path"] == candidates[2]
    assert mock_save.call_count == 2
    
def test_run_import_loop_stops_when_successful_candidate_needs_metadata(
    tmp_path,
):
    candidate = tmp_path / "successful.jpg"
    photos_directory = tmp_path / "photos"
    photos_directory.mkdir()

    checkpoint = {
        "workspace": {"event": "Test Event"},
        "filesystem_importer": {
            "source_manifest": {"candidate_count": 1},
        },
        "photos": [],
    }

    with (
        patch(
            "filesystem_importer.import_loop.process_candidate",
            return_value=None,
        ) as mock_process,
        patch(
            "filesystem_importer.import_loop.update_progress_display",
        ),
        patch(
            "filesystem_importer.import_loop.save_recovery_checkpoint",
        ) as mock_save,
    ):
        with pytest.raises(
            NotImplementedError,
            match="Metadata resolution is not implemented",
        ):
            run_import_loop(
                checkpoint=checkpoint,
                candidate_paths=[candidate],
                photos_directory=photos_directory,
                checkpoint_path=tmp_path / "importing.json",
            )

    assert checkpoint["photos"] == []
    mock_process.assert_called_once()
    mock_save.assert_not_called()
    
def test_build_photo_record_contains_all_required_fields(tmp_path):
    source_path = tmp_path / "photo.jpg"

    record = build_photo_record(
        source_path=source_path,
        downloaded=False,
        file="",
        event="Test Event",
    )

    assert set(record) == {
        "guid",
        "moment_id",
        "lat",
        "lng",
        "file",
        "downloaded",
        "retry_count",
        "status",
        "exif_written",
        "last_updated",
        "location_key",
        "geo_location",
        "event",
        "year",
        "location",
        "info",
    }


def test_build_photo_record_uses_defaults(tmp_path):
    source_path = tmp_path / "photo.jpg"

    record = build_photo_record(
        source_path=source_path,
        downloaded=False,
        file="",
        event="Test Event",
    )

    assert record["guid"] == str(source_path.resolve())
    assert record["moment_id"] == ""
    assert record["lat"] is None
    assert record["lng"] is None
    assert record["retry_count"] == 0
    assert record["status"] == "pending"
    assert record["exif_written"] is False
    assert record["location_key"] is None
    assert record["geo_location"] is None
    assert record["event"] == "Test Event"
    assert record["year"] == ""
    assert record["location"] == ""
    assert record["info"] == ""


def test_build_photo_record_uses_supplied_values(tmp_path):
    source_path = tmp_path / "photo.jpg"

    record = build_photo_record(
        source_path=source_path,
        downloaded=True,
        file="photo_2.jpg",
        event="Holiday",
        moment_id="moment-123",
        lat=-27.47,
        lng=153.03,
        retry_count=1,
        status="downloaded",
        exif_written=True,
        location_key="brisbane",
        geo_location="Brisbane, Queensland",
        year="2026",
        location="Brisbane",
        info="Family trip",
    )

    assert record["downloaded"] is True
    assert record["file"] == "photo_2.jpg"
    assert record["moment_id"] == "moment-123"
    assert record["lat"] == -27.47
    assert record["lng"] == 153.03
    assert record["retry_count"] == 1
    assert record["status"] == "downloaded"
    assert record["exif_written"] is True
    assert record["location_key"] == "brisbane"
    assert record["geo_location"] == "Brisbane, Queensland"
    assert record["event"] == "Holiday"
    assert record["year"] == "2026"
    assert record["location"] == "Brisbane"
    assert record["info"] == "Family trip"


def test_build_photo_record_timestamp_is_utc_iso_format(tmp_path):
    from datetime import datetime

    source_path = tmp_path / "photo.jpg"

    record = build_photo_record(
        source_path=source_path,
        downloaded=False,
        file="",
        event="Test Event",
    )

    timestamp = record["last_updated"]

    assert timestamp.endswith("Z")
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
