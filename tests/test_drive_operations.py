from unittest.mock import MagicMock

import pytest

from drive_migrator.migrator_engine import (
    DriveMigrator,
    FAILURE_PHASE_EXECUTION,
    FAILURE_PHASE_MANIFEST,
    FOLDER_MIME,
)
from drive_migrator.migration_helpers import (
    DEFAULT_STAGING_FOLDER_NAME,
    MigrationHelpers,
    STAGING_FOLDER_PROPERTY,
    STAGING_FOLDER_PROPERTY_VALUE,
    STAGING_TASK_PROPERTY,
)


def make_request(result):
    request = MagicMock()
    request.execute.return_value = result
    return request


def make_migrator(
    tmp_path,
    service,
):
    """
    Build a DriveMigrator without invoking OAuth.
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

    migrator.service = service
    migrator.verbose = False

    migrator.helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            migrator.work_list_path
        ),
    )

    return migrator


# ----------------------------------------------------------------------
# Recursive scanning
# ----------------------------------------------------------------------


def test_scan_folder_reads_single_page(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": [
                    {
                        "id": "FILE1",
                        "name": "Copy of Report.pdf",
                        "mimeType": "application/pdf",
                        "parents": ["ROOT"],
                        "size": "123",
                        "md5Checksum": "abc123",
                        "modifiedTime": (
                            "2026-01-01T00:00:00Z"
                        ),
                    }
                ]
            }
        )
    )

    migrator = make_migrator(
        tmp_path,
        service,
    )

    inventory = migrator.scan_folder(
        "ROOT"
    )

    assert "FILE1" in inventory

    item = inventory["FILE1"]

    assert (
        item["original_name"]
        == "Copy of Report.pdf"
    )

    assert (
        item["name"]
        == "Report.pdf"
    )

    assert (
        item["relative_path"]
        == "Report.pdf"
    )

    assert (
        item["parent_id"]
        == "ROOT"
    )

    assert item["depth"] == 1


def test_scan_folder_follows_pagination(
    tmp_path,
):
    service = MagicMock()

    first_page = make_request(
        {
            "nextPageToken": "PAGE2",
            "files": [
                {
                    "id": "FILE1",
                    "name": "One.pdf",
                    "mimeType": "application/pdf",
                    "parents": ["ROOT"],
                }
            ],
        }
    )

    second_page = make_request(
        {
            "files": [
                {
                    "id": "FILE2",
                    "name": "Two.pdf",
                    "mimeType": "application/pdf",
                    "parents": ["ROOT"],
                }
            ]
        }
    )

    service.files.return_value.list.side_effect = [
        first_page,
        second_page,
    ]

    migrator = make_migrator(
        tmp_path,
        service,
    )

    inventory = migrator.scan_folder(
        "ROOT"
    )

    assert set(
        inventory.keys()
    ) == {
        "FILE1",
        "FILE2",
    }

    assert (
        service.files.return_value.list.call_count
        == 2
    )


def test_scan_folder_recurses_into_subfolders(
    tmp_path,
):
    service = MagicMock()

    root_request = make_request(
        {
            "files": [
                {
                    "id": "FOLDER1",
                    "name": "Copy of Projects",
                    "mimeType": FOLDER_MIME,
                    "parents": ["ROOT"],
                }
            ]
        }
    )

    child_request = make_request(
        {
            "files": [
                {
                    "id": "FILE1",
                    "name": "Copy of Plan.pdf",
                    "mimeType": "application/pdf",
                    "parents": ["FOLDER1"],
                }
            ]
        }
    )

    service.files.return_value.list.side_effect = [
        root_request,
        child_request,
    ]

    migrator = make_migrator(
        tmp_path,
        service,
    )

    inventory = migrator.scan_folder(
        "ROOT"
    )

    assert (
        inventory["FOLDER1"][
            "relative_path"
        ]
        == "Projects"
    )

    assert (
        inventory["FILE1"][
            "relative_path"
        ]
        == "Projects/Plan.pdf"
    )

    assert (
        inventory["FILE1"][
            "parent_relative_path"
        ]
        == "Projects"
    )

    assert (
        inventory["FILE1"]["depth"]
        == 2
    )


def test_scan_folder_destination_mode_preserves_names(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": [
                    {
                        "id": "FILE1",
                        "name": "Copy of Report.pdf",
                        "mimeType": "application/pdf",
                        "parents": ["ROOT"],
                    }
                ]
            }
        )
    )

    migrator = make_migrator(
        tmp_path,
        service,
    )

    inventory = migrator.scan_folder(
        "ROOT",
        source_mode=False,
    )

    assert (
        inventory["FILE1"]["name"]
        == "Copy of Report.pdf"
    )

    assert (
        inventory["FILE1"][
            "relative_path"
        ]
        == "Copy of Report.pdf"
    )


# ----------------------------------------------------------------------
# My Drive staging folder
# ----------------------------------------------------------------------


def test_get_or_create_staging_folder_reuses_existing(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": [
                    {
                        "id": "STAGING_FOLDER",
                        "name": (
                            DEFAULT_STAGING_FOLDER_NAME
                        ),
                        "mimeType": FOLDER_MIME,
                        "parents": ["root"],
                        "appProperties": {
                            STAGING_FOLDER_PROPERTY: (
                                STAGING_FOLDER_PROPERTY_VALUE
                            )
                        },
                    }
                ]
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    result = (
        helpers.get_or_create_staging_folder()
    )

    assert result == "STAGING_FOLDER"

    service.files.return_value.create.assert_not_called()


def test_get_or_create_staging_folder_creates_in_my_drive(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": []
            }
        )
    )

    service.files.return_value.create.return_value = (
        make_request(
            {
                "id": "STAGING_FOLDER",
                "name": (
                    DEFAULT_STAGING_FOLDER_NAME
                ),
                "mimeType": FOLDER_MIME,
                "parents": ["root"],
                "appProperties": {
                    STAGING_FOLDER_PROPERTY: (
                        STAGING_FOLDER_PROPERTY_VALUE
                    )
                },
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    result = (
        helpers.get_or_create_staging_folder()
    )

    assert result == "STAGING_FOLDER"

    service.files.return_value.create.assert_called_once()

    call = (
        service.files.return_value.create.call_args
    )

    assert (
        call.kwargs["body"]["parents"]
        == ["root"]
    )

    assert (
        call.kwargs[
            "body"
        ][
            "appProperties"
        ][
            STAGING_FOLDER_PROPERTY
        ]
        == STAGING_FOLDER_PROPERTY_VALUE
    )


def test_get_or_create_staging_folder_rejects_duplicates(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": [
                    {
                        "id": "A",
                        "parents": ["root"],
                    },
                    {
                        "id": "B",
                        "parents": ["root"],
                    },
                ]
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="multiple Drive Migrator staging folders",
    ):
        helpers.get_or_create_staging_folder()


def test_get_or_create_staging_folder_ignores_shared_drive_candidate(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": [
                    {
                        "id": "SHARED_STAGE",
                        "name": (
                            DEFAULT_STAGING_FOLDER_NAME
                        ),
                        "driveId": "SHARED_DRIVE",
                    }
                ]
            }
        )
    )

    service.files.return_value.create.return_value = (
        make_request(
            {
                "id": "MY_DRIVE_STAGE",
                "name": (
                    DEFAULT_STAGING_FOLDER_NAME
                ),
                "parents": ["root"],
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    result = (
        helpers.get_or_create_staging_folder()
    )

    assert result == "MY_DRIVE_STAGE"

    service.files.return_value.create.assert_called_once()


def test_get_or_create_staging_folder_rejects_created_shared_drive_folder(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": []
            }
        )
    )

    service.files.return_value.create.return_value = (
        make_request(
            {
                "id": "BAD_STAGE",
                "name": (
                    DEFAULT_STAGING_FOLDER_NAME
                ),
                "driveId": "SHARED_DRIVE",
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="shared drive",
    ):
        helpers.get_or_create_staging_folder()


def test_get_or_create_staging_folder_requires_returned_id(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": []
            }
        )
    )

    service.files.return_value.create.return_value = (
        make_request(
            {
                "name": (
                    DEFAULT_STAGING_FOLDER_NAME
                ),
                "parents": ["root"],
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="did not return an ID",
    ):
        helpers.get_or_create_staging_folder()


# ----------------------------------------------------------------------
# Persisted staging folder metadata
# ----------------------------------------------------------------------


def test_load_or_create_staging_folder_reuses_manifest_value(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "staging_folder_id": (
                    "STAGING_FOLDER"
                ),
            },
            "tasks": [],
        }
    )

    migrator.helpers.get_or_create_staging_folder = (
        MagicMock()
    )

    manifest = (
        migrator.helpers.load_manifest()
    )

    result = (
        migrator._load_or_create_staging_folder_id(
            manifest
        )
    )

    assert result == "STAGING_FOLDER"

    migrator.helpers.get_or_create_staging_folder.assert_not_called()


def test_load_or_create_staging_folder_persists_new_value(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "staging_folder_id": None,
            },
            "tasks": [],
        }
    )

    migrator.helpers.get_or_create_staging_folder = (
        MagicMock(
            return_value="STAGING_FOLDER"
        )
    )

    manifest = (
        migrator.helpers.load_manifest()
    )

    result = (
        migrator._load_or_create_staging_folder_id(
            manifest
        )
    )

    assert result == "STAGING_FOLDER"

    saved = (
        migrator.helpers.load_manifest()
    )

    assert (
        saved[
            "migration_metadata"
        ][
            "staging_folder_id"
        ]
        == "STAGING_FOLDER"
    )


# ----------------------------------------------------------------------
# Staging-copy operations
# ----------------------------------------------------------------------


def test_perform_staging_app_copy(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.copy.return_value = (
        make_request(
            {
                "id": "STAGED1",
                "name": "Report.pdf",
                "parents": [
                    "STAGING_FOLDER"
                ],
                "appProperties": {
                    STAGING_TASK_PROPERTY: (
                        "TASK1"
                    )
                },
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    staged_id = (
        helpers.perform_staging_app_copy(
            source_id="SOURCE_FILE",
            target_name="Report.pdf",
            staging_folder_id=(
                "STAGING_FOLDER"
            ),
            task_id="TASK1",
        )
    )

    assert staged_id == "STAGED1"

    service.files.return_value.copy.assert_called_once_with(
        fileId="SOURCE_FILE",
        body={
            "name": "Report.pdf",
            "parents": [
                "STAGING_FOLDER"
            ],
            "appProperties": {
                STAGING_TASK_PROPERTY: (
                    "TASK1"
                )
            },
        },
        supportsAllDrives=True,
        fields=(
            "id,name,mimeType,parents,"
            "driveId,appProperties"
        ),
    )


def test_perform_staging_copy_requires_returned_id(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.copy.return_value = (
        make_request(
            {
                "name": "Report.pdf",
                "parents": [
                    "STAGING_FOLDER"
                ],
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="did not return an ID",
    ):
        helpers.perform_staging_app_copy(
            source_id="SOURCE_FILE",
            target_name="Report.pdf",
            staging_folder_id=(
                "STAGING_FOLDER"
            ),
            task_id="TASK1",
        )


def test_perform_staging_copy_rejects_wrong_parent(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.copy.return_value = (
        make_request(
            {
                "id": "STAGED1",
                "name": "Report.pdf",
                "parents": [
                    "WRONG_FOLDER"
                ],
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="staging folder",
    ):
        helpers.perform_staging_app_copy(
            source_id="SOURCE_FILE",
            target_name="Report.pdf",
            staging_folder_id=(
                "STAGING_FOLDER"
            ),
            task_id="TASK1",
        )


def test_perform_staging_copy_rejects_shared_drive_result(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.copy.return_value = (
        make_request(
            {
                "id": "STAGED1",
                "name": "Report.pdf",
                "parents": [
                    "STAGING_FOLDER"
                ],
                "driveId": "SHARED_DRIVE",
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="shared drive",
    ):
        helpers.perform_staging_app_copy(
            source_id="SOURCE_FILE",
            target_name="Report.pdf",
            staging_folder_id=(
                "STAGING_FOLDER"
            ),
            task_id="TASK1",
        )


def test_find_staging_copy_returns_existing_id(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": [
                    {
                        "id": "STAGED1",
                        "name": "Report.pdf",
                        "parents": [
                            "STAGING_FOLDER"
                        ],
                        "appProperties": {
                            STAGING_TASK_PROPERTY: (
                                "TASK1"
                            )
                        },
                    }
                ]
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    result = helpers.find_staging_copy(
        "TASK1",
        staging_folder_id=(
            "STAGING_FOLDER"
        ),
    )

    assert result == "STAGED1"


def test_find_staging_copy_returns_none(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": []
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    assert (
        helpers.find_staging_copy(
            "TASK1",
            staging_folder_id=(
                "STAGING_FOLDER"
            ),
        )
        is None
    )


def test_find_staging_copy_rejects_duplicates(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": [
                    {
                        "id": "A"
                    },
                    {
                        "id": "B"
                    },
                ]
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="multiple staging copies",
    ):
        helpers.find_staging_copy(
            "TASK1",
            staging_folder_id=(
                "STAGING_FOLDER"
            ),
        )


# ----------------------------------------------------------------------
# Final move
# ----------------------------------------------------------------------


def test_perform_final_move(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.update.return_value = (
        make_request(
            {
                "id": "STAGED1",
                "name": "Report.pdf",
                "parents": ["DEST"],
            }
        )
    )

    helpers = MigrationHelpers(
        service=service,
        work_list_path=(
            tmp_path / "manifest.json"
        ),
    )

    result = helpers.perform_final_move(
        file_id="STAGED1",
        dest_folder_id="DEST",
        staging_folder_id=(
            "STAGING_FOLDER"
        ),
    )

    assert (
        result["id"]
        == "STAGED1"
    )

    service.files.return_value.update.assert_called_once_with(
        fileId="STAGED1",
        addParents="DEST",
        removeParents="STAGING_FOLDER",
        supportsAllDrives=True,
        fields=(
            "id,name,mimeType,parents,"
            "driveId,appProperties"
        ),
    )


# ----------------------------------------------------------------------
# Destination child lookup
# ----------------------------------------------------------------------


def test_find_named_child_returns_file(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": [
                    {
                        "id": "FILE1",
                        "name": "Report.pdf",
                        "mimeType": "application/pdf",
                        "parents": ["DEST"],
                    }
                ]
            }
        )
    )

    migrator = make_migrator(
        tmp_path,
        service,
    )

    result = migrator._find_named_child(
        parent_id="DEST",
        name="Report.pdf",
        want_folder=False,
    )

    assert result["id"] == "FILE1"


def test_find_named_child_distinguishes_folder(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": [
                    {
                        "id": "FILE1",
                        "name": "Reports",
                        "mimeType": "application/pdf",
                        "parents": ["DEST"],
                    },
                    {
                        "id": "FOLDER1",
                        "name": "Reports",
                        "mimeType": FOLDER_MIME,
                        "parents": ["DEST"],
                    },
                ]
            }
        )
    )

    migrator = make_migrator(
        tmp_path,
        service,
    )

    result = migrator._find_named_child(
        parent_id="DEST",
        name="Reports",
        want_folder=True,
    )

    assert (
        result["id"]
        == "FOLDER1"
    )


def test_find_named_child_returns_none(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": []
            }
        )
    )

    migrator = make_migrator(
        tmp_path,
        service,
    )

    result = migrator._find_named_child(
        parent_id="DEST",
        name="Missing.pdf",
        want_folder=False,
    )

    assert result is None


def test_find_named_child_rejects_duplicate_matches(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.list.return_value = (
        make_request(
            {
                "files": [
                    {
                        "id": "A",
                        "mimeType": (
                            "application/pdf"
                        ),
                    },
                    {
                        "id": "B",
                        "mimeType": (
                            "application/pdf"
                        ),
                    },
                ]
            }
        )
    )

    migrator = make_migrator(
        tmp_path,
        service,
    )

    with pytest.raises(
        RuntimeError,
        match="Multiple destination items",
    ):
        migrator._find_named_child(
            parent_id="DEST",
            name="Report.pdf",
            want_folder=False,
        )


# ----------------------------------------------------------------------
# Folder task execution
# ----------------------------------------------------------------------


def test_execute_folder_task_reuses_existing_folder(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "folder_map": {
                    "SOURCE_ROOT": (
                        "DEST_ROOT"
                    )
                }
            },
            "tasks": [
                {
                    "task_id": "TASK1",
                    "type": (
                        "folder_creation"
                    ),
                    "source_id": (
                        "SOURCE_CHILD"
                    ),
                    "source_parent_id": (
                        "SOURCE_ROOT"
                    ),
                    "target_name": (
                        "Projects"
                    ),
                    "relative_path": (
                        "Projects"
                    ),
                    "status": "pending",
                }
            ],
        }
    )

    migrator._find_named_child = (
        MagicMock(
            return_value={
                "id": "DEST_CHILD"
            }
        )
    )

    folder_map = {
        "SOURCE_ROOT": "DEST_ROOT"
    }

    task = (
        migrator.helpers.load_manifest()
        ["tasks"][0]
    )

    migrator._execute_folder_task(
        task,
        folder_map,
    )

    assert (
        folder_map["SOURCE_CHILD"]
        == "DEST_CHILD"
    )

    manifest = (
        migrator.helpers.load_manifest()
    )

    saved_task = (
        manifest["tasks"][0]
    )

    assert (
        saved_task["status"]
        == "completed"
    )

    assert (
        saved_task["dest_id"]
        == "DEST_CHILD"
    )

    assert (
        saved_task.get(
            "failure_phase"
        )
        is None
    )

    service.files.return_value.create.assert_not_called()


def test_execute_folder_task_creates_missing_folder(
    tmp_path,
):
    service = MagicMock()

    service.files.return_value.create.return_value = (
        make_request(
            {
                "id": "DEST_CHILD",
                "name": "Projects",
                "parents": ["DEST_ROOT"],
            }
        )
    )

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "folder_map": {
                    "SOURCE_ROOT": (
                        "DEST_ROOT"
                    )
                }
            },
            "tasks": [
                {
                    "task_id": "TASK1",
                    "type": (
                        "folder_creation"
                    ),
                    "source_id": (
                        "SOURCE_CHILD"
                    ),
                    "source_parent_id": (
                        "SOURCE_ROOT"
                    ),
                    "target_name": (
                        "Projects"
                    ),
                    "relative_path": (
                        "Projects"
                    ),
                    "status": "pending",
                }
            ],
        }
    )

    migrator._find_named_child = (
        MagicMock(
            return_value=None
        )
    )

    folder_map = {
        "SOURCE_ROOT": "DEST_ROOT"
    }

    task = (
        migrator.helpers.load_manifest()
        ["tasks"][0]
    )

    migrator._execute_folder_task(
        task,
        folder_map,
    )

    service.files.return_value.create.assert_called_once()

    assert (
        folder_map["SOURCE_CHILD"]
        == "DEST_CHILD"
    )


def test_execute_folder_task_fails_without_parent_mapping(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    task = {
        "task_id": "TASK1",
        "source_id": "SOURCE_CHILD",
        "source_parent_id": "UNKNOWN",
        "target_name": "Projects",
        "relative_path": "Projects",
    }

    with pytest.raises(
        RuntimeError,
        match="unresolved",
    ):
        migrator._execute_folder_task(
            task,
            {},
        )


# ----------------------------------------------------------------------
# File task execution
# ----------------------------------------------------------------------


def test_execute_file_task_reconciles_existing_destination(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {},
            "tasks": [
                {
                    "task_id": "TASK1",
                    "type": "file_migration",
                    "source_id": "SOURCE_FILE",
                    "source_parent_id": (
                        "SOURCE_FOLDER"
                    ),
                    "target_name": "Report.pdf",
                    "relative_path": (
                        "Report.pdf"
                    ),
                    "status": "pending",
                }
            ],
        }
    )

    migrator._find_named_child = (
        MagicMock(
            return_value={
                "id": "DEST_FILE"
            }
        )
    )

    task = (
        migrator.helpers.load_manifest()
        ["tasks"][0]
    )

    migrator._execute_file_task(
        task,
        {
            "SOURCE_FOLDER": "DEST_FOLDER"
        },
        "STAGING_FOLDER",
    )

    saved = (
        migrator.helpers.load_manifest()
        ["tasks"][0]
    )

    assert (
        saved["status"]
        == "completed"
    )

    assert (
        saved["dest_id"]
        == "DEST_FILE"
    )

    service.files.return_value.copy.assert_not_called()
    service.files.return_value.update.assert_not_called()


def test_execute_file_task_uses_existing_staged_file_id(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {},
            "tasks": [
                {
                    "task_id": "TASK1",
                    "type": "file_migration",
                    "source_id": "SOURCE_FILE",
                    "source_parent_id": (
                        "SOURCE_FOLDER"
                    ),
                    "target_name": "Report.pdf",
                    "relative_path": (
                        "Report.pdf"
                    ),
                    "staged_file_id": "STAGED1",
                    "status": "in_progress",
                }
            ],
        }
    )

    migrator._find_named_child = (
        MagicMock(
            return_value=None
        )
    )

    migrator.helpers.find_staging_copy = (
        MagicMock()
    )

    migrator.helpers.perform_staging_app_copy = (
        MagicMock()
    )

    migrator.helpers.perform_final_move = (
        MagicMock(
            return_value={
                "id": "STAGED1"
            }
        )
    )

    task = (
        migrator.helpers.load_manifest()
        ["tasks"][0]
    )

    migrator._execute_file_task(
        task,
        {
            "SOURCE_FOLDER": "DEST_FOLDER"
        },
        "STAGING_FOLDER",
    )

    migrator.helpers.find_staging_copy.assert_not_called()

    migrator.helpers.perform_staging_app_copy.assert_not_called()

    migrator.helpers.perform_final_move.assert_called_once_with(
        file_id="STAGED1",
        dest_folder_id="DEST_FOLDER",
        staging_folder_id=(
            "STAGING_FOLDER"
        ),
    )

    saved = (
        migrator.helpers.load_manifest()
        ["tasks"][0]
    )

    assert (
        saved["status"]
        == "completed"
    )

    assert (
        saved["dest_id"]
        == "STAGED1"
    )


def test_execute_file_task_recovers_staging_copy_from_drive(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {},
            "tasks": [
                {
                    "task_id": "TASK1",
                    "type": "file_migration",
                    "source_id": "SOURCE_FILE",
                    "source_parent_id": (
                        "SOURCE_FOLDER"
                    ),
                    "target_name": "Report.pdf",
                    "relative_path": (
                        "Report.pdf"
                    ),
                    "staged_file_id": None,
                    "status": "in_progress",
                }
            ],
        }
    )

    migrator._find_named_child = (
        MagicMock(
            return_value=None
        )
    )

    migrator.helpers.find_staging_copy = (
        MagicMock(
            return_value=(
                "RECOVERED_STAGE"
            )
        )
    )

    migrator.helpers.perform_staging_app_copy = (
        MagicMock()
    )

    migrator.helpers.perform_final_move = (
        MagicMock(
            return_value={
                "id": "RECOVERED_STAGE"
            }
        )
    )

    task = (
        migrator.helpers.load_manifest()
        ["tasks"][0]
    )

    migrator._execute_file_task(
        task,
        {
            "SOURCE_FOLDER": "DEST_FOLDER"
        },
        "STAGING_FOLDER",
    )

    migrator.helpers.find_staging_copy.assert_called_once_with(
        "TASK1",
        staging_folder_id=(
            "STAGING_FOLDER"
        ),
    )

    migrator.helpers.perform_staging_app_copy.assert_not_called()

    migrator.helpers.perform_final_move.assert_called_once_with(
        file_id="RECOVERED_STAGE",
        dest_folder_id="DEST_FOLDER",
        staging_folder_id=(
            "STAGING_FOLDER"
        ),
    )

    saved = (
        migrator.helpers.load_manifest()
        ["tasks"][0]
    )

    assert (
        saved["status"]
        == "completed"
    )

    assert (
        saved["staged_file_id"]
        == "RECOVERED_STAGE"
    )


def test_execute_file_task_creates_new_stage_when_needed(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {},
            "tasks": [
                {
                    "task_id": "TASK1",
                    "type": "file_migration",
                    "source_id": "SOURCE_FILE",
                    "source_parent_id": (
                        "SOURCE_FOLDER"
                    ),
                    "target_name": "Report.pdf",
                    "relative_path": (
                        "Report.pdf"
                    ),
                    "staged_file_id": None,
                    "status": "pending",
                }
            ],
        }
    )

    migrator._find_named_child = (
        MagicMock(
            return_value=None
        )
    )

    migrator.helpers.find_staging_copy = (
        MagicMock(
            return_value=None
        )
    )

    migrator.helpers.perform_staging_app_copy = (
        MagicMock(
            return_value="NEW_STAGE"
        )
    )

    migrator.helpers.perform_final_move = (
        MagicMock(
            return_value={
                "id": "NEW_STAGE"
            }
        )
    )

    task = (
        migrator.helpers.load_manifest()
        ["tasks"][0]
    )

    migrator._execute_file_task(
        task,
        {
            "SOURCE_FOLDER": "DEST_FOLDER"
        },
        "STAGING_FOLDER",
    )

    migrator.helpers.find_staging_copy.assert_called_once_with(
        "TASK1",
        staging_folder_id=(
            "STAGING_FOLDER"
        ),
    )

    migrator.helpers.perform_staging_app_copy.assert_called_once_with(
        source_id="SOURCE_FILE",
        target_name="Report.pdf",
        staging_folder_id=(
            "STAGING_FOLDER"
        ),
        task_id="TASK1",
    )

    migrator.helpers.perform_final_move.assert_called_once_with(
        file_id="NEW_STAGE",
        dest_folder_id="DEST_FOLDER",
        staging_folder_id=(
            "STAGING_FOLDER"
        ),
    )

    saved = (
        migrator.helpers.load_manifest()
        ["tasks"][0]
    )

    assert (
        saved["status"]
        == "completed"
    )

    assert (
        saved["staged_file_id"]
        == "NEW_STAGE"
    )


def test_execute_file_task_fails_without_parent_mapping(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    task = {
        "task_id": "TASK1",
        "source_id": "SOURCE_FILE",
        "source_parent_id": "UNKNOWN",
        "target_name": "Report.pdf",
        "relative_path": "Report.pdf",
    }

    with pytest.raises(
        RuntimeError,
        match="unresolved",
    ):
        migrator._execute_file_task(
            task,
            {},
            "STAGING_FOLDER",
        )


# ----------------------------------------------------------------------
# Migration orchestration
# ----------------------------------------------------------------------


def test_execute_migration_processes_folders_before_files(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "source_root_id": "SOURCE",
                "dest_root_id": "DEST",
                "folder_map": {
                    "SOURCE": "DEST"
                },
                "staging_folder_id": None,
            },
            "tasks": [
                {
                    "task_id": "FILE_TASK",
                    "type": "file_migration",
                    "source_id": "FILE1",
                    "source_parent_id": (
                        "SOURCE_FOLDER"
                    ),
                    "relative_path": (
                        "Folder/File.pdf"
                    ),
                    "depth": 2,
                    "status": "pending",
                    "failure_phase": None,
                },
                {
                    "task_id": "FOLDER_TASK",
                    "type": (
                        "folder_creation"
                    ),
                    "source_id": (
                        "SOURCE_FOLDER"
                    ),
                    "source_parent_id": (
                        "SOURCE"
                    ),
                    "relative_path": (
                        "Folder"
                    ),
                    "depth": 1,
                    "status": "pending",
                    "failure_phase": None,
                },
            ],
        }
    )

    migrator._load_or_create_staging_folder_id = (
        MagicMock(
            return_value=(
                "STAGING_FOLDER"
            )
        )
    )

    execution_order = []

    def fake_folder(
        task,
        folder_map,
    ):
        execution_order.append(
            task["task_id"]
        )

        folder_map[
            "SOURCE_FOLDER"
        ] = "DEST_FOLDER"

        migrator.helpers.update_task_status(
            task["task_id"],
            "completed",
            dest_id="DEST_FOLDER",
            failure_phase=None,
        )

    def fake_file(
        task,
        folder_map,
        staging_folder_id,
    ):
        assert (
            staging_folder_id
            == "STAGING_FOLDER"
        )

        execution_order.append(
            task["task_id"]
        )

        migrator.helpers.update_task_status(
            task["task_id"],
            "completed",
            dest_id="DEST_FILE",
            failure_phase=None,
        )

    migrator._execute_folder_task = (
        fake_folder
    )

    migrator._execute_file_task = (
        fake_file
    )

    stats = migrator.execute_migration()

    assert execution_order == [
        "FOLDER_TASK",
        "FILE_TASK",
    ]

    assert stats == {
        "completed": 2,
        "failed": 0,
        "skipped": 0,
        "blocked": 0,
    }


def test_execute_migration_marks_failed_task_and_continues(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "source_root_id": "SOURCE",
                "dest_root_id": "DEST",
                "folder_map": {
                    "SOURCE": "DEST"
                },
                "staging_folder_id": None,
            },
            "tasks": [
                {
                    "task_id": "TASK1",
                    "type": "file_migration",
                    "source_id": "FILE1",
                    "source_parent_id": (
                        "SOURCE"
                    ),
                    "relative_path": (
                        "One.pdf"
                    ),
                    "depth": 1,
                    "status": "pending",
                    "failure_phase": None,
                },
                {
                    "task_id": "TASK2",
                    "type": "file_migration",
                    "source_id": "FILE2",
                    "source_parent_id": (
                        "SOURCE"
                    ),
                    "relative_path": (
                        "Two.pdf"
                    ),
                    "depth": 1,
                    "status": "pending",
                    "failure_phase": None,
                },
            ],
        }
    )

    migrator._load_or_create_staging_folder_id = (
        MagicMock(
            return_value=(
                "STAGING_FOLDER"
            )
        )
    )

    def fake_file(
        task,
        folder_map,
        staging_folder_id,
    ):
        if (
            task["task_id"]
            == "TASK1"
        ):
            raise PermissionError(
                "Denied"
            )

        migrator.helpers.update_task_status(
            task["task_id"],
            "completed",
            failure_phase=None,
        )

    migrator._execute_file_task = (
        fake_file
    )

    stats = migrator.execute_migration()

    assert stats == {
        "completed": 1,
        "failed": 1,
        "skipped": 0,
        "blocked": 0,
    }

    manifest = (
        migrator.helpers.load_manifest()
    )

    first = manifest["tasks"][0]
    second = manifest["tasks"][1]

    assert (
        first["status"]
        == "failed"
    )

    assert (
        first["failure_phase"]
        == FAILURE_PHASE_EXECUTION
    )

    assert (
        "PermissionError"
        in first["error_message"]
    )

    assert (
        second["status"]
        == "completed"
    )


def test_execute_migration_skips_completed_tasks(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "source_root_id": "SOURCE",
                "dest_root_id": "DEST",
                "folder_map": {
                    "SOURCE": "DEST"
                },
                "staging_folder_id": None,
            },
            "tasks": [
                {
                    "task_id": "TASK1",
                    "type": "file_migration",
                    "relative_path": (
                        "Done.pdf"
                    ),
                    "depth": 1,
                    "status": "completed",
                    "failure_phase": None,
                }
            ],
        }
    )

    migrator._load_or_create_staging_folder_id = (
        MagicMock(
            return_value=(
                "STAGING_FOLDER"
            )
        )
    )

    migrator._execute_file_task = (
        MagicMock()
    )

    stats = migrator.execute_migration()

    assert stats == {
        "completed": 0,
        "failed": 0,
        "skipped": 1,
        "blocked": 0,
    }

    migrator._execute_file_task.assert_not_called()


def test_execute_migration_can_skip_failed_tasks(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "source_root_id": "SOURCE",
                "dest_root_id": "DEST",
                "folder_map": {
                    "SOURCE": "DEST"
                },
                "staging_folder_id": None,
            },
            "tasks": [
                {
                    "task_id": "TASK1",
                    "type": "file_migration",
                    "relative_path": (
                        "Failed.pdf"
                    ),
                    "depth": 1,
                    "status": "failed",
                    "failure_phase": (
                        FAILURE_PHASE_EXECUTION
                    ),
                }
            ],
        }
    )

    migrator._load_or_create_staging_folder_id = (
        MagicMock(
            return_value=(
                "STAGING_FOLDER"
            )
        )
    )

    migrator._execute_file_task = (
        MagicMock()
    )

    stats = migrator.execute_migration(
        retry_failed=False
    )

    assert stats == {
        "completed": 0,
        "failed": 0,
        "skipped": 1,
        "blocked": 0,
    }

    migrator._execute_file_task.assert_not_called()


def test_execute_migration_blocks_manifest_failure(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "source_root_id": "SOURCE",
                "dest_root_id": "DEST",
                "folder_map": {
                    "SOURCE": "DEST"
                },
                "staging_folder_id": None,
            },
            "tasks": [
                {
                    "task_id": "TASK1",
                    "type": "file_migration",
                    "relative_path": (
                        "Shortcut"
                    ),
                    "depth": 1,
                    "status": "failed",
                    "failure_phase": (
                        FAILURE_PHASE_MANIFEST
                    ),
                    "error_message": (
                        "Google Drive shortcuts "
                        "are not supported."
                    ),
                }
            ],
        }
    )

    migrator._load_or_create_staging_folder_id = (
        MagicMock(
            return_value="STAGING_FOLDER"
        )
    )

    migrator._execute_file_task = (
        MagicMock()
    )

    stats = migrator.execute_migration()

    assert stats == {
        "completed": 0,
        "failed": 0,
        "skipped": 0,
        "blocked": 1,
    }

    migrator._execute_file_task.assert_not_called()

    migrator._load_or_create_staging_folder_id.assert_not_called()


def test_execute_migration_retries_execution_failure(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "source_root_id": "SOURCE",
                "dest_root_id": "DEST",
                "folder_map": {
                    "SOURCE": "DEST"
                },
                "staging_folder_id": None,
            },
            "tasks": [
                {
                    "task_id": "TASK1",
                    "type": "file_migration",
                    "source_id": "FILE1",
                    "source_parent_id": (
                        "SOURCE"
                    ),
                    "relative_path": (
                        "Retry.pdf"
                    ),
                    "depth": 1,
                    "status": "failed",
                    "failure_phase": (
                        FAILURE_PHASE_EXECUTION
                    ),
                    "error_message": (
                        "Temporary failure"
                    ),
                }
            ],
        }
    )

    migrator._load_or_create_staging_folder_id = (
        MagicMock(
            return_value=(
                "STAGING_FOLDER"
            )
        )
    )

    def fake_file(
        task,
        folder_map,
        staging_folder_id,
    ):
        migrator.helpers.update_task_status(
            task["task_id"],
            "completed",
            dest_id="DEST_FILE",
            failure_phase=None,
        )

    migrator._execute_file_task = (
        MagicMock(
            side_effect=fake_file
        )
    )

    stats = migrator.execute_migration()

    assert stats == {
        "completed": 1,
        "failed": 0,
        "skipped": 0,
        "blocked": 0,
    }

    migrator._execute_file_task.assert_called_once()


# ----------------------------------------------------------------------
# Verification
# ----------------------------------------------------------------------


def test_verify_destination_success(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "dest_root_id": "DEST"
            },
            "tasks": [
                {
                    "type": (
                        "folder_creation"
                    ),
                    "relative_path": (
                        "Projects"
                    ),
                },
                {
                    "type": (
                        "file_migration"
                    ),
                    "relative_path": (
                        "Projects/Plan.pdf"
                    ),
                },
            ],
        }
    )

    migrator.scan_folder = MagicMock(
        return_value={
            "FOLDER1": {
                "id": "FOLDER1",
                "relative_path": (
                    "Projects"
                ),
                "mimeType": FOLDER_MIME,
            },
            "FILE1": {
                "id": "FILE1",
                "relative_path": (
                    "Projects/Plan.pdf"
                ),
                "mimeType": (
                    "application/pdf"
                ),
            },
        }
    )

    result = (
        migrator.verify_destination()
    )

    migrator.scan_folder.assert_called_once_with(
        "DEST",
        source_mode=False,
    )

    assert result["ok"] is True

    assert (
        result[
            "missing_or_ambiguous"
        ]
        == []
    )

    assert (
        result["expected_items"]
        == 2
    )


def test_verify_destination_reports_missing_item(
    tmp_path,
):
    service = MagicMock()

    migrator = make_migrator(
        tmp_path,
        service,
    )

    migrator.helpers.write_manifest(
        {
            "migration_metadata": {
                "dest_root_id": "DEST"
            },
            "tasks": [
                {
                    "type": (
                        "file_migration"
                    ),
                    "relative_path": (
                        "Missing.pdf"
                    ),
                }
            ],
        }
    )

    migrator.scan_folder = MagicMock(
        return_value={}
    )

    result = (
        migrator.verify_destination()
    )

    migrator.scan_folder.assert_called_once_with(
        "DEST",
        source_mode=False,
    )

    assert result["ok"] is False

    assert (
        result[
            "missing_or_ambiguous"
        ]
        == [
            {
                "path": (
                    "Missing.pdf"
                ),
                "error": "missing",
            }
        ]
    )