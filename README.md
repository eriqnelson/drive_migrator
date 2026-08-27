# Drive Migrator

Drive Migrator is a resumable structural migration tool for copying a Google Drive folder tree into another Google Drive or Shared Drive location.

It is designed for migrations where a direct source-to-destination copy may be restricted by Google Drive ownership or permission boundaries.

The tool:

- Recursively inventories the source and destination.
- Recreates missing folder structure.
- Removes `Copy of ` prefixes from migrated names.
- Creates a clean staging copy in the user's "My Drive".
- Moves the staging copy into the appropriate destination folder.
- Preserves the original source files.
- Maintains a persistent migration manifest.
- Can safely resume interrupted migrations.
- Records failed operations without stopping the entire migration.
- Can perform structural verification after migration.

## Requirements

- Python 3.10 or newer
- A Google account with access to the source
- Permission to create copies in the source
- Permission to create folders and add files to the destination
- A Google OAuth desktop application client-secret JSON file for initial authorization

## Installation

Clone or download the repository, then enter the project directory:

```bash
cd drive-migrator
```

Create a virtual environment:

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

Install Drive Migrator and its dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

The editable installation is useful when running directly from a cloned repository.

Once installed, the command should be available inside the active virtual environment:

```bash
drive-migrator --help
```

The application can also be invoked as a Python module:

```bash
python -m drive_migrator --help
```

## Google OAuth Setup

Drive Migrator uses Google's OAuth installed-application flow.

The OAuth client must have access to the Google Drive API.

Download the OAuth client-secret JSON file for the application.

Do not commit this file to the repository.

For the first run, provide it using:

```bash
drive-migrator \
    --credentials /path/to/credentials.json \
    --source SOURCE_FOLDER_ID \
    --destination DESTINATION_FOLDER_ID \
    --fresh
```

A browser window will open for Google authorization.

After successful authorization, Drive Migrator stores the resulting OAuth token in its application state directory.

The client-secret file generally does not need to be supplied again while the stored token remains valid or refreshable.

## Runtime State

Application code and migration state are deliberately kept separate.

By default, Drive Migrator uses the operating system's standard per-user application-data location.

Typical locations include:

### macOS

```text
~/Library/Application Support/drive-migrator/
```

### Linux

```text
~/.local/share/drive-migrator/
```

### Windows

The appropriate per-user application data directory is selected automatically.

The state directory contains:

```text
token.json
migration_work_list.json
migration.log
```

### `token.json`

Contains the user's Google OAuth authorization token.

Treat this as sensitive data.

### `migration_work_list.json`

Contains the persistent migration manifest.

This is the authoritative record of migration progress.

### `migration.log`

Contains timestamped operational and error messages.

## Custom State Directory

A different state directory can be selected using:

```bash
drive-migrator \
    --state-dir /path/to/state
```

It can also be configured using the environment variable:

```bash
export DRIVE_MIGRATOR_STATE_DIR="/path/to/state"
```

On Windows PowerShell:

```powershell
$env:DRIVE_MIGRATOR_STATE_DIR="C:\path\to\state"
```

Command-line arguments take precedence over environment variables.

## Credentials Environment Variable

Instead of supplying `--credentials`, the OAuth client-secret location can be configured with:

```bash
export DRIVE_MIGRATOR_CREDENTIALS="/path/to/credentials.json"
```

On Windows PowerShell:

```powershell
$env:DRIVE_MIGRATOR_CREDENTIALS="C:\path\to\credentials.json"
```

The resolution order is:

1. `--credentials`
2. `DRIVE_MIGRATOR_CREDENTIALS`
3. Existing OAuth token, when authorization has already occurred

## Source and Destination IDs

Drive Migrator uses Google Drive folder IDs rather than folder names.

A Google Drive folder URL generally resembles:

```text
https://drive.google.com/drive/folders/FOLDER_ID
```

The portion following `/folders/` is the folder ID.

For example:

```text
https://drive.google.com/drive/folders/1AbCdEfGhExample
```

has the folder ID:

```text
1AbCdEfGhExample
```

## Recommended First Run

For a production migration, first generate the manifest without moving anything:

```bash
drive-migrator \
    --credentials /path/to/credentials.json \
    --source SOURCE_FOLDER_ID \
    --destination DESTINATION_FOLDER_ID \
    --fresh \
    --manifest-only
```

This performs:

```text
Source inventory
        +
Destination inventory
        ↓
Filename normalization
        ↓
Destination reconciliation
        ↓
Migration manifest
        ↓
STOP
```

No migration tasks are executed.

Inspect `migration_work_list.json` before continuing.

## Running the Migration

After inspecting the manifest, run:

```bash
drive-migrator
```

Do **not** use `--fresh` when continuing the migration.

Drive Migrator reads the existing manifest and processes unfinished work.

## Migration Process

For each source folder, Drive Migrator recreates or reconciles the corresponding destination folder.

Files then follow this process:

```text
ORIGINAL SOURCE FILE
        │
        │ Google Drive copy
        │ + normalized filename
        ▼
SOURCE STAGING COPY
        │
        │ change Drive parent
        ▼
DESTINATION FILE
```

The original source file remains in place.

For example:

```text
Before:

Source/
└── Copy of Report.pdf
```

During migration:

```text
Source/
├── Copy of Report.pdf
└── Report.pdf            ← staging copy
```

After migration:

```text
Source/
└── Copy of Report.pdf

Destination/
└── Report.pdf
```

## Filename Normalization

Drive Migrator removes one or more leading `Copy of ` prefixes.

For example:

```text
Copy of Report.pdf
```

becomes:

```text
Report.pdf
```

and:

```text
Copy of Copy of Report.pdf
```

