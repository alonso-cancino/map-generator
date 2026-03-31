#!/usr/bin/env python3
"""Automatically bump release versions from git history."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
PACKAGE_INIT_PATH = REPO_ROOT / "dcel_builder" / "__init__.py"
FRONTEND_PACKAGE_PATH = REPO_ROOT / "frontend" / "package.json"
FRONTEND_LOCK_PATH = REPO_ROOT / "frontend" / "package-lock.json"

SEMVER_TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
BREAKING_SUBJECT_PATTERN = re.compile(r"^[^:\n]+!:")
PYPROJECT_VERSION_PATTERN = re.compile(r'^(version = ")([^"]+)(")$', re.MULTILINE)
PACKAGE_FALLBACK_PATTERN = re.compile(r'^( {8}return ")([^"]+)(")$', re.MULTILINE)


@dataclass(frozen=True)
class Commit:
    subject: str
    body: str


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def latest_release_tag() -> str | None:
    try:
        output = git("describe", "--tags", "--abbrev=0", "--match", "v*.*.*")
    except subprocess.CalledProcessError:
        return None
    return output or None


def parse_version(version: str) -> tuple[int, int, int]:
    match = SEMVER_TAG_PATTERN.fullmatch(version)
    if not match:
        raise ValueError(f"Invalid semantic version tag: {version}")
    return tuple(int(part) for part in match.groups())


def bump_version(version: tuple[int, int, int], bump: str) -> str:
    major, minor, patch = version
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unknown bump level: {bump}")


def commits_since(tag: str | None) -> list[Commit]:
    revision = "HEAD" if tag is None else f"{tag}..HEAD"
    output = git("log", "--format=%s%x1f%b%x1e", revision)
    commits: list[Commit] = []
    for entry in output.split("\x1e"):
        if not entry.strip():
            continue
        subject, _, body = entry.partition("\x1f")
        commits.append(Commit(subject=subject.strip(), body=body.strip()))
    return commits


def classify_bump(commits: list[Commit]) -> str | None:
    if not commits:
        return None

    level = "patch"
    for commit in commits:
        subject = commit.subject.lower()
        body = commit.body.lower()
        if "breaking change" in body or BREAKING_SUBJECT_PATTERN.match(commit.subject):
            return "major"
        if subject.startswith(("feat", "add", "implement")):
            level = "minor"
    return level


def replace_regex(path: Path, pattern: re.Pattern[str], version: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, count = pattern.subn(rf"\g<1>{version}\g<3>", content, count=1)
    if count != 1:
        raise ValueError(f"Could not update version in {path}")
    path.write_text(updated, encoding="utf-8")


def update_json_version(path: Path, version: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = version
    if path == FRONTEND_LOCK_PATH:
        payload["packages"][""]["version"] = version
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def apply_version(version: str) -> None:
    replace_regex(PYPROJECT_PATH, PYPROJECT_VERSION_PATTERN, version)
    replace_regex(PACKAGE_INIT_PATH, PACKAGE_FALLBACK_PATTERN, version)
    update_json_version(FRONTEND_PACKAGE_PATH, version)
    update_json_version(FRONTEND_LOCK_PATH, version)


def next_release_version() -> tuple[str | None, str | None]:
    latest = latest_release_tag()
    commits = commits_since(latest)
    bump = classify_bump(commits)
    if bump is None:
        return None, None

    base = (0, 0, 0) if latest is None else parse_version(latest)
    return bump_version(base, bump), bump


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("plan", help="Print and emit the next semantic version")

    apply_parser = subparsers.add_parser("apply", help="Write a version into tracked files")
    apply_parser.add_argument("--version", required=True)

    args = parser.parse_args()

    if args.command == "plan":
        version, bump = next_release_version()
        changed = version is not None
        if changed:
            print(version)
            write_output("changed", "true")
            write_output("version", version)
            write_output("bump", bump or "")
        else:
            write_output("changed", "false")
        return

    if args.command == "apply":
        apply_version(args.version)
        return

    raise ValueError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    main()
