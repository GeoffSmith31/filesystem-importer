import json

import pytest

from filesystem_importer.checkpoint_writer import (
    write_recovery_checkpoint,
)


def test_write_recovery_checkpoint_creates_json_file(tmp_path):
    checkpoint_path = tmp_path / "importing.json"
    checkpoint = {
        "workspace": {"event": "Test Event"},
        "photos": [],
    }

    write_recovery_checkpoint(checkpoint_path, checkpoint)

    assert json.loads(
        checkpoint_path.read_text(encoding="utf-8")
    ) == checkpoint


def test_write_recovery_checkpoint_replaces_existing_file(tmp_path):
    checkpoint_path = tmp_path / "importing.json"
    checkpoint_path.write_text(
        '{"old": true}\n',
        encoding="utf-8",
    )
    checkpoint = {"new": True, "photos": []}

    write_recovery_checkpoint(checkpoint_path, checkpoint)

    assert json.loads(
        checkpoint_path.read_text(encoding="utf-8")
    ) == checkpoint


def test_write_recovery_checkpoint_preserves_old_file_on_serialization_failure(
    tmp_path,
):
    checkpoint_path = tmp_path / "importing.json"
    original_content = '{"previous": "checkpoint"}\n'
    checkpoint_path.write_text(original_content, encoding="utf-8")

    invalid_checkpoint = {"invalid": object()}

    with pytest.raises(TypeError):
        write_recovery_checkpoint(checkpoint_path, invalid_checkpoint)

    assert checkpoint_path.read_text(encoding="utf-8") == original_content
