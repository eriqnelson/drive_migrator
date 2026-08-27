import datetime
import json
import os
import subprocess
import sys
from pathlib import Path


def run_tests() -> int:
    """
    Run the full pytest suite and export test artifacts.

    Artifacts produced:
        test-results/junit-YYYYMMDD-HHMMSS.xml
        test-results/summary-YYYYMMDD-HHMMSS.json
        test-results/output-YYYYMMDD-HHMMSS.txt

    The project's src directory is added explicitly to PYTHONPATH so the
    test suite always exercises the current working tree, even when the
    package has not been installed into the active environment.

    The runner preserves pytest's exit code so it can be used in CI or
    other automation.
    """
    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    src_dir = (
        project_root / "src"
    )

    tests_dir = (
        project_root / "tests"
    )

    results_dir = (
        project_root / "test-results"
    )

    results_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = (
        datetime.datetime.now()
        .strftime("%Y%m%d-%H%M%S")
    )

    junit_path = (
        results_dir
        / f"junit-{timestamp}.xml"
    )

    summary_path = (
        results_dir
        / f"summary-{timestamp}.json"
    )

    output_path = (
        results_dir
        / f"output-{timestamp}.txt"
    )

    command = [
        sys.executable,
        "-m",
        "pytest",
        str(tests_dir),
        "-q",
        "--disable-warnings",
        "--maxfail=0",
        f"--junitxml={junit_path}",
    ]

    env = os.environ.copy()

    existing_pythonpath = env.get(
        "PYTHONPATH"
    )

    if existing_pythonpath:
        env["PYTHONPATH"] = (
            f"{src_dir}"
            f"{os.pathsep}"
            f"{existing_pythonpath}"
        )
    else:
        env["PYTHONPATH"] = str(
            src_dir
        )

    print("Running test suite...")
    print(
        f"Python executable: "
        f"{sys.executable}"
    )
    print(
        f"Project root: "
        f"{project_root}"
    )
    print(
        f"Source directory: "
        f"{src_dir}"
    )
    print(
        f"Results directory: "
        f"{results_dir}"
    )
    print()

    started_at = (
        datetime.datetime.now(
            datetime.timezone.utc
        )
    )

    result = subprocess.run(
        command,
        cwd=project_root,
        env=env,
        text=True,
        capture_output=True,
    )

    finished_at = (
        datetime.datetime.now(
            datetime.timezone.utc
        )
    )

    combined_output = ""

    if result.stdout:
        combined_output += (
            result.stdout
        )

    if result.stderr:
        if combined_output:
            combined_output += "\n"

        combined_output += (
            result.stderr
        )

    output_path.write_text(
        combined_output,
        encoding="utf-8",
    )

    if result.stdout:
        print(
            result.stdout
        )

    if result.stderr:
        print(
            result.stderr,
            file=sys.stderr,
        )

    summary = {
        "status": (
            "passed"
            if result.returncode == 0
            else "failed"
        ),
        "exit_code": (
            result.returncode
        ),
        "started_at": (
            started_at.isoformat()
        ),
        "finished_at": (
            finished_at.isoformat()
        ),
        "duration_seconds": (
            finished_at
            - started_at
        ).total_seconds(),
        "python_executable": str(
            sys.executable
        ),
        "project_root": str(
            project_root
        ),
        "source_directory": str(
            src_dir
        ),
        "tests_directory": str(
            tests_dir
        ),
        "command": command,
        "artifacts": {
            "junit_xml": str(
                junit_path
            ),
            "summary_json": str(
                summary_path
            ),
            "console_output": str(
                output_path
            ),
        },
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "Test runner summary:"
    )
    print(
        json.dumps(
            summary,
            indent=2,
        )
    )

    return result.returncode


if __name__ == "__main__":
    raise SystemExit(
        run_tests()
    )