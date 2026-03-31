from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_semver_module():
    path = Path(__file__).resolve().parent.parent.parent / "scripts" / "semver_release.py"
    spec = importlib.util.spec_from_file_location("semver_release", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_classify_bump_prefers_major_breaking_changes():
    semver = _load_semver_module()

    commits = [
        semver.Commit(subject="feat: add release automation", body=""),
        semver.Commit(subject="refactor!: rename package metadata", body=""),
    ]

    assert semver.classify_bump(commits) == "major"


def test_classify_bump_uses_minor_for_features():
    semver = _load_semver_module()

    commits = [
        semver.Commit(subject="feat: automate release tagging", body=""),
        semver.Commit(subject="fix: tighten workflow checks", body=""),
    ]

    assert semver.classify_bump(commits) == "minor"


def test_classify_bump_defaults_to_patch_for_non_feature_commits():
    semver = _load_semver_module()

    commits = [
        semver.Commit(subject="Rename PyPI distribution", body=""),
        semver.Commit(subject="Fix npm publish tarball path", body=""),
    ]

    assert semver.classify_bump(commits) == "patch"


def test_bump_version_increments_expected_component():
    semver = _load_semver_module()

    assert semver.bump_version((1, 2, 3), "major") == "2.0.0"
    assert semver.bump_version((1, 2, 3), "minor") == "1.3.0"
    assert semver.bump_version((1, 2, 3), "patch") == "1.2.4"
