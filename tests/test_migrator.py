import json

import pytest

from drive_migrator.migrator_engine import (
    DriveMigrator,
    FAILURE_PHASE_EXECUTION,
    FAILURE_PHASE_MANIFEST,
    FOLDER_MIME,
)
from drive_migrator.migration_helpers import (
    MigrationHelpers,
)


GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDES_MIME = "application/vnd.google-apps.presentation"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"


def make_migrator_without_auth(
    tmp_path,
):
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

    migrator.verbose = False
    migrator.service = None

    migrator.helpers = MigrationHelpers(
        service=None,
        work_list_path=(
            migrator.work_list_path
        ),
    )

    return migrator


# ----------------------------------------------------------------------
# Filename normalization
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        (
            "Copy of Report.pdf",
            "Report.pdf",
        ),
        (
            "copy of Report.pdf",
            "Report.pdf",
        ),
        (
            "COPY OF Report.pdf",
            "Report.pdf",
        ),
        (
            "Copy Of Report.pdf",
            "Report.pdf",
        ),
        (
            "Copy of Copy of Report.pdf",
            "Report.pdf",
        ),
        (
            "copy of COPY OF Report.pdf",
            "Report.pdf",
        ),
        (
            "Report.pdf",
            "Report.pdf",
        ),
        (
            "My Copy of Report.pdf",
            "My Copy of Report.pdf",
        ),
        (
            "  Copy of Report.pdf  ",
            "Report.pdf",
        ),
        (
            "Copy   of   Report.pdf",
            "Report.pdf",
        ),
    ],
)
def test_normalize_name(
    original,
    expected,
):
    assert (
        DriveMigrator.normalize_name(
            original
        )
        == expected
    )


def test_normalize_name_does_not_remove_middle_copy_of():
    assert (
        DriveMigrator.normalize_name(
            "Archive Copy of Report.pdf"
        )
        == "Archive Copy of Report.pdf"
    )


# ----------------------------------------------------------------------
# Google-native MIME handling
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "mime_type",
    [
        GOOGLE_DOC_MIME,
        GOOGLE_SHEET_MIME,
        GOOGLE_SLIDES_MIME,
        "application/vnd.google-apps.form",
        "application/vnd.google-apps.drawing",
        FOLDER_MIME,
        SHORTCUT_MIME,
    ],
)
def test_is_google_native_mime(
    mime_type,
):
    assert (
        DriveMigrator._is_google_native_mime(
            mime_type
        )
        is True
    )


@pytest.mark.parametrize(
    "mime_type",
    [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/plain",
        "application/zip",
        None,
        "",
    ],
)
def test_is_not_google_native_mime(
    mime_type,
):
    assert (
        DriveMigrator._is_google_native_mime(
            mime_type
        )
        is False
    )


# ----------------------------------------------------------------------
# Collision suffix generation
# ----------------------------------------------------------------------


def test_add_collision_suffix_to_folder():
    assert (
        DriveMigrator._add_collision_suffix(
            "Reports",
            2,
            is_folder=True,
            mime_type=FOLDER_MIME,
        )
        == "Reports (2)"
    )


def test_add_collision_suffix_to_pdf():
    assert (
        DriveMigrator._add_collision_suffix(
            "Report.pdf",
            2,
            is_folder=False,
            mime_type="application/pdf",
        )
        == "Report (2).pdf"
    )


def test_add_collision_suffix_to_image():
    assert (
        DriveMigrator._add_collision_suffix(
            "Photo.jpg",
            3,
            is_folder=False,
            mime_type="image/jpeg",
        )
        == "Photo (3).jpg"
    )


def test_add_collision_suffix_to_file_without_extension():
    assert (
        DriveMigrator._add_collision_suffix(
            "README",
            2,
            is_folder=False,
            mime_type="text/plain",
        )
        == "README (2)"
    )


def test_add_collision_suffix_to_dotfile():
    assert (
        DriveMigrator._add_collision_suffix(
            ".env",
            2,
            is_folder=False,
            mime_type="text/plain",
        )
        == ".env (2)"
    )


def test_add_collision_suffix_preserves_final_extension():
    assert (
        DriveMigrator._add_collision_suffix(
            "archive.tar.gz",
            2,
            is_folder=False,
            mime_type="application/gzip",
        )
        == "archive.tar (2).gz"
    )


