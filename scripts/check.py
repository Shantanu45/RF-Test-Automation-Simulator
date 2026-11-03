"""Run the same checks locally, in Compose, and in CI."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    output = Path(os.environ.get("CHECK_OUTPUT", "/artifacts"))
    output.mkdir(parents=True, exist_ok=True)
    commands = [
        [sys.executable, "-m", "pip", "check"],
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "src",
            "tests",
            "acceptance",
            "scripts",
        ],
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "src",
            "tests",
            "acceptance",
            "scripts",
        ],
        [sys.executable, "-m", "mypy", "--cache-dir=/tmp/rf-mypy", "src"],
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "acceptance",
            "--cov=rf_test_sim",
            f"--cov-report=xml:{output / 'coverage.xml'}",
            f"--junitxml={output / 'junit.xml'}",
        ],
    ]
    for command in commands:
        result = subprocess.run(command, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
