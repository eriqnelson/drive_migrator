from unittest.mock import MagicMock

import pytest

from drive_migrator.migrator_engine import (
    DriveMigrator,
    DRIVE_SCOPE,
)


def make_migrator_without_init(
    tmp_path,
    credentials_path=None,
):
    """
    Build a DriveMigrator instance without invoking __init__.

    This lets authentication behavior be tested in isolation.
    """
    migrator = DriveMigrator.__new__(
        DriveMigrator
    )

    migrator.state_dir = tmp_path
    migrator.token_path = (
        tmp_path / "token.json"
    )
    migrator.work_list_path = (
        tmp_path
        / "migration_work_list.json"
    )
    migrator.log_path = (
        tmp_path / "migration.log"
    )

    migrator.creds_path = (
        credentials_path
    )

    migrator.log_message = MagicMock()

    return migrator


def test_auth_uses_existing_valid_token(
    monkeypatch,
    tmp_path,
):
    token_path = (
        tmp_path / "token.json"
    )

    token_path.write_text(
        "{}",
        encoding="utf-8",
    )

    fake_creds = MagicMock()
    fake_creds.valid = True

    credentials_loader = MagicMock(
        return_value=fake_creds
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine."
        "Credentials.from_authorized_user_file",
        credentials_loader,
    )

    fake_service = MagicMock()

    build_mock = MagicMock(
        return_value=fake_service
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine.build",
        build_mock,
    )

    migrator = make_migrator_without_init(
        tmp_path
    )

    result = migrator._authenticate()

    assert result is fake_service

    credentials_loader.assert_called_once_with(
        str(token_path),
        scopes=[DRIVE_SCOPE],
    )

    build_mock.assert_called_once_with(
        "drive",
        "v3",
        credentials=fake_creds,
    )


def test_auth_refreshes_expired_token(
    monkeypatch,
    tmp_path,
):
    token_path = (
        tmp_path / "token.json"
    )

    token_path.write_text(
        "{}",
        encoding="utf-8",
    )

    fake_creds = MagicMock()
    fake_creds.valid = False
    fake_creds.expired = True
    fake_creds.refresh_token = "REFRESH"

    fake_creds.to_json.return_value = (
        '{"token": "new"}'
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine."
        "Credentials.from_authorized_user_file",
        MagicMock(
            return_value=fake_creds
        ),
    )

    fake_request = MagicMock()

    request_class = MagicMock(
        return_value=fake_request
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine.Request",
        request_class,
    )

    fake_service = MagicMock()

    build_mock = MagicMock(
        return_value=fake_service
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine.build",
        build_mock,
    )

    migrator = make_migrator_without_init(
        tmp_path
    )

    result = migrator._authenticate()

    assert result is fake_service

    fake_creds.refresh.assert_called_once_with(
        fake_request
    )

    assert (
        token_path.read_text(
            encoding="utf-8"
        )
        == '{"token": "new"}'
    )


def test_auth_logs_token_load_failure(
    monkeypatch,
    tmp_path,
):
    token_path = (
        tmp_path / "token.json"
    )

    token_path.write_text(
        "broken",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine."
        "Credentials.from_authorized_user_file",
        MagicMock(
            side_effect=ValueError(
                "Invalid token"
            )
        ),
    )

    migrator = make_migrator_without_init(
        tmp_path
    )

    with pytest.raises(
        RuntimeError,
        match="OAuth credentials are required",
    ):
        migrator._authenticate()

    migrator.log_message.assert_called()

    logged = (
        migrator.log_message.call_args[0][0]
    )

    assert (
        "Unable to load existing OAuth token"
        in logged
    )


def test_auth_logs_refresh_failure_and_falls_back_to_oauth(
    monkeypatch,
    tmp_path,
):
    token_path = (
        tmp_path / "token.json"
    )

    token_path.write_text(
        "{}",
        encoding="utf-8",
    )

    credentials_path = (
        tmp_path / "credentials.json"
    )

    credentials_path.write_text(
        "{}",
        encoding="utf-8",
    )

    expired_creds = MagicMock()
    expired_creds.valid = False
    expired_creds.expired = True
    expired_creds.refresh_token = "REFRESH"

    expired_creds.refresh.side_effect = (
        RuntimeError(
            "Refresh failed"
        )
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine."
        "Credentials.from_authorized_user_file",
        MagicMock(
            return_value=expired_creds
        ),
    )

    new_creds = MagicMock()
    new_creds.to_json.return_value = (
        '{"token": "new"}'
    )

    flow = MagicMock()
    flow.run_local_server.return_value = (
        new_creds
    )

    flow_factory = MagicMock(
        return_value=flow
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine."
        "InstalledAppFlow.from_client_secrets_file",
        flow_factory,
    )

    fake_service = MagicMock()

    monkeypatch.setattr(
        "drive_migrator.migrator_engine.build",
        MagicMock(
            return_value=fake_service
        ),
    )

    migrator = make_migrator_without_init(
        tmp_path,
        credentials_path=credentials_path,
    )

    result = migrator._authenticate()

    assert result is fake_service

    assert any(
        "OAuth token refresh failed"
        in call.args[0]
        for call
        in migrator.log_message.call_args_list
    )

    flow_factory.assert_called_once_with(
        str(credentials_path),
        scopes=[DRIVE_SCOPE],
    )

    flow.run_local_server.assert_called_once_with(
        port=0
    )