def test_google_doc_does_not_treat_period_as_extension():
    assert (
        DriveMigrator._add_collision_suffix(
            (
                "6.2.2021_RWG Fire Season "
                "Prep Mtg Agenda/Notes"
            ),
            2,
            is_folder=False,
            mime_type=GOOGLE_DOC_MIME,
        )
        == (
            "6.2.2021_RWG Fire Season "
            "Prep Mtg Agenda/Notes (2)"
        )
    )


def test_google_sheet_does_not_treat_period_as_extension():
    assert (
        DriveMigrator._add_collision_suffix(
            "Budget v2.1",
            2,
            is_folder=False,
            mime_type=GOOGLE_SHEET_MIME,
        )
        == "Budget v2.1 (2)"
    )


def test_google_slides_does_not_treat_period_as_extension():
    assert (
        DriveMigrator._add_collision_suffix(
            "Presentation 2026.08.21",
            2,
            is_folder=False,
            mime_type=GOOGLE_SLIDES_MIME,
        )
        == "Presentation 2026.08.21 (2)"
    )


def test_shortcut_name_is_treated_as_google_native():
    assert (
        DriveMigrator._add_collision_suffix(
            "Reference v2.1",
            2,
            is_folder=False,
            mime_type=SHORTCUT_MIME,
        )
        == "Reference v2.1 (2)"
    )


# ----------------------------------------------------------------------
# Source sibling-name allocation
# ----------------------------------------------------------------------


