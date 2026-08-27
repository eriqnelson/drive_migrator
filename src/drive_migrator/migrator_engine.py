import datetime
import json
import re
import uuid
from collections import defaultdict
from typing import Any, Dict, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import (
    resolve_credentials_path,
    resolve_state_dir,
)
from .migration_helpers import MigrationHelpers


FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_NATIVE_MIME_PREFIX = "application/vnd.google-apps."
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"

FAILURE_PHASE_MANIFEST = "manifest_reconciliation"
FAILURE_PHASE_EXECUTION = "execution"


class DriveMigrator:
    """
    Resumable structural migration between Google Drive folder trees.
    """

    def __init__(
        self,
        credentials_path=None,
        state_dir=None,
        verbose: bool = False,
    ):
        self.state_dir = resolve_state_dir(
            state_dir
        )

        self.creds_path = (
            resolve_credentials_path(
                credentials_path
            )
        )

        self.token_path = (
            self.state_dir
            / "token.json"
        )

        self.work_list_path = (
            self.state_dir
            / "migration_work_list.json"
        )

        self.log_path = (
            self.state_dir
            / "migration.log"
        )

        self.verbose = verbose

        self.service = self._authenticate()

        self.helpers = MigrationHelpers(
            service=self.service,
            work_list_path=self.work_list_path,
        )

        self.log_message(
            "Authenticated. "
            f"State directory: {self.state_dir}"
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self):
        scopes = [
            DRIVE_SCOPE
        ]

        creds = None

        if self.token_path.exists():
            try:
                creds = (
                    Credentials.from_authorized_user_file(
                        str(self.token_path),
                        scopes=scopes,
                    )
                )
            except Exception as exc:
                self.log_message(
                    "Unable to load existing "
                    f"OAuth token: {exc}"
                )

        if creds and creds.valid:
            return build(
                "drive",
                "v3",
                credentials=creds,
            )

        if (
            creds
            and creds.expired
            and creds.refresh_token
        ):
            try:
                creds.refresh(
                    Request()
                )

                self.token_path.write_text(
                    creds.to_json(),
                    encoding="utf-8",
                )

                return build(
                    "drive",
                    "v3",
                    credentials=creds,
                )

            except Exception as exc:
                self.log_message(
                    "OAuth token refresh "
                    f"failed: {exc}"
                )

        if self.creds_path is None:
            raise RuntimeError(
                "Google OAuth credentials are required "
                "for initial authorization.\n\n"
                "Supply a client-secret file using:\n"
                "  --credentials /path/to/credentials.json\n\n"
                "or set:\n"
                "  DRIVE_MIGRATOR_CREDENTIALS"
            )

        if not self.creds_path.exists():
            raise FileNotFoundError(
                "Google OAuth credentials file "
                f"not found: {self.creds_path}"
            )

        flow = (
            InstalledAppFlow
            .from_client_secrets_file(
                str(self.creds_path),
                scopes=scopes,
            )
        )

        creds = flow.run_local_server(
            port=0
        )

        self.token_path.write_text(
            creds.to_json(),
            encoding="utf-8",
        )

        return build(
            "drive",
            "v3",
            credentials=creds,
        )

    # ------------------------------------------------------------------
    # Logging / console output
    # ------------------------------------------------------------------

    def log_message(
        self,
        message: str,
    ) -> None:
        timestamp = (
            datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
        )

        formatted = (
            f"[{timestamp}] {message}"
        )

        self.log_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.log_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                f"{formatted}\n"
            )

        if self.verbose:
            print(
                formatted,
                flush=True,
            )

    def verbose_message(
        self,
        message: str,
    ) -> None:
        if self.verbose:
            print(
                message,
                flush=True,
            )

    # ------------------------------------------------------------------
    # Name handling
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_name(
        name: str,
    ) -> str:
        cleaned = name.strip()

        while True:
            new_value = re.sub(
                r"^copy\s+of\s+",
                "",
                cleaned,
                count=1,
                flags=re.I,
            )

            if new_value == cleaned:
                return cleaned.strip()

            cleaned = new_value.strip()

    @staticmethod
    def _is_google_native_mime(
        mime_type: Optional[str],
    ) -> bool:
        if not mime_type:
            return False

        return mime_type.startswith(
            GOOGLE_NATIVE_MIME_PREFIX
        )

    @classmethod
    def _add_collision_suffix(
        cls,
        name: str,
        number: int,
        is_folder: bool,
        mime_type: Optional[str] = None,
    ) -> str:
        suffix = f" ({number})"

        if is_folder:
            return f"{name}{suffix}"

        if cls._is_google_native_mime(
            mime_type
        ):
            return f"{name}{suffix}"

        if (
            "." in name
            and not name.startswith(".")
            and not name.endswith(".")
        ):
            stem, extension = name.rsplit(
                ".",
                1,
            )

            return (
                f"{stem}{suffix}.{extension}"
            )

        return f"{name}{suffix}"

    def _allocate_source_names(
        self,
        items: list[Dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        prepared = []

        for item in items:
            prepared_item = dict(
                item
            )

            prepared_item[
                "_normalized_name"
            ] = self.normalize_name(
                item["name"]
            )

            prepared.append(
                prepared_item
            )

        prepared.sort(
            key=lambda item: (
                item[
                    "_normalized_name"
                ].casefold(),
                item[
                    "name"
                ].casefold(),
                item.get(
                    "mimeType",
                    "",
                ),
                item["id"],
            )
        )

        used_names = {
            True: set(),
            False: set(),
        }

        allocated = []

        for item in prepared:
            mime_type = item.get(
                "mimeType"
            )

            is_folder = (
                mime_type
                == FOLDER_MIME
            )

            base_name = item.pop(
                "_normalized_name"
            )

            target_name = base_name
            counter = 2

            namespace = (
                used_names[
                    is_folder
                ]
            )

            while (
                target_name.casefold()
                in namespace
            ):
                target_name = (
                    self._add_collision_suffix(
                        base_name,
                        counter,
                        is_folder,
                        mime_type=mime_type,
                    )
                )

                counter += 1

            namespace.add(
                target_name.casefold()
            )

            item[
                "target_name"
            ] = target_name

            allocated.append(
                item
            )

        return allocated

    @staticmethod
    def _join_relative(
        parent_path: str,
        name: str,
    ) -> str:
        if parent_path:
            return (
                f"{parent_path}/{name}"
            )

        return name

    # ------------------------------------------------------------------
    # Drive inventory
    # ------------------------------------------------------------------

    def _list_children(
        self,
        folder_id: str,
    ) -> list[Dict[str, Any]]:
        children = []
        page_token = None

        while True:
            query = (
                f"'{folder_id}' in parents "
                "and trashed = false"
            )

            result = (
                self.service.files()
                .list(
                    q=query,
                    fields=(
                        "nextPageToken, "
                        "files("
                        "id,"
                        "name,"
                        "mimeType,"
                        "size,"
                        "parents,"
                        "modifiedTime,"
                        "md5Checksum"
                        ")"
                    ),
                    pageToken=page_token,
                    pageSize=1000,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )

            children.extend(
                result.get(
                    "files",
                    [],
                )
            )

            page_token = result.get(
                "nextPageToken"
            )

            if not page_token:
                break

        return children

    def scan_folder(
        self,
        folder_id: str,
        relative_path: str = "",
        depth: int = 0,
        source_mode: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        inventory: Dict[
            str,
            Dict[str, Any],
        ] = {}

        mode = (
            "source"
            if source_mode
            else "destination"
        )

        display_path = (
            relative_path
            or "/"
        )

        self.verbose_message(
            f"Scanning {mode}: "
            f"{display_path}"
        )

        immediate_children = (
            self._list_children(
                folder_id
            )
        )

        self.verbose_message(
            f"  Found "
            f"{len(immediate_children)} "
            f"items"
        )

        if source_mode:
            children = (
                self._allocate_source_names(
                    immediate_children
                )
            )

        else:
            children = []

            for item in immediate_children:
                literal_item = dict(
                    item
                )

                literal_item[
                    "target_name"
                ] = item["name"]

                children.append(
                    literal_item
                )

        children.sort(
            key=lambda item: (
                item[
                    "target_name"
                ].casefold(),
                item.get(
                    "mimeType",
                    "",
                ),
                item["id"],
            )
        )

        for item in children:
            file_id = item["id"]

            original_name = (
                item["name"]
            )

            target_name = (
                item["target_name"]
            )

            item_path = (
                self._join_relative(
                    relative_path,
                    target_name,
                )
            )

            parents = (
                item.get("parents")
                or [folder_id]
            )

            inventory[file_id] = {
                "id": file_id,
                "original_name": (
                    original_name
                ),
                "name": target_name,
                "mimeType": (
                    item.get(
                        "mimeType"
                    )
                ),
                "size": (
                    item.get("size")
                ),
                "md5Checksum": (
                    item.get(
                        "md5Checksum"
                    )
                ),
                "modifiedTime": (
                    item.get(
                        "modifiedTime"
                    )
                ),
                "parent_id": (
                    parents[0]
                ),
                "relative_path": (
                    item_path
                ),
                "parent_relative_path": (
                    relative_path
                ),
                "depth": depth + 1,
            }

            if (
                item.get("mimeType")
                == FOLDER_MIME
            ):
                inventory.update(
                    self.scan_folder(
                        file_id,
                        item_path,
                        depth=depth + 1,
                        source_mode=source_mode,
                    )
                )

        return inventory

    # ------------------------------------------------------------------
    # Destination collision repair
    # ------------------------------------------------------------------

    def _next_available_destination_name(
        self,
        base_name: str,
        is_folder: bool,
        mime_type: Optional[str],
        used_names: set[str],
    ) -> str:
        counter = 2

        while True:
            candidate = (
                self._add_collision_suffix(
                    base_name,
                    counter,
                    is_folder,
                    mime_type=mime_type,
                )
            )

            if (
                candidate.casefold()
                not in used_names
            ):
                return candidate

            counter += 1

    def resolve_destination_collisions(
        self,
        folder_id: str,
        relative_path: str = "",
    ) -> Dict[str, Any]:
        result = {
            "renamed": [],
            "errors": [],
        }

        display_path = (
            relative_path
            or "/"
        )

        self.verbose_message(
            "Checking destination collisions: "
            f"{display_path}"
        )

        try:
            children = (
                self._list_children(
                    folder_id
                )
            )

        except Exception as exc:
            message = (
                "Unable to inspect destination folder "
                f"'{display_path}' "
                f"({folder_id}): "
                f"{type(exc).__name__}: {exc}"
            )

            self.log_message(
                "DESTINATION COLLISION ERROR: "
                f"{message}"
            )

            result[
                "errors"
            ].append(
                {
                    "folder_id": folder_id,
                    "path": relative_path,
                    "error": message,
                }
            )

            return result

        grouped = defaultdict(
            list
        )

        for item in children:
            is_folder = (
                item.get("mimeType")
                == FOLDER_MIME
            )

            grouped[
                (
                    item["name"],
                    is_folder,
                )
            ].append(
                item
            )

        used_names = {
            True: {
                item["name"].casefold()
                for item in children
                if (
                    item.get("mimeType")
                    == FOLDER_MIME
                )
            },
            False: {
                item["name"].casefold()
                for item in children
                if (
                    item.get("mimeType")
                    != FOLDER_MIME
                )
            },
        }

        for (
            base_name,
            is_folder,
        ), duplicates in sorted(
            grouped.items(),
            key=lambda pair: (
                pair[0][0].casefold(),
                pair[0][1],
            ),
        ):
            if (
                len(duplicates)
                <= 1
            ):
                continue

            duplicates.sort(
                key=lambda item: item["id"]
            )

            for duplicate in duplicates[1:]:
                mime_type = (
                    duplicate.get(
                        "mimeType"
                    )
                )

                new_name = (
                    self._next_available_destination_name(
                        base_name,
                        is_folder,
                        mime_type,
                        used_names[
                            is_folder
                        ],
                    )
                )

                old_path = (
                    self._join_relative(
                        relative_path,
                        duplicate["name"],
                    )
                )

                new_path = (
                    self._join_relative(
                        relative_path,
                        new_name,
                    )
                )

                try:
                    updated = (
                        self.service.files()
                        .update(
                            fileId=duplicate["id"],
                            body={
                                "name": new_name
                            },
                            supportsAllDrives=True,
                            fields=(
                                "id,"
                                "name,"
                                "mimeType,"
                                "parents"
                            ),
                        )
                        .execute()
                    )

                    duplicate[
                        "name"
                    ] = updated.get(
                        "name",
                        new_name,
                    )

                    used_names[
                        is_folder
                    ].add(
                        new_name.casefold()
                    )

                    result[
                        "renamed"
                    ].append(
                        {
                            "id": duplicate["id"],
                            "old_path": old_path,
                            "new_path": new_path,
                            "type": (
                                "folder"
                                if is_folder
                                else "file"
                            ),
                        }
                    )

                    self.log_message(
                        "DESTINATION COLLISION REPAIRED: "
                        f"{old_path} "
                        f"[{duplicate['id']}] "
                        f"-> {new_path}"
                    )

                except Exception as exc:
                    message = (
                        f"Unable to rename destination "
                        f"{'folder' if is_folder else 'file'} "
                        f"'{old_path}' "
                        f"[{duplicate['id']}]: "
                        f"{type(exc).__name__}: {exc}"
                    )

                    result[
                        "errors"
                    ].append(
                        {
                            "id": duplicate["id"],
                            "path": old_path,
                            "error": message,
                        }
                    )

                    self.log_message(
                        "DESTINATION COLLISION ERROR: "
                        f"{message}"
                    )

        try:
            current_children = (
                self._list_children(
                    folder_id
                )
            )

        except Exception as exc:
            message = (
                "Unable to re-scan destination folder "
                f"'{display_path}' "
                "after collision repair: "
                f"{type(exc).__name__}: {exc}"
            )

            result[
                "errors"
            ].append(
                {
                    "folder_id": folder_id,
                    "path": relative_path,
                    "error": message,
                }
            )

            self.log_message(
                "DESTINATION COLLISION ERROR: "
                f"{message}"
            )

            return result

        for item in sorted(
            current_children,
            key=lambda child: (
                child["name"].casefold(),
                child["id"],
            ),
        ):
            if (
                item.get("mimeType")
                != FOLDER_MIME
            ):
                continue

            child_path = (
                self._join_relative(
                    relative_path,
                    item["name"],
                )
            )

            child_result = (
                self.resolve_destination_collisions(
                    item["id"],
                    child_path,
                )
            )

            result[
                "renamed"
            ].extend(
                child_result[
                    "renamed"
                ]
            )

            result[
                "errors"
            ].extend(
                child_result[
                    "errors"
                ]
            )

        return result

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    @staticmethod
    def _index_by_path(
        inventory: Dict[
            str,
            Dict[str, Any],
        ],
    ) -> Dict[
        str,
        list[Dict[str, Any]],
    ]:
        index: Dict[
            str,
            list[Dict[str, Any]],
        ] = defaultdict(list)

        for item in inventory.values():
            index[
                item["relative_path"]
            ].append(
                item
            )

        return index

    @staticmethod
    def _single_match(
        index: Dict[
            str,
            list[Dict[str, Any]],
        ],
        relative_path: str,
        want_folder: bool,
    ) -> Optional[Dict[str, Any]]:
        matches = [
            item
            for item in index.get(
                relative_path,
                [],
            )
            if (
                (
                    item.get("mimeType")
                    == FOLDER_MIME
                )
                == want_folder
            )
        ]

        if (
            len(matches)
            > 1
        ):
            kind = (
                "folder"
                if want_folder
                else "file"
            )

            raise RuntimeError(
                "Destination contains multiple "
                f"{kind}s at '{relative_path}'."
            )

        if matches:
            return matches[0]

        return None

    # ------------------------------------------------------------------
    # Manifest generation
    # ------------------------------------------------------------------

    def generate_fresh_sync_manifest(
        self,
        source_id: str,
        dest_id: str,
        resolve_destination_collisions: bool = False,
    ) -> Dict[str, Any]:
        self.log_message(
            "Starting fresh manifest generation"
        )

        collision_summary = {
            "renamed": [],
            "errors": [],
        }

        if resolve_destination_collisions:
            self.log_message(
                "Starting destination collision preflight"
            )

            collision_summary = (
                self.resolve_destination_collisions(
                    dest_id
                )
            )

            self.log_message(
                "Destination collision preflight complete: "
                f"{len(collision_summary['renamed'])} renamed, "
                f"{len(collision_summary['errors'])} errors"
            )

        source_inventory = (
            self.scan_folder(
                source_id,
                source_mode=True,
            )
        )

        self.log_message(
            "Source inventory complete: "
            f"{len(source_inventory)} items"
        )

        dest_inventory = (
            self.scan_folder(
                dest_id,
                source_mode=False,
            )
        )

        self.log_message(
            "Destination inventory complete: "
            f"{len(dest_inventory)} items"
        )

        dest_index = (
            self._index_by_path(
                dest_inventory
            )
        )

        folder_map: Dict[
            str,
            str,
        ] = {
            source_id: dest_id
        }

        blocked_source_folders = set()

        tasks = []

        folders = sorted(
            (
                item
                for item
                in source_inventory.values()
                if (
                    item["mimeType"]
                    == FOLDER_MIME
                )
            ),
            key=lambda item: (
                item["depth"],
                item[
                    "relative_path"
                ].casefold(),
            ),
        )

        files = sorted(
            (
                item
                for item
                in source_inventory.values()
                if (
                    item["mimeType"]
                    != FOLDER_MIME
                )
            ),
            key=lambda item: (
                item["depth"],
                item[
                    "relative_path"
                ].casefold(),
            ),
        )

        for item in folders:
            existing = None
            reconciliation_error = None

            if (
                item["parent_id"]
                in blocked_source_folders
            ):
                reconciliation_error = (
                    "Destination reconciliation blocked because "
                    "the parent folder is ambiguous."
                )

            else:
                try:
                    existing = (
                        self._single_match(
                            dest_index,
                            item[
                                "relative_path"
                            ],
                            want_folder=True,
                        )
                    )

                except RuntimeError as exc:
                    reconciliation_error = (
                        str(exc)
                    )

            if reconciliation_error:
                blocked_source_folders.add(
                    item["id"]
                )

                self.log_message(
                    "MANIFEST RECONCILIATION ERROR: "
                    f"{item['relative_path']}: "
                    f"{reconciliation_error}"
                )

            elif existing:
                folder_map[
                    item["id"]
                ] = existing["id"]

            if reconciliation_error:
                status = "failed"
                failure_phase = (
                    FAILURE_PHASE_MANIFEST
                )

            elif existing:
                status = "completed"
                failure_phase = None

            else:
                status = "pending"
                failure_phase = None

            tasks.append(
                {
                    "task_id": str(
                        uuid.uuid4()
                    ),
                    "type": "folder_creation",
                    "source_id": item["id"],
                    "source_parent_id": (
                        item["parent_id"]
                    ),
                    "dest_parent_id": (
                        folder_map.get(
                            item[
                                "parent_id"
                            ]
                        )
                    ),
                    "dest_id": (
                        existing["id"]
                        if existing
                        else None
                    ),
                    "original_name": (
                        item[
                            "original_name"
                        ]
                    ),
                    "target_name": (
                        item["name"]
                    ),
                    "relative_path": (
                        item[
                            "relative_path"
                        ]
                    ),
                    "depth": (
                        item["depth"]
                    ),
                    "status": status,
                    "reconciled_existing": (
                        bool(existing)
                    ),
                    "error_message": (
                        reconciliation_error
                    ),
                    "failure_phase": (
                        failure_phase
                    ),
                }
            )

        for item in files:
            existing = None
            reconciliation_error = None

            if (
                item["parent_id"]
                in blocked_source_folders
            ):
                reconciliation_error = (
                    "Destination reconciliation blocked because "
                    "the parent folder is ambiguous."
                )

            else:
                try:
                    existing = (
                        self._single_match(
                            dest_index,
                            item[
                                "relative_path"
                            ],
                            want_folder=False,
                        )
                    )

                except RuntimeError as exc:
                    reconciliation_error = (
                        str(exc)
                    )

            if reconciliation_error:
                self.log_message(
                    "MANIFEST RECONCILIATION ERROR: "
                    f"{item['relative_path']}: "
                    f"{reconciliation_error}"
                )

            if reconciliation_error:
                status = "failed"
                failure_phase = (
                    FAILURE_PHASE_MANIFEST
                )

            elif existing:
                status = "completed"
                failure_phase = None

            else:
                status = "pending"
                failure_phase = None

            tasks.append(
                {
                    "task_id": str(
                        uuid.uuid4()
                    ),
                    "type": "file_migration",
                    "source_id": item["id"],
                    "source_parent_id": (
                        item["parent_id"]
                    ),
                    "dest_parent_id": (
                        folder_map.get(
                            item[
                                "parent_id"
                            ]
                        )
                    ),
                    "dest_id": (
                        existing["id"]
                        if existing
                        else None
                    ),
                    "staged_file_id": None,
                    "original_name": (
                        item[
                            "original_name"
                        ]
                    ),
                    "target_name": (
                        item["name"]
                    ),
                    "relative_path": (
                        item[
                            "relative_path"
                        ]
                    ),
                    "depth": (
                        item["depth"]
                    ),
                    "source_size": (
                        item.get(
                            "size"
                        )
                    ),
                    "source_md5": (
                        item.get(
                            "md5Checksum"
                        )
                    ),
                    "status": status,
                    "reconciled_existing": (
                        bool(existing)
                    ),
                    "error_message": (
                        reconciliation_error
                    ),
                    "failure_phase": (
                        failure_phase
                    ),
                }
            )

        now = (
            datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
        )

        manifest = {
            "migration_metadata": {
                "created_at": now,
                "updated_at": now,
                "source_root_id": (
                    source_id
                ),
                "dest_root_id": (
                    dest_id
                ),
                "folder_map": (
                    folder_map
                ),
                "staging_folder_id": None,
                "destination_collision_preflight": {
                    "enabled": (
                        resolve_destination_collisions
                    ),
                    "renamed_count": len(
                        collision_summary[
                            "renamed"
                        ]
                    ),
                    "error_count": len(
                        collision_summary[
                            "errors"
                        ]
                    ),
                    "renamed": (
                        collision_summary[
                            "renamed"
                        ]
                    ),
                    "errors": (
                        collision_summary[
                            "errors"
                        ]
                    ),
                },
            },
            "tasks": tasks,
        }

        self.helpers.write_manifest(
            manifest
        )

        failed_count = sum(
            task["status"] == "failed"
            for task in tasks
        )

        pending_count = sum(
            task["status"] == "pending"
            for task in tasks
        )

        completed_count = sum(
            task["status"] == "completed"
            for task in tasks
        )

        self.log_message(
            "Manifest written: "
            f"{len(tasks)} tasks, "
            f"{pending_count} pending, "
            f"{completed_count} completed, "
            f"{failed_count} failed"
        )

        return manifest

    # ------------------------------------------------------------------
    # Folder/staging map persistence
    # ------------------------------------------------------------------

    def _load_folder_map(
        self,
        manifest: Dict[str, Any],
    ) -> Dict[str, str]:
        metadata = manifest.get(
            "migration_metadata",
            {},
        )

        folder_map = dict(
            metadata.get(
                "folder_map",
                {},
            )
        )

        source_root = metadata.get(
            "source_root_id"
        )

        dest_root = metadata.get(
            "dest_root_id"
        )

        if (
            source_root
            and dest_root
        ):
            folder_map.setdefault(
                source_root,
                dest_root,
            )

        for task in manifest.get(
            "tasks",
            [],
        ):
            if (
                task.get("type")
                == "folder_creation"
                and task.get(
                    "dest_id"
                )
                and task.get(
                    "status"
                )
                == "completed"
            ):
                folder_map[
                    task["source_id"]
                ] = task["dest_id"]

        return folder_map

    def _persist_folder_map(
        self,
        folder_map: Dict[str, str],
    ) -> None:
        self.helpers.update_metadata(
            folder_map=folder_map
        )

    def _load_or_create_staging_folder_id(
        self,
        manifest: Dict[str, Any],
    ) -> str:
        """
        Reuse the persisted My Drive staging folder if available.

        Otherwise discover/create it through MigrationHelpers and persist
        the resulting ID into migration metadata.
        """
        metadata = manifest.get(
            "migration_metadata",
            {},
        )

        staging_folder_id = (
            metadata.get(
                "staging_folder_id"
            )
        )

        if staging_folder_id:
            self.verbose_message(
                "Using existing My Drive staging folder: "
                f"{staging_folder_id}"
            )

            return staging_folder_id

        staging_folder_id = (
            self.helpers
            .get_or_create_staging_folder()
        )

        self.helpers.update_metadata(
            staging_folder_id=(
                staging_folder_id
            )
        )

        self.log_message(
            "Using My Drive staging folder: "
            f"{staging_folder_id}"
        )

        return staging_folder_id

    # ------------------------------------------------------------------
    # Runtime destination lookup
    # ------------------------------------------------------------------

    def _find_named_child(
        self,
        parent_id: str,
        name: str,
        mime_type: Optional[str] = None,
        want_folder: Optional[
            bool
        ] = None,
    ) -> Optional[Dict[str, Any]]:
        escaped_name = (
            name.replace(
                "'",
                "\\'",
            )
        )

        query = (
            f"'{parent_id}' in parents "
            f"and name = '{escaped_name}' "
            "and trashed = false"
        )

        if mime_type:
            escaped_mime = (
                mime_type.replace(
                    "'",
                    "\\'",
                )
            )

            query += (
                " and mimeType = "
                f"'{escaped_mime}'"
            )

        result = (
            self.service.files()
            .list(
                q=query,
                fields=(
                    "files("
                    "id,"
                    "name,"
                    "mimeType,"
                    "parents"
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

        if want_folder is not None:
            files = [
                item
                for item in files
                if (
                    (
                        item.get(
                            "mimeType"
                        )
                        == FOLDER_MIME
                    )
                    == want_folder
                )
            ]

        if len(files) > 1:
            raise RuntimeError(
                "Multiple destination items "
                f"named '{name}' under "
                f"parent {parent_id}"
            )

        if files:
            return files[0]

        return None

    # ------------------------------------------------------------------
    # Folder execution
    # ------------------------------------------------------------------

    def _execute_folder_task(
        self,
        task: Dict[str, Any],
        folder_map: Dict[str, str],
    ) -> None:
        task_id = (
            task["task_id"]
        )

        dest_parent_id = (
            folder_map.get(
                task[
                    "source_parent_id"
                ]
            )
        )

        if not dest_parent_id:
            raise RuntimeError(
                "Destination parent is "
                "unresolved for "
                f"{task['relative_path']}"
            )

        existing = (
            self._find_named_child(
                dest_parent_id,
                task[
                    "target_name"
                ],
                FOLDER_MIME,
                want_folder=True,
            )
        )

        if existing:
            dest_id = (
                existing["id"]
            )

        else:
            created = (
                self.service.files()
                .create(
                    body={
                        "name": (
                            task[
                                "target_name"
                            ]
                        ),
                        "mimeType": (
                            FOLDER_MIME
                        ),
                        "parents": [
                            dest_parent_id
                        ],
                    },
                    supportsAllDrives=True,
                    fields=(
                        "id,"
                        "name,"
                        "parents"
                    ),
                )
                .execute()
            )

            dest_id = (
                created["id"]
            )

        folder_map[
            task["source_id"]
        ] = dest_id

        self.helpers.update_task_status(
            task_id,
            "completed",
            dest_id=dest_id,
            dest_parent_id=(
                dest_parent_id
            ),
            failure_phase=None,
            error_message=None,
        )

        self._persist_folder_map(
            folder_map
        )

    # ------------------------------------------------------------------
    # File execution
    # ------------------------------------------------------------------

    def _execute_file_task(
        self,
        task: Dict[str, Any],
        folder_map: Dict[str, str],
        staging_folder_id: str,
    ) -> None:
        task_id = (
            task["task_id"]
        )

        dest_parent_id = (
            folder_map.get(
                task[
                    "source_parent_id"
                ]
            )
        )

        if not dest_parent_id:
            raise RuntimeError(
                "Destination parent is "
                "unresolved for "
                f"{task['relative_path']}"
            )

        existing = (
            self._find_named_child(
                dest_parent_id,
                task[
                    "target_name"
                ],
                want_folder=False,
            )
        )

        if existing:
            self.helpers.update_task_status(
                task_id,
                "completed",
                dest_id=(
                    existing["id"]
                ),
                dest_parent_id=(
                    dest_parent_id
                ),
                failure_phase=None,
                error_message=None,
            )

            return

        staged_id = (
            task.get(
                "staged_file_id"
            )
        )

        if not staged_id:
            staged_id = (
                self.helpers
                .find_staging_copy(
                    task_id,
                    staging_folder_id=(
                        staging_folder_id
                    ),
                )
            )

        if not staged_id:
            staged_id = (
                self.helpers
                .perform_staging_app_copy(
                    source_id=(
                        task[
                            "source_id"
                        ]
                    ),
                    target_name=(
                        task[
                            "target_name"
                        ]
                    ),
                    staging_folder_id=(
                        staging_folder_id
                    ),
                    task_id=task_id,
                )
            )

        self.helpers.update_task_status(
            task_id,
            "in_progress",
            staged_file_id=(
                staged_id
            ),
            dest_parent_id=(
                dest_parent_id
            ),
            failure_phase=None,
            error_message=None,
        )

        moved = (
            self.helpers
            .perform_final_move(
                file_id=staged_id,
                dest_folder_id=(
                    dest_parent_id
                ),
                staging_folder_id=(
                    staging_folder_id
                ),
            )
        )

        self.helpers.update_task_status(
            task_id,
            "completed",
            staged_file_id=(
                staged_id
            ),
            dest_id=moved.get(
                "id",
                staged_id,
            ),
            dest_parent_id=(
                dest_parent_id
            ),
            failure_phase=None,
            error_message=None,
        )

    # ------------------------------------------------------------------
    # Migration execution
    # ------------------------------------------------------------------

    def execute_migration(
        self,
        retry_failed: bool = True,
    ) -> Dict[str, int]:
        manifest = (
            self.helpers.load_manifest()
        )

        folder_map = (
            self._load_folder_map(
                manifest
            )
        )

        staging_folder_id = (
            self._load_or_create_staging_folder_id(
                manifest
            )
        )

        eligible = {
            "pending",
            "in_progress",
        }

        if retry_failed:
            eligible.add(
                "failed"
            )

        tasks = sorted(
            manifest.get(
                "tasks",
                [],
            ),
            key=lambda task: (
                (
                    0
                    if (
                        task.get("type")
                        == "folder_creation"
                    )
                    else 1
                ),
                task.get(
                    "depth",
                    0,
                ),
                task.get(
                    "relative_path",
                    "",
                ).casefold(),
            ),
        )

        stats = {
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "blocked": 0,
        }

        total_tasks = len(
            tasks
        )

        for task_number, task in enumerate(
            tasks,
            start=1,
        ):
            status = (
                task.get(
                    "status"
                )
            )

            failure_phase = (
                task.get(
                    "failure_phase"
                )
            )

            if (
                status == "failed"
                and failure_phase
                == FAILURE_PHASE_MANIFEST
            ):
                stats[
                    "blocked"
                ] += 1

                self.verbose_message(
                    f"[{task_number}/{total_tasks}] "
                    "Blocked manifest-reconciliation failure: "
                    f"{task.get('relative_path', '')}"
                )

                continue

            if (
                status
                not in eligible
            ):
                stats[
                    "skipped"
                ] += 1

                continue

            task_id = (
                task["task_id"]
            )

            self.verbose_message(
                f"[{task_number}/{total_tasks}] "
                f"Processing "
                f"{task.get('type', 'unknown')}: "
                f"{task.get('relative_path', '')}"
            )

            try:
                self.helpers.update_task_status(
                    task_id,
                    "in_progress",
                    failure_phase=None,
                    error_message=None,
                )

                if (
                    task["type"]
                    == "folder_creation"
                ):
                    self._execute_folder_task(
                        task,
                        folder_map,
                    )

                elif (
                    task["type"]
                    == "file_migration"
                ):
                    self._execute_file_task(
                        task,
                        folder_map,
                        staging_folder_id,
                    )

                else:
                    raise ValueError(
                        "Unknown task type: "
                        f"{task.get('type')}"
                    )

                stats[
                    "completed"
                ] += 1

                self.log_message(
                    "Completed "
                    f"{task['type']}: "
                    f"{task['relative_path']}"
                )

            except Exception as exc:
                stats[
                    "failed"
                ] += 1

                message = (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

                self.helpers.update_task_status(
                    task_id,
                    "failed",
                    message,
                    failure_phase=(
                        FAILURE_PHASE_EXECUTION
                    ),
                )

                self.log_message(
                    "FAILED "
                    f"{task.get('relative_path')}: "
                    f"{message}"
                )

        final_manifest = (
            self.helpers.load_manifest()
        )

        final_manifest.setdefault(
            "migration_metadata",
            {},
        )["updated_at"] = (
            datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
        )

        self.helpers.write_manifest(
            final_manifest
        )

        self.log_message(
            "Migration execution complete: "
            f"{stats['completed']} completed, "
            f"{stats['failed']} failed, "
            f"{stats['skipped']} skipped, "
            f"{stats['blocked']} blocked"
        )

        return stats

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify_destination(
        self,
    ) -> Dict[str, Any]:
        manifest = (
            self.helpers.load_manifest()
        )

        dest_root = (
            manifest[
                "migration_metadata"
            ][
                "dest_root_id"
            ]
        )

        dest_inventory = (
            self.scan_folder(
                dest_root,
                source_mode=False,
            )
        )

        dest_index = (
            self._index_by_path(
                dest_inventory
            )
        )

        missing = []

        tasks = manifest.get(
            "tasks",
            [],
        )

        total_tasks = len(
            tasks
        )

        for task_number, task in enumerate(
            tasks,
            start=1,
        ):
            if (
                self.verbose
                and (
                    task_number == 1
                    or task_number % 100 == 0
                    or task_number == total_tasks
                )
            ):
                self.verbose_message(
                    "Verification progress: "
                    f"{task_number}/{total_tasks}"
                )

            want_folder = (
                task["type"]
                == "folder_creation"
            )

            try:
                match = (
                    self._single_match(
                        dest_index,
                        task[
                            "relative_path"
                        ],
                        want_folder=(
                            want_folder
                        ),
                    )
                )

            except RuntimeError as exc:
                missing.append(
                    {
                        "path": (
                            task[
                                "relative_path"
                            ]
                        ),
                        "error": (
                            str(exc)
                        ),
                    }
                )

                continue

            if not match:
                missing.append(
                    {
                        "path": (
                            task[
                                "relative_path"
                            ]
                        ),
                        "error": "missing",
                    }
                )

        result = {
            "expected_items": len(
                tasks
            ),
            "destination_items": len(
                dest_inventory
            ),
            "missing_or_ambiguous": (
                missing
            ),
            "ok": (
                not missing
            ),
        }

        self.log_message(
            "Verification: "
            f"{json.dumps(result)}"
        )

        return result