def test_auth_requires_credentials_for_initial_authorization(
    tmp_path,
):
    migrator = make_migrator_without_init(
        tmp_path,
        credentials_path=None,
    )

    with pytest.raises(
        RuntimeError,
        match="OAuth credentials are required",
    ):
        migrator._authenticate()


def test_auth_rejects_missing_credentials_file(
    tmp_path,
):
    missing_path = (
        tmp_path
        / "missing-credentials.json"
    )

    migrator = make_migrator_without_init(
        tmp_path,
        credentials_path=missing_path,
    )

    with pytest.raises(
        FileNotFoundError,
        match="credentials file not found",
    ):
        migrator._authenticate()


def test_auth_runs_initial_oauth_flow(
    monkeypatch,
    tmp_path,
):
    credentials_path = (
        tmp_path / "credentials.json"
    )

    credentials_path.write_text(
        "{}",
        encoding="utf-8",
    )

    new_creds = MagicMock()
    new_creds.to_json.return_value = (
        '{"token": "authorized"}'
    )

    flow = MagicMock()
    flow.run_local_server.return_value = (
        new_creds
    )

    flow_factory = MagicMock(
        return_value=flow
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine."
        "InstalledAppFlow.from_client_secrets_file",
        flow_factory,
    )

    fake_service = MagicMock()

    build_mock = MagicMock(
        return_value=fake_service
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine.build",
        build_mock,
    )

    migrator = make_migrator_without_init(
        tmp_path,
        credentials_path=credentials_path,
    )

    result = migrator._authenticate()

    assert result is fake_service

    flow_factory.assert_called_once_with(
        str(credentials_path),
        scopes=[DRIVE_SCOPE],
    )

    flow.run_local_server.assert_called_once_with(
        port=0
    )

    assert (
        migrator.token_path.read_text(
            encoding="utf-8"
        )
        == '{"token": "authorized"}'
    )

    build_mock.assert_called_once_with(
        "drive",
        "v3",
        credentials=new_creds,
    )


def test_auth_prefers_existing_valid_token_over_credentials_file(
    monkeypatch,
    tmp_path,
):
    token_path = (
        tmp_path / "token.json"
    )

    token_path.write_text(
        "{}",
        encoding="utf-8",
    )

    credentials_path = (
        tmp_path / "credentials.json"
    )

    credentials_path.write_text(
        "{}",
        encoding="utf-8",
    )

    valid_creds = MagicMock()
    valid_creds.valid = True

    monkeypatch.setattr(
        "drive_migrator.migrator_engine."
        "Credentials.from_authorized_user_file",
        MagicMock(
            return_value=valid_creds
        ),
    )

    flow_factory = MagicMock()

    monkeypatch.setattr(
        "drive_migrator.migrator_engine."
        "InstalledAppFlow.from_client_secrets_file",
        flow_factory,
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine.build",
        MagicMock(
            return_value=MagicMock()
        ),
    )

    migrator = make_migrator_without_init(
        tmp_path,
        credentials_path=credentials_path,
    )

    migrator._authenticate()

    flow_factory.assert_not_called()


def test_auth_does_not_attempt_refresh_without_refresh_token(
    monkeypatch,
    tmp_path,
):
    token_path = (
        tmp_path / "token.json"
    )

    token_path.write_text(
        "{}",
        encoding="utf-8",
    )

    credentials_path = (
        tmp_path / "credentials.json"
    )

    credentials_path.write_text(
        "{}",
        encoding="utf-8",
    )

    expired_creds = MagicMock()
    expired_creds.valid = False
    expired_creds.expired = True
    expired_creds.refresh_token = None

    monkeypatch.setattr(
        "drive_migrator.migrator_engine."
        "Credentials.from_authorized_user_file",
        MagicMock(
            return_value=expired_creds
        ),
    )

    new_creds = MagicMock()
    new_creds.to_json.return_value = "{}"

    flow = MagicMock()
    flow.run_local_server.return_value = (
        new_creds
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine."
        "InstalledAppFlow.from_client_secrets_file",
        MagicMock(
            return_value=flow
        ),
    )

    monkeypatch.setattr(
        "drive_migrator.migrator_engine.build",
        MagicMock(
            return_value=MagicMock()
        ),
    )

    migrator = make_migrator_without_init(
        tmp_path,
        credentials_path=credentials_path,
    )

    migrator._authenticate()

    expired_creds.refresh.assert_not_called()

    flow.run_local_server.assert_called_once_with(
        port=0
    )