also becomes:

```text
Report.pdf
```

Matching is case-insensitive.

Normalization applies to both files and folders.

## Name Collisions

Normalization can cause two source objects to resolve to the same destination path.

For example:

```text
Report.pdf
Copy of Report.pdf
```

would both become:

```text
Report.pdf
```

Drive Migrator detects these collisions while building the manifest and stops rather than choosing one automatically.

The source conflict must be resolved before migration continues.

## Resuming an Interrupted Migration

The migration manifest is designed to survive interruptions.

If execution stops because of:

- A network failure
- A Google API error
- Program termination
- Computer restart
- Authentication problem

run:

```bash
drive-migrator
```

again.

Tasks in these states are eligible for execution:

```text
pending
in_progress
failed
```

Failed tasks are retried by default.

## Staging Recovery

Each staging copy receives a Google Drive application property containing its migration task ID.

This allows Drive Migrator to rediscover a staging copy if execution stops after Google creates it but before its ID can be recorded in the local manifest.

The property is:

```text
driveMigratorTaskId
```

This is used internally for recovery and duplicate prevention.

## Failed Tasks

A failed task is recorded in the manifest with:

```json
{
  "status": "failed",
  "error_message": "..."
}
```

Processing continues with other tasks.

After correcting the cause of the failure, run:

```bash
drive-migrator
```

to retry it.

To leave failed tasks untouched:

```bash
drive-migrator --no-retry-failed
```

## Verification

To execute or resume the migration and then verify the destination structure:

```bash
drive-migrator --verify
```

Verification performs a new recursive scan of the destination and compares it against the expected manifest paths.

A successful result resembles:

```json
{
  "verification": {
    "expected_items": 100,
    "destination_items": 100,
    "missing_or_ambiguous": [],
    "ok": true
  }
}
```

Verification is currently **structural**.

It verifies that the expected files and folders exist at the expected normalized paths.

It does not perform a complete byte-for-byte integrity check.

## Starting a New Migration

The `--fresh` option creates a new manifest from the current source and destination state.

Use:

```bash
drive-migrator \
    --source SOURCE_FOLDER_ID \
    --destination DESTINATION_FOLDER_ID \
    --fresh
```

Use `--fresh` when intentionally beginning or reconstructing a migration.

Do not use it merely because a previous execution stopped.

For an interrupted migration, resume the existing manifest instead.

## Command-Line Options

```text
--credentials PATH
    Google OAuth client-secret JSON file.

--state-dir PATH
    Runtime state directory.

--source ID
    Source root Google Drive folder ID.

--destination ID
    Destination root Google Drive folder ID.

--fresh
    Generate a new manifest from current Drive state.

--manifest-only
    Generate the manifest without executing migration tasks.

--verify
    Verify destination structure after execution.

--no-retry-failed
    Do not retry tasks currently marked failed.
```

Run:

```bash
drive-migrator --help
```

for the command's built-in help.

## Environment Variables

Drive Migrator recognizes:

```text
DRIVE_MIGRATOR_CREDENTIALS
DRIVE_MIGRATOR_STATE_DIR
```

For example:

```bash
export DRIVE_MIGRATOR_CREDENTIALS="$HOME/secrets/google-drive.json"
export DRIVE_MIGRATOR_STATE_DIR="$HOME/drive-migration-state"

drive-migrator \
    --source SOURCE_FOLDER_ID \
    --destination DESTINATION_FOLDER_ID \
    --fresh
```

## Project Structure

The source repository uses a standard Python `src` layout:

```text
drive-migrator/
├── pyproject.toml
├── README.md
├── .gitignore
└── src/
    └── drive_migrator/
        ├── __init__.py
        ├── __main__.py
        ├── cli.py
        ├── config.py
        ├── migrator_engine.py
        └── migration_helpers.py
```

The application does not depend on the repository remaining in any particular filesystem location after installation.

## Using Drive Migrator as a Library

The migration engine is also exposed as a Python package.

```python
from drive_migrator import DriveMigrator


migrator = DriveMigrator(
    credentials_path="/path/to/credentials.json",
)

manifest = migrator.generate_fresh_sync_manifest(
    source_id="SOURCE_FOLDER_ID",
    dest_id="DESTINATION_FOLDER_ID",
)

results = migrator.execute_migration()

verification = migrator.verify_destination()
```

A custom state directory can also be supplied:

```python
migrator = DriveMigrator(
    credentials_path="/path/to/credentials.json",
    state_dir="/path/to/state",
)
```

## Security

The following files should never be committed to source control:

```text
credentials.json
client_secret*.json
token.json
```

The included `.gitignore` excludes common credential and runtime-state filenames.

The OAuth token grants access according to the authorization granted to the application and should be treated as sensitive.

## Important Operational Notes

### The source is preserved

Drive Migrator creates a copy before moving anything into the destination. The original source object remains in its original location.

### Existing destination objects are reconciled

If the expected file or folder already exists at the normalized destination path, Drive Migrator attempts to reconcile it rather than blindly creating another copy.

### The manifest is persistent state

Once a migration begins, `migration_work_list.json` should be retained until the migration has been completed and verified.

Deleting it removes Drive Migrator's local record of migration progress.

### Google permissions still apply

Drive Migrator cannot bypass Google Drive permissions.

The authenticated account must have sufficient permissions to:

- Read source content
- Create source copies
- Create destination folders
- Add or move staged files into the destination

### Shared Drives are supported

Drive API operations are performed with Shared Drive support enabled where applicable.

## Development

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the project in editable mode:

```bash
python -m pip install -e .
```

The console command then executes the code directly from the local `src/` tree, so changes do not require reinstalling the package.

## License

No license has been specified yet.