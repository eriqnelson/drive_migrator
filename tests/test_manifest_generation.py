from unittest.mock import MagicMock

import pytest

from drive_migrator.migrator_engine import (
    DriveMigrator,
    FOLDER_MIME,
)
from drive_migrator.migration_helpers import (
    MigrationHelpers,
)


def make_migrator(tmp_path):
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

    migrator.service = MagicMock()

    migrator.helpers = MigrationHelpers(
        service=migrator.service,
        work_list_path=(
            migrator.work_list_path
        ),
    )

    migrator.log_message = MagicMock()

    return migrator


def folder(
    file_id,
    name,
    parent_id,
    relative_path,
    depth,
):
    return {
        "id": file_id,
        "original_name": name,
        "name": name,
        "mimeType": FOLDER_MIME,
        "size": None,
        "md5Checksum": None,
        "modifiedTime": None,
        "parent_id": parent_id,
        "relative_path": relative_path,
        "parent_relative_path": (
            relative_path.rpartition("/")[0]
        ),
        "depth": depth,
    }


def file_item(
    file_id,
    name,
    parent_id,
    relative_path,
    depth,
    mime_type="application/pdf",
    size="100",
    md5="abc123",
):
    return {
        "id": file_id,
        "original_name": name,
        "name": name,
        "mimeType": mime_type,
        "size": size,
        "md5Checksum": md5,
        "modifiedTime": (
            "2026-01-01T00:00:00Z"
        ),
        "parent_id": parent_id,
        "relative_path": relative_path,
        "parent_relative_path": (
            relative_path.rpartition("/")[0]
        ),
        "depth": depth,
    }


