import argparse
import json

from .config import resolve_state_dir
from .migrator_engine import DriveMigrator


def build_parser() -> argparse.ArgumentParser:
    """
    Build and return the command-line argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="drive-migrator",
        description=(
            "Resumable structural migration tool for "
            "Google Drive and Shared Drives."
        ),
    )

    parser.add_argument(
        "--credentials",
        help=(
            "Path to the Google OAuth client-secret JSON file. "
            "May also be supplied with the "
            "DRIVE_MIGRATOR_CREDENTIALS environment variable."
        ),
    )

    parser.add_argument(
        "--state-dir",
        help=(
            "Directory used for persistent runtime state, including "
            "the OAuth token, migration manifest, and migration log. "
            "May also be supplied with the "
            "DRIVE_MIGRATOR_STATE_DIR environment variable."
        ),
    )

    parser.add_argument(
        "--source",
        help="Source root Google Drive folder ID.",
    )

    parser.add_argument(
        "--destination",
        help="Destination root Google Drive folder ID.",
    )

    parser.add_argument(
        "--fresh",
        action="store_true",
        help=(
            "Build a new migration manifest from the current "
            "source and destination state."
        ),
    )

    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help=(
            "Generate or load the migration manifest, "
            "but do not execute migration tasks."
        ),
    )

    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Verify the destination structure after "
            "migration execution."
        ),
    )

    parser.add_argument(
        "--no-retry-failed",
        action="store_true",
        help=(
            "Do not retry tasks currently marked as failed."
        ),
    )

    parser.add_argument(
        "--resolve-destination-collisions",
        action="store_true",
        help=(
            "Before building a fresh manifest, rename duplicate "
            "destination siblings so each file/folder path is "
            "unambiguous. This modifies the destination and "
            "therefore requires --fresh."
        ),
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help=(
            "Enable verbose operational logging."
        ),
    )

    return parser


def main() -> None:
    """
    Command-line entry point.
    """
    args = build_parser().parse_args()

    state_dir = resolve_state_dir(
        args.state_dir
    )

    migrator = DriveMigrator(
        credentials_path=args.credentials,
        state_dir=state_dir,
        verbose=args.verbose,
    )

    manifest_path = (
        state_dir
        / "migration_work_list.json"
    )

    manifest_exists = (
        manifest_path.exists()
        and manifest_path.stat().st_size > 0
    )

    if (
        args.resolve_destination_collisions
        and manifest_exists
        and not args.fresh
    ):
        raise SystemExit(
            "--resolve-destination-collisions requires --fresh "
            "when a migration manifest already exists."
        )

    if (
        args.fresh
        or not manifest_exists
    ):
        if (
            not args.source
            or not args.destination
        ):
            raise SystemExit(
                "--source and --destination are required "
                "when creating a new migration manifest."
            )

        manifest = (
            migrator.generate_fresh_sync_manifest(
                args.source,
                args.destination,
                resolve_destination_collisions=(
                    args.resolve_destination_collisions
                ),
            )
        )

        print(
            json.dumps(
                {
                    "manifest": str(
                        manifest_path
                    ),
                    "manifest_tasks": len(
                        manifest["tasks"]
                    ),
                    "state_dir": str(
                        state_dir
                    ),
                },
                indent=2,
            )
        )

    elif (
        args.source
        or args.destination
    ):
        print(
            "Existing migration manifest found. "
            "--source and --destination are ignored "
            "unless --fresh is supplied."
        )

    if args.manifest_only:
        return

    stats = migrator.execute_migration(
        retry_failed=(
            not args.no_retry_failed
        )
    )

    print(
        json.dumps(
            {
                "migration": stats
            },
            indent=2,
        )
    )

    if args.verify:
        verification = (
            migrator.verify_destination()
        )

        print(
            json.dumps(
                {
                    "verification": verification
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()