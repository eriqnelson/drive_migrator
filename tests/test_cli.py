import json
import sys
from unittest.mock import MagicMock

import pytest

from drive_migrator import cli


def run_cli(
    monkeypatch,
    args,
):
    """
    Execute cli.main() with controlled command-line arguments.
    """
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "drive-migrator",
            *args,
        ],
    )

    cli.main()


def write_manifest(
    tmp_path,
    manifest=None,
):
    """
    Write a minimal existing migration manifest.
    """
    if manifest is None:
        manifest = {
            "migration_metadata": {},
            "tasks": [],
        }

    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    return manifest_path


def make_cli_migrator(
    monkeypatch,
):
    fake_migrator = MagicMock()

    fake_migrator.generate_fresh_sync_manifest.return_value = {
        "tasks": []
    }

    fake_migrator.execute_migration.return_value = {
        "completed": 0,
        "failed": 0,
        "skipped": 0,
        "blocked": 0,
    }

    migrator_class = MagicMock(
        return_value=fake_migrator
    )

    monkeypatch.setattr(
        cli,
        "DriveMigrator",
        migrator_class,
    )

    return (
        migrator_class,
        fake_migrator,
    )


# ----------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------


def test_build_parser_program_name():
    parser = cli.build_parser()

    assert (
        parser.prog
        == "drive-migrator"
    )


def test_parser_defaults():
    parser = cli.build_parser()

    args = parser.parse_args([])

    assert args.credentials is None
    assert args.state_dir is None
    assert args.source is None
    assert args.destination is None

    assert (
        args.fresh
        is False
    )

    assert (
        args.manifest_only
        is False
    )

    assert (
        args.verify
        is False
    )

    assert (
        args.no_retry_failed
        is False
    )

    assert (
        args.resolve_destination_collisions
        is False
    )

    assert (
        args.verbose
        is False
    )


def test_parser_verbose_long_flag():
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "--verbose",
        ]
    )

    assert (
        args.verbose
        is True
    )


def test_parser_verbose_short_flag():
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "-v",
        ]
    )

    assert (
        args.verbose
        is True
    )


# ----------------------------------------------------------------------
# New manifest requirements
# ----------------------------------------------------------------------


def test_cli_requires_source_and_destination_for_new_manifest(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    make_cli_migrator(
        monkeypatch
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "drive-migrator",
        ],
    )

    with pytest.raises(
        SystemExit,
        match=(
            "--source and --destination "
            "are required"
        ),
    ):
        cli.main()


@pytest.mark.parametrize(
    "args",
    [
        [
            "--source",
            "SOURCE",
        ],
        [
            "--destination",
            "DEST",
        ],
        [
            "--source",
            "SOURCE",
            "--fresh",
        ],
        [
            "--destination",
            "DEST",
            "--fresh",
        ],
    ],
)
def test_cli_requires_both_source_and_destination(
    monkeypatch,
    tmp_path,
    args,
):
    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    make_cli_migrator(
        monkeypatch
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "drive-migrator",
            *args,
        ],
    )

    with pytest.raises(
        SystemExit,
        match=(
            "--source and --destination "
            "are required"
        ),
    ):
        cli.main()


# ----------------------------------------------------------------------
# Fresh manifest generation
# ----------------------------------------------------------------------


def test_cli_creates_fresh_manifest(
    monkeypatch,
    tmp_path,
    capsys,
):
    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    fake_migrator.generate_fresh_sync_manifest.return_value = {
        "tasks": [
            {
                "task_id": "TASK1"
            },
            {
                "task_id": "TASK2"
            },
        ]
    }

    fake_migrator.execute_migration.return_value = {
        "completed": 2,
        "failed": 0,
        "skipped": 0,
        "blocked": 0,
    }

    run_cli(
        monkeypatch,
        [
            "--credentials",
            "/tmp/credentials.json",
            "--source",
            "SOURCE",
            "--destination",
            "DEST",
            "--fresh",
        ],
    )

    fake_migrator.generate_fresh_sync_manifest.assert_called_once_with(
        "SOURCE",
        "DEST",
        resolve_destination_collisions=False,
    )

    fake_migrator.execute_migration.assert_called_once_with(
        retry_failed=True
    )

    output = (
        capsys.readouterr().out
    )

    assert (
        '"manifest_tasks": 2'
        in output
    )

    assert (
        '"completed": 2'
        in output
    )

    assert (
        '"blocked": 0'
        in output
    )


def test_cli_generates_new_manifest_without_explicit_fresh_when_none_exists(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--source",
            "SOURCE",
            "--destination",
            "DEST",
        ],
    )

    fake_migrator.generate_fresh_sync_manifest.assert_called_once_with(
        "SOURCE",
        "DEST",
        resolve_destination_collisions=False,
    )


