import os
from pathlib import Path
from typing import Optional

from platformdirs import user_data_path


APP_NAME = "drive-migrator"

STATE_DIR_ENV = "DRIVE_MIGRATOR_STATE_DIR"
CREDENTIALS_ENV = "DRIVE_MIGRATOR_CREDENTIALS"


def get_default_state_dir() -> Path:
    """
    Return the operating system's standard per-user application
    data directory for Drive Migrator.

    Typical locations:

    macOS:
        ~/Library/Application Support/drive-migrator

    Linux:
        ~/.local/share/drive-migrator

    Windows:
        %LOCALAPPDATA%\\drive-migrator
    """
    return Path(
        user_data_path(
            APP_NAME,
            appauthor=False,
        )
    )


def resolve_state_dir(
    override: Optional[str] = None,
) -> Path:
    """
    Resolve and create the directory used for persistent runtime state.

    Resolution priority:

    1. Explicit path supplied by the caller.
    2. DRIVE_MIGRATOR_STATE_DIR environment variable.
    3. OS-specific per-user application data directory.

    The directory contains runtime data such as:

        token.json
        migration_work_list.json
        migration.log
    """
    value = (
        override
        or os.environ.get(STATE_DIR_ENV)
    )

    if value:
        path = Path(value).expanduser()
    else:
        path = get_default_state_dir()

    path = path.resolve()

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path


def resolve_credentials_path(
    override: Optional[str] = None,
) -> Optional[Path]:
    """
    Resolve the Google OAuth client-secret file.

    Resolution priority:

    1. Explicit path supplied by the caller.
    2. DRIVE_MIGRATOR_CREDENTIALS environment variable.

    Returns None if no credentials file has been configured.

    A credentials file is required for initial OAuth authorization,
    but an existing valid or refreshable token can subsequently be
    used without supplying the client-secret file again.
    """
    value = (
        override
        or os.environ.get(CREDENTIALS_ENV)
    )

    if not value:
        return None

    return Path(value).expanduser().resolve()