from pathlib import Path

import pytest

from drive_migrator import config


# ----------------------------------------------------------------------
# Default state directory
# ----------------------------------------------------------------------


def test_get_default_state_dir_uses_platformdirs(
    monkeypatch,
    tmp_path,
):
    expected = (
        tmp_path
        / "platform-data"
        / "drive-migrator"
    )

    monkeypatch.setattr(
        config,
        "user_data_path",
        lambda app_name, appauthor=False: expected,
    )

    result = (
        config.get_default_state_dir()
    )

    assert result == expected


def test_get_default_state_dir_passes_app_name(
    monkeypatch,
    tmp_path,
):
    calls = {}

    def fake_user_data_path(
        app_name,
        appauthor=False,
    ):
        calls["app_name"] = app_name
        calls["appauthor"] = appauthor

        return (
            tmp_path
            / "state"
        )

    monkeypatch.setattr(
        config,
        "user_data_path",
        fake_user_data_path,
    )

    config.get_default_state_dir()

    assert (
        calls["app_name"]
        == config.APP_NAME
    )

    assert (
        calls["appauthor"]
        is False
    )


# ----------------------------------------------------------------------
# State directory resolution
# ----------------------------------------------------------------------


def test_resolve_state_dir_uses_explicit_override(
    monkeypatch,
    tmp_path,
):
    environment_path = (
        tmp_path
        / "environment"
    )

    override_path = (
        tmp_path
        / "override"
    )

    monkeypatch.setenv(
        config.STATE_DIR_ENV,
        str(environment_path),
    )

    result = config.resolve_state_dir(
        str(override_path)
    )

    assert (
        result
        == override_path.resolve()
    )

    assert result.exists()
    assert result.is_dir()


def test_resolve_state_dir_uses_environment_variable(
    monkeypatch,
    tmp_path,
):
    state_path = (
        tmp_path
        / "environment-state"
    )

    monkeypatch.setenv(
        config.STATE_DIR_ENV,
        str(state_path),
    )

    result = (
        config.resolve_state_dir()
    )

    assert (
        result
        == state_path.resolve()
    )

    assert result.exists()
    assert result.is_dir()


def test_resolve_state_dir_uses_default_when_unconfigured(
    monkeypatch,
    tmp_path,
):
    default_path = (
        tmp_path
        / "default-state"
    )

    monkeypatch.delenv(
        config.STATE_DIR_ENV,
        raising=False,
    )

    monkeypatch.setattr(
        config,
        "get_default_state_dir",
        lambda: default_path,
    )

    result = (
        config.resolve_state_dir()
    )

    assert (
        result
        == default_path.resolve()
    )

    assert result.exists()
    assert result.is_dir()


def test_resolve_state_dir_creates_missing_directory(
    monkeypatch,
    tmp_path,
):
    state_path = (
        tmp_path
        / "nested"
        / "state"
        / "directory"
    )

    assert (
        state_path.exists()
        is False
    )

    result = config.resolve_state_dir(
        str(state_path)
    )

    assert result.exists()
    assert result.is_dir()


def test_resolve_state_dir_accepts_existing_directory(
    tmp_path,
):
    state_path = (
        tmp_path
        / "existing"
    )

    state_path.mkdir()

    result = config.resolve_state_dir(
        str(state_path)
    )

    assert (
        result
        == state_path.resolve()
    )


def test_resolve_state_dir_expands_home_directory(
    monkeypatch,
    tmp_path,
):
    fake_home = (
        tmp_path
        / "home"
    )

    fake_home.mkdir()

    monkeypatch.setattr(
        Path,
        "home",
        lambda: fake_home,
    )

    # Path.expanduser() does not use Path.home()
    # consistently on every Python/platform combination,
    # so HOME is set explicitly as well.
    monkeypatch.setenv(
        "HOME",
        str(fake_home),
    )

    result = config.resolve_state_dir(
        "~/drive-migrator-state"
    )

    assert (
        result
        == (
            fake_home
            / "drive-migrator-state"
        ).resolve()
    )