def test_cli_rebuilds_existing_manifest_when_fresh_is_supplied(
    monkeypatch,
    tmp_path,
):
    write_manifest(
        tmp_path
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--source",
            "NEW_SOURCE",
            "--destination",
            "NEW_DEST",
            "--fresh",
        ],
    )

    fake_migrator.generate_fresh_sync_manifest.assert_called_once_with(
        "NEW_SOURCE",
        "NEW_DEST",
        resolve_destination_collisions=False,
    )


def test_cli_empty_manifest_is_treated_as_missing(
    monkeypatch,
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    manifest_path.touch()

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--source",
            "SOURCE",
            "--destination",
            "DEST",
        ],
    )

    fake_migrator.generate_fresh_sync_manifest.assert_called_once_with(
        "SOURCE",
        "DEST",
        resolve_destination_collisions=False,
    )


# ----------------------------------------------------------------------
# Destination collision resolution
# ----------------------------------------------------------------------


def test_cli_passes_destination_collision_resolution_flag(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--source",
            "SOURCE",
            "--destination",
            "DEST",
            "--fresh",
            "--resolve-destination-collisions",
        ],
    )

    fake_migrator.generate_fresh_sync_manifest.assert_called_once_with(
        "SOURCE",
        "DEST",
        resolve_destination_collisions=True,
    )


def test_cli_collision_resolution_requires_fresh_with_existing_manifest(
    monkeypatch,
    tmp_path,
):
    write_manifest(
        tmp_path
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "drive-migrator",
            "--resolve-destination-collisions",
        ],
    )

    with pytest.raises(
        SystemExit,
        match=(
            "--resolve-destination-collisions"
        ),
    ):
        cli.main()

    fake_migrator.generate_fresh_sync_manifest.assert_not_called()
    fake_migrator.execute_migration.assert_not_called()


def test_cli_collision_resolution_allowed_with_fresh_existing_manifest(
    monkeypatch,
    tmp_path,
):
    write_manifest(
        tmp_path
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--source",
            "SOURCE",
            "--destination",
            "DEST",
            "--fresh",
            "--resolve-destination-collisions",
        ],
    )

    fake_migrator.generate_fresh_sync_manifest.assert_called_once_with(
        "SOURCE",
        "DEST",
        resolve_destination_collisions=True,
    )


# ----------------------------------------------------------------------
# Manifest-only mode
# ----------------------------------------------------------------------


def test_cli_manifest_only_does_not_execute(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--source",
            "SOURCE",
            "--destination",
            "DEST",
            "--fresh",
            "--manifest-only",
        ],
    )

    fake_migrator.generate_fresh_sync_manifest.assert_called_once_with(
        "SOURCE",
        "DEST",
        resolve_destination_collisions=False,
    )

    fake_migrator.execute_migration.assert_not_called()
    fake_migrator.verify_destination.assert_not_called()


def test_cli_manifest_only_with_existing_manifest_exits_cleanly(
    monkeypatch,
    tmp_path,
):
    write_manifest(
        tmp_path
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--manifest-only",
        ],
    )

    fake_migrator.generate_fresh_sync_manifest.assert_not_called()
    fake_migrator.execute_migration.assert_not_called()
    fake_migrator.verify_destination.assert_not_called()


# ----------------------------------------------------------------------
# Existing manifest / resume behavior
# ----------------------------------------------------------------------


def test_cli_resumes_existing_manifest_without_source_or_destination(
    monkeypatch,
    tmp_path,
):
    write_manifest(
        tmp_path
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [],
    )

    fake_migrator.generate_fresh_sync_manifest.assert_not_called()

    fake_migrator.execute_migration.assert_called_once_with(
        retry_failed=True
    )


def test_cli_existing_manifest_ignores_source_and_destination_without_fresh(
    monkeypatch,
    tmp_path,
    capsys,
):
    write_manifest(
        tmp_path
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--source",
            "NEW_SOURCE",
            "--destination",
            "NEW_DEST",
        ],
    )

    fake_migrator.generate_fresh_sync_manifest.assert_not_called()

    fake_migrator.execute_migration.assert_called_once_with(
        retry_failed=True
    )

    output = (
        capsys.readouterr().out
    )

    assert (
        "Existing migration manifest found"
        in output
    )

    assert (
        "--source and --destination are ignored"
        in output
    )


# ----------------------------------------------------------------------
# Retry behavior
# ----------------------------------------------------------------------


