import datetime
import json
from pathlib import Path
from typing import Any, Dict, Optional


FOLDER_MIME = "application/vnd.google-apps.folder"

STAGING_TASK_PROPERTY = "driveMigratorTaskId"

STAGING_FOLDER_PROPERTY = "driveMigratorStagingFolder"
STAGING_FOLDER_PROPERTY_VALUE = "1"

DEFAULT_STAGING_FOLDER_NAME = "Drive Migrator Staging"


class MigrationHelpers:
    """
    Helper methods for:

    - migration manifest persistence
    - task-state updates
    - My Drive staging-folder management
    - staging-copy discovery
    - staging-copy creation
    - final movement into the destination Drive

    Files are staged in a dedicated folder under the authenticated user's
    My Drive rather than in the source folder.

    This is important when the user can read/copy an item but cannot create
    new files inside the source item's parent folder.
    """

    def __init__(
        self,
        service,
        work_list_path,
    ):
        self.service = service
        self.work_list_path = Path(
            work_list_path
        )

    # ------------------------------------------------------------------
    # Manifest persistence
    # ------------------------------------------------------------------

    def load_manifest(
        self,
    ) -> Dict[str, Any]:
        """
        Load and return the migration manifest.

        Raises:
            FileNotFoundError:
                If the manifest does not exist.

            RuntimeError:
                If the manifest exists but is empty.

            json.JSONDecodeError:
                If the manifest contains invalid JSON.
        """
        if not self.work_list_path.exists():
            raise FileNotFoundError(
                "Migration manifest not found: "
                f"{self.work_list_path}"
            )

        raw = self.work_list_path.read_text(
            encoding="utf-8"
        )

        if not raw.strip():
            raise RuntimeError(
                "Migration manifest is empty: "
                f"{self.work_list_path}"
            )

        return json.loads(
            raw
        )

    def write_manifest(
        self,
        manifest: Dict[str, Any],
    ) -> None:
        """
        Persist the migration manifest using a temporary file followed by
        replacement of the live manifest.

        This prevents most ordinary interruptions from leaving a partially
        written JSON document.
        """
        self.work_list_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = (
            self.work_list_path.with_suffix(
                self.work_list_path.suffix
                + ".tmp"
            )
        )

        temporary_path.write_text(
            json.dumps(
                manifest,
                indent=2,
                sort_keys=False,
            )
            + "\n",
            encoding="utf-8",
        )

        temporary_path.replace(
            self.work_list_path
        )

    # ------------------------------------------------------------------
    # Task updates
    # ------------------------------------------------------------------

    def update_task(
        self,
        task_id: str,
        **updates,
    ) -> Dict[str, Any]:
        """
        Update arbitrary fields on one manifest task.

        Arbitrary keyword fields are intentionally accepted so the manifest
        schema can evolve without requiring changes here for every new task
        property.
        """
        manifest = (
            self.load_manifest()
        )

        tasks = manifest.get(
            "tasks",
            [],
        )

        target = None

        for task in tasks:
            if (
                task.get("task_id")
                == task_id
            ):
                target = task
                break

        if target is None:
            raise KeyError(
                "Migration task not found: "
                f"{task_id}"
            )

        target.update(
            updates
        )

        metadata = (
            manifest.setdefault(
                "migration_metadata",
                {},
            )
        )

        metadata[
            "updated_at"
        ] = (
            datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
        )

        self.write_manifest(
            manifest
        )

        return target

    def update_task_status(
        self,
        task_id: str,
        status: str,
        error_message: Optional[str] = None,
        **updates,
    ) -> Dict[str, Any]:
        """
        Update task status and any associated task fields.

        error_message is always written explicitly. Passing None clears an
        older failure message when a retry succeeds or re-enters progress.
        """
        task_updates = {
            "status": status,
            "error_message": error_message,
        }

        task_updates.update(
            updates
        )

        return self.update_task(
            task_id,
            **task_updates,
        )

    def update_metadata(
        self,
        **updates,
    ) -> Dict[str, Any]:
        """
        Update migration-level metadata.
        """
        manifest = (
            self.load_manifest()
        )

        metadata = (
            manifest.setdefault(
                "migration_metadata",
                {},
            )
        )

        metadata.update(
            updates
        )

        metadata[
            "updated_at"
        ] = (
            datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
        )

        self.write_manifest(
            manifest
        )

        return metadata

    # ------------------------------------------------------------------
    # My Drive staging-folder management
    # ------------------------------------------------------------------

    def get_or_create_staging_folder(
        self,
        folder_name: str = DEFAULT_STAGING_FOLDER_NAME,
    ) -> str:
        """
        Return the dedicated Drive Migrator staging folder in My Drive.

        The folder is identified primarily with an appProperty rather than
        by display name, so renaming it manually does not break recovery.

        The staging folder is explicitly created beneath the special
        ``root`` parent. For a user OAuth credential, ``root`` refers to
        that user's My Drive root.

        If more than one marked staging folder exists under My Drive root,
        refuse to choose one automatically.
        """
        if self.service is None:
            raise RuntimeError(
                "Google Drive service is not configured."
            )

        escaped_property = (
            STAGING_FOLDER_PROPERTY_VALUE.replace(
                "'",
                "\\'",
            )
        )

        query = (
            "trashed = false "
            f"and mimeType = '{FOLDER_MIME}' "
            "and 'root' in parents "
            "and appProperties has "
            "{ "
            f"key='{STAGING_FOLDER_PROPERTY}' "
            f"and value='{escaped_property}' "
            "}"
        )

        result = (
            self.service.files()
            .list(
                q=query,
                spaces="drive",
                corpora="user",
                fields=(
                    "files("
                    "id,"
                    "name,"
                    "mimeType,"
                    "parents,"
                    "driveId,"
                    "appProperties"
                    ")"
                ),
                pageSize=10,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )

        candidates = []

        for item in result.get(
            "files",
            [],
        ):
            # A My Drive object does not have a shared-drive driveId.
            if item.get("driveId"):
                continue

            candidates.append(
                item
            )

        if len(candidates) > 1:
            raise RuntimeError(
                "Found multiple Drive Migrator staging "
                "folders in My Drive. Refusing to choose "
                "one automatically."
            )

        if candidates:
            return candidates[0]["id"]

        created = (
            self.service.files()
            .create(
                body={
                    "name": folder_name,
                    "mimeType": FOLDER_MIME,
                    "parents": [
                        "root"
                    ],
                    "appProperties": {
                        STAGING_FOLDER_PROPERTY: (
                            STAGING_FOLDER_PROPERTY_VALUE
                        )
                    },
                },
                supportsAllDrives=True,
                fields=(
                    "id,"
                    "name,"
                    "mimeType,"
                    "parents,"
                    "driveId,"
                    "appProperties"
                ),
            )
            .execute()
        )

        staging_folder_id = (
            created.get(
                "id"
            )
        )

        if not staging_folder_id:
            raise RuntimeError(
                "Google Drive did not return an ID "
                "when creating the My Drive staging folder."
            )

        if created.get("driveId"):
            raise RuntimeError(
                "Drive Migrator staging folder was unexpectedly "
                "created inside a shared drive instead of My Drive."
            )

        return staging_folder_id

    # ------------------------------------------------------------------
    # Staging-copy discovery
    # ------------------------------------------------------------------

    def find_staging_copy(
        self,
        task_id: str,
        staging_folder_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Find an existing staging copy by migration task ID.

        When staging_folder_id is supplied, restrict discovery to the
        dedicated My Drive staging folder.

        This prevents a successfully moved destination file that still
        carries the task appProperty from being mistaken for an unfinished
        staging object.

        Returns:
            str:
                The staging file ID when exactly one match exists.

            None:
                When no staging copy exists.

        Raises:
            RuntimeError:
                If multiple staging copies exist for the same task.
        """
        if self.service is None:
            raise RuntimeError(
                "Google Drive service is not configured."
            )

        escaped_task_id = (
            task_id.replace(
                "'",
                "\\'",
            )
        )

        query_parts = [
            "trashed = false",
            (
                "appProperties has "
                "{ "
                f"key='{STAGING_TASK_PROPERTY}' "
                f"and value='{escaped_task_id}' "
                "}"
            ),
        ]

        if staging_folder_id:
            query_parts.append(
                f"'{staging_folder_id}' in parents"
            )

        query = " and ".join(
            query_parts
        )

        result = (
            self.service.files()
            .list(
                q=query,
                spaces="drive",
                corpora="user",
                fields=(
                    "files("
                    "id,"
                    "name,"
                    "mimeType,"
                    "parents,"
                    "driveId,"
                    "appProperties"
                    ")"
                ),
                pageSize=10,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )

        files = result.get(
            "files",
            [],
        )

        if len(files) > 1:
            raise RuntimeError(
                "Found multiple staging copies "
                f"for migration task {task_id}."
            )

        if files:
            return files[0]["id"]

        return None

    # ------------------------------------------------------------------
    # Staging-copy creation
    # ------------------------------------------------------------------

    def perform_staging_app_copy(
        self,
        source_id: str,
        target_name: str,
        staging_folder_id: str,
        task_id: str,
    ) -> str:
        """
        Create a staging copy inside the dedicated My Drive staging folder.

        This deliberately does NOT use the source file's parent.

        That distinction allows migration of files for which the
        authenticated user can read and copy the source object but cannot
        create new objects inside its source folder.

        The created copy is owned by the authenticated user and carries a
        task-specific appProperty so interrupted migrations can recover it.
        """
        if self.service is None:
            raise RuntimeError(
                "Google Drive service is not configured."
            )

        if not staging_folder_id:
            raise ValueError(
                "A My Drive staging folder ID is required."
            )

        result = (
            self.service.files()
            .copy(
                fileId=source_id,
                body={
                    "name": target_name,
                    "parents": [
                        staging_folder_id
                    ],
                    "appProperties": {
                        STAGING_TASK_PROPERTY: (
                            task_id
                        )
                    },
                },
                supportsAllDrives=True,
                fields=(
                    "id,"
                    "name,"
                    "mimeType,"
                    "parents,"
                    "driveId,"
                    "appProperties"
                ),
            )
            .execute()
        )

        staged_id = (
            result.get(
                "id"
            )
        )

        if not staged_id:
            raise RuntimeError(
                "Google Drive copy operation "
                "did not return an ID."
            )

        parents = (
            result.get("parents")
            or []
        )

        if (
            parents
            and staging_folder_id
            not in parents
        ):
            raise RuntimeError(
                "Google Drive created the staging copy "
                "outside the expected My Drive staging folder."
            )

        # A file staged in My Drive should not already belong to a
        # shared drive.
        if result.get("driveId"):
            raise RuntimeError(
                "Google Drive unexpectedly created the staging "
                "copy inside a shared drive."
            )

        return staged_id

    # ------------------------------------------------------------------
    # Final move
    # ------------------------------------------------------------------

    def perform_final_move(
        self,
        file_id: str,
        dest_folder_id: str,
        staging_folder_id: str,
    ) -> Dict[str, Any]:
        """
        Move one staging copy from My Drive into its final destination.

        For a Shared Drive destination this is the operation at which
        domain policy can still reject the migration, for example with
        fileWriterTeamDriveMoveInDisabled.

        If that happens, the staging file remains in My Drive and can be
        recovered on the next run.
        """
        if self.service is None:
            raise RuntimeError(
                "Google Drive service is not configured."
            )

        if not staging_folder_id:
            raise ValueError(
                "A My Drive staging folder ID is required."
            )

        return (
            self.service.files()
            .update(
                fileId=file_id,
                addParents=dest_folder_id,
                removeParents=staging_folder_id,
                supportsAllDrives=True,
                fields=(
                    "id,"
                    "name,"
                    "mimeType,"
                    "parents,"
                    "driveId,"
                    "appProperties"
                ),
            )
            .execute()
        )