def test_manifest_generation_empty_source(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    migrator.scan_folder = MagicMock(
        side_effect=[
            {},
            {},
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    assert (
        manifest[
            "migration_metadata"
        ]["source_root_id"]
        == "SOURCE_ROOT"
    )

    assert (
        manifest[
            "migration_metadata"
        ]["dest_root_id"]
        == "DEST_ROOT"
    )

    assert (
        manifest[
            "migration_metadata"
        ]["folder_map"]
        == {
            "SOURCE_ROOT": "DEST_ROOT"
        }
    )

    assert manifest["tasks"] == []

    saved = (
        migrator.helpers.load_manifest()
    )

    assert saved == manifest


def test_manifest_generation_creates_folder_task(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "SOURCE_FOLDER": folder(
            file_id="SOURCE_FOLDER",
            name="Projects",
            parent_id="SOURCE_ROOT",
            relative_path="Projects",
            depth=1,
        )
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            {},
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    assert len(
        manifest["tasks"]
    ) == 1

    task = manifest["tasks"][0]

    assert (
        task["type"]
        == "folder_creation"
    )

    assert (
        task["source_id"]
        == "SOURCE_FOLDER"
    )

    assert (
        task["source_parent_id"]
        == "SOURCE_ROOT"
    )

    assert (
        task["target_name"]
        == "Projects"
    )

    assert (
        task["relative_path"]
        == "Projects"
    )

    assert (
        task["status"]
        == "pending"
    )

    assert task["dest_id"] is None

    assert (
        task["dest_parent_id"]
        == "DEST_ROOT"
    )

    assert (
        task["reconciled_existing"]
        is False
    )


def test_manifest_generation_creates_file_task(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "SOURCE_FILE": file_item(
            file_id="SOURCE_FILE",
            name="Report.pdf",
            parent_id="SOURCE_ROOT",
            relative_path="Report.pdf",
            depth=1,
        )
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            {},
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    assert len(
        manifest["tasks"]
    ) == 1

    task = manifest["tasks"][0]

    assert (
        task["type"]
        == "file_migration"
    )

    assert (
        task["source_id"]
        == "SOURCE_FILE"
    )

    assert (
        task["source_parent_id"]
        == "SOURCE_ROOT"
    )

    assert (
        task["target_name"]
        == "Report.pdf"
    )

    assert (
        task["relative_path"]
        == "Report.pdf"
    )

    assert (
        task["source_size"]
        == "100"
    )

    assert (
        task["source_md5"]
        == "abc123"
    )

    assert (
        task["staged_file_id"]
        is None
    )

    assert (
        task["dest_parent_id"]
        == "DEST_ROOT"
    )

    assert (
        task["status"]
        == "pending"
    )


def test_manifest_reconciles_existing_folder(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "SOURCE_FOLDER": folder(
            file_id="SOURCE_FOLDER",
            name="Projects",
            parent_id="SOURCE_ROOT",
            relative_path="Projects",
            depth=1,
        )
    }

    dest_inventory = {
        "DEST_FOLDER": folder(
            file_id="DEST_FOLDER",
            name="Projects",
            parent_id="DEST_ROOT",
            relative_path="Projects",
            depth=1,
        )
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            dest_inventory,
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    task = manifest["tasks"][0]

    assert (
        task["status"]
        == "completed"
    )

    assert (
        task["dest_id"]
        == "DEST_FOLDER"
    )

    assert (
        task["reconciled_existing"]
        is True
    )

    assert (
        manifest[
            "migration_metadata"
        ]["folder_map"][
            "SOURCE_FOLDER"
        ]
        == "DEST_FOLDER"
    )


def test_manifest_reconciles_existing_file(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "SOURCE_FILE": file_item(
            file_id="SOURCE_FILE",
            name="Report.pdf",
            parent_id="SOURCE_ROOT",
            relative_path="Report.pdf",
            depth=1,
        )
    }

    dest_inventory = {
        "DEST_FILE": file_item(
            file_id="DEST_FILE",
            name="Report.pdf",
            parent_id="DEST_ROOT",
            relative_path="Report.pdf",
            depth=1,
        )
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            dest_inventory,
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    task = manifest["tasks"][0]

    assert (
        task["status"]
        == "completed"
    )

    assert (
        task["dest_id"]
        == "DEST_FILE"
    )

    assert (
        task["reconciled_existing"]
        is True
    )


def test_manifest_uses_existing_parent_folder_mapping_for_nested_file(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "SOURCE_FOLDER": folder(
            file_id="SOURCE_FOLDER",
            name="Projects",
            parent_id="SOURCE_ROOT",
            relative_path="Projects",
            depth=1,
        ),
        "SOURCE_FILE": file_item(
            file_id="SOURCE_FILE",
            name="Plan.pdf",
            parent_id="SOURCE_FOLDER",
            relative_path=(
                "Projects/Plan.pdf"
            ),
            depth=2,
        ),
    }

    dest_inventory = {
        "DEST_FOLDER": folder(
            file_id="DEST_FOLDER",
            name="Projects",
            parent_id="DEST_ROOT",
            relative_path="Projects",
            depth=1,
        )
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            dest_inventory,
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    file_task = next(
        task
        for task in manifest["tasks"]
        if (
            task["type"]
            == "file_migration"
        )
    )

    assert (
        file_task["dest_parent_id"]
        == "DEST_FOLDER"
    )


def test_manifest_nested_file_parent_unresolved_when_folder_missing(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "SOURCE_FOLDER": folder(
            file_id="SOURCE_FOLDER",
            name="Projects",
            parent_id="SOURCE_ROOT",
            relative_path="Projects",
            depth=1,
        ),
        "SOURCE_FILE": file_item(
            file_id="SOURCE_FILE",
            name="Plan.pdf",
            parent_id="SOURCE_FOLDER",
            relative_path=(
                "Projects/Plan.pdf"
            ),
            depth=2,
        ),
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            {},
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    file_task = next(
        task
        for task in manifest["tasks"]
        if (
            task["type"]
            == "file_migration"
        )
    )

    assert (
        file_task["dest_parent_id"]
        is None
    )


def test_manifest_orders_folders_before_files(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "SOURCE_FILE": file_item(
            file_id="SOURCE_FILE",
            name="Root.pdf",
            parent_id="SOURCE_ROOT",
            relative_path="Root.pdf",
            depth=1,
        ),
        "SOURCE_FOLDER": folder(
            file_id="SOURCE_FOLDER",
            name="Projects",
            parent_id="SOURCE_ROOT",
            relative_path="Projects",
            depth=1,
        ),
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            {},
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    assert (
        manifest["tasks"][0]["type"]
        == "folder_creation"
    )

    assert (
        manifest["tasks"][1]["type"]
        == "file_migration"
    )


def test_manifest_orders_folders_by_depth(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "CHILD": folder(
            file_id="CHILD",
            name="Child",
            parent_id="PARENT",
            relative_path=(
                "Parent/Child"
            ),
            depth=2,
        ),
        "PARENT": folder(
            file_id="PARENT",
            name="Parent",
            parent_id="SOURCE_ROOT",
            relative_path="Parent",
            depth=1,
        ),
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            {},
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    folder_tasks = [
        task
        for task in manifest["tasks"]
        if (
            task["type"]
            == "folder_creation"
        )
    ]

    assert (
        folder_tasks[0][
            "source_id"
        ]
        == "PARENT"
    )

    assert (
        folder_tasks[1][
            "source_id"
        ]
        == "CHILD"
    )


def test_manifest_orders_same_depth_paths_case_insensitively(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "B": folder(
            file_id="B",
            name="beta",
            parent_id="SOURCE_ROOT",
            relative_path="beta",
            depth=1,
        ),
        "A": folder(
            file_id="A",
            name="Alpha",
            parent_id="SOURCE_ROOT",
            relative_path="Alpha",
            depth=1,
        ),
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            {},
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    assert [
        task["relative_path"]
        for task in manifest["tasks"]
    ] == [
        "Alpha",
        "beta",
    ]


def test_manifest_rejects_source_collision(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "A": file_item(
            file_id="A",
            name="Report.pdf",
            parent_id="SOURCE_ROOT",
            relative_path="Report.pdf",
            depth=1,
        ),
        "B": file_item(
            file_id="B",
            name="Report.pdf",
            parent_id="SOURCE_ROOT",
            relative_path="Report.pdf",
            depth=1,
        ),
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            {},
        ]
    )

    with pytest.raises(
        RuntimeError,
        match="duplicate paths",
    ):
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )

    assert (
        migrator.work_list_path.exists()
        is False
    )


def test_manifest_rejects_ambiguous_destination_file(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "SOURCE_FILE": file_item(
            file_id="SOURCE_FILE",
            name="Report.pdf",
            parent_id="SOURCE_ROOT",
            relative_path="Report.pdf",
            depth=1,
        )
    }

    dest_inventory = {
        "DEST_A": file_item(
            file_id="DEST_A",
            name="Report.pdf",
            parent_id="DEST_ROOT",
            relative_path="Report.pdf",
            depth=1,
        ),
        "DEST_B": file_item(
            file_id="DEST_B",
            name="Report.pdf",
            parent_id="DEST_ROOT",
            relative_path="Report.pdf",
            depth=1,
        ),
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            dest_inventory,
        ]
    )

    with pytest.raises(
        RuntimeError,
        match="multiple files",
    ):
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )


def test_manifest_allows_file_and_folder_same_destination_path(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "SOURCE_FOLDER": folder(
            file_id="SOURCE_FOLDER",
            name="Reports",
            parent_id="SOURCE_ROOT",
            relative_path="Reports",
            depth=1,
        ),
        "SOURCE_FILE": file_item(
            file_id="SOURCE_FILE",
            name="Reports",
            parent_id="SOURCE_ROOT",
            relative_path="Reports",
            depth=1,
        ),
    }

    dest_inventory = {
        "DEST_FOLDER": folder(
            file_id="DEST_FOLDER",
            name="Reports",
            parent_id="DEST_ROOT",
            relative_path="Reports",
            depth=1,
        ),
        "DEST_FILE": file_item(
            file_id="DEST_FILE",
            name="Reports",
            parent_id="DEST_ROOT",
            relative_path="Reports",
            depth=1,
        ),
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            dest_inventory,
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    folder_task = next(
        task
        for task in manifest["tasks"]
        if (
            task["type"]
            == "folder_creation"
        )
    )

    file_task = next(
        task
        for task in manifest["tasks"]
        if (
            task["type"]
            == "file_migration"
        )
    )

    assert (
        folder_task["dest_id"]
        == "DEST_FOLDER"
    )

    assert (
        file_task["dest_id"]
        == "DEST_FILE"
    )


def test_manifest_generates_unique_task_ids(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "FILE1": file_item(
            file_id="FILE1",
            name="One.pdf",
            parent_id="SOURCE_ROOT",
            relative_path="One.pdf",
            depth=1,
        ),
        "FILE2": file_item(
            file_id="FILE2",
            name="Two.pdf",
            parent_id="SOURCE_ROOT",
            relative_path="Two.pdf",
            depth=1,
        ),
        "FOLDER1": folder(
            file_id="FOLDER1",
            name="Projects",
            parent_id="SOURCE_ROOT",
            relative_path="Projects",
            depth=1,
        ),
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            {},
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    task_ids = [
        task["task_id"]
        for task in manifest["tasks"]
    ]

    assert (
        len(task_ids)
        == len(set(task_ids))
    )


def test_manifest_records_timestamps(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    migrator.scan_folder = MagicMock(
        side_effect=[
            {},
            {},
        ]
    )

    manifest = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    metadata = (
        manifest[
            "migration_metadata"
        ]
    )

    assert (
        metadata["created_at"]
    )

    assert (
        metadata["updated_at"]
    )

    assert (
        metadata["created_at"]
        == metadata["updated_at"]
    )


def test_manifest_persists_to_disk(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "SOURCE_FILE": file_item(
            file_id="SOURCE_FILE",
            name="Report.pdf",
            parent_id="SOURCE_ROOT",
            relative_path="Report.pdf",
            depth=1,
        )
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            {},
        ]
    )

    returned = (
        migrator.generate_fresh_sync_manifest(
            "SOURCE_ROOT",
            "DEST_ROOT",
        )
    )

    saved = (
        migrator.helpers.load_manifest()
    )

    assert saved == returned


def test_manifest_logs_generation_summary(
    tmp_path,
):
    migrator = make_migrator(
        tmp_path
    )

    source_inventory = {
        "SOURCE_FILE": file_item(
            file_id="SOURCE_FILE",
            name="Report.pdf",
            parent_id="SOURCE_ROOT",
            relative_path="Report.pdf",
            depth=1,
        )
    }

    migrator.scan_folder = MagicMock(
        side_effect=[
            source_inventory,
            {},
        ]
    )

    migrator.generate_fresh_sync_manifest(
        "SOURCE_ROOT",
        "DEST_ROOT",
    )

    messages = [
        call.args[0]
        for call
        in migrator.log_message.call_args_list
    ]

    assert (
        "Starting fresh manifest generation"
        in messages
    )

    assert any(
        "1 tasks"
        in message
        and "1 pending"
        in message
        for message in messages
    )