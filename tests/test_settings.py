
import json

import pytest

from filesystem_importer.constants import (
    APP_NAME,
    APP_VERSION,
    DEVELOPER_EMAIL,
)
from filesystem_importer.settings import (
    AppSettings,
    DEFAULT_MINIMUM_REQUEST_INTERVAL_SECONDS,
    SETTINGS_VERSION,
    get_settings_path,
    load_settings,
    save_settings,
)


def test_defaults_have_one_second_interval():
    settings = AppSettings()

    assert (
        settings.minimum_request_interval_seconds
        == DEFAULT_MINIMUM_REQUEST_INTERVAL_SECONDS
        == 1.0
    )


def test_user_agent_uses_application_constants():
    settings = AppSettings()

    assert settings.user_agent == (
        f"{APP_NAME}/{APP_VERSION} (contact: {DEVELOPER_EMAIL})"
    )


def test_user_agent_is_not_empty():
    assert AppSettings().user_agent


def test_missing_settings_file_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"

    settings = load_settings(path)

    assert isinstance(settings, AppSettings)
    assert settings.minimum_request_interval_seconds == 1.0


def test_save_and_reload_settings(tmp_path):
    path = tmp_path / "settings.json"
    original = AppSettings(minimum_request_interval_seconds=1.5)

    save_settings(original, path)
    loaded = load_settings(path)

    assert loaded.minimum_request_interval_seconds == 1.5
    assert loaded.user_agent == original.user_agent


def test_saved_file_has_expected_structure(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(AppSettings(), path)

    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["version"] == SETTINGS_VERSION
    assert data["geocoding"]["minimum_request_interval_seconds"] == 1.0
    assert "contact_email" not in data["geocoding"]
    assert "user_agent" not in data["geocoding"]


def test_missing_interval_uses_default(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"version": SETTINGS_VERSION, "geocoding": {}}),
        encoding="utf-8",
    )

    settings = load_settings(path)

    assert settings.minimum_request_interval_seconds == 1.0


def test_invalid_json_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{invalid json", encoding="utf-8")

    settings = load_settings(path)

    assert settings.minimum_request_interval_seconds == 1.0


def test_unsupported_version_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"version": SETTINGS_VERSION + 1, "geocoding": {}}),
        encoding="utf-8",
    )

    settings = load_settings(path)

    assert settings.minimum_request_interval_seconds == 1.0


@pytest.mark.parametrize("interval", [0.0, 0.5, -1.0])
def test_interval_below_one_second_is_rejected(interval):
    settings = AppSettings(
        minimum_request_interval_seconds=interval,
    )

    with pytest.raises(ValueError):
        settings.validate()


@pytest.mark.parametrize("interval", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_interval_is_rejected(interval):
    settings = AppSettings(
        minimum_request_interval_seconds=interval,
    )

    with pytest.raises(ValueError):
        settings.validate()


def test_boolean_interval_is_rejected():
    settings = AppSettings(
        minimum_request_interval_seconds=True,
    )

    with pytest.raises(TypeError):
        settings.validate()


def test_non_numeric_interval_is_rejected():
    settings = AppSettings(
        minimum_request_interval_seconds="1",
    )

    with pytest.raises(TypeError):
        settings.validate()


def test_valid_interval_is_accepted():
    AppSettings(minimum_request_interval_seconds=1.5).validate()


def test_invalid_settings_are_not_saved(tmp_path):
    path = tmp_path / "settings.json"
    settings = AppSettings(minimum_request_interval_seconds=0.5)

    with pytest.raises(ValueError):
        save_settings(settings, path)

    assert not path.exists()


def test_default_settings_path():
    assert get_settings_path().name == "settings.json"
    assert get_settings_path().parent.name == "filesystem-importer"


def test_old_contact_email_key_is_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": SETTINGS_VERSION,
                "geocoding": {
                    "contact_email": "old@example.com",
                    "minimum_request_interval_seconds": 2.0,
                },
            }
        ),
        encoding="utf-8",
    )

    settings = load_settings(path)

    assert settings.minimum_request_interval_seconds == 2.0
    assert settings.user_agent == (
        f"{APP_NAME}/{APP_VERSION} (contact: {DEVELOPER_EMAIL})"
    )