def test_allocate_source_names_without_collision(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    items = [
        {
            "id": "A",
            "name": "Report.pdf",
            "mimeType": "application/pdf",
        },
        {
            "id": "B",
            "name": "Projects",
            "mimeType": FOLDER_MIME,
        },
    ]

    result = (
        migrator._allocate_source_names(
            items
        )
    )

    by_id = {
        item["id"]: item
        for item in result
    }

    assert (
        by_id["A"]["target_name"]
        == "Report.pdf"
    )

    assert (
        by_id["B"]["target_name"]
        == "Projects"
    )


def test_allocate_source_names_resolves_pdf_copy_collision(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    items = [
        {
            "id": "A",
            "name": "Report.pdf",
            "mimeType": "application/pdf",
        },
        {
            "id": "B",
            "name": "Copy of Report.pdf",
            "mimeType": "application/pdf",
        },
    ]

    result = (
        migrator._allocate_source_names(
            items
        )
    )

    names = {
        item["target_name"]
        for item in result
    }

    assert names == {
        "Report.pdf",
        "Report (2).pdf",
    }


def test_allocate_google_doc_collision_suffixes_at_end(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    items = [
        {
            "id": "A",
            "name": (
                "6.2.2021_RWG Fire Season "
                "Prep Mtg Agenda/Notes"
            ),
            "mimeType": GOOGLE_DOC_MIME,
        },
        {
            "id": "B",
            "name": (
                "Copy of 6.2.2021_RWG Fire Season "
                "Prep Mtg Agenda/Notes"
            ),
            "mimeType": GOOGLE_DOC_MIME,
        },
    ]

    result = (
        migrator._allocate_source_names(
            items
        )
    )

    names = {
        item["target_name"]
        for item in result
    }

    assert names == {
        (
            "6.2.2021_RWG Fire Season "
            "Prep Mtg Agenda/Notes"
        ),
        (
            "6.2.2021_RWG Fire Season "
            "Prep Mtg Agenda/Notes (2)"
        ),
    }


def test_allocate_google_doc_repeated_copy_prefixes(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    items = [
        {
            "id": "A",
            "name": "Meeting Notes v2.1",
            "mimeType": GOOGLE_DOC_MIME,
        },
        {
            "id": "B",
            "name": "Copy of Meeting Notes v2.1",
            "mimeType": GOOGLE_DOC_MIME,
        },
        {
            "id": "C",
            "name": (
                "Copy of Copy of "
                "Meeting Notes v2.1"
            ),
            "mimeType": GOOGLE_DOC_MIME,
        },
    ]

    result = (
        migrator._allocate_source_names(
            items
        )
    )

    names = {
        item["target_name"]
        for item in result
    }

    assert names == {
        "Meeting Notes v2.1",
        "Meeting Notes v2.1 (2)",
        "Meeting Notes v2.1 (3)",
    }


def test_allocate_duplicate_folder_names(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    items = [
        {
            "id": "A",
            "name": "Notes",
            "mimeType": FOLDER_MIME,
        },
        {
            "id": "B",
            "name": "Notes",
            "mimeType": FOLDER_MIME,
        },
        {
            "id": "C",
            "name": "Notes",
            "mimeType": FOLDER_MIME,
        },
    ]

    result = (
        migrator._allocate_source_names(
            items
        )
    )

    names = {
        item["target_name"]
        for item in result
    }

    assert names == {
        "Notes",
        "Notes (2)",
        "Notes (3)",
    }


def test_allocate_file_and_folder_use_separate_namespaces(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    items = [
        {
            "id": "FILE",
            "name": "Reports",
            "mimeType": GOOGLE_DOC_MIME,
        },
        {
            "id": "FOLDER",
            "name": "Reports",
            "mimeType": FOLDER_MIME,
        },
    ]

    result = (
        migrator._allocate_source_names(
            items
        )
    )

    by_id = {
        item["id"]: item
        for item in result
    }

    assert (
        by_id["FILE"]["target_name"]
        == "Reports"
    )

    assert (
        by_id["FOLDER"]["target_name"]
        == "Reports"
    )


def test_allocate_source_names_is_deterministic(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    items = [
        {
            "id": "C",
            "name": "Copy of Report.pdf",
            "mimeType": "application/pdf",
        },
        {
            "id": "A",
            "name": "Report.pdf",
            "mimeType": "application/pdf",
        },
        {
            "id": "B",
            "name": "Copy of Report.pdf",
            "mimeType": "application/pdf",
        },
    ]

    first = (
        migrator._allocate_source_names(
            items
        )
    )

    second = (
        migrator._allocate_source_names(
            list(
                reversed(
                    items
                )
            )
        )
    )

    first_map = {
        item["id"]: item["target_name"]
        for item in first
    }

    second_map = {
        item["id"]: item["target_name"]
        for item in second
    }

    assert first_map == second_map


# ----------------------------------------------------------------------
# Destination collision-name allocation
# ----------------------------------------------------------------------


def test_next_destination_name_for_pdf(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    used = {
        "report.pdf",
        "report (2).pdf",
    }

    assert (
        migrator._next_available_destination_name(
            "Report.pdf",
            False,
            "application/pdf",
            used,
        )
        == "Report (3).pdf"
    )


def test_next_destination_name_for_google_doc(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    used = {
        "meeting notes v2.1",
        "meeting notes v2.1 (2)",
    }

    assert (
        migrator._next_available_destination_name(
            "Meeting Notes v2.1",
            False,
            GOOGLE_DOC_MIME,
            used,
        )
        == "Meeting Notes v2.1 (3)"
    )


def test_next_destination_name_for_folder(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    used = {
        "marxi gras",
        "marxi gras (2)",
    }

    assert (
        migrator._next_available_destination_name(
            "Marxi Gras",
            True,
            FOLDER_MIME,
            used,
        )
        == "Marxi Gras (3)"
    )


# ----------------------------------------------------------------------
# Relative path generation
# ----------------------------------------------------------------------


def test_join_relative_at_root():
    assert (
        DriveMigrator._join_relative(
            "",
            "Folder",
        )
        == "Folder"
    )


def test_join_relative_nested():
    assert (
        DriveMigrator._join_relative(
            "Department/Projects",
            "Report.pdf",
        )
        == (
            "Department/Projects/"
            "Report.pdf"
        )
    )


# ----------------------------------------------------------------------
# Inventory indexing
# ----------------------------------------------------------------------


def test_index_by_path():
    inventory = {
        "1": {
            "relative_path": "Folder",
            "mimeType": FOLDER_MIME,
        },
        "2": {
            "relative_path": (
                "Folder/Report.pdf"
            ),
            "mimeType": "application/pdf",
        },
    }

    index = (
        DriveMigrator._index_by_path(
            inventory
        )
    )

    assert (
        len(index["Folder"])
        == 1
    )

    assert (
        index["Folder"][0][
            "mimeType"
        ]
        == FOLDER_MIME
    )

    assert (
        index[
            "Folder/Report.pdf"
        ][0]["mimeType"]
        == "application/pdf"
    )


def test_index_by_path_preserves_duplicates():
    inventory = {
        "1": {
            "relative_path": "Report.pdf",
            "mimeType": "application/pdf",
        },
        "2": {
            "relative_path": "Report.pdf",
            "mimeType": "application/pdf",
        },
    }

    index = (
        DriveMigrator._index_by_path(
            inventory
        )
    )

    assert (
        len(
            index["Report.pdf"]
        )
        == 2
    )


# ----------------------------------------------------------------------
# Destination matching
# ----------------------------------------------------------------------


def test_single_match_returns_file():
    index = {
        "Report.pdf": [
            {
                "id": "FILE_ID",
                "mimeType": "application/pdf",
            }
        ]
    }

    result = (
        DriveMigrator._single_match(
            index,
            "Report.pdf",
            want_folder=False,
        )
    )

    assert (
        result["id"]
        == "FILE_ID"
    )


def test_single_match_returns_folder():
    index = {
        "Reports": [
            {
                "id": "FOLDER_ID",
                "mimeType": FOLDER_MIME,
            }
        ]
    }

    result = (
        DriveMigrator._single_match(
            index,
            "Reports",
            want_folder=True,
        )
    )

    assert (
        result["id"]
        == "FOLDER_ID"
    )


def test_single_match_distinguishes_file_and_folder():
    index = {
        "Reports": [
            {
                "id": "FILE_ID",
                "mimeType": GOOGLE_DOC_MIME,
            },
            {
                "id": "FOLDER_ID",
                "mimeType": FOLDER_MIME,
            },
        ]
    }

    folder = (
        DriveMigrator._single_match(
            index,
            "Reports",
            want_folder=True,
        )
    )

    file_item = (
        DriveMigrator._single_match(
            index,
            "Reports",
            want_folder=False,
        )
    )

    assert (
        folder["id"]
        == "FOLDER_ID"
    )

    assert (
        file_item["id"]
        == "FILE_ID"
    )


def test_single_match_returns_none_when_missing():
    assert (
        DriveMigrator._single_match(
            {},
            "Missing.pdf",
            want_folder=False,
        )
        is None
    )


def test_single_match_rejects_multiple_files():
    index = {
        "Report.pdf": [
            {
                "id": "A",
                "mimeType": "application/pdf",
            },
            {
                "id": "B",
                "mimeType": "application/pdf",
            },
        ]
    }

    with pytest.raises(
        RuntimeError,
        match="multiple files",
    ):
        DriveMigrator._single_match(
            index,
            "Report.pdf",
            want_folder=False,
        )


def test_single_match_rejects_multiple_folders():
    index = {
        "Reports": [
            {
                "id": "A",
                "mimeType": FOLDER_MIME,
            },
            {
                "id": "B",
                "mimeType": FOLDER_MIME,
            },
        ]
    }

    with pytest.raises(
        RuntimeError,
        match="multiple folders",
    ):
        DriveMigrator._single_match(
            index,
            "Reports",
            want_folder=True,
        )


# ----------------------------------------------------------------------
# Manifest persistence
# ----------------------------------------------------------------------


def test_write_and_load_manifest(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    expected = {
        "migration_metadata": {
            "source_root_id": "SOURCE",
            "dest_root_id": "DEST",
        },
        "tasks": [],
    }

    helpers.write_manifest(
        expected
    )

    assert (
        helpers.load_manifest()
        == expected
    )


def test_manifest_write_produces_valid_json(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    helpers.write_manifest(
        {
            "tasks": [
                {
                    "task_id": "123",
                    "status": "pending",
                }
            ]
        }
    )

    parsed = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        parsed["tasks"][0][
            "task_id"
        ]
        == "123"
    )


def test_load_manifest_missing_file(
    tmp_path,
):
    helpers = MigrationHelpers(
        service=None,
        work_list_path=(
            tmp_path
            / "missing.json"
        ),
    )

    with pytest.raises(
        FileNotFoundError
    ):
        helpers.load_manifest()


def test_load_manifest_empty_file(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    manifest_path.touch()

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    with pytest.raises(
        RuntimeError,
        match="empty",
    ):
        helpers.load_manifest()


# ----------------------------------------------------------------------
# Arbitrary task updates
# ----------------------------------------------------------------------


def test_update_task(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    helpers.write_manifest(
        {
            "tasks": [
                {
                    "task_id": "TASK1",
                    "status": "pending",
                }
            ]
        }
    )

    updated = helpers.update_task(
        "TASK1",
        dest_id="DEST1",
    )

    assert (
        updated["dest_id"]
        == "DEST1"
    )

    assert (
        helpers.load_manifest()
        ["tasks"][0]["dest_id"]
        == "DEST1"
    )


def test_update_task_accepts_new_schema_fields(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    helpers.write_manifest(
        {
            "tasks": [
                {
                    "task_id": "TASK1",
                    "status": "pending",
                }
            ]
        }
    )

    updated = helpers.update_task(
        "TASK1",
        failure_phase=(
            FAILURE_PHASE_EXECUTION
        ),
        staged_file_id="STAGED1",
        custom_future_field="VALUE",
    )

    assert (
        updated["failure_phase"]
        == FAILURE_PHASE_EXECUTION
    )

    assert (
        updated["staged_file_id"]
        == "STAGED1"
    )

    assert (
        updated["custom_future_field"]
        == "VALUE"
    )


def test_update_task_rejects_unknown_task(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    helpers.write_manifest(
        {
            "tasks": []
        }
    )

    with pytest.raises(
        KeyError,
        match="not found",
    ):
        helpers.update_task(
            "UNKNOWN",
            status="completed",
        )


# ----------------------------------------------------------------------
# Task status / failure phase
# ----------------------------------------------------------------------


def test_update_task_status(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    helpers.write_manifest(
        {
            "tasks": [
                {
                    "task_id": "TASK1",
                    "status": "pending",
                    "error_message": None,
                    "failure_phase": None,
                }
            ]
        }
    )

    helpers.update_task_status(
        "TASK1",
        "completed",
        dest_id="DEST1",
        failure_phase=None,
    )

    task = (
        helpers.load_manifest()
        ["tasks"][0]
    )

    assert (
        task["status"]
        == "completed"
    )

    assert (
        task["dest_id"]
        == "DEST1"
    )

    assert (
        task["error_message"]
        is None
    )

    assert (
        task["failure_phase"]
        is None
    )


def test_execution_failure_records_failure_phase(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    helpers.write_manifest(
        {
            "tasks": [
                {
                    "task_id": "TASK1",
                    "status": "pending",
                }
            ]
        }
    )

    helpers.update_task_status(
        "TASK1",
        "failed",
        "Permission denied",
        failure_phase=(
            FAILURE_PHASE_EXECUTION
        ),
    )

    task = (
        helpers.load_manifest()
        ["tasks"][0]
    )

    assert (
        task["status"]
        == "failed"
    )

    assert (
        task["error_message"]
        == "Permission denied"
    )

    assert (
        task["failure_phase"]
        == FAILURE_PHASE_EXECUTION
    )


def test_manifest_failure_records_failure_phase(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    helpers.write_manifest(
        {
            "tasks": [
                {
                    "task_id": "TASK1",
                    "status": "pending",
                }
            ]
        }
    )

    helpers.update_task_status(
        "TASK1",
        "failed",
        (
            "Destination contains multiple "
            "folders."
        ),
        failure_phase=(
            FAILURE_PHASE_MANIFEST
        ),
    )

    task = (
        helpers.load_manifest()
        ["tasks"][0]
    )

    assert (
        task["status"]
        == "failed"
    )

    assert (
        task["failure_phase"]
        == FAILURE_PHASE_MANIFEST
    )


def test_status_transition_clears_previous_error(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    helpers.write_manifest(
        {
            "tasks": [
                {
                    "task_id": "TASK1",
                    "status": "failed",
                    "error_message": (
                        "Temporary API failure"
                    ),
                    "failure_phase": (
                        FAILURE_PHASE_EXECUTION
                    ),
                }
            ]
        }
    )

    helpers.update_task_status(
        "TASK1",
        "in_progress",
        failure_phase=None,
    )

    task = (
        helpers.load_manifest()
        ["tasks"][0]
    )

    assert (
        task["status"]
        == "in_progress"
    )

    assert (
        task["error_message"]
        is None
    )

    assert (
        task["failure_phase"]
        is None
    )


def test_completed_status_clears_previous_failure(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    helpers.write_manifest(
        {
            "tasks": [
                {
                    "task_id": "TASK1",
                    "status": "failed",
                    "error_message": "Network error",
                    "failure_phase": (
                        FAILURE_PHASE_EXECUTION
                    ),
                }
            ]
        }
    )

    helpers.update_task_status(
        "TASK1",
        "completed",
        dest_id="DEST1",
        failure_phase=None,
    )

    task = (
        helpers.load_manifest()
        ["tasks"][0]
    )

    assert (
        task["status"]
        == "completed"
    )

    assert (
        task["dest_id"]
        == "DEST1"
    )

    assert (
        task["error_message"]
        is None
    )

    assert (
        task["failure_phase"]
        is None
    )


# ----------------------------------------------------------------------
# Metadata updates
# ----------------------------------------------------------------------


def test_update_metadata(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    helpers.write_manifest(
        {
            "migration_metadata": {
                "source_root_id": "SOURCE",
            },
            "tasks": [],
        }
    )

    metadata = (
        helpers.update_metadata(
            dest_root_id="DEST"
        )
    )

    assert (
        metadata["source_root_id"]
        == "SOURCE"
    )

    assert (
        metadata["dest_root_id"]
        == "DEST"
    )

    assert (
        metadata["updated_at"]
    )


def test_update_metadata_can_store_staging_folder_id(
    tmp_path,
):
    manifest_path = (
        tmp_path
        / "migration_work_list.json"
    )

    helpers = MigrationHelpers(
        service=None,
        work_list_path=manifest_path,
    )

    helpers.write_manifest(
        {
            "migration_metadata": {},
            "tasks": [],
        }
    )

    helpers.update_metadata(
        staging_folder_id="STAGING"
    )

    metadata = (
        helpers.load_manifest()
        ["migration_metadata"]
    )

    assert (
        metadata["staging_folder_id"]
        == "STAGING"
    )


# ----------------------------------------------------------------------
# Folder map recovery
# ----------------------------------------------------------------------


def test_load_folder_map_includes_roots(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    manifest = {
        "migration_metadata": {
            "source_root_id": "SOURCE",
            "dest_root_id": "DEST",
            "folder_map": {},
        },
        "tasks": [],
    }

    result = (
        migrator._load_folder_map(
            manifest
        )
    )

    assert (
        result["SOURCE"]
        == "DEST"
    )


def test_load_folder_map_rehydrates_completed_folder_tasks(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    manifest = {
        "migration_metadata": {
            "source_root_id": "SOURCE",
            "dest_root_id": "DEST",
            "folder_map": {},
        },
        "tasks": [
            {
                "type": "folder_creation",
                "source_id": "SOURCE_CHILD",
                "dest_id": "DEST_CHILD",
                "status": "completed",
            }
        ],
    }

    result = (
        migrator._load_folder_map(
            manifest
        )
    )

    assert (
        result["SOURCE"]
        == "DEST"
    )

    assert (
        result["SOURCE_CHILD"]
        == "DEST_CHILD"
    )


def test_load_folder_map_ignores_failed_folder_tasks(
    tmp_path,
):
    migrator = make_migrator_without_auth(
        tmp_path
    )

    manifest = {
        "migration_metadata": {
            "source_root_id": "SOURCE",
            "dest_root_id": "DEST",
            "folder_map": {},
        },
        "tasks": [
            {
                "type": "folder_creation",
                "source_id": "SOURCE_CHILD",
                "dest_id": "DEST_CHILD",
                "status": "failed",
                "failure_phase": (
                    FAILURE_PHASE_EXECUTION
                ),
            }
        ],
    }

    result = (
        migrator._load_folder_map(
            manifest
        )
    )

    assert (
        "SOURCE_CHILD"
        not in result
    )