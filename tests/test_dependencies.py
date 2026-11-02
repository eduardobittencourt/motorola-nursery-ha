"""Dependency input changes must regenerate the hash-locked CI environments."""

from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def input_requirements(path):
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("-r "):
            yield from input_requirements(path.parent / line[3:].strip())
        elif line:
            yield Requirement(line)


@pytest.mark.parametrize("environment", ["current", "minimum", "build"])
def test_ci_lock_matches_dependency_inputs(environment):
    source = (
        "requirements-test.txt"
        if environment == "current"
        else f"requirements-test-{environment}.txt"
    )
    lock = ROOT / f"requirements-test-{environment}.lock"
    locked = {
        canonicalize_name(req.name): req.specifier
        for line in lock.read_text().splitlines()
        if line and not line[0].isspace() and not line.startswith("#")
        for req in [Requirement(line.removesuffix("\\").strip())]
    }
    for requirement in input_requirements(ROOT / source):
        assert locked[canonicalize_name(requirement.name)] == requirement.specifier