def test_cli_retries_failed_tasks_by_default(
    monkeypatch,
    tmp_path,
):
    write_manifest(
        tmp_path
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [],
    )

    fake_migrator.execute_migration.assert_called_once_with(
        retry_failed=True
    )


def test_cli_no_retry_failed_flag(
    monkeypatch,
    tmp_path,
):
    write_manifest(
        tmp_path
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    fake_migrator.execute_migration.return_value = {
        "completed": 0,
        "failed": 0,
        "skipped": 1,
        "blocked": 0,
    }

    run_cli(
        monkeypatch,
        [
            "--no-retry-failed",
        ],
    )

    fake_migrator.execute_migration.assert_called_once_with(
        retry_failed=False
    )


# ----------------------------------------------------------------------
# Verification
# ----------------------------------------------------------------------


def test_cli_verify_calls_verification(
    monkeypatch,
    tmp_path,
    capsys,
):
    write_manifest(
        tmp_path
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    fake_migrator.execute_migration.return_value = {
        "completed": 1,
        "failed": 0,
        "skipped": 0,
        "blocked": 0,
    }

    fake_migrator.verify_destination.return_value = {
        "expected_items": 1,
        "destination_items": 1,
        "missing_or_ambiguous": [],
        "ok": True,
    }

    run_cli(
        monkeypatch,
        [
            "--verify",
        ],
    )

    fake_migrator.verify_destination.assert_called_once_with()

    output = (
        capsys.readouterr().out
    )

    assert (
        '"verification"'
        in output
    )

    assert (
        '"ok": true'
        in output
    )


def test_cli_without_verify_does_not_call_verification(
    monkeypatch,
    tmp_path,
):
    write_manifest(
        tmp_path
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [],
    )

    fake_migrator.verify_destination.assert_not_called()


def test_cli_manifest_only_takes_precedence_over_verify(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--source",
            "SOURCE",
            "--destination",
            "DEST",
            "--fresh",
            "--manifest-only",
            "--verify",
        ],
    )

    fake_migrator.execute_migration.assert_not_called()
    fake_migrator.verify_destination.assert_not_called()


# ----------------------------------------------------------------------
# Constructor / configuration plumbing
# ----------------------------------------------------------------------


def test_cli_passes_credentials_and_state_directory_to_migrator(
    monkeypatch,
    tmp_path,
):
    custom_state = (
        tmp_path
        / "custom-state"
    )

    custom_state.mkdir()

    resolve_state = MagicMock(
        return_value=custom_state
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        resolve_state,
    )

    migrator_class, _ = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--credentials",
            "/example/client.json",
            "--state-dir",
            "/example/state",
            "--source",
            "SOURCE",
            "--destination",
            "DEST",
            "--fresh",
        ],
    )

    resolve_state.assert_called_once_with(
        "/example/state"
    )

    migrator_class.assert_called_once_with(
        credentials_path=(
            "/example/client.json"
        ),
        state_dir=custom_state,
        verbose=False,
    )


def test_cli_passes_verbose_true_to_migrator(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    migrator_class, _ = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--source",
            "SOURCE",
            "--destination",
            "DEST",
            "--fresh",
            "--verbose",
        ],
    )

    migrator_class.assert_called_once_with(
        credentials_path=None,
        state_dir=tmp_path,
        verbose=True,
    )


def test_cli_short_verbose_flag_passes_verbose_true(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    migrator_class, _ = (
        make_cli_migrator(
            monkeypatch
        )
    )

    run_cli(
        monkeypatch,
        [
            "--source",
            "SOURCE",
            "--destination",
            "DEST",
            "--fresh",
            "-v",
        ],
    )

    migrator_class.assert_called_once_with(
        credentials_path=None,
        state_dir=tmp_path,
        verbose=True,
    )


# ----------------------------------------------------------------------
# Printed execution summary
# ----------------------------------------------------------------------


def test_cli_prints_execution_summary_as_json(
    monkeypatch,
    tmp_path,
    capsys,
):
    write_manifest(
        tmp_path
    )

    monkeypatch.setattr(
        cli,
        "resolve_state_dir",
        lambda value=None: tmp_path,
    )

    _, fake_migrator = (
        make_cli_migrator(
            monkeypatch
        )
    )

    fake_migrator.execute_migration.return_value = {
        "completed": 8,
        "failed": 2,
        "skipped": 3,
        "blocked": 4,
    }

    run_cli(
        monkeypatch,
        [],
    )

    output = (
        capsys.readouterr().out
    )

    assert (
        '"completed": 8'
        in output
    )

    assert (
        '"failed": 2'
        in output
    )

    assert (
        '"skipped": 3'
        in output
    )

    assert (
        '"blocked": 4'
        in output
    )