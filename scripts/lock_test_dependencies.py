"""Compile HA test locks and record their complete dependency input digest."""

from __future__ import annotations

import argparse
import hashlib
import shlex

# The generator invokes trusted uv directly, without a shell.
import subprocess  # nosec B404
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = ("current", "minimum", "build")
DIGEST_PREFIX = "# input-sha256: "


def requirement_lines(
    path: Path, parents: frozenset[Path] = frozenset()
) -> Iterator[str]:
    """Expand includes while retaining extras, markers and direct references."""
    path = path.resolve()
    if path in parents:
        raise ValueError("Cyclic requirements include")
    for raw in path.read_text().splitlines():
        line = raw.partition(" #")[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            yield from requirement_lines(
                path.parent / line[3:].strip(), parents | {path}
            )
        else:
            yield line


def input_digest(source: Path) -> str:
    """Hash expanded input lines, including extras, markers and direct references."""
    expanded = "\n".join(requirement_lines(source)) + "\n"
    return hashlib.sha256(expanded.encode()).hexdigest()


def record_input_digest(source: Path, lock: Path) -> None:
    """Replace lock metadata only after its dependency compilation succeeds."""
    lines = [
        line
        for line in lock.read_text().splitlines()
        if not line.startswith(DIGEST_PREFIX)
    ]
    lock.write_text(
        DIGEST_PREFIX + input_digest(source) + "\n" + "\n".join(lines) + "\n"
    )


def verify_lock_inputs(source: Path, lock: Path) -> None:
    """Reject a missing or stale digest of the complete dependency inputs."""
    expected = DIGEST_PREFIX + input_digest(source)
    if expected not in lock.read_text().splitlines():
        raise ValueError(f"Regenerate {lock.name}: dependency inputs changed")


def main() -> None:
    """Compile selected CI locks with pinned target settings and fresh metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environments", nargs="*", choices=ENVIRONMENTS)
    parser.add_argument("--upgrade", action="store_true")
    parser.add_argument("--upgrade-package", action="append", default=[])
    args = parser.parse_args()
    for environment in args.environments or ENVIRONMENTS:
        source = (
            "requirements-test.txt"
            if environment == "current"
            else f"requirements-test-{environment}.txt"
        )
        lock = f"requirements-test-{environment}.lock"
        regeneration = ["python", "scripts/lock_test_dependencies.py", environment]
        options = []
        if args.upgrade:
            options.append("--upgrade")
        for package in args.upgrade_package:
            options.extend(["--upgrade-package", package])
        command = [
            "uv",
            "pip",
            "compile",
            source,
            "--python-version",
            "3.14.8",
            "--python-platform",
            "x86_64-manylinux_2_39",
            "--generate-hashes",
            "--custom-compile-command",
            shlex.join(regeneration + options),
            "-o",
            lock,
            *options,
        ]
        # Only the fixed uv command and explicit CLI options are passed; no shell.
        subprocess.run(command, cwd=ROOT, check=True)  # nosec B603
        record_input_digest(ROOT / source, ROOT / lock)


if __name__ == "__main__":
    main()