def test_resolve_state_dir_override_beats_environment(
    monkeypatch,
    tmp_path,
):
    environment_path = (
        tmp_path
        / "from-env"
    )

    override_path = (
        tmp_path
        / "from-cli"
    )

    monkeypatch.setenv(
        config.STATE_DIR_ENV,
        str(environment_path),
    )

    result = config.resolve_state_dir(
        str(override_path)
    )

    assert (
        result
        == override_path.resolve()
    )

    assert (
        result
        != environment_path.resolve()
    )


# ----------------------------------------------------------------------
# Credentials path resolution
# ----------------------------------------------------------------------


def test_resolve_credentials_path_uses_override(
    monkeypatch,
    tmp_path,
):
    environment_file = (
        tmp_path
        / "environment.json"
    )

    override_file = (
        tmp_path
        / "override.json"
    )

    monkeypatch.setenv(
        config.CREDENTIALS_ENV,
        str(environment_file),
    )

    result = (
        config.resolve_credentials_path(
            str(override_file)
        )
    )

    assert (
        result
        == override_file.resolve()
    )


def test_resolve_credentials_path_uses_environment_variable(
    monkeypatch,
    tmp_path,
):
    credentials_file = (
        tmp_path
        / "credentials.json"
    )

    monkeypatch.setenv(
        config.CREDENTIALS_ENV,
        str(credentials_file),
    )

    result = (
        config.resolve_credentials_path()
    )

    assert (
        result
        == credentials_file.resolve()
    )


def test_resolve_credentials_path_returns_none_when_unconfigured(
    monkeypatch,
):
    monkeypatch.delenv(
        config.CREDENTIALS_ENV,
        raising=False,
    )

    result = (
        config.resolve_credentials_path()
    )

    assert result is None


def test_credentials_override_beats_environment(
    monkeypatch,
    tmp_path,
):
    environment_file = (
        tmp_path
        / "environment.json"
    )

    override_file = (
        tmp_path
        / "override.json"
    )

    monkeypatch.setenv(
        config.CREDENTIALS_ENV,
        str(environment_file),
    )

    result = (
        config.resolve_credentials_path(
            str(override_file)
        )
    )

    assert (
        result
        == override_file.resolve()
    )

    assert (
        result
        != environment_file.resolve()
    )


def test_resolve_credentials_path_expands_home(
    monkeypatch,
    tmp_path,
):
    fake_home = (
        tmp_path
        / "home"
    )

    fake_home.mkdir()

    monkeypatch.setenv(
        "HOME",
        str(fake_home),
    )

    result = (
        config.resolve_credentials_path(
            "~/credentials.json"
        )
    )

    assert (
        result
        == (
            fake_home
            / "credentials.json"
        ).resolve()
    )


def test_resolve_credentials_path_does_not_require_file_to_exist(
    tmp_path,
):
    """
    Config resolution only resolves the requested path.

    File existence is checked later by DriveMigrator when an OAuth
    authorization flow is actually required.
    """
    credentials_file = (
        tmp_path
        / "does-not-exist.json"
    )

    result = (
        config.resolve_credentials_path(
            str(credentials_file)
        )
    )

    assert (
        result
        == credentials_file.resolve()
    )

    assert (
        result.exists()
        is False
    )


# ----------------------------------------------------------------------
# Environment constant sanity checks
# ----------------------------------------------------------------------


def test_state_directory_environment_variable_name():
    assert (
        config.STATE_DIR_ENV
        == "DRIVE_MIGRATOR_STATE_DIR"
    )


def test_credentials_environment_variable_name():
    assert (
        config.CREDENTIALS_ENV
        == "DRIVE_MIGRATOR_CREDENTIALS"
    )


def test_application_name():
    assert (
        config.APP_NAME
        == "drive-migrator"